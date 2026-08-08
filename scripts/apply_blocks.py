#!/usr/bin/env python3
"""Bring one consuming repository up to a release of the shared blocks.

    apply_blocks.py [--target FILE] <blocks-dir> <repo-root> <tag> <block>...

Applies each named block into `<repo-root>/<target>`, drops any block the
repository carries that the release no longer has or the caller no longer
names, and moves its drift-check pin to `<tag>`. It writes
`<repo-root>/<target>` and the workflow files under `<repo-root>`, and
nothing else — whether that tree is a throwaway clone or the checkout the
caller is standing in is the driver's business.

Two drivers need exactly this sequence: `sync.sh`, which a maintainer
runs against every repository at once, and `apply.yml`, which a consumer
schedules against itself. Writing it twice, once in bash and once in
workflow YAML, would make "the two agree" a promise rather than a
property. It lives here instead and both call it.

`render.py` and `pin.py` are driven through their command lines — the
contract their own tests cover — rather than imported and half
reimplemented here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RENDER = SCRIPTS / "render.py"
PIN = SCRIPTS / "pin.py"


def run(script: Path, *args: str) -> int:
    return subprocess.run([sys.executable, str(script), *args]).returncode


def carried(target: Path) -> list[str] | None:
    result = subprocess.run(
        [sys.executable, str(RENDER), "names", str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return None
    return result.stdout.split()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("blocks_dir", metavar="blocks-dir", type=Path)
    parser.add_argument("root", metavar="repo-root", type=Path)
    parser.add_argument("tag")
    parser.add_argument("blocks", nargs="*")
    parser.add_argument(
        "--target",
        default="AGENTS.md",
        help="file in the repository holding the blocks (default: AGENTS.md)",
    )
    args = parser.parse_args()

    # Naming nothing would remove every region the repository carries, since
    # each one is then a block it no longer lists. No driver means that:
    # sync.sh skips a repository whose list is empty, and apply.yml declares
    # the input required — but `required: true` accepts an empty string, and
    # `$BLOCKS` then expands to no arguments at all. Refuse it for the same
    # reason the empty blocks directory below is refused.
    if not args.blocks:
        print("name at least one block to apply", file=sys.stderr)
        return 1

    target = args.root / args.target
    if not target.is_file():
        print(f"{target}: no such file", file=sys.stderr)
        return 1

    # A block the repository lists that the release does not carry has been
    # retired upstream. Drop it here rather than failing: it is removed
    # below along with any unlisted block, and the pin then stops naming it,
    # which is what un-reds that repository's drift check. Failing instead
    # would make a retirement undeliverable by the one driver upstream
    # cannot edit the block list of.
    wanted = [b for b in args.blocks if (args.blocks_dir / f"{b}.md").is_file()]
    retired = [b for b in args.blocks if b not in wanted]
    if retired:
        print(f"{args.tag} has no {', '.join(retired)}; retiring here too")
    # Unless none of them exist, which is not a retirement — that is a
    # blocks directory pointing somewhere unintended, and applying it would
    # strip every region the repository has.
    if not wanted:
        print(
            f"{args.blocks_dir} carries none of the blocks this repository"
            " lists; refusing to treat that as retiring all of them",
            file=sys.stderr,
        )
        return 1

    # The pin goes first, before the target is touched. A repository with no
    # pin is not a consumer: nothing would compare what we are about to
    # write against upstream, so it would float. Failing here leaves the
    # target exactly as it was, which is what the drivers rely on — one
    # clones into a temporary directory, the other commits whatever it finds
    # changed.
    if run(PIN, args.tag, str(args.root), *wanted):
        return 1

    for block in wanted:
        if run(RENDER, "apply", str(target), str(args.blocks_dir / f"{block}.md")):
            return 1

    # A block this release does not have leaves its region behind otherwise:
    # nothing renders it, and the drift check only compares the blocks a
    # repository still lists, so a stale copy of a rule sits beside its
    # replacement with nothing to notice.
    present = carried(target)
    if present is None:
        return 1
    for name in present:
        if name not in wanted and run(RENDER, "remove", str(target), name):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
