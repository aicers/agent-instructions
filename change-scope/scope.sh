#!/usr/bin/env bash
# Decide whether a CI run's change touches documentation only.
#
# Called by `change-scope/action.yml`, which passes the event context and
# the caller's inputs as the `CS_*` variables below and nothing else. It
# reads nothing but those variables and the git repository in the current
# directory, so a test or a contributor can run it directly:
#
#   CS_EVENT=pull_request CS_BASE_REF=main CS_PR_HEAD=<sha> ... \
#     GITHUB_OUTPUT=/tmp/out bash change-scope/scope.sh
#
# Outputs, appended to "$GITHUB_OUTPUT":
#
#   docs-only     true when at least one path changed, every changed path
#                 is on the documentation list, and none is on the
#                 not-documentation list; false otherwise
#   docs-touched  true when any changed path is on the documentation list
#                 (the not-documentation list is not subtracted), and true
#                 whenever the change could not be classified
#
# Anything this script cannot establish ends in "run everything":
# docs-only=false, docs-touched=true, a ::warning:: naming the reason, and
# exit status 0. A wrong "docs-only" skips the tests on a code change; a
# wrong "run everything" only costs runner time. So every git call is
# checked, and an empty answer from a git call that failed is never read
# as "nothing outside the documentation list".
#
# It does not fetch. The calling job checks out with `fetch-depth: 0`,
# which already brings every branch as `refs/remotes/origin/*` and, on a
# pull request, the head commit as the merge commit's second parent.
#
# bash 3.2 (macOS /bin/bash) and BSD tools: no associative arrays, no
# mapfile, and every array expansion guarded so that an empty one does not
# trip `set -u`.

set -uo pipefail

# Byte semantics for every tool here. Under a UTF-8 locale BSD sed and
# sort stop at a path that is not valid UTF-8, and a list cut short there
# would lose exactly the paths that are not documentation.
export LC_ALL=C

out=${GITHUB_OUTPUT:-/dev/stdout}

full() {
  echo "::warning::Change scope: running everything ($1)"
  {
    echo "docs-only=false"
    echo "docs-touched=true"
  } >> "$out"
  exit 0
}

# Every context value arrives through the environment and is only ever
# expanded inside quotes. A branch name may hold `$`, a backquote, `;` or
# `(`, and none of that may reach a shell as syntax.
event=${CS_EVENT:-}
ref_type=${CS_REF_TYPE:-}
ref_name=${CS_REF_NAME:-}
default_branch=${CS_DEFAULT_BRANCH:-}
base_ref=${CS_BASE_REF:-}
pr_head=${CS_PR_HEAD:-}
before=${CS_BEFORE:-}
sha=${CS_SHA:-}
dispatch_full=${CS_DISPATCH_FULL:-false}

is_sha() {
  # A full object name, SHA-1 or SHA-256, and not the all-zeros name
  # GitHub sends as `before` on a branch's first push.
  case "$1" in
    *[!0-9a-f]*) return 1 ;;
  esac
  [ "${#1}" -eq 40 ] || [ "${#1}" -eq 64 ] || return 1
  case "$1" in
    *[!0]*) return 0 ;;
  esac
  return 1
}

have_commit() {
  git cat-file -e "$1^{commit}" 2>/dev/null
}

# --- the checkout has to carry history ------------------------------------

shallow=$(git rev-parse --is-shallow-repository 2>/dev/null) \
  || full "not a git repository"
[ "$shallow" = false ] || full "shallow checkout; check out with fetch-depth: 0"

# Pathspecs below are relative to the working directory; run from the top
# so that `.` means the whole repository wherever the step was started.
top=$(git rev-parse --show-toplevel 2>/dev/null) || full "no work tree"
cd "$top" || full "cannot enter $top"

# --- which commits to compare ---------------------------------------------
#
# One rule: a branch's change runs from its merge-base with the branch it
# is headed for to its head; the default branch's change runs from
# `before` to `after`.

