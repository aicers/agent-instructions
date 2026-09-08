#!/usr/bin/env bash
#
# Say, on a consumer's pull request, that its pin is behind the latest
# release -- and exit 0 whatever happens on the way.
#
#   scripts/warn_behind.sh <pin>
#
# Run from the calling repository's working tree, which is where the
# branch listing comes from. `scripts/check_drift.py` decides what to say;
# this is the part that talks to the network, and it holds the two answers
# apart -- a listing that could not be fetched is not an empty one.
#
# `check-drift.yml` does this inline and wraps the step in
# `continue-on-error: true`, for the reason its comment gives: the step
# must not decide the job even when it is the step that broke. Going red
# because a release exists upstream is the exact outcome this warns
# instead of producing, and a check that cries wolf gets ignored.
#
# `continue-on-error` does not exist for a step inside a composite action,
# so the action cannot say that and this script says it instead: every
# path out of here is `exit 0`. What is lost is that a broken step now
# reads as green rather than as failed-but-not-blocking -- the failure is
# still in the log, but nothing marks the run. The half that matters is
# unchanged.
#
# Including the argument check. A missing pin is a bug in the caller
# rather than a hiccup, and a caller here is `check-drift/action.yml` at
# `@main` -- so shipping one would turn every consumer's pull request red
# at once, which is the one thing this file exists to prevent. It says so
# in the log and leaves the job alone.
#
# The inline copy in `check-drift.yml` stays. Sharing this with it would
# quietly convert a step that shows as failed-but-not-blocking into one
# that shows as green, in the workflow thirteen repositories call today,
# for no gain to any of them.

set -uo pipefail

REPOSITORY=aicers/agent-instructions

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)

pin=${1:-}
if [[ -z $pin ]]; then
  echo "usage: scripts/warn_behind.sh <pin>" >&2
  exit 0
fi

# "Latest release", not "latest tag", for apply.yml's reason: a tag that
# was never released has not passed the release-surface guard. It is also
# what the apply would deliver, so this names the release dispatching that
# job would actually bring.
if ! latest=$(gh release view --repo "$REPOSITORY" \
                --json tagName --jq .tagName); then
  echo "could not resolve the latest release; nothing to compare"
  exit 0
fi

# The branches say whether the apply ran. `--heads` with a pattern prints
# nothing and exits 0 when none matches, which is the ordinary case in a
# repository that is up to date -- so a non-zero exit here really is a
# listing that could not be fetched, and that is a different thing from an
# empty one. An empty listing says the apply pushed nothing; an unreadable
# one says nothing at all, and passing it off as empty warns the
# repository whose update branch may be sitting right there.
# `--branches-unknown` tells the script which it got; it stays quiet for
# that one run rather than crying wolf.
unknown=""
if ! branches=$(git ls-remote --heads origin 'shared-instructions/*'); then
  echo "could not list this repository's branches"
  branches=""
  unknown="--branches-unknown"
fi

# $unknown is that flag or the empty string, and is meant to split away to
# nothing when it is the empty string.
printf '%s\n' "$branches" |
  python3 "$here/check_drift.py" $unknown "$pin" "$latest"

# Unconditional, and the reason for `set -uo pipefail` rather than
# `set -euo pipefail` above: a python3 that is not there, or a
# check_drift.py that raises, must not reach the job either.
exit 0
