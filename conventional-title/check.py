#!/usr/bin/env python3
"""Check one title against the organization's Conventional title rule.

Called by `conventional-title/action.yml`, which hands it everything
through the environment and nothing on the command line:

    CT_TITLE      the string to check
    CT_PR_SUFFIX  "true" when the string must end with ` (#<digits>)`,
                  which is removed before the rest is checked
    GH_TOKEN      the caller's token, for fetching the rule
    SCRIPTS       this repository's `scripts/`, for `pin_file.py`

The rule is `conventional-title/pattern.txt`, read from
aicers/agent-instructions at the `ref` the caller's
`.agent-instructions.toml` pins -- the mechanism is this file, from
`@main`; the rule is content, from the release. The expression is written
nowhere else, here included.

The title is untrusted. Under `pull_request_target` it is whatever the
author of a pull request typed, so it arrives as an environment variable
rather than as `${{ }}` pasted into a shell, and it is only ever printed
quoted and escaped: a line break in it would end the line this prints
and start one of the title's own, which the runner would read as a
workflow command. A title holding a carriage return or a line feed
therefore fails before it is matched at all -- `grep -E` matches line by
line, Python's `$` matches before a trailing newline, and `[^#]` matches
a line break under Python and JavaScript, so no reader of `pattern.txt`
can be trusted to give such a title the verdict the form intends.

`curl` fetches the rule rather than Python's `urllib`, because this runs
inside a consumer's job, which may be on a self-hosted macOS runner whose
Python has no certificate store of its own; curl uses the system's. The
token reaches it on standard input through `--config -`, never as an
argument another process on that machine could read.

Exit status 0 when the title matches, 1 when it does not or when the
check could not be run, with an `::error::` saying which.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

REPOSITORY = "aicers/agent-instructions"
RULE = "conventional-title/pattern.txt"

# The squash-merge suffix GitHub appends to a commit title on `main`. This
# is not the rule -- it is what a merge adds after the rule was applied to
# the pull request's title -- so it is spelled here, and only here.
SUFFIX = re.compile(r" \(#[0-9]+\)\Z")

EXPECTED = (
    "Expected <type>[(<scope>)][!]: <description>, where <type> is one of"
    " feat, fix, docs, style, refactor, perf, test, build, ci, chore or"
    " revert; <scope>, when present, is lowercase letters, digits, '.', '_'"
    " and '-', starting with a letter or digit; '!' marks a breaking change"
    " and sits right before the colon; the colon is followed by one space;"
    " and <description> starts with a lowercase letter, does not end with"
    " '.', a space or a tab, and holds no '#' followed by a digit."
)


class Refused(Exception):
    """The check could not be run, or the title failed it."""


def quoted(text: str) -> str:
    """`text` in double quotes, with every unprintable character escaped.

    Nothing taken from the title may reach the log unescaped: a line
    break, or any other character a log viewer might break a line on,
    comes out as a visible escape instead.
    """
    out = []
    for character in text:
        if character in '"\\':
            out.append("\\" + character)
        elif character == "\t":
            out.append("\\t")
        elif character.isprintable():
            out.append(character)
        elif ord(character) < 0x10000:
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(f"\\U{ord(character):08x}")
    return '"' + "".join(out) + '"'


def error(message: str) -> None:
    """Print one `::error::` line.

    `%` is the runner's escape character in a workflow command, and a
    title holding `%0A` would otherwise come out of the annotation as a
    line break. `quoted` has already removed every real one.
    """
    message = message.replace("%", "%25").replace("\r", "%0D")
    print(f"::error::{message.replace(chr(10), '%0A')}", flush=True)


def read_pin(root: Path, scripts: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(scripts / "pin_file.py"), "read", str(root), "ref"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "pin_file.py failed"
        raise Refused(
            "Could not read the pin in .agent-instructions.toml, which"
            " names the release of aicers/agent-instructions whose title"
            " rule this repository follows.\n" + detail
        )
    return result.stdout.strip()


def fetch_rule(ref: str) -> str:
    api = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
    url = f"{api}/repos/{REPOSITORY}/contents/{RULE}?ref={quote(ref, safe='')}"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    # A config file on standard input: double quotes, with backslash and
    # quote escaped, is how curl reads a value that has to survive intact.
    config = ""
    if token:
        value = f"Authorization: Bearer {token}"
        value = value.replace("\\", "\\\\").replace('"', '\\"')
        config = f'header = "{value}"\n'

    with tempfile.TemporaryDirectory() as scratch:
        body = Path(scratch) / "pattern.txt"
        try:
            result = subprocess.run(
                [
                    "curl", "-sS", "-L", "--retry", "3",
                    "--config", "-",
                    "-H", "Accept: application/vnd.github.raw+json",
                    "-H", "X-GitHub-Api-Version: 2022-11-28",
                    "-o", str(body),
                    "-w", "%{http_code}",
                    url,
                ],
                input=config,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise Refused("curl is not installed on this runner") from None
        status = result.stdout.strip()
        if result.returncode != 0:
            raise Refused(
                f"Could not fetch {RULE} from {REPOSITORY} at {ref}:"
                f" {result.stderr.strip() or f'curl exited {result.returncode}'}"
            )
        if status == "404":
            raise Refused(
                f"{REPOSITORY} at {ref}, the release .agent-instructions.toml"
                f" pins, has no {RULE}. That release is older than the"
                " conventional-title action; move the pin to a release that"
                " carries the rule."
            )
        if status != "200":
            raise Refused(
                f"Could not fetch {RULE} from {REPOSITORY} at {ref}:"
                f" HTTP {status}"
            )
        try:
            text = body.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            text = None

    # The format every reader relies on: one line, the expression, and one
    # newline. Anything else is not something to guess at.
    if (
        text is None
        or not text.endswith("\n")
        or "\n" in text[:-1]
        or "\r" in text
        or not text.startswith("^")
        or not text[:-1].endswith("$")
    ):
        raise Refused(
            f"{RULE} at {ref} is not one anchored expression on one line"
        )
    return text[:-1]


def check(title: str, pr_suffix: bool, pattern: str, ref: str) -> None:
    shown = quoted(title)
    if "\r" in title or "\n" in title:
        raise Refused(
            f"The title {shown} contains a line break. A title is one line;"
            " " + EXPECTED
        )

    subject = title
    if pr_suffix:
        match = SUFFIX.search(title)
        if not match:
            raise Refused(
                f"The commit title {shown} does not end with ' (#<number>)',"
                " the pull-request number a squash merge appends."
            )
        subject = title[: match.start()]

    try:
        rule = re.compile(pattern)
    except re.error as failure:
        raise Refused(f"{RULE} at {ref} does not compile: {failure}") from None
    if not rule.search(subject):
        what = "commit title" if pr_suffix else "title"
        raise Refused(
            f"The {what} {shown} is not a Conventional title. {EXPECTED}"
            f" (Rule: {RULE} at {ref}.)"
        )


def main() -> int:
    title = os.environ.get("CT_TITLE", "")
    flag = os.environ.get("CT_PR_SUFFIX", "false")
    root = Path(os.environ.get("GITHUB_WORKSPACE") or ".")
    scripts = Path(
        os.environ.get("SCRIPTS") or Path(__file__).resolve().parent.parent / "scripts"
    )

    try:
        if flag not in ("true", "false"):
            raise Refused(
                f"pr-suffix is {quoted(flag)}; it takes \"true\" or \"false\""
            )
        ref = read_pin(root, scripts)
        pattern = fetch_rule(ref)
        check(title, flag == "true", pattern, ref)
    except Refused as refusal:
        first, _, rest = str(refusal).partition("\n")
        error(first)
        if rest:
            print(rest)
        return 1

    print(f"Conventional title: {quoted(title)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
