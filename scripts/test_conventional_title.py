#!/usr/bin/env python3
"""Tests for `conventional-title/pattern.txt` and the action that reads it.

The rule is read by several checkers in several regex engines: the
`conventional-title` action here, the drive-agentcoop merge scripts, and
AgentCoop. So the expression is held to the format they all rely on --
one line, anchored, a dialect common to Python `re`, JavaScript `RegExp`
and POSIX ERE -- and every title below is put through all three, which
must give the verdict listed and agree with each other. `node` is
required; a run without it would be testing two engines out of three.

The action is then run the way a runner runs it: its `run:` line, through
`bash`, with the inputs in the environment, from a workspace holding a
pin. GitHub is replaced by a local server that serves `pattern.txt` at
the refs it knows and 404 at the rest, and `curl` by a wrapper that
records its arguments before handing over to the real one, so that the
token can be seen arriving at the server and not on a command line.

Run it directly; it needs nothing beyond the standard library, `grep`,
`curl` and `node`.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
PATTERN = ROOT / "conventional-title" / "pattern.txt"
ACTION = ROOT / "conventional-title" / "action.yml"
CHECK = ROOT / "conventional-title" / "check.py"
SCRIPTS = ROOT / "scripts"

ACCEPTED = (
    # The acceptance criteria's list.
    "feat: add a sign-in limit",
    "fix(security): reject empty tokens",
    "feat!: drop the v1 endpoint",
    "feat(api)!: rename the field",
    "chore(deps): bump serde from 1.0.210 to 1.0.215",
    "chore(main): release 0.5.2",
    "chore: release 0.30.0",
    "chore(release): bump bootler-security to 1.2.3",
    "chore: update shared instruction blocks to 0.6.0",
    "revert: feat: add a sign-in limit",
    "ci: automate releases with release-plz",
    # Every type.
    "docs: x",
    "style: x",
    "refactor: x",
    "perf: x",
    "test: x",
    "build: x",
    # Scopes at their edges.
    "fix(a): x",
    "fix(0): x",
    "fix(a.b_c-d): x",
    "fix(1-x): x",
    # Descriptions at their edges.
    "feat: a",
    "feat: x #",
    "feat: x #a",
    "feat: x ##a",
    "feat: x#",
    "feat: x ## y",
    "feat: add\tx",
    "feat: add x)",
    "feat: add x...a",
    "feat: add naïve café",
    "feat: add $(touch pwned) `x`",
    "feat: add %0A::warning::x",
)

REJECTED = (
    # The acceptance criteria's list.
    "Add a sign-in limit",
    "feat: Add a sign-in limit",
    "feat: add a sign-in limit.",
    "feat: add a sign-in limit (#12)",
    "fix: handle the case from #34",
    "feature: add x",
    "feat:add x",
    "feat:  add x",
    "feat(): add x",
    "feat(API): add x",
    "feat!(api): add x",
    "feat: ",
    "feat: x ##1 y",
    "Update shared instruction blocks to 0.6.0",
    # More of the same edges.
    "",
    "feat",
    "feat:",
    "feat: x ",
    "feat: x\t",
    "feat: x.",
    "feat: #1",
    "feat: x#1",
    "feat: x #1y",
    "feat: x ###9",
    "feat: 1x",
    "feat: Éclair",
    "feat: \tx",
    "Feat: x",
    "FEAT: x",
    " feat: x",
    "feat : x",
    "feat(-a): x",
    "feat(.a): x",
    "feat(_a): x",
    "feat(a b): x",
    "feat(a)(b): x",
    "feat!!: x",
    "feat(a)! : x",
    "fixup: x",
    "chores: x",
    "feat: add x (#41)",
)

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def expression() -> str:
    return PATTERN.read_bytes().decode("utf-8")[:-1]


# --- the file -------------------------------------------------------------


def test_format() -> None:
    print("pattern.txt is one anchored expression on one line")
    raw = PATTERN.read_bytes()
    check(raw.endswith(b"\n"), "ends with a newline")
    check(raw.count(b"\n") == 1, "holds exactly one line")
    check(b"\r" not in raw, "holds no carriage return")
    text = raw.decode("utf-8")[:-1]
    check(text.startswith("^") and text.endswith("$"), "is anchored at both ends")
    check(text.isascii(), "is ASCII")
    check(not text.lstrip("^").startswith("#"), "is not a comment")

    print("pattern.txt uses only the dialect every reader shares")
    # Only `\(` and `\)`: every other escape -- `\d`, `\w`, `\s`, `\t`,
    # `\.` -- means something different, or nothing, in one of the three.
    escapes = re.findall(r"\\(.)", text)
    check(
        all(escaped in "()" for escaped in escapes),
        f"escapes only parentheses (found {sorted(set(escapes))})",
    )
    for construct, why in (
        ("(?", "no non-capturing group, lookaround or inline flag"),
        ("[:", "no POSIX character class"),
        ("[=", "no equivalence class"),
        ("[.", "no collating symbol"),
        ("*?", "no lazy `*`"),
        ("+?", "no lazy `+`"),
        ("??", "no lazy `?`"),
        ("{", "no interval quantifier"),
    ):
        check(construct not in text, why)


# --- the three engines ----------------------------------------------------


def python_verdicts(titles: list[str]) -> list[bool]:
    rule = re.compile(expression())
    return [rule.search(title) is not None for title in titles]


def grep_verdicts(titles: list[str], scratch: Path) -> list[bool]:
    # One title per line, every title a line: none of them holds a line
    # break, which is what lets `grep -E` judge whole titles at all.
    listing = scratch / "titles.txt"
    listing.write_bytes(
        b"".join(title.encode("utf-8") + b"\n" for title in titles)
    )
    result = subprocess.run(
        ["grep", "-nE", "-e", expression(), str(listing)],
        capture_output=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode not in (0, 1):
        raise SystemExit(f"grep failed: {result.stderr.decode()}")
    matched = {
        int(line.split(b":", 1)[0]) for line in result.stdout.splitlines()
    }
    return [index + 1 in matched for index in range(len(titles))]


NODE = """
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const text = fs.readFileSync(input.pattern, "utf8");
const rule = new RegExp(text.slice(0, -1));
process.stdout.write(JSON.stringify(input.titles.map((t) => rule.test(t))));
"""


def node_verdicts(titles: list[str]) -> list[bool]:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("node is required: the rule is read by JavaScript too")
    result = subprocess.run(
        [node, "-e", NODE],
        input=json.dumps({"pattern": str(PATTERN), "titles": titles}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_engines(scratch: Path) -> None:
    titles = list(ACCEPTED) + list(REJECTED)
    expected = [True] * len(ACCEPTED) + [False] * len(REJECTED)
    python = python_verdicts(titles)
    grep = grep_verdicts(titles, scratch)
    node = node_verdicts(titles)
    print("every title gets its verdict from Python, grep -E and node")
    for title, want, a, b, c in zip(titles, expected, python, grep, node):
        verdict = "accepts" if want else "rejects"
        check(
            a == b == c == want,
            f"{verdict} {title!r}"
            + ("" if a == b == c else f" (python {a}, grep {b}, node {c})"),
        )


# --- the action -----------------------------------------------------------


class Server:
    """GitHub, as far as the action asks it anything."""

    def __init__(self, rules: dict[str, bytes]) -> None:
        self.rules = rules
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
                url = urlparse(self.path)
                ref = parse_qs(url.query).get("ref", [""])[0]
                outer.requests.append(
                    {
                        "path": url.path,
                        "ref": ref,
                        "authorization": self.headers.get("Authorization"),
                        "accept": self.headers.get("Accept"),
                    }
                )
                wanted = (
                    "/repos/aicers/agent-instructions/contents/"
                    "conventional-title/pattern.txt"
                )
                if url.path != wanted:
                    self.reply(404, b'{"message":"Not Found"}')
                elif ref == "broken":
                    self.reply(500, b'{"message":"Server Error"}')
                elif ref in outer.rules:
                    self.reply(200, outer.rules[ref])
                else:
                    self.reply(404, b'{"message":"Not Found"}')

            def reply(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def run_line() -> str:
    """The action's `run:` line, which is what the runner hands bash."""
    for line in ACTION.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("run: "):
            return stripped.removeprefix("run: ")
    raise SystemExit("action.yml has no run: line")


