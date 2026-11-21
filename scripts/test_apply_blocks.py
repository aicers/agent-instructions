#!/usr/bin/env python3
"""Tests for apply_blocks.py and the pin file it writes.

`render.py` is covered on its own; the sequence that drives it was not,
and it is the one path here with effects on another repository. Since
`apply.yml` landed it also runs unattended, on a schedule, in every
consumer — so what gets tested is a throwaway consumer built in a
temporary directory, and what the script leaves on its disk.

`pin_file.py` is covered from here rather than from a file of its own:
what the apply writes and what the drift check reads have to be the same
two keys, and a test that writes with one and reads with the other says
so.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # tomllib arrived in 3.11
    tomllib = None

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
APPLY = SCRIPTS / "apply_blocks.py"
# A real, public consumer's AGENTS.md as 0.5.0 left it, copied verbatim
# from its default branch, with the Commit messages rules still inside
# its workflow region. `.txt` so that this repository's markdownlint does
# not take it for one of its own.
CONSUMER = SCRIPTS / "fixtures" / "consumer-agents.txt"
CONSUMER_PIN = (
    'ref = "0.5.0"\nblocks = ["workflow", "agentcoop", "rust", "changelog"]\n'
)
PIN_FILE = SCRIPTS / "pin_file.py"

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

PIN = """ref = "0.1.0"
blocks = ["demo", "other", "retired"]
"""

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def release(
    root: Path,
    repos: dict[str, list[str]],
    *,
    blocks: dict[str, str] | None = RELEASE,
    target: str = "AGENTS.md",
) -> Path:
    """A checkout of this repository at a release: blocks and repos.json."""
    root.mkdir(parents=True)
    (root / "repos.json").write_text(
        json.dumps({"org": "aicers", "target": target, "repos": repos}),
        encoding="utf-8",
    )
    if blocks is not None:
        directory = root / "blocks"
        directory.mkdir()
        for name, body in blocks.items():
            (directory / f"{name}.md").write_text(body, encoding="utf-8")
    return root


def consumer(root: Path, agents: str = AGENTS, pin: str | None = PIN) -> Path:
    root.mkdir(parents=True)
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    if pin is not None:
        (root / ".agent-instructions.toml").write_text(pin, encoding="utf-8")
    return root


def pin_of(root: Path) -> str:
    return (root / ".agent-instructions.toml").read_text(encoding="utf-8")


def run(
    release_root: Path,
    root: Path,
    tag: str,
    repository: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(APPLY),
            str(release_root),
            str(root),
            repository if repository is not None else root.name,
            tag,
        ],
        capture_output=True,
        text=True,
    )


def read(root: Path, *field: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIN_FILE), "read", str(root), *field],
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        print("applying a release to a consumer")
        upstream = release(tmp / "upstream", {"consumer": ["demo", "other"]})
        root = consumer(tmp / "consumer")
        result = run(upstream, root, "0.2.0")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
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
        check(
            "shared:retired" not in agents,
            "a block repos.json dropped is removed",
        )
        check(
            "a rule withdrawn upstream" not in agents,
            "its content goes with it",
        )
        check("\n\n\n" not in agents, "removing it leaves no blank-line scar")
        check('ref = "0.2.0"' in pin_of(root), "the pin moves")
        check(
            'blocks = ["demo", "other"]' in pin_of(root),
            "the pin lists what repos.json says this repository carries",
        )
        check(
            agents.startswith("# Instructions for AI coding agents\n")
            and agents.endswith("## CI requirements\n\n- local content\n"),
            "content outside the markers is untouched",
        )
        check(
            not (root / ".github").exists(),
            "no workflow file is written",
        )

        print("reading back what was written")
        result = read(root)
        check(result.returncode == 0, "exits 0")
        check(
            result.stdout == "ref=0.2.0\nblocks=demo other\n",
            "prints both keys in the shape $GITHUB_OUTPUT takes",
        )
        check(
            read(root, "blocks").stdout == "demo other\n",
            "prints one field on its own when asked for it",
        )

        # `pin_file.py` emits the file by hand and reads it back with a
        # regex over two keys of known shape, which is what spares every
        # consumer's runner a TOML dependency. It is still a `.toml`, so
        # anything else opening it will use a real parser -- and that has to
        # find the same two keys.
        print("parsing what was written as TOML")
        if tomllib is None:
            print("  skip this runner is older than Python 3.11")
        else:
            check(
                tomllib.loads(pin_of(root))
                == {"ref": "0.2.0", "blocks": ["demo", "other"]},
                "a real parser reads the same two keys",
            )

        print("re-running against the result")
        before = (agents, pin_of(root))
        result = run(upstream, root, "0.2.0")
        check(result.returncode == 0, "exits 0")
        check(
            ((root / "AGENTS.md").read_text(encoding="utf-8"), pin_of(root))
            == before,
            "changes nothing",
        )

        print("a caller passing owner/name, as github.repository does")
        owned = consumer(tmp / "owned")
        result = run(
            release(tmp / "owned-upstream", {"owned": ["demo"]}),
            owned,
            "0.2.0",
            "aicers/owned",
        )
        check(result.returncode == 0, "exits 0")
        check(
            'ref = "0.2.0"' in pin_of(owned),
            "the owner is stripped rather than searched for",
        )

        print("a repository with no pin file")
        unpinned = consumer(tmp / "unpinned", pin=None)
        result = run(
            release(
                tmp / "unpinned-upstream", {"unpinned": ["demo", "other"]}
            ),
            unpinned,
            "0.2.0",
        )
        check(result.returncode != 0, "exits non-zero")
        check(
            ".agent-instructions.toml" in result.stderr
            and 'ref = "' in result.stderr,
            "names the file and what to put in it",
        )
        check(
            (unpinned / "AGENTS.md").read_text(encoding="utf-8") == AGENTS,
            "nothing is written",
        )
        check(
            not (unpinned / ".agent-instructions.toml").exists(),
            "and the file is not created behind the message",
        )

        print("a repository absent from repos.json")
        stranger = consumer(tmp / "stranger")
        result = run(
            release(tmp / "stranger-upstream", {"other": ["demo"]}),
            stranger,
            "0.2.0",
        )
        check(result.returncode != 0, "exits non-zero")
        check("not in" in result.stderr and "repos.json" in result.stderr,
              "says where to add it")
        check(
            (stranger / "AGENTS.md").read_text(encoding="utf-8") == AGENTS
            and pin_of(stranger) == PIN,
            "nothing is written",
        )

        print("a repository repos.json lists with no blocks")
        idle = consumer(tmp / "idle")
        result = run(
            release(tmp / "idle-upstream", {"idle": []}), idle, "0.2.0"
        )
        check(result.returncode != 0, "exits non-zero")
        check(
            (idle / "AGENTS.md").read_text(encoding="utf-8") == AGENTS
            and pin_of(idle) == PIN,
            "nothing is written",
        )

        # repos.json comes from the release, so upstream can now retire a
        # block by dropping it from both — but a release checked out from
        # somewhere unintended looks the same as a repository whose every
        # block was retired at once. Only the second is refused.
        print("a block repos.json lists that the release has retired")
        listed = consumer(tmp / "listed")
        result = run(
            release(
                tmp / "listed-upstream",
                {"listed": ["demo", "other", "gone"]},
            ),
            listed,
            "0.2.0",
        )
        agents = (listed / "AGENTS.md").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        check("retiring here too" in result.stdout, "says it dropped one")
        check(
            'blocks = ["demo", "other"]' in pin_of(listed),
            "the pin stops naming it",
        )
        check("- current text" in agents, "the surviving blocks are applied")

        print("a release carrying none of them")
        empty = consumer(tmp / "empty")
        result = run(
            release(
                tmp / "empty-upstream",
                {"empty": ["demo", "other"]},
                blocks=None,
            ),
            empty,
            "0.2.0",
        )
        check(result.returncode != 0, "exits non-zero")
        check(
            "refusing to treat that as retiring all of them" in result.stderr,
            "says why",
        )
        check(
            (empty / "AGENTS.md").read_text(encoding="utf-8") == AGENTS
            and pin_of(empty) == PIN,
            "nothing is written",
        )

        # Naming a block in repos.json is how a repository takes on a new
        # one, and nothing in the repository has to change first: the
        # region goes after the block the list puts before it.
        print("a listed block the repository has no markers for")
        partial = consumer(
            tmp / "partial",
            agents="# Instructions\n\n"
            "<!-- BEGIN shared:demo -->\nstale text\n<!-- END shared:demo -->\n"
            "\n## Local\n\n- local content\n",
        )
        result = run(
            release(tmp / "partial-upstream", {"partial": ["demo", "other"]}),
            partial,
            "0.2.0",
        )
        check(result.returncode == 0, "exits 0")
        check(
            (partial / "AGENTS.md").read_text(encoding="utf-8")
            == "# Instructions\n\n"
            + RELEASE["demo"]
            + "\n"
            + RELEASE["other"]
            + "\n## Local\n\n- local content\n",
            "inserts it right after its predecessor's END marker",
        )
        check(
            'blocks = ["demo", "other"]' in pin_of(partial),
            "and the pin names it",
        )
        before = (partial / "AGENTS.md").read_text(encoding="utf-8")
        run(tmp / "partial-upstream", partial, "0.2.0")
        check(
            (partial / "AGENTS.md").read_text(encoding="utf-8") == before,
            "a second apply changes nothing",
        )

        # In list order, so a block inserted a moment ago is the
        # predecessor the next one lands behind.
        print("several missing blocks in a row")
        chain_blocks = dict(RELEASE)
        for extra in ("one", "two", "first"):
            chain_blocks[extra] = (
                f"<!-- BEGIN shared:{extra} -->\n## {extra.title()}\n\n"
                f"- {extra} text\n<!-- END shared:{extra} -->\n"
            )
        chain = consumer(
            tmp / "chain",
            agents="# Instructions\n\n" + RELEASE["demo"] + "\n"
            + RELEASE["other"] + "\n## Local\n",
        )
        result = run(
            release(
                tmp / "chain-upstream",
                {"chain": ["first", "demo", "one", "two", "other"]},
                blocks=chain_blocks,
            ),
            chain,
            "0.2.0",
        )
        text = (chain / "AGENTS.md").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        render_names = subprocess.run(
            [sys.executable, str(SCRIPTS / "render.py"), "names",
             str(chain / "AGENTS.md")],
            capture_output=True, text=True,
        ).stdout.split()
        check(
            render_names == ["first", "demo", "one", "two", "other"],
            "each lands after the one before it, an inserted one included",
        )
        check(
            text.startswith("# Instructions\n\n<!-- BEGIN shared:first -->"),
            "one with no predecessor in the file goes before the first region",
        )
        check("\n\n\n" not in text, "every region is set off by one blank line")
        check(text.endswith("\n## Local\n"), "the repository's own text stays")

        # The block before it in the list has been retired, and its region
        # is about to be removed. Landing after that region would leave the
        # new one wherever the retired one was, not where the list puts it.
        print("a missing block whose predecessor is retired")
        skip_blocks = dict(chain_blocks)
        retiring = consumer(
            tmp / "retiring",
            agents="# Instructions\n\n"
            "<!-- BEGIN shared:gone -->\n- old\n<!-- END shared:gone -->\n\n"
            + RELEASE["demo"]
            + "\n## Local\n",
        )
        result = run(
            release(
                tmp / "retiring-upstream",
                {"retiring": ["demo", "gone", "one"]},
                blocks=skip_blocks,
            ),
            retiring,
            "0.2.0",
        )
        check(result.returncode == 0, "exits 0")
        check(
            (retiring / "AGENTS.md").read_text(encoding="utf-8")
            == "# Instructions\n\n" + RELEASE["demo"] + "\n"
            + chain_blocks["one"] + "\n## Local\n",
            "goes after the nearest predecessor the release still has",
        )

        # Where the generated text starts in a file that has none is a
        # decision for whoever onboards it.
        print("a repository whose file has no shared region at all")
        bare = consumer(tmp / "bare", agents="# Instructions\n\n## Local\n")
        result = run(
            release(tmp / "bare-upstream", {"bare": ["demo"]}), bare, "0.2.0"
        )
        check(result.returncode != 0, "exits non-zero")
        check(
            "no shared:demo block" in result.stderr
            and "add the markers first" in result.stderr,
            "with the message it always gave",
        )
        check(
            (bare / "AGENTS.md").read_text(encoding="utf-8")
            == "# Instructions\n\n## Local\n",
            "and the file is left as it was",
        )

        # A variant is another text for the same region. Switching between
        # it and the default rewrites what is between the markers, and the
        # markers stay where they were.
        print("a block listed with a variant")
        variants = dict(RELEASE)
        variants["demo.alt"] = """<!-- BEGIN shared:demo -->
