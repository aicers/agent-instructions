#!/usr/bin/env python3
"""Tests for lint_blocks.py.

The repository-name check is the part worth pinning down. It reads the
roster rather than a fixed list, so a repository named after an ordinary
English word decides what every block may say — and the two exemptions
that makes necessary are exactly the kind of thing a later tightening
would undo without noticing.

The linter takes no arguments and resolves its root from its own
location, so each case builds a throwaway tree with a copy of the script
in it. Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LINTER = Path(__file__).resolve().parent / "lint_blocks.py"

ROSTER = {
    "org": "aicers",
    "target": "AGENTS.md",
    "repos": {
        "bootroot": ["demo"],
        "review": ["demo"],
        "review-database": ["demo"],
        "agentcoop": ["demo"],
    },
}

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def lint(
    name: str, body: str = "", *, raw: str | None = None
) -> subprocess.CompletedProcess:
    """Lint one block, named `name`, whose body sits between the markers.

    `raw` writes the file verbatim instead, for the cases about the
    markers themselves.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "scripts").mkdir()
        shutil.copy(LINTER, root / "scripts" / LINTER.name)
        (root / "repos.json").write_text(json.dumps(ROSTER), encoding="utf-8")
        (root / "blocks").mkdir()
        (root / "blocks" / f"{name}.md").write_text(
            raw
            if raw is not None
            else f"<!-- BEGIN shared:{name} -->\n{body}"
            f"<!-- END shared:{name} -->\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(root / "scripts" / LINTER.name)],
            capture_output=True,
            text=True,
        )


def main() -> int:
    print("a block named after a repository")
    # Its own markers carry that name. Nothing else may, which is what
    # the filename check above already decides.
    result = lint("agentcoop", "## AgentCoop\n\n- text\n")
    check(result.returncode == 0, "passes on its own markers")
    check(
        "agentcoop" not in result.stdout,
        "does not report the name in the markers",
    )

    print("a repository name that is also an ordinary word")
    result = lint("demo", "## Demo\n\n- the reviewer reviews it\n")
    check(result.returncode == 0, "passes when the word is prose")
    result = lint("demo", "## Demo\n\n- see aicers/review for the rest\n")
    check(result.returncode != 0, "fails when the name is org-qualified")
    check("'review'" in result.stdout, "names the repository it caught")
    result = lint("demo", "## Demo\n\n- see `review` for the rest\n")
    check(result.returncode != 0, "fails when the name is a code span")
    result = lint("demo", "## Demo\n\n- see `review-database` for it\n")
    check(
        result.returncode != 0 and "review-database" in result.stdout,
        "still catches a longer name the word is a prefix of",
    )

    print("a repository name that is not an ordinary word")
    result = lint("demo", "## Demo\n\n- bootroot does it this way\n")
    check(result.returncode != 0, "fails on a bare mention in prose")

    print("the rest of the authoring rules")
    result = lint("demo", "## Demo\n\n- " + "x" * 80 + "\n")
    check(result.returncode != 0, "fails a line over 76 columns")
    result = lint("demo", "## Demo\n\n* text\n")
    check(result.returncode != 0, "fails a '*' bullet")
    result = lint("demo", "## Demo\n\n- a @path reference\n")
    check(result.returncode != 0, "fails a bare '@'")
    result = lint("demo", "## Demo\n\n- a `@path` reference\n")
    check(result.returncode == 0, "allows '@' inside a code span")

    print("a block whose markers do not match its filename")
    # What the marker exemption above rests on: the name a marker carries
    # is not free, it has to be the filename.
    result = lint(
        "demo",
        raw="<!-- BEGIN shared:other -->\n- text\n<!-- END shared:other -->\n",
    )
    check(result.returncode != 0, "fails the marker check")
    check("first line must be" in result.stdout, "says which line is wrong")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all lint_blocks.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
