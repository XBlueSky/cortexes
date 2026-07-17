#!/bin/bash
set -euo pipefail

# SessionEnd hook — filters transcript into Raw/ with context-preservation priority.
# Pipeline: regex cleanup → rtk-style per-command filter → LLM classifier for
# >12KB residue (fail-open). See hooks/scripts/filter-transcript.py for details.
#
# Recursion guard: classifier invokes `claude -p` which triggers its own
# SessionEnd. The CORTEX_SESSION_RECORDING env var short-circuits nested calls.
# nohup+disown: Claude Code kills SessionEnd hooks early, so heavy work is
# detached to survive parent exit.

if [[ -n "${CORTEX_SESSION_RECORDING:-}" ]]; then
  exit 0
fi
export CORTEX_SESSION_RECORDING=1

# Opt-out: a launcher can set CORTEX_SKIP_RECORD=1 to suppress recording this
# session into Raw/. Used by cc-loadout probe sessions (which exist only to
# tick the 5h usage window and carry no distill-worthy content) so they do not
# litter the vault with empty Raws. Checked before any file/queue work.
if [[ -n "${CORTEX_SKIP_RECORD:-}" ]]; then
  exit 0
fi

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // ""')
cwd=$(echo "$input" | jq -r '.cwd // ""')

if [[ -z "$transcript_path" || ! -f "$transcript_path" ]]; then
  exit 0
fi

file_size=$(stat -c%s "$transcript_path" 2>/dev/null || stat -f%z "$transcript_path" 2>/dev/null || echo 0)
if [[ "$file_size" -lt 4096 ]]; then
  exit 0
fi

CORTEX_CONFIG="$HOME/.cortex/config.json"
if [[ ! -f "$CORTEX_CONFIG" ]]; then
  exit 0
fi

vault_path=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null)
if [[ -z "$vault_path" || ! -d "$vault_path" ]]; then
  exit 0
fi

repo_name="unknown"
if [[ -n "$cwd" ]] && git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || basename "$cwd")
fi
repo_name="${repo_name:-unknown}"

date_dir=$(date +%Y/%m/%d)
timestamp=$(date +%H%M%S)
filename="${timestamp}_session_${repo_name}.md"
target_dir="${vault_path}/Raw/${date_dir}"
target_file="${target_dir}/${filename}"
mkdir -p "$target_dir"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER="${SCRIPT_DIR}/filter-transcript.py"
META="${SCRIPT_DIR}/meta_session.py"

nohup bash -c '
  CORTEX_SESSION_RECORDING=1
  export CORTEX_SESSION_RECORDING

  target_file="$1"
  transcript_path="$2"
  repo_name="$3"
  vault_path="$4"
  CORTEX_CONFIG="$5"
  FILTER="$6"
  META="$7"

  {
    cat <<FRONTMATTER
---
date: $(date +%Y-%m-%d)
time: $(date +%H:%M:%S)
type: session
repo: ${repo_name}
tags: [session]
---

FRONTMATTER
    python3 "$FILTER" "$transcript_path" 2>/dev/null || echo "(filter failed)"
  } > "$target_file"

  # Cortex maintenance-pipeline sessions (distill/broadcast/genesis) only
  # process the vault; recording them would re-feed Raw/ into its own distill
  # queue, so the queue could never reach empty. Keep the record as an audit
  # trail but pre-stamp a distilled marker so the grep -rL "<!-- distilled:"
  # queue scan never picks it up again. Fail-open: any error → no marker.
  if python3 "$META" "$transcript_path" >/dev/null 2>&1; then
    printf "\n<!-- distilled: %s → (skip: meta-session) -->\n" "$(date +%Y-%m-%d)" >> "$target_file"
  fi

  auto_commit=$(jq -r ".git.auto_commit // false" "$CORTEX_CONFIG" 2>/dev/null)
  auto_push=$(jq -r ".git.auto_push // false" "$CORTEX_CONFIG" 2>/dev/null)
  if [[ "$auto_commit" == "true" ]]; then
    git -C "$vault_path" add "$target_file" 2>/dev/null || true
    git -C "$vault_path" commit -m "raw: session ${repo_name} $(date +%Y-%m-%d)" 2>/dev/null || true
    if [[ "$auto_push" == "true" ]]; then
      git -C "$vault_path" push 2>/dev/null || true
    fi
  fi
' _ "$target_file" "$transcript_path" "$repo_name" "$vault_path" "$CORTEX_CONFIG" "$FILTER" "$META" >/dev/null 2>&1 &
disown

exit 0
