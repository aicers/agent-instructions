#!/usr/bin/env bash
#
# Fan out the current shared blocks to every consuming repository as pull
# requests, using the operator's own `gh` credentials. No bot account and
# no organization token are required.
#
#   scripts/sync.sh [--dry-run] <tag> [repo ...]
#
# This is the urgent path. Normally each consumer applies a release to
# itself on a schedule, through `.github/workflows/apply.yml`, and nobody
# has to remember anything. Reach for this script when a release should
# not wait for the next scheduled run — withdrawing a rule, say — or to
# push a repository that has not been onboarded to the scheduled job yet.
#
# <tag> is a release tag of this repository, already pushed. Each
# consuming repository gets its blocks rewritten and its
# .agents/instructions.toml moved to that tag, in one pull request on
# <github-username>/instructions-<tag>. Pass repository names to limit
# the fan-out; the default is every repository in repos.json.
#
# What is applied is that tag's tree, fetched from origin — its blocks/
# and its repos.json — not this checkout's, which is normally ahead of
# the tag being synced.
#
# --dry-run clones and renders, then prints the diff each pull request
# would carry, without branching, committing, or pushing anything.
#
# Repositories whose blocks are already current are skipped.
#
# Written for bash 3.2, the version macOS ships.

set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

dry_run=false
if [[ ${1:-} == --dry-run ]]; then
  dry_run=true
  shift
fi

label=${1:-}
if [[ -z $label ]]; then
  echo "usage: scripts/sync.sh [--dry-run] <tag> [repo ...]" >&2
  exit 2
fi
shift

# Consumers check out the blocks at this tag. Syncing to one that does
# not exist yet would pin every repository to a ref their CI cannot
# resolve, so refuse before touching anything.
if ! git -C "$root" ls-remote --exit-code --tags origin \
     "refs/tags/$label" >/dev/null 2>&1; then
  echo "no tag '$label' on origin - tag the release first" >&2
  exit 2
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# What gets applied is the release, not this checkout. The two are rarely
# the same tree: the tag was cut somewhere in main's past and whoever runs
# this is standing on main. Applying what happens to be checked out here
# while writing $label into every consumer's pin file would open pull
# requests that are wrong the moment they merge — the pin naming one
# release and the blocks beside it coming from another, which the next
# drift check reports as the consumer's divergence. So materialize the tag
# and hand that to apply_blocks.py.
#
# The driver stays this checkout's: you run the sync.sh you have. It is
# the release payload that has to be the release.
release=$work/release
mkdir -p "$release"
git -C "$root" fetch --quiet --no-tags origin "refs/tags/$label"
git -C "$root" archive FETCH_HEAD | tar -xf - -C "$release"

# repos.json comes from the release for the same reason, and it is the
# copy apply_blocks.py reads. Resolving the fan-out from a different one
# would let this loop admit a repository the apply then refuses, aborting
# a fan-out that has already opened pull requests.
config=$release/repos.json
query() { python3 -c "$1" "$config" "${2:-}"; }

org=$(query 'import json,sys; print(json.load(open(sys.argv[1]))["org"])')

repos=("$@")
if [[ ${#repos[@]} -eq 0 ]]; then
  while IFS= read -r line; do
    [[ -n $line ]] && repos+=("$line")
  done < <(query 'import json,sys
print("\n".join(json.load(open(sys.argv[1]))["repos"]))')
fi

user=$(gh api user --jq .login)
branch="$user/instructions-$label"

opened=0
skipped=0

for repo in "${repos[@]}"; do
  # Which blocks this repository takes is apply_blocks.py's to resolve,
  # out of repos.json. All this needs to know is whether it is listed at
  # all, so that a mistyped name on the command line is skipped here
  # rather than aborting a fan-out that has already opened pull requests.
  if ! query 'import json,sys
sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["repos"] else 1)' \
       "$repo"; then
    echo "==> $org/$repo: not in repos.json, skipping" >&2
    continue
  fi

  echo "==> $org/$repo"
  # Under $work/repos/ rather than $work/ directly, so that a repository
  # named like the release directory cannot land on top of it.
  clone=$work/repos/$repo
  gh repo clone "$org/$repo" "$clone" -- --depth=1 --quiet

  # Applying the blocks, retiring the ones repos.json dropped, and moving
  # the pin is one sequence, and `apply.yml` needs the same one. It lives
  # in apply_blocks.py so the two drivers cannot disagree.
  python3 "$root/scripts/apply_blocks.py" \
    "$release" "$clone" "$repo" "$label"

  blocks=$(python3 "$root/scripts/pin_file.py" read "$clone" blocks)

  if git -C "$clone" diff --quiet; then
    echo "    already current, no pull request"
    skipped=$((skipped + 1))
    continue
  fi

  if $dry_run; then
    git -C "$clone" --no-pager diff --stat
    opened=$((opened + 1))
    continue
  fi

  git -C "$clone" switch -c "$branch" --quiet
  git -C "$clone" commit -aqm "Update shared instruction blocks to $label

Synced from $org/agent-instructions at $label, which the drift check is
now pinned to. Do not edit the marked blocks in this repository; change
them upstream, tag a release, and re-run the sync."
  git -C "$clone" push -q -u origin HEAD

  gh pr create -R "$org/$repo" \
    --head "$branch" \
    --title "Update shared instruction blocks to $label" \
    --body "Synced from \`$org/agent-instructions\` by \`scripts/sync.sh\`.

Blocks in this pull request: $blocks

The marked blocks are generated. Change the wording upstream in
\`$org/agent-instructions\` rather than editing it here — the drift check in CI
will fail if this repository's copy diverges."
  opened=$((opened + 1))
done

if $dry_run; then
  echo "dry run: $opened repository/repositories would get a pull request,"\
       "$skipped already current"
else
  echo "$opened pull request(s) opened, $skipped already current"
fi
