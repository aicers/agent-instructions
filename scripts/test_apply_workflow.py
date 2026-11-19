#!/usr/bin/env python3
"""Run `.github/workflows/apply.yml` against throwaway consumers.

The workflow's steps are shell and Python, and almost everything that
can go wrong in it -- the title it picks, the branch it pushes, the pull
request it does or does not open, a GitHub API call that fails -- lives
in the `run:` blocks rather than in the scripts the other tests cover. So
this runs them: every step in order, with the environment the runner
would give it, from a workspace that is a checkout of a local consumer.

What stands in for the runner:

- `actions/checkout` is the one action the job uses. The caller's
  checkout becomes a depth-1 fetch from a local bare repository, done
  into the same workspace on every run so that a second run sees what a
  self-hosted runner leaves behind. The checkout of this repository at
  `main` is this working tree, and the checkout of the release is a
  fixture tree, refused unless the tag asked for is the latest release.
- `${{ }}` in `env:` and `with:` is resolved from the contexts the job
  reads, and an expression this harness does not know fails the run
  rather than resolving to nothing.
- GitHub's API is a local server, reached through `GITHUB_API_URL` as the
  runner sets it. It answers the calls the job makes, records them, and
  can be told to fail any of them.
- `PATH` holds `git`, `python3`, `curl` and `tar` and nothing else, so a
  step reaching for `gh`, or for any other tool the self-hosted machines
  are not known to carry, fails here.

The runner choice is an expression, evaluated here under both events
the callers use, for a private caller and a public one.

Run it directly; it needs nothing beyond the standard library and git.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "apply.yml"
PATTERN = ROOT / "conventional-title" / "pattern.txt"

CALLER = "aicers/consumer"
TOKEN = "ghs_not-a-real-token"
LATEST = "0.2.0"
BRANCH = f"shared-instructions/{LATEST}"
MARKERS = ("release-plz.toml", "release-please-config.json", ".manual-release")
TOOLS = ("git", "python3", "curl", "tar")

TRADITIONAL = f"Update shared instruction blocks to {LATEST}"
CONVENTIONAL = f"chore: update shared instruction blocks to {LATEST}"

# What the job has always put in the pull request and the commit; only the
# title and the commit subject move.
BODY = (
    f"Applied from `aicers/agent-instructions` at `{LATEST}` by its"
    " `apply.yml` reusable workflow, which also moved this repository's pin"
    " in `.agent-instructions.toml`.\n"
    "\n"
    "Blocks in this pull request: demo\n"
    "\n"
    "This pull request has no checks on it. One opened with `GITHUB_TOKEN`"
    " triggers no workflow runs — close it and reopen it to run them, which"
    " is worth doing the first time this job runs here.\n"
    "\n"
    "The marked blocks are generated. Change the wording upstream in"
    " `aicers/agent-instructions` rather than editing it here — the drift"
    " check in CI will fail if this repository's copy diverges.\n"
)
COMMIT_BODY = (
    f"Applied from aicers/agent-instructions at {LATEST}, which this\n"
    "repository's drift check is now pinned to. Do not edit the\n"
    "marked blocks here; change them upstream and cut a release."
)

RELEASED_BLOCK = """<!-- BEGIN shared:demo -->
## Demo

- the rule as the release has it
<!-- END shared:demo -->
"""

AGENTS = """# Instructions for AI coding agents

