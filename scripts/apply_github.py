#!/usr/bin/env python3
"""The GitHub API calls `.github/workflows/apply.yml` makes.

    apply_github.py latest-release
    apply_github.py default-branch <owner/repo>
    apply_github.py open-pull-request <owner/repo> <head> <base> <title> <body-file>

`latest-release` prints the tag of aicers/agent-instructions' latest
release. `default-branch` prints a repository's default branch.
`open-pull-request` opens one pull request from <head> into <base>,
unless <head> already has one in any state, and says which it did.

These were `gh` calls once. The apply job runs on a self-hosted runner
for a private caller, and those machines carry git, python3, curl and
tar, not `gh`. Python rather than curl here, because the job runs only on
Linux, where Python reads the system's certificates, and because the
token is then sent from this process rather than handed to another one on
its command line: a self-hosted machine is shared, and any process on it
can read another's arguments.

The token is the caller's `GITHUB_TOKEN`, read from the environment and
never from an argument. `GITHUB_API_URL`, which the runner sets, says
where the API is; the tests point it at a local server.

Every failed call fails the job, with the status and what GitHub said.
An apply that could not look for an existing pull request and opened one
anyway would be the duplicate that check exists to prevent; one that
treated a failed lookup as "nothing to do" would go quiet in exactly the
way a stopped schedule does.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "aicers/agent-instructions"

# What a tag or a branch has to look like before it goes anywhere: the
# shape `pin_file.py` holds a pin to, plus `/` for a branch.
TAG = re.compile(r"[\w.-]+")
REPO = re.compile(r"[\w.-]+/[\w.-]+")


class Failure(Exception):
    """A call to the API that did not do what it was asked."""


def request(method: str, path: str, payload: dict | None = None):
    api = (os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "aicers-agent-instructions-apply",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    call = urllib.request.Request(
        api + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(call, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as failure:
        detail = failure.read().decode("utf-8", "replace").strip()
        try:
            detail = json.loads(detail).get("message", detail)
        except (ValueError, AttributeError):
            pass
        raise Failure(f"{method} {path}: HTTP {failure.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as failure:
        raise Failure(f"{method} {path}: {failure}") from None
    try:
        return json.loads(body)
    except ValueError:
        raise Failure(f"{method} {path}: the response is not JSON") from None


def latest_release() -> str:
    # "Latest release", not "latest tag": a tag that was never released
    # has not passed the release-surface guard.
    tag = request("GET", f"/repos/{REPOSITORY}/releases/latest").get("tag_name")
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise Failure(f"the latest release has no usable tag: {tag!r}")
    return tag


def default_branch(repository: str) -> str:
    branch = request("GET", f"/repos/{repository}").get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise Failure(f"{repository} reports no default branch")
    return branch


def open_pull_request(
    repository: str, head: str, base: str, title: str, body: str
) -> str:
    owner = repository.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {"head": f"{owner}:{head}", "state": "all", "per_page": "1"}
    )
    found = request("GET", f"/repos/{repository}/pulls?{query}")
    if not isinstance(found, list):
        raise Failure("the pull-request listing is not a list")
    # Any state, not just open. An open one is already up to date -- the
    # push before this did that. A closed one was somebody declining this
    # release, and reopening it every Monday is not a review comment. A
    # merged one means the work landed.
    if found:
        existing = found[0]
        state = "merged" if existing.get("merged_at") else existing.get("state")
        return f"{head} already has pull request #{existing.get('number')} ({state})"

    created = request(
        "POST",
        f"/repos/{repository}/pulls",
        {"title": title, "head": head, "base": base, "body": body},
    )
    number = created.get("number")
    if not isinstance(number, int):
        raise Failure("GitHub did not say which pull request it opened")
    return f"opened pull request #{number}: {created.get('html_url', '')}"


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["latest-release"] and len(argv) == 1:
            print(latest_release())
        elif argv[:1] == ["default-branch"] and len(argv) == 2:
            if not REPO.fullmatch(argv[1]):
                raise Failure(f"{argv[1]!r} is not owner/repo")
            print(default_branch(argv[1]))
        elif argv[:1] == ["open-pull-request"] and len(argv) == 6:
            repository, head, base, title, body_file = argv[1:]
            if not REPO.fullmatch(repository):
                raise Failure(f"{repository!r} is not owner/repo")
            with open(body_file, encoding="utf-8") as handle:
                body = handle.read()
            print(open_pull_request(repository, head, base, title, body))
        else:
            print(__doc__.split("\n\n")[1], file=sys.stderr)
            return 2
    except Failure as failure:
        # Standard error, which the runner reads workflow commands from too:
        # standard output is the value a step captures with `$(...)`, and
        # an error there would be swallowed into a variable unread.
        print(f"::error::GitHub API call failed: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
