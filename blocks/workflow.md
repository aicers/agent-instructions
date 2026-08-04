<!-- BEGIN shared:workflow v1 -->
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
- The sole exception is a branch carrying a synced update to the shared
  blocks below, which uses `<github-username>/instructions-<label>` and
  needs no issue.

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

## Attribution

- Do NOT add `Co-Authored-By` lines naming an AI (`Claude`, `Codex`,
  `Gemini`, or any similar name) to commit messages.
- Do NOT add "Generated with Claude Code", "Generated with Codex",
  "Generated with Gemini", or any similar AI attribution to PR
  descriptions or issue comments.
<!-- END shared:workflow -->
