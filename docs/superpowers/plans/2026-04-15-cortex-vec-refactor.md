# Cortex-Vec Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor cortex-vec from a single script into a proper Python module, fix the critical upsert bug, replace the custom frontmatter parser, redesign session-start hook as lazy loading, and align specs/docs with reality.

**Architecture:** The single `scripts/cortex-vec` (491 lines) becomes a `cortex-vec/` Python package installed via `pip install -e .`. Session-start hook is rewritten from 183-line eager loader to ~25-line prompt injector. `_repo_index.json` and `export-repo-index` are removed (YAGNI).

**Tech Stack:** Python 3.8+, ChromaDB, python-frontmatter (PyYAML), pysqlite3-binary, bash

---

## File Structure

```
cortex-vec/                          # NEW — Python package
├── pyproject.toml                   # Package definition + dependencies
└── src/
    └── cortex_vec/
        ├── __init__.py              # Version string
        ├── cli.py                   # argparse entry point, dispatches to store
        ├── config.py                # load_config, get_vault_path, constants
        ├── parser.py                # python-frontmatter wrapper, extract_summary, classify_path
        └── store.py                 # ChromaDB: rebuild, upsert (with stale cleanup), delete, search, status

scripts/cortex-vec                   # DELETE — replaced by package
hooks/scripts/session-start-inject.sh # REWRITE — lazy loading prompt
skills/cortex-evolve/SKILL.md        # EDIT — remove export-repo-index
skills/cortex-distill/SKILL.md       # EDIT — remove export-repo-index
skills/cortex-query/SKILL.md         # EDIT — remove --tags
docs/specs/2026-04-14-cortex-vec-design.md # EDIT — align with reality
README.md                           # EDIT — update architecture + deps
```

---

## Task 1: Create Python Package Skeleton

**Files:**
- Create: `cortex-vec/pyproject.toml`
- Create: `cortex-vec/src/cortex_vec/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "cortex-vec"
version = "0.2.0"
description = "Vector store CLI for the cortex vault"
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

- [ ] **Step 2: Create __init__.py**

```python
"""cortex-vec — Vector store CLI for the cortex vault."""

__version__ = "0.2.0"
```

- [ ] **Step 3: Verify directory structure**

Run: `find cortex-vec/ -type f`

Expected:
```
cortex-vec/pyproject.toml
cortex-vec/src/cortex_vec/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add cortex-vec/
git commit -m "chore(cortex-vec): scaffold Python package skeleton"
```

---

## Task 2: Implement config.py

**Files:**
- Create: `cortex-vec/src/cortex_vec/config.py`

- [ ] **Step 1: Create config.py**

```python
"""Configuration loading and constants."""

import json
import sys
from pathlib import Path

CORTEX_CONFIG = Path.home() / ".cortex" / "config.json"
VECTORSTORE_DIR = Path.home() / ".cortex" / "vectorstore"
COLLECTION_NAME = "cortex"


