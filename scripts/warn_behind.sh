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
#
# Asked with curl rather than with `gh`, because this runs as a step
# inside the caller's job and that job may be on a self-hosted runner.
# Those hosts carry git, python3, curl and tar; they do not carry `gh`,
# and the fleet's rule is that the machine provides a tool and keeps it
# current -- one more entry on that list to save a `curl` is the wrong
# trade. It is also the failure nobody would see: `gh` missing takes the
# branch below, which says it could not compare and stays green, so the
# repository whose schedule stopped is told nothing on the very check
# that runs everywhere to tell it. `gh release view` with no tag reads
# this endpoint, so the question is the one that was being asked before.
#
# `-H "Authorization:"` with no value sends no such header, which is the
# anonymous request a public repository still answers; an empty Bearer
# would be a bad credential rather than none. Same token and same
# treatment as `scripts/fetch_blocks.sh`, which says the rest.
token=${GH_TOKEN:-${GITHUB_TOKEN:-}}
if [[ -n $token ]]; then
  authorization="Authorization: Bearer $token"
else
  authorization="Authorization:"
fi

# python3 for the field rather than a grep over the response: how the API
# lays that JSON out is the API's to change, and this repository already
# needs the interpreter for check_drift.py below. A python3 that is not
# there therefore fails here too, which is the same "could not resolve"
# branch -- not a warning, and not a failed job.
#
# `or ""` rather than the subscript, so that a body carrying no usable
# tag comes out empty and meets the same check an empty answer does.
# Printed straight, a JSON null would arrive as the string "None" and be
# warned about as though it were a release somebody could go and get.
#
# The traceback goes to /dev/null. What it says is that the body was not
# a release, which is the line below, and it says it in fifteen lines of
# Python on a pull request that has nothing to do with any of this --
# from a step whose whole point is not to look like something is wrong.
# curl keeps its stderr, so the transport failure behind a 404 or a
# timeout is still named; a run that reaches the parser and fails there
# is the one where curl said nothing.
tag_name='import json, sys; print(json.load(sys.stdin).get("tag_name") or "")'

# A repository with no releases answers 404, which `-f` turns into a
# non-zero exit; so does a network that is not there, and so does a body
# with no tag in it. All three are the same thing to this step: a lookup
# that could not be performed, which is not the same as a pin that is
# behind and does not get the warning that belongs to one.
api="https://api.github.com/repos/$REPOSITORY/releases/latest"
if ! latest=$(curl -fsSL --retry 3 \
                -H "$authorization" \
                -H "X-GitHub-Api-Version: 2022-11-28" \
                "$api" |
              python3 -c "$tag_name" 2>/dev/null) || [[ -z $latest ]]; then
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
