#!/usr/bin/env python3
"""Exercise the HEAD-to-release comparison in a throwaway repository."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "check_release_surface.sh"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], check=True, cwd=root, capture_output=True)


def commit(root: Path, changes: dict[str, str]) -> None:
    for name, content in changes.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")


def check(root: Path, description: str, status: int, message: str) -> None:
    result = subprocess.run(
        [str(GUARD)], cwd=root, capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != status or message not in output:
        raise AssertionError(
            f"{description}: expected exit {status} and {message!r}, "
            f"got exit {result.returncode} and {output!r}"
        )
    print(f"  ok   {description}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        git(root, "init", "-q")
        git(root, "config", "user.name", "test")
        git(root, "config", "user.email", "test@example.invalid")
        surface = {
            "blocks/demo.md": "an existing rule\n",
            "repos.json": "{}\n",
            "conventional-title/pattern.txt": "an existing title rule\n",
        }
        commit(root, surface)
        git(root, "tag", "v1")
        check(root, "no plain version tag", 2, "checkout has no release tags")

        git(root, "tag", "1.10.0")
        comparison = (
            "blocks/, repos.json and conventional-title/pattern.txt "
            "are byte-identical at 1.10.0 and HEAD"
        )
        check(root, "HEAD is the last release", 1, comparison)

        commit(root, {name: "outside the surface\n" for name in (
            "README.md",
            "scripts/check.py",
            ".github/workflows/ci.yml",
            "CHANGELOG.md",
            "version.txt",
            "AGENTS.md",
            ".agent-instructions.toml",
            "conventional-title/check.py",
        )})
        check(root, "only paths outside the surface changed", 1, comparison)

        commit(root, {"blocks/demo.md": "other rules\n"})
        for tag in ("1.9.0", "v2", "2.0.0-rc.1"):
            git(root, "tag", tag)
        commit(root, surface)
        check(
            root, "uses the newest plain version by version order",
            1, comparison,
        )

        for path, changed in (
            ("blocks/demo.md", "blocks/"),
            ("repos.json", "repos.json"),
            ("conventional-title/pattern.txt", "conventional-title/pattern.txt"),
        ):
            git(root, "reset", "--hard", "1.10.0")
            commit(root, {path: "updated\n"})
            check(
                root, f"only {changed} changed", 0,
                f"Changed release surface: {changed}\n",
            )

    print("all check_release_surface.sh tests passed")


if __name__ == "__main__":
    main()
