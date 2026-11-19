#!/usr/bin/env python3
"""Tests for sync.sh.

What this driver has to get right, and cannot be checked by reading it,
is that the tree it applies and the tag it writes into every consumer's
pin file are the same release. The maintainer running it is standing on
`main`, which is ahead of the tag being synced by definition — every
release is cut in the past — so a driver that applied its own checkout
would open pull requests whose pin and blocks disagree, and the next
drift check would call that the consumer's divergence.

So the fixture below deliberately separates the two: a tagged release
carrying one text and a `main` carrying another, and a `repos.json` that
differs between them as well. Everything asserted here is asserted
against the branch the sync actually pushed.

`gh` and the network are replaced by a stub on `PATH` that clones from,
and reports on, local repositories. Nothing here talks to GitHub.

The title is asserted too, on the pull request and on the commit: a
repository whose default branch holds one of the marker files gets the
Conventional one, which `conventional-title/pattern.txt` has to accept,
and a repository holding none gets the title it always had.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PATTERN = SCRIPTS.parent / "conventional-title" / "pattern.txt"

# Each consumer, and the marker its default branch holds at the root.
MARKED = {
    "plz": "release-plz.toml",
    "please": "release-please-config.json",
    "manual": ".manual-release",
}

RELEASED = """<!-- BEGIN shared:demo -->
## Demo

- the rule as the release has it
<!-- END shared:demo -->
"""

# What the maintainer has checked out: the next release, not this one.
UNRELEASED = """<!-- BEGIN shared:demo -->
## Demo

- a rule not in any release yet
<!-- END shared:demo -->
"""

AGENTS = """# Instructions for AI coding agents

<!-- BEGIN shared:demo -->
- stale text
<!-- END shared:demo -->

## CI requirements

- local content
"""

PIN = """ref = "0.0.9"
blocks = ["demo"]
"""

# `gh api user`, `gh repo clone`, and `gh pr create` are all sync.sh uses.
# The clone comes from $FAKE_ORIGINS and the pull request is appended to
# $FAKE_PR_LOG instead of being opened.
GH_STUB = """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  api)  echo tester ;;
  repo) git clone --quiet "$FAKE_ORIGINS/${3#*/}.git" "$4" ;;
  pr)   printf '%s\\0' "$@" >> "$FAKE_PR_LOG"; printf '\\036' >> "$FAKE_PR_LOG" ;;
  *)    echo "fake gh: unexpected $*" >&2; exit 1 ;;
