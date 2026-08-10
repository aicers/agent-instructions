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

# Repository names that are also ordinary English words. The rule is that
# a block must not *name a repository*, and for these the plain substring
# match cannot tell that from a block using the word: `review` joined the
# roster while blocks were already free to say "reviewer". Naming one of
# these reads as `aicers/review` or as a code span, so that is what is
# looked for; the word itself is left alone.
WORD_LIKE_REPOS = frozenset({"review"})


def names_repository(line: str, repo: str, org: str) -> bool:
    """Does this line name the repository, rather than merely contain it?"""
    if repo not in WORD_LIKE_REPOS:
        return repo in line
    qualified = rf"{re.escape(org)}/{re.escape(repo)}(?![\w-])"
    if re.search(qualified, line):
        return True
    return any(span.strip("`") == repo for span in CODE_SPAN.findall(line))


def main() -> int:
    roster = json.loads((ROOT / "repos.json").read_text())
    org = roster["org"]
    repos = set(roster["repos"])
    failures: list[str] = []

    for path in sorted((ROOT / "blocks").glob("*.md")):
        name = path.stem
        lines = path.read_text(encoding="utf-8").rstrip("\n").splitlines()
        where = path.relative_to(ROOT)

        if not re.fullmatch(rf"<!-- BEGIN shared:{re.escape(name)} -->",
                            lines[0]):
            failures.append(
                f"{where}:1: first line must be "
                f"'<!-- BEGIN shared:{name} -->'"
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
            # The markers carry the block's name, and a block may be named
            # after a repository — the one explaining the pipeline that
            # drives these repositories is. Which name they may carry was
            # settled above, against the filename.
            is_marker = number in (1, len(lines))
            if not is_marker:
                for repo in repos:
                    if names_repository(line, repo, org):
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
