# Session-Start Memory Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the cortex vault so Projects are organized by repo name, Notes have repo associations, and the session-start hook injects relevant memories via a `_repo_index.json` lookup.

**Architecture:** Vault files at `/synosrc/cortex/` get reorganized (move/archive/delete), frontmatter gets `repos` fields, a new `_repo_index.json` maps repo→files, and `session-start-inject.sh` is rewritten to use it.

**Tech Stack:** Bash, jq, Obsidian-flavored Markdown (YAML frontmatter)

---

### Task 1: Create target directories in vault

**Files:**
- Create: `/synosrc/cortex/Projects/libsynosharing/`
- Create: `/synosrc/cortex/Projects/libsynow3/`
- Create: `/synosrc/cortex/Projects/libsynosysnotify/`
- Create: `/synosrc/cortex/Projects/synooauth.synology.com/`
- Create: `/synosrc/cortex/Projects/_archive/`
- Create: `/synosrc/cortex/Projects/_archive/Login portal/`
- Create: `/synosrc/cortex/Notes/FSDN/`

- [ ] **Step 1: Create all directories**

```bash
cd /synosrc/cortex
mkdir -p "Projects/libsynosharing" \
         "Projects/libsynow3" \
         "Projects/libsynosysnotify" \
         "Projects/synooauth.synology.com" \
         "Projects/_archive/Login portal" \
         "Notes/FSDN"
```

- [ ] **Step 2: Verify directories exist**

```bash
ls -d Projects/libsynosharing Projects/libsynow3 Projects/libsynosysnotify \
      "Projects/synooauth.synology.com" Projects/_archive "Projects/_archive/Login portal" \
      Notes/FSDN
```

Expected: All 7 directories listed without error.

- [ ] **Step 3: Commit**

```bash
cd /synosrc/cortex
git add -A Projects/ Notes/FSDN/
git commit -m "chore(vault): create repo-based project directories and Notes/FSDN"
```

Note: git won't track empty directories. Add a `.gitkeep` in each if needed, or this commit happens after files are moved in Task 2.

---

### Task 2: Move Project files to repo directories

**Files:**
- Move: `/synosrc/cortex/Projects/Sharing/Sharing db 搬移至 volume.md` → `Projects/libsynosharing/`
- Move: `/synosrc/cortex/Projects/Sharing/Sharing db 使用 libcephsqlite.md` → `Projects/libsynosharing/`
- Move: `/synosrc/cortex/Projects/Sharing/Application portal support FSDN.md` → `Projects/libsynow3/`

- [ ] **Step 1: Move files**

```bash
cd /synosrc/cortex
mv "Projects/Sharing/Sharing db 搬移至 volume.md" "Projects/libsynosharing/"
mv "Projects/Sharing/Sharing db 使用 libcephsqlite.md" "Projects/libsynosharing/"
mv "Projects/Sharing/Application portal support FSDN.md" "Projects/libsynow3/"
```

- [ ] **Step 2: Verify**

```bash
ls "Projects/libsynosharing/" "Projects/libsynow3/"
```

Expected:
```
Projects/libsynosharing/:
Sharing db 使用 libcephsqlite.md
Sharing db 搬移至 volume.md

Projects/libsynow3/:
Application portal support FSDN.md
```

- [ ] **Step 3: Commit**

```bash
cd /synosrc/cortex
git add -A Projects/
git commit -m "refactor(vault): move project files to repo-based directories"
```

---

### Task 3: Move Notes to Projects

**Files:**
- Move: `/synosrc/cortex/Notes/DSM/synooauth flow chart.md` → `Projects/libsynosysnotify/`
- Move: `/synosrc/cortex/Notes/Nginx/synooauth.md` → `Projects/synooauth.synology.com/`

- [ ] **Step 1: Move files**

```bash
cd /synosrc/cortex
mv "Notes/DSM/synooauth flow chart.md" "Projects/libsynosysnotify/"
mv "Notes/Nginx/synooauth.md" "Projects/synooauth.synology.com/"
```

- [ ] **Step 2: Add `repos` frontmatter to synooauth flow chart**

The file at `Projects/libsynosysnotify/synooauth flow chart.md` currently has:

```yaml
---
title: "synooauth flow chart"
tags:
  - DSM
  - oauth
  - authentication
  - notification
created: 2023-08-22
source: notion
url: https://www.notion.so/6a91a8d5304c49e697bf6936507155a0
---
```

Add `repos` field after `title`:

