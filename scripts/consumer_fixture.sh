#!/usr/bin/env bash
#
# Build a throwaway consumer of aicers/agent-instructions here.
#
#   scripts/consumer_fixture.sh <release tag>
#
# This repository is not one of its own consumers. It has no AGENTS.md and
# no `.agent-instructions.toml`, so the drift check has nothing here to
# run against, and `check-drift/action.yml` would otherwise ship exercised
# only by the thirteen repositories that call it -- which is to say, first
# exercised after it was published. A check that has never been seen to
# fail is not known to work.
#
# So `ci.yml` builds a consumer in its workspace and points the action at
# it. This writes the two files that makes one: a target file carrying a
# block, and a pin naming the release the block came from.
#
# The block is fetched from the release rather than taken from this
# checkout. `main` is normally ahead of the tag, so filling the fixture
# from the working tree would produce a consumer pinned to one release and
# carrying another -- which the check would fail, correctly, and for a
# reason that has nothing to do with what was being tested.
#
# One block, `workflow`: every consumer in repos.json carries it and every
# release has had it. Which block is compared is not what varies between
# the action and the workflow, so a second one would only lengthen the
# job this exists to keep short.

set -euo pipefail

BLOCK=workflow
TARGET=AGENTS.md

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)

ref=${1:-}
if [[ -z $ref ]]; then
  echo "usage: scripts/consumer_fixture.sh <release tag>" >&2
  exit 2
fi

# `mktemp -d` rather than a path under this directory: `fetch_blocks.sh`
# refuses to unpack inside `$GITHUB_WORKSPACE`, which is where the fixture
# is being built. On a runner TMPDIR is $RUNNER_TEMP, so this lands where
# the action puts its own copy.
blocks=$(mktemp -d)
trap 'rm -rf "$blocks"' EXIT

"$here/fetch_blocks.sh" "$ref" "$blocks/release"

# An empty marker pair is all a consumer has to write by hand; render.py
# fills it, the same way an apply fills it in a repository being onboarded.
printf '%s\n' \
  '# Instructions for AI coding agents' \
  '' \
  "<!-- BEGIN shared:$BLOCK -->" \
  "<!-- END shared:$BLOCK -->" \
  > "$TARGET"

python3 "$here/render.py" apply "$TARGET" "$blocks/release/blocks/$BLOCK.md"
python3 "$here/pin_file.py" write . "$ref" "$BLOCK"
