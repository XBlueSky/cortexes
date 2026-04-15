# Cortex Vec — Vector Store Infrastructure

**Date:** 2026-04-14
**Status:** Draft
**Depends on:** session-start-memory-injection (completed)

**Updated:** 2026-04-15 — Refactored to Python package. Removed: export-repo-index,
info, --tags filter, --plain output, status "Last rebuild". See
`docs/superpowers/specs/2026-04-15-cortex-vec-refactor-design.md` for rationale.

## Problem

Cortex vault search relies on keyword grep and `_index.md` table scanning. This misses semantically similar content (e.g., "nginx config path" won't find "Service config"). The `_repo_index.json` is maintained separately from the vault content, creating a sync risk. There's no shared infrastructure for query, distill, and evolve to leverage semantic understanding.

## Goals

1. Provide a single vector store as the semantic index for the entire vault
2. Expose it via a CLI tool (`cortex-vec`) callable from bash hooks and Claude skills
3. Support metadata filtering (by repo, type, tags, category)
4. Replace `_repo_index.json` with an export from the vector store
5. Keep the vault as plain markdown — vector store is a derived, rebuildable index

## Architecture

```
Vault (.md files)                    ← source of truth, git-synced
    ↓ cortex-vec rebuild
ChromaDB PersistentClient            ← derived index, local only
    ~/.cortex/vectorstore/           ← SQLite-based, not in git
    ↓ cortex-vec export-repo-index
_repo_index.json                     ← derived from vector store
```

### What lives where

| Artifact | Location | In git? |
|----------|----------|---------|
| Vault markdown files | `/synosrc/cortex/` | Yes |
| ChromaDB data | `~/.cortex/vectorstore/` | No |
| `cortex-vec` CLI | `/synosrc/misc/cortex/scripts/cortex-vec` | Yes (plugin repo) |

### ChromaDB collection schema

Single collection: `cortex`

Each document = one `.md` file from the vault.

**Document content:** Full text of the `.md` file (excluding YAML frontmatter delimiters).

**Document ID:** Relative path from vault root (e.g., `Notes/Nginx/Nginx.md`).

**Metadata fields:**

| Field | Type | Source | Example |
|-------|------|--------|---------|
| `type` | string | Directory prefix | `note`, `project`, `weekly`, `raw` |
| `category` | string | Parent directory | `Nginx`, `DSM`, `C++`, `FSDN` |
| `repo` | string | Directory name (Projects) or frontmatter `repos` | `libsynow3` |
| `repos` | string (comma-separated) | Frontmatter `repos` field | `libsynow3,synonginx` |
| `title` | string | Frontmatter `title` or filename | `Certificate` |
| `status` | string | Frontmatter `status` | `Done`, `In progress` |
| `tags` | string (comma-separated) | Frontmatter `tags` | `nginx,dsm,security` |
| `source_path` | string | Absolute path | `/synosrc/cortex/Notes/Nginx/Nginx.md` |

**Notes on metadata:**
- ChromaDB metadata values must be strings, ints, floats, or bools — no arrays. So `repos` and `tags` are stored as comma-separated strings.
- A file under `Projects/libsynow3/` gets `repo: "libsynow3"` automatically. If it also has `repos: [synooauth.synology.com, libsynosysnotify]` in frontmatter, the document is **inserted multiple times** with different `repo` values — once per repo. Document IDs use a repo suffix to stay unique (e.g., `Projects/libsynosysnotify/synooauth flow chart.md::synooauth.synology.com`). The base path (without `::` suffix) is the real file path used for reading and display.
- `_archive/` files are excluded from indexing.

### Embedding model

`all-MiniLM-L6-v2` via ChromaDB's default embedding function.

- ChromaDB ships with `chromadb.utils.embedding_functions.DefaultEmbeddingFunction` which uses `all-MiniLM-L6-v2` from sentence-transformers
- Auto-downloads on first use (~80MB)
- Runs locally, no API key needed
- 384-dimensional embeddings
- Good balance of quality and speed for our vault size (~90 documents)

## CLI Design: `cortex-vec`

A Python script at `/synosrc/misc/cortex/scripts/cortex-vec`.

### Installation

Requires: `pip install chromadb`

The script reads vault path from `~/.cortex/config.json` (same as all cortex tools).

### Subcommands

#### `cortex-vec rebuild`

Full rebuild of the vector store from vault contents.

```bash
cortex-vec rebuild
```

1. Delete existing ChromaDB collection `cortex` (if any)
2. Scan `Notes/`, `Projects/` (skip `_archive/`), `Weekly/` for `.md` files
3. For each file: parse frontmatter, extract metadata, embed full content
4. For files with multiple `repos`: insert once per repo with suffixed ID
5. Auto-run `export-repo-index` at the end
6. Report: `Rebuilt: N documents indexed`

#### `cortex-vec upsert <relative-path>`

Add or update a single document.

```bash
cortex-vec upsert Notes/Nginx/new-note.md
```

1. Read the file, parse frontmatter
2. Upsert into ChromaDB (by document ID)
3. Handle multi-repo insertion
4. Report: `Upserted: Notes/Nginx/new-note.md`

Does NOT auto-run `export-repo-index` — caller decides when to export.

#### `cortex-vec delete <relative-path>`

Remove a document from the index.

```bash
cortex-vec delete Notes/DSM/re-send\ notify.md
```

#### `cortex-vec search <query>`

Semantic search across the vault.

```bash
cortex-vec search "nginx certificate 設定"
cortex-vec search "nginx config" --repo libsynow3
cortex-vec search "sharing db" --type project
cortex-vec search "OAuth flow" --n 3
```

Options:
- `--repo <name>` — filter by repo metadata
- `--type <note|project|weekly|raw>` — filter by type
- `--category <name>` — filter by category (Nginx, DSM, etc.)
- `--n <count>` — number of results (default: 5)

Output: newline-delimited JSON, one per result:
```json
{"id": "Notes/Nginx/Certificate.md", "score": 0.87, "title": "Certificate", "type": "note", "repo": "libsynow3", "summary": "Certificate architecture, important locations"}
```

The `summary` field is the first 120 chars of content after frontmatter (same logic as session-start hook).

#### `cortex-vec status`

Show index health.

```bash
cortex-vec status
```

Output:
```
Collection: cortex
Documents:  92
Model:      all-MiniLM-L6-v2
DB path:    /root/.cortex/vectorstore/
Vault:      /synosrc/cortex
```

### CLI output conventions

- Default output: JSON (machine-readable, for AI agent consumption)
- Exit 0: success
- Exit 1: error (message to stderr)

## Integration points

### session-start hook

The hook no longer reads `_repo_index.json`. Instead, it injects a lazy loading
prompt that asks the AI to offer memory loading to the user. If the user accepts,
the AI uses `cortex-vec search --repo <name>` to retrieve relevant content.

### cortex:evolve skill

After writing a `.md` file to the vault:
1. Run `cortex-vec upsert <path>`

### cortex:distill skill

Before writing a refined note:
1. Run `cortex-vec search "<discovery text>" --n 3` to check for duplicates
2. If high similarity (score > 0.85) to existing note → suggest merging instead of creating new

After writing:
1. Run `cortex-vec upsert <path>`

### cortex:query skill

Replace grep-based search with:
1. Run `cortex-vec search "<query>" [--repo] [--type] [--tags]`
2. Present ranked results to user
3. If user wants details → read the file

### cortex:genesis skill

Add to initialization:
1. `pip install chromadb` (if not installed)
2. `cortex-vec rebuild`

## Migration

1. Install chromadb: `pip install chromadb`
2. Create `scripts/cortex-vec` CLI
3. Run `cortex-vec rebuild` to build initial index
4. Remove `scripts/build-repo-index.sh` (replaced by `cortex-vec export-repo-index`)
5. Update skills to use `cortex-vec` commands
6. Update `cortex:genesis` to include vector store rebuild

## Out of scope

- Skill rewrites (distill, query, evolve) — covered in Spec B
- MCP server for cortex-vec — not needed yet
- Multi-collection support — one collection is enough
- Incremental re-embedding detection (ChromaDB doesn't deduplicate by content hash) — full rebuild is fast enough for ~90 docs
