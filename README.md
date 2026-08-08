# agent-instructions

Shared instruction blocks for AI coding agents across the `aicers`
repositories. One source of truth, fanned out into each repository's
`AGENTS.md` as marked, generated regions.

## Why this exists

AI agents read instructions from the checked-out working tree, so the
text has to be physically present in every repository. Central hosting
alone does not work: a `CLAUDE.md` that points at a path outside the
repository resolves only on one person's machine, and breaks in CI, in
automation containers, and for every other contributor.

So the copies stay. What this repository removes is the *manual* editing
of those copies — and the silent divergence that follows.

Divergence was already measurable when this repository was created, with
the standards duplicated by hand across ten repositories:

| Section | Repositories | Distinct variants |
| --- | --- | --- |
| Rust coding standards | 7 | 3 |
| Commit messages | 10 | 4 |
| Attribution | 10 | 3 |
| Branching and pushing | 10 | 4 |

Most differences were cosmetic, but not all: one repository carried a
Rust block half the length of the others, and two carried genuinely
better commit-message rules that the rest never received.

## Layout

```text
blocks/         the shared regions, one file per block
repos.json      which repository consumes which blocks
scripts/
  render.py       apply, verify, list, or retire a block in one file
  pin.py          move a consumer's instructions-ref to a release tag
  apply_blocks.py bring one repository up to a release: apply, retire, pin
  sync.sh         fan out apply_blocks.py to every repository at once
  lint_blocks.py  enforce the authoring rules in STYLE.md
  check_release_surface.sh  refuse a release with nothing in it
  test_*.py       tests for the scripts above, run in CI
STYLE.md        how to write a block
CHANGELOG.md    what each release changed; also its release notes
```

The two workflows under `.github/workflows/` that consumers call are
`apply.yml`, which delivers a release, and `check-drift.yml`, which
notices when a repository's copy stops matching the release it is pinned
to.

## The consumer contract

Each consuming repository has:

- `AGENTS.md` — the real file, containing the shared blocks plus its own
  sections. Every agent that reads `AGENTS.md` gets it directly.
- `CLAUDE.md` — the import, `@AGENTS.md`. Claude Code reads `CLAUDE.md`
  and not `AGENTS.md`, and expands this import at session start, so the
  two tools read one text rather than two copies. Anything
  Claude-specific, should a repository ever need it, goes below the
  import.

A symlink also works, and was the original plan here. The import wins on
two counts: it needs no privileges on Windows, where a symlink degrades
into a one-line text file and an agent silently reads a filename instead
of any rules, and it leaves room for that Claude-only section.

Measured on Claude Code 2.1.220, with file tools disabled so the agent
could not simply open the file: a canary in `AGENTS.md` is invisible
with neither mechanism in place, and loads with either. The markers
themselves do not load — Claude Code strips block-level HTML comments
before injecting the text, which is why they are HTML comments. They
cost no context and the agent never sees them.

Inside `AGENTS.md`, the shared regions are delimited by markers and
everything outside them belongs to the repository:

```markdown
# Instructions for AI coding agents

<!-- BEGIN shared:workflow -->
...generated...
<!-- END shared:workflow -->

<!-- BEGIN shared:rust -->
...generated...
<!-- END shared:rust -->

## CI requirements

Repository-specific commands, paths, and gates go here.
```

Blocks are deliberately repository-neutral, so anything naming a path, a
product, or a command lives in the repository's own sections. The Rust
block's certificate-verification rule, for instance, says verification
lives in one dedicated module and leaves the repository to name it.

## Changing a block

1. Edit the file in `blocks/`.
2. Add a `CHANGELOG.md` entry under the version you are about to cut.
   The entry *is* the release notes, and `release.yml` refuses to
   release a tag that has none.
3. Open a pull request here. CI lints the Markdown, tests the scripts
   consumers depend on, and checks the authoring rules.
4. After it merges, tag the release. Consumers pin to release tags, so an
   untagged change reaches nobody:

   ```sh
   git tag 1.1.0 && git push origin 1.1.0
   ```

   `release.yml` turns the tag into a GitHub Release with those notes. It
   first refuses a tag whose `blocks/` tree is byte-identical to the
   previous release's, since that release would give every consumer a
   pull request that moves a pin and changes no rule.
5. Wait. Each consumer applies the release to itself on a schedule and
   opens its own pull request; review and merge those.

## Version scheme

`MAJOR.MINOR.PATCH`, no `v` prefix. The grade is defined by the review a
release demands, not by build compatibility — blocks are prose, and
nothing downstream compiles:

- **MAJOR** — an existing rule is reversed or removed. Consumers have to
  check whether their code already violates the new rule.
- **MINOR** — a rule is added. It applies going forward and does not
  retroactively invalidate existing code.
- **PATCH** — wording or structure only; the rule set is unchanged.

A PATCH can still change how an agent behaves; prompt text is not CSS.
The grade says how hard to look, nothing more.

The monotonic `v1` and `v2` tags predate this scheme and are kept. They
go inert as soon as the last repository pinned to one moves to a semver
pin, but a tag costs nothing, and deleting one retroactively breaks any
branch still pinned to it.

## How a release reaches a repository

Each consuming repository pulls, on its own schedule, with its own
`GITHUB_TOKEN`:

```yaml
name: Update shared instructions
on:
  schedule: [{ cron: "0 6 * * 1" }]
  workflow_dispatch:

jobs:
  update:
    permissions:
      contents: write
      pull-requests: write
    uses: aicers/agent-instructions/.github/workflows/apply.yml@main
    with:
      blocks: "workflow rust changelog"
```

