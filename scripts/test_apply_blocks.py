#!/usr/bin/env python3
"""Tests for apply_blocks.py.

`render.py` and `pin.py` are covered on their own; the sequence that
composes them was not, and it is the one path here with effects on another
repository. Since `apply.yml` landed it also runs unattended, on a
schedule, in every consumer — so what gets tested is a throwaway consumer
built in a temporary directory, and what the script leaves on its disk.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

APPLY = Path(__file__).resolve().parent / "apply_blocks.py"

RELEASE = {
    "demo": """<!-- BEGIN shared:demo -->
## Demo

- current text
<!-- END shared:demo -->
""",
    "other": """<!-- BEGIN shared:other -->
## Other

- also current
<!-- END shared:other -->
""",
}

# What a repository onboarded before this release looks like: one block
# stale, one marker still carrying the `v<N>` that markers used to have,
# a block it no longer lists, and its own sections around them.
AGENTS = """# Instructions for AI coding agents

<!-- BEGIN shared:demo v2 -->
stale text
<!-- END shared:demo -->

<!-- BEGIN shared:other -->
## Other

- also stale
<!-- END shared:other -->

<!-- BEGIN shared:retired -->
## Retired

- a rule withdrawn upstream
<!-- END shared:retired -->

## CI requirements

- local content
"""

WORKFLOW = """name: CI

on: [pull_request]

jobs:
  instructions:
    uses: aicers/agent-instructions/.github/workflows/check-drift.yml@main
    with:
      blocks: "demo other retired"
      instructions-ref: 0.9.0