<!-- BEGIN shared:demo -->
- stale text
<!-- END shared:demo -->
"""

PIN = """ref = "0.1.0"
blocks = ["demo"]
"""

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


# --- reading the workflow -------------------------------------------------


@dataclass
class Step:
    name: str = ""
    id: str = ""
    uses: str = ""
    run: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    with_: dict[str, str] = field(default_factory=dict)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_steps(text: str) -> list[Step]:
    """The steps of the `apply` job, from the subset of YAML they use.

    Strict on purpose: a line in the steps that this does not recognize
    fails the test, rather than being skipped and leaving a step that
    runs on GitHub and never here.
    """
    lines = text.splitlines()
    start = lines.index("    steps:") + 1
    steps: list[Step] = []
    block: list[str] | None = None
    mapping: dict[str, str] | None = None

    def assign(step: Step, rest: str) -> None:
        nonlocal block, mapping
        key, _, value = rest.partition(":")
        value = value.strip()
        block = mapping = None
        if key == "run" and value == "|":
            block = []
            step.run = ""
        elif key == "run":
            step.run = value
        elif key in ("env", "with") and not value:
            mapping = step.env if key == "env" else step.with_
        elif key in ("name", "id", "uses"):
            setattr(step, key, unquote(value))
        else:
            raise SystemExit(f"apply.yml: unhandled step key {key!r}")

    for line in lines[start:]:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if block is not None and (not stripped or indent >= 10):
            block.append(line[10:])
            steps[-1].run = "\n".join(block)
            continue
        if not stripped:
            continue
        if stripped.startswith("#") and indent >= 6:
            block = mapping = None
            continue
        if indent == 6 and stripped.startswith("- "):
            steps.append(Step())
            assign(steps[-1], stripped[2:])
        elif indent == 8:
            assign(steps[-1], stripped)
        elif indent == 10 and mapping is not None:
            key, _, value = stripped.partition(":")
            mapping[key] = unquote(value)
        elif indent < 6:
            break
        else:
            raise SystemExit(f"apply.yml: unhandled line {line!r}")
    for step in steps:
        if step.run is not None:
            step.run = step.run.rstrip("\n") + "\n"
    return steps


def runs_on(text: str) -> str:
    match = re.search(r"(?m)^    runs-on: (.*)$", text)
    if not match:
        raise SystemExit("apply.yml: the apply job has no runs-on")
    return match.group(1)


# --- GitHub's expressions, as far as runs-on uses them ----------------------


def evaluate(template: str, contexts: dict):
    """Evaluate a value that is one `${{ }}` expression, or a literal."""
    match = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", template.strip())
    if not match:
        return template
    tokens = re.findall(
        r"'(?:[^']|'')*'|&&|\|\||\(|\)|[A-Za-z_][\w.-]*|\S", match.group(1)
    )
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else None

    def take():
        nonlocal position
        position += 1
        return tokens[position - 1]

    def truthy(value) -> bool:
        return value not in (None, False, 0, "")

    def primary():
        token = take()
        if token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if token == "(":
            value = either()
            assert take() == ")"
            return value
        if token in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[token]
        if token == "fromJSON":
            assert take() == "("
            value = json.loads(either())
            assert take() == ")"
            return value
        value = contexts
        for part in token.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    def both():
        value = primary()
        while peek() == "&&":
            take()
            right = primary()
            value = right if truthy(value) else value
        return value

    def either():
        value = both()
        while peek() == "||":
            take()
            right = both()
            value = value if truthy(value) else right
        return value

    result = either()
    if position != len(tokens):
        raise SystemExit(f"unparsed expression: {template}")
    return result


def resolve(value: str, contexts: dict) -> str:
    """Substitute every `${{ path }}` in a step's env or with value."""

    def one(match: re.Match) -> str:
        path = match.group(1)
        node = contexts
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"unknown expression {path!r}")
            node = node[part]
        return str(node)

    return re.sub(r"\$\{\{\s*([\w.-]+)\s*\}\}", one, value)


# --- GitHub -----------------------------------------------------------------


