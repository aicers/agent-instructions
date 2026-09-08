#!/usr/bin/env python3
"""Tests for fetch_blocks.sh.

What is tested here is where it refuses to put things, which is the
constraint that made the script exist at all. `curl` is stubbed, so these
run offline; the real download is exercised by the `action` job in
`ci.yml`, which runs the whole action against a fixture.

The blocks are Markdown, and the action unpacks them while a job the
consumer owns is running. Anywhere inside that job's workspace is wrong:
its own `markdownlint-cli2 "**/*.md"`, or any other tree walk, would pick
up this repository's release, and a runner whose workspace persists would
still be holding it during the next job. The guard has to hold for a path
that reaches the workspace through a symlink too, since a runner
workspace is commonly reached by one, and it has to refuse without having
created anything on the way.

Run it directly; it needs nothing beyond the standard library.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "fetch_blocks.sh"

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {description}")
    if not condition:
        failures.append(description)


def run(
    *args: str,
    workspace: Path | None,
    curl: str | None = None,
    path: Path | None = None,
) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.pop("GITHUB_WORKSPACE", None)
    if workspace is not None:
        environment["GITHUB_WORKSPACE"] = str(workspace)
    if curl is not None:
        assert path is not None
        stub = path / "curl"
        stub.write_text(f"#!/usr/bin/env bash\n{curl}\n", encoding="utf-8")
        stub.chmod(0o755)
        environment["PATH"] = f"{path}:{environment['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=environment,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        (workspace / "nested").mkdir(parents=True)
        elsewhere = root / "temp"
        elsewhere.mkdir()

        print("no arguments")
        result = run(workspace=workspace)
        check(result.returncode == 2, "refuses")
        check("usage:" in result.stderr, "says what it wanted")

        print("a destination directly in the workspace")
        target = workspace / "agent-instructions-blocks"
        result = run("0.3.1", str(target), workspace=workspace)
        check(result.returncode == 2, "refuses")
        check("refusing to unpack" in result.stderr, "says why")
        check(not target.exists(), "and creates nothing there")

        print("a destination further down inside the workspace")
        target = workspace / "nested" / "blocks"
        result = run("0.3.1", str(target), workspace=workspace)
        check(result.returncode == 2, "refuses")
        check(not target.exists(), "and creates nothing there")

        print("the workspace itself")
        result = run("0.3.1", str(workspace), workspace=workspace)
        check(result.returncode == 2, "refuses")

        print("a destination reaching the workspace through a symlink")
        link = root / "link"
        link.symlink_to(workspace / "nested")
        target = link / "blocks"
        result = run("0.3.1", str(target), workspace=workspace)
        check(result.returncode == 2, "refuses, so `pwd -P` is doing its job")
        check(not (workspace / "nested" / "blocks").exists(), "creates nothing")

        print("a destination whose parent does not exist")
        result = run("0.3.1", str(elsewhere / "gone" / "blocks"),
                     workspace=workspace)
        check(result.returncode == 2, "refuses rather than making the path")
        check("no such directory" in result.stderr, "names it")

        # Everything above stops before the download. The rest replaces
        # `curl` with one that hands over a tarball shaped like the one
        # the API returns -- a single top-level directory named after the
        # commit, which is what `--strip-components=1` is for.
        tarball = root / "release.tar.gz"
        with tarfile.open(tarball, "w:gz") as archive:
            payload = root / "demo.md"
            payload.write_text("<!-- BEGIN shared:demo -->\n", encoding="utf-8")
            archive.add(payload, arcname="aicers-agent-instructions-9f1c2a4/"
                                        "blocks/demo.md")

        bin_dir = root / "bin"
        bin_dir.mkdir()

        print("a destination outside the workspace")
        target = elsewhere / "blocks"
        target.mkdir()
        # A leftover from an earlier run in the same job, which must not
        # be compared against as if it came from the pin.
        (target / "stale").write_text("old\n", encoding="utf-8")
        result = run("0.3.1", str(target), workspace=workspace,
                     curl=f"cat {str(tarball)!r}", path=bin_dir)
        check(result.returncode == 0, "is allowed")
        check(
            (target / "blocks" / "demo.md").is_file(),
            "unpacks the release with its top-level directory stripped",
        )
        check(not (target / "stale").exists(), "having emptied it first")

        print("a ref that does not resolve")
        result = run("0.3.1", str(elsewhere / "missing"), workspace=workspace,
                     curl='exit 22', path=bin_dir)
        check(result.returncode == 1, "fails")
        check("could not fetch" in result.stderr, "names the repository and ref")

    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all fetch_blocks.sh tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
