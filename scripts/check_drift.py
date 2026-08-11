#!/usr/bin/env python3
"""Say, on a consumer's pull request, that its pin is behind the latest
release.

    check_drift.py [--branches-unknown] <pin> <latest release>
        < <branch listing>

`check-drift.yml` reads the pin and resolves the latest release, and
hands both here with `git ls-remote --heads origin 'shared-instructions/*'`
on standard input. This prints one `::warning::` line when the repository
is behind, and nothing when it is not.

A warning rather than a failure, and the distinction is the point. A
repository's pull requests have nothing to do with which release of the
shared instructions it carries, and turning them red because a release
exists upstream is exactly what pinning is for. A check that cries wolf
gets ignored, and then it is no longer catching the drift it was written
for either. The annotation appears on the pull request and in the run
summary; the check still passes.

What it is looking for is a schedule that has stopped. GitHub disables a
scheduled workflow in a repository that has seen no activity for 60 days,
and does so silently -- no failed run, no notification, nothing on any
pull request. A repository that goes quiet for two months simply stops
proposing releases to itself, and the only symptom is the absence of pull
requests nobody was expecting on a particular day. `workflow_dispatch`
recovers it, but only for somebody who already suspects.

Silent in three cases, all of which would otherwise make the warning
furniture:

- The repository is on the latest release. Nothing to say.
- The branch `shared-instructions/<latest release>` is already on the
  repository. The apply pushed it, so the schedule ran; somebody has not
  merged the pull request yet, which is a different situation and one
  this warning cannot help with.
- The listing could not be read, which the driver says with
  `--branches-unknown`. An empty listing means the apply pushed nothing;
  an unreadable one rules nothing out, and reading the second as the
  first warns the repository whose update branch may be sitting right
  there. Quiet loses one run's worth of a warning that repeats on every
  pull request; the alternative is the false positive the branch case
  exists to prevent.

The branch rather than the pull request, though the pull request is what
a reader would think of. Listing pull requests needs `pull-requests:
read`, and a reusable workflow can only narrow the caller's token, never
widen it -- so every consumer's `ci.yml` would have to grant it by hand,
in the one directory nothing upstream may write. A branch is a ref, which
`contents: read` already covers, and it answers the same question.

The comparison lives here rather than inline in the workflow because
every test in this repository exercises a script and none exercises a
workflow file. `scripts/test_check_drift.py` covers it.
"""

from __future__ import annotations

import argparse
import sys

BRANCH = "shared-instructions/{tag}"

WARNING = (
    "::warning::This repository carries shared instruction blocks from"
    " aicers/agent-instructions {pin}, and the latest release is {latest}."
    " Run the \"Update shared instructions\" workflow from this"
    " repository's Actions tab to get the pull request that updates them."
    " Nothing in this pull request is wrong: the weekly job that would"
    " have proposed {latest} may have stopped, which GitHub does silently"
    " to a schedule in a repository nobody has touched for 60 days."
)


def version(tag: str) -> tuple[int, ...] | None:
    """The tag as numbers to compare, or None if it is not that shape.

    Release tags are `MAJOR.MINOR.PATCH`. The monotonic `v1` and `v2`
    predate that scheme and are kept so a repository pinned to one does
    not break, so a pin can still be one of them -- and such a pin is
    behind by definition, which the caller below decides rather than this.
    """
    parts = tag.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def behind(pin: str, latest: str) -> bool:
    """Whether `pin` names an older release than `latest`.

    Behind, not merely different. A pin *ahead* of the latest release is
    somebody testing an unreleased tag by hand, and telling them to
    dispatch a job that would move them backwards is noise -- the one
    thing this must not produce.
    """
    if pin == latest:
        return False
    here, there = version(pin), version(latest)
    if here is None or there is None:
        # Nothing orders these two. They differ, and every tag that is not
        # `MAJOR.MINOR.PATCH` predates every one that is, so a pin that
        # cannot be compared is an old pin.
        return True
    width = max(len(here), len(there))
    pad = (0,) * width
    return (here + pad)[:width] < (there + pad)[:width]


def branches(listing: str) -> set[str]:
    """Branch names out of `git ls-remote --heads` output.

    Each line is `<sha>\\t<ref>`; blank lines are what an empty listing
    arrives as, and are not branches.

    The whole name, matched whole by the caller. `git ls-remote` matches
    its pattern against the tail of a ref at slash boundaries, so a
    listing asked for `shared-instructions/*` also carries somebody's
    `feature/shared-instructions/0.3.0` -- which the apply did not push,
    and which must not answer for it.
    """
    names = set()
    for line in listing.splitlines():
        ref = line.split("\t")[-1].strip()
        if not ref:
            continue
        names.add(ref.removeprefix("refs/heads/"))
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pin")
    parser.add_argument("latest", metavar="latest-release")
    parser.add_argument(
        "--branches-unknown",
        action="store_true",
        help="the branch listing could not be fetched; it is not empty",
    )
    args = parser.parse_args()

    # Read the listing before deciding anything, including in the case
    # that never looks at it. The driver pipes it in, and a process that
    # exits without draining its standard input leaves that `printf`
    # writing into a closed pipe -- which under `pipefail` makes SIGPIPE
    # the step's exit status. A red build, produced by the branch of this
    # script that had nothing to say, is the one outcome it must not have.
    listing = sys.stdin.read()

    if not behind(args.pin, args.latest):
        # Both tags rather than "which is the latest release": a pin
        # *ahead* of it is quiet here too, and that sentence would be
        # false in the log of the one repository trying an unreleased tag.
        print(f"pinned to {args.pin}; the latest release is {args.latest}")
        return 0

    proposed = BRANCH.format(tag=args.latest)
    if args.branches_unknown:
        # Nothing here can tell whether `proposed` is on the repository,
        # and the warning is only right when it is not. It repeats on
        # every pull request, so staying quiet costs one run of a message
        # that comes back; warning wrongly costs the reader's trust in it,
        # which does not.
        print(
            f"pinned to {args.pin}, and this repository's branches could"
            f" not be listed: not warning, since {proposed} may already"
            " be there"
        )
        return 0

    if proposed in branches(listing):
        print(
            f"pinned to {args.pin}, and {proposed} is already on this"
            " repository: the apply ran and its pull request is waiting"
        )
        return 0

    print(WARNING.format(pin=args.pin, latest=args.latest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
