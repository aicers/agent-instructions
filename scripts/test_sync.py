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
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

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
  pr)   printf '%s\\n' "$*" >> "$FAKE_PR_LOG" ;;
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

    commit(RELEASED, {"consumer": ["demo"]}, "the release")
    git(root, "tag", "0.1.0")
    # Since the tag: a reworded block and a repository added to the
    # registry. Neither is in 0.1.0, and syncing 0.1.0 must deliver
    # neither.
    commit(
        UNRELEASED,
        {"consumer": ["demo"], "newcomer": ["demo"]},
        "after the release",
    )
    # sync.sh resolves the tag against `origin`; here that is this
    # repository itself, which is the whole point — the tag is reachable
    # while the working tree has moved past it.
    git(root, "remote", "add", "origin", str(root))
    return root


def consumer(origins: Path, work: Path) -> Path:
    """A bare repository standing in for a consumer on GitHub."""
    work.mkdir(parents=True)
    (work / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    # Deliberately the superseded path. A consumer arrives on the current
    # through an ordinary apply, so the fan-out has to carry both halves of
    # that move -- the new file added and the old one deleted -- in the
    # commit it was already making.
    (work / ".agents").mkdir()
    (work / ".agents" / "instructions.toml").write_text(PIN, encoding="utf-8")
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


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        origins = tmp / "origins"
        origins.mkdir()
        bare = consumer(origins, tmp / "consumer")
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
        tree = git(bare, "ls-tree", "-r", "--name-only", branch)
        check(
            ".agents/instructions.toml" not in tree,
            "the superseded pin is deleted on the branch, not left beside it",
        )
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
        check(log.read_text(encoding="utf-8").count("pr create") == 1,
              "one pull request is opened, with the blocks in its body")
        check("demo" in log.read_text(encoding="utf-8"), "which it names")

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
