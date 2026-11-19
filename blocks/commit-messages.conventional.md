<!-- BEGIN shared:commit-messages -->
## Commit messages

- Pull requests are squash-merged, and a pull request's title becomes
  the title of its squash commit. So the title follows Conventional
  Commits 1.0.0: `<type>[(<scope>)][!]: <description>`.
- `<type>` is one of `feat`, `fix`, `docs`, `style`, `refactor`,
  `perf`, `test`, `build`, `ci`, `chore`, or `revert`. A dependency
  update is `chore(deps)`.
- A breaking change puts `!` before the colon, as in
  `feat(api)!: drop the v1 endpoints`. A `BREAKING CHANGE:` footer
  alone is not enough: merge checks and reviewers read only the title.
  A breaking change that alters only a wire or stored format takes `!`
  too, even though no API compatibility check detects it.
- The description is English and imperative, starts with a lowercase
  letter, and has no trailing period and no issue or PR number. The
  merge appends the pull request's number to it, as `(#N)`.
- Write the description as a line a user of the release would read:
  what changed for them, not how the code got there.
- The pull request body carries `Closes #N`, or `Part of #N` when the
  pull request delivers part of the issue, and becomes the body of the
  squash commit.
- Body: wrap at 72 characters, free-form, explain *why* not *what*.
- Separate title and body with a blank line.
- Do NOT rely on literal `\n` escapes for a commit body — they land in
  the subject line as characters, and git reports success. Use a real
  multiline string, or `git commit -F` with a file or heredoc.
- Reference issues in the body, not the title, and only the issue the
  commit delivers: `Closes #N` to close it, or `Part of #N` when the
  commit addresses part of it. Every new version of the commit you
  push, after an amend or a rebase, posts another entry on the timeline
  of each issue it names.
<!-- END shared:commit-messages -->
