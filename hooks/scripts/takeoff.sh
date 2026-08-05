#!/bin/bash
set -euo pipefail

# cortex takeoff helper — repo-scoped, topic-keyed baton management + git safety.
#
# Subcommands (cwd is REQUIRED everywhere — no $PWD fallback; a stale shell
# cwd once deleted the wrong repo's baton, see the 2026-08-05 multi-baton
# design):
#   list    <cwd>           one baton per line: topic<TAB>summary<TAB>path,
#                           mtime-newest first, legacy <slug>.md included
#   path    <cwd> <topic>   print the baton path (no side effects)
#   prepare <cwd> <topic>   git-safety preflight; prints two lines: baton
#                           path, then workdir (repo toplevel realpath)
#   clear   <cwd> <topic>|--legacy [--force]
#                           soft-delete into .takeoff/.trash/ (exit 4 =
#                           workdir mismatch, 5 = no baton)
#
# Vault: $CORTEX_VAULT_PATH else ~/.cortex/config.json .vault_path (same as the
# SessionStart inject hook). Slug: lib/repo-slug.sh (shared with that hook so
# the create-side path and the detect-side path are always identical).

here="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib/repo-slug.sh
source "$here/lib/repo-slug.sh"

usage() {
  echo "usage: takeoff.sh {list|path|prepare|clear} <cwd> [<topic>|--legacy] [--force]" >&2
  exit 64
}

# Topic keys become filenames and CLI arguments: enforce kebab-case, cap the
# length, and reserve words that collide with the command grammar (resume/
# done) or the legacy display label (legacy).
validate_topic() {
  local t="$1"
  [[ "$t" =~ ^[a-z0-9][a-z0-9-]*$ ]] || return 1
  (( ${#t} <= 64 )) || return 1
  case "$t" in resume|done|legacy) return 1 ;; esac
  return 0
}

resolve_vault() {
  if [[ -n "${CORTEX_VAULT_PATH:-}" ]]; then
    printf '%s' "$CORTEX_VAULT_PATH"
  elif [[ -f "$HOME/.cortex/config.json" ]]; then
    jq -r '.vault_path // ""' "$HOME/.cortex/config.json" 2>/dev/null || true
  fi
}

repo_workdir() {
  realpath "$(git -C "$cwd" rev-parse --show-toplevel)"
}

# Soft-deleted batons are kept 30 days, pruned opportunistically by the
# subcommands that already write (prepare/clear) — no cron needed.
prune_trash() {
  local trash="$vault/.takeoff/.trash"
  [[ -d "$trash" ]] || return 0
  find "$trash" -type f -mtime +30 -delete 2>/dev/null || true
  find "$trash" -mindepth 1 -type d -empty -delete 2>/dev/null || true
}

cmd="${1:-}"
cwd="${2:-}"

case "$cmd" in list|path|prepare|clear) ;; *) usage ;; esac
[[ -n "$cwd" ]] || usage

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

case "$cmd" in
  list)
    shopt -s nullglob
    entries=("$vault/.takeoff/$slug"/*.md)
    [[ -f "$vault/.takeoff/$slug.md" ]] && entries+=("$vault/.takeoff/$slug.md")
    if ((${#entries[@]})); then
      while IFS= read -r f; do
        if [[ "$f" == "$vault/.takeoff/$slug.md" ]]; then
          topic="legacy"
        else
          topic="$(basename "$f" .md)"
        fi
        summary="$(sed -n 's/^summary:[[:space:]]*//p' "$f" | head -1)"
        [[ -z "$summary" ]] && summary="(無摘要)"
        printf '%s\t%s\t%s\n' "$topic" "$summary" "$f"
      done < <(ls -t -- "${entries[@]}")
    fi
    ;;
  path)
    topic="${3:-}"
    validate_topic "$topic" || usage
    printf '%s\n' "$vault/.takeoff/$slug/$topic.md"
    ;;
  prepare)
    topic="${3:-}"
    validate_topic "$topic" || usage
    baton="$vault/.takeoff/$slug/$topic.md"
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
    if ! git -C "$vault" check-ignore -q ".takeoff/$slug/$topic.md"; then
      echo "cortex: refusing to write — $baton is not git-ignored" >&2
      echo "add '.takeoff/' to $gitignore (vault must be a git repo)" >&2
      exit 3
    fi
    mkdir -p "$vault/.takeoff/$slug"
    prune_trash
    printf '%s\n' "$baton"
    repo_workdir
    ;;
  clear)
    target="${3:-}"
    force="${4:-}"
    [[ -n "$target" ]] || usage
    [[ -z "$force" || "$force" == "--force" ]] || usage
    if [[ "$target" == "--legacy" ]]; then
      baton="$vault/.takeoff/$slug.md"
      trash_name="legacy"
    else
      validate_topic "$target" || usage
      baton="$vault/.takeoff/$slug/$target.md"
      trash_name="$target"
    fi
    if [[ ! -f "$baton" ]]; then
      echo "cortex: no baton at $baton — nothing to clear" >&2
      exit 5
    fi
    # Ownership check: a baton records the physical repo it belongs to; a
    # matching slug from a DIFFERENT clone (vault repo vs tool repo share
    # the slug "cortex") must not clear it. printf-style warnings are
    # useless to an agent — refusal before the mv is the only real guard.
    if [[ "$force" != "--force" ]]; then
      wd="$(sed -n 's/^workdir:[[:space:]]*//p' "$baton" | head -1)"
      if [[ -z "$wd" ]]; then
        echo "cortex: warning — $baton has no workdir field, skipping ownership check" >&2
      elif [[ "$wd" != "$(repo_workdir)" ]]; then
        echo "cortex: refusing to clear — baton belongs to $wd, current repo is $(repo_workdir)" >&2
        echo "pass --force to override" >&2
        exit 4
      fi
    fi
    trash_dir="$vault/.takeoff/.trash/$slug"
    mkdir -p "$trash_dir"
    trash_path="$trash_dir/$trash_name-$(date +%Y%m%dT%H%M%S).md"
    mv -- "$baton" "$trash_path"
    prune_trash
    printf 'trashed %s -> %s\n' "$baton" "$trash_path"
    ;;
esac
