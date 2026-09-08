#!/usr/bin/env python3
"""Tests for warn_behind.sh.

One property matters more than what it prints: it exits 0. It is the step
that talks to the network, it runs on every pull request in every
consumer, and inside a composite action there is no `continue-on-error`
left to catch it. A `curl` that cannot reach GitHub, a `git` that cannot
list the branches, a `python3` that is not on the runner at all -- none of
those may turn somebody's pull request red over a release they were not
asking about.

So every command it calls is stubbed here, including `python3`, and every
one of them is made to fail in turn. Nothing reaches the network, which
is also what lets these run on a checkout with no `origin`.

`gh` is stubbed too, and never for the script to use: it announces itself
on standard error, which a command substitution does not capture, so a
run that reached for it says so here. The script must not, because the
action runs inside a consumer's job and a self-hosted runner has no `gh`
-- and a missing one would not fail anything, it would take the "could
not resolve" path on every pull request and leave the job green.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "warn_behind.sh"

# What a run that called `gh` leaves behind. On standard error, because
# the script reads a command's standard output into a variable and this
# has to show up whether or not that happened.
GH_WAS_CALLED = "gh: this script must not reach for gh"

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def stub(directory: Path, name: str, body: str) -> None:
    """Put a fake `name` first on PATH."""
    path = directory / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def run(
    *args: str,
    latest: str | None = "0.3.0",
    body: str | None = None,
    branches: str | None = "",
    python: bool = True,
) -> subprocess.CompletedProcess:
    """Run the script with `curl`, `gh`, `git` and `python3` replaced.

    `latest=None` is a `curl` that fails, which is a repository with no
    releases as much as it is a network that is not there -- the API
    answers 404 and `-f` makes that an exit status. `body` is a response
    that arrived and cannot be used. `branches=None` is a `git ls-remote`
    that fails, and `python=False` a `python3` that is not usable. None
    of them is anything being wrong with the pull request in front of it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        # Never usable, only detectable. Nothing here may call it.
        stub(bin_dir, "gh", f'echo {GH_WAS_CALLED!r} >&2; exit 1')
        if latest is None:
            stub(
                bin_dir,
                "curl",
                'echo "curl: (22) The requested URL returned error: 404" >&2;'
                " exit 22",
            )
        else:
            # The response the endpoint sends, through a file: the script
            # parses it as JSON, so it has to arrive as JSON rather than
            # as a tag somebody already picked out of one.
            payload = Path(tmp) / "release.json"
            payload.write_text(
                body
                if body is not None
                else json.dumps(
                    {
                        "tag_name": latest,
                        "name": latest,
                        "draft": False,
                        "prerelease": False,
                    }
                ),
                encoding="utf-8",
            )
            stub(bin_dir, "curl", f'cat {str(payload)!r}')
        if branches is None:
            stub(bin_dir, "git", 'echo "fatal: could not read" >&2; exit 128')
        else:
            # Through a file, so the tabs and newlines of a real
            # `git ls-remote --heads` listing reach the script as
            # themselves. A parser fed bare names passes whatever it does
            # to the real thing.
            listing = Path(tmp) / "listing"
            listing.write_text(branches, encoding="utf-8")
            stub(bin_dir, "git", f'cat {str(listing)!r}')
        if python:
            # The real interpreter, so the real check_drift.py decides
            # what is printed. Stubbing that too would leave this testing
            # a stub's opinion of the warning.
            stub(bin_dir, "python3", f'exec {sys.executable!r} "$@"')
        else:
            stub(bin_dir, "python3", 'echo "python3: not found" >&2; exit 127')

        environment = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=environment,
            cwd=tmp,
        )


BRANCH = (
    "1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c\t"
    "refs/heads/shared-instructions/0.3.0\n"
)


def main() -> int:
    print("a repository whose pin is behind")
    result = run("0.1.0")
    check(result.returncode == 0, "exits 0")
    check("::warning::" in result.stdout, "warns")
    check("0.1.0" in result.stdout and "0.3.0" in result.stdout, "names both")

    print("a repository on the latest release")
    result = run("0.3.0")
    check(result.returncode == 0, "exits 0")
    check("::warning::" not in result.stdout, "says nothing")

    print("a repository whose update branch is already pushed")
    result = run("0.1.0", branches=BRANCH)
    check(result.returncode == 0, "exits 0")
    check("::warning::" not in result.stdout, "says nothing")

    print("the release is resolved without `gh`")
    result = run("0.1.0")
    check(GH_WAS_CALLED not in result.stderr, "calls no `gh` on the way")
    result = run("0.1.0", latest=None)
    check(
        GH_WAS_CALLED not in result.stderr,
        "and does not fall back to one when the lookup fails",
    )

    print("the latest release cannot be resolved")
    # A repository with no releases at all reaches this the same way: the
    # endpoint answers 404, and `-f` turns that into an exit status like
    # any other. Nothing downstream can tell the two apart, and nothing
    # downstream should -- neither is a pin that is behind.
    result = run("0.1.0", latest=None)
    check(result.returncode == 0, "exits 0, so the job stays green")
    check(
        "could not resolve the latest release" in result.stdout,
        "says so in the log",
    )
    check("::warning::" not in result.stdout, "warns about nothing")

    print("the lookup answers with something that has no release in it")
    # A 200 with a body this cannot use is a lookup that did not happen,
    # not a repository that is up to date: the second would print nothing
    # at all and leave a stopped schedule unmentioned.
    for description, body in (
        ("an error document", '{"message": "Not Found"}'),
        ("something that is not JSON", "<html>502 Bad Gateway</html>"),
        ("a release with no tag on it", '{"tag_name": null}'),
    ):
        result = run("0.1.0", body=body)
        check(result.returncode == 0, f"{description}: exits 0")
        check(
            "could not resolve the latest release" in result.stdout,
            f"{description}: says the lookup failed",
        )
        check(
            "::warning::" not in result.stdout,
            f"{description}: warns about nothing",
        )

    print("the branch listing cannot be fetched")
    result = run("0.1.0", branches=None)
    check(result.returncode == 0, "exits 0, so the job stays green")
    check(
        "could not list this repository's branches" in result.stdout,
        "says so in the log",
    )
    check(
        "::warning::" not in result.stdout,
        "does not warn, since the branch may already be there",
    )

    print("python3 is not usable")
    result = run("0.1.0", python=False)
    check(result.returncode == 0, "exits 0, so the job stays green")

    print("everything the network is asked for fails at once")
    result = run("0.1.0", latest=None, branches=None, python=False)
    check(result.returncode == 0, "exits 0")

    print("no pin was passed")
    result = run()
    check(result.returncode == 0, "exits 0 rather than failing thirteen"
                                  " repositories over a bug in the caller")
    check("usage:" in result.stderr, "says what it wanted")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all warn_behind.sh tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
