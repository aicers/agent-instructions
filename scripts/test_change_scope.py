#!/usr/bin/env python3
"""Tests for change-scope/scope.sh, and for how action.yml calls it.

Each case builds a throwaway "origin" repository, clones it the way
`actions/checkout` with `fetch-depth: 0` leaves a workspace -- every
branch as `refs/remotes/origin/*`, full history -- and runs scope.sh in
the clone with the `CS_*` variables `change-scope/action.yml` passes.

The property that matters most is the asymmetry: a wrong "docs-only"
skips the tests on a code change, a wrong "run everything" only costs
runner time. So besides the cases that should come out docs-only, every
way of not knowing has to come out docs-only=false and docs-touched=true
with exit status 0 -- and each of those cases names the reason it expects
to see, so that a case cannot pass on some other fallback than the one it
is about.

The script runs under `/bin/bash` (override with SCOPE_BASH), which on
macOS is bash 3.2 with BSD tools: CI runs this file on ubuntu-latest and
macos-latest.

Run it directly; it needs git and the standard library.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "change-scope" / "scope.sh"
ACTION = ROOT / "change-scope" / "action.yml"
BASH = os.environ.get("SCOPE_BASH", "/bin/bash")
ZERO = "0" * 40
FULL = "::warning::Change scope: running everything ("

# HOME is pointed at the test directory on every call, so no user git
# configuration leaks into a run.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}

# What action.yml must hand scope.sh: RFC 0001 §4.1.
ACTION_ENV = {
    "CS_EVENT": "${{ github.event_name }}",
    "CS_REF_TYPE": "${{ github.ref_type }}",
    "CS_REF_NAME": "${{ github.ref_name }}",
    "CS_DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
    "CS_BASE_REF": "${{ github.base_ref }}",
    "CS_PR_HEAD": "${{ github.event.pull_request.head.sha }}",
    "CS_BEFORE": "${{ github.event.before }}",
    "CS_SHA": "${{ github.sha }}",
    "CS_DOCS_PATHS": "${{ inputs.docs-paths }}",
    "CS_NOT_DOCS_PATHS": "${{ inputs.not-docs-paths }}",
    "CS_DISPATCH_FULL": "${{ inputs.dispatch-full }}",
}

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


class Repo:
    """An origin repository with a `main` branch, and helpers to grow it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.work = root / "author"
        self.origin = root / "origin.git"
        self.env = {**os.environ, **GIT_ENV, "HOME": str(root)}
        self.git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=root)
        self.git("init", "-q", "-b", "main", str(self.work), cwd=root)
        self.git("remote", "add", "origin", str(self.origin))
        self.commit("start", {"src/main.rs": "fn main() {}\n", "README.md": "# x\n"})
        self.git("push", "-q", "origin", "main")

    def git(self, *args: str, cwd: Path | None = None, data: bytes | None = None):
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.work,
            env=self.env,
            check=True,
            capture_output=True,
            input=data,
        )
        return result.stdout.decode("utf-8", "surrogateescape").strip()

    def commit(self, message: str, files: dict[str, str]) -> str:
        for name, content in files.items():
            path = self.work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self.git("add", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, start: str = "main") -> None:
        self.git("checkout", "-q", "-B", name, start)

    def push(self, *refs: str) -> None:
        self.git("push", "-q", "-f", "origin", *refs)

    def feature(self, name: str, files: dict[str, str], start: str = "main") -> str:
        self.branch(name, start)
        sha = self.commit(name, files)
        self.push(name)
        self.git("checkout", "-q", "main")
        return sha

    def clone(self, name: str = "checkout", depth: int | None = None) -> Path:
        target = self.root / name
        if target.exists():
            shutil.rmtree(target)
        args = ["clone", "-q"]
        if depth:
            args += ["--depth", str(depth)]
        self.git(*args, f"file://{self.origin}", str(target), cwd=self.root)
        return target


def scope(checkout: Path, path_prefix: str = "", locale: str = "", **cs: str):
    """Run scope.sh in `checkout`; return status, outputs, and the log."""
    output = checkout.parent / "github-output"
    output.write_text("", encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CS_", "LC_")) and k != "GITHUB_OUTPUT"
    }
    env.update(GIT_ENV)
    env.update(HOME=str(checkout.parent), GITHUB_OUTPUT=str(output))
    if path_prefix:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    if locale:
        env["LC_ALL"] = locale
    env.update({"CS_DEFAULT_BRANCH": "main", "CS_REF_TYPE": "branch", **cs})
    result = subprocess.run(
        [BASH, str(SCRIPT)], cwd=checkout, env=env, capture_output=True
    )
    values = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        values[key] = value
    log = (result.stdout + result.stderr).decode("utf-8", "surrogateescape")
    return result.returncode, values, log


