#!/bin/bash
set -euo pipefail

# Resolve vault path: env var > config.json > skip
CORTEX_CONFIG="$HOME/.cortex/config.json"
CORTEX_DIR=""

if [[ -n "${CORTEX_VAULT_PATH:-}" ]]; then
  CORTEX_DIR="$CORTEX_VAULT_PATH"
elif [[ -f "$CORTEX_CONFIG" ]]; then
  CORTEX_DIR=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null || echo "")
fi

# No vault configured or no directory, skip silently
if [[ -z "$CORTEX_DIR" || ! -d "$CORTEX_DIR" ]]; then
  exit 0
fi

REPO_INDEX="$CORTEX_DIR/_repo_index.json"
if [[ ! -f "$REPO_INDEX" ]]; then
  exit 0
fi

# Read stdin JSON, extract .cwd
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")

if [[ -z "$cwd" ]]; then
  exit 0
fi

# Detect repo name from cwd via git remote
repo_name=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null | sed 's|.*/||;s|\.git$||' || true)
fi

if [[ -z "$repo_name" ]]; then
  exit 0
fi

# Look up repo in _repo_index.json with jq
matched=$(jq -r --arg repo "$repo_name" '
  if has($repo) then
    (.[$repo].projects // [])[] ,
    (.[$repo].notes // [])[]
  else empty end
' "$REPO_INDEX" 2>/dev/null || true)

if [[ -z "$matched" ]]; then
  exit 0
fi

# Helper: extract title and status from YAML frontmatter and first paragraph summary
extract_file_info() {
  local filepath="$1"
  local full_path="$CORTEX_DIR/$filepath"

  if [[ ! -f "$full_path" ]]; then
    return
  fi

  local filename
  filename=$(basename "$filepath" .md)

  # Extract frontmatter (between first and second ---)
  local title status summary

  title=$(awk '
    BEGIN { in_fm=0; found=0 }
    /^---$/ { if (!in_fm) { in_fm=1; next } else { exit } }
    in_fm && /^title:/ { sub(/^title:[[:space:]]*/, ""); print; found=1; exit }
  ' "$full_path" 2>/dev/null | sed 's/^["'"'"']//;s/["'"'"']$//' || true)

  status=$(awk '
    BEGIN { in_fm=0 }
    /^---$/ { if (!in_fm) { in_fm=1; next } else { exit } }
    in_fm && /^status:/ { sub(/^status:[[:space:]]*/, ""); print; exit }
  ' "$full_path" 2>/dev/null | sed 's/^["'"'"']//;s/["'"'"']$//' || true)

  # Use filename if title is empty
  if [[ -z "$title" ]]; then
    title="$filename"
  fi

  # Extract first non-empty, non-heading paragraph after frontmatter
  # Skip frontmatter, skip blank lines and headings, get first content line
  summary=$(awk '
    BEGIN { in_fm=0; fm_done=0; found=0 }
    /^---$/ {
      if (!in_fm) { in_fm=1; next }
      else { fm_done=1; next }
    }
    !fm_done { next }
    fm_done && found { next }
    /^#/ { next }
    /^[[:space:]]*$/ { next }
    {
      # Strip callout prefixes like "> " and "> [!note]" etc.
      line = $0
      gsub(/^>[[:space:]]*(\[![a-zA-Z]+\])?[[:space:]]*/, "", line)
      if (line != "") {
        print line
        found=1
      }
    }
  ' "$full_path" 2>/dev/null | head -1 || true)

  # Cap summary at 120 chars
  if [[ ${#summary} -gt 120 ]]; then
    summary="${summary:0:120}..."
  fi

  echo "${title}|${status}|${summary}"
}

# Collect projects and notes entries
project_files=$(jq -r --arg repo "$repo_name" '
  if has($repo) then (.[$repo].projects // [])[] else empty end
' "$REPO_INDEX" 2>/dev/null || true)

note_files=$(jq -r --arg repo "$repo_name" '
  if has($repo) then (.[$repo].notes // [])[] else empty end
' "$REPO_INDEX" 2>/dev/null || true)

# Build output sections, cap at 10 total
output_projects=""
output_notes=""
total_count=0

while IFS= read -r fpath; do
  [[ -z "$fpath" ]] && continue
  [[ $total_count -ge 10 ]] && break
  info=$(extract_file_info "$fpath")
  [[ -z "$info" ]] && continue
  title=$(echo "$info" | cut -d'|' -f1)
  status=$(echo "$info" | cut -d'|' -f2)
  summary=$(echo "$info" | cut -d'|' -f3-)
  if [[ -n "$status" ]]; then
    line="- ${title} (${status}) — ${summary}"
  else
    line="- ${title} — ${summary}"
  fi
  output_projects="${output_projects}${line}"$'\n'
  ((total_count++)) || true
done <<< "$project_files"

while IFS= read -r fpath; do
  [[ -z "$fpath" ]] && continue
  [[ $total_count -ge 10 ]] && break
  info=$(extract_file_info "$fpath")
  [[ -z "$info" ]] && continue
  title=$(echo "$info" | cut -d'|' -f1)
  summary=$(echo "$info" | cut -d'|' -f3-)
  line="- ${title} — ${summary}"
  output_notes="${output_notes}${line}"$'\n'
  ((total_count++)) || true
done <<< "$note_files"

# If nothing collected, exit silently
if [[ -z "$output_projects" && -z "$output_notes" ]]; then
  exit 0
fi

# Print formatted output
echo "[Cortex Memory] ${repo_name} 相關記憶："
echo ""

if [[ -n "$output_projects" ]]; then
  echo "## Projects"
  printf "%s" "$output_projects"
fi

if [[ -n "$output_notes" ]]; then
  if [[ -n "$output_projects" ]]; then
    echo ""
  fi
  echo "## Related Notes"
  printf "%s" "$output_notes"
fi

exit 0
