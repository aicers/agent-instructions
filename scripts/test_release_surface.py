#!/usr/bin/env python3
"""Tests for check_release_surface.sh.

The guard runs once per release, in the one job nobody watches until it
goes wrong, and what it decides — which tag is the previous release —
comes out of a sorted tag list rather than out of the commit graph. A tag
cut in the middle of the order is the case that separates the two, so the
fixture below cuts one deliberately.

A throwaway upstream is built in a temporary directory, with tags in a
creation order that disagrees with their version order.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "check_release_surface.sh"

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def release(
    root: Path, tag: str, *, blocks: str, notes: str, roster: str = "{}\n"
) -> None:
    (root / "blocks" / "demo.md").write_text(blocks, encoding="utf-8")
    (root / "README.md").write_text(notes, encoding="utf-8")
    (root / "repos.json").write_text(roster, encoding="utf-8")
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        tag,
    )
    git(root, "tag", tag)


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(GUARD), *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "upstream"
        (root / "blocks").mkdir(parents=True)
        git(root, "init", "-q", ".")

        release(root, "1.0.0", blocks="a rule\n", notes="first\n")
        release(root, "1.1.0", blocks="a changed rule\n", notes="second\n")
        # Neither path moved. README.md did, and it is mechanism: a change
        # to it reaches nobody from the tag. The release to refuse.
        release(root, "1.1.1", blocks="a changed rule\n", notes="third\n")
        # Cut after 1.1.1 but sorting below it: the predecessor is 1.0.0 by
        # version order and 1.1.1 by creation order, and its blocks match
        # 1.1.1's, so picking the wrong one turns this into a refusal.
        release(root, "1.0.1", blocks="a changed rule\n", notes="fourth\n")
        # Kept so a branch pinned to one does not break; never a predecessor.
        git(root, "tag", "v2")

        print("the first release")
        result = run(root, "1.0.0")
        check(result.returncode == 0, "exits 0")
        check(
            "no release before 1.0.0" in result.stdout,
            "says there was nothing to compare",
        )

        print("a release that changes only mechanism")
        result = run(root, "1.1.1")
        check(result.returncode != 0, "exits non-zero")
        check(
            "changed between 1.1.0 and 1.1.1" in result.stderr,
            "names both tags, and the monotonic v2 is not one of them",
        )

        print("a release cut below the newest tag")
        result = run(root, "1.0.1")
        check(result.returncode == 0, "exits 0")
        check(
            "comparing blocks/ and repos.json: 1.0.0 -> 1.0.1"
            in result.stdout,
            "compares against the previous tag in version order",
        )

        # repos.json says which blocks each repository takes, and apply.yml
        # reads it out of the release. Giving a repository another block is
        # therefore a release with nothing in blocks/ — which is exactly the
        # shape the guard used to refuse, back when it compared one path.
        print("a release that changes only repos.json")
        release(
            root,
            "1.2.0",
            blocks="a changed rule\n",
            notes="third\n",
            roster='{"repos": {"one": ["demo"]}}\n',
        )
        result = run(root, "1.2.0")
        check(result.returncode == 0, "exits 0")
        check(
            "comparing blocks/ and repos.json: 1.1.1 -> 1.2.0"
            in result.stdout,
            "compares both paths",
        )

        print("a release that changes neither path")
        release(
            root,
            "1.2.1",
            blocks="a changed rule\n",
            notes="fourth\n",
            roster='{"repos": {"one": ["demo"]}}\n',
        )
        result = run(root, "1.2.1")
        check(result.returncode != 0, "exits non-zero")
        check(
            "blocks/ and repos.json are both byte-identical"
            in result.stderr,
            "says both paths are unchanged",
        )

        # The guard resolves the previous release out of the tag list, so a
        # checkout that fetched no tags finds no predecessor for any tag —
        # indistinguishable from a first release unless it is checked for.
        # Reporting "nothing to compare" there would wave through exactly
        # the release this exists to refuse.
        print("a tag this checkout cannot see")
        result = run(root, "9.9.9")
        check(result.returncode != 0, "exits non-zero rather than passing")
        check(
            "no release tag '9.9.9' in this checkout" in result.stderr,
            "says the tag is missing rather than that there is nothing to"
            " compare",
        )

        print("no tag given")
        check(run(root).returncode == 2, "exits 2")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all check_release_surface.sh tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