"""

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def blocks_dir(root: Path) -> Path:
    path = root / "blocks"
    path.mkdir(parents=True)
    for name, body in RELEASE.items():
        (path / f"{name}.md").write_text(body, encoding="utf-8")
    return path


def consumer(root: Path, agents: str = AGENTS, workflow: str | None = WORKFLOW) -> Path:
    root.mkdir(parents=True)
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    if workflow is not None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(workflow, encoding="utf-8")
    return root


def run(
    blocks: Path,
    root: Path,
    tag: str,
    *names: str,
    target: str = "AGENTS.md",
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(APPLY),
            "--target",
            target,
            str(blocks),
            str(root),
            tag,
            *names,
        ],
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        blocks = blocks_dir(tmp / "upstream")

        print("applying a release to a consumer")
        root = consumer(tmp / "consumer")
        result = run(blocks, root, "1.0.0", "demo", "other")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        check("- current text" in agents, "a listed block is rewritten")
        check("stale text" not in agents, "its old body is gone")
        check(
            "- also current" in agents and "- also stale" not in agents,
            "every listed block is rewritten, not just the first",
        )
        check(
            "<!-- BEGIN shared:demo -->" in agents and " v2 -->" not in agents,
            "a marker still carrying a version is replaced",
        )
        check("shared:retired" not in agents, "an unlisted block is removed")
        check(
            "a rule withdrawn upstream" not in agents,
            "its content goes with it",
        )
        check("\n\n\n" not in agents, "removing it leaves no blank-line scar")
        check("instructions-ref: 1.0.0" in workflow, "the pin moves")
        check(
            'blocks: "demo other"' in workflow,
            "the blocks input follows what was applied",
        )
        check(
            agents.startswith("# Instructions for AI coding agents\n")
            and agents.endswith("## CI requirements\n\n- local content\n"),
            "content outside the markers is untouched",
        )

        print("re-running against the result")
        before = (agents, workflow)
        result = run(blocks, root, "1.0.0", "demo", "other")
        check(result.returncode == 0, "exits 0")
        check(
            (
                (root / "AGENTS.md").read_text(encoding="utf-8"),
                (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
            )
            == before,
            "changes nothing",
        )

        print("a repository with no pin")
        unpinned = consumer(tmp / "unpinned", workflow="name: CI\non: [push]\n")
        result = run(blocks, unpinned, "1.0.0", "demo", "other")
        check(result.returncode != 0, "exits non-zero")
        check("add the drift-check job" in result.stderr, "says what to do")
        check(
            (unpinned / "AGENTS.md").read_text(encoding="utf-8") == AGENTS,
            "nothing is written",
        )

        # Upstream cannot edit the block list in a consumer's calling
        # workflow, so a retirement has to survive a caller that still names
        # the retired block. It is dropped from the target and from the pin,
        # which is what un-reds that repository's drift check.
        print("a block the caller lists that the release has retired")
        listed = consumer(tmp / "listed")
        result = run(blocks, listed, "1.0.0", "demo", "other", "retired")
        agents = (listed / "AGENTS.md").read_text(encoding="utf-8")
        workflow = (listed / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        check("shared:retired" not in agents, "its region is removed")
        check('blocks: "demo other"' in workflow, "the pin stops naming it")
        check("- current text" in agents, "the surviving blocks are applied")

        print("a blocks directory carrying none of them")
        empty = consumer(tmp / "empty")
        result = run(tmp / "nowhere", empty, "1.0.0", "demo", "other")
        check(result.returncode != 0, "exits non-zero")
        check(
            (empty / "AGENTS.md").read_text(encoding="utf-8") == AGENTS,
            "nothing is written",
        )

        # `blocks` is a required workflow_call input, but a required input
        # accepts an empty string, and `$BLOCKS` then expands to nothing.
        # Every region would be a block the caller no longer lists.
        print("a caller that names no blocks")
        nameless = consumer(tmp / "nameless")
        result = run(blocks, nameless, "1.0.0")
        check(result.returncode != 0, "exits non-zero")
        check(
            (nameless / "AGENTS.md").read_text(encoding="utf-8") == AGENTS,
            "nothing is written",
        )

        # Naming a block before inserting its marker pair is how a
        # repository takes on a new block, and getting the order wrong is
        # the one failure the scheduled job hits after onboarding. It has
        # to name the missing pair: the tree is left part-applied, and
        # neither driver commits it -- sync.sh throws the clone away and
        # apply.yml fails the job before its commit step -- so the message
        # is all anyone sees.
        print("a listed block the repository has no markers for")
        partial = consumer(
            tmp / "partial",
            agents="# Instructions\n\n"
            "<!-- BEGIN shared:demo -->\nstale text\n<!-- END shared:demo -->\n",
        )
        result = run(blocks, partial, "1.0.0", "demo", "other")
        check(result.returncode != 0, "exits non-zero")
        check(
            "no shared:other block" in result.stderr
            and "add the markers first" in result.stderr,
            "names the missing pair rather than the block that applied",
        )

        # `target` is a caller input in apply.yml and reaches the script
        # unexamined, so a mistyped one must fail on the step that read it
        # rather than rewrite a file outside the repository being applied
        # to. All three shapes are refused before the pin moves, so the
        # repository itself is left alone too.
        print("a target outside the repository")
        outside = tmp / "outside"
        outside.mkdir()
        bystander = outside / "AGENTS.md"
        bystander.write_text(AGENTS, encoding="utf-8")
        escape = consumer(tmp / "escape")
        link = escape / "LINKED.md"
        link.symlink_to(bystander)
        for description, value in (
            ("an absolute target", str(bystander)),
            ("a relative target that climbs out", "../outside/AGENTS.md"),
            ("a symlink pointing out of the tree", "LINKED.md"),
        ):
            result = run(blocks, escape, "1.0.0", "demo", "other", target=value)
            check(result.returncode != 0, f"{description} exits non-zero")
            check(
                "outside" in result.stderr,
                f"{description} says why",
            )
        check(
            bystander.read_text(encoding="utf-8") == AGENTS,
            "the file outside is untouched",
        )
        check(
            "instructions-ref: 0.9.0"
            in (escape / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
            "the repository's own pin never moved",
        )

        print("a repository with no target file")
        headless = tmp / "headless"
        (headless / ".github" / "workflows").mkdir(parents=True)
        (headless / ".github/workflows/ci.yml").write_text(WORKFLOW, encoding="utf-8")
        check(
            run(blocks, headless, "1.0.0", "demo").returncode != 0,
            "exits non-zero",
        )

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all apply_blocks.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
