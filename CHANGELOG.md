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

Those three are about block content. A change to the interface a consumer
calls — an input renamed or dropped, a file this repository expects to
find in a consumer moved — is MAJOR on its own, whatever it does to the
rules.

Below `1.0.0` the grades shift down one: a breaking change bumps MINOR and
everything else bumps PATCH.

## [0.1.0] - 2026-08-08

First release under `MAJOR.MINOR.PATCH`. The monotonic `v1` and `v2` tags
are kept — a branch pinned to one would otherwise break — but nothing new
is tagged that way.

`0.x` rather than `1.0.0`: the blocks contract is proven, the delivery
contract has never run in a consumer once.

### Added

- Consumers can apply a release to themselves. `apply.yml` is a reusable
  workflow a repository schedules against itself; it resolves the latest
  release, rewrites its marked blocks, moves its pin, and opens one pull
  request. A repository already on the latest release gets none. This
  repository holds no cross-repository credentials, and a consumer needs
  none of its own either: the caller passes no inputs and no secrets, and
  runs on its default `GITHUB_TOKEN`.
- `.agents/instructions.toml` in each consumer records the release it
  carries and the blocks it has. It replaces the `instructions-ref` and
  `blocks` inputs on the drift check, which lived in the caller's own
  workflow file — the one place a consumer's automation may not write,
  and the only reason a token was ever needed. Which blocks a repository
  should carry is resolved from `repos.json` in the release, so a release
  can now add a block to a repository as well as change one.
- `scripts/apply_blocks.py` holds the per-repository sequence — apply,
  retire, pin — that `sync.sh` used to spell out inline, so the two
  drivers cannot drift apart. `scripts/test_apply_blocks.py` covers it.
- `scripts/pin_file.py` reads and writes that pin file. It replaces
  `scripts/pin.py`, which rewrote YAML by regular expression, finding the
  pair of keys by indentation and proximity.
- `release.yml` turns a `MAJOR.MINOR.PATCH` tag into a GitHub Release with
  notes from this file, and refuses a tag whose `blocks/` tree matches the
  previous release's.

### Changed

- The `workflow` block's branch-name exception now covers a branch opened
  by CI. It named `<github-username>/instructions-<label>` only, which
  assumed a person had run the sync.
- `sync.sh` is the urgent path rather than the only one: reach for it when
  a release should not wait for the next scheduled run.