class Server:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.pulls: list[dict] = []
        self.fail: dict[str, int] = {}
        self.private = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def handle_any(self, method: str) -> None:
                url = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                key = f"{method} {url.path}"
                outer.requests.append(
                    {
                        "key": key,
                        "query": parse_qs(url.query),
                        "authorization": self.headers.get("Authorization"),
                        "body": json.loads(body) if body else None,
                    }
                )
                if key in outer.fail:
                    return self.reply(outer.fail[key], {"message": "injected"})
                if key == "GET /repos/aicers/agent-instructions/releases/latest":
                    return self.reply(200, {"tag_name": LATEST})
                if key == f"GET /repos/{CALLER}":
                    return self.reply(
                        200,
                        {"default_branch": "main", "private": outer.private},
                    )
                if key == f"GET /repos/{CALLER}/pulls":
                    query = parse_qs(url.query)
                    head = query.get("head", [""])[0]
                    found = [
                        p for p in outer.pulls
                        if f"aicers:{p['head']}" == head
                    ]
                    return self.reply(200, found[:1])
                if key == f"POST /repos/{CALLER}/pulls":
                    created = {
                        "number": 100 + len(outer.pulls),
                        "html_url": "https://github.invalid/pull/1",
                        "state": "open",
                        "merged_at": None,
                        "head": outer.requests[-1]["body"]["head"],
                    }
                    outer.pulls.append(created)
                    return self.reply(201, created)
                self.reply(404, {"message": "Not Found"})

            def do_GET(self) -> None:  # noqa: N802
                self.handle_any("GET")

            def do_POST(self) -> None:  # noqa: N802
                self.handle_any("POST")

            def reply(self, status: int, payload) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def reset(self) -> None:
        self.requests.clear()
        self.pulls.clear()
        self.fail.clear()

    def created(self) -> list[dict]:
        return [r for r in self.requests if r["key"] == f"POST /repos/{CALLER}/pulls"]

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# --- the runner ---------------------------------------------------------------