```yaml
---
title: "synooauth flow chart"
repos:
  - synooauth.synology.com
  - libsynosysnotify
  - webapi-Notification
  - dsm-AdminCenter
tags:
  - DSM
  - oauth
  - authentication
  - notification
created: 2023-08-22
source: notion
url: https://www.notion.so/6a91a8d5304c49e697bf6936507155a0
---
```

- [ ] **Step 3: Verify**

```bash
ls "Projects/libsynosysnotify/" "Projects/synooauth.synology.com/"
head -15 "Projects/libsynosysnotify/synooauth flow chart.md"
```

Expected: Both files present. Frontmatter shows `repos:` field.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/cortex
git add -A Notes/ Projects/
git commit -m "refactor(vault): move synooauth notes to project directories"
```

---

### Task 4: Move Notes to FSDN category

**Files:**
- Move: `/synosrc/cortex/Notes/DSM/FSDN.md` → `Notes/FSDN/`
- Move: `/synosrc/cortex/Notes/DSM/volume move.md` → `Notes/FSDN/`

- [ ] **Step 1: Move files**

```bash
cd /synosrc/cortex
mv "Notes/DSM/FSDN.md" "Notes/FSDN/"
mv "Notes/DSM/volume move.md" "Notes/FSDN/"
```

- [ ] **Step 2: Verify**

```bash
ls "Notes/FSDN/"
```

Expected:
```
FSDN.md
volume move.md
```

- [ ] **Step 3: Commit**

```bash
cd /synosrc/cortex
git add -A Notes/
git commit -m "refactor(vault): create Notes/FSDN category, move FSDN and volume move"
```

---

### Task 5: Archive old Projects and delete re-send notify

**Files:**
- Move to archive: 7 files (see below)
- Delete: `/synosrc/cortex/Notes/DSM/re-send notify.md`

- [ ] **Step 1: Move old projects to archive**

```bash
cd /synosrc/cortex
mv "Projects/Login portal.md" "Projects/_archive/"
mv "Projects/Login portal/修正 Webapi-theme.md" "Projects/_archive/Login portal/"
mv "Projects/Login portal/Web service & domain relay.md" "Projects/_archive/Login portal/"
mv "Projects/Login portal/Reverse proxy remove in FSDN.md" "Projects/_archive/Login portal/"
mv "Projects/Sharing/Sharing.md" "Projects/_archive/"
mv "Projects/Sharing/Access control profiles support FSDN.md" "Projects/_archive/"
mv "Projects/WebAPI.md" "Projects/_archive/"
```

- [ ] **Step 2: Remove empty old directories**

```bash
cd /synosrc/cortex
rmdir "Projects/Login portal" 2>/dev/null || true
rmdir "Projects/Sharing" 2>/dev/null || true
```

- [ ] **Step 3: Delete re-send notify**

```bash
rm "Notes/DSM/re-send notify.md"
```

- [ ] **Step 4: Verify vault structure**

```bash
cd /synosrc/cortex
find Projects -name "*.md" | sort
echo "---"
find Notes -name "*.md" | sort
```

Expected Projects:
```
Projects/_archive/Access control profiles support FSDN.md
Projects/_archive/Login portal.md
Projects/_archive/Login portal/Reverse proxy remove in FSDN.md
Projects/_archive/Login portal/Web service & domain relay.md
Projects/_archive/Login portal/修正 Webapi-theme.md
Projects/_archive/Sharing.md
Projects/_archive/WebAPI.md
Projects/libsynosharing/Sharing db 使用 libcephsqlite.md
Projects/libsynosharing/Sharing db 搬移至 volume.md
Projects/libsynosysnotify/synooauth flow chart.md
Projects/libsynow3/Application portal support FSDN.md
Projects/synooauth.synology.com/synooauth.md
```

Expected Notes should NOT contain `re-send notify.md`, `FSDN.md` in DSM, or `volume move.md` in DSM.

- [ ] **Step 5: Commit**

```bash
cd /synosrc/cortex
git add -A Projects/ Notes/
git commit -m "chore(vault): archive old projects, delete re-send notify"
```

---

### Task 6: Add `repos` frontmatter to Notes

**Files:**
- Modify: `/synosrc/cortex/Notes/Nginx/Nginx.md`
- Modify: `/synosrc/cortex/Notes/Nginx/Service config.md`
- Modify: `/synosrc/cortex/Notes/Nginx/Certificate.md`
- Modify: `/synosrc/cortex/Notes/Nginx/Avahi.md`
- Modify: `/synosrc/cortex/Notes/Nginx/server alias location.md`
- Modify: `/synosrc/cortex/Notes/DSM/DSM6 web 問題.md`

All 6 files get `repos:\n  - libsynow3` added to their YAML frontmatter, after `tags` (or after the last existing field before `---`).

- [ ] **Step 1: Add repos to Nginx.md**

Current frontmatter:
```yaml
---
title: Nginx
tags:
  - nginx
  - dsm
