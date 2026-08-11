#!/usr/bin/env python3
"""Tests for pin_file.py.

The pin moved out of `.agents/`, and the reader still accepts the
old path so that the drift check — which runs these scripts from `@main`
against whatever path a repository's last apply wrote — does not turn
every repository red the moment the move lands. That compatibility window
is what these tests hold in place: it is invisible while it works, and
removing it early breaks repositories nobody was looking at.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PIN_FILE = Path(__file__).resolve().parent / "pin_file.py"
CURRENT = ".agent-instructions.toml"
LEGACY = Path(".agents") / "instructions.toml"

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


def repo(directory: str, *, current: str | None, legacy: str | None) -> Path:
    root = Path(directory)
    if current is not None:
        (root / CURRENT).write_text(current, encoding="utf-8")
    if legacy is not None:
        (root / LEGACY).parent.mkdir(parents=True, exist_ok=True)
        (root / LEGACY).write_text(legacy, encoding="utf-8")
    return root


def main() -> int:
    print("a repository on the current path")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=PIN, legacy=None)
        result = run("read", str(root))
        check(result.returncode == 0, "reads")
        check("ref=0.2.1" in result.stdout, "reports the ref")
        check("blocks=workflow rust" in result.stdout, "reports the blocks")

    print("a repository still on the superseded path")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None, legacy=PIN)
        result = run("read", str(root))
        check(result.returncode == 0, "reads, rather than failing as missing")
        check("ref=0.2.1" in result.stdout, "reports the ref")

    print("a write against a repository on the old path")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None, legacy=PIN)
        result = run("write", str(root), "0.3.0", "workflow", "rust")
        check(result.returncode == 0, "succeeds")
        check((root / CURRENT).is_file(), "writes the current path")
        check(not (root / LEGACY).exists(), "deletes the old file")
        check(
            not (root / LEGACY).parent.exists(),
            "removes the directory it was alone in",
        )
        # Both surviving is the state to avoid: the reader prefers the new
        # one, so the old would sit there naming a release nobody carries.
        check(
            run("read", str(root), "ref").stdout.strip() == "0.3.0",
            "leaves one pin, saying the release just written",
        )

    print("a write where the old directory holds something else")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None, legacy=PIN)
        (root / ".agents" / "notes.md").write_text("theirs", encoding="utf-8")
        run("write", str(root), "0.3.0", "workflow")
        check(not (root / LEGACY).exists(), "still deletes the old pin")
        check(
            (root / ".agents" / "notes.md").is_file(),
            "leaves a directory that is not empty alone",
        )

    print("a repository holding both")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(
            directory,
            current='ref = "0.3.0"\nblocks = ["workflow"]\n',
            legacy=PIN,
        )
        check(
            run("read", str(root), "ref").stdout.strip() == "0.3.0",
            "prefers the current path",
        )

    print("a repository holding neither")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current=None, legacy=None)
        result = run("read", str(root))
        check(result.returncode != 0, "fails")
        check(CURRENT in result.stderr, "names the current path, not the old")

    print("a pin that does not say both things")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current='ref = "0.3.0"\n', legacy=None)
        result = run("read", str(root))
        check(result.returncode != 0, "fails on a missing blocks list")
        check("blocks" in result.stderr, "says which key is missing")
    with tempfile.TemporaryDirectory() as directory:
        root = repo(directory, current='blocks = ["workflow"]\n', legacy=None)
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
