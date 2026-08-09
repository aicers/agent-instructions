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

## [Unreleased]

### Added

- The `rust` block says that dropping a `JoinSet` aborts the tasks in
  it, and that a graceful shutdown therefore signals its tasks and
  drains the set with `join_next` rather than relying on `Drop`. The
  orphan-task rule offered `JoinSet` as the way to keep a handle, which
  is true, and left the reader to discover that the container whose
  whole job is holding tasks kills them when it goes.
- The atomic-write rule separates atomic replacement from durability.
  Temp-file-and-rename settles which of two versions a reader sees and
  says nothing about either surviving a power loss; a file the program
  reads back to resume from needs `sync_all` on the temporary file and
  on the directory. Naming only the first half read as though it
  covered both.

### Changed

- The error-type rule leads with the criterion — `thiserror` where a
  caller matches on the kind — and demotes application-versus-library
  to the shorthand it was. The criterion was already in the sentence,
  behind an em dash, which is one clause further than a reader who has
  found a rule that fits tends to go.

### Fixed

- The atomic-write rule creates its temporary file with the finished
  file's permissions. `rename` carries the temporary file's inode, and
  so its mode, to the destination — so a `0o600` file rewritten by the
  book came back `0o644`, and the two rules, adjacent in the block,
  undid each other on every write.

## [0.1.3] - 2026-08-09

### Added

- The `rust` block says how production code should be shaped so tests
  never need to mutate the process environment: keep `env::var` at a
  thin composition boundary and pass the values to the logic
  underneath. The ban alone left the situation that produces the
  violation in place, which is how one repository ended up with the
  forbidden lock reimplemented six times.

### Changed

- The environment rule names `remove_var` beside `set_var`, offers a
  configuration map or a substitutable resolver as well as a plain
  parameter, and points at `Command::env_remove` and
  `Command::env_clear` for a child process that needs a clean
  environment rather than a set value.

### Fixed

- The release-surface guard names the path that actually differs. It
  reported `blocks/ differs` however the comparison passed, which has
  been wrong for every release since it started comparing `repos.json`
  — both of them.

## [0.1.2] - 2026-08-09

### Changed

- All twelve repositories take the `changelog` block. `bootler`,
  `multifold`, `roxyd`, `aice-web-next`, and `aimer-web` are gaining a
  `CHANGELOG.md`, so the block follows the file as `STYLE.md` asks.
  Nothing reaches those five until they are onboarded; `repos.json` is
  intent, and intent has no effect on a repository that consumes
  nothing yet.

## [0.1.1] - 2026-08-09

### Changed

- `deploy-core` takes the `changelog` block. The repository is
  introducing a `CHANGELOG.md`, and the block follows the file.

### Fixed

- The release-surface guard compares `repos.json` as well as `blocks/`.
  Since the pin moved out of the caller's workflow file, `apply.yml`
  reads `repos.json` out of the release to decide which blocks a
  repository takes — so giving a repository another block is a release
  with nothing in `blocks/`, which the guard refused. It was refusing
  exactly the release that carries such a change, and `0.1.1` is one.

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
  a release should not wait for the next scheduled run. It now applies the
  tag's own `blocks/` and `repos.json`, fetched from `origin`, rather than
  the working checkout it is run from — which is normally ahead of the tag
  and would leave every pull request pinned to one release and filled from
  another. `scripts/test_sync.py` covers it.

[Unreleased]: https://github.com/aicers/agent-instructions/compare/0.1.3...main
[0.1.3]: https://github.com/aicers/agent-instructions/compare/0.1.2...0.1.3
[0.1.2]: https://github.com/aicers/agent-instructions/compare/0.1.1...0.1.2
[0.1.1]: https://github.com/aicers/agent-instructions/compare/0.1.0...0.1.1
[0.1.0]: https://github.com/aicers/agent-instructions/tree/0.1.0
