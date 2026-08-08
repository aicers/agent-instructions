<!-- BEGIN shared:workflow -->
## Language

- Code, comments, commit messages, PR descriptions, and issues are written
  in English.

## Commit messages

- Title: preferably under 50 characters, start with an imperative verb
  (e.g., `Add`, `Fix`, `Remove`).
- Do NOT use prefixes such as `feat:`, `chore:`, or `fix:`.
- Do NOT put issue or PR numbers in the title.
- Body: wrap at 72 characters, free-form, explain *why* not *what*.
- Separate title and body with a blank line.
- Reference issues in the body, not the title: `Closes #N` to close an
  issue, or `Part of #N` when the commit addresses part of one.

## Branching and pushing

- NEVER push directly to `main`. Always create a new branch before
  pushing.
- Branch names must follow the format `<github-username>/issue-#` (e.g.,
  `alice/issue-42`). If there is no related issue, ask the user how to
  proceed before creating the branch.
- The sole exception is a branch carrying an update to the shared blocks
  below, which needs no issue. CI opens it as
  `shared-instructions/<release>`; a maintainer running the fan-out by
  hand opens it as `<github-username>/instructions-<release>`.

## GitHub issues and PRs

- Do NOT hard-wrap lines in issue or PR body text. GitHub renders
  Markdown, so manual line breaks hurt readability. (This applies to the
  body text only — commit messages still wrap at 72.)
- Issues and PRs share ONE number namespace, so `gh issue edit N` and
  `gh issue view N` can silently operate on PR #N when N is a PR. Before
  ANY `gh` write (edit, close, comment), confirm the target's type and
  identity with a read first: `gh issue view N --json
  number,title,state,url`, and check `/pull/` vs `/issues/` in the URL.
- Never act on failed or garbled command output. Re-verify every create
  and edit with a structured `--json` re-query before reporting success.

## Markdown lint configuration

- The repository-root `.markdownlint-cli2.yaml` carries `globs`,
  `ignores`, and `MD024: siblings_only`. No other rule configuration
  belongs there, and no rule is disabled there.
- Configure or disable any other rule at the narrowest scope that
  works, choosing in this order: the line, then the file, then the
  directory. Use `markdownlint-disable-next-line` for one line,
  `markdownlint-disable-file` for one file, and a
  `.markdownlint-cli2.yaml` beside the files for one directory.
- A directory config named `.markdownlint-cli2.yaml` merges with the
  root config; one named `.markdownlint.yaml` replaces it wholesale.
  Use the former.
- Scope narrowly because a global entry outlives its reason. It
  silences the file that needed it and every file added afterwards
  that should have tripped the rule, and nothing in the config records
  which was which.

## Attribution

- Do NOT add `Co-Authored-By` lines naming an AI (`Claude`, `Codex`,
  `Gemini`, or any similar name) to commit messages.
- Do NOT add "Generated with Claude Code", "Generated with Codex",
  "Generated with Gemini", or any similar AI attribution to PR
  descriptions or issue comments.
<!-- END shared:workflow -->
