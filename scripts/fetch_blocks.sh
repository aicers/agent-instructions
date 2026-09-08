#!/usr/bin/env bash
#
# Put one release's blocks somewhere the calling repository's tooling
# cannot see them.
#
#   scripts/fetch_blocks.sh <ref> <destination>
#
# `check-drift/action.yml` runs as a step inside a job the consumer
# already has, so the workspace it lands in belongs to that job rather
# than to this check. The reusable workflow can afford `actions/checkout`
# with a `path:`, because the job is its own and nothing else in it ever
# looks at the tree. A step cannot: the blocks are Markdown, and a job
# that later runs `markdownlint-cli2 "**/*.md"` -- or any other tree walk
# -- would be linting this repository's release. On a self-hosted runner,
# where the workspace persists between jobs, they would still be there
# for the next one.
#
# `actions/checkout` cannot place them anywhere else. It refuses a `path:`
# outside `$GITHUB_WORKSPACE` -- "Repository path ... is not under ..." --
# so the only safe location is one it will not write to, and this fetches
# them another way. The destination is `$RUNNER_TEMP`, which the runner
# clears between jobs and which no consumer's globs reach; the guard below
# refuses a destination inside the workspace outright, so that the
# constraint is enforced rather than merely intended.
#
# A tarball rather than a clone: one request, no `.git` left behind, and
# nothing to shallow-fetch. The API endpoint redirects to a signed
# codeload URL, and curl drops the Authorization header across that
# redirect on its own, which is what should happen.
#
# The whole tarball is extracted rather than just `blocks/`. Selecting a
# subtree needs `--wildcards` on GNU tar and must not be passed to BSD
# tar, and the destination is a scratch directory being deleted at the
# end of the step regardless. `-f -` names the pipe rather than relying
# on tar's default archive, which is a compile-time setting `$TAPE` can
# override.

set -euo pipefail

REPOSITORY=aicers/agent-instructions

ref=${1:-}
dest=${2:-}
if [[ -z $ref || -z $dest ]]; then
  echo "usage: scripts/fetch_blocks.sh <ref> <destination>" >&2
  exit 2
fi

# Resolve through the parent, so the destination itself does not have to
# exist yet and the check below still compares real paths rather than the
# two spellings a symlinked runner workspace has. Nothing is created
# first: a destination under the workspace must be refused without this
# having made a directory there on the way to refusing it.
parent=$(dirname "$dest")
if [[ ! -d $parent ]]; then
  echo "no such directory: $parent" >&2
  exit 2
fi
resolved="$(cd "$parent" && pwd -P)/$(basename "$dest")"

workspace=${GITHUB_WORKSPACE:-}
if [[ -n $workspace && -d $workspace ]]; then
  workspace=$(cd "$workspace" && pwd -P)
  if [[ "$resolved/" == "$workspace"/* ]]; then
    cat >&2 <<EOF
refusing to unpack $REPOSITORY into $resolved

That is inside the calling repository's workspace. These are Markdown
files, and this check runs as a step in a job doing other work: a linter
or any other tree walk in that job would pick them up, and on a runner
whose workspace persists they would outlive the run. Unpack them under
\$RUNNER_TEMP instead.
EOF
    exit 2
  fi
fi

# Only after the guard, and only on the resolved path.
rm -rf "$resolved"
mkdir -p "$resolved"

# `-H "Authorization:"` with no value tells curl to send no such header,
# which is the anonymous request a public repository still answers. An
# empty Bearer would be a bad credential rather than no credential.
token=${GH_TOKEN:-${GITHUB_TOKEN:-}}
if [[ -n $token ]]; then
  authorization="Authorization: Bearer $token"
else
  authorization="Authorization:"
fi

if ! curl -fsSL --retry 3 \
       -H "$authorization" \
       -H "X-GitHub-Api-Version: 2022-11-28" \
       "https://api.github.com/repos/$REPOSITORY/tarball/$ref" \
     | tar -xz -f - -C "$resolved" --strip-components=1; then
  echo "could not fetch $REPOSITORY at '$ref'" >&2
  exit 1
fi

echo "$REPOSITORY at $ref is in $resolved"
