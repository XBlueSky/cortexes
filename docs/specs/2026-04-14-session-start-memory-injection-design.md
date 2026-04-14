# Session-Start Memory Injection Redesign

**Date:** 2026-04-14
**Status:** Draft

## Problem

The current `session-start-inject.sh` hook uses `grep -i "$repo_name" _index.md` to find relevant vault memories at session start. This is broken:

1. Matches title lines like `# Cortex Index` — noise
2. Tag extraction fails on non-table rows
3. No repo-to-note mapping exists — even correct grep can't find useful content
4. `_index.md` has no real repo names in it

## Goals

1. Automatically inject relevant Projects and Notes when entering a repo
2. Multi-layer lookup: find matching files → extract summaries
3. Keep injection concise (frontmatter + first paragraph) to stay within timeout
4. Maintain a machine-readable index for O(1) lookup

## Design

### 1. Vault Structure Changes

#### 1.1 Projects — Repo-based directories

New Projects use `Projects/<repo-name>/` as directory structure.

**Migrations from existing Projects:**

| File | Target |
|------|--------|
| `Sharing db 搬移至 volume.md` | `Projects/libsynosharing/` |
| `Sharing db 使用 libcephsqlite.md` | `Projects/libsynosharing/` |
| `Application portal support FSDN.md` | `Projects/libsynow3/` |

**Migrations from Notes to Projects:**

| File | Target |
|------|--------|
| `Notes/DSM/synooauth flow chart.md` | `Projects/libsynosysnotify/` |
| `Notes/Nginx/synooauth.md` | `Projects/synooauth.synology.com/` |

**Archive (no longer useful):**

Move to `Projects/_archive/`:
- `Login portal.md` (index page, no content)
- `Login portal/修正 Webapi-theme.md` (Done, minimal)
- `Login portal/Web service & domain relay.md` (Done, minimal)
- `Login portal/Reverse proxy remove in FSDN.md` (Done, minimal)
- `Sharing/Sharing.md` (index page, no content)
- `Sharing/Access control profiles support FSDN.md` (Done, minimal)
- `WebAPI.md` (Notion template remnant, empty)

**Delete:**
- `Notes/DSM/re-send notify.md`

#### 1.2 Notes — Add FSDN category, add repos frontmatter

**New directory:** `Notes/FSDN/`

Move into `Notes/FSDN/`:
- `Notes/DSM/FSDN.md` → `Notes/FSDN/FSDN.md`
- `Notes/DSM/volume move.md` → `Notes/FSDN/volume move.md`

**Add `repos` frontmatter** to strongly-associated Notes:

| Note | repos |
|------|-------|
| `Notes/Nginx/Nginx.md` | `[libsynow3]` |
| `Notes/Nginx/Service config.md` | `[libsynow3]` |
| `Notes/Nginx/Certificate.md` | `[libsynow3]` |
| `Notes/Nginx/Avahi.md` | `[libsynow3]` |
| `Notes/Nginx/server alias location.md` | `[libsynow3]` |
| `Notes/DSM/DSM6 web 問題.md` | `[libsynow3]` |

All other Notes (C++, Linux, Web, remaining DSM/Nginx) remain unchanged — general knowledge, not repo-specific.

#### 1.3 Project file frontmatter convention

All Project files under `Projects/<repo-name>/` inherit repo association from directory name. Cross-repo projects add explicit `repos` in frontmatter:

```yaml
---
title: synooauth flow chart
status: Done
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
---
```

### 2. Repo Index (`_repo_index.json`)

A machine-readable index mapping repo names to vault files.

**Location:** `<vault>/_repo_index.json`

**Schema:**

```json
{
  "<repo-name>": {
    "projects": ["Projects/<repo-name>/file.md", ...],
    "notes": ["Notes/Nginx/Nginx.md", ...]
  }
}
```

**Maintenance:**
- `cortex:evolve` skill updates the index when saving to vault
- Can be rebuilt from scratch by scanning all `.md` files for `repos` frontmatter + `Projects/<dir>/` structure

**Example:**

```json
{
  "libsynow3": {
    "projects": [
      "Projects/libsynow3/Application portal support FSDN.md"
    ],
    "notes": [
      "Notes/Nginx/Nginx.md",
      "Notes/Nginx/Service config.md",
      "Notes/Nginx/Certificate.md",
      "Notes/Nginx/Avahi.md",
      "Notes/Nginx/server alias location.md",
      "Notes/DSM/DSM6 web 問題.md"
    ]
  },
  "libsynosharing": {
    "projects": [
      "Projects/libsynosharing/Sharing db 搬移至 volume.md",
      "Projects/libsynosharing/Sharing db 使用 libcephsqlite.md"
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
  }
}
```

### 3. Hook Rewrite (`session-start-inject.sh`)

**Flow:**

1. Resolve vault path (same as current)
2. Detect repo name from cwd (same as current)
3. Read `_repo_index.json` with `jq` — get file lists for repo
4. For each matched file (cap at 10):
   - Extract `title` and `status` from frontmatter
   - Extract first non-frontmatter paragraph as summary (cap at 3 lines)
5. Format and output

**Output format:**

```
[Cortex Memory] libsynow3 相關記憶：

## Projects
- Application portal support FSDN (Done) — relay type => sync two sides, AppPortal access control

## Related Notes
- Nginx — Config 路徑, server/location 匹配規則, CLI 工具, 診斷流程
- Certificate — 憑證架構, synocrtregister, self-signed cert
- Service config — .sc 檔格式, GenW3Conf 內部流程
```

**Timeout:** Keep 10s. The jq + head approach should complete in <1s.

### 4. `_index.md` Update

After all migrations, `_index.md` needs to be rebuilt to reflect:
- New `Projects/<repo-name>/` structure
- Moved/archived/deleted files
- New `Notes/FSDN/` category

This can be done by `cortex:genesis` or a dedicated rebuild script.

## Out of Scope

- `cortex:evolve` changes to auto-maintain `_repo_index.json` (separate task)
- `cortex:query` integration with repo index
- Prompt-based hooks (SessionStart doesn't support `type: "prompt"`)

## Migration Order

1. Create new directories (`Projects/libsynosharing/`, etc.)
2. Move/archive/delete files
3. Add `repos` frontmatter to Notes
4. Generate `_repo_index.json`
5. Rewrite `session-start-inject.sh`
6. Rebuild `_index.md`
