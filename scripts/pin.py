#!/usr/bin/env python3
"""Move a consuming repository's instructions-ref pin to a release tag.

The pin lives in the caller's workflow file, as the `instructions-ref`
input to the drift check. It decides what the comparison runs against,
so it is the one authoritative record of which release a repository
carries — and the reason no comment repeats it.

    pin.py <tag> <repository-root>

Exits non-zero when no pin is found, since a repository that consumes
blocks without one would silently float.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PIN = re.compile(r"^(?P<lead>\s*instructions-ref:\s*)(?P<value>\S+)\s*$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    workflows = args.root / ".github" / "workflows"
    found = 0
    changed = 0

    for path in sorted(workflows.glob("*.y*ml")):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        out: list[str] = []
        touched = False
        for line in lines:
            match = PIN.match(line.rstrip("\n"))
            if not match:
                out.append(line)
                continue
            found += 1
            if match.group("value") == args.tag:
                out.append(line)
                continue
            ending = "\n" if line.endswith("\n") else ""
            out.append(f"{match.group('lead')}{args.tag}{ending}")
            touched = True
        if touched:
            path.write_text("".join(out), encoding="utf-8")
            changed += 1
            print(f"pinned {path.relative_to(args.root)} to {args.tag}")

    if not found:
        print(
            f"no instructions-ref pin under {workflows.relative_to(args.root)}"
            " — add the drift-check job before syncing this repository",
            file=sys.stderr,
        )
        return 1

    if not changed:
        print(f"already pinned to {args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
