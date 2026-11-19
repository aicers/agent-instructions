<!-- BEGIN shared:commit-messages -->
## Commit messages

- Title: preferably under 50 characters, start with an imperative verb
  (e.g., `Add`, `Fix`, `Remove`).
- Do NOT use prefixes such as `feat:`, `chore:`, or `fix:`.
- Do NOT put issue or PR numbers in the title.
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
