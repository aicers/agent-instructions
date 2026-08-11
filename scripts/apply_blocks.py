#!/usr/bin/env python3
"""Bring one consuming repository up to a release of the shared blocks.

    apply_blocks.py <release> <repo-root> <repository> <tag>

`<release>` is a checkout of this repository at `<tag>`: its `blocks/`
supplies the text and its `repos.json` says which blocks `<repository>`
should carry and which file holds them. `<repository>` is the consuming
repository's name, with or without its owner — `github.repository` passes
straight through. `<repo-root>` is the tree to write into; whether that
is a throwaway clone or the checkout the caller is standing in is the
driver's business.

Applies each of those blocks into `<repo-root>/<target>`, drops any block
the repository carries that the release no longer has or `repos.json` no
longer lists, and records the release and the list in
`<repo-root>/.agent-instructions.toml`. It writes that file and the
target, and nothing else — a `target` that resolves outside the
repository is refused rather than followed.

Intent lives upstream and state lives downstream: `repos.json` says which
blocks a repository *should* consume, the pin file says what it *does*
carry. This script moves the second toward the first, which is what lets
a newly added block reach a repository whose own files upstream cannot
edit.

Two drivers need exactly this sequence: `sync.sh`, which a maintainer
runs against every repository at once, and `apply.yml`, which a consumer
schedules against itself. Writing it twice, once in bash and once in
workflow YAML, would make "the two agree" a promise rather than a
property. It lives here instead and both call it.

`render.py` and `pin_file.py` are driven through their command lines —
the contract their own tests cover — rather than imported and half
reimplemented here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RENDER = SCRIPTS / "render.py"
PIN_FILE = SCRIPTS / "pin_file.py"


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
    parser.add_argument("release", type=Path)
    parser.add_argument("root", metavar="repo-root", type=Path)
    parser.add_argument("repository")
    parser.add_argument("tag")
    args = parser.parse_args()

    config = args.release / "repos.json"
    try:
        registry = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"{config}: {error}", file=sys.stderr)
        return 1

    # `github.repository` is `owner/name`; sync.sh has the bare name. Both
    # are the same repository, and repos.json is keyed by name under one
    # `org`.
    name = args.repository.rsplit("/", 1)[-1]
    listed = registry.get("repos", {}).get(name)
    if listed is None:
        print(
            f"{name} is not in {config} — add it there with the blocks it"
            " should consume, in the release being applied",
            file=sys.stderr,
        )
        return 1
    # Naming nothing would remove every region the repository carries, since
    # each one is then a block it no longer lists. Refuse it for the same
    # reason the release carrying none of them is refused below.
    if not listed:
        print(f"{name} lists no blocks in {config}", file=sys.stderr)
        return 1

    # This script is documented to write nothing outside `<repo-root>`. An
    # absolute target discards the root entirely, a relative one can climb
    # out of it, and a symlink inside the tree can point anywhere -- so
    # resolve both sides, which follows links, and refuse a target that
    # lands elsewhere. Not a privilege boundary: a consumer already owns the
    # runner it schedules this on. It is the difference between a mistyped
    # value failing where it was read and it quietly rewriting a file
    # nothing here should touch.
    wanted_target = registry.get("target", "AGENTS.md")
    root = args.root.resolve()
    target = (root / wanted_target).resolve()
    if not target.is_relative_to(root):
        print(f"{wanted_target}: outside {args.root}", file=sys.stderr)
        return 1
    if not target.is_file():
        print(f"{target}: no such file", file=sys.stderr)
        return 1

    # A repository whose pin file is missing, or does not say both things,
    # is not a consumer: nothing would compare what we are about to write
    # against upstream, so it would float. Reading it is how that is
    # checked, since the reader already names what a repository has to fix.
    # It happens before the target is touched, which is what the drivers
    # rely on -- one clones into a temporary directory, the other commits
    # whatever it finds changed.
    readable = subprocess.run(
        [sys.executable, str(PIN_FILE), "read", str(root)],
        capture_output=True,
        text=True,
    )
    if readable.returncode:
        sys.stderr.write(readable.stderr)
        return 1

    blocks_dir = args.release / "blocks"

    # A block repos.json lists that the release does not carry has been
    # retired upstream. Drop it here rather than failing: it is removed
    # below along with any unlisted block, and the pin file then stops
    # naming it, which is what un-reds that repository's drift check.
    wanted = [b for b in listed if (blocks_dir / f"{b}.md").is_file()]
    retired = [b for b in listed if b not in wanted]
    if retired:
        print(f"{args.tag} has no {', '.join(retired)}; retiring here too")
    # Unless none of them exist, which is not a retirement — that is a
    # release checkout pointing somewhere unintended, and applying it would
    # strip every region the repository has.
    if not wanted:
        print(
            f"{blocks_dir} carries none of the blocks {name} lists;"
            " refusing to treat that as retiring all of them",
            file=sys.stderr,
        )
        return 1

    if run(PIN_FILE, "write", str(root), args.tag, *wanted):
        return 1

    for block in wanted:
        if run(RENDER, "apply", str(target), str(blocks_dir / f"{block}.md")):
            return 1

    # A block this release does not have leaves its region behind otherwise:
    # nothing renders it, and the drift check only compares the blocks the
    # pin file lists, so a stale copy of a rule sits beside its replacement
    # with nothing to notice.
    present = carried(target)
    if present is None:
        return 1
    for block in present:
        if block not in wanted and run(RENDER, "remove", str(target), block):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
