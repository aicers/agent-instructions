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
  render.py       apply or verify one block in one file
  test_render.py  tests for render.py, which every consumer's CI runs
  sync.sh         fan out every block as pull requests
  lint_blocks.py  enforce the authoring rules in STYLE.md
STYLE.md        how to write a block
```

## The consumer contract

Each consuming repository has:

- `AGENTS.md` — the real file, containing the shared blocks plus its own
  sections.
- `CLAUDE.md` — a symbolic link to `AGENTS.md`. The two files were
  byte-identical apart from a title line, so the link removes half the
  surface that can drift. (Skip the link if the repository is checked out
  on Windows or with `core.symlinks=false`, where it degrades into a
  one-line text file.)

Inside `AGENTS.md`, the shared regions are delimited by markers and
everything outside them belongs to the repository:

```markdown
# Instructions for AI coding agents

<!-- BEGIN shared:workflow v1 -->
...generated...
<!-- END shared:workflow -->

<!-- BEGIN shared:rust v1 -->
...generated...
<!-- END shared:rust -->

## CI requirements

Repository-specific commands, paths, and gates go here.
```

Blocks are deliberately repository-neutral, so anything naming a path, a
product, or a command lives in the repository's own sections. `rust-tls`,
for instance, says the TLS verifiers live in one dedicated module and
leaves the repository to name it.

## Changing a block

1. Edit the file in `blocks/` and bump the version on its BEGIN marker.
2. Open a pull request here. CI lints the Markdown and checks the
   authoring rules.
3. After it merges, fan it out:

   ```sh
   scripts/sync.sh rust-v2
   ```

   This clones each consuming repository, rewrites the marked regions,
   and opens a pull request per repository under
   `<github-username>/instructions-rust-v2`. Repositories already current
   are skipped.

   Nothing here holds cross-repository permissions. The script runs on
   your workstation with your own `gh` credentials — there is no bot
   account and no organization token. Pass `--dry-run` first to see the
   diff each pull request would carry:

   ```sh
   scripts/sync.sh --dry-run rust-v2
   ```

4. Review and merge the generated pull requests.

Limiting the fan-out to specific repositories is allowed:

```sh
scripts/sync.sh rust-v2 bootroot roxyd
```

## Catching drift

Each consuming repository calls the reusable workflow from its own CI:

```yaml
jobs:
  instructions:
    uses: aicers/agent-instructions/.github/workflows/check-drift.yml@main
    with:
      blocks: "workflow rust rust-tls rust-crypto changelog"
```

It fails when a repository's copy differs from this one — whether because
someone edited a generated region locally, or because a sync pull request
was never merged.

If this repository is private, the caller's default `GITHUB_TOKEN` cannot
read it; the checkout step then needs a token with access. Making this
repository public is the simpler option, since it holds no secrets.

## Onboarding a repository

1. Add it to `repos.json` with the blocks it should consume.
2. Restructure its `AGENTS.md`: convert bullets to `-`, drop section
   numbering, and insert the marker pairs where each block belongs.
3. Replace its `CLAUDE.md` with a symbolic link to `AGENTS.md`.
4. Add the drift-check job to its CI.
5. Run `scripts/sync.sh <label> <repo>` to fill the regions.