esac
"""

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def upstream(root: Path) -> Path:
    """A clone of this repository: released at 0.1.0, moved on since."""
    (root / "blocks").mkdir(parents=True)
    shutil.copytree(SCRIPTS, root / "scripts")
    git(root, "init", "-q", ".")

    def commit(blocks: str, repos: dict[str, list[str]], message: str) -> None:
        (root / "blocks" / "demo.md").write_text(blocks, encoding="utf-8")
        (root / "repos.json").write_text(
            json.dumps({"org": "aicers", "target": "AGENTS.md",
                        "repos": repos}),
            encoding="utf-8",
        )
        git(root, "add", "-A")
        git(root, "commit", "-qm", message)

    released = {"consumer": ["demo"], "nested": ["demo"], "directory": ["demo"]}
    released.update({name: ["demo"] for name in MARKED})
    commit(RELEASED, released, "the release")
    git(root, "tag", "0.1.0")
    # Since the tag: a reworded block and a repository added to the
    # registry. Neither is in 0.1.0, and syncing 0.1.0 must deliver
    # neither.
    commit(
        UNRELEASED,
        {**released, "newcomer": ["demo"]},
        "after the release",
    )
    # sync.sh resolves the tag against `origin`; here that is this
    # repository itself, which is the whole point — the tag is reachable
    # while the working tree has moved past it.
    git(root, "remote", "add", "origin", str(root))
    return root


def consumer(origins: Path, work: Path, marker: str | None = None) -> Path:
    """A bare repository standing in for a consumer on GitHub."""
    work.mkdir(parents=True)
    (work / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    (work / ".agent-instructions.toml").write_text(PIN, encoding="utf-8")
    if marker:
        (work / marker).parent.mkdir(parents=True, exist_ok=True)
        (work / marker).write_text("", encoding="utf-8")
    git(work, "init", "-q", ".")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "onboard")
    bare = origins / f"{work.name}.git"
    subprocess.run(
        ["git", "clone", "--quiet", "--bare", str(work), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare


def pull_requests(log: Path) -> list[list[str]]:
    """Each `gh pr` call the stub logged, as its argument list."""
    records = log.read_text(encoding="utf-8").split("\036")
    return [record.split("\0")[:-1] for record in records if record]


def argument(call: list[str], flag: str) -> str:
    return call[call.index(flag) + 1] if flag in call else ""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        origins = tmp / "origins"
        origins.mkdir()
        bare = consumer(origins, tmp / "consumer")
        bares = {
            name: consumer(origins, tmp / name, marker)
            for name, marker in MARKED.items()
        }
        # A marker below the root is not a converted repository, and nor
        # is a directory at the root that shares a marker's name.
        bares["nested"] = consumer(
            origins, tmp / "nested", "crates/x/release-plz.toml"
        )
        bares["directory"] = consumer(
            origins, tmp / "directory", ".manual-release/README.md"
        )
        root = upstream(tmp / "upstream")

        binary = tmp / "bin"
        binary.mkdir()
        (binary / "gh").write_text(GH_STUB, encoding="utf-8")
        (binary / "gh").chmod(0o755)
        log = tmp / "pr.log"

        environment = {
            **os.environ,
            "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
            "FAKE_ORIGINS": str(origins),
            "FAKE_PR_LOG": str(log),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }

        def sync(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["bash", str(root / "scripts" / "sync.sh"), *args],
                capture_output=True,
                text=True,
                env=environment,
            )

        print("syncing a tag the checkout has moved past")
        result = sync("0.1.0", "consumer")
        check(result.returncode == 0, "exits 0")
        check(
            "1 pull request(s) opened" in result.stdout,
            "opens one pull request",
        )
        branch = "tester/instructions-0.1.0"
        pushed = git(bare, "show", f"{branch}:AGENTS.md")
        pin = git(bare, "show", f"{branch}:.agent-instructions.toml")
        check(
            "- the rule as the release has it" in pushed,
            "the pushed blocks are the tag's",
        )
        check(
            "- a rule not in any release yet" not in pushed,
            "not the ones checked out where the sync was run",
        )
        check('ref = "0.1.0"' in pin, "the pin names the tag")
        check("- local content" in pushed, "content outside the markers stays")
        requests = pull_requests(log)
        check(len(requests) == 1 and requests[0][:2] == ["pr", "create"],
              "one pull request is opened, with the blocks in its body")
        check(bool(requests) and "demo" in argument(requests[0], "--body"),
              "which it names")
        traditional = "Update shared instruction blocks to 0.1.0"
        check(
            bool(requests) and argument(requests[0], "--title") == traditional,
            "a repository with no marker file keeps the title it had",
        )
        check(
            git(bare, "log", "-1", "--format=%s", branch).strip() == traditional,
            "and so does the commit",
        )

        rule = re.compile(PATTERN.read_text(encoding="utf-8")[:-1])
        conventional = "chore: update shared instruction blocks to 0.1.0"
        unconverted = {
            "nested": "a marker file below the root",
            "directory": "a directory named like a marker at the root",
        }
        for name in (*MARKED, *unconverted):
            want = traditional if name in unconverted else conventional
            where = unconverted.get(name) or MARKED[name]
            print(f"syncing a repository holding {where}")
            log.write_text("", encoding="utf-8")
            result = sync("0.1.0", name)
            check(result.returncode == 0, "exits 0")
            requests = pull_requests(log)
            check(
                len(requests) == 1 and argument(requests[0], "--title") == want,
                f"titles the pull request {want!r}",
            )
            subject = git(bares[name], "log", "-1", "--format=%s", branch).strip()
            check(subject == want, "and the commit subject the same")
            body = git(bares[name], "log", "-1", "--format=%b", branch)
            check(
                body.startswith("Synced from aicers/agent-instructions at 0.1.0"),
                "with the commit body unchanged",
            )
            if want == conventional:
                check(rule.search(want) is not None, "which pattern.txt accepts")

        print("a dry run")
        result = sync("--dry-run", "0.1.0", "plz")
        check(result.returncode == 0, "exits 0")
        check(f"title: {conventional}" in result.stdout,
              "says what the pull request would be titled")

        # The roster is the release's too. A repository added to
        # repos.json after the tag is not a consumer of that tag, and
        # apply_blocks.py -- which reads the same copy -- would refuse it
        # partway through a fan-out that had already opened pull requests.
        print("a repository repos.json gained after the tag")
        result = sync("0.1.0", "newcomer")
        check(result.returncode == 0, "exits 0 rather than aborting")
        check(
            "not in repos.json, skipping" in result.stderr,
            "skips it where a mistyped name is skipped",
        )
        check(
            "0 pull request(s) opened" in result.stdout,
            "and opens nothing for it",
        )

        print("a tag that is not on origin")
        result = sync("9.9.9", "consumer")
        check(result.returncode == 2, "exits 2")
        check(
            "no tag '9.9.9' on origin" in result.stderr,
            "says to tag the release first",
        )

        print("no tag given")
        check(sync().returncode == 2, "exits 2")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all sync.sh tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
