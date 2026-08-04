# Authoring rules for blocks

These constraints are enforced by `scripts/lint_blocks.py`. They exist so
a block can be dropped into any repository unchanged.

## Repository-neutral

A block must not name a repository, a file path, a product, or a person.
Anything specific belongs in the consuming repository's own sections,
below the blocks. When a rule needs a local anchor, phrase it so the repo
supplies the detail — for example, "lives in one dedicated module per
crate, named in the repository-specific section below."

This is not a style preference. The drift check is a byte comparison; the
moment a block needs per-repository substitution, it needs a template
engine, and the check stops being trivially correct.

## Markers

The first and last lines are the markers, and the name must match the
filename:

```text
<!-- BEGIN shared:rust v1 -->
...
<!-- END shared:rust -->
```

The version lives on the BEGIN marker only, so a consuming repository can
be inspected at a glance to see which revision it carries. Versions are
per block: bumping `rust` does not disturb repositories that only consume
`workflow`.

## Formatting

- Wrap at **76 columns**. Consumers' markdownlint configurations vary; the
  strictest applies MD013's default of 80 to prose *and* fenced code, so
  76 leaves room and never triggers it.
- Use `-` for bullets, never `*`. MD004 defaults to `consistent`, which
  compares against the rest of the consuming file — so every consumer's
  `AGENTS.md` uses `-` throughout, and blocks must match.
- Use unnumbered `##` and `###` headings. Section numbers break as soon as
  a repository adds or drops a block.
- Keep headings unique within a block, and distinct from the headings in
  other blocks. Consumers set MD024 `siblings_only`, but overlapping
  headings across blocks confuse readers regardless.
- Wrap any `@` in backticks. A consumer's `CLAUDE.md` imports
  `AGENTS.md`, and Claude Code parses imported files for further
  `@path` imports, skipping only code spans and fenced blocks. A bare
  `@ts-ignore` in a block would send it looking for a file named
  `ts-ignore`.

## Versioning

Bump the version on the BEGIN marker whenever the block's content
changes, even for a typo. The version is how a stale consumer is
identified in a diff; a silent edit defeats it.