class Harness:
    def __init__(self, scratch: Path, server: Server) -> None:
        self.scratch = scratch
        self.server = server
        self.workspace = scratch / "workspace"
        self.bin = scratch / "bin"
        self.argv_log = scratch / "curl-argv"
        self.bin.mkdir()
        curl = shutil.which("curl")
        if curl is None:
            raise SystemExit("curl is required")
        (self.bin / "curl").write_text(
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$*" >> "{self.argv_log}"\n'
            f'exec "{curl}" "$@"\n',
            encoding="utf-8",
        )
        (self.bin / "curl").chmod(0o755)

    def pin(self, ref: str | None) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)
        self.workspace.mkdir()
        if ref is not None:
            subprocess.run(
                [sys.executable, str(SCRIPTS / "pin_file.py"), "write",
                 str(self.workspace), ref, "workflow",
                 # A converted repository takes the Conventional variant;
                 # its pin must read as any other.
                 "commit-messages:conventional"],
                check=True,
                capture_output=True,
            )

    def run(
        self, title: str, pr_suffix: str = "false", token: str = "a-token"
    ) -> subprocess.CompletedProcess:
        environment = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.scratch),
            "GITHUB_WORKSPACE": str(self.workspace),
            "GITHUB_API_URL": self.server.url,
            "CT_TITLE": title,
            "CT_PR_SUFFIX": pr_suffix,
            "GH_TOKEN": token,
            "SCRIPTS": str(ROOT / "conventional-title" / ".." / "scripts"),
            "CHECK": str(CHECK),
        }
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", run_line()],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
        )


