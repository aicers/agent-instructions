#!/usr/bin/env python3
"""Apply or verify a shared instruction block inside a consuming repository.

A block is delimited in the target file by

    <!-- BEGIN shared:<name> -->
    ...
    <!-- END shared:<name> -->

A BEGIN marker still carrying the `v<N>` that markers used to have is
matched too, and `apply` replaces it with the current form. Repositories
onboarded before the version was dropped still have them, and nothing
upstream can edit a consumer's file except through this script.

`apply` replaces everything between (and including) the markers with the
current contents of the block file. `check` reports drift without writing.

A block file's name is `<block>.md`, or `<block>.<variant>.md` for a
variant of it, and either one carries the markers `shared:<block>`. The
region is named from the file's own BEGIN marker, never from its
filename, so applying a different variant rewrites the same region and
keeps its markers where they are.

When the target has no region for the block, `apply` inserts one rather
than failing, provided the file has at least one shared region to place
it against. Each `--after <name>` names a block that comes before this one
in the repository's list, nearest first; the new region goes right after
the END marker of the first of those the file carries. With none of them
in the file it goes right before the first shared region. A file with no
shared region at all still fails: where the generated text starts in a
file nothing has generated into yet is a decision for whoever onboards
it, and nothing here can make it.

`names` prints the block names a file carries, and `remove` deletes a
marker pair and its content. A block retired upstream leaves its region
behind otherwise: nothing renders it, and the drift check only compares
the blocks a repository still lists, so a stale copy of a rule sits
alongside its replacement with nothing to notice.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

# Not `\b` after the name: a hyphen is a word boundary, so `shared:commit`
# would otherwise find `shared:commit-messages`.
BEGIN = r"<!--\s*BEGIN shared:{name}(?![\w.-])[^>]*-->"
END = r"<!--\s*END shared:{name}\s*-->"


def block_name(block_path: Path) -> str:
    first = block_path.read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"BEGIN shared:([\w.-]+)", first)
    if not match:
        sys.exit(f"{block_path}: first line is not a BEGIN marker")
    return match.group(1)


def span(text: str, name: str, target: Path) -> tuple[int, int]:
    begin = re.search(BEGIN.format(name=re.escape(name)), text)
    end = re.search(END.format(name=re.escape(name)), text)
    if not begin or not end:
        sys.exit(f"{target}: no shared:{name} block; add the markers first")
    if end.start() < begin.start():
        sys.exit(f"{target}: shared:{name} markers are out of order")
    return begin.start(), end.end()


def names(text: str) -> list[str]:
    return re.findall(r"<!--\s*BEGIN shared:([\w.-]+)\b[^>]*-->", text)


def has(text: str, name: str) -> bool:
    """Does the file carry a region for `name`, either marker of it?

    Either rather than both: a file with only one of the pair is broken,
    and inserting a fresh pair beside the half that is there would hide
    that rather than fail on it, which `span` then does.
    """
    escaped = re.escape(name)
    return bool(
        re.search(BEGIN.format(name=escaped), text)
        or re.search(END.format(name=escaped), text)
    )


def insert(
    text: str, want: str, after: list[str], target: Path
) -> str | None:
    """Place a region the file does not have yet.

    After the nearest preceding block the file carries, so a block added
    to a repository's list lands where the list puts it. The separator
    that already followed that block's END marker is kept as it was, and
    the new region is set off from it by one blank line, the way the
    regions beside it are.
    """
    for name in after:
        if has(text, name):
            _, stop = span(text, name, target)
            return text[:stop] + "\n\n" + want + text[stop:]
    first = re.search(r"<!--\s*BEGIN shared:[\w.-]+\b[^>]*-->", text)
    if first is None:
        return None
    return text[:first.start()] + want + "\n\n" + text[first.start():]


def remove(target: Path, name: str) -> int:
    text = target.read_text(encoding="utf-8")
    if name not in names(text):
        print(f"{target}: no shared:{name} block to remove")
        return 0
    start, stop = span(text, name, target)
    # Collapse to exactly one blank line where the region was, so removing a
    # block leaves no scar and the file stays idempotent under markdownlint.
    head = text[:start].rstrip("\n")
    tail = text[stop:].lstrip("\n")
    joined = f"{head}\n\n{tail}" if head and tail else f"{head}{tail}"
    target.write_text(joined.rstrip("\n") + "\n", encoding="utf-8")
    print(f"removed shared:{name} from {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("apply", "check", "names", "remove"))
    parser.add_argument("target", type=Path)
    parser.add_argument("block", type=Path, nargs="?")
    parser.add_argument(
        "--after",
        action="append",
        default=[],
        metavar="name",
        help="apply only: a block listed before this one, nearest first",
    )
    args = parser.parse_args()

    if args.mode == "names":
        for found in names(args.target.read_text(encoding="utf-8")):
            print(found)
        return 0

    if args.mode == "remove":
        if args.block is None:
            sys.exit("remove needs a block name")
        return remove(args.target, str(args.block))

    if args.block is None:
        sys.exit(f"{args.mode} needs a block file")
    name = block_name(args.block)
    want = args.block.read_text(encoding="utf-8").rstrip("\n")
    text = args.target.read_text(encoding="utf-8")

    if args.mode == "apply" and not has(text, name):
        placed = insert(text, want, args.after, args.target)
        if placed is None:
            sys.exit(
                f"{args.target}: no shared:{name} block; add the markers first"
            )
        args.target.write_text(placed, encoding="utf-8")
        print(f"added shared:{name} to {args.target}")
        return 0

    start, stop = span(text, name, args.target)
    have = text[start:stop]

    if have == want:
        return 0

    if args.mode == "check":
        diff = difflib.unified_diff(
            have.splitlines(),
            want.splitlines(),
            fromfile=f"{args.target} (local)",
            tofile=f"{args.block} (upstream)",
            lineterm="",
        )
        print("\n".join(diff))
        print(f"\nshared:{name} is out of date in {args.target}")
        return 1

    args.target.write_text(text[:start] + want + text[stop:], encoding="utf-8")
    print(f"updated shared:{name} in {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