base=
head=
target=
case "$event" in
  pull_request)
    # The PR head, not the merge commit GitHub builds: comparing the merge
    # commit with a stale `base.sha` would count `main`'s own progress as
    # part of the pull request. Stacked pull requests compare with the
    # branch they target.
    head=$pr_head
    target=$base_ref
    ;;
  push)
    [ "$ref_type" = branch ] || full "push of a $ref_type"
    head=$sha
    if [ "$ref_name" = "$default_branch" ]; then
      base=$before
    else
      target=$default_branch
    fi
    ;;
  workflow_dispatch)
    [ "$ref_type" = branch ] || full "dispatch on a $ref_type"
    [ "$dispatch_full" != true ] || full "dispatch-full is set"
    # Dispatching on the default branch is how a person asks for the
    # whole suite, so it is never narrowed.
    [ "$ref_name" != "$default_branch" ] || full "dispatch on $default_branch"
    head=$sha
    target=$default_branch
    ;;
  *)
    full "event ${event:-<none>}"
    ;;
esac

is_sha "$head" || full "no head commit"
have_commit "$head" || full "head $head is not in the checkout"

if [ -n "$target" ]; then
  # The full ref name, never a bare branch name, so that a branch called
  # `-x` cannot be read by git as an option.
  target_ref="refs/remotes/origin/$target"
  git rev-parse -q --verify "$target_ref" >/dev/null \
    || full "origin/$target is not in the checkout"
  base=$(git merge-base "$target_ref" "$head") \
    || full "no merge-base with origin/$target"
fi

is_sha "$base" || full "no base commit"
have_commit "$base" || full "base $base is not in the checkout"

# --- the path lists -------------------------------------------------------

docs=()
not_docs=()
rejected=

# One pattern per line. Surrounding whitespace and a trailing CR are
# dropped; blank lines and `#` lines are skipped. A line git would read as
# magic, a negation, a parent-relative or absolute path, or a quoted
# YAML-list item copied over from a dorny filter matches nothing, so it is
# refused outright rather than left to silently widen or narrow the list.
read_list() {
  # $1: name of the array to append to; $2: the list text.
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] || continue
    case "$line" in
      '#'*) continue ;;
      ':'* | '/'* | '-'* | '!'* | *..* | *'"'* | *"'"* | *'{'* | *'['* | *'?'*)
        rejected=$line
        continue
        ;;
    esac
    eval "$1+=(\"\$line\")"
  done <<EOF
$2
EOF
}

read_list docs '*.md
LICENSE
.agent-instructions.toml
.markdownlint*' || full "could not read the built-in list"
read_list docs "${CS_DOCS_PATHS:-}" || full "could not read docs-paths"
read_list not_docs "${CS_NOT_DOCS_PATHS:-}" \
  || full "could not read not-docs-paths"
[ "${#docs[@]}" -ge 4 ] || full "the built-in list did not load"
[ -z "$rejected" ] || full "path list holds an unsupported line: $rejected"

# --- the comparison -------------------------------------------------------

diff_names() {
  git -c core.quotePath=false diff --no-ext-diff --no-textconv --no-renames \
    --name-only "$base" "$head" "$@"
}

changed=$(diff_names) || full "git diff failed"
[ -n "$changed" ] || full "the change has no paths"

exclude=()
include=()
for pattern in ${docs[@]+"${docs[@]}"}; do
  exclude+=(":(glob,exclude)$pattern")
  include+=(":(glob)$pattern")
done

not_on_list=$(diff_names -- . ${exclude[@]+"${exclude[@]}"}) \
  || full "git diff failed"

held_back=
if [ "${#not_docs[@]}" -gt 0 ]; then
  not_docs_specs=()
  for pattern in "${not_docs[@]}"; do
    not_docs_specs+=(":(glob)$pattern")
  done
  held_back=$(diff_names -- "${not_docs_specs[@]}") || full "git diff failed"
fi

touched=$(diff_names -- ${include[@]+"${include[@]}"}) \
  || full "git diff failed"

# Decided from git's own output, never from text a later tool rewrote.
if [ -z "$not_on_list" ] && [ -z "$held_back" ]; then
  docs_only=true
else
  docs_only=false
fi
if [ -n "$touched" ]; then
  docs_touched=true
else
  docs_touched=false
fi

echo "Change scope: event=$event base=$base head=$head"
echo "Changed paths:"
printf '%s\n' "$changed" | sed 's/^/  /'
echo "Paths that are not documentation:"
if [ "$docs_only" = false ]; then
  printf '%s\n%s\n' "$not_on_list" "$held_back" | sed '/^$/d' | sort -u \
    | sed 's/^/  /'
else
  echo "  (none)"
fi
echo "docs-only=$docs_only docs-touched=$docs_touched"

{
  echo "docs-only=$docs_only"
  echo "docs-touched=$docs_touched"
} >> "$out"
