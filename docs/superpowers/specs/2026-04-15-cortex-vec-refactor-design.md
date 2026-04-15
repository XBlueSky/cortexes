# Cortex-Vec Refactor — Design Spec

**Date:** 2026-04-15
**Status:** Approved
**Based on:** Design review report (`report.md`, commits `fd807f7..b0e0aab`)

## Problem

The cortex-vec implementation has several issues identified in the design review:

1. **Critical:** `upsert` does not remove stale `::repo`-suffixed entries when a note's repo membership changes, causing wrong search results and stale data
2. **High:** Spec describes features not implemented (`--tags` filter, `--plain` output, `status` last rebuild) — spec/impl drift
3. **High:** Frontmatter parser is a custom regex-based implementation that is fragile against edge cases — now core infrastructure for indexing
4. **Medium:** Metadata extraction logic duplicated between `cortex-vec` (Python) and `session-start-inject.sh` (bash/awk)
5. **Medium:** README claims "zero external dependency" but ChromaDB, pysqlite3, and embedding model are required
6. **Medium:** Runtime dependencies undocumented
7. **Low-Medium:** `_repo_index.json` export couples session-start hook to export freshness

## Decisions Made During Brainstorming

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Frontmatter parser | Replace with `python-frontmatter` (PyYAML-based) | Most common library in Obsidian Python tooling; chromadb already broke "zero deps" |
| Spec/impl drift | Remove unneeded features from spec, not implement them | `--tags` (no controlled vocabulary, semantic search covers it), `--plain` (consumer is AI agent), `status` last rebuild (all writes go through skills + upsert, no drift) |
| Project structure | Refactor into proper Python module with `pyproject.toml` | Enables `pip install -e .`, clean CLI in PATH, proper dependency management |
| Session-start hook | Rewrite as lazy loading prompt (like superpowers plugin) | Eliminates: duplicated metadata extraction (#4), hook/export coupling (#7), `_repo_index.json` dependency. AI asks user whether to load memory — avoids wasting context on small tasks |
| `_repo_index.json` + `export-repo-index` | Remove (YAGNI) | Only consumer was session-start hook, which no longer reads it |
| `info` subcommand | Not needed | Was designed for hook file parsing, hook no longer parses files |
| Execution strategy | Module refactor in one pass (方案 B) | 491 lines, ~90 docs — small enough for one-shot refactor |

## Architecture

### Before

```
scripts/cortex-vec (single 491-line Python script)
    ↓ imports chromadb at top level (~2.7s cold start)
    ↓ custom regex frontmatter parser
    ↓ export-repo-index → _repo_index.json

hooks/scripts/session-start-inject.sh (183 lines)
    ↓ reads _repo_index.json
    ↓ awk/sed parses each matched file for title/status/summary
    ↓ injects formatted output into session context
```

### After

```
cortex-vec/ (Python module, pip install -e .)
    ├── parser.py      ← python-frontmatter, no chromadb dependency
    ├── store.py       ← chromadb operations, upsert with stale cleanup
    └── cli.py         ← argparse entry point

hooks/scripts/session-start-inject.sh (~25 lines)
    ↓ detects repo name from git remote
    ↓ injects prompt: "ask user if they want to load cortex memory"
    ↓ AI decides whether to call cortex-vec search
```

## Module Structure

```
cortex-vec/
├── pyproject.toml
└── src/
    └── cortex_vec/
        ├── __init__.py
        ├── cli.py          # argparse + main, lazy dispatch to store
        ├── config.py       # load_config, get_vault_path, VECTORSTORE_DIR, COLLECTION_NAME
        ├── parser.py       # python-frontmatter wrapper, extract_summary, classify_path
        └── store.py        # get_client, get_collection, rebuild, upsert, delete, search, status
```

### pyproject.toml

```toml
[project]
name = "cortex-vec"
version = "0.2.0"
requires-python = ">=3.8"
dependencies = [
    "chromadb",
    "python-frontmatter",
    "pysqlite3-binary",
]

[project.scripts]
cortex-vec = "cortex_vec.cli:main"

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
```

Installation: `pip install -e /path/to/cortex/cortex-vec`

## CLI Subcommands (Final)

| Subcommand | Description | Needs ChromaDB |
|------------|-------------|:-:|
| `rebuild` | Full rebuild of vector store from vault | Yes |
| `upsert <path>` | Add/update single document (with stale entry cleanup) | Yes |
| `delete <path>` | Remove a document and all `::repo` variants | Yes |
| `search <query>` | Semantic search (`--repo`, `--type`, `--category`, `--n`) | Yes |
| `status` | Show collection name, document count, model, DB path, vault path | Yes |

### Removed from spec

- ~~`export-repo-index`~~ — no consumer after hook redesign
- ~~`info <path>`~~ — hook no longer parses files
- ~~`--tags` filter~~ — no controlled vocabulary; semantic search covers tag content
- ~~`--plain` output flag~~ — consumer is AI agent, JSON only
- ~~`status` "Last rebuild"~~ — all writes go through skills + upsert

## Fix: Upsert Stale Entry Cleanup

The most important correctness fix. In `store.py`:

```python
def upsert_document(collection, rel_path, document, metadata_list, repos):
    """Upsert a document, cleaning up stale repo-suffixed entries first."""
    # Step 1: Remove ALL existing entries for this path
    existing_ids = collection.get(include=[])["ids"]
    stale = [i for i in existing_ids if i == rel_path or i.startswith(f"{rel_path}::")]
    if stale:
        collection.delete(ids=stale)

    # Step 2: Insert current entries
    for repo, metadata in zip(repos, metadata_list):
        doc_id = rel_path if not repo or len(repos) == 1 else f"{rel_path}::{repo}"
        collection.upsert(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )
```

This ensures that when a note's `repos` field changes (e.g., `[repoA, repoB]` → `[repoA]`), the stale `path::repoB` entry is removed before reinserting.

The same pattern is reused in `rebuild` (which deletes the entire collection first, so no stale issue) and `delete` (which already does prefix matching).

## Fix: Frontmatter Parser

Replace custom `parse_frontmatter()` with `python-frontmatter` in `parser.py`:

```python
import frontmatter

def parse_document(text):
    """Parse frontmatter and body from markdown text."""
    post = frontmatter.loads(text)
    fm = dict(post.metadata)

    # Normalize tags/repos lists to comma-separated strings (ChromaDB metadata constraint)
    for key in ("tags", "repos"):
        if key in fm and isinstance(fm[key], list):
            fm[key] = ",".join(str(v) for v in fm[key])

    return fm, post.content
```

`extract_summary()` and `classify_path()` remain as utility functions in `parser.py`, unchanged in logic.

## Session-Start Hook Redesign

Replace the 183-line eager-loading hook with a ~25-line lazy-loading prompt injection:

```bash
#!/usr/bin/env bash
set -euo pipefail

input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")
[[ -z "$cwd" ]] && exit 0

repo_name=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || true)
fi
[[ -z "$repo_name" ]] && exit 0

context="[Cortex] 你目前在 ${repo_name} repo。\
Cortex vault 中可能有此 repo 的相關記憶（技術筆記、專案決策、踩坑紀錄）。\
請詢問使用者是否需要載入 cortex memory。\
如需載入，使用 cortex-vec search --repo ${repo_name} 查詢相關內容。"

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
  "$(echo "$context" | sed 's/"/\\"/g')"
exit 0
```

**Key behavior change:** Instead of eagerly loading all related vault content into context, the hook injects a prompt that asks the AI to offer memory loading to the user. The user decides per-session whether they need context.

## Files Changed

| Category | File | Action |
|----------|------|--------|
| **New** | `cortex-vec/pyproject.toml` | Create Python package definition |
| **New** | `cortex-vec/src/cortex_vec/__init__.py` | Module init |
| **New** | `cortex-vec/src/cortex_vec/cli.py` | CLI entry point + argparse |
| **New** | `cortex-vec/src/cortex_vec/config.py` | Config loading + constants |
| **New** | `cortex-vec/src/cortex_vec/parser.py` | python-frontmatter wrapper |
| **New** | `cortex-vec/src/cortex_vec/store.py` | ChromaDB operations + upsert fix |
| **Delete** | `scripts/cortex-vec` | Replaced by Python module |
| **Rewrite** | `hooks/scripts/session-start-inject.sh` | 183 → ~25 lines, lazy loading |
| **Edit** | `skills/cortex-evolve/SKILL.md` | Remove `export-repo-index` step |
| **Edit** | `skills/cortex-distill/SKILL.md` | Remove `export-repo-index` step |
| **Edit** | `skills/cortex-query/SKILL.md` | Remove `--tags` filter description |
| **Edit** | `docs/specs/2026-04-14-cortex-vec-design.md` | Align with actual implementation |
| **Edit** | `README.md` | Update architecture, deps, data flow |

### Not changed

- `hooks/hooks.json` — hook config unchanged
- `hooks/scripts/session-end-record.sh` — unrelated
- `skills/cortex-weekly/SKILL.md` — unaffected
