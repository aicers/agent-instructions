#!/usr/bin/env python3
"""Tests for render.py.

Ten repositories' CI depends on render.py, so its command-line contract
is what gets tested: exit codes, what lands on disk, and what is left
alone. Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

RENDER = Path(__file__).resolve().parent / "render.py"

BLOCK = """<!-- BEGIN shared:demo v2 -->
## Demo

- current text
<!-- END shared:demo -->
"""

OTHER = """<!-- BEGIN shared:other v1 -->
## Other

- untouched
<!-- END shared:other -->
"""

failures: list[str] = []


def run(mode: str, target: Path, block: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RENDER), mode, str(target), str(block)],
        capture_output=True,
        text=True,
    )


def check(condition: bool, description: str) -> None:
    if condition:
        print(f"  ok   {description}")
    else:
        print(f"  FAIL {description}")
        failures.append(description)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        block = root / "demo.md"
        block.write_text(BLOCK, encoding="utf-8")
        other = root / "other.md"
        other.write_text(OTHER, encoding="utf-8")

        stale = (
            "# Title\n\n"
            "<!-- BEGIN shared:demo v1 -->\n"
            "stale text\n"
            "<!-- END shared:demo -->\n\n"
            f"{OTHER}\n"
            "## Repository section\n\n"
            "- local content\n"
        )

        print("drift detection")
        target = root / "AGENTS.md"
        target.write_text(stale, encoding="utf-8")
        result = run("check", target, block)
        check(result.returncode == 1, "check exits 1 on drift")
        check("current text" in result.stdout, "check prints a diff")
        check(
            target.read_text(encoding="utf-8") == stale,
            "check leaves the file untouched",
        )

        print("apply")
        result = run("apply", target, block)
        text = target.read_text(encoding="utf-8")
        check(result.returncode == 0, "apply exits 0")
        check("stale text" not in text, "apply removes the old body")
        check("- current text" in text, "apply writes the new body")
        check(
            "<!-- BEGIN shared:demo v2 -->" in text,
            "apply updates the version on the marker",
        )
        check(
            text.startswith("# Title\n") and text.endswith("- local content\n"),
            "apply preserves content outside the markers",
        )
        check("- untouched" in text, "apply leaves a sibling block alone")

        print("verification after apply")
        check(run("check", target, block).returncode == 0, "check exits 0")
        check(
            run("check", target, other).returncode == 0,
            "the sibling block is also current",
        )

        print("idempotence")
        before = target.read_text(encoding="utf-8")
        run("apply", target, block)
        check(
            target.read_text(encoding="utf-8") == before,
            "re-applying changes nothing",
        )

        print("malformed input")
        bare = root / "bare.md"
        bare.write_text("no markers here\n", encoding="utf-8")
        check(run("check", bare, block).returncode != 0, "check fails without markers")
        check(run("apply", bare, block).returncode != 0, "apply fails without markers")
        check(
            bare.read_text(encoding="utf-8") == "no markers here\n",
            "a file without markers is not modified",
        )

        reversed_markers = root / "reversed.md"
        reversed_markers.write_text(
            "<!-- END shared:demo -->\nx\n<!-- BEGIN shared:demo v1 -->\n",
            encoding="utf-8",
        )
        check(
            run("apply", reversed_markers, block).returncode != 0,
            "out-of-order markers are rejected",
        )

        headless = root / "headless.md"
        headless.write_text("## Not a marker\n", encoding="utf-8")
        check(
            run("apply", target, headless).returncode != 0,
            "a block file without a BEGIN marker is rejected",
        )

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all render.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
