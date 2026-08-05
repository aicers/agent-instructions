#!/usr/bin/env python3
"""Point a consuming repository's drift check at what the sync applied.

Two inputs to that check live in the caller's workflow file and have to
agree with what `sync.sh` just wrote: `instructions-ref`, the release
the blocks came from, and `blocks`, the list of them. The pin decides
what the comparison runs against, which is why it is the one
authoritative record of which release a repository carries, and why no
comment repeats it. The list decides which blocks are compared at all —
leave it naming a retired block and the check goes looking for a file
that release does not have.

    pin.py <tag> <repository-root> [block ...]

Exits non-zero when either input is missing, since a repository
consuming blocks without them would silently float.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PIN = re.compile(r"^(?P<lead>\s*)instructions-ref:\s*(?P<value>\S+)\s*$")
BLOCKS = re.compile(
    r"^(?P<lead>\s*)blocks:\s*(?P<quote>[\"']?)(?P<value>.*?)(?P=quote)\s*$"
)
NEARBY = 4


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("root", type=Path)
    parser.add_argument("blocks", nargs="*")
    args = parser.parse_args()

    workflows = args.root / ".github" / "workflows"
    wanted = " ".join(args.blocks)
    pins = 0
    lists = 0

    for path in sorted(workflows.glob("*.y*ml")):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

        # Both inputs sit in one `with:` mapping, so a `blocks:` that
        # belongs to the drift check shares the pin's indent and sits
        # within a line or two of it. Indent alone is not enough: any
        # other mapping at the same depth would match.
        anchors = [
            (i, m.group("lead"))
            for i, m in enumerate(PIN.match(l.rstrip("\n")) for l in lines)
            if m
        ]
        if not anchors:
            continue
        pins += 1

        def beside_pin(index: int, lead: str) -> bool:
            return any(
                lead == indent and abs(index - at) <= NEARBY
                for at, indent in anchors
            )

        out: list[str] = []
        notes: list[str] = []
        for index, line in enumerate(lines):
            bare = line.rstrip("\n")
            ending = "\n" if line.endswith("\n") else ""

            pin = PIN.match(bare)
            if pin:
                if pin.group("value") != args.tag:
                    notes.append(f"pinned to {args.tag}")
                out.append(f"{pin.group('lead')}instructions-ref: {args.tag}{ending}")
                continue

            blocks = BLOCKS.match(bare)
            if blocks and beside_pin(index, blocks.group("lead")):
                lists += 1
                if args.blocks:
                    if blocks.group("value").split() != args.blocks:
                        notes.append(f"blocks set to {wanted}")
                    quote = blocks.group("quote") or '"'
                    out.append(
                        f"{blocks.group('lead')}blocks: "
                        f"{quote}{wanted}{quote}{ending}"
                    )
                    continue

            out.append(line)

        if notes:
            path.write_text("".join(out), encoding="utf-8")
            where = path.relative_to(args.root)
            for note in dict.fromkeys(notes):
                print(f"{where}: {note}")

    if not pins:
        print(
            f"no instructions-ref pin under {workflows.relative_to(args.root)}"
            " — add the drift-check job before syncing this repository",
            file=sys.stderr,
        )
        return 1

    if args.blocks and not lists:
        print(
            "no blocks list beside the pin — the drift check compares"
            " nothing without one",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
