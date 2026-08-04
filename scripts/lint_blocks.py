#!/usr/bin/env python3
"""Enforce the authoring rules that let a block drop into any repository.

See STYLE.md. The rules exist so that a block passes every consumer's
markdownlint configuration and so that the drift check stays a plain byte
comparison — which means no repository-specific names or paths.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAX_WIDTH = 76
ROOT = Path(__file__).resolve().parent.parent
CODE_SPAN = re.compile(r"`[^`]*`")


def main() -> int:
    repos = set(json.loads((ROOT / "repos.json").read_text())["repos"])
    failures: list[str] = []

    for path in sorted((ROOT / "blocks").glob("*.md")):
        name = path.stem
        lines = path.read_text(encoding="utf-8").rstrip("\n").splitlines()
        where = path.relative_to(ROOT)

        if not re.fullmatch(rf"<!-- BEGIN shared:{re.escape(name)} v\d+ -->",
                            lines[0]):
            failures.append(
                f"{where}:1: first line must be "
                f"'<!-- BEGIN shared:{name} v<N> -->'"
            )
        if not re.fullmatch(rf"<!-- END shared:{re.escape(name)} -->",
                            lines[-1]):
            failures.append(
                f"{where}:{len(lines)}: last line must be "
                f"'<!-- END shared:{name} -->'"
            )

        in_fence = False
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if len(line) > MAX_WIDTH:
                failures.append(
                    f"{where}:{number}: {len(line)} columns exceeds "
                    f"{MAX_WIDTH}"
                )
            if not in_fence and re.match(r"\s*\*\s", line):
                failures.append(
                    f"{where}:{number}: use '-' for bullets, not '*'"
                )
            if not in_fence and "@" in CODE_SPAN.sub("", line):
                failures.append(
                    f"{where}:{number}: bare '@' — Claude Code parses "
                    f"'@path' in an imported file as another import. "
                    f"Wrap it in backticks."
                )
            for repo in repos:
                if repo in line:
                    failures.append(
                        f"{where}:{number}: mentions the repository "
                        f"'{repo}'; blocks must be repository-neutral"
                    )

    for failure in failures:
        print(failure)
    if failures:
        print(f"\n{len(failures)} problem(s)")
        return 1
    print("blocks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
