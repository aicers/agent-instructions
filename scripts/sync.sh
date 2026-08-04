#!/usr/bin/env bash
#
# Fan out the current shared blocks to every consuming repository as pull
# requests, using the operator's own `gh` credentials. No bot account and
# no organization token are required.
#
#   scripts/sync.sh [--dry-run] <version-label> [repo ...]
#
# <version-label> names the branch (<github-username>/instructions-<label>)
# and appears in the commit subject. Pass repository names to limit the
# fan-out; the default is every repository in repos.json.
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
  echo "usage: scripts/sync.sh [--dry-run] <version-label> [repo ...]" >&2
  exit 2
fi
shift

config=$root/repos.json
query() { python3 -c "$1" "$config" "${2:-}"; }

org=$(query 'import json,sys; print(json.load(open(sys.argv[1]))["org"])')
target=$(query 'import json,sys; print(json.load(open(sys.argv[1]))["target"])')

repos=("$@")
if [[ ${#repos[@]} -eq 0 ]]; then
  while IFS= read -r line; do
    [[ -n $line ]] && repos+=("$line")
  done < <(query 'import json,sys
print("\n".join(json.load(open(sys.argv[1]))["repos"]))')
fi

user=$(gh api user --jq .login)
branch="$user/instructions-$label"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

opened=0
skipped=0

for repo in "${repos[@]}"; do
  blocks=()
  while IFS= read -r line; do
    [[ -n $line ]] && blocks+=("$line")
  done < <(query 'import json,sys
print("\n".join(json.load(open(sys.argv[1]))["repos"].get(sys.argv[2], [])))' \
    "$repo")

  if [[ ${#blocks[@]} -eq 0 ]]; then
    echo "==> $org/$repo: not in repos.json, skipping" >&2
    continue
  fi

  echo "==> $org/$repo (${blocks[*]})"
  gh repo clone "$org/$repo" "$work/$repo" -- --depth=1 --quiet

  for block in "${blocks[@]}"; do
    python3 "$root/scripts/render.py" apply \
      "$work/$repo/$target" "$root/blocks/$block.md"
  done

  if git -C "$work/$repo" diff --quiet; then
    echo "    already current, no pull request"
    skipped=$((skipped + 1))
    continue
  fi

  if $dry_run; then
    git -C "$work/$repo" --no-pager diff --stat
    opened=$((opened + 1))
    continue
  fi

  git -C "$work/$repo" switch -c "$branch" --quiet
  git -C "$work/$repo" commit -aqm "Update shared instruction blocks to $label

Synced from $org/agent-instructions. Do not edit the marked blocks in this
repository; change them upstream and re-run the sync."
  git -C "$work/$repo" push -q -u origin HEAD

  gh pr create -R "$org/$repo" \
    --head "$branch" \
    --title "Update shared instruction blocks to $label" \
    --body "Synced from \`$org/agent-instructions\` by \`scripts/sync.sh\`.

Blocks in this pull request: ${blocks[*]}

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