def git(root: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout


@dataclass
class Outcome:
    ok: bool
    failed: str
    log: str


class Runner:
    def __init__(self, scratch: Path, server: Server) -> None:
        self.scratch = scratch
        self.server = server
        self.steps = parse_steps(WORKFLOW.read_text(encoding="utf-8"))
        self.bin = scratch / "bin"
        self.bin.mkdir()
        for tool in TOOLS:
            found = shutil.which(tool)
            if found is None:
                raise SystemExit(f"{tool} is required")
            (self.bin / tool).symlink_to(found)
        empty = scratch / "gitconfig"
        empty.write_text("", encoding="utf-8")
        self.base_env = {
            "PATH": str(self.bin),
            "HOME": str(scratch),
            "GIT_CONFIG_GLOBAL": str(empty),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GITHUB_API_URL": server.url,
            "LANG": "C.UTF-8",
        }
        self.release = scratch / "release"
        (self.release / "blocks").mkdir(parents=True)
        (self.release / "blocks" / "demo.md").write_text(
            RELEASED_BLOCK, encoding="utf-8"
        )
        (self.release / "repos.json").write_text(
            json.dumps(
                {"org": "aicers", "target": "AGENTS.md",
                 "repos": {"consumer": ["demo"]}}
            ),
            encoding="utf-8",
        )

    def caller(self, name: str, marker_on_main: str | None = None,
               topic_marker: str | None = None) -> Path:
        """A bare repository standing in for the caller on GitHub."""
        work = self.scratch / f"{name}-source"
        work.mkdir()
        identity = {**self.base_env, "PATH": os.environ["PATH"],
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@invalid"}
        (work / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
        (work / ".agent-instructions.toml").write_text(PIN, encoding="utf-8")
        git(work, "init", "-q", "-b", "main", ".", env=identity)
        git(work, "add", "-A", env=identity)
        git(work, "commit", "-qm", "onboard", env=identity)
        # A topic branch, for a dispatch that is not started on main. It
        # forks before the marker lands, and carries one of its own if
        # asked.
        git(work, "branch", "topic", env=identity)
        if marker_on_main:
            (work / marker_on_main).parent.mkdir(parents=True, exist_ok=True)
            (work / marker_on_main).write_text("", encoding="utf-8")
            git(work, "add", "-A", env=identity)
            git(work, "commit", "-qm", "convert", env=identity)
        if topic_marker:
            git(work, "switch", "-q", "topic", env=identity)
            (work / topic_marker).write_text("", encoding="utf-8")
            git(work, "add", "-A", env=identity)
            git(work, "commit", "-qm", "convert on topic", env=identity)
            git(work, "switch", "-q", "main", env=identity)
        bare = self.scratch / f"{name}.git"
        git(self.scratch, "clone", "-q", "--bare", str(work), str(bare),
            env=identity)
        return bare

    def checkout(self, step: Step, workspace: Path, origin: Path, ref: str,
                 with_: dict[str, str]) -> None:
        env = {**self.base_env}
        if not with_:
            # What actions/checkout does in a workspace it may already have
            # used: reset and clean it, fetch the one commit, and stand on
            # it -- leaving every other local branch where it was.
            workspace.mkdir(exist_ok=True)
            if not (workspace / ".git").exists():
                git(workspace, "init", "-q", ".", env=env)
                git(workspace, "remote", "add", "origin", f"file://{origin}",
                    env=env)
            else:
                git(workspace, "reset", "-q", "--hard", env=env)
                git(workspace, "clean", "-qffdx", env=env)
            git(workspace, "fetch", "-q", "--depth=1", "origin",
                f"+refs/heads/{ref}:refs/remotes/origin/{ref}", env=env)
            git(workspace, "checkout", "-q", "-f", "-B", ref,
                f"refs/remotes/origin/{ref}", env=env)
            return
        if with_.get("repository") != "aicers/agent-instructions":
            raise SystemExit(f"unexpected checkout {with_}")
        target = workspace / with_["path"]
        shutil.rmtree(target, ignore_errors=True)
        if with_.get("ref") == "main":
            shutil.copytree(
                ROOT, target,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
        elif with_.get("ref") == LATEST:
            shutil.copytree(self.release, target)
        else:
            raise RuntimeError(f"no release {with_.get('ref')!r} to check out")

    def run(self, origin: Path, workspace: Path, *, event: str = "schedule",
            ref: str = "main") -> Outcome:
        temp = self.scratch / "runner-temp"
        shutil.rmtree(temp, ignore_errors=True)
        temp.mkdir()
        contexts = {
            "github": {
                "token": TOKEN,
                "repository": CALLER,
                "event_name": event,
            },
            "runner": {"temp": str(temp)},
            "steps": {},
        }
        log: list[str] = []
        for step in self.steps:
            try:
                env = {k: resolve(v, contexts) for k, v in step.env.items()}
                with_ = {k: resolve(v, contexts) for k, v in step.with_.items()}
            except KeyError as missing:
                raise SystemExit(f"{step.name}: {missing}") from None
            outputs: dict[str, str] = {}
            if step.uses:
                if not step.uses.startswith("actions/checkout@"):
                    raise SystemExit(f"unexpected action {step.uses}")
                try:
                    self.checkout(step, workspace, origin, ref, with_)
                except (RuntimeError, subprocess.CalledProcessError) as failure:
                    log.append(f"{step.name}: {failure}")
                    return Outcome(False, step.name, "\n".join(log))
            else:
                output = temp / f"output-{len(log)}"
                output.write_text("", encoding="utf-8")
                script = temp / "step.sh"
                script.write_text(step.run or "", encoding="utf-8")
                result = subprocess.run(
                    ["/bin/bash", "--noprofile", "--norc", "-eo", "pipefail",
                     str(script)],
                    cwd=workspace,
                    env={
                        **self.base_env,
                        "GITHUB_OUTPUT": str(output),
                        "GITHUB_WORKSPACE": str(workspace),
                        "RUNNER_TEMP": str(temp),
                        **env,
                    },
                    capture_output=True,
                    text=True,
                )
                log.append(f"## {step.name}\n{result.stdout}{result.stderr}")
                for line in output.read_text(encoding="utf-8").splitlines():
                    key, _, value = line.partition("=")
                    outputs[key] = value
                if result.returncode != 0:
                    return Outcome(False, step.name, "\n".join(log))
            if step.id:
                contexts["steps"][step.id] = {"outputs": outputs}
        return Outcome(True, "", "\n".join(log))


# --- the tests ----------------------------------------------------------------


def test_static() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    steps = parse_steps(text)
    print("the workflow's steps")
    check(len(steps) >= 10, f"are all read ({len(steps)})")
    # Comments dropped: one may mention `gh` as what a step used to call.
    scripts = [
        "\n".join(line for line in step.run.splitlines()
                  if not line.lstrip().startswith("#"))
        for step in steps if step.run is not None
    ]
    check(
        all("${{" not in script for script in scripts),
        "interpolate nothing into a run: block",
    )
    check(
        not any(re.search(r"(?m)(^|[\s;|&(`$])gh(\s|$)", s) for s in scripts),
        "never invoke gh",
    )
    check(
        not any(re.search(r"\$\{?(GITHUB_TOKEN|GH_TOKEN)", s) for s in scripts),
        "never put the token on a command line",
    )
    check(
        all(step.uses.startswith("actions/checkout@") for step in steps if step.uses),
        "use no action but actions/checkout",
    )


def test_runner() -> None:
    expression = runs_on(WORKFLOW.read_text(encoding="utf-8"))
    print("the runner")
    for event in ("schedule", "workflow_dispatch"):
        for private, want in ((True, ["self-hosted", "linux"]),
                              (False, "ubuntu-latest")):
            payload = {"repository": {"private": private,
                                      "default_branch": "main"}}
            if event == "schedule":
                payload["schedule"] = "0 6 * * 1"
            else:
                payload["inputs"] = {}
                payload["ref"] = "refs/heads/main"
            got = evaluate(
                expression,
                {"github": {"event_name": event, "event": payload}},
            )
            check(
                got == want,
                f"{'a private' if private else 'a public'} caller under"
                f" {event} runs on {want}",
            )
    got = evaluate(expression, {"github": {"event": {"schedule": "x"}}})
    check(got == "ubuntu-latest",
          "a payload without the repository falls back to a hosted runner")


def pushed(origin: Path, what: str) -> str:
    return git(origin, "log", "-1", f"--format={what}", BRANCH)


def has_branch(origin: Path) -> bool:
    return bool(git(origin, "branch", "--list", BRANCH).strip())


def test_runs(scratch: Path, server: Server) -> None:
    runner = Runner(scratch, server)
    rule = re.compile(PATTERN.read_text(encoding="utf-8")[:-1])
    counter = iter(range(1000))

    def fresh(**kwargs) -> tuple[Path, Path]:
        name = f"caller{next(counter)}"
        server.reset()
        return runner.caller(name, **kwargs), scratch / f"{name}-workspace"

    print("a caller with no marker file and no pull request")
    origin, workspace = fresh()
    outcome = runner.run(origin, workspace)
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    created = server.created()
    check(len(created) == 1, "one pull request is opened")
    if created:
        body = created[0]["body"]
        check(body["title"] == TRADITIONAL, f"titled {TRADITIONAL!r}")
        check(body["head"] == BRANCH, f"from {BRANCH}")
        check(body["base"] == "main", "into the default branch")
        check(body["body"] == BODY, "with the body it always had")
    check(pushed(origin, "%s") .strip() == TRADITIONAL, "the commit subject is the title")
    check(pushed(origin, "%b").strip() == COMMIT_BODY, "the commit body is unchanged")
    tree = git(origin, "show", f"{BRANCH}:.agent-instructions.toml")
    check(f'ref = "{LATEST}"' in tree, "the pin moves to the release")
    check(
        "- the rule as the release has it"
        in git(origin, "show", f"{BRANCH}:AGENTS.md"),
        "the blocks are the release's",
    )
    check(
        all(r["authorization"] == f"Bearer {TOKEN}" for r in server.requests),
        "every API call carries the caller's token",
    )
    lookups = [r for r in server.requests if r["key"] == f"GET /repos/{CALLER}/pulls"]
    check(
        len(lookups) == 1
        and lookups[0]["query"].get("head") == [f"aicers:{BRANCH}"]
        and lookups[0]["query"].get("state") == ["all"],
        "after looking for a pull request from the branch in any state",
    )

    print("a second run in the same workspace, as on a self-hosted runner")
    server.requests.clear()
    outcome = runner.run(origin, workspace)
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    check(not server.created(), "and opens no second pull request")
    check("already has pull request #100 (open)" in outcome.log, "saying why")

    for marker in MARKERS:
        print(f"a caller whose default branch holds {marker}")
        origin, workspace = fresh(marker_on_main=marker)
        outcome = runner.run(origin, workspace)
        check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
        created = server.created()
        check(
            len(created) == 1 and created[0]["body"]["title"] == CONVENTIONAL,
            f"titles the pull request {CONVENTIONAL!r}",
        )
        check(pushed(origin, "%s").strip() == CONVENTIONAL,
              "and the commit subject the same")
        check(pushed(origin, "%b").strip() == COMMIT_BODY,
              "with the commit body unchanged")
        check(
            bool(created) and created[0]["body"]["body"] == BODY,
            "and the pull-request body unchanged",
        )
        check(rule.search(CONVENTIONAL) is not None, "a title pattern.txt accepts")

    print("a caller whose default branch holds a directory named .manual-release")
    origin, workspace = fresh(marker_on_main=".manual-release/README.md")
    outcome = runner.run(origin, workspace)
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    created = server.created()
    check(
        len(created) == 1 and created[0]["body"]["title"] == TRADITIONAL,
        "keeps the title it had: a directory is not a marker file",
    )
    check(pushed(origin, "%s").strip() == TRADITIONAL,
          "and so does the commit subject")

    print("a dispatch from a branch without the marker the default branch has")
    origin, workspace = fresh(marker_on_main="release-plz.toml")
    outcome = runner.run(origin, workspace, event="workflow_dispatch", ref="topic")
    created = server.created()
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    check(
        len(created) == 1 and created[0]["body"]["title"] == CONVENTIONAL
        and created[0]["body"]["base"] == "main",
        "is titled by the default branch, and opened into it",
    )

    print("a dispatch from a branch with a marker the default branch lacks")
    origin, workspace = fresh(topic_marker=".manual-release")
    outcome = runner.run(origin, workspace, event="workflow_dispatch", ref="topic")
    created = server.created()
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    check(
        len(created) == 1 and created[0]["body"]["title"] == TRADITIONAL,
        "keeps the title the default branch calls for",
    )

    for state, merged in (("open", None), ("closed", None),
                          ("closed", "2026-11-01T00:00:00Z")):
        what = "merged" if merged else state
        print(f"a branch that already has a pull request, {what}")
        origin, workspace = fresh()
        server.pulls.append({"number": 7, "state": state, "merged_at": merged,
                             "head": BRANCH})
        outcome = runner.run(origin, workspace)
        check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
        check(not server.created(), "and opens none")
        check(f"already has pull request #7 ({what})" in outcome.log, "saying which")
        check(has_branch(origin), "after pushing the branch")

    print("a caller already on the latest release")
    origin, workspace = fresh()
    first = runner.run(origin, workspace)
    check(first.ok, "the first run applies it")
    # Merge it, the way a reviewer would, and take the branch away.
    git(origin, "update-ref", "refs/heads/main", f"refs/heads/{BRANCH}")
    git(origin, "update-ref", "-d", f"refs/heads/{BRANCH}")
    server.reset()
    before = git(origin, "for-each-ref")
    outcome = runner.run(origin, scratch / "on-latest-workspace")
    check(outcome.ok, "the job succeeds" + ("" if outcome.ok else f":\n{outcome.log}"))
    check(not server.created(), "and opens nothing")
    check(
        not any(r["key"].endswith("/pulls") for r in server.requests),
        "without even looking for a pull request",
    )
    check(git(origin, "for-each-ref") == before, "and pushes nothing")
    check("already on" in outcome.log or "nothing to commit" in outcome.log,
          "saying it is up to date")

    for key, step, what in (
        ("GET /repos/aicers/agent-instructions/releases/latest",
         "Resolve the latest release", "the release lookup"),
        (f"GET /repos/{CALLER}", "Title the pull request",
         "the default-branch lookup"),
        (f"GET /repos/{CALLER}/pulls", "Open the pull request",
         "the pull-request lookup"),
        (f"POST /repos/{CALLER}/pulls", "Open the pull request",
         "the pull-request creation"),
    ):
        print(f"{what} failing")
        origin, workspace = fresh()
        server.fail[key] = 500 if key.startswith("GET") else 422
        outcome = runner.run(origin, workspace)
        check(not outcome.ok, "fails the job")
        check(outcome.failed == step, f"in {step!r}")
        check("::error::GitHub API call failed" in outcome.log,
              "saying which call failed")
        if key.startswith("GET") and key.endswith("/pulls"):
            check(not server.created(), "without opening a pull request blind")


def main() -> int:
    test_static()
    test_runner()
    server = Server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            test_runs(Path(tmp), server)
    finally:
        server.close()

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all apply.yml tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
