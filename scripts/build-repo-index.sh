#!/usr/bin/env bash
# build-repo-index.sh
# Builds _repo_index.json mapping repo names to vault files.
#
# Sources:
#   1. Directory-based: Files under Projects/<repo-name>/ (excluding _archive)
#   2. Frontmatter-based: Any .md file with `repos:` field in YAML frontmatter
#
# Output schema:
#   {
#     "<repo-name>": {
#       "projects": ["Projects/<repo-name>/file.md", ...],
#       "notes":    ["Notes/Nginx/Nginx.md", ...]
#     }
#   }

set -euo pipefail

VAULT="${1:-/synosrc/cortex}"
OUTPUT="${VAULT}/_repo_index.json"
JQ=/usr/bin/jq

if [[ ! -d "$VAULT" ]]; then
    echo "Error: vault directory '$VAULT' does not exist" >&2
    exit 1
fi

if [[ ! -x "$JQ" ]]; then
    echo "Error: jq not found at $JQ" >&2
    exit 1
fi

# index is built as a bash associative array:
#   index_projects[<repo>] = newline-separated relative paths
#   index_notes[<repo>]    = newline-separated relative paths
declare -A index_projects
declare -A index_notes

# -----------------------------------------------------------------------
# 1. Directory-based: Projects/<repo-name>/**/*.md  (skip _archive)
# -----------------------------------------------------------------------
if [[ -d "${VAULT}/Projects" ]]; then
    while IFS= read -r -d '' abs_path; do
        # Derive relative path from vault root
        rel_path="${abs_path#${VAULT}/}"

        # Extract repo name: second component after "Projects/"
        # rel_path format: Projects/<repo>/<...>.md
        repo=$(echo "$rel_path" | cut -d'/' -f2)

        [[ -z "$repo" ]] && continue

        # Append to projects list for this repo
        if [[ -n "${index_projects[$repo]+set}" ]]; then
            index_projects[$repo]+=$'\n'"$rel_path"
        else
            index_projects[$repo]="$rel_path"
        fi
    done < <(find "${VAULT}/Projects" \
        -path "${VAULT}/Projects/_archive" -prune -o \
        -path "${VAULT}/Projects/_archive/*" -prune -o \
        -name "*.md" -print0 | sort -z)
fi

# -----------------------------------------------------------------------
# Helper: parse repos list from YAML frontmatter of a single file.
# Handles both inline list (repos: [a, b]) and block list:
#   repos:
#     - a
#     - b
# Returns one repo name per line.
# -----------------------------------------------------------------------
parse_repos_from_file() {
    local file="$1"
    python3 - "$file" <<'PYEOF'
import sys, re

path = sys.argv[1]
try:
    with open(path, encoding='utf-8', errors='replace') as f:
        content = f.read()
except Exception:
    sys.exit(0)

# Extract YAML frontmatter between first --- delimiters
m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
if not m:
    sys.exit(0)

fm = m.group(1)

# Find the repos: key — either inline list or block list
# Inline: repos: [a, b, c]
inline = re.search(r'^repos:\s*\[([^\]]+)\]', fm, re.MULTILINE)
if inline:
    items = [x.strip().strip('"\'') for x in inline.group(1).split(',')]
    for item in items:
        if item:
            print(item)
    sys.exit(0)

# Block list: repos:\n  - item
block = re.search(r'^repos:\s*\n((?:[ \t]+-[^\n]+\n?)+)', fm, re.MULTILINE)
if block:
    for line in block.group(1).splitlines():
        item = re.sub(r'^[ \t]+-\s*', '', line).strip().strip('"\'')
        if item:
            print(item)
PYEOF
}

# -----------------------------------------------------------------------
# 2. Frontmatter-based: all .md files under Projects/ and Notes/
# -----------------------------------------------------------------------
for scan_dir in Projects Notes; do
    [[ ! -d "${VAULT}/${scan_dir}" ]] && continue

    while IFS= read -r -d '' abs_path; do
        rel_path="${abs_path#${VAULT}/}"

        # Determine bucket: projects or notes
        bucket=$(echo "$rel_path" | cut -d'/' -f1 | tr '[:upper:]' '[:lower:]')

        # Read repos from frontmatter
        repos_list=$(parse_repos_from_file "$abs_path")
        [[ -z "$repos_list" ]] && continue

        while IFS= read -r repo; do
            [[ -z "$repo" ]] && continue

            if [[ "$bucket" == "projects" ]]; then
                if [[ -n "${index_projects[$repo]+set}" ]]; then
                    # Avoid duplicates
                    if ! echo "${index_projects[$repo]}" | grep -qxF "$rel_path"; then
                        index_projects[$repo]+=$'\n'"$rel_path"
                    fi
                else
                    index_projects[$repo]="$rel_path"
                fi
            else
                if [[ -n "${index_notes[$repo]+set}" ]]; then
                    if ! echo "${index_notes[$repo]}" | grep -qxF "$rel_path"; then
                        index_notes[$repo]+=$'\n'"$rel_path"
                    fi
                else
                    index_notes[$repo]="$rel_path"
                fi
            fi
        done <<< "$repos_list"
    done < <(find "${VAULT}/${scan_dir}" \
        -path "${VAULT}/Projects/_archive" -prune -o \
        -path "${VAULT}/Projects/_archive/*" -prune -o \
        -name "*.md" -print0 | sort -z)
done

# -----------------------------------------------------------------------
# 3. Collect all repo names
# -----------------------------------------------------------------------
declare -A all_repos
for r in "${!index_projects[@]}"; do all_repos[$r]=1; done
for r in "${!index_notes[@]}"; do all_repos[$r]=1; done

# -----------------------------------------------------------------------
# 4. Build JSON with jq
# -----------------------------------------------------------------------
# Strategy: build a jq null-input expression by feeding data via --argjson

# Build a JSON object: { "<repo>": { "projects": [...], "notes": [...] }, ... }
result='{}'

for repo in "${!all_repos[@]}"; do
    projects_json='[]'
    notes_json='[]'

    if [[ -n "${index_projects[$repo]+set}" && -n "${index_projects[$repo]}" ]]; then
        # Convert newline-separated list to JSON array via jq, deduplicating
        projects_json=$(printf '%s\n' "${index_projects[$repo]}" \
            | sort -u \
            | $JQ -Rs '[split("\n")[] | select(length > 0)] | unique')
    fi

    if [[ -n "${index_notes[$repo]+set}" && -n "${index_notes[$repo]}" ]]; then
        notes_json=$(printf '%s\n' "${index_notes[$repo]}" \
            | sort -u \
            | $JQ -Rs '[split("\n")[] | select(length > 0)] | unique')
    fi

    repo_obj=$($JQ -n \
        --argjson projects "$projects_json" \
        --argjson notes "$notes_json" \
        '{"projects": $projects, "notes": $notes}')

    result=$($JQ -n \
        --argjson acc "$result" \
        --arg repo "$repo" \
        --argjson entry "$repo_obj" \
        '$acc + {($repo): $entry}')
done

# Sort keys for deterministic output
echo "$result" | $JQ --sort-keys '.' > "$OUTPUT"
echo "Written: $OUTPUT"