created: 2023-07-24
source: notion
url: "http://nginx.org/en/docs/"
---
```

Add `repos` after `tags`:
```yaml
---
title: Nginx
tags:
  - nginx
  - dsm
repos:
  - libsynow3
created: 2023-07-24
source: notion
url: "http://nginx.org/en/docs/"
---
```

- [ ] **Step 2: Add repos to Service config.md**

Current frontmatter:
```yaml
---
title: Service config
tags:
  - nginx
  - dsm
created: 2023-08-22
source: notion
---
```

Change to:
```yaml
---
title: Service config
tags:
  - nginx
  - dsm
repos:
  - libsynow3
created: 2023-08-22
source: notion
---
```

- [ ] **Step 3: Add repos to Certificate.md**

Current frontmatter:
```yaml
---
title: Certificate
tags:
  - nginx
  - dsm
  - security
created: 2023-07-24
source: notion
url: "https://synowiki.synology.inc/index.php/Certificate_Center"
---
```

Change to:
```yaml
---
title: Certificate
tags:
  - nginx
  - dsm
  - security
repos:
  - libsynow3
created: 2023-07-24
source: notion
url: "https://synowiki.synology.inc/index.php/Certificate_Center"
---
```

- [ ] **Step 4: Add repos to Avahi.md**

Current frontmatter:
```yaml
---
title: Avahi
tags:
  - nginx
  - dsm
  - network
created: 2023-09-06
source: notion
---
```

Change to:
```yaml
---
title: Avahi
tags:
  - nginx
  - dsm
  - network
repos:
  - libsynow3
created: 2023-09-06
source: notion
---
```

- [ ] **Step 5: Add repos to server alias location.md**

Current frontmatter:
```yaml
---
title: "server alias location"
tags:
  - nginx
  - configuration
  - mustache
created: 2023-09-20
source: notion
url: https://www.notion.so/4ba0727f20fa431394a7a0b4ede2eb81
---
```

Change to:
```yaml
---
title: "server alias location"
tags:
  - nginx
  - configuration
  - mustache
repos:
  - libsynow3
created: 2023-09-20
source: notion
url: https://www.notion.so/4ba0727f20fa431394a7a0b4ede2eb81
---
```

- [ ] **Step 6: Add repos to DSM6 web 問題.md**

Current frontmatter:
```yaml
---
title: DSM6 web 問題
tags:
  - dsm
  - web
  - php
created: 2023-08-22
source: notion
---
```

Change to:
```yaml
---
title: DSM6 web 問題
tags:
  - dsm
  - web
  - php
repos:
  - libsynow3
created: 2023-08-22
source: notion
---
```

- [ ] **Step 7: Verify all 6 files have repos field**

```bash
cd /synosrc/cortex
for f in "Notes/Nginx/Nginx.md" "Notes/Nginx/Service config.md" "Notes/Nginx/Certificate.md" \
         "Notes/Nginx/Avahi.md" "Notes/Nginx/server alias location.md" "Notes/DSM/DSM6 web 問題.md"; do
  echo "=== $f ==="
  grep -A1 "^repos:" "$f" || echo "MISSING repos!"
done
```

Expected: All 6 show `repos:` followed by `  - libsynow3`.

- [ ] **Step 8: Commit**

```bash
cd /synosrc/cortex
git add Notes/
git commit -m "feat(vault): add repos frontmatter to repo-associated notes"
```

---

### Task 7: Generate `_repo_index.json`

**Files:**
- Create: `/synosrc/cortex/_repo_index.json`

The index is built from two sources:
1. **Directory-based:** Files under `Projects/<repo-name>/` (excluding `_archive`)
2. **Frontmatter-based:** Any `.md` file with `repos:` field in frontmatter

- [ ] **Step 1: Write the index generation script**

Create `/synosrc/misc/cortex/scripts/build-repo-index.sh`:

```bash
#!/bin/bash
set -euo pipefail

VAULT="${1:-/synosrc/cortex}"
OUTPUT="$VAULT/_repo_index.json"

# Start with empty JSON object
index="{}"