def log_lines(result: subprocess.CompletedProcess) -> list[str]:
    """Every line a runner would log, split where a log viewer splits."""
    return [
        line
        for line in re.split(r"\r\n|\r|\n", result.stdout + result.stderr)
        if line
    ]


def test_action_shape() -> None:
    print("the action is a composite action that takes its inputs safely")
    text = ACTION.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    check("using: composite" in lines, "declares `using: composite`")
    check(
        not any(line.startswith("- uses:") or line.startswith("uses:")
                for line in lines),
        "checks nothing out and calls no other action",
    )
    steps = [i for i, line in enumerate(lines) if line.startswith("- name:")]
    check(len(steps) >= 1, "has a step")
    for index in steps:
        end = next((s for s in steps if s > index), len(lines))
        check(
            any(line.startswith("shell:") for line in lines[index:end]),
            f"{lines[index].removeprefix('- name: ')!r} sets `shell:`",
        )
    check("${{" not in run_line(), "the run: line interpolates nothing")
    check(
        "CT_TITLE: ${{ inputs.title }}" in lines,
        "the title reaches the step only as an environment variable",
    )
    check(
        "SCRIPTS: ${{ github.action_path }}/../scripts" in lines,
        "pin_file.py is reached through github.action_path",
    )
    check(
        re.search(r"(?m)^\s*pr-suffix:\n(?:\s+.*\n)*?\s+default: \"false\"$", text)
        is not None,
        'pr-suffix defaults to "false"',
    )
    # The rule is written once, in pattern.txt. The checker must read it,
    # not restate it.
    source = CHECK.read_text(encoding="utf-8")
    check(
        "feat|fix" not in source and "refactor|" not in source,
        "check.py does not restate the expression",
    )


