#!/bin/bash
set -euo pipefail

# Resolve vault path: env var > config.json > skip
CORTEX_CONFIG="$HOME/.cortex/config.json"
CORTEX_DIR=""

if [[ -n "${CORTEX_VAULT_PATH:-}" ]]; then
  CORTEX_DIR="$CORTEX_VAULT_PATH"
elif [[ -f "$CORTEX_CONFIG" ]]; then
  CORTEX_DIR=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null)
fi

# No vault configured or no _index.md, skip silently
if [[ -z "$CORTEX_DIR" || ! -d "$CORTEX_DIR" ]]; then
  exit 0
fi

INDEX_FILE="$CORTEX_DIR/_index.md"
if [[ ! -f "$INDEX_FILE" ]]; then
  exit 0
fi

# Try to detect current repo name from cwd
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")

if [[ -z "$cwd" ]]; then
  exit 0
fi

repo_name=""
if [[ -d "$cwd/.git" ]] || git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null | sed 's|.*/||;s|\.git$||' || basename "$cwd")
fi

if [[ -z "$repo_name" ]]; then
  exit 0
fi

# Search _index.md for matching project and related notes
project_line=$(grep -i "$repo_name" "$INDEX_FILE" 2>/dev/null | head -5 || true)

if [[ -z "$project_line" ]]; then
  exit 0
fi

# Extract tags from the project line (second column in table)
tags=$(echo "$project_line" | sed 's/.*| *\([^|]*\) *|.*/\1/' | tr ',' '\n' | sed 's/^ *//;s/ *$//' | head -5)

# Find related notes by tags
related_notes=""
for tag in $tags; do
  matches=$(grep -i "$tag" "$INDEX_FILE" 2>/dev/null | grep -v "^##" | head -3 || true)
  if [[ -n "$matches" ]]; then
    related_notes="$related_notes
$matches"
  fi
done

# Deduplicate
related_notes=$(echo "$related_notes" | sort -u | head -10)

# Output context for injection
cat <<INJECT
[Cortex Memory] ${repo_name} 相關記憶：
${project_line}
${related_notes}
INJECT

exit 0
