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
  sync.sh         fan out blocks and pins as pull requests
  lint_blocks.py  enforce the authoring rules in STYLE.md
  test_*.py       tests for the two scripts consumers depend on
STYLE.md        how to write a block
```

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
2. Open a pull request here. CI lints the Markdown, tests the two
   scripts consumers depend on, and checks the authoring rules.
3. After it merges, tag the release. Consumers pin to tags, so an
   untagged change reaches nobody:

   ```sh
   git tag v2 && git push origin v2
   ```

4. Fan it out:

   ```sh
   scripts/sync.sh v2
   ```

   This clones each consuming repository, rewrites the marked regions,
   drops any block the repository no longer takes, sets the drift
   check's `blocks` and `instructions-ref` inputs to match, and opens
   one pull request per repository under
   `<github-username>/instructions-v2`.
   Repositories already current are skipped, and a tag that is not on
   `origin` is refused before anything is touched.

   Nothing here holds cross-repository permissions. The script runs on
   your workstation with your own `gh` credentials — there is no bot
   account and no organization token. Pass `--dry-run` first to see the
   diff each pull request would carry:

   ```sh
   scripts/sync.sh --dry-run v2
   ```

5. Review and merge the generated pull requests.

Limiting the fan-out to specific repositories is allowed:

```sh
scripts/sync.sh v2 bootroot roxyd
```

## Retiring a block

Drop it from `repos.json` and delete the file. `sync.sh` then removes the
region from every repository that carried it, because a retired block is
otherwise the one thing nothing looks at: no file renders it, and the
drift check only compares the blocks a repository still lists. A stale
copy of a rule would sit beside its replacement indefinitely.

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
      instructions-ref: v2
```

It fails when a repository's copy differs from this repository at
`instructions-ref` — whether because someone edited a generated region
locally, or because a sync pull request was never merged.

`instructions-ref` is a release tag, and it is required. Comparing
against a branch would make every upstream edit turn ten repositories
red at once, including pull requests that have nothing to do with the
instructions, which is how a check gets ignored. Pinned, an edit here
reaches a repository only through its sync pull request.

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

If this repository is private, the caller's default `GITHUB_TOKEN` cannot
read it; the checkout steps then need a token with access. Making this
repository public is the simpler option, since it holds no secrets.

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
   pin. `sync.sh` refuses a repository that consumes blocks without
   one, rather than leaving it floating.
5. Run `scripts/sync.sh <tag> <repo>` to fill the regions and set the
   pin.
