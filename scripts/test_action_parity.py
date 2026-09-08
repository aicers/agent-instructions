#!/usr/bin/env python3
"""Hold `check-drift/action.yml` to what `check-drift.yml` already does.

The two are the same check reached two ways: the reusable workflow, which
runs it as a job of its own, and the composite action, which runs it as a
step inside a job the consumer already has. Thirteen repositories call
the first today and will move to the second one at a time, so for as long
as both exist a repository must not be able to tell which one it called
from what the check decides or what it says when it fails.

Nothing enforces that on its own. The two files are edited separately,
and the halves that would drift are the ones nobody reads twice: the
message a failing check prints, the default target, the scripts each one
drives, and the pin warning, which is the one piece the workflow still
keeps a copy of instead of sharing. Comparing the files wholesale would
only be noise -- the paths
differ, deliberately, and that difference is the entire point of the
action -- so what is compared here is what a consumer can observe.

Two things about the action itself are checked as well. A composite step
without `shell:` is a hard error, and one raised in a consumer's job
rather than here. And an `actions/checkout` in this file would put this
repository's Markdown inside the caller's workspace, which is what
`fetch_blocks.sh` exists to avoid.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / "check-drift" / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "check-drift.yml"
WARN = ROOT / "scripts" / "warn_behind.sh"

# What a consumer sees when the check fails. The one thing a repository
# would notice having moved, and the one thing neither file's author is
# looking at while editing the other.
MESSAGES = (
    (
        'echo "::error::$TARGET is out of date with aicers/agent-instructions."',
        'echo "Do not edit the marked blocks here. Change them upstream and"',
        "echo \"cut a release; this repository's scheduled apply.yml job then\"",
        'echo "opens the pull request that updates this copy."',
    ),
    (
        'echo "::error::$TARGET carries shared:$present, which this"\\',
        '"repository no longer lists. Remove the marker pair."',
    ),
)

# The same work, whatever the paths in front of them are.
COMMANDS = (
    "pin_file.py read .",
    "render.py check",
    "render.py names",
)

# The pin warning is the one part of the check the two do not share a
# file for: `warn_behind.sh` cannot be called from the workflow without
# turning a step that shows as failed-but-not-blocking into one that
# shows as green, which the script's own header explains, so the workflow
# keeps an inline copy. That leaves the same logic written twice, and the
# thing it decides -- whether a consumer is told its pin is behind -- is
# something a repository can see. So the parts that decide it are held
# together here: what each asks GitHub, how each tells an unreadable
# branch listing from an empty one, and what each says when the network
# does not answer.
#
# Including how each asks it. Neither reaches for `gh`: the action runs
# inside a consumer's job, and a self-hosted runner carries git, python3,
# curl and tar but not that -- where the pin warning would take its
# "could not resolve" branch on every pull request and stay green, which
# looks in a log almost exactly like the check working. The workflow runs
# on `ubuntu-latest` and could have kept `gh`, but then the two would ask
# GitHub two different ways, and the one nobody exercises is the one that
# rots.
WARNING = (
    "curl -fsSL --retry 3",
    "https://api.github.com/repos/",
    "/releases/latest",
    "Authorization: Bearer $token",
    'print(json.load(sys.stdin).get("tag_name") or "")',
    'python3 -c "$tag_name"',
    "git ls-remote --heads origin shared-instructions/*",
    "--branches-unknown",
    "check_drift.py",
    "could not resolve the latest release; nothing to compare",
    "could not list this repository's branches",
)

# The steps that do the checking, as opposed to the ones that put the
# files where each driver needs them.
STEPS = (
    "Read the pin",
    "Warn when the pin is behind the latest release",
    "Compare blocks",
    "Reject blocks this repository no longer lists",
)

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def lines(path: Path) -> list[str]:
    """The file with its YAML indentation taken off.

    The two nest the same steps at different depths, and nothing compared
    here is about the indentation.
    """
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]


def unquoted(path: Path) -> list[str]:
    """The same, with double quotes dropped.

    `python3 "$SCRIPTS/render.py" check` and
    `python3 .agent-instructions/scripts/render.py check` are the same
    call reaching the script by the two routes; the quoting is where the
    path went, not what was run.
    """
    return [line.replace('"', "") for line in lines(path)]


def normalize(text: str) -> str:
    """Text with the shell's spelling of it taken off.

    Line continuations are joined, quotes dropped and runs of spaces
    collapsed, so that a command reaching the two files at different
    widths -- one wrapped after `origin`, the other not -- reads the same
    here. Where a line breaks is not something a consumer can see.

    The fragments below are put through this too, rather than written
    pre-mangled: an apostrophe in a message is a quote to this and has to
    go from both sides, and a needle nobody can read is a needle nobody
    corrects when the message changes.
    """
    joined = re.sub(r"\\\n", " ", text).replace('"', "").replace("'", "")
    return re.sub(r"[ \t]+", " ", joined)


def flattened(path: Path) -> str:
    """The whole file as one normalized string."""
    return normalize(path.read_text(encoding="utf-8"))


def contains(haystack: list[str], needle: tuple[str, ...]) -> bool:
    for start in range(len(haystack) - len(needle) + 1):
        if tuple(haystack[start:start + len(needle)]) == needle:
            return True
    return False


def main() -> int:
    action, workflow = lines(ACTION), lines(WORKFLOW)

    print("the action is a composite action")
    check("using: composite" in action, "declares `using: composite`")
    check(
        not any(line.startswith("- uses: actions/checkout") for line in action),
        "checks nothing out into the caller's workspace",
    )

    print("every composite step names its shell")
    steps = [index for index, line in enumerate(action) if line.startswith("- name:")]
    for index in steps:
        end = next((s for s in steps if s > index), len(action))
        check(
            "shell: bash" in action[index:end],
            f"{action[index].removeprefix('- name: ')!r} sets `shell:`",
        )

    print("the two agree on the target input")
    for line in (
        "description: File in the caller repository holding the blocks",
        "required: false",
        "default: AGENTS.md",
    ):
        check(line in action and line in workflow, f"both say `{line}`")

    print("the two print the same thing when the check fails")
    for message in MESSAGES:
        check(contains(workflow, message), f"the workflow prints {message[0][:48]}...")
        check(contains(action, message), "the action prints the same")

    print("the two drive the same scripts")
    action_calls, workflow_calls = unquoted(ACTION), unquoted(WORKFLOW)
    for command in COMMANDS:
        check(
            any(command in line for line in workflow_calls),
            f"the workflow runs `{command}`",
        )
        check(
            any(command in line for line in action_calls),
            f"the action runs `{command}`",
        )

    print("the two name their steps alike")
    for step in STEPS:
        check(f"- name: {step}" in action, f"the action has {step!r}")
        check(f"- name: {step}" in workflow, f"the workflow has {step!r}")

    print("the warning cannot decide the job in either")
    check(
        contains(workflow, ("continue-on-error: true",)),
        "the workflow's warning step carries `continue-on-error`",
    )
    check(
        not any(line.startswith("continue-on-error") for line in action),
        "the action does not, since a composite step has no such key",
    )
    check(
        re.search(r"^exit 0$", WARN.read_text(encoding="utf-8"), re.M) is not None,
        "and `warn_behind.sh` ends by exiting 0 unconditionally instead",
    )
    check(
        any("warn_behind.sh" in line for line in action),
        "the action drives its warning through that script",
    )

    print("the two decide the warning the same way")
    warn_script, warn_inline = flattened(WARN), flattened(WORKFLOW)
    for fragment in WARNING:
        needle = normalize(fragment)
        check(needle in warn_inline, f"the workflow's copy has `{fragment}`")
        check(needle in warn_script, "`warn_behind.sh` has the same")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all check-drift parity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
