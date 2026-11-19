#!/usr/bin/env python3
"""Run the shell that lives inside workflow YAML, against local trees.

Some of what a consumer depends on is not a script here but a `run:`
block: the drift check's "Compare blocks" and "Reject blocks this
repository no longer lists" steps, written twice -- once in
`check-drift/action.yml`, once in `.github/workflows/check-drift.yml` --
and the roster check in `ci.yml`. Each turns a listed block name into a
file and a region, and a name may carry a variant. `test_action_parity.py`
holds the two drift-check copies to the same lines; this runs them.

They cannot be run the way the `action` job in `ci.yml` runs the action,
through `consumer_fixture.sh`: that builds a consumer from a real
release, and no release carries a variant yet. CI never runs the reusable
workflow at all. So each step's script is read out of its YAML file and
run with the environment the step declares, in a consumer built here,
against a blocks tree built here, under the shell GitHub would use: `bash
--noprofile --norc -eo pipefail` for a step that says `shell: bash`, and
`bash -e` for one that names none.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / "check-drift" / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "check-drift.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"

COMPARE = "Compare blocks"
REJECT = "Reject blocks this repository no longer lists"
ROSTER = "Verify repos.json references existing blocks"

DEFAULT = """<!-- BEGIN shared:demo -->
## Demo

- the default text
<!-- END shared:demo -->
"""

VARIANT = """<!-- BEGIN shared:demo -->
## Demo

- the variant text
<!-- END shared:demo -->
"""

OTHER = """<!-- BEGIN shared:other -->
## Other

- other text
<!-- END shared:other -->
"""

STRAY = """<!-- BEGIN shared:stray -->
- a block nobody lists
<!-- END shared:stray -->
"""

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def step(path: Path, name: str) -> tuple[str, str | None]:
    """The `run: |` script of the step called `name`, and its `shell:`.

    Not a YAML parser: these files are hand-written in one shape, and
    reading that shape is all this needs. A step it cannot find fails the
    test rather than being skipped.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines)
              if line.strip() == f"- name: {name}"]
    if len(starts) != 1:
        raise SystemExit(f"{path}: {len(starts)} steps named {name!r}")
    start = starts[0]
    depth = indent(lines[start])
    end = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].strip() and indent(lines[i]) <= depth),
        len(lines),
    )
    body = lines[start:end]
    shell = next(
        (line.split(":", 1)[1].strip() for line in body
         if line.strip().startswith("shell:")),
        None,
    )
    runs = [i for i, line in enumerate(body) if line.strip() == "run: |"]
    if len(runs) != 1:
        raise SystemExit(f"{path}: step {name!r} has no `run: |` block")
    key = indent(body[runs[0]])
    script: list[str] = []
    for line in body[runs[0] + 1:]:
        if line.strip() and indent(line) <= key:
            break
        script.append(line)
    margin = min(indent(line) for line in script if line.strip())
    return "\n".join(line[margin:] for line in script) + "\n", shell


