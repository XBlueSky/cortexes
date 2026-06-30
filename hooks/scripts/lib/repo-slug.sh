#!/bin/bash
# Shared repo-slug derivation for cortex hooks/scripts.
#
# The slug keys repo-scoped artifacts: takeoff batons (.takeoff/<slug>.md) and
# the SessionStart menu's pending-baton detection. The create-side helper and
# the detect-side hook MUST agree on this derivation, so it lives here and is
# sourced by both — never duplicated.

# cortex_repo_slug <dir>
#   Prints the repo slug for <dir>: basename of the origin remote URL with a
#   trailing ".git" stripped. Prints nothing and returns 1 when <dir> is not a
#   git repo or has no origin remote.
cortex_repo_slug() {
  local dir="$1" url
  git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || return 1
  url=$(git -C "$dir" remote get-url origin 2>/dev/null) || return 1
  [[ -z "$url" ]] && return 1
  printf '%s' "$url" | sed 's|.*/||;s|\.git$||'
}
