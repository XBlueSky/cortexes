# Cortex Vec & Skill Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a ChromaDB-backed vector store to the cortex plugin with a `cortex-vec` CLI, then update distill/query/evolve skills to use semantic search for dedup, retrieval, and classification.

**Architecture:** `cortex-vec` is a standalone Python CLI that wraps ChromaDB PersistentClient. All other components (hooks, skills) call it via bash. The vault stays as plain markdown (source of truth); the vector store is a derived, rebuildable index at `~/.cortex/vectorstore/`.

**Tech Stack:** Python 3.12, ChromaDB (with default all-MiniLM-L6-v2 embeddings), bash, jq

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/cortex-vec` (create) | Python CLI — rebuild, upsert, delete, search, export-repo-index, status |
| `scripts/build-repo-index.sh` (delete) | Replaced by `cortex-vec export-repo-index` |
| `skills/cortex-query/SKILL.md` (rewrite) | Vector-first search with grep fallback |
| `skills/cortex-distill/SKILL.md` (update) | Add value assessment criteria, dedup check, fix glob |
| `skills/cortex-evolve/SKILL.md` (update) | Add cortex-vec upsert + export after writing |
| `commands/distill.md` (update) | Add Bash to allowed-tools for cortex-vec calls |
| `commands/evolve.md` (update) | Add Bash to allowed-tools for cortex-vec calls |

---

### Task 1: Install ChromaDB

**Files:**
- None (system-level install)

- [ ] **Step 1: Install chromadb**

```bash
pip install chromadb
```

- [ ] **Step 2: Verify installation**

```bash
python3 -c "import chromadb; print(chromadb.__version__)"
```

Expected: Version number printed (e.g., `0.6.x`).

- [ ] **Step 3: Verify default embedding function works**

```bash
python3 -c "
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
ef = DefaultEmbeddingFunction()
result = ef(['hello world'])
print(f'Embedding dim: {len(result[0])}')
"
```

Expected: `Embedding dim: 384` (first run downloads ~80MB model).

---

### Task 2: Create `cortex-vec` CLI — core infrastructure

**Files:**
- Create: `/synosrc/misc/cortex/scripts/cortex-vec`

This task builds the CLI skeleton with `status` and `rebuild` subcommands.

- [ ] **Step 1: Create the CLI file with argument parsing and helpers**

Create `/synosrc/misc/cortex/scripts/cortex-vec`:

```python
#!/usr/bin/env python3
"""cortex-vec — Vector store CLI for the cortex vault.

Subcommands:
    rebuild             Full rebuild of vector store from vault
    upsert <path>       Add/update a single document
    delete <path>       Remove a document
    search <query>      Semantic search
    export-repo-index   Export _repo_index.json from vector store
    status              Show index health
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import chromadb

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CORTEX_CONFIG = Path.home() / ".cortex" / "config.json"
VECTORSTORE_DIR = Path.home() / ".cortex" / "vectorstore"
COLLECTION_NAME = "cortex"


def load_config():
    if not CORTEX_CONFIG.exists():
        print("Error: ~/.cortex/config.json not found. Run /cortex:genesis first.", file=sys.stderr)
        sys.exit(1)
    with open(CORTEX_CONFIG) as f:
        return json.load(f)


def get_vault_path():
    cfg = load_config()
    vault = cfg.get("vault_path", "")
    if not vault or not Path(vault).is_dir():
        print(f"Error: vault_path '{vault}' not found.", file=sys.stderr)
        sys.exit(1)
    return Path(vault)


def get_client():
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTORSTORE_DIR))


def get_collection(client):
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def parse_frontmatter(text):
    """Extract YAML frontmatter as a dict of strings. Handles tags/repos lists."""
    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return fm, text

    fm_text = m.group(1)
    body = text[m.end():]

    # Simple line-by-line parser for flat YAML
    current_key = None
    current_list = []

    for line in fm_text.splitlines():
        # List item (indented "- value")
        list_match = re.match(r"^\s+-\s+(.+)", line)
        if list_match and current_key:
            current_list.append(list_match.group(1).strip().strip("'\""))
            continue

        # Key: value
        kv_match = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if kv_match:
            # Save previous list key
            if current_key and current_list:
                fm[current_key] = ",".join(current_list)
                current_list = []

            key = kv_match.group(1)
            val = kv_match.group(2).strip().strip("'\"")

            # Inline list: [a, b, c]
            inline_match = re.match(r"\[([^\]]*)\]", val)
            if inline_match:
                items = [x.strip().strip("'\"") for x in inline_match.group(1).split(",") if x.strip()]
                fm[key] = ",".join(items)
                current_key = None
            elif val:
                fm[key] = val
                current_key = None
            else:
                # Empty value — might be start of a list
                current_key = key
                current_list = []
            continue

    # Final list key
    if current_key and current_list:
        fm[current_key] = ",".join(current_list)

    return fm, body


def extract_summary(body, max_len=120):
    """Extract first non-empty, non-heading line from body."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip callout prefixes
        stripped = re.sub(r"^>\s*(\[![a-zA-Z]+\])?\s*", "", stripped)
        if stripped:
            return stripped[:max_len]
    return ""