## Demo

- the alternative text
<!-- END shared:demo -->
"""
        switching = consumer(tmp / "switching")
        alt_upstream = release(
            tmp / "alt-upstream",
            {"switching": ["demo:alt", "other"]},
            blocks=variants,
        )
        result = run(alt_upstream, switching, "0.2.0")
        text = (switching / "AGENTS.md").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        check(
            "<!-- BEGIN shared:demo -->\n## Demo\n\n- the alternative text\n"
            "<!-- END shared:demo -->" in text,
            "renders the variant's text into shared:demo",
        )
        check("shared:demo:alt" not in text and "shared:demo.alt" not in text,
              "and names the region after the block, not the variant")
        check(
            'blocks = ["demo:alt", "other"]' in pin_of(switching),
            "the pin records the variant",
        )
        check(read(switching, "blocks").stdout == "demo:alt other\n",
              "and reads it back")
        check("shared:retired" not in text,
              "an unlisted region is still removed")
        with_variant = text

        result = run(
            release(
                tmp / "default-upstream",
                {"switching": ["demo", "other"]},
                blocks=variants,
            ),
            switching,
            "0.3.0",
        )
        text = (switching / "AGENTS.md").read_text(encoding="utf-8")
        check(result.returncode == 0, "switching to the default exits 0")
        check(
            text == with_variant.replace(
                "- the alternative text", "- current text"
            ),
            "replaces only the text between the markers",
        )
        check('blocks = ["demo", "other"]' in pin_of(switching),
              "and the pin drops the variant")

        result = run(alt_upstream, switching, "0.4.0")
        check(
            (switching / "AGENTS.md").read_text(encoding="utf-8")
            == with_variant,
            "switching back restores the variant in the same place",
        )

        print("a variant the release does not carry")
        missing = consumer(tmp / "missing")
        result = run(
            release(
                tmp / "missing-upstream",
                {"missing": ["demo:nope", "other"]},
                blocks=variants,
            ),
            missing,
            "0.2.0",
        )
        check(result.returncode != 0, "exits non-zero when the block is there")
        check("not a retirement" in result.stderr, "says why")
        check(
            (missing / "AGENTS.md").read_text(encoding="utf-8") == AGENTS
            and pin_of(missing) == PIN,
            "nothing is written",
        )

        result = run(
            release(
                tmp / "gone-upstream",
                {"missing": ["demo", "other", "retired:alt"]},
                blocks=variants,
            ),
            missing,
            "0.2.0",
        )
        check(
            result.returncode == 0 and "retiring here too" in result.stdout,
            "a variant of a block the release no longer has is retired",
        )
        check(
            'blocks = ["demo", "other"]' in pin_of(missing)
            and "shared:retired"
            not in (missing / "AGENTS.md").read_text(encoding="utf-8"),
            "and its region goes with it",
        )

        print("names repos.json cannot mean")
        for description, listing in (
            ("a dot in place of the colon", ["demo.alt", "other"]),
            ("an empty block", [":alt", "other"]),
            ("an empty variant", ["demo:", "other"]),
            ("two variants", ["demo:alt:more", "other"]),
            ("one region named twice", ["demo", "demo:alt"]),
        ):
            slug = description.replace(" ", "-")
            odd = consumer(tmp / f"names-{slug}")
            result = run(
                release(
                    tmp / f"names-{slug}-upstream",
                    {odd.name: listing},
                    blocks=variants,
                ),
                odd,
                "0.2.0",
            )
            check(result.returncode != 0, f"{description} exits non-zero")
            check(
                (odd / "AGENTS.md").read_text(encoding="utf-8") == AGENTS
                and pin_of(odd) == PIN,
                f"{description} writes nothing",
            )

        # What this tree's blocks do to a repository that is on 0.5.0 and
        # takes the default blocks: the Commit messages section leaves the
        # workflow region for a region of its own right after it, and
        # nothing else in the file moves or changes. The consumer's entry
        # is pinned to the default blocks in a copy of this tree, since
        # this tree's own repos.json moves repositories to the variants
        # one batch at a time.
        print("this tree applied to a current consumer")
        default_tree = tmp / "default-tree"
        shutil.copytree(ROOT / "blocks", default_tree / "blocks")
        roster = json.loads((ROOT / "repos.json").read_text(encoding="utf-8"))
        roster["repos"]["bootroot"] = [
            "workflow", "commit-messages", "agentcoop", "rust", "changelog"
        ]
        (default_tree / "repos.json").write_text(
            json.dumps(roster, indent=2) + "\n", encoding="utf-8"
        )
        original = CONSUMER.read_text(encoding="utf-8")
        current = consumer(
            tmp / "bootroot", agents=original, pin=CONSUMER_PIN
        )
        result = run(default_tree, current, "0.6.0")
        applied = (current / "AGENTS.md").read_text(encoding="utf-8")
        check(result.returncode == 0, "exits 0")
        heading = "## Commit messages\n"
        section_start = original.index(heading)
        section_end = original.index("## Branching and pushing\n")
        section = original[section_start:section_end].rstrip("\n")
        without = original[:section_start] + original[section_end:]
        workflow_end = "<!-- END shared:workflow -->"
        expected = without.replace(
            workflow_end,
            workflow_end
            + "\n\n<!-- BEGIN shared:commit-messages -->\n"
            + section
            + "\n<!-- END shared:commit-messages -->",
            1,
        )
        check(applied == expected,
              "only the section moves, and its markers are added")
        check(
            sorted(applied.splitlines())
            == sorted(
                original.splitlines()
                + ["<!-- BEGIN shared:commit-messages -->",
                   "<!-- END shared:commit-messages -->"]
            ),
            "every line it had is still there, once",
        )
        check(
            'blocks = ["workflow", "commit-messages", "agentcoop", "rust",'
            ' "changelog"]' in pin_of(current),
            "the pin names the new block where the list does",
        )

        # `target` is a repos.json key and reaches the script unexamined,
        # so a mistyped one must fail where it was read rather than rewrite
        # a file outside the repository being applied to. All three shapes
        # are refused before the pin moves, so the repository itself is
        # left alone too.
        print("a target outside the repository")
        outside = tmp / "outside"
        outside.mkdir()
        bystander = outside / "AGENTS.md"
        bystander.write_text(AGENTS, encoding="utf-8")
        escape = consumer(tmp / "escape")
        link = escape / "LINKED.md"
        link.symlink_to(bystander)
        for index, (description, value) in enumerate((
            ("an absolute target", str(bystander)),
            ("a relative target that climbs out", "../outside/AGENTS.md"),
            ("a symlink pointing out of the tree", "LINKED.md"),
        )):
            result = run(
                release(
                    tmp / f"escape-upstream-{index}",
                    {"escape": ["demo", "other"]},
                    target=value,
                ),
                escape,
                "0.2.0",
            )
            check(result.returncode != 0, f"{description} exits non-zero")
            check("outside" in result.stderr, f"{description} says why")
        check(
            bystander.read_text(encoding="utf-8") == AGENTS,
            "the file outside is untouched",
        )
        check(pin_of(escape) == PIN, "the repository's own pin never moved")

        print("a repository with no target file")
        headless = tmp / "headless"
        headless.mkdir(parents=True)
        (headless / ".agent-instructions.toml").write_text(
            PIN, encoding="utf-8"
        )
        check(
            run(
                release(tmp / "headless-upstream", {"headless": ["demo"]}),
                headless,
                "0.2.0",
            ).returncode
            != 0,
            "exits non-zero",
        )

        # The file is written by the apply but created by a person, so the
        # reader takes what a person would plausibly write rather than only
        # what the writer emits.
        print("reading a hand-written pin file")
        handwritten = consumer(
            tmp / "handwritten",
            pin="""# which release we are on
