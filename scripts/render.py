#!/usr/bin/env python3
"""Apply or verify a shared instruction block inside a consuming repository.

A block is delimited in the target file by

    <!-- BEGIN shared:<name> v<N> -->
    ...
    <!-- END shared:<name> -->

`apply` replaces everything between (and including) the markers with the
current contents of the block file. `check` reports drift without writing.

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

BEGIN = r"<!--\s*BEGIN shared:{name}\b[^>]*-->"
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
