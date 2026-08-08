#!/usr/bin/env bash
#
# Refuse a release that has nothing in it for a consumer.
#
#   scripts/check_release_surface.sh <new-tag>
#
# `blocks/` is the entire surface a consumer sees. Everything else here is
# mechanism and reaches a consumer from `@main` — the reusable workflows
# and the scripts they run — so it is deliberately not compared, and this
# guard needs no path list. A tag whose `blocks/` tree is byte-identical
# to the previous release's would give every consumer a pull request whose
# only content is a moved pin, which is churn dressed as an update.
#
# The previous release is the tag immediately below <new-tag> in
# MAJOR.MINOR.PATCH order, over the tags release.yml triggers on. The
# monotonic v1 and v2 tags that predate the scheme are ignored: they are
# kept so that a branch still pinned to one does not break, not compared
# against.
#
# Requires history and tags, so it runs after an actions/checkout with
# fetch-depth: 0 and fetch-tags: true. Without them the previous tag
# cannot resolve, and the guard would pass while comparing nothing.

set -euo pipefail

new_tag=${1:-}
if [[ -z $new_tag ]]; then
  echo "usage: scripts/check_release_surface.sh <new-tag>" >&2
  exit 2
fi

tags=$(git tag --list | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V || true)

# `grep -B1 -Fx` prints the predecessor together with the match, so the
# first line is the predecessor. For the first release tag, or one that
# sorts below every existing tag, that first line is the tag itself.
prev_tag=$(printf '%s\n' "$tags" | grep -B1 -Fx "$new_tag" | head -n1 || true)

if [[ -z $prev_tag || $prev_tag == "$new_tag" ]]; then
  echo "no release before $new_tag; nothing to compare"
  exit 0
fi

echo "comparing blocks/: $prev_tag -> $new_tag"

if git diff --quiet "$prev_tag" "$new_tag" -- blocks/; then
  cat >&2 <<EOF
blocks/ is byte-identical between $prev_tag and $new_tag.

There is nothing here for a consumer to apply: every repository would get
a pull request that moves its pin and changes no rule. Scripts and
workflows reach consumers from @main rather than from the tag, so a change
to one of those is not a reason to cut a release either. This tag should
not have been cut.
EOF
  exit 1
fi

echo "blocks/ differs; proceeding"
