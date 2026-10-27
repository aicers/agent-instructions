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
- Do NOT rely on literal `\n` escapes for a commit body — they land in
  the subject line as characters, and git reports success. Use a real
  multiline string, or `git commit -F` with a file or heredoc.
- Reference issues in the body, not the title, and only the issue the
  commit delivers: `Closes #N` to close it, or `Part of #N` when the
  commit addresses part of it. Every new version of the commit you
  push, after an amend or a rebase, posts another entry on the timeline
  of each issue it names.

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
- A body that was overwritten is recoverable: GitHub keeps every prior
  version, and `gh api graphql` reads them out of
  `userContentEdits(first: N) { nodes { editedAt editor { login } diff } }`
  on the issue or pull request. Restore the one you want with
  `--body-file`. Do NOT retype it from memory — a body that reads like
  the original and is not is worse than the empty one it replaced.

## Referring to other issues and PRs

- Any reference GitHub recognizes as an issue or PR posts an entry on
  that issue's or PR's timeline: a bare `#N`, `GH-N`, `owner/repo#N`,
  its URL (a link to one of its comments or a URL with a query
  included), and a Markdown or HTML link to that URL alike. Editing the
  text or deleting the comment afterwards does not remove the entry, so
  choose the form before you post.
- Ask one question of every reference: once the other side sees it,
  does it give them something to do or something to avoid?
  - **Yes: link it.** Use `#N` within the repository and `owner/repo#N`
    across repositories. This covers closes, part of, depends on or
    blocks, follow-up of, parent or child, and supersedes or
    duplicates, on a pull request only as the bullet below allows.
  - **No: use a form that posts no entry.** A PR as its
    `https://github.com/owner/repo/pull/N/files` URL; a commit as its
    SHA and title; a range of commits as one
    `https://github.com/owner/repo/compare/A...B` URL; an issue as its
    full URL in a code span,
    `` `https://github.com/owner/repo/issues/N` ``. Never a bare
    `` `#N` `` in a code span: it names no repository. Describe what
    must be left alone by what it is ("every other open PR based on
    `main`"), not by listing numbers. If you find yourself returning to
    the target as you work, your work relies on it, and the answer is
    yes.
- Quoting text with `>` posts entries again for every reference in it,
  and a `<details>` block does not stop them. Put pasted logs and
  command output in a fenced code block, where references post none.
- Anywhere on a pull request (its body, a comment, a review, an inline
  review comment), link an issue of the same repository only if the
  pull request delivers it, and then as `Closes #N` or `Part of #N` in
  the body, never in a code span. AgentCoop's verification takes every
  merged pull request that mentions an issue anywhere as a candidate,
  and an agent judges from its title and body whether it delivered that
  issue; a `Part of #N` link is the only trace a partial delivery
  leaves. State any other relationship in the issue.
- Leave the references AgentCoop writes as they are: its children
  roster, its dependency lines and its issue-sync list. It reads some
  of them back, and its verification walks the entries they post.

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

## Shared instruction blocks

- The regions between `<!-- BEGIN shared:... -->` and
  `<!-- END shared:... -->` in this file are generated from a shared
  source. Do NOT edit them here. Change the wording upstream and cut a
  release there; it arrives as a pull request against this repository.
  An edit made here is overwritten by the next one of those, and turns
  the drift check red until it lands.
- `.agent-instructions.toml` records which release those regions came
  from and which blocks this repository carries. It is source, not tool
  output: the drift check reads it, the apply rewrites it, and nothing
  generates it from anything else. Never add it to `.gitignore`, and
  never untrack it — a repository whose pin cannot be read fails the
  check outright rather than being read as carrying no blocks.

## Attribution

- Do NOT add `Co-Authored-By` lines naming an AI (`Claude`, `Codex`,
  `Gemini`, or any similar name) to commit messages.
- Do NOT add "Generated with Claude Code", "Generated with Codex",
  "Generated with Gemini", or any similar AI attribution to PR
  descriptions or issue comments.
<!-- END shared:workflow -->
