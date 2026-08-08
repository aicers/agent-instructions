#!/usr/bin/env python3
"""Read and write a consuming repository's `.agents/instructions.toml`.

    ref = "0.1.0"
    blocks = ["workflow", "rust"]

`ref` is the release of aicers/agent-instructions the repository carries;
`blocks` are the shared blocks it has. The drift check reads both — the
ref decides what the comparison runs against, the list decides what is
compared at all — and the apply rewrites both.

The file exists so that neither value lives in `.github/workflows/`.
GitHub refuses a push touching that directory when it is authenticated
with the default GITHUB_TOKEN, so a pin kept there forced every consumer
to mint and register a token of its own before the automation could run
once. Nothing else needed one. `.agents/` rather than `.github/`: only
`.github/workflows/` is closed, but this file is not GitHub's — it
records what the repository carries, and any driver can read it.

    pin_file.py read <repo-root> [ref|blocks]

prints `ref=<tag>` and `blocks=<space-separated>`, one per line — the
shape `$GITHUB_OUTPUT` takes — or just the named field's value, and fails
naming what is missing when the file does not say both things.

    pin_file.py write <repo-root> <tag> <block>...

replaces it with those two keys.

The standard library reads TOML only on 3.11 and later, and writes none
at all. Two keys of known shape do not justify a dependency in every
consumer's runner, so the file is emitted directly and parsed by the
reader below.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RELATIVE = Path(".agents") / "instructions.toml"
NAME = re.compile(r"[\w.-]+")

HEADER = """\
# What this repository carries from aicers/agent-instructions: the release
# it is on, and the shared blocks it has. Its drift check reads this file,
# and its apply job rewrites it. Which blocks a repository should carry is
# decided upstream in repos.json, not here.
"""

EXAMPLE = """\
    ref = "<release tag of aicers/agent-instructions>"
    blocks = ["workflow", "rust"]\
"""


class PinError(Exception):
    """The pin file does not say what it has to, or could not be written."""


def path_in(root: Path) -> Path:
    return root / RELATIVE


def dump(ref: str, blocks: list[str]) -> str:
    # Names come from repos.json, which CI checks against `blocks/`, so a
    # name that would need escaping is a bug upstream rather than input to
    # handle. Refuse it instead of emitting a file the reader cannot read.
    for block in blocks:
        if not NAME.fullmatch(block):
            raise PinError(f"{block!r} is not a usable block name")
    listed = ", ".join(f'"{block}"' for block in blocks)
    return f'{HEADER}ref = "{ref}"\nblocks = [{listed}]\n'


def write(root: Path, ref: str, blocks: list[str]) -> Path:
    path = path_in(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(ref, blocks), encoding="utf-8")
    return path


def uncomment(text: str) -> str:
    """Drop `#` comments, leaving a `#` inside a quoted value alone."""
    kept = []
    for line in text.splitlines():
        quote = ""
        for index, character in enumerate(line):
            if quote:
                if character == quote:
                    quote = ""
            elif character in "\"'":
                quote = character
            elif character == "#":
                line = line[:index]
                break
        kept.append(line)
    return "\n".join(kept)


def load(root: Path) -> tuple[str, list[str]]:
    path = path_in(root)
    if not path.is_file():
        raise PinError(
            f"{path}: no such file. A repository consuming shared"
            " instruction blocks records which release it carries and which"
            f" blocks it has. Create it with:\n\n{EXAMPLE}"
        )

    text = uncomment(path.read_text(encoding="utf-8"))

    ref = re.search(r"""(?m)^\s*ref\s*=\s*(["'])(?P<value>[^"']*)\1""", text)
    if not ref or not ref.group("value").strip():
        raise PinError(f'{path}: no ref = "<release tag>"')

    # A missing list is never an empty one. Read this file as naming no
    # blocks and the drift check would compare nothing while calling every
    # region the repository carries unlisted, and an apply would strip the
    # lot.
    listed = re.search(r"(?ms)^\s*blocks\s*=\s*\[(?P<value>.*?)\]", text)
    if not listed:
        raise PinError(f'{path}: no blocks = ["<name>", ...]')
    blocks = re.findall(r"""["']([^"']+)["']""", listed.group("value"))
    if not blocks:
        raise PinError(f"{path}: blocks is empty; name the blocks this"
                       " repository carries, or drop the file and the drift"
                       " check together")

    return ref.group("value").strip(), blocks


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="mode", required=True)

    reader = subcommands.add_parser("read")
    reader.add_argument("root", metavar="repo-root", type=Path)
    reader.add_argument("field", nargs="?", choices=("ref", "blocks"))

    writer = subcommands.add_parser("write")
    writer.add_argument("root", metavar="repo-root", type=Path)
    writer.add_argument("tag")
    writer.add_argument("blocks", nargs="+")

    args = parser.parse_args()

    try:
        if args.mode == "write":
            path = write(args.root, args.tag, args.blocks)
            print(f"{path}: {args.tag}, {' '.join(args.blocks)}")
            return 0

        ref, blocks = load(args.root)
    except PinError as error:
        print(error, file=sys.stderr)
        return 1

    values = {"ref": ref, "blocks": " ".join(blocks)}
    if args.field:
        print(values[args.field])
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
