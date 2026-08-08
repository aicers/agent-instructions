# Changelog

This file documents notable changes to the shared instruction blocks and
to the machinery that delivers them. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

Versions are `MAJOR.MINOR.PATCH`, graded by the review a release demands
rather than by build compatibility — blocks are prose, and nothing
downstream compiles:

- **MAJOR** — an existing rule is reversed or removed. Consumers have to
  check whether their code already violates the new rule.
- **MINOR** — a rule is added. It applies going forward and does not
  retroactively invalidate existing code.
- **PATCH** — wording or structure only; the rule set is unchanged.

A PATCH can still change how an agent behaves. Prompt text is not CSS.
The grade says how hard to look, nothing more.

## [1.0.0] - 2026-08-08

First release under `MAJOR.MINOR.PATCH`. The monotonic `v1` and `v2` tags
are kept — a branch pinned to one would otherwise break — but nothing new
is tagged that way.

### Added

- Consumers can apply a release to themselves. `apply.yml` is a reusable
  workflow a repository schedules against itself; it resolves the latest
  release, rewrites its marked blocks, moves its drift-check pin, and
  opens one pull request. A repository already on the latest release gets
  none. This repository holds no cross-repository credentials, and now
  does not need any for a release to arrive; the caller passes a `token`
  secret scoped to itself, which it needs because moving the pin rewrites
  its own workflow file and `GITHUB_TOKEN` may not push one.
- `scripts/apply_blocks.py` holds the per-repository sequence — apply,
  retire, pin — that `sync.sh` used to spell out inline, so the two
  drivers cannot drift apart. `scripts/test_apply_blocks.py` covers it.
- `release.yml` turns a `MAJOR.MINOR.PATCH` tag into a GitHub Release with
  notes from this file, and refuses a tag whose `blocks/` tree matches the
  previous release's.

### Changed

- The `workflow` block's branch-name exception now covers a branch opened
  by CI. It named `<github-username>/instructions-<label>` only, which
  assumed a person had run the sync.
- `sync.sh` is the urgent path rather than the only one: reach for it when
  a release should not wait for the next scheduled run.
