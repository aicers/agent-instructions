#!/usr/bin/env python3
"""Tests for render.py.

Ten repositories' CI depends on render.py, so its command-line contract
is what gets tested: exit codes, what lands on disk, and what is left
alone. Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

RENDER = Path(__file__).resolve().parent / "render.py"

BLOCK = """<!-- BEGIN shared:demo -->
## Demo

- current text
<!-- END shared:demo -->
"""

OTHER = """<!-- BEGIN shared:other -->
## Other

- untouched
<!-- END shared:other -->
"""

failures: list[str] = []


def run(
    mode: str, target: Path, block: Path, *after: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(RENDER),
            mode,
            str(target),
            str(block),
            *(option for name in after for option in ("--after", name)),
        ],
        capture_output=True,
        text=True,
    )


def check(condition: bool, description: str) -> None:
    if condition:
        print(f"  ok   {description}")
    else:
        print(f"  FAIL {description}")
        failures.append(description)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        block = root / "demo.md"
        block.write_text(BLOCK, encoding="utf-8")
        other = root / "other.md"
        other.write_text(OTHER, encoding="utf-8")

        stale = (
            "# Title\n\n"
            "<!-- BEGIN shared:demo v1 -->\n"
            "stale text\n"
            "<!-- END shared:demo -->\n\n"
            f"{OTHER}\n"
            "## Repository section\n\n"
            "- local content\n"
        )

        print("drift detection")
        target = root / "AGENTS.md"
        target.write_text(stale, encoding="utf-8")
        result = run("check", target, block)
        check(result.returncode == 1, "check exits 1 on drift")
        check("current text" in result.stdout, "check prints a diff")
        check(
            target.read_text(encoding="utf-8") == stale,
            "check leaves the file untouched",
        )

        print("apply")
        result = run("apply", target, block)
        text = target.read_text(encoding="utf-8")
        check(result.returncode == 0, "apply exits 0")
        check("stale text" not in text, "apply removes the old body")
        check("- current text" in text, "apply writes the new body")
        # Markers used to carry a version. A repository synced before that
        # was dropped still has one, so apply has to replace the marker
        # itself rather than only the body between the markers.
        check(
            "<!-- BEGIN shared:demo -->" in text and " v1 -->" not in text,
            "apply replaces a marker still carrying a version",
        )
        check(
            text.startswith("# Title\n") and text.endswith("- local content\n"),
            "apply preserves content outside the markers",
        )
        check("- untouched" in text, "apply leaves a sibling block alone")

        print("verification after apply")
        check(run("check", target, block).returncode == 0, "check exits 0")
        check(
            run("check", target, other).returncode == 0,
            "the sibling block is also current",
        )

        print("idempotence")
        before = target.read_text(encoding="utf-8")
        run("apply", target, block)
        check(
            target.read_text(encoding="utf-8") == before,
            "re-applying changes nothing",
        )

        print("malformed input")
        bare = root / "bare.md"
        bare.write_text("no markers here\n", encoding="utf-8")
        check(run("check", bare, block).returncode != 0, "check fails without markers")
        check(run("apply", bare, block).returncode != 0, "apply fails without markers")
        check(
            bare.read_text(encoding="utf-8") == "no markers here\n",
            "a file without markers is not modified",
        )

        reversed_markers = root / "reversed.md"
        reversed_markers.write_text(
            "<!-- END shared:demo -->\nx\n<!-- BEGIN shared:demo v1 -->\n",
            encoding="utf-8",
        )
        check(
            run("apply", reversed_markers, block).returncode != 0,
            "out-of-order markers are rejected",
        )

        headless = root / "headless.md"
        headless.write_text("## Not a marker\n", encoding="utf-8")
        check(
            run("apply", target, headless).returncode != 0,
            "a block file without a BEGIN marker is rejected",
        )

        print("names")
        listed = subprocess.run(
            [sys.executable, str(RENDER), "names", str(target)],
            capture_output=True,
            text=True,
        )
        check(listed.returncode == 0, "names exits 0")
        check(
            listed.stdout.split() == ["demo", "other"],
            "names reports every block, in file order",
        )

        print("remove")
        result = subprocess.run(
            [sys.executable, str(RENDER), "remove", str(target), "other"],
            capture_output=True,
            text=True,
        )
        text = target.read_text(encoding="utf-8")
        check(result.returncode == 0, "remove exits 0")
        check("shared:other" not in text, "the marker pair is gone")
        check("- untouched" not in text, "its content is gone with it")
        check("- current text" in text, "the sibling block survives")
        check(
            text.startswith("# Title\n") and text.endswith("- local content\n"),
            "content outside the markers is preserved",
        )
        check(
            "\n\n\n" not in text,
            "no blank-line scar is left behind",
        )

        result = subprocess.run(
            [sys.executable, str(RENDER), "remove", str(target), "other"],
            capture_output=True,
            text=True,
        )
        check(result.returncode == 0, "removing an absent block is not an error")
        check(
            target.read_text(encoding="utf-8") == text,
            "removing an absent block writes nothing",
        )

        print("a variant file")
        # Named `<block>.<variant>.md` and carrying `shared:<block>`: the
        # region comes from the marker, so a variant rewrites the block's
        # own region rather than looking for one named after the file.
        variant = root / "demo.alt.md"
        variant.write_text(
            "<!-- BEGIN shared:demo -->\n## Demo\n\n- variant text\n"
            "<!-- END shared:demo -->\n",
            encoding="utf-8",
        )
        switched = root / "switched.md"
        switched.write_text(
            f"# Title\n\n{BLOCK}\n{OTHER}\n## Local\n", encoding="utf-8"
        )
        check(run("check", switched, variant).returncode == 1,
              "check reports the default text as drift from the variant")
        check(run("apply", switched, variant).returncode == 0, "apply exits 0")
        check(
            switched.read_text(encoding="utf-8")
            == f"# Title\n\n{BLOCK.replace('current text', 'variant text')}"
            f"\n{OTHER}\n## Local\n",
            "apply rewrites shared:demo in place",
        )
        check(run("check", switched, variant).returncode == 0,
              "and check then passes against the variant")
        run("apply", switched, block)
        check(
            switched.read_text(encoding="utf-8")
            == f"# Title\n\n{BLOCK}\n{OTHER}\n## Local\n",
            "applying the default puts the default back, markers unmoved",
        )

        print("a region the file does not have yet")
        new = root / "new.md"
        new.write_text(
            "<!-- BEGIN shared:new -->\n## New\n\n- new text\n"
            "<!-- END shared:new -->\n",
            encoding="utf-8",
        )
        body = f"# Title\n\n{BLOCK}\n{OTHER}\n## Local\n"
        growing = root / "growing.md"

        growing.write_text(body, encoding="utf-8")
        check(run("check", growing, new).returncode != 0,
              "check fails rather than inserting")
        check(growing.read_text(encoding="utf-8") == body,
              "and writes nothing")

        result = run("apply", growing, new, "demo")
        check(result.returncode == 0, "apply exits 0")
        check(
            growing.read_text(encoding="utf-8")
            == f"# Title\n\n{BLOCK}\n{new.read_text()}\n{OTHER}\n## Local\n",
            "goes right after the END marker of the block named by --after",
        )
        check(run("check", growing, new).returncode == 0,
              "and is current afterwards")

        growing.write_text(body, encoding="utf-8")
        run("apply", growing, new, "absent", "other", "demo")
        check(
            growing.read_text(encoding="utf-8")
            == f"# Title\n\n{BLOCK}\n{OTHER}\n{new.read_text()}\n## Local\n",
            "the first --after the file carries wins, absent ones skipped",
        )

        growing.write_text(body, encoding="utf-8")
        run("apply", growing, new, "absent")
        check(
            growing.read_text(encoding="utf-8")
            == f"# Title\n\n{new.read_text()}\n{BLOCK}\n{OTHER}\n## Local\n",
            "with none of them present, before the first shared region",
        )

        growing.write_text(f"# Title\n\n{BLOCK}", encoding="utf-8")
        run("apply", growing, new, "demo")
        check(
            growing.read_text(encoding="utf-8")
            == f"# Title\n\n{BLOCK}\n{new.read_text()}",
            "at the end of the file, the file still ends in one newline",
        )

        result = run("apply", bare, new, "demo")
        check(result.returncode != 0, "a file with no shared region fails")
        check("add the markers first" in result.stderr,
              "with the message it always gave")
        check(bare.read_text(encoding="utf-8") == "no markers here\n",
              "and is left alone")

        half = root / "half.md"
        half.write_text(
            f"# Title\n\n{BLOCK}\n<!-- BEGIN shared:new -->\n- orphan\n",
            encoding="utf-8",
        )
        check(run("apply", half, new, "demo").returncode != 0,
              "half a marker pair fails instead of gaining a second BEGIN")

        print("a name that another one starts with")
        prefix = root / "commit.md"
        prefix.write_text(
            "<!-- BEGIN shared:commit -->\n- short\n<!-- END shared:commit -->\n",
            encoding="utf-8",
        )
        longer = root / "longer.md"
        longer.write_text(
            "# Title\n\n<!-- BEGIN shared:commit-messages -->\n- long\n"
            "<!-- END shared:commit-messages -->\n",
            encoding="utf-8",
        )
        run("apply", longer, prefix, "commit-messages")
        check(
            "- long" in longer.read_text(encoding="utf-8")
            and "- short" in longer.read_text(encoding="utf-8"),
            "shared:commit is not found inside shared:commit-messages",
        )

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all render.py tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
