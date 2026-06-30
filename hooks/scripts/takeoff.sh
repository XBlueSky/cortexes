#!/bin/bash
set -euo pipefail

# cortex takeoff helper — repo-scoped baton path resolution + git safety.
#
# Subcommands:
#   path <cwd>     print the baton path for the repo at <cwd> (no side effects)
#   prepare <cwd>  ensure .takeoff/ is git-ignored in the vault, verify with
#                  check-ignore, mkdir the dir, then print the baton path
#   clear <cwd>    remove the baton for the repo at <cwd>
#
# Vault: $CORTEX_VAULT_PATH else ~/.cortex/config.json .vault_path (same as the
# SessionStart inject hook). Slug: lib/repo-slug.sh (shared with that hook so
# the create-side path and the detect-side path are always identical).

here="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib/repo-slug.sh
source "$here/lib/repo-slug.sh"

resolve_vault() {
  if [[ -n "${CORTEX_VAULT_PATH:-}" ]]; then
    printf '%s' "$CORTEX_VAULT_PATH"
  elif [[ -f "$HOME/.cortex/config.json" ]]; then
    jq -r '.vault_path // ""' "$HOME/.cortex/config.json" 2>/dev/null || true
  fi
}

cmd="${1:-}"
cwd="${2:-$PWD}"

vault="$(resolve_vault)"
if [[ -z "$vault" || ! -d "$vault" ]]; then
  echo "cortex: vault not configured (run /cortex:genesis)" >&2
  exit 2
fi

slug="$(cortex_repo_slug "$cwd" || true)"
if [[ -z "$slug" ]]; then
  echo "cortex: no git repo / origin remote at $cwd — takeoff is repo-scoped" >&2
  exit 2
fi

baton="$vault/.takeoff/$slug.md"

case "$cmd" in
  path)
    printf '%s\n' "$baton"
    ;;
  prepare)
    gitignore="$vault/.gitignore"
    if ! grep -qxF '.takeoff/' "$gitignore" 2>/dev/null; then
      printf '.takeoff/\n' >>"$gitignore"
      # Commit the ignore rule (path-scoped) so the vault never carries a
      # perpetually-dirty .gitignore and the rule propagates to other clones.
      # A non-git vault skips this and fails closed at check-ignore below.
      if git -C "$vault" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "$vault" add .gitignore
        git -C "$vault" commit -q -m "cortex: gitignore .takeoff/ (takeoff batons)" -- .gitignore
      fi
    fi
    if ! git -C "$vault" check-ignore -q ".takeoff/$slug.md"; then
      echo "cortex: refusing to write — $baton is not git-ignored" >&2
      echo "add '.takeoff/' to $gitignore (vault must be a git repo)" >&2
      exit 3
    fi
    mkdir -p "$vault/.takeoff"
    printf '%s\n' "$baton"
    ;;
  clear)
    rm -f "$baton"
    printf 'cleared %s\n' "$baton"
    ;;
  *)
    echo "usage: takeoff.sh {path|prepare|clear} [cwd]" >&2
    exit 64
    ;;
esac
