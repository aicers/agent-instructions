#!/usr/bin/env python3
"""Tests for check_drift.py.

Three outcomes decide whether the warning is worth having: a repository
that is behind sees it, a repository that is current sees nothing, and a
repository whose update branch is already pushed sees nothing either.
The third is the one that gets got wrong, and getting it wrong is not a
crash — it is a warning on every pull request in a repository where the
schedule is working, which is how a warning stops being read.

So the branch cases are exercised with real `git ls-remote --heads`
output, tabs and `refs/heads/` and all, rather than with the bare names
that would make a broken parser pass.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

CHECK = Path(__file__).resolve().parent / "check_drift.py"

# What `git ls-remote --heads origin 'shared-instructions/*'` prints in a
# repository whose last apply pushed 0.2.0 and nothing since.
STALE = (
    "9f1c2a4b6d8e0f2a4c6e8a0b2d4f6a8c0e2f4a6b\t"
    "refs/heads/shared-instructions/0.2.0\n"
)
CURRENT = STALE + (
    "1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c\t"
    "refs/heads/shared-instructions/0.3.0\n"
)

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def run(*args: str, branches: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        input=branches,
        capture_output=True,
        text=True,
    )


def main() -> int:
    print("a repository whose pin is behind")
    result = run("0.1.0", "0.3.0")
    check(result.returncode == 0, "exits 0, so the check still passes")
    check(result.stdout.startswith("::warning::"), "warns")
    check("0.1.0" in result.stdout, "names the pin")
    check("0.3.0" in result.stdout, "names the latest release")
    check(
        "Update shared instructions" in result.stdout,
        "names the workflow to dispatch",
    )
    # An annotation is one line. A second one would be rendered as the
    # whole of the message by GitHub and dropped from the pull request.
    check(
        len(result.stdout.strip().splitlines()) == 1,
        "says it in one line",
    )

    print("a repository on the latest release")
    result = run("0.3.0", "0.3.0")
    check(result.returncode == 0, "exits 0")
    check("::warning::" not in result.stdout, "says nothing")

    print("a repository whose update branch is already pushed")
    result = run("0.2.0", "0.3.0", branches=CURRENT)
    check(result.returncode == 0, "exits 0")
    check(
        "::warning::" not in result.stdout,
        "says nothing: the schedule ran, and an unmerged pull request is"
        " a different problem",
    )
    check(
        "shared-instructions/0.3.0" in result.stdout,
        "says in the log why it is quiet",
    )

    # The branch for some earlier release proves only that the schedule
    # ran at some point, which is exactly what a stopped one also looks
    # like. Reading any branch under the prefix as "the apply ran" would
    # silence the warning in the repository that needs it most: one whose
    # apply last succeeded before it stopped.
    print("a repository holding only an older update branch")
    result = run("0.1.0", "0.3.0", branches=STALE)
    check(result.stdout.startswith("::warning::"), "warns anyway")

    # `git ls-remote --heads origin 'shared-instructions/*'` matches the
    # pattern against the tail of a ref at slash boundaries, so somebody's
    # `feature/shared-instructions/0.3.0` comes back in the listing too.
    # It is not a branch the apply pushed, and reading it as one would go
    # quiet in a repository whose schedule has stopped -- silenced by a
    # branch a person made while reading about this very warning.
    print("a repository holding a branch ending in the apply's branch name")
    result = run(
        "0.1.0",
        "0.3.0",
        branches=(
            "5c7e9b1d3f5a7c9e1b3d5f7a9c1e3b5d7f9a1c3e\t"
            "refs/heads/feature/shared-instructions/0.3.0\n"
        ),
    )
    check(result.stdout.startswith("::warning::"), "warns anyway")

    print("a repository pinned to a tag from before the version scheme")
    result = run("v1", "0.3.0")
    check(result.stdout.startswith("::warning::"), "warns")

    # Somebody pinned a tag by hand to try it before it was released.
    # Dispatching the apply would move them backwards, so there is
    # nothing to tell them.
    print("a repository pinned ahead of the latest release")
    result = run("0.4.0", "0.3.0")
    check("::warning::" not in result.stdout, "says nothing")
    check(
        "0.3.0" in result.stdout,
        "says which release is the latest, rather than calling the pin it",
    )

    print("releases of differing depth")
    check(
        "::warning::" not in run("1.2", "1.2.0").stdout,
        "reads 1.2 and 1.2.0 as the same release",
    )
    check(
        run("1.2", "1.2.1").stdout.startswith("::warning::"),
        "reads 1.2 as behind 1.2.1",
    )
    # Ordered as numbers, not as text, where "10" sorts below "9".
    check(
        run("0.9.0", "0.10.0").stdout.startswith("::warning::"),
        "reads 0.9.0 as behind 0.10.0",
    )

    print("a repository with no update branches at all")
    result = run("0.1.0", "0.3.0", branches="\n")
    check(result.stdout.startswith("::warning::"), "warns")

    # Driven the way check-drift.yml drives it: a shell pipeline under
    # `pipefail`. Every outcome has to drain the listing, because exiting
    # with the pipe still full leaves the writer on the other end filling
    # a closed one, and `pipefail` makes that SIGPIPE the step's exit
    # status -- a red build produced by the branch of the script with
    # nothing to say. It only shows up past a pipe buffer's worth, which
    # is where the writer blocks instead of racing ahead and finishing.
    print("piped a listing larger than a pipe buffer, as the workflow pipes it")
    flood = "".join(
        f"{index:040x}\trefs/heads/shared-instructions/9.9.{index}\n"
        for index in range(4096)
    )
    for pin, description in (
        ("0.3.0", "current"),
        ("0.1.0", "behind"),
        ("0.2.0", "behind with its branch already pushed"),
    ):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as listing:
            listing.write(flood + CURRENT)
            listing.flush()
            piped = subprocess.run(
                [
                    "bash",
                    "-c",
                    'set -uo pipefail; cat "$1" | "$2" "$3" "$4" "$5"',
                    "check_drift",
                    listing.name,
                    sys.executable,
                    str(CHECK),
                    pin,
                    "0.3.0",
                ],
                capture_output=True,
                text=True,
            )
        check(piped.returncode == 0, f"leaves the pipeline at 0 when {description}")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all check_drift.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