def expect(name, result, docs_only, docs_touched=None, reason=None) -> None:
    """Check a verdict. `reason` is required for a run-everything verdict."""
    status, values, log = result
    before = len(failures)
    print(name)
    check(status == 0, f"exits 0 (got {status})")
    got_only, got_touched = values.get("docs-only"), values.get("docs-touched")
    check(got_only == docs_only, f"docs-only={docs_only} (got {got_only})")
    if docs_touched is not None:
        check(
            got_touched == docs_touched,
            f"docs-touched={docs_touched} (got {got_touched})",
        )
    check(
        len(values) == 2,
        f"both outputs written exactly once (got {sorted(values)})",
    )
    if reason is None:
        check(FULL not in log, "judged, not a run-everything fallback")
    else:
        check(FULL + reason in log, f"falls back for: {reason}")
        check(got_touched == "true", "a fallback reports docs-touched=true")
    if len(failures) > before:
        print("    log:\n      " + log.replace("\n", "\n      "))


def pr(repo: Repo, checkout: Path, head_branch: str, base: str = "main", **extra):
    head = repo.git("rev-parse", head_branch)
    return scope(
        checkout,
        CS_EVENT="pull_request",
        CS_BASE_REF=base,
        CS_PR_HEAD=head,
        CS_REF_NAME="1/merge",
        CS_SHA=head,
        **extra,
    )


def test_action_wiring() -> None:
    """action.yml passes exactly the §4.1 variables and pastes nothing."""
    print("action.yml hands scope.sh the §4.1 environment")
    text = ACTION.read_text(encoding="utf-8")
    for key, value in ACTION_ENV.items():
        check(f"{key}: {value}" in text, f"{key} is {value}")
    run_lines = [line for line in text.splitlines() if line.strip().startswith("run:")]
    check(len(run_lines) == 1, "one run: line")
    check(all("${{" not in line for line in run_lines), "no ${{ }} inside run:")


