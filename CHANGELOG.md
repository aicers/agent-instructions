# Changelog

This file documents recent notable changes to this project. The format of this
file is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The drift check warns, on every pull request in a consumer, when the
  repository's pin is behind the latest release, naming both and the
  workflow to dispatch. A scheduled apply can stop without anybody
  noticing — GitHub disables one silently in a repository nobody has
  touched for 60 days — and the only symptom until now was the absence
  of pull requests nobody was expecting. It warns rather than fails:
  going red because a release exists upstream would break pull requests
  that have nothing to do with the instructions, which is what pinning
  is for. It says nothing when the repository is current, or when the
  branch `shared-instructions/<latest release>` is already pushed, since
  the apply having run and its pull request sitting unmerged is a
  different situation. `scripts/check_drift.py` holds the comparison and
  `scripts/test_check_drift.py` covers it.

## [0.3.0] - 2026-08-11

### Added

- The `workflow` block says that the marked regions are generated and
  are not edited in the repository that carries them, and that
  `.agent-instructions.toml` is source rather than tool output — never
  ignored, never untracked. Both rules were written only in the pull
  requests that deliver a release, which are read once; the file an
  agent actually loads before touching anything said neither. The pin
  is the one file the drift check cannot do without, and it looks
  generated to anyone who has not read the repository it comes from.

### Changed

- The pin moved from `.agents/instructions.toml` to
  `.agent-instructions.toml` at the repository root. `.agents/` is a
  generic name in a namespace where every tool marks its own —
  `.claude/`, `.cursor/`, `.gemini/` — which left it open to a later
  tool claiming it, and open to being read as tool output and added to
  a `.gitignore`. The name now says whose the file is, and a single
  file has no directory anyone can ignore wholesale.
- Nothing has to be done in a consuming repository. The reader still
  accepts the old path where that is the only one present, and every
  write moves the repository onto the new one and deletes the old, so
  a consumer migrates inside whatever release its apply was already
  delivering. The fallback comes out once no repository is on the old
  path.

### Fixed

- The apply and the fan-out commit what they wrote rather than only
  what git was already tracking. Both staged with `commit -a`, which
  covers modifications to tracked files and not a new path, so
  delivering a release to a repository that had to gain a file — the
  moved pin, or any pin at all in a repository being onboarded — would
  have pushed the rewritten blocks with no pin beside them, and the
  drift check would then have failed on a file it could not read. The
  fan-out also decided "already current" with `diff --quiet`, which is
  blind to the same case and would have skipped exactly the repository
  that needed the run.

## [0.2.1] - 2026-08-10

### Changed

- The `agentcoop` block calls AgentCoop an orchestration system rather
  than a pipeline. Its own manual reserves that word for the nine
  stages one implementation run goes through, and of the three stages
  the block goes on to describe, only implementation has that shape —
  design converges in rounds, and verification audits work already
  merged. The sentence also now says outright that AgentCoop is
  software, which neither wording did, and says it without naming the
  form it runs in.

## [0.2.0] - 2026-08-10

### Added

- A shared `agentcoop` block says what AgentCoop is: the author and the
  reviewer agent and how the two converge, what its implementation,
  design, and verification stages each do, and that the issue is the
  only input a run is given. That vocabulary is already in these
  repositories' issues and pull request comments — and AgentCoop
  injects no instructions of its own, so an agent running inside it
  reads whatever the repository provides and nothing else.
- Every repository takes the block. It reaches one only once that
  repository's `AGENTS.md` carries the `<!-- BEGIN shared:agentcoop -->`
  and `<!-- END shared:agentcoop -->` pair: nothing upstream can decide
  where in that file a block belongs, so until the pair is there the
  apply fails naming the repository and writes nothing.

## [0.1.5] - 2026-08-09

### Added

- `review` joins the roster, taking `workflow`, `rust`, and `changelog`
  — the same list as `review-database`, since it is Rust and already
  keeps a `CHANGELOG.md`. Nothing reaches it until it is onboarded, but
  until `repos.json` names it the apply refuses the repository outright,
  so the roster has to move first.

## [0.1.4] - 2026-08-09

### Added

- The `rust` block says that dropping a `JoinSet` aborts the async
  tasks in it — locals are dropped, the rest of the body is not run,
  and a `spawn_blocking` task already running is not stopped at all —
  and that a graceful shutdown therefore signals its tasks and drains
  the set with `join_next` rather than relying on `Drop`. The
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

- The cryptography rules name the function rather than the crate —
  `constant_time::verify_slices_are_equal` and `rand::SystemRandom`,
  from whichever crypto stack the crate already has. `ring` and
  `aws-lc-rs` spell both alike, so the rules hold on either side of a
  stack migration. The comparison rule reached its example through "in
  a crate that already depends on `ring`", which correctly stopped
  anyone adding `ring` for it and left a crate on any other stack with
  no function named at all; the source-of-randomness rule named `ring`
  with no such condition, so the two did not even agree on their own
  shape.
- The error-type rule leads with the criterion — `thiserror` where a
  caller matches on the kind — and demotes application-versus-library
  to the shorthand it was. The criterion was already in the sentence,
  behind an em dash, which is one clause further than a reader who has
  found a rule that fits tends to go.

### Fixed

- The atomic-write rule creates its temporary file with the finished
  file's permissions. `rename` carries the temporary file's inode, and
  so its mode, to the destination, which means the mode a file ends up
  with is whichever one its temporary happened to be made with — the
  umask under `OpenOptions`, `0o600` under `tempfile`. The two rules,
  adjacent in the block, could quietly undo each other.

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

[Unreleased]: https://github.com/aicers/agent-instructions/compare/0.3.0...main
[0.3.0]: https://github.com/aicers/agent-instructions/compare/0.2.1...0.3.0
[0.2.1]: https://github.com/aicers/agent-instructions/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/aicers/agent-instructions/compare/0.1.5...0.2.0
[0.1.5]: https://github.com/aicers/agent-instructions/compare/0.1.4...0.1.5
[0.1.4]: https://github.com/aicers/agent-instructions/compare/0.1.3...0.1.4
[0.1.3]: https://github.com/aicers/agent-instructions/compare/0.1.2...0.1.3
[0.1.2]: https://github.com/aicers/agent-instructions/compare/0.1.1...0.1.2
[0.1.1]: https://github.com/aicers/agent-instructions/compare/0.1.0...0.1.1
[0.1.0]: https://github.com/aicers/agent-instructions/tree/0.1.0