def load_config():
    """Load ~/.cortex/config.json. Exit with error if not found."""
    if not CORTEX_CONFIG.exists():
        print(
            "Error: ~/.cortex/config.json not found. Run /cortex:genesis first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(CORTEX_CONFIG) as f:
        return json.load(f)


def get_vault_path():
    """Return the vault path from config. Exit with error if invalid."""
    cfg = load_config()
    vault = cfg.get("vault_path", "")
    if not vault or not Path(vault).is_dir():
        print(f"Error: vault_path '{vault}' not found.", file=sys.stderr)
        sys.exit(1)
    return Path(vault)
```

- [ ] **Step 2: Commit**

```bash
git add cortex-vec/src/cortex_vec/config.py
git commit -m "feat(cortex-vec): add config module"
```

---

## Task 3: Implement parser.py

**Files:**
- Create: `cortex-vec/src/cortex_vec/parser.py`

- [ ] **Step 1: Install python-frontmatter**

Run: `pip install python-frontmatter`

- [ ] **Step 2: Create parser.py**

```python
"""Frontmatter parsing and content classification."""

import re
from pathlib import Path

import frontmatter


def parse_document(text):
    """Parse frontmatter and body from markdown text.

    Returns (dict, str) — metadata dict and body content.
    Lists in tags/repos are normalized to comma-separated strings
    (ChromaDB metadata only accepts scalar values).
    """
    post = frontmatter.loads(text)
    fm = dict(post.metadata)

    for key in ("tags", "repos"):
        if key in fm and isinstance(fm[key], list):
            fm[key] = ",".join(str(v) for v in fm[key])

    return fm, post.content


def extract_summary(body, max_len=120):
    """Extract first non-empty, non-heading line from body."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"^>\s*(\[![a-zA-Z]+\])?\s*", "", stripped)
        if stripped:
            return stripped[:max_len]
    return ""


def classify_path(rel_path):
    """Determine (type, category) from vault-relative path.

    Returns:
        tuple: (doc_type, category) e.g. ("note", "Nginx"), ("project", "libsynow3")
    """
    parts = Path(rel_path).parts
    if not parts:
        return "unknown", ""

    top = parts[0]
    if top == "Notes":
        category = parts[1] if len(parts) > 2 else ""
        return "note", category
    elif top == "Projects":
        if len(parts) > 1 and parts[1] == "_archive":
            return "archive", ""
        repo = parts[1] if len(parts) > 1 else ""
        return "project", repo
    elif top == "Weekly":
        return "weekly", ""
    elif top == "Raw":
        return "raw", ""
    return "unknown", ""
```

- [ ] **Step 3: Verify import works**

Run: `cd /synosrc/misc/cortex && PYTHONPATH=cortex-vec/src python3 -c "from cortex_vec.parser import parse_document; print('ok')"`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add cortex-vec/src/cortex_vec/parser.py
git commit -m "feat(cortex-vec): add parser module with python-frontmatter"
```

---

## Task 4: Implement store.py (with upsert fix)

**Files:**
- Create: `cortex-vec/src/cortex_vec/store.py`

This is the most critical module — contains the upsert stale entry fix.

- [ ] **Step 1: Create store.py**

```python
"""ChromaDB vector store operations."""

# pysqlite3 patch: system SQLite (3.22) is too old for ChromaDB (needs >= 3.35)
__import__("pysqlite3")
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import chromadb

from .config import COLLECTION_NAME, VECTORSTORE_DIR, get_vault_path
from .parser import classify_path, extract_summary, parse_document


def get_client():
    """Return a persistent ChromaDB client."""
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTORSTORE_DIR))


def get_collection(client):
    """Get or create the cortex collection."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _resolve_repos(doc_type, category, repos_str):
    """Build repo list from doc type, category, and frontmatter repos field."""
    repos = []
    if doc_type == "project" and category:
        repos.append(category)
    if repos_str:
        for r in repos_str.split(","):
            r = r.strip()
            if r and r not in repos:
                repos.append(r)
    return repos if repos else [""]


def _build_metadata(doc_type, category, title, tags, repos_str, status, source_path, repo):
    """Build metadata dict for a single ChromaDB entry."""
    metadata = {
        "type": doc_type,
        "category": category,
        "title": title,
        "tags": tags,
        "source_path": str(source_path),
    }
    if repo:
        metadata["repo"] = repo
    if repos_str:
        metadata["repos"] = repos_str
    if status:
        metadata["status"] = status
    return metadata


def _delete_stale_entries(collection, rel_path):
    """Remove all existing entries for a path (base + ::repo variants).

    This is the critical fix for the stale repo association bug.
    Must be called before inserting new entries for a document.
    """
    all_ids = collection.get(include=[])["ids"]
    stale = [i for i in all_ids if i == rel_path or i.startswith(f"{rel_path}::")]
    if stale:
        collection.delete(ids=stale)
    return stale


def cmd_status(_args):
    """Show index health."""
    vault = get_vault_path()
    client = get_client()
    try:
        col = client.get_collection(COLLECTION_NAME)
        count = col.count()
    except Exception:
        count = 0

    print(f"Collection: {COLLECTION_NAME}")
    print(f"Documents:  {count}")
    print(f"Model:      all-MiniLM-L6-v2 (default)")
    print(f"DB path:    {VECTORSTORE_DIR}")
    print(f"Vault:      {vault}")


def cmd_rebuild(_args):
    """Full rebuild of vector store from vault."""
    vault = get_vault_path()
    client = get_client()

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    col = get_collection(client)
    scan_dirs = ["Notes", "Projects", "Weekly"]
    doc_count = 0

    for scan_dir in scan_dirs:
        scan_path = vault / scan_dir
        if not scan_path.is_dir():
            continue

        for md_file in scan_path.rglob("*.md"):
            rel_path = str(md_file.relative_to(vault))
            if "_archive" in rel_path:
                continue

            text = md_file.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_document(text)

            doc_type, category = classify_path(rel_path)
            title = fm.get("title", md_file.stem)
            status = fm.get("status", "")
            tags = fm.get("tags", "")
            repos_str = fm.get("repos", "")

            repos = _resolve_repos(doc_type, category, repos_str)
            embed_content = f"{title}\n\n{body}".strip()
            if not embed_content:
                continue

            for repo in repos:
                doc_id = (
                    rel_path
                    if not repo or len(repos) == 1
                    else f"{rel_path}::{repo}"
                )
                metadata = _build_metadata(
                    doc_type, category, title, tags, repos_str, status,
                    str(md_file), repo,
                )
                col.upsert(
                    ids=[doc_id],
                    documents=[embed_content],
                    metadatas=[metadata],
                )
                doc_count += 1

    print(f"Rebuilt: {doc_count} documents indexed")


def cmd_upsert(args):
    """Add or update a single document with stale entry cleanup."""
    vault = get_vault_path()
    rel_path = args.path
    full_path = vault / rel_path

    if not full_path.exists():
        print(f"Error: {full_path} not found.", file=sys.stderr)
        sys.exit(1)

    client = get_client()
    col = get_collection(client)

    # Critical fix: clean stale entries before reinserting
    _delete_stale_entries(col, rel_path)

    text = full_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_document(text)

    doc_type, category = classify_path(rel_path)
    title = fm.get("title", full_path.stem)
    status = fm.get("status", "")
    tags = fm.get("tags", "")
    repos_str = fm.get("repos", "")

    repos = _resolve_repos(doc_type, category, repos_str)
    embed_content = f"{title}\n\n{body}".strip()

    for repo in repos:
        doc_id = (
            rel_path
            if not repo or len(repos) == 1
            else f"{rel_path}::{repo}"
        )
        metadata = _build_metadata(
            doc_type, category, title, tags, repos_str, status,
            str(full_path), repo,
        )
        col.upsert(
            ids=[doc_id],
            documents=[embed_content],
            metadatas=[metadata],
        )

    print(f"Upserted: {rel_path}")


def cmd_delete(args):
    """Remove a document from the index."""
    client = get_client()
    col = get_collection(client)
    rel_path = args.path

    stale = _delete_stale_entries(col, rel_path)
    if not stale:
        print(f"Not found: {rel_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Deleted: {len(stale)} entries for {rel_path}")


def cmd_search(args):
    """Semantic search across the vault."""
    import json
    from pathlib import Path

    client = get_client()
    col = get_collection(client)
    vault = get_vault_path()

    query = args.query
    n = args.n or 5

    where_clauses = []
    if args.repo:
        where_clauses.append({"repo": args.repo})
    if args.type:
        where_clauses.append({"type": args.type})
    if args.category:
        where_clauses.append({"category": args.category})

    where = None
    if len(where_clauses) == 1:
        where = where_clauses[0]
    elif len(where_clauses) > 1:
        where = {"$and": where_clauses}

    kwargs = {
        "query_texts": [query],
        "n_results": n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = col.query(**kwargs)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, dists):
        score = round(1 - dist, 4)
        doc_id = meta.get("source_path", "")
        try:
            rel_id = str(Path(doc_id).relative_to(vault))
        except (ValueError, TypeError):
            rel_id = doc_id

        summary = extract_summary(doc)

        entry = {
            "id": rel_id,
            "score": score,
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "repo": meta.get("repo", ""),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", ""),
            "summary": summary,
        }
        print(json.dumps(entry, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): add store module with upsert stale entry fix"
```

---

## Task 5: Implement cli.py

**Files:**
- Create: `cortex-vec/src/cortex_vec/cli.py`

- [ ] **Step 1: Create cli.py**

```python
"""CLI entry point for cortex-vec."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="cortex-vec — Vector store CLI for cortex vault"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show index health")
    sub.add_parser("rebuild", help="Full rebuild from vault")

    p_upsert = sub.add_parser("upsert", help="Add/update a document")
    p_upsert.add_argument("path", help="Relative path from vault root")

    p_delete = sub.add_parser("delete", help="Remove a document")
    p_delete.add_argument("path", help="Relative path from vault root")

    p_search = sub.add_parser("search", help="Semantic search")
    p_search.add_argument("query", help="Search query text")
    p_search.add_argument("--repo", help="Filter by repo")
    p_search.add_argument("--type", help="Filter by type (note/project/weekly)")
    p_search.add_argument("--category", help="Filter by category")
    p_search.add_argument("--n", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Lazy import: chromadb (~2.7s) only loaded when store is needed
    from . import store

    commands = {
        "status": store.cmd_status,
        "rebuild": store.cmd_rebuild,
        "upsert": store.cmd_upsert,
        "delete": store.cmd_delete,
        "search": store.cmd_search,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Install package in editable mode**

Run: `pip install -e /synosrc/misc/cortex/cortex-vec`

- [ ] **Step 3: Verify CLI works**

Run: `cortex-vec --help`

Expected:
```
usage: cortex-vec [-h] {status,rebuild,upsert,delete,search} ...

cortex-vec — Vector store CLI for cortex vault

positional arguments:
  {status,rebuild,upsert,delete,search}
    status              Show index health
    rebuild             Full rebuild from vault
    upsert              Add/update a document
    delete              Remove a document
    search              Semantic search
```

- [ ] **Step 4: Verify cortex-vec status works end-to-end**

Run: `cortex-vec status`

Expected: Output showing collection name, document count, model, DB path, vault path.

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/cli.py
git commit -m "feat(cortex-vec): add CLI entry point"
```

---

## Task 6: Delete Old Script

**Files:**
- Delete: `scripts/cortex-vec`

- [ ] **Step 1: Verify new CLI is functional**

Run: `which cortex-vec && cortex-vec status`

Expected: Shows the pip-installed path and valid status output.

- [ ] **Step 2: Delete old script**

Run: `rm /synosrc/misc/cortex/scripts/cortex-vec`

- [ ] **Step 3: Remove empty scripts/ directory if empty**

Run: `rmdir /synosrc/misc/cortex/scripts/ 2>/dev/null || true`

- [ ] **Step 4: Commit**

```bash
git rm scripts/cortex-vec
git commit -m "chore: remove old cortex-vec script, replaced by Python package"
```

---

## Task 7: Rewrite Session-Start Hook

**Files:**
- Rewrite: `hooks/scripts/session-start-inject.sh`

- [ ] **Step 1: Rewrite the hook**

Replace the entire contents of `hooks/scripts/session-start-inject.sh` with:

```bash
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

# No vault configured, skip silently
if [[ -z "$CORTEX_DIR" || ! -d "$CORTEX_DIR" ]]; then
  exit 0
fi

# Read stdin JSON, extract .cwd
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")
[[ -z "$cwd" ]] && exit 0

# Detect repo name from cwd via git remote
repo_name=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || true)
fi
[[ -z "$repo_name" ]] && exit 0

# Lazy loading prompt — AI asks user whether to load memory
context="[Cortex] 你目前在 ${repo_name} repo。Cortex vault 中可能有此 repo 的相關記憶（技術筆記、專案決策、踩坑紀錄）。請詢問使用者是否需要載入 cortex memory。如需載入，使用 cortex-vec search --repo ${repo_name} 查詢相關內容。"

# Escape for JSON
context_escaped=$(echo "$context" | sed 's/"/\\"/g')

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
  "$context_escaped"
exit 0
```

- [ ] **Step 2: Test the hook**

Run: `echo '{"cwd":"/synosrc/misc/cortex"}' | bash hooks/scripts/session-start-inject.sh`

Expected: JSON output with `hookSpecificOutput.additionalContext` containing the lazy loading prompt with repo name "cortex".

- [ ] **Step 3: Commit**

```bash
git add hooks/scripts/session-start-inject.sh
git commit -m "refactor(hook): rewrite session-start as lazy loading prompt"
```

---

## Task 8: Update Skills

**Files:**
- Edit: `skills/cortex-evolve/SKILL.md`
- Edit: `skills/cortex-distill/SKILL.md`
- Edit: `skills/cortex-query/SKILL.md`

- [ ] **Step 1: Update cortex-evolve**

In `skills/cortex-evolve/SKILL.md`, replace the "Update Vector Store" section at the end:

Change from:
```markdown
## Update Vector Store

After committing the new file to the vault:

1. Run: `cortex-vec upsert <relative-path-from-vault>`
2. Run: `cortex-vec export-repo-index`

Where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`.
```

Change to:
```markdown
## Update Vector Store

After committing the new file to the vault:

1. Run: `cortex-vec upsert <relative-path-from-vault>`
```

- [ ] **Step 2: Update cortex-distill**

In `skills/cortex-distill/SKILL.md`:

In Step 3 (Deduplication Check), change the cortex-vec path:

Change from:
```markdown
1. Run: `cortex-vec search "<discovery text>" --n 3`
   (where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`)
```

Change to:
```markdown
1. Run: `cortex-vec search "<discovery text>" --n 3`
```

In Step 6 (Update Index), change from:
```markdown
1. Run: `cortex-vec upsert <relative-path>`
2. Run: `cortex-vec export-repo-index`
3. Update `_index.md`: append row, update entries count and date
```

Change to:
```markdown
1. Run: `cortex-vec upsert <relative-path>`
2. Update `_index.md`: append row, update entries count and date
```

In Step 7 (Commit), change from:
```markdown
git add Raw/ Notes/ Projects/ _index.md _repo_index.json
```

Change to:
```markdown
git add Raw/ Notes/ Projects/ _index.md
```

- [ ] **Step 3: Update cortex-query**

In `skills/cortex-query/SKILL.md`, in Layer 1 section, change the cortex-vec path:

Change from:
```markdown
Where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`.
```

Change to:
```markdown
`cortex-vec` is installed as a CLI tool (via pip).
```

Remove the `--tags` filter from the "Additional filters" section. Change from:
```markdown
**Additional filters:** Apply when the user specifies:
- `--type note|project|weekly` — filter by content type
- `--category Nginx|DSM|...` — filter by category
- `--tags <tag>` — filter by tags
```

Change to:
```markdown
**Additional filters:** Apply when the user specifies:
- `--type note|project|weekly` — filter by content type
- `--category Nginx|DSM|...` — filter by category
```

- [ ] **Step 4: Commit**

```bash
git add skills/cortex-evolve/SKILL.md skills/cortex-distill/SKILL.md skills/cortex-query/SKILL.md
git commit -m "docs(skills): update skills for cortex-vec package migration"
```

---

## Task 9: Update Spec

**Files:**
- Edit: `docs/specs/2026-04-14-cortex-vec-design.md`

- [ ] **Step 1: Update the spec**

Apply the following changes to `docs/specs/2026-04-14-cortex-vec-design.md`:

1. Add a note at the top after the header:

```markdown
**Updated:** 2026-04-15 — Refactored to Python package. Removed: export-repo-index,
info, --tags filter, --plain output, status "Last rebuild". See
`docs/superpowers/specs/2026-04-15-cortex-vec-refactor-design.md` for rationale.
```

2. In "### What lives where" table, remove the `_repo_index.json` row.

3. In "### Subcommands" section:
   - Remove the `cortex-vec export-repo-index` subsection entirely
   - In `cortex-vec search`, remove `--tags` from options list and examples
   - In `cortex-vec status`, remove `Last rebuild: 2026-04-14` from example output
   - In `cortex-vec upsert`, add note about stale entry cleanup

4. In "### CLI output conventions", remove the `--plain` flag description. Change to:
```markdown
### CLI output conventions

- Default output: JSON (machine-readable, for AI agent consumption)
- Exit 0: success
- Exit 1: error (message to stderr)
```

5. In "## Integration points", update `### session-start hook` to:
```markdown
### session-start hook

The hook no longer reads `_repo_index.json`. Instead, it injects a lazy loading
prompt that asks the AI to offer memory loading to the user. If the user accepts,
the AI uses `cortex-vec search --repo <name>` to retrieve relevant content.
```

6. Remove `_repo_index.json` references from the `### cortex:evolve skill` and `### cortex:distill skill` integration sections — remove the `cortex-vec export-repo-index` step from each.

- [ ] **Step 2: Commit**

```bash
git add docs/specs/2026-04-14-cortex-vec-design.md
git commit -m "docs(spec): align cortex-vec spec with refactored implementation"
```

---

## Task 10: Update README

**Files:**
- Edit: `README.md`

- [ ] **Step 1: Update README**

Apply the following changes to `README.md`:

1. Replace the design philosophy line:

Change from:
```markdown
**設計哲學：** 零外部依賴，純 markdown + JSON + git。
```

Change to:
```markdown
**設計哲學：** Vault 是 source of truth（純 markdown + git），vector store 是可重建的衍生索引。
```

2. Update the Architecture section. Add after the existing `~/.cortex/` block:

```markdown
~/.cortex/
├── config.json                ← genesis 產生的設定
├── distill-state.json         ← distill 處理狀態快取
└── vectorstore/               ← ChromaDB 語意索引（local only，不在 git）
```

3. Update Install section — add after `安裝後執行初始化：`:

```markdown
安裝 cortex-vec CLI：

```bash
pip install -e "$(claude plugin root cortex)/cortex-vec"
```

4. Update the Retrieval Strategy section:

Change from:
```markdown
## Retrieval Strategy

分層檢索，避免 token 浪費：

1. **_index.md**（快）— 每個檔案一行摘要 + tags，SessionStart 自動注入
2. **Notes/Projects**（中）— grep 搜尋精煉後的完整內容
3. **Raw/**（慢）— 只在追溯時查詢原始 session 記錄
```

Change to:
```markdown
## Retrieval Strategy

分層檢索，避免 token 浪費：

1. **Vector Search**（主要）— `cortex-vec search` 語意搜尋，ranked results
2. **Grep Fallback**（補充）— 精確字串搜尋 Notes/Projects
3. **Raw Search**（按需）— 只在追溯時查詢原始 session 記錄
```

5. Update the Hooks table:

Change the Memory Injection row from:
```markdown
| Memory Injection | SessionStart | 讀 `_index.md`，match 當前 repo，注入相關記憶到 context |
```

Change to:
```markdown
| Memory Injection | SessionStart | 偵測當前 repo，詢問使用者是否載入 cortex memory |
```

6. Update Data Flow:

Change from:
```markdown
每個 session:
  SessionStart → 注入相關記憶
```

Change to:
```markdown
每個 session:
  SessionStart → 提示有 memory 可用 → 使用者決定是否載入
```

7. Add a Dependencies section before License:

```markdown
## Dependencies

- Python 3.8+
- [ChromaDB](https://www.trychroma.com/) — 語意向量索引
- [python-frontmatter](https://python-frontmatter.readthedocs.io/) — YAML frontmatter 解析
- pysqlite3-binary — SQLite 3.35+ 相容（系統 SQLite 太舊時需要）

安裝：`pip install -e ./cortex-vec`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for cortex-vec package and lazy loading"
```

---

## Task 11: End-to-End Verification

- [ ] **Step 1: Verify cortex-vec status**

Run: `cortex-vec status`

Expected: Shows collection info with document count > 0.

- [ ] **Step 2: Verify cortex-vec rebuild**

Run: `cortex-vec rebuild`

Expected: `Rebuilt: N documents indexed` where N > 0.

- [ ] **Step 3: Verify cortex-vec search**

Run: `cortex-vec search "nginx certificate"`

Expected: JSON output with search results, scores between 0 and 1.

- [ ] **Step 4: Verify upsert stale cleanup works**

This is the critical bug fix. Test scenario:

Run:
```bash
# Check current entries for any file that has repo associations
cortex-vec search "certificate" --n 1
# Note the file path and repo from results
# Run upsert on a known file
cortex-vec upsert Notes/Nginx/Certificate.md
```

Expected: `Upserted: Notes/Nginx/Certificate.md` — no stale entries remain.

- [ ] **Step 5: Verify session-start hook**

Run: `echo '{"cwd":"/synosrc/misc/cortex"}' | bash hooks/scripts/session-start-inject.sh`

Expected: JSON with lazy loading prompt mentioning "cortex" as repo name.

- [ ] **Step 6: Verify old script is gone**

Run: `ls scripts/cortex-vec 2>&1`

Expected: `No such file or directory`

- [ ] **Step 7: Final commit if any fixes needed**

If any fixes were applied during verification, commit them:

```bash
git add -A
git commit -m "fix(cortex-vec): address issues found during verification"
```