def classify_path(rel_path):
    """Determine type and category from relative path."""
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


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_status(args):
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


def cmd_rebuild(args):
    vault = get_vault_path()
    client = get_client()

    # Delete existing collection
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

            # Skip archive
            if "_archive" in rel_path:
                continue

            text = md_file.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_frontmatter(text)

            doc_type, category = classify_path(rel_path)
            title = fm.get("title", md_file.stem)
            status = fm.get("status", "")
            tags = fm.get("tags", "")
            repos_str = fm.get("repos", "")

            # Determine repo list
            repos = []
            if doc_type == "project" and category:
                repos.append(category)
            if repos_str:
                for r in repos_str.split(","):
                    r = r.strip()
                    if r and r not in repos:
                        repos.append(r)

            # Content to embed: title + body (skip raw frontmatter)
            embed_content = f"{title}\n\n{body}".strip()
            if not embed_content:
                continue

            # Insert once per repo (or once with empty repo if no repo)
            if not repos:
                repos = [""]

            for repo in repos:
                doc_id = rel_path if not repo or len(repos) == 1 else f"{rel_path}::{repo}"
                metadata = {
                    "type": doc_type,
                    "category": category,
                    "title": title,
                    "tags": tags,
                    "source_path": str(md_file),
                }
                if repo:
                    metadata["repo"] = repo
                if repos_str:
                    metadata["repos"] = repos_str
                if status:
                    metadata["status"] = status

                col.upsert(
                    ids=[doc_id],
                    documents=[embed_content],
                    metadatas=[metadata],
                )
                doc_count += 1

    print(f"Rebuilt: {doc_count} documents indexed")

    # Auto export repo index
    _export_repo_index(vault, col)


def cmd_upsert(args):
    vault = get_vault_path()
    rel_path = args.path
    full_path = vault / rel_path

    if not full_path.exists():
        print(f"Error: {full_path} not found.", file=sys.stderr)
        sys.exit(1)

    client = get_client()
    col = get_collection(client)

    text = full_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)

    doc_type, category = classify_path(rel_path)
    title = fm.get("title", full_path.stem)
    status = fm.get("status", "")
    tags = fm.get("tags", "")
    repos_str = fm.get("repos", "")

    repos = []
    if doc_type == "project" and category:
        repos.append(category)
    if repos_str:
        for r in repos_str.split(","):
            r = r.strip()
            if r and r not in repos:
                repos.append(r)

    embed_content = f"{title}\n\n{body}".strip()
    if not repos:
        repos = [""]

    for repo in repos:
        doc_id = rel_path if not repo or len(repos) == 1 else f"{rel_path}::{repo}"
        metadata = {
            "type": doc_type,
            "category": category,
            "title": title,
            "tags": tags,
            "source_path": str(full_path),
        }
        if repo:
            metadata["repo"] = repo
        if repos_str:
            metadata["repos"] = repos_str
        if status:
            metadata["status"] = status

        col.upsert(
            ids=[doc_id],
            documents=[embed_content],
            metadatas=[metadata],
        )

    print(f"Upserted: {rel_path}")