The workflow resolves the latest release, rewrites the marked regions,
drops any block the repository no longer lists, sets the drift check's
`blocks` and `instructions-ref` inputs to match, and opens one pull
request on `shared-instructions/<release>`. A repository already on the
latest release gets none, and a second run against an unchanged
repository neither opens a pull request nor rewrites the branch behind an
open one.

The organization setting *Allow GitHub Actions to create and approve pull
requests* has to be enabled, or the pull-request step fails.

`workflow_dispatch` is in the caller for a reason: GitHub disables a
scheduled workflow in a repository with 60 days of no activity, and does
so quietly, so a dormant repository can stop pulling with nothing to show
for it.

Pulling rather than pushing is the whole point. A workflow here that
pushed into twelve repositories would need a token with write access to
all twelve, which this repository deliberately does not hold; inverted,
each consumer needs only a token for itself. And a consumer can no longer
lag silently — the schedule proposes the release whether or not anyone
remembered.

## The urgent path

`scripts/sync.sh` is the same apply, driven from a maintainer's
workstation against every repository at once. Reach for it when a release
should not wait for the next scheduled run — withdrawing a rule, say — or
to update a repository that has not been onboarded to the scheduled job
yet:

```sh
scripts/sync.sh 1.1.0
```

This clones each consuming repository, runs `scripts/apply_blocks.py`
against it — the same script `apply.yml` runs, which is why the two
cannot disagree — and opens one pull request per repository under
`<github-username>/instructions-1.1.0`. Repositories already current are
skipped, and a tag that is not on `origin` is refused before anything is
touched.

It holds no cross-repository permissions either: it runs with your own
`gh` credentials, and there is no bot account and no organization token.
Pass `--dry-run` first to see the diff each pull request would carry:

```sh
scripts/sync.sh --dry-run 1.1.0
```

Limiting the fan-out to specific repositories is allowed:

```sh
scripts/sync.sh 1.1.0 bootroot roxyd
```

## Retiring a block

Drop it from `repos.json` and delete the file. Either driver then removes
the region from every repository that carried it, because a retired block
is otherwise the one thing nothing looks at: no file renders it, and the
drift check only compares the blocks a repository still lists. A stale copy
of a rule would sit beside its replacement indefinitely.

A consumer's own `blocks` input still names the retired block at that
point, and nothing upstream can edit it. `apply_blocks.py` therefore treats
a listed block the release does not carry as retired rather than as an
error: it drops the region and drops the name from the drift check's
`blocks` input, which is what stops that check looking for a file the
release does not have. The calling workflow's copy of the list is left for
whoever maintains that repository to tidy; a stale name there is inert.

The drift check compares the other direction too, and fails on a marker
the repository no longer lists — so a retirement that never reached a
repository is visible rather than silent.

## Catching drift

Each consuming repository calls the reusable workflow from its own CI:

```yaml
jobs:
  instructions:
    uses: aicers/agent-instructions/.github/workflows/check-drift.yml@main
    with:
      blocks: "workflow rust changelog"
      instructions-ref: 1.0.0
```

It fails when a repository's copy differs from this repository at
`instructions-ref` — whether because someone edited a generated region
locally, or because an update pull request was never merged.

`instructions-ref` is a release tag, and it is required. Comparing
against a branch would make every upstream edit turn ten repositories
red at once, including pull requests that have nothing to do with the
instructions, which is how a check gets ignored. Pinned, an edit here
reaches a repository only through the pull request that moves the pin.

That pin is also the answer to "which release is this repository on",
and the only one. It is deliberately not repeated in a comment, nor in a
version on each BEGIN marker: this input decides what the comparison
runs against, so unlike either of those it cannot be wrong.

The pin covers the blocks, and only the blocks. The workflow checks the
scripts out separately, from wherever it comes from itself, because they
are mechanism rather than content — the same reason `uses:` sits at
`@main`. Pin the scripts to the release and the check's implementation
freezes at whatever shipped with those blocks, so a step added here
would fail on every repository still on an older release, calling a
subcommand that release has never heard of.

Both reusable workflows read this repository with the caller's own
default `GITHUB_TOKEN` — the checkouts in either, and `apply.yml`'s
lookup of the latest release. That token cannot read a private
repository, and neither workflow takes an input to hand it a different
one, so this repository is public. It holds no secrets, which is what
makes that the simpler answer rather than a compromise.

## Onboarding a repository

1. Add it to `repos.json` with the blocks it should consume.
2. Restructure its `AGENTS.md`: convert bullets to `-`, drop section
   numbering, and insert the marker pairs where each block belongs.
3. Write its `CLAUDE.md`:

   ```markdown
   <!-- markdownlint-disable-file MD041 -->
   @AGENTS.md
   ```

   The lint directive is needed because a file whose first line is an
   import has no top-level heading. It costs nothing — block-level HTML
   comments are stripped before the text reaches context — and it does
   not interfere with the import, which was measured rather than
   assumed.
4. Add the drift-check job to its CI, including an `instructions-ref`
   pin. Both drivers refuse a repository that consumes blocks without
   one, rather than leaving it floating. Any existing release tag will do
   as the initial value — the first apply moves it — but it has to be one
   that resolves, since the check itself checks that ref out.
5. Add the calling workflow from [How a release reaches a
   repository](#how-a-release-reaches-a-repository), so the repository
   pulls every release from then on.
6. Run `scripts/sync.sh <tag> <repo>` to fill the regions and set the
   pin now, rather than waiting for the first scheduled run. Running the
   caller's `workflow_dispatch` does the same thing from the other side.
