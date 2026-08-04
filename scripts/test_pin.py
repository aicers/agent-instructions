#!/usr/bin/env python3
"""Tests for pin.py.

The pin is the only record of which release a repository carries, so a
silent no-op here would leave a repository claiming a version it does
not have.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PIN = Path(__file__).resolve().parent / "pin.py"

WORKFLOW = """name: CI

on: [pull_request]

jobs:
  instructions:
    uses: aicers/agent-instructions/.github/workflows/check-drift.yml@main
    with:
      blocks: "workflow rust"
      instructions-ref: v1
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
"""

failures: list[str] = []


def run(tag: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIN), tag, str(root)],
        capture_output=True,
        text=True,
    )


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def repo(root: Path, body: str, name: str = "ci.yml") -> Path:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / name
    path.write_text(body, encoding="utf-8")
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "consumer"
        path = repo(root, WORKFLOW)

        print("moving the pin")
        result = run("v3", root)
        text = path.read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        check("instructions-ref: v3" in text, "the pin moves to the new tag")
        check("instructions-ref: v1" not in text, "the old tag is gone")
        check("      instructions-ref:" in text, "indentation is preserved")
        check("- run: echo build" in text, "the rest of the file is untouched")
        check(
            text.count("uses: aicers/agent-instructions") == 1,
            "the workflow reference is left alone",
        )

        print("idempotence")
        before = path.read_text(encoding="utf-8")
        result = run("v3", root)
        check(result.returncode == 0, "re-pinning exits 0")
        check(
            path.read_text(encoding="utf-8") == before,
            "re-pinning changes nothing",
        )
        check("already pinned" in result.stdout, "re-pinning says so")

        print("several workflow files")
        multi = Path(tmp) / "multi"
        first = repo(multi, WORKFLOW, "ci.yml")
        second = repo(multi, WORKFLOW.replace("v1", "v2"), "nightly.yaml")
        check(run("v4", multi).returncode == 0, "exits 0")
        check(
            "instructions-ref: v4" in first.read_text(encoding="utf-8")
            and "instructions-ref: v4" in second.read_text(encoding="utf-8"),
            "every workflow file is pinned, including .yaml",
        )

        print("a repository with no pin")
        bare = Path(tmp) / "bare"
        unpinned = repo(bare, "name: CI\non: [push]\n")
        result = run("v3", bare)
        check(result.returncode != 0, "exits non-zero rather than silently")
        check("add the drift-check job" in result.stderr, "says what to do")
        check(
            unpinned.read_text(encoding="utf-8") == "name: CI\non: [push]\n",
            "nothing is written",
        )

        print("a repository with no workflows at all")
        empty = Path(tmp) / "empty"
        empty.mkdir()
        check(run("v3", empty).returncode != 0, "exits non-zero")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all pin.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