# 1. Scan Projects/<repo-name>/ directories (skip _archive)
for dir in "$VAULT"/Projects/*/; do
  dir_name=$(basename "$dir")
  [[ "$dir_name" == "_archive" ]] && continue
  [[ ! -d "$dir" ]] && continue

  # Find all .md files in this directory
  while IFS= read -r -d '' f; do
    rel_path="${f#$VAULT/}"
    index=$(echo "$index" | jq --arg repo "$dir_name" --arg path "$rel_path" \
      '.[$repo].projects += [$path]')
  done < <(find "$dir" -name "*.md" -print0)
done

# 2. Scan all .md files for repos: frontmatter
while IFS= read -r -d '' f; do
  rel_path="${f#$VAULT/}"

  # Extract repos from frontmatter (between first --- and second ---)
  in_frontmatter=false
  in_repos=false
  while IFS= read -r line; do
    if [[ "$line" == "---" ]]; then
      if $in_frontmatter; then break; fi
      in_frontmatter=true
      continue
    fi
    if $in_frontmatter; then
      if [[ "$line" =~ ^repos: ]]; then
        in_repos=true
        continue
      fi
      if $in_repos; then
        if [[ "$line" =~ ^[[:space:]]+- ]]; then
          repo=$(echo "$line" | sed 's/^[[:space:]]*- *//')
          # Determine if this is a project or note
          if [[ "$rel_path" == Projects/* ]]; then
            index=$(echo "$index" | jq --arg repo "$repo" --arg path "$rel_path" \
              '.[$repo].projects += [$path]')
          else
            index=$(echo "$index" | jq --arg repo "$repo" --arg path "$rel_path" \
              '.[$repo].notes += [$path]')
          fi
        else
          in_repos=false
        fi
      fi
    fi
  done < "$f"
done < <(find "$VAULT/Notes" "$VAULT/Projects" -name "*.md" -print0 2>/dev/null)

# 3. Deduplicate arrays and ensure both keys exist for each repo
index=$(echo "$index" | jq '
  to_entries | map(
    .value = {
      projects: (.value.projects // [] | unique),
      notes: (.value.notes // [] | unique)
    }
  ) | from_entries
')

# Write output
echo "$index" | jq '.' > "$OUTPUT"
echo "Written to $OUTPUT ($(echo "$index" | jq 'keys | length') repos)"
```

- [ ] **Step 2: Run the script**

```bash
chmod +x /synosrc/misc/cortex/scripts/build-repo-index.sh
bash /synosrc/misc/cortex/scripts/build-repo-index.sh /synosrc/cortex
```

Expected output: `Written to /synosrc/cortex/_repo_index.json (N repos)`

- [ ] **Step 3: Verify index content**

```bash
cat /synosrc/cortex/_repo_index.json | jq .
```

Expected output (order may vary):
```json
{
  "libsynow3": {
    "projects": [
      "Projects/libsynow3/Application portal support FSDN.md"
    ],
    "notes": [
      "Notes/DSM/DSM6 web 問題.md",
      "Notes/Nginx/Avahi.md",
      "Notes/Nginx/Certificate.md",
      "Notes/Nginx/Nginx.md",
      "Notes/Nginx/Service config.md",
      "Notes/Nginx/server alias location.md"
    ]
  },
  "libsynosharing": {
    "projects": [
      "Projects/libsynosharing/Sharing db 使用 libcephsqlite.md",
      "Projects/libsynosharing/Sharing db 搬移至 volume.md"
    ],
    "notes": []
  },
  "libsynosysnotify": {
    "projects": [
      "Projects/libsynosysnotify/synooauth flow chart.md"
    ],
    "notes": []
  },
  "synooauth.synology.com": {
    "projects": [
      "Projects/synooauth.synology.com/synooauth.md"
    ],
    "notes": []
  },
  "dsm-AdminCenter": {
    "projects": [
      "Projects/libsynosysnotify/synooauth flow chart.md"
    ],
    "notes": []
  },
  "webapi-Notification": {
    "projects": [
      "Projects/libsynosysnotify/synooauth flow chart.md"
    ],
    "notes": []
  }
}
```

Note: `synooauth flow chart.md` has `repos: [synooauth.synology.com, libsynosysnotify, webapi-Notification, dsm-AdminCenter]`, so it appears under all 4 repo keys. It also appears under `libsynosysnotify` via directory-based scan.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/cortex
git add _repo_index.json
cd /synosrc/misc/cortex
git add scripts/build-repo-index.sh
```

Commit in vault repo:
```bash
cd /synosrc/cortex
git add _repo_index.json
git commit -m "feat(vault): add _repo_index.json for session-start lookup"
```

Commit in plugin repo:
```bash
cd /synosrc/misc/cortex
git add scripts/build-repo-index.sh
git commit -m "feat(scripts): add build-repo-index.sh for vault index generation"
```

---

### Task 8: Rewrite `session-start-inject.sh`

**Files:**
- Modify: `/synosrc/misc/cortex/hooks/scripts/session-start-inject.sh`

- [ ] **Step 1: Write the new hook**

Replace the entire content of `hooks/scripts/session-start-inject.sh` with:

```bash
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

if [[ -z "$CORTEX_DIR" || ! -d "$CORTEX_DIR" ]]; then
  exit 0
fi

REPO_INDEX="$CORTEX_DIR/_repo_index.json"
if [[ ! -f "$REPO_INDEX" ]]; then
  exit 0
fi

# Detect repo name from cwd
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

# Look up repo in index
entry=$(jq -r --arg r "$repo_name" '.[$r] // empty' "$REPO_INDEX" 2>/dev/null)
if [[ -z "$entry" ]]; then
  exit 0
fi

# Extract file summaries
# For each file: read title + status from frontmatter, first non-empty paragraph as summary
extract_summary() {
  local filepath="$1"
  local full_path="$CORTEX_DIR/$filepath"
  [[ ! -f "$full_path" ]] && return

  local title="" st="" summary="" in_fm=false past_fm=false

  while IFS= read -r line; do
    if [[ "$line" == "---" ]]; then
      if $in_fm; then past_fm=true; in_fm=false; continue; fi
      in_fm=true; continue
    fi
    if $in_fm; then
      [[ "$line" =~ ^title:\ *(.*) ]] && title="${BASH_REMATCH[1]//\"/}"
      [[ "$line" =~ ^status:\ *(.*) ]] && st="${BASH_REMATCH[1]}"
      continue
    fi
    if $past_fm; then
      # Skip blank lines and headings before first paragraph
      [[ -z "$line" || "$line" =~ ^# ]] && continue
      # Strip callout prefix
      line="${line#> }"
      line="${line#\[!*\]}"
      # Take first 120 chars as summary
      summary="${line:0:120}"
      break
    fi
  done < "$full_path"

  [[ -z "$title" ]] && title=$(basename "$filepath" .md)

  if [[ -n "$st" ]]; then
    echo "- $title ($st) — $summary"
  else
    echo "- $title — $summary"
  fi
}

# Build output
output=""

# Projects
projects=$(echo "$entry" | jq -r '.projects[]? // empty' 2>/dev/null)
if [[ -n "$projects" ]]; then
  output+="## Projects"$'\n'
  while IFS= read -r f; do
    output+="$(extract_summary "$f")"$'\n'
  done <<< "$projects"
  output+=$'\n'
fi

# Notes
notes=$(echo "$entry" | jq -r '.notes[]? // empty' 2>/dev/null)
if [[ -n "$notes" ]]; then
  output+="## Related Notes"$'\n'
  while IFS= read -r f; do
    output+="$(extract_summary "$f")"$'\n'
  done <<< "$notes"
fi

if [[ -z "$output" ]]; then
  exit 0
fi

cat <<INJECT
[Cortex Memory] ${repo_name} 相關記憶：
${output}
INJECT

exit 0
```

- [ ] **Step 2: Test with mock input (cortex repo — no match expected)**

```bash
echo '{"cwd":"/synosrc/misc/cortex"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
echo "exit: $?"
```

Expected: Empty output (cortex is not in `_repo_index.json`), exit 0.

- [ ] **Step 3: Test with mock input (libsynow3 repo — should match)**

First, find a libsynow3 repo path to simulate:

```bash
echo '{"cwd":"/synosrc/curr/ds.base/source/libsynow3"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
```

Expected output similar to:
```
[Cortex Memory] libsynow3 相關記憶：
## Projects
- Application portal support FSDN (Done) — relay type => sync two sides

## Related Notes
- Nginx — Config 路徑
- Service config — DSM service configuration is defined in `.sc` files.
- Certificate — Architecture
- Avahi — Network discovery protocols used in DSM.
- server alias location — 在 Application 自帶的 mustache 中可以用以下設定
- DSM6 web 問題 — 遇到問題時，先確認是哪個 server config 在作用。
```

- [ ] **Step 4: Test timeout compliance**

```bash
time (echo '{"cwd":"/synosrc/curr/ds.base/source/libsynow3"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh > /dev/null)
```

Expected: Well under 10s (should be <1s).

- [ ] **Step 5: Commit**

```bash
cd /synosrc/misc/cortex
git add hooks/scripts/session-start-inject.sh
git commit -m "feat(hook): rewrite session-start-inject to use _repo_index.json lookup"
```

---

### Task 9: Rebuild `_index.md`

**Files:**
- Modify: `/synosrc/cortex/_index.md`

The `_index.md` needs to reflect the new vault structure. This is a full rewrite of the file.

- [ ] **Step 1: Write updated `_index.md`**

Replace `/synosrc/cortex/_index.md` with content reflecting:

```markdown
---
updated: 2026-04-14
entries: <count>
---

# Cortex Index

## Projects

### libsynow3

| Project | Tags | Summary |
|---------|------|---------|
| [[Application portal support FSDN]] | `FSDN` | relay type => sync two sides, AppPortal access control |

### libsynosharing

| Project | Tags | Summary |
|---------|------|---------|
| [[Sharing db 搬移至 volume]] | `FSDN`, `DSM` | Sharing db 放在 root 可能大量讀寫 => 改成 volume |
| [[Sharing db 使用 libcephsqlite]] | `SOFS` | Sharing db 在 sofs 環境中使用 libcephsqlite |

### libsynosysnotify

| Project | Tags | Summary |
|---------|------|---------|
| [[synooauth flow chart]] | `DSM`, `oauth` | Gmail notification flow: login.php => oauth2/auth |

### synooauth.synology.com

| Project | Tags | Summary |
|---------|------|---------|
| [[synooauth]] | `nginx`, `dsm`, `security` | synooauth.synology.com 行為確認, X-Host redirect 分析 |

## Notes

### C++

| Note | Tags | Summary |
|------|------|---------|
| [[class]] | `c++` | Perfect Forwarding Constructors Should Be Constrained |
| [[Design Pattern 導讀]] | `design-pattern`, `C++`, `OOP` | Design Pattern 系列文章導讀 |
| [[Design Patterns]] | `design-pattern`, `C++` | Design Patterns and Architectural Patterns with C++ |
| [[Radix tree]] | `data-structure`, `radix-tree`, `trie` | Trie tree stores each character as a separate node |
| [[rvalue]] | `c++` | Three For-Range Patterns: Copy, Modify, Read-only |
| [[Rule of Five]] | — | 自動函數產生遵循以下規則 (constructor generation rules) |
| [[C++ library]] | `C++`, `library`, `guides` | Json (nlohmann/json), backtrace utilities |
| [[SOLID intro]] | `design-pattern`, `SOLID`, `OOP` | 物件導向設計五個準則 Principle 的開頭縮寫 |

### Linux

| Note | Tags | Summary |
|------|------|---------|
| [[Linux misc]] | `linux` | dmidecode, 常用指令, emptying buffers cache |
| [[tcpdump]] | `linux`, `networking`, `tcpdump`, `debugging` | tcpdump usage examples with nc and port filtering |
| [[performance bottleneck]] | `linux`, `performance`, `debugging`, `networking` | statmeter, iperf, pidstat for performance analysis |
| [[IPC inspection]] | — | SystemV IPC inspection: ipcs for shm, queues, semaphores |
| [[ssh tunnel]] | `linux`, `ssh` | R 逆向通道, L 本地轉發, D 動態代理 三種用法 |
| [[stop]] | `linux`, `systemd`, `strace`, `syslog-ng` | Add timeout in systemd service, strace PID debugging |
| [[Find process on pipe]] | `linux` | Find process on the other end of a pipe via symlink ID |
| [[Telnet]] | — | connect moxa 用 telnet, session hang solution |

### Web

| Note | Tags | Summary |
|------|------|---------|
| [[CSS selector syntax]] | — | CSS selector: .one .two (descendant) vs .one.two (both) |
| [[playwright]] | `playwright`, `testing`, `remote-debugging`, `mcp` | 遠端 VM 透過 MCP 操控本機瀏覽器 Chrome |
| [[ajax & fetch]] | `web`, `javascript`, `ajax`, `fetch` | Ext.Ajax.request GET/POST and fetch API examples |

### Nginx

| Note | Tags | Summary |
|------|------|---------|
| [[check site server]] | `nginx`, `openssl`, `certificate`, `debugging` | Check site is connected to right server via openssl |
| [[Service config]] | `nginx`, `dsm` | DSM service configuration defined in .sc files |
| [[Certificate]] | `nginx`, `dsm`, `security` | Certificate architecture, important locations |
| [[Avahi]] | `nginx`, `dsm`, `network` | Network discovery protocols: mDNS / DNS-SD in DSM |
| [[status code limit]] | `nginx`, `apache` | apache22 vs apache24 supported HTTP status codes |
| [[server alias location]] | `nginx`, `configuration`, `mustache` | server 端 alias, volumes location 在 mustache 設定 |
| [[Remote Server Debugging Guide]] | `dsm`, `mcp`, `debugging` | MCP + Chrome CDP 進行遠端伺服器除錯 |
| [[link 失敗可能原因]] | `nginx`, `dsm` | mismatch_count, resync 檢查, nginx conf 修復問題 |
| [[proxy redirect]] | `nginx` | trailing slash 影響 URI, alias params 設定 |
| [[Nginx]] | `nginx`, `dsm` | Config 路徑: /etc/nginx, sites-enabled, conf.d |

### DSM

| Note | Tags | Summary |
|------|------|---------|
| [[Web benchmark]] | `dsm`, `webapi`, `performance` | synowebbenchmark 受測機 IP 及 SynoCI machine info |
| [[Disk misc]] | `dsm`, `linux` | smartctl disk health, du vs stat size 差異 |
| [[導測試站]] | `dsm`, `package-center` | sed 修改 pkgupdate_server 導至測試站或 RC 站 |
| [[Package Center guide]] | `dsm`, `package-center` | GitLab Pages developer-guide, showInternalSections |
| [[Support FAQ]] | `dsm` | Web Support 101, support list, uihelp 修改流程 |
| [[Pear]] | — | PHP Pear After DSM7.0, how to install |
| [[裸版開 sshd]] | `DSM`, `ssh`, `systemd` | After mounting, ln -s sshd.service to enable SSH |
| [[3rdparty misc]] | `dsm`, `php` | PHP dependency search script via SYNO.Core.Package API |
| [[DSM6 web 問題]] | `dsm`, `web`, `php` | PHP Config 對應關係: 套件 vs vhost 不同 config |
| [[Nix on DSM]] | `dsm`, `nix`, `devtools` | chroot 套件不齊全, Nix on DSM 解決方案 |
| [[inotify watch limit]] | — | inotify max_user_watches 到達上限造成 service 沒起來 |

### FSDN

| Note | Tags | Summary |
|------|------|---------|
| [[FSDN]] | — | FSDN chassis sn, mgmt ip, controller A/B info |
| [[volume move]] | `dsm`, `fsdn` | FSDN volume switchover 流程, synostgpool 取得 pool info |

## Weekly

### 2025

| Week | Highlights |
|------|------------|
| [[2025-06-30]] | fix(app_portal): get app again for latest config; feat(lib): cluster lock for certificate |
| [[2025-07-07]] | fix(lib): cluster lock cert un-registration; libsynohtmlhander vite manifest parser |
| [[2025-07-14]] | fix(doc): longest prefix match for local_location; vite manifest parser reinforcement |
| [[2025-07-21]] | fix(webapi): check jsoncpp null before isObject; vite manifest parser importmap/nonce |
| [[2025-07-28]] | vite manifest: Static mode with runtime modification; drogon controller [wip] |
| [[2025-08-04]] | vite manifest: entry_name change; code review enhancement: zep memory support |
| [[2025-08-11]] | fix(tarfile): treat overflow in UID/GID; vite manifest constraint order; nodejs 22 porting |
| [[2025-08-18]] | fix(fsdn): hostname in standalone launch URL; njs upgrade 0.9.1; nodejs 22 porting |
| [[2025-08-25]] | fix(core): restore firewall notification; fix(nginx): internal redirect loop; drogon split |
| [[2025-09-01]] | fix(doc): preflight OPTIONS CORS; feat(vite): jsBaseURL from dsm configs; drogon unix socket |
| [[2025-09-08]] | fix(lib): check double parsing issue; drogon server for index handler; syno-toolbox remedy |
| [[2025-09-15]] | fix(libsynoHtmlHandler): ViteEntryScriptTpl Static mode; fix(lib): prevent coredump large double |
| [[2025-09-22]] | feat(security_options): CSP header subdomain support; drogon mobile flow/middleware |
| [[2025-09-29]] | Osaka trip |
| [[2025-10-06]] | Osaka trip |
| [[2025-10-13]] | refactor(template): type-safe template data; vite manifest cache with redis/xxHash |
| [[2025-10-20]] | fix(php): replace rtd1296 with rtd1619b; feat(dsm): per-node relay DDNS for PAM |
| [[2025-10-27]] | fix(login_portal): public access for app_launch; vite cache 3xx ms -> 9x ms |
| [[2025-11-03]] | porting PHP8.3/8.4; vite cache coroutine async; openapi-aggregator [wip] |
| [[2025-11-10]] | fix(portal): init subdomains for null array; porting PHP8.3/PHP8.4; vite cache refactor |
| [[2025-11-17]] | fix(webapi): session cookie domain FQDN; openapi-aggregator registry schema |
| [[2025-11-24]] | openapi-aggregator multi version; nginx tiering; remove wildcard cgi |
| [[2025-12-01]] | feat(gitlab): multi-token rate limiting; fix(csp): synologydownload.com CSP |
| [[2025-12-08]] | fix(cgi): remove trailing dot hostname redirect; openapi-aggregator step by step |
| [[2025-12-15]] | feat(upgrade): c-ares 1.14.0 -> 1.28.1; drogon/trantor Synology build config |
| [[2025-12-22]] | fix(dsm): load before save race condition; openapi-toolchain wiki; drogon redis client |
| [[2025-12-29]] | introduce system version; refactor(htmlhandler): parallel inheritance V3 |

### 2026

| Week | Highlights |
|------|------------|
| [[2026-01-05]] | refactor(htmlhandler): V3 ESM mode JS/CSS; drogon perf report; openapi system version |
| [[2026-01-12]] | fix(PkgManApp): block uninstall unmounted volumes; NextGen-Web-Core cache/middleware |
| [[2026-01-19]] | fix(nginx): clean stale socket files; fix(fsdn): skip reload prevent cluster loop |
| [[2026-01-26]] | NextGen-Web-Core: desktop drogon upstream; webapi perf: optimize lock contention |
| [[2026-02-02]] | NextGen-Web-Core: 3rdparty package registry; css: nginx abnormal cert residual |
| [[2026-02-09]] | fix(core): proxy_pass 443 failure; feat(tierfs): TIERFS silent read; drogon poc benchmark |
| [[2026-02-16]] | (no activity) |
| [[2026-02-23]] | (no activity) |
| [[2026-03-02]] | fix(webapi): validate sort_by whitelist; openapi-toolchain porting python3.8 |
| [[2026-03-09]] | fix(tool): harden synosharingbackup injection; NextGen-Web-Core compatible mode |
| [[2026-03-16]] | feat(nextweb): introduce nextweb; Lite-WebAPI-Shell survey; trantor syslog |
| [[2026-03-23]] | fix(build): drogon migrate deps; feat(nginx): nextweb upstream; webapi boost.beast |
| [[2026-03-30]] | feat(upgrade): cares-1_28_1; fix(login): filter app portal list HA node |
| [[2026-04-06]] | chore(build): replace per-product virtual projects with base build |

## Raw (未提煉)

| Date | Count | Topics |
|------|-------|--------|
| (empty) | 0 | — |
```

Update the `entries` count in frontmatter to match the total number of entries.

- [ ] **Step 2: Count entries and set in frontmatter**

Count: Projects (4 active) + Notes (C++ 8 + Linux 8 + Web 3 + Nginx 10 + DSM 12 + FSDN 2) = 4 + 43 = 47 active entries. Plus weekly entries. Set `entries` to approximate total.

- [ ] **Step 3: Verify wikilinks resolve**

Spot-check that moved files still have correct names:
```bash
cd /synosrc/cortex
ls "Projects/libsynow3/Application portal support FSDN.md"
ls "Notes/FSDN/FSDN.md"
ls "Notes/FSDN/volume move.md"
```

- [ ] **Step 4: Commit**

```bash
cd /synosrc/cortex
git add _index.md
git commit -m "docs(vault): rebuild _index.md for new repo-based structure"
```

---

### Task 10: End-to-end verification

- [ ] **Step 1: Verify vault structure is clean**

```bash
cd /synosrc/cortex
echo "=== Projects (active) ==="
find Projects -name "*.md" -not -path "*/\_archive/*" | sort
echo "=== Projects (archived) ==="
find Projects/_archive -name "*.md" | sort
echo "=== Notes ==="
find Notes -name "*.md" | sort
echo "=== Index ==="
jq 'keys' _repo_index.json
```

- [ ] **Step 2: Test hook with libsynow3**

```bash
echo '{"cwd":"/synosrc/curr/ds.base/source/libsynow3"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
```

Expected: Projects + Related Notes output for libsynow3.

- [ ] **Step 3: Test hook with libsynosharing**

```bash
echo '{"cwd":"/synosrc/curr/ds.base/source/libsynosharing"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
```

Expected: Two sharing project summaries.

- [ ] **Step 4: Test hook with unknown repo**

```bash
echo '{"cwd":"/tmp/some-random-repo"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
echo "exit: $?"
```

Expected: Empty output, exit 0.

- [ ] **Step 5: Test hook with no git repo**

```bash
echo '{"cwd":"/tmp"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
echo "exit: $?"
```

Expected: Empty output, exit 0.