def cmd_delete(args):
    client = get_client()
    col = get_collection(client)
    rel_path = args.path

    # Delete all IDs that start with this path (handles ::repo suffixes)
    all_ids = col.get(include=[])["ids"]
    to_delete = [i for i in all_ids if i == rel_path or i.startswith(f"{rel_path}::")]

    if not to_delete:
        print(f"Not found: {rel_path}", file=sys.stderr)
        sys.exit(1)

    col.delete(ids=to_delete)
    print(f"Deleted: {len(to_delete)} entries for {rel_path}")


def cmd_search(args):
    client = get_client()
    col = get_collection(client)
    vault = get_vault_path()

    query = args.query
    n = args.n or 5

    # Build where filter
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
        # Get relative path from source_path
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


def _export_repo_index(vault, col):
    """Export _repo_index.json from vector store metadata."""
    all_data = col.get(include=["metadatas"])
    ids = all_data["ids"]
    metas = all_data["metadatas"]

    index = {}
    for doc_id, meta in zip(ids, metas):
        repo = meta.get("repo", "")
        if not repo:
            continue

        doc_type = meta.get("type", "")
        # Get the base path (strip ::repo suffix)
        base_path = doc_id.split("::")[0]

        if repo not in index:
            index[repo] = {"projects": [], "notes": []}

        bucket = "projects" if doc_type == "project" else "notes"
        if base_path not in index[repo][bucket]:
            index[repo][bucket].append(base_path)

    # Sort for deterministic output
    for repo in index:
        index[repo]["projects"].sort()
        index[repo]["notes"].sort()

    output_path = vault / "_repo_index.json"
    with open(output_path, "w") as f:
        json.dump(dict(sorted(index.items())), f, indent=2, ensure_ascii=False)

    print(f"Exported: {len(index)} repos to _repo_index.json")


def cmd_export_repo_index(args):
    vault = get_vault_path()
    client = get_client()
    col = get_collection(client)
    _export_repo_index(vault, col)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="cortex-vec — Vector store CLI for cortex vault")
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
    p_search.add_argument("--tags", help="Filter by tags")
    p_search.add_argument("--n", type=int, default=5, help="Number of results")

    sub.add_parser("export-repo-index", help="Export _repo_index.json")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "rebuild": cmd_rebuild,
        "upsert": cmd_upsert,
        "delete": cmd_delete,
        "search": cmd_search,
        "export-repo-index": cmd_export_repo_index,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x /synosrc/misc/cortex/scripts/cortex-vec
```

- [ ] **Step 3: Test status (empty store)**

```bash
/synosrc/misc/cortex/scripts/cortex-vec status
```

Expected:
```
Collection: cortex
Documents:  0
Model:      all-MiniLM-L6-v2 (default)
DB path:    /root/.cortex/vectorstore
Vault:      /synosrc/cortex
```

- [ ] **Step 4: Test rebuild**

```bash
/synosrc/misc/cortex/scripts/cortex-vec rebuild
```

Expected: `Rebuilt: N documents indexed` (N should be ~90+) followed by `Exported: M repos to _repo_index.json`.

- [ ] **Step 5: Test search**

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "nginx certificate 設定"
```

Expected: JSON lines with Certificate.md, check site server.md, etc. ranked by score.