def execute(
    script: str, shell: str | None, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    if "${{" in script:
        raise SystemExit("a step script still holds a `${{ }}` expression")
    if shell == "bash":
        command = ["bash", "--noprofile", "--norc", "-eo", "pipefail"]
    elif shell is None:
        command = ["bash", "-e"]
    else:
        raise SystemExit(f"no way to run a step with shell {shell!r}")
    path = cwd.parent / f"step-{os.getpid()}.sh"
    path.write_text(script, encoding="utf-8")
    try:
        return subprocess.run(
            [*command, str(path)],
            cwd=cwd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
        )
    finally:
        path.unlink()


def blocks_tree(root: Path) -> Path:
    """A release's tree: `blocks/` with a block, a variant of it, another."""
    (root / "blocks").mkdir(parents=True)
    (root / "blocks" / "demo.md").write_text(DEFAULT, encoding="utf-8")
    (root / "blocks" / "demo.alt.md").write_text(VARIANT, encoding="utf-8")
    (root / "blocks" / "other.md").write_text(OTHER, encoding="utf-8")
    return root


class Copy:
    """One of the two drift-check copies, and how it reaches its files."""

    def __init__(self, label: str, path: Path) -> None:
        self.label = label
        self.path = path
        self.compare = step(path, COMPARE)
        self.reject = step(path, REJECT)

    def consumer(self, root: Path, agents: str, tree: Path) -> Path:
        root.mkdir(parents=True)
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
        if self.path == WORKFLOW:
            # The workflow checks this repository out at
            # `.agent-instructions` and the pinned release at
            # `.agent-instructions-blocks`, both inside the workspace.
            (root / ".agent-instructions").symlink_to(ROOT)
            (root / ".agent-instructions-blocks").symlink_to(tree)
        return root

    def env(self, blocks: str, tree: Path) -> dict[str, str]:
        env = {"BLOCKS": blocks, "TARGET": "AGENTS.md"}
        if self.path == ACTION:
            # `${{ github.action_path }}/../scripts`, and the directory
            # `fetch_blocks.sh` unpacked the release into.
            env["SCRIPTS"] = str(ROOT / "scripts")
            env["BLOCKS_DIR"] = str(tree)
        return env

    def run(self, which: tuple[str, str | None], consumer: Path,
            blocks: str, tree: Path) -> subprocess.CompletedProcess:
        script, shell = which
        return execute(script, shell, consumer, self.env(blocks, tree))


def drift(copy: Copy, tmp: Path) -> None:
    print(f"{copy.label}")
    tree = blocks_tree(tmp / "release")

    def consumer(slug: str, agents: str) -> Path:
        return copy.consumer(tmp / slug, agents, tree)

    matching = consumer("matching", f"# Title\n\n{VARIANT}\n{OTHER}")
    result = copy.run(copy.compare, matching, "demo:alt other", tree)
    check(result.returncode == 0,
          "compare passes a region matching the variant it lists")
    result = copy.run(copy.reject, matching, "demo:alt other", tree)
    check(result.returncode == 0,
          "reject does not flag a region listed with a variant")

    result = copy.run(copy.compare, matching, "demo other", tree)
    check(result.returncode == 1,
          "compare fails the variant's text where the default is listed")

    default = consumer("default", f"# Title\n\n{DEFAULT}\n{OTHER}")
    result = copy.run(copy.compare, default, "demo:alt other", tree)
    check(result.returncode == 1,
          "compare fails a region holding the default instead of the variant")
    check(
        "out of date with aicers/agent-instructions" in result.stdout
        and "- the variant text" in result.stdout,
        "and says so, with the diff against the variant",
    )
    # What every pin up to now lists: names with no variant, each its own
    # file, exactly as before variants existed.
    result = copy.run(copy.compare, default, "demo other", tree)
    check(result.returncode == 0, "compare passes names with no variant")
    result = copy.run(copy.reject, default, "demo other", tree)
    check(result.returncode == 0, "and reject passes them too")

    stray = consumer("stray", f"# Title\n\n{VARIANT}\n{OTHER}\n{STRAY}")
    result = copy.run(copy.reject, stray, "demo:alt other", tree)
    check(result.returncode == 1, "reject fails a region nobody lists")
    check(
        "carries shared:stray" in result.stdout
        and "shared:demo" not in result.stdout,
        "and names that region alone",
    )

    missing = consumer("missing", f"# Title\n\n{VARIANT}\n{OTHER}")
    result = copy.run(copy.compare, missing, "demo:nope other", tree)
    check(result.returncode != 0,
          "compare fails a variant the release does not carry")


def roster(tmp: Path) -> None:
    print("the roster step in ci.yml")
    script, shell = step(CI, ROSTER)

    def run(slug: str, repos: dict[str, list[str]]) -> subprocess.CompletedProcess:
        root = blocks_tree(tmp / slug)
        (root / "blocks" / "commit-messages.md").write_text(
            "x\n", encoding="utf-8")
        (root / "blocks" / "commit-messages.conventional.md").write_text(
            "x\n", encoding="utf-8")
        (root / "blocks" / "changelog.md").write_text("x\n", encoding="utf-8")
        (root / "blocks" / "changelog.generated.md").write_text(
            "x\n", encoding="utf-8")
        (root / "repos.json").write_text(
            json.dumps({"org": "aicers", "target": "AGENTS.md",
                        "repos": repos}),
            encoding="utf-8",
        )
        # At the root of the tree, where the step runs in this repository.
        return execute(script, shell, root, {})

    result = run("roster-variants", {
        "one": ["commit-messages:conventional", "changelog:generated",
                "demo:alt", "other"],
        "two": ["commit-messages", "changelog"],
    })
    check(result.returncode == 0, "passes a roster listing variants")
    check("not consumed" not in result.stdout,
          "and counts a variant file as its block, not an unused one")

    result = run("roster-defaults", {
        "one": ["commit-messages", "changelog", "demo", "other"],
    })
    check(result.returncode == 0, "passes a roster that lists no variant")
    check(
        "not consumed" not in result.stdout
        and "commit-messages.conventional" in result.stdout,
        "notes the variants nobody takes, not as unused blocks",
    )

    result = run("roster-unused", {"one": ["demo", "other"]})
    check(
        result.returncode == 0
        and "not consumed by any repository: ['changelog', 'commit-messages']"
        in result.stdout,
        "still notes a block nobody consumes",
    )

    result = run("roster-unknown", {"one": ["changelog:nope", "demo"]})
    check(result.returncode != 0, "fails a variant whose file does not exist")
    check("changelog:nope" in result.stderr, "and names it")

    for bad in ("changelog.generated", ":x", "x:", "x:y:z"):
        result = run(f"roster-bad-{bad.replace(':', '_')}", {"one": [bad]})
        check(result.returncode != 0, f"fails the malformed name {bad!r}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        drift(Copy("check-drift/action.yml", ACTION), tmp / "action")
        drift(Copy(".github/workflows/check-drift.yml", WORKFLOW),
              tmp / "workflow")
        roster(tmp / "roster")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all workflow step tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
