#!/usr/bin/env python3
"""Run workflow shell steps against local trees and GitHub API fixtures.

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

The release and changelog gates run with a fake `gh` and real `jq`.
Run it directly with Python, Bash and jq.
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
RELEASE = CI.with_name("release-please.yml")
CHANGELOG = CI.with_name("changelog.yml")
REPOSITORY = "aicers/agent-instructions"

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


def github_step(
    tmp: Path, workflow: Path, name: str,
    responses: list[tuple[list[str], list | None]],
) -> tuple[subprocess.CompletedProcess, str]:
    output = tmp / "output"
    output.write_text("")
    result = execute(*step(workflow, name), tmp, {
        "PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_OUTPUT": str(output),
        "GH_RESPONSES": json.dumps(responses),
        "NUMBER": "1",
    })
    return result, output.read_text()


def changelog(tmp: Path) -> None:
    print("the changelog gate")
    endpoint = f"repos/{REPOSITORY}/pulls/1"
    files_args = ["api", "--paginate", f"{endpoint}/files?per_page=100", "--jq"]
    root_edit = {"filename": "CHANGELOG.md"}
    other_edit = {"filename": "docs/CHANGELOG.md"}
    rename = {"filename": "archive.md", "previous_filename": "CHANGELOG.md"}
    cases = (
        ("ordinary PR changes the changelog", "topic", "User", [[root_edit]], 1, 1),
        ("human opens a release-like PR", "release-please--main", "User", [[root_edit]], 1, 1),
        ("bot opens a release PR", "release-please--main", "Bot", [[root_edit]], 1, 0),
        ("only a nested changelog changes", "topic", "User", [[other_edit]], 1, 0),
        ("second page renames the root changelog", "topic", "User", [[other_edit], [rename]], 2, 1),
        ("the API returns too few files", "topic", "User", [[]], 1, 1),
        ("the files endpoint fails", "topic", "User", None, 1, 1),
    )
    for description, branch, user_type, pages, count, status in cases:
        pull = {
            "user": {"login": "github-actions[bot]" if user_type == "Bot" else "person",
                     "type": user_type},
            "head": {"repo": {"full_name": REPOSITORY}, "ref": branch},
            "base": {"repo": {"default_branch": "main"}, "ref": "main"},
            "changed_files": count,
        }
        result, _ = github_step(tmp, CHANGELOG, "Allow CHANGELOG.md only in the release PR", [
            (["api", endpoint], [pull]),
            (files_args, pages),
        ])
        check(result.returncode == status, description)


def release_gate(tmp: Path) -> None:
    print("the merged release CI gate")
    endpoint = f"repos/{REPOSITORY}"
    issues_args = ["api", "--paginate", "-X", "GET", f"{endpoint}/issues",
                   "-f", "state=closed", "-f", "labels=autorelease: pending",
                   "-f", "per_page=100", "--jq"]
    first, second = "1" * 40, "2" * 40
    merged = {"merged_at": "2026-11-21T00:00:00Z"}
    unmerged = {"number": 3, "pull_request": {"merged_at": None}}
    issues = [[unmerged, {"number": 1, "pull_request": merged}],
              [{"number": 2, "pull_request": merged}]]

    def ci_args(sha: str) -> list[str]:
        return ["api", "-X", "GET", f"{endpoint}/actions/workflows/ci.yml/runs",
                "-f", f"head_sha={sha}", "-f", "event=push", "-f", "branch=main",
                "-f", "status=success", "-f", "per_page=1", "--jq"]

    for description, pages, ci_runs, expected in (
        ("ignores closed unmerged PRs", [[unmerged]], [], "none"),
        ("waits for a pending merge on a later page", issues, [{"total_count": 0}], "waiting"),
        ("releases once all pending merges passed", issues, [{"total_count": 1}], "ready"),
        ("fails if GitHub cannot list the pending releases", None, [], None),
        ("fails if GitHub cannot list CI runs", issues, None, None),
        ("fails if GitHub omits the CI run count", issues, [{}], None),
    ):
        result, output = github_step(tmp, RELEASE, "Check the merge commits of pending release PRs", [
            (issues_args, pages),
            (["api", f"{endpoint}/pulls/1"], [{"base": {"ref": "main"}, "merge_commit_sha": first}]),
            (["api", f"{endpoint}/pulls/2"], [{"base": {"ref": "main"}, "merge_commit_sha": second}]),
            (ci_args(first), [{"total_count": 1}]),
            (ci_args(second), ci_runs),
        ])
        if expected is None:
            check(result.returncode == 1 and not output, description)
        else:
            check(result.returncode == 0 and output == f"release={expected}\n", description)


def release_steps(tmp: Path) -> None:
    tmp.mkdir()
    gh = tmp / "gh"
    gh.write_text('''#!/usr/bin/env python3
import json
import os
import subprocess
import sys

args = sys.argv[1:]
query = args.pop() if args[-2:-1] == ["--jq"] else None
for expected, pages in json.loads(os.environ["GH_RESPONSES"]):
    if args == expected:
        if pages is None:
            sys.exit("GitHub API request failed")
        for page in pages:
            if query is None:
                print(json.dumps(page))
            else:
                subprocess.run(["jq", "-r", query], input=json.dumps(page), text=True, check=True)
        break
else:
    print(f"Unexpected gh call: {args!r}", file=sys.stderr)
    sys.exit(47)
''')
    gh.chmod(0o755)
    changelog(tmp)
    release_gate(tmp)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        drift(Copy("check-drift/action.yml", ACTION), tmp / "action")
        drift(Copy(".github/workflows/check-drift.yml", WORKFLOW),
              tmp / "workflow")
        roster(tmp / "roster")
        release_steps(tmp / "release")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all workflow step tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