- [ ] **Step 6: Test search with repo filter**

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "config" --repo libsynow3
```

Expected: Only results with `"repo": "libsynow3"`.

- [ ] **Step 7: Test upsert**

```bash
/synosrc/misc/cortex/scripts/cortex-vec upsert "Notes/Nginx/Nginx.md"
```

Expected: `Upserted: Notes/Nginx/Nginx.md`

- [ ] **Step 8: Test export-repo-index**

```bash
/synosrc/misc/cortex/scripts/cortex-vec export-repo-index
cat /synosrc/cortex/_repo_index.json | jq 'keys'
```

Expected: Same repo keys as before (`dsm-AdminCenter`, `libsynosharing`, `libsynosysnotify`, `libsynow3`, `synooauth.synology.com`, `webapi-Notification`).

- [ ] **Step 9: Test status (populated)**

```bash
/synosrc/misc/cortex/scripts/cortex-vec status
```

Expected: `Documents: N` (matching rebuild count).

- [ ] **Step 10: Commit**

```bash
cd /synosrc/misc/cortex
git add scripts/cortex-vec
git commit -m "feat(scripts): add cortex-vec CLI with ChromaDB vector store"
```

---

### Task 3: Remove `build-repo-index.sh`

**Files:**
- Delete: `/synosrc/misc/cortex/scripts/build-repo-index.sh`

- [ ] **Step 1: Verify export-repo-index produces equivalent output**

```bash
# Save current index
cp /synosrc/cortex/_repo_index.json /tmp/old-index.json

# Rebuild and export via cortex-vec
/synosrc/misc/cortex/scripts/cortex-vec rebuild

# Compare keys
diff <(jq 'keys' /tmp/old-index.json) <(jq 'keys' /synosrc/cortex/_repo_index.json)
```

Expected: No differences (or only ordering changes).

- [ ] **Step 2: Delete old script**

```bash
rm /synosrc/misc/cortex/scripts/build-repo-index.sh
```

- [ ] **Step 3: Commit**

```bash
cd /synosrc/misc/cortex
git add -A scripts/
git commit -m "chore(scripts): remove build-repo-index.sh, replaced by cortex-vec export-repo-index"
```

---

### Task 4: Update `cortex-evolve` skill

**Files:**
- Modify: `/synosrc/misc/cortex/skills/cortex-evolve/SKILL.md`
- Modify: `/synosrc/misc/cortex/commands/evolve.md`

- [ ] **Step 1: Add vector store update steps to evolve skill**

In `skills/cortex-evolve/SKILL.md`, add a new section after the existing `## Commit` section:

```markdown
## Update Vector Store

After committing the new file to the vault:

1. Run: `cortex-vec upsert <relative-path-from-vault>`
2. Run: `cortex-vec export-repo-index`

Where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`.
```

- [ ] **Step 2: Verify evolve command has Bash in allowed-tools**

Read `commands/evolve.md` — it already has `Bash` in `allowed-tools`. No change needed.

- [ ] **Step 3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-evolve/SKILL.md
git commit -m "feat(evolve): add cortex-vec upsert after writing to vault"
```

---

### Task 5: Update `cortex-distill` skill

**Files:**
- Modify: `/synosrc/misc/cortex/skills/cortex-distill/SKILL.md`

- [ ] **Step 1: Rewrite the distill skill**

Replace the entire content of `skills/cortex-distill/SKILL.md` with:

```markdown
---
name: cortex-distill
description: >
  Distill raw session records into refined Notes and Projects. Use when
  the user says "提煉", "整理 raw", "distill", "distill raw records",
  or when cortex-weekly invokes distill before compiling.
---

# Cortex Distill — Refine Raw Records

Extract valuable knowledge from Raw/ session dumps into Notes/ and Projects/.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Step 1: Find Unprocessed Raw Files

1. Read `~/.cortex/distill-state.json` (local cache)
2. Find all `.md` files recursively under `<vault_path>/Raw/`:
   ```bash
   find <vault_path>/Raw -name "*.md" -type f
   ```
3. For each file:
   - In distill-state.json → skip (fast path)
   - Not in distill-state.json → read file, grep `<!-- distilled:`
     - Has marker → already processed, add to distill-state.json
     - No marker → unprocessed, add to pending list
4. Show user the pending list count and ask to proceed

## Step 2: Assess Value

For each unprocessed Raw file:

1. Read the full content
2. Check if it has `## Discoveries` or `## Decisions` sections with content
   - No such sections → **skip** (mark as processed with no extractable content)
   - Has sections → apply the three-filter criteria

