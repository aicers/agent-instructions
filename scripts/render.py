#!/usr/bin/env python3
"""Apply or verify a shared instruction block inside a consuming repository.

A block is delimited in the target file by

    <!-- BEGIN shared:<name> v<N> -->
    ...
    <!-- END shared:<name> -->

`apply` replaces everything between (and including) the markers with the
current contents of the block file. `check` reports drift without writing.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("apply", "check"))
    parser.add_argument("target", type=Path)
    parser.add_argument("block", type=Path)
    args = parser.parse_args()

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
