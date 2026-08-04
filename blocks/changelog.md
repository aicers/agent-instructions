<!-- BEGIN shared:changelog v1 -->
## Changelog

- `CHANGELOG.md` records what changed for a user of the **last release**,
  not how `main` got there. Before writing an entry, ask whether someone
  running the last released version could observe it. Work that builds,
  reworks, or removes something they never had is invisible to them and
  does not belong.
- Entries carry NO issue or PR references. `Closes #N` and `Part of #N`
  are GitHub automation keywords: they close an issue when they appear
  in a commit message or a pull request body, and do nothing whatever
  inside `CHANGELOG.md`. All that is left there is a command addressed
  to a bot, stranded in a record of what already shipped — it cannot
  act, and the reader has no use for it. Git and the issue tracker
  already hold that history.
- Announce a feature once, under `### Added`, describing what it does.
  If it was reworked or renamed before the release shipped, that is not
  a separate `### Changed` entry — no user saw the earlier form.
<!-- END shared:changelog -->
