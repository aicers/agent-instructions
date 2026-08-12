#!/usr/bin/env python3
"""Tests for pin_file.py.

The pin moved out of `.agents/`, and the reader accepted the old path
until every repository had been carried off it by an apply. That window
is closed, so one of these tests holds the other end of it: a repository
that turns up on the old path is a repository restored from a branch
older than the move, and it is told to create the file rather than read
silently from one nothing else writes.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PIN_FILE = Path(__file__).resolve().parent / "pin_file.py"
CURRENT = ".agent-instructions.toml"
# Kept only to build a repository that is on it, which is now an error.
SUPERSEDED = Path(".agents") / "instructions.toml"

PIN = 'ref = "0.2.1"\nblocks = ["workflow", "rust"]\n'

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIN_FILE), *args], capture_output=True, text=True
    )


def repo(directory: str, *, current: str | None,
         superseded: str | None = None) -> Path:
    root = Path(directory)
    if current is not None:
        (root / CURRENT).write_text(current, encoding="utf-8")
    if superseded is not None:
        (root / SUPERSEDED).parent.mkdir(parents=True, exist_ok=True)
        (root / SUPERSEDED).write_text(superseded, encoding="utf-8")
    return root


def main() -> int:
    print("a repository on the current path")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=PIN)
        result = run("read", str(root))
        check(result.returncode == 0, "reads")
        check("ref=0.2.1" in result.stdout, "reports the ref")
        check("blocks=workflow rust" in result.stdout, "reports the blocks")

    print("a repository on the superseded path")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None, superseded=PIN)
        result = run("read", str(root))
        # Every repository was carried onto the current path by an apply
        # before this stopped being read. One arriving on it now was
        # restored from a branch older than that move, and reading it would
        # report a release from a file no driver has written since.
        check(result.returncode != 0, "fails rather than reading it")
        check(CURRENT in result.stderr, "names the path the file belongs at")
        check("0.2.1" not in result.stdout, "reports no ref from it")

    print("a write")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None)
        result = run("write", str(root), "0.3.0", "workflow", "rust")
        check(result.returncode == 0, "succeeds")
        check((root / CURRENT).is_file(), "writes the current path")
        check(
            run("read", str(root), "ref").stdout.strip() == "0.3.0",
            "reads back the release just written",
        )

    print("a repository holding neither")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None)
        result = run("read", str(root))
        check(result.returncode != 0, "fails")
        check(CURRENT in result.stderr, "names the current path, not the old")

    print("a pin that does not say both things")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current='ref = "0.3.0"\n')
        result = run("read", str(root))
        check(result.returncode != 0, "fails on a missing blocks list")
        check("blocks" in result.stderr, "says which key is missing")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current='blocks = ["workflow"]\n')
        result = run("read", str(root))
        check(result.returncode != 0, "fails on a missing ref")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all pin_file.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
