#!/bin/bash
set -euo pipefail

# SessionEnd hook — automatic session recording via claude -p
# Reads transcript, calls Claude Sonnet to summarize, writes to vault

# Recursion guard: child claude -p also triggers SessionEnd → prevent infinite loop
if [[ -n "${CORTEX_SESSION_RECORDING:-}" ]]; then
  exit 0
fi
export CORTEX_SESSION_RECORDING=1

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // ""')
cwd=$(echo "$input" | jq -r '.cwd // ""')

# No transcript → skip
if [[ -z "$transcript_path" || ! -f "$transcript_path" ]]; then
  exit 0
fi

# Trivial session? skip (< 4KB)
file_size=$(stat -c%s "$transcript_path" 2>/dev/null || stat -f%z "$transcript_path" 2>/dev/null || echo 0)
if [[ "$file_size" -lt 4096 ]]; then
  exit 0
fi

# Read vault config
CORTEX_CONFIG="$HOME/.cortex/config.json"
if [[ ! -f "$CORTEX_CONFIG" ]]; then
  exit 0
fi

vault_path=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null)

if [[ -z "$vault_path" || ! -d "$vault_path" ]]; then
  exit 0
fi

# Detect repo name
repo_name="unknown"
if [[ -n "$cwd" ]] && git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || basename "$cwd")
fi
repo_name="${repo_name:-unknown}"

# Prepare output path
date_dir=$(date +%Y/%m/%d)
timestamp=$(date +%H%M%S)
filename="${timestamp}_session_${repo_name}.md"
target_dir="${vault_path}/Raw/${date_dir}"
target_file="${target_dir}/${filename}"
mkdir -p "$target_dir"

# Summarize transcript with claude -p
prompt='You are a session recorder. Given a Claude Code session transcript (JSONL), produce a concise session report in Markdown. Include ONLY sections that have real content — omit empty sections entirely.

Sections to consider:
## Commits — git commits made (subject, repo, issue ref)
## Discoveries — technical insights, root causes, observations
## Decisions — architecture/design decisions and reasoning
## Other — code reviews, support tickets, helping colleagues
## Unfinished — work in progress, things left to do

Rules:
- Be concise, capture essence not verbatim
- If the session was truly trivial, output exactly: TRIVIAL
- Write in the same language the user used in the session'

report=$(cat "$transcript_path" \
  | claude -p --model sonnet --no-session-persistence "$prompt" 2>/dev/null) \
  || exit 0

# Trivial session → clean up and skip
if [[ "$report" == "TRIVIAL" ]]; then
  exit 0
fi

# Write report with frontmatter
cat > "$target_file" <<EOF
---
date: $(date +%Y-%m-%d)
time: $(date +%H:%M:%S)
type: session
repo: ${repo_name}
tags: [session]
---

${report}
EOF

# Git commit and push if enabled
auto_commit=$(jq -r '.git.auto_commit // false' "$CORTEX_CONFIG" 2>/dev/null)
auto_push=$(jq -r '.git.auto_push // false' "$CORTEX_CONFIG" 2>/dev/null)
if [[ "$auto_commit" == "true" ]]; then
  git -C "$vault_path" add "$target_file" 2>/dev/null || true
  git -C "$vault_path" commit -m "raw: session ${repo_name} $(date +%Y-%m-%d)" 2>/dev/null || true
  if [[ "$auto_push" == "true" ]]; then
    git -C "$vault_path" push 2>/dev/null || true
  fi
fi

exit 0
