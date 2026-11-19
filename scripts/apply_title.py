#!/usr/bin/env python3
"""Title an apply pull request, and the commit it carries.

    apply_title.py <repo> <tree-ish> <tag>

prints `chore: update shared instruction blocks to <tag>` when the root of
<tree-ish> in the git repository <repo> holds any of the marker files
below, and `Update shared instruction blocks to <tag>` when it holds none.
A marker counts only as a file (a symlink included): a directory or a
submodule of the same name does not.

A repository holding a marker has moved to Conventional Commits titles
and tool-generated changelogs, and every title that lands on its default
branch is checked against `conventional-title/pattern.txt`; the title
these pull requests always had fails that check. A repository holding
none has not moved, and sees no change at all.

Both drivers call this -- `.github/workflows/apply.yml` and
`scripts/sync.sh` -- so the two cannot disagree about which repositories
have moved. Each passes its target's default branch as <tree-ish>: what
decides the title is what the repository has merged, not what the branch
being proposed carries, nor whatever a dispatched run was started on.
"""

from __future__ import annotations

import subprocess
import sys

MARKERS = ("release-plz.toml", "release-please-config.json", ".manual-release")

CONVENTIONAL = "chore: update shared instruction blocks to {tag}"
TRADITIONAL = "Update shared instruction blocks to {tag}"


def converted(repo: str, treeish: str) -> bool:
    # `ls-tree` on the root alone rather than a path lookup per marker:
    # one call. Each entry is `<mode> <type> <object>\t<name>`, and only a
    # blob counts -- a regular file, or a symlink, which git stores as one.
    # A directory (`tree`) or a submodule (`commit`) that happens to share a
    # marker's name is not a marker file, so `.manual-release/README.md`
    # leaves the repository unconverted.
    entries = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-z", treeish, "--"],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", "surrogateescape").split("\0")
    files = set()
    for entry in entries:
        header, tab, name = entry.partition("\t")
        if tab and header.split(" ")[1:2] == ["blob"]:
            files.add(name)
    return any(marker in files for marker in MARKERS)


def title(repo: str, treeish: str, tag: str) -> str:
    template = CONVENTIONAL if converted(repo, treeish) else TRADITIONAL
    return template.format(tag=tag)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: apply_title.py <repo> <tree-ish> <tag>", file=sys.stderr)
        return 2
    _, repo, treeish, tag = sys.argv
    try:
        print(title(repo, treeish, tag))
    except subprocess.CalledProcessError as failure:
        print(
            f"could not list {treeish} in {repo}:"
            f" {failure.stderr.decode(errors='replace').strip()}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
