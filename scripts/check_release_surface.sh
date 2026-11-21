#!/usr/bin/env bash
#
# Compare the consumer-facing files at HEAD with the last release.
# Consumers take the rules, roster and title pattern from their pinned
# release. The reusable workflows, actions and scripts come from @main.
# Run with full history and tags so the latest plain version is available.

set -euo pipefail

if [[ $# -ne 0 ]]; then
  echo "usage: scripts/check_release_surface.sh" >&2
  exit 2
fi

last_tag=$(git tag --list --sort=-version:refname \
  | awk '/^[0-9]+\.[0-9]+\.[0-9]+$/ && !found { print; found=1 }')
if [[ -z $last_tag ]]; then
  echo "This checkout has no release tags (plain X.Y.Z). Fetch full history and tags." >&2
  exit 2
fi

surface=(blocks/ repos.json conventional-title/pattern.txt)
changed=$(
  git diff --raw --no-abbrev --no-renames -z "refs/tags/$last_tag" HEAD -- "${surface[@]}" \
    | while IFS= read -r -d '' entry && IFS= read -r -d '' path; do
        read -r _ _ before after status <<< "$entry"
        # Executable bits do not change what consumers read. File type
        # changes, which can replace a file with a symlink, still count.
        if [[ $before == "$after" && $status != T ]]; then
          continue
        fi
        if [[ $path == blocks/* ]]; then
          path=blocks/
        fi
        printf '%s\n' "$path"
      done | sort -u | paste -sd' ' -
)

echo "Comparing blocks/, repos.json and conventional-title/pattern.txt: $last_tag -> HEAD"
if [[ -z $changed ]]; then
  echo "blocks/, repos.json and conventional-title/pattern.txt are byte-identical at $last_tag and HEAD." >&2
  exit 1
fi

echo "Changed release surface: $changed"