ref = '0.1.0'  # bumped by the apply
blocks = [
  "demo",
  "other",
]
""",
        )
        result = read(handwritten)
        check(result.returncode == 0, "exits 0")
        check(
            result.stdout == "ref=0.1.0\nblocks=demo other\n",
            "comments, single quotes, and a list over several lines all read",
        )

        # The last two would otherwise read as something: an unclosed quote
        # swallows the next line into the tag, and a name with a space in it
        # splits into two blocks once the caller's shell has it. Both leave
        # here as `$GITHUB_OUTPUT` lines, so the reader has to refuse what
        # the writer would.
        print("reading a pin file that does not say both things usably")
        for description, body, says in (
            ("no file at all", None, "no such file"),
            ("no ref", 'blocks = ["demo"]\n', "no ref"),
            ("no blocks", 'ref = "0.1.0"\n', "no blocks"),
            (
                "an empty list",
                'ref = "0.1.0"\nblocks = []\n',
                "blocks is empty",
            ),
            (
                "an unclosed quote",
                'ref = "0.1.0\nblocks = ["demo"]\n',
                "not a usable release tag",
            ),
            (
                "a block name with a space",
                'ref = "0.1.0"\nblocks = ["de mo"]\n',
                "not a usable block name",
            ),
        ):
            slug = description.replace(" ", "-")
            broken = consumer(tmp / f"broken-{slug}", pin=body)
            result = read(broken)
            check(result.returncode != 0, f"{description} exits non-zero")
            check(says in result.stderr, f"{description} says what is missing")

        # Neither value can be anything the reader above would refuse, or
        # the apply would rewrite a consumer's file and then fail reading
        # back what it had just written -- blaming that file rather than
        # the tag or the repos.json entry that is actually wrong.
        print("writing what the reader would refuse")
        for description, tag, block in (
            ("a block name needing an escape", "0.2.0", 'a"b'),
            ("a release tag that is not one word", "0.2 beta", "demo"),
        ):
            slug = description.replace(" ", "-")
            odd = consumer(tmp / f"odd-{slug}")
            result = subprocess.run(
                [sys.executable, str(PIN_FILE), "write", str(odd), tag, block],
                capture_output=True,
                text=True,
            )
            check(result.returncode != 0, f"{description} exits non-zero")
            check(pin_of(odd) == PIN, f"{description} writes nothing")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all apply_blocks.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
