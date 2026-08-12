<!-- BEGIN shared:changelog -->
## Changelog

- `CHANGELOG.md` records what changed for a user of the **last release**,
  not how `main` got there. Before writing an entry, ask whether someone
  running the last released version could observe it. Work that builds,
  reworks, or removes something they never had is invisible to them and
  does not belong.
- Entries carry NO issue or PR references. A reader of the release notes
  cannot act on one: the number names something in a tracker they may
  not be able to open, and git and that tracker already hold the history
  it points at. `Closes #N` and `Part of #N` are worse still. They are
  GitHub automation keywords, closing an issue when they appear in a
  commit message or a pull request body and doing nothing whatever
  here, so what is left is a command addressed to a bot, stranded in a
  record of what already shipped.
- Announce a feature once, under `### Added`, describing what it does.
  If it was reworked or renamed before the release shipped, that is not
  a separate `### Changed` entry — no user saw the earlier form.
- A released file carries no `[Unreleased]` section. Cutting a release
  turns that heading into the version being released and its link
  reference into a compare range, and the next change to land opens a
  new one. An empty section left behind is not cosmetic where a release
  job builds the notes by finding the heading that matches the tag: it
  finds nothing, and fails after the tag has already been pushed.
<!-- END shared:changelog -->