def main() -> int:
    test_action_wiring()
    version = subprocess.run(
        [BASH, "-c", 'echo "$BASH_VERSION"'], capture_output=True, text=True
    ).stdout.strip()
    print(f"scope.sh under {BASH} {version}")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(Path(tmp))
        docs = repo.feature("docs", {"README.md": "# y\n", "docs/a.md": "a\n"})
        repo.feature("readme", {"README.md": "# z\n"})
        repo.feature("mixed", {"docs/a.md": "a\n", "src/lib.rs": "\n"})
        repo.feature("nested-md", {"src/notes.md": "n\n"})
        repo.feature("src-md", {"src/x.md": "x\n"})
        repo.feature("code", {"src/main.rs": "fn main() { }\n"})
        repo.feature("both-lists", {"docs/reference/api.md": "r\n"})

        repo.commit("lib", {"src/lib.rs": "pub fn f() {}\n"})
        repo.push("main")
        repo.branch("rename")
        (repo.work / "docs").mkdir(exist_ok=True)
        repo.git("mv", "src/lib.rs", "docs/lib.md")
        repo.git("commit", "-q", "-m", "rename")
        repo.push("rename")
        repo.git("checkout", "-q", "main")

        repo.feature("stack-base", {"src/main.rs": "fn main() { 1; }\n"})
        repo.feature("stacked", {"docs/b.md": "b\n"}, start="stack-base")
        repo.feature("korean", {"docs/한글.md": "가\n"})
        # A ref name cannot hold a space, so `${IFS}` stands in for it: run
        # by a shell, this name still creates a file called `pwned`.
        injection = "x$(touch${IFS}pwned)`id`"
        repo.feature(injection, {"docs/c.md": "c\n"})
        repo.branch("same")
        repo.push("same")
        repo.git("checkout", "-q", "main")

        # A path that is not valid UTF-8, built through plumbing because
        # some file systems refuse to create one.
        blob = repo.git("hash-object", "-w", "--stdin", data=b"x\n")
        tree = subprocess.run(
            ["git", "ls-tree", "-z", "main"],
            cwd=repo.work,
            env=repo.env,
            check=True,
            capture_output=True,
        ).stdout
        tree += b"100644 blob " + blob.encode() + b"\t\xff.rs\0"
        new_tree = repo.git("mktree", "-z", data=tree)
        bad = repo.git("commit-tree", new_tree, "-p", "main", "-m", "bad path")
        repo.git("update-ref", "refs/heads/bad-utf8", bad)
        repo.push("bad-utf8")

        repo.git("checkout", "-q", "--orphan", "orphan")
        repo.git("rm", "-q", "-rf", ".")
        repo.commit("orphan", {"docs/o.md": "o\n"})
        repo.push("orphan")
        repo.git("checkout", "-q", "-f", "main")

        # A pull request opened before `main` moved on with a code commit.
        repo.feature("early-docs", {"docs/early.md": "e\n"})
        repo.commit("main moves on", {"src/main.rs": "fn main() { 2; }\n"})
        repo.push("main")
        repo.git("tag", "v1")
        repo.push("v1")

        checkout = repo.clone()
        dp = "docs/**\n"

        expect("PR, root README.md and docs/a.md",
               pr(repo, checkout, "docs", CS_DOCS_PATHS=dp), "true")
        expect("PR, root README.md only, no inputs (built-in list)",
               pr(repo, checkout, "readme"), "true", "true")
        expect("PR, documentation and src/lib.rs",
               pr(repo, checkout, "mixed", CS_DOCS_PATHS=dp), "false", "true")
        expect("PR, src/notes.md only, no inputs (*.md is root only)",
               pr(repo, checkout, "nested-md"), "false", "false")
        expect("PR, src/x.md with **/*.md listed and src/** held back",
               pr(repo, checkout, "src-md",
                  CS_DOCS_PATHS="**/*.md", CS_NOT_DOCS_PATHS="src/**"),
               "false", "true")
        expect("PR, a file on both lists",
               pr(repo, checkout, "both-lists", CS_DOCS_PATHS=dp,
                  CS_NOT_DOCS_PATHS="docs/reference/**"),
               "false", "true")
        expect("PR, code only",
               pr(repo, checkout, "code", CS_DOCS_PATHS=dp), "false", "false")
        expect("stacked PR, documentation only",
               pr(repo, checkout, "stacked", base="stack-base", CS_DOCS_PATHS=dp),
               "true")
        expect("PR whose base moved on with a code commit",
               pr(repo, checkout, "early-docs", CS_DOCS_PATHS=dp), "true")
        expect("PR renaming src/lib.rs to docs/lib.md",
               pr(repo, checkout, "rename", CS_DOCS_PATHS=dp), "false")
        expect("PR adding a path that is not valid UTF-8, UTF-8 locale",
               pr(repo, checkout, "bad-utf8", CS_DOCS_PATHS=dp,
                  locale="en_US.UTF-8"),
               "false", "false")
        expect("PR targeting a branch the checkout does not have",
               pr(repo, checkout, "docs", base="nope", CS_DOCS_PATHS=dp),
               "false", reason="origin/nope is not in the checkout")

        noisy = "\n   \n# a comment\n  docs/**  \r\n\n"
        expect("blank, whitespace, comment, padded and CR lines in docs-paths",
               pr(repo, checkout, "docs", CS_DOCS_PATHS=noisy), "true")
        expect("an empty not-docs-paths",
               pr(repo, checkout, "docs", CS_DOCS_PATHS=dp, CS_NOT_DOCS_PATHS=""),
               "true")
        expect("no inputs at all",
               pr(repo, checkout, "docs"), "false", "true")

        for line in ("../x", "/x", ":x"):
            expect(f"docs-paths line {line!r} beside docs/**",
                   pr(repo, checkout, "docs", CS_DOCS_PATHS=dp + line),
                   "false", reason="path list holds an unsupported line")
        for line in ('"src/**"', "- src/**"):
            expect(f"not-docs-paths line {line!r}",
                   pr(repo, checkout, "docs", CS_DOCS_PATHS=dp,
                      CS_NOT_DOCS_PATHS=line),
                   "false", reason="path list holds an unsupported line")

        # A git that fails the second diff and prints nothing: its silence
        # must not read as "nothing outside the documentation list".
        shim = Path(tmp) / "shim"
        shim.mkdir()
        real_git = shutil.which("git")
        (shim / "git").write_text(
            "#!/bin/sh\n"
            'for a in "$@"; do case $a in ":(glob,exclude)"*) exit 1;; esac; done\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        (shim / "git").chmod(0o755)
        expect("a git diff that fails",
               pr(repo, checkout, "docs", CS_DOCS_PATHS=dp, path_prefix=str(shim)),
               "false", reason="git diff failed")

        repo.commit("docs on main", {"docs/d.md": "d\n"})
        repo.push("main")
        main_head = repo.git("rev-parse", "main~1")
        main_parent = repo.git("rev-parse", "main~2")
        docs_main = repo.git("rev-parse", "main")
        checkout = repo.clone()

        def push(before, after, ref="main", **extra):
            return scope(checkout, CS_EVENT="push", CS_REF_NAME=ref,
                         CS_BEFORE=before, CS_SHA=after, CS_DOCS_PATHS=dp, **extra)

        def dispatch(ref, after, **extra):
            return scope(checkout, CS_EVENT="workflow_dispatch", CS_REF_NAME=ref,
                         CS_SHA=after, CS_DOCS_PATHS=dp, **extra)

        expect("default-branch push, documentation only",
               push(main_head, docs_main), "true")
        expect("default-branch push, code",
               push(main_parent, main_head), "false", "false")
        expect("default-branch push, before is zeros",
               push(ZERO, docs_main), "false", reason="no base commit")
        expect("default-branch push, before not in the checkout",
               push("1" * 40, docs_main), "false",
               reason=f"base {'1' * 40} is not in the checkout")
        expect("first push of another branch, documentation only",
               push(ZERO, docs, ref="docs"), "true")

        expect("dispatch on another branch, documentation only",
               dispatch("docs", docs), "true")
        expect("the same with dispatch-full",
               dispatch("docs", docs, CS_DISPATCH_FULL="true"),
               "false", reason="dispatch-full is set")
        expect("dispatch on the default branch",
               dispatch("main", docs), "false", reason="dispatch on main")
        expect("dispatch on the default branch, dispatch-full false",
               dispatch("main", docs, CS_DISPATCH_FULL="false"),
               "false", reason="dispatch on main")
        expect("dispatch on a tag with dispatch-full",
               dispatch("v1", docs, CS_REF_TYPE="tag", CS_DISPATCH_FULL="true"),
               "false", reason="dispatch on a tag")
        expect("dispatch on a tag",
               dispatch("v1", docs, CS_REF_TYPE="tag"),
               "false", reason="dispatch on a tag")
        expect("tag push",
               push(ZERO, docs, ref="v1", CS_REF_TYPE="tag"),
               "false", reason="push of a tag")
        expect("schedule",
               scope(checkout, CS_EVENT="schedule", CS_REF_NAME="main",
                     CS_SHA=docs, CS_DOCS_PATHS=dp),
               "false", reason="event schedule")
        expect("dispatch on a branch whose tip is main's (empty diff)",
               dispatch("same", repo.git("rev-parse", "same")),
               "false", reason="the change has no paths")
        expect("dispatch on a branch with no history in common with main",
               dispatch("orphan", repo.git("rev-parse", "orphan")),
               "false", reason="no merge-base")

        shallow = repo.clone("shallow", depth=2)
        expect("shallow clone",
               scope(shallow, CS_EVENT="push", CS_REF_NAME="main",
                     CS_BEFORE=main_head, CS_SHA=docs_main, CS_DOCS_PATHS=dp),
               "false", reason="shallow checkout")

        sub = checkout / "docs"
        expect("run from a subdirectory of the work tree",
               scope(sub, CS_EVENT="push", CS_REF_NAME="main",
                     CS_BEFORE=main_parent, CS_SHA=main_head, CS_DOCS_PATHS=dp),
               "false", "false")

        result = push(ZERO, repo.git("rev-parse", injection), ref=injection)
        expect(f"branch named {injection}", result, "true")
        print("the branch name was not run")
        check(not list(Path(tmp).rglob("pwned")), "no file named pwned was created")

        result = push(ZERO, repo.git("rev-parse", "korean"), ref="korean")
        expect("a path with Korean in it", result, "true")
        check("docs/한글.md" in result[2], "the log shows docs/한글.md as written")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