def test_action(scratch: Path) -> None:
    rule = PATTERN.read_bytes()
    server = Server(
        {
            "1.0.0": rule,
            "two-lines": b"^feat: x$\n^fix: x$\n",
            "no-newline": rule.rstrip(b"\n"),
        }
    )
    try:
        harness = Harness(scratch, server)

        print("an accepted title")
        harness.pin("1.0.0")
        result = harness.run("feat: add a sign-in limit")
        check(result.returncode == 0, "passes")
        check(
            'Conventional title: "feat: add a sign-in limit"' in result.stdout,
            "and prints the title",
        )
        check(server.requests[-1]["ref"] == "1.0.0", "reading the rule at the pin")
        check(
            server.requests[-1]["authorization"] == "Bearer a-token",
            "with the caller's token",
        )
        check(
            "a-token" not in harness.argv_log.read_text(encoding="utf-8"),
            "which never appears on curl's command line",
        )

        print("a rejected title")
        result = harness.run("feat: Add a sign-in limit")
        check(result.returncode == 1, "fails")
        errors = [line for line in log_lines(result) if line.startswith("::error::")]
        check(len(errors) == 1, "with one ::error::")
        check(
            bool(errors) and '"feat: Add a sign-in limit"' in errors[0],
            "quoting the title",
        )
        check(
            bool(errors) and "<type>[(<scope>)][!]: <description>" in errors[0],
            "and stating the expected form",
        )

        print("pr-suffix")
        for title, passes in (
            ("feat: add x (#41)", True),
            ("chore(main): release 0.5.2 (#7)", True),
            ("feat: add x", False),
            ("feat: add x (#41) (#42)", False),
            ("Add x (#41)", False),
            ("feat: add x (#)", False),
            ("feat: add x(#41)", False),
        ):
            result = harness.run(title, pr_suffix="true")
            check(
                (result.returncode == 0) == passes,
                f"{'passes' if passes else 'fails'} {title!r}",
            )
        result = harness.run("feat: add x", pr_suffix="true")
        check(
            "does not end with ' (#<number>)'" in result.stdout,
            "a title without the suffix is told what it lacks",
        )
        result = harness.run("feat: add x (#41)")
        check(
            result.returncode == 1,
            "without pr-suffix, a suffixed title fails like any '#<digit>'",
        )
        result = harness.run("feat: add x", pr_suffix="yes")
        check(
            result.returncode == 1 and "pr-suffix is" in result.stdout,
            "a pr-suffix other than true or false fails, saying so",
        )

        print("a title holding shell syntax")
        for title, passes in (
            ("feat: add $(touch pwned) `touch pwned-too`", True),
            ("Feat: $(touch pwned) `touch pwned-too`; touch pwned-three", False),
            ('feat: add "; touch pwned; echo "', True),
        ):
            result = harness.run(title)
            check(
                (result.returncode == 0) == passes,
                f"{'passes' if passes else 'fails'} {title!r}, checked as text",
            )
            created = sorted(p.name for p in harness.workspace.iterdir()
                             if p.name.startswith("pwned"))
            check(not created, "and executes nothing")

        print("a title holding a line break")
        for title in (
            "feat: add x\n::warning::x",
            "feat: add x\r::warning::x",
            "feat: add x\r\n::warning::x",
            "feat: add x\n",
            "feat: add x\r",
            "\nfeat: add x",
        ):
            for suffix in ("false", "true"):
                result = harness.run(title + (" (#1)" if suffix == "true" else ""),
                                     pr_suffix=suffix)
                check(result.returncode == 1, f"fails {title!r} (pr-suffix {suffix})")
                lines = log_lines(result)
                check(
                    bool(lines) and all(line.startswith("::error::") for line in lines),
                    "and no line of the log starts with text from the title",
                )
                check(
                    "line break" in result.stdout,
                    "saying it holds a line break",
                )

        print("a title holding the runner's escape character")
        result = harness.run("feat: Add %0A::warning::x")
        check(result.returncode == 1, "fails")
        check(
            "%0A::warning" not in result.stdout and "%250A::warning" in result.stdout,
            "with `%` escaped, so the annotation cannot grow a line",
        )

        print("an anonymous caller")
        result = harness.run("feat: add x", token="")
        check(result.returncode == 0, "still reads a public rule")
        check(server.requests[-1]["authorization"] is None, "sending no header")

        print("no pin")
        harness.pin(None)
        result = harness.run("feat: add x")
        check(result.returncode == 1, "fails")
        check(
            "::error::Could not read the pin in .agent-instructions.toml"
            in result.stdout,
            "naming the pin file as the cause",
        )
        check("no such file" in result.stdout, "and saying it is missing")

        print("a pin that cannot be read")
        harness.pin(None)
        (harness.workspace / ".agent-instructions.toml").write_text(
            'ref = "1.0.0"\n', encoding="utf-8"
        )
        result = harness.run("feat: add x")
        check(result.returncode == 1, "fails")
        check(
            "Could not read the pin" in result.stdout and "no blocks" in result.stdout,
            "saying what the pin lacks",
        )

        print("a pin to a release older than pattern.txt")
        harness.pin("0.5.0")
        result = harness.run("feat: add x")
        check(result.returncode == 1, "fails")
        check(
            "at 0.5.0, the release .agent-instructions.toml pins, has no"
            " conventional-title/pattern.txt" in result.stdout,
            "naming the release and the missing file",
        )

        print("a rule GitHub could not serve")
        harness.pin("broken")
        result = harness.run("feat: add x")
        check(result.returncode == 1 and "HTTP 500" in result.stdout,
              "fails, naming the status")

        print("a rule not in the one-line format")
        for ref in ("two-lines", "no-newline"):
            harness.pin(ref)
            result = harness.run("feat: x")
            check(
                result.returncode == 1
                and "is not one anchored expression on one line" in result.stdout,
                f"fails for {ref}",
            )
    finally:
        server.close()


def main() -> int:
    test_format()
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        (scratch / "engines").mkdir()
        test_engines(scratch / "engines")
        test_action_shape()
        (scratch / "action").mkdir()
        test_action(scratch / "action")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all conventional-title tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
