#!/usr/bin/env bash
#
# Refuse a release that has nothing in it for a consumer.
#
#   scripts/check_release_surface.sh <new-tag>
#
# The surface a consumer sees is `blocks/`, `repos.json` and
# `conventional-title/pattern.txt`: the text of the rules, which of them
# each repository takes, and the title rule. `apply.yml` reads the first
# two out of the release, and every checker of a title reads the third
# at the release a repository pins, so a change to any of them is
# something a consumer takes by moving its pin. Everything else here is
# mechanism and reaches a consumer from `@main` — the reusable workflows,
# the actions, and the scripts they run — so it is deliberately not
# compared.
#
# A tag matching the previous release across all three paths would give
# every consumer a pull request whose only content is a moved pin, which
# is churn dressed as an update.
#
# `repos.json` was not always part of this. Until the pin moved out of the
# caller's workflow file, `blocks:` was an input each consumer passed and
# `repos.json` was upstream bookkeeping nobody downstream ever read — so
# this guard compared one path and said it needed no list. Adding a block
# to a repository is now a release, and comparing only `blocks/` refused
# the one release that carries it.
#
# The previous release is the tag immediately below <new-tag> in
# MAJOR.MINOR.PATCH order, over the tags release.yml triggers on. The
# monotonic v1 and v2 tags that predate the scheme are ignored: they are
# kept so that a branch still pinned to one does not break, not compared
# against.
#
# Requires history and tags, so it runs after an actions/checkout with
# fetch-depth: 0 and fetch-tags: true. Without them no tag resolves, so
# the guard refuses to run rather than reporting a comparison it never
# made.

set -euo pipefail

new_tag=${1:-}
if [[ -z $new_tag ]]; then
  echo "usage: scripts/check_release_surface.sh <new-tag>" >&2
  exit 2
fi

tags=$(git tag --list | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V || true)

# A tag that is not in the list resolves no predecessor, which reads
# exactly like a first release. It is not one: it is a checkout that
# fetched no tags, and treating it as "nothing to compare" would wave
# through the release this guard exists to refuse. Separate the two
# before the search rather than inferring afterwards.
if ! printf '%s\n' "$tags" | grep -qFx "$new_tag"; then
  echo "no release tag '$new_tag' in this checkout - tag the release" \
       "first, and check out with fetch-depth: 0 and fetch-tags: true" >&2
  exit 2
fi

# `grep -B1 -Fx` prints the predecessor together with the match, so the
# first line is the predecessor. For the first release tag, or one that
# sorts below every existing tag, that first line is the tag itself.
prev_tag=$(printf '%s\n' "$tags" | grep -B1 -Fx "$new_tag" | head -n1)

if [[ $prev_tag == "$new_tag" ]]; then
  echo "no release before $new_tag; nothing to compare"
  exit 0
fi

surface=(blocks/ repos.json conventional-title/pattern.txt)

echo "comparing blocks/, repos.json and conventional-title/pattern.txt:" \
     "$prev_tag -> $new_tag"

if git diff --quiet "$prev_tag" "$new_tag" -- "${surface[@]}"; then
  cat >&2 <<EOF
Nothing a consumer applies changed between $prev_tag and $new_tag.

blocks/, repos.json and conventional-title/pattern.txt are all
byte-identical, so every repository would get a pull request that moves
its pin and changes neither a rule, nor which rules it takes, nor the
title rule. Scripts, actions and workflows reach consumers from @main
rather than from the tag, so a change to one of those is not a reason to
cut a release either. This tag should not have been cut.
EOF
  exit 1
fi

# Name what actually moved. Saying "blocks/ differs" was wrong for every
# release that changed only repos.json, which both releases since the
# guard started comparing it have been. Every file under blocks/ is named
# as blocks/; the other two are single files and named as themselves.
changed=$(git diff --name-only "$prev_tag" "$new_tag" -- "${surface[@]}" \
          | sed 's#^blocks/.*#blocks/#' | sort -u | paste -sd' ' -)
echo "$changed differs; proceeding"