### Three-Filter Criteria

| Category | What to look for | Example |
|----------|-----------------|---------|
| **踩坑知識 (Gotchas)** | Non-obvious behavior, hidden traps, root causes | "jsoncpp returns null for oversized doubles instead of throwing" |
| **內部慣例 (Internal conventions)** | Synology-specific practices, internal API quirks | "subdomain: Drive uses AppPortal.json, MailClient uses API" |
| **關鍵決策 (Key decisions)** | Why A over B, trade-offs, decisions that will be forgotten | "Use build-history.json vs PID check because..." |

- Matches any criterion → **extract** (proceed to Step 3)
- Matches none → **skip** (routine knowledge already in code/commits)

### What to skip (not worth extracting)

- Routine commits (fix is in the code, commit message has context)
- General programming knowledge (Google-able)
- Tool/plugin configuration (changes frequently, in config files)
- Records that only say "what was done" without insight

## Step 3: Deduplication Check

Before creating a new note:

1. Run: `cortex-vec search "<discovery text>" --n 3`
   (where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`)
2. Check results:
   - **Score > 0.85** → High overlap. Show existing note. Suggest: merge, skip, or create anyway.
   - **Score 0.70-0.85** → Possible overlap. Show to user for judgment.
   - **Score < 0.70** → New knowledge. Proceed to create.

## Step 4: Create Refined Note

1. Draft the refined content
2. Determine placement:
   - Repo-specific knowledge → `Projects/<repo>/` (repo from Raw file's `repo:` frontmatter)
   - General technical knowledge → `Notes/<category>/` (match existing categories)
3. Add `repos:` to frontmatter if repo-specific
4. Present draft to user for confirmation
5. Write to vault using Obsidian Flavored Markdown (wikilinks, frontmatter, callouts)

## Step 5: Mark as Processed

1. Append marker to Raw file:
   ```
   <!-- distilled: YYYY-MM-DD → Notes/path.md -->
   ```
   or if skipped:
   ```
   <!-- distilled: YYYY-MM-DD → (no extractable content) -->
   ```
2. Update `~/.cortex/distill-state.json`

## Step 6: Update Index

For each new file created:

1. Run: `cortex-vec upsert <relative-path>`
2. Run: `cortex-vec export-repo-index`
3. Update `_index.md`: append row, update entries count and date

## Step 7: Commit

```
git add Raw/ Notes/ Projects/ _index.md _repo_index.json
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`
```

- [ ] **Step 2: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git commit -m "feat(distill): add value assessment, dedup check, fix nested glob"
```

---

### Task 6: Rewrite `cortex-query` skill

**Files:**
- Modify: `/synosrc/misc/cortex/skills/cortex-query/SKILL.md`

- [ ] **Step 1: Rewrite the query skill**

Replace the entire content of `skills/cortex-query/SKILL.md` with:

```markdown
---
name: cortex-query
description: >
  Search and retrieve content from the cortex vault. Use when the user says
  "查 cortex", "之前有記過", "cortex 裡有沒有", "check my notes",
  "what did I write about", or needs to find previously saved knowledge.
---

# Cortex Query — Search the Vault

Search the cortex Obsidian vault using semantic search.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Search Strategy (Layered)

### Layer 1: Vector Search (primary)

Use `cortex-vec` for semantic search:

```bash
cortex-vec search "<query>" --n 5
```

Where `cortex-vec` is at `${CLAUDE_PLUGIN_ROOT}/scripts/cortex-vec`.

**Context-aware filtering:** If the current session is inside a git repo,
detect the repo name and add `--repo` filter as default scope:

```bash
cortex-vec search "<query>" --repo <detected-repo> --n 5
```

The user can override this by saying "search all" or "search across everything".

**Additional filters:** Apply when the user specifies:
- `--type note|project|weekly` — filter by content type
- `--category Nginx|DSM|...` — filter by category
- `--tags <tag>` — filter by tags

**Interpreting scores:**
- Score > 0.80: High confidence match — present prominently
- Score 0.60-0.80: Possible match — present as suggestions
- Score < 0.60: Weak match — mention only if nothing better found

### Layer 2: Exact Match (supplement)

If Layer 1 returns no strong results (all scores < 0.60), or if the user
is searching for an exact string (command, config path, error message):

```bash
grep -ri "<query>" <vault_path>/Notes/ <vault_path>/Projects/
```

Show matching files with brief excerpts.

### Layer 3: Raw Search (archive, on request)

Only when the user specifically asks about recent sessions or raw data:

```bash
grep -ri "<query>" <vault_path>/Raw/
```

Show matches with date and repo context.

## Response Format

Present results to the user:

```
Found N results for "<query>":

1. [score] Title (Type, Category/Repo)
   → one-line summary

2. [score] Title (Type, Category/Repo)
   → one-line summary
```

- Use wikilink format when referencing notes: `[[note-name]]`
- If multiple matches, list them and ask which one to read
- If user wants details → read the full file
- For Weekly entries, show the date and summary line
```

- [ ] **Step 2: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-query/SKILL.md
git commit -m "feat(query): rewrite with vector-first search and grep fallback"
```

---

### Task 7: End-to-end verification

- [ ] **Step 1: Verify full rebuild + export**

```bash
/synosrc/misc/cortex/scripts/cortex-vec rebuild
```

Expected: Documents indexed count and repo export.

- [ ] **Step 2: Test semantic search — synonym matching**

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "nginx 設定檔路徑"
```

Expected: `Nginx.md` and/or `Service config.md` should appear with high scores, even though the exact phrase "設定檔路徑" doesn't appear in them.

- [ ] **Step 3: Test semantic search — cross-language**

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "certificate setup tutorial"
```

Expected: `Certificate.md` should rank high.

- [ ] **Step 4: Test repo filter accuracy**

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "config" --repo libsynow3 --n 3
```

Expected: Only results associated with `libsynow3`.

```bash
/synosrc/misc/cortex/scripts/cortex-vec search "config" --repo libsynosharing --n 3
```

Expected: Only sharing-related results.

- [ ] **Step 5: Test session-start hook still works**

```bash
echo '{"cwd":"/synosrc/curr/ds.base/source/libsynow3"}' | bash /synosrc/misc/cortex/hooks/scripts/session-start-inject.sh
```

Expected: Same output as before (hook reads `_repo_index.json` which was re-exported by rebuild).

- [ ] **Step 6: Test upsert + search round-trip**

Create a temporary test file:
```bash
cat > /tmp/test-note.md << 'EOF'
---
title: Test Note
tags:
  - test
repos:
  - testrepo
---

This is a test note about FSDN volume switchover procedures.
EOF
cp /tmp/test-note.md /synosrc/cortex/Notes/DSM/test-note.md
/synosrc/misc/cortex/scripts/cortex-vec upsert "Notes/DSM/test-note.md"
/synosrc/misc/cortex/scripts/cortex-vec search "volume switchover" --n 1
```

Expected: `test-note.md` appears in results.

Clean up:
```bash
rm /synosrc/cortex/Notes/DSM/test-note.md
/synosrc/misc/cortex/scripts/cortex-vec delete "Notes/DSM/test-note.md"
```

- [ ] **Step 7: Verify cortex-vec status**

```bash
/synosrc/misc/cortex/scripts/cortex-vec status
```

Expected: Accurate document count, correct paths.
