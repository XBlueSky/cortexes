# Search Quality Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve search quality by adding a LLM-generated bilingual summary vector per document and excluding Weekly from the index.

**Architecture:** Each document gets 2 ChromaDB entries: full body (existing) + LLM summary (new, bilingual). Search deduplicates results so each file appears once with the highest score. Weekly files are excluded from indexing.

**Tech Stack:** Python, ChromaDB, OpenAI (gpt-5-mini for summaries, text-embedding-3-small for embeddings)

---

## File Structure

```
cortex-vec/src/cortex_vec/
├── config.py       # MODIFY — add SUMMARY_MODEL constant
└── store.py        # MODIFY — add summary generation, dual-vector embed, search dedup, exclude Weekly
```

---

## Task 1: Add SUMMARY_MODEL constant

**Files:**
- Modify: `cortex-vec/src/cortex_vec/config.py`

- [ ] **Step 1: Add constant**

Add after line 9 (`COLLECTION_NAME = "cortex"`):

```python
SUMMARY_MODEL = "gpt-5-mini"
```

- [ ] **Step 2: Commit**

```bash
git add cortex-vec/src/cortex_vec/config.py
git commit -m "feat(cortex-vec): add SUMMARY_MODEL constant"
```

---

## Task 2: Add summary generation function

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`

- [ ] **Step 1: Add import**

At the top of `store.py`, add to the import from config (line 14):

Change from:
```python
from .config import COLLECTION_NAME, VECTORSTORE_DIR, get_vault_path
```

Change to:
```python
from .config import COLLECTION_NAME, SUMMARY_MODEL, VECTORSTORE_DIR, get_vault_path
```

- [ ] **Step 2: Add the summary prompt and function**

Add after the `_get_embedding_function()` function (after line 26):

```python
_SUMMARY_PROMPT = """Summarize this markdown note in 2-3 sentences, capturing the core knowledge.
Include both Chinese and English terms for key concepts.
End with "Keywords:" listing the most important terms in both languages.
Keep total output under 200 characters.

Title: {title}
Tags: {tags}
---
{body}"""


def _generate_summary(title, tags, body):
    """Generate a bilingual summary using LLM. Falls back to title+tags on failure."""
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": _SUMMARY_PROMPT.format(title=title, tags=tags, body=body[:3000]),
                }
            ],
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return f"{title}. Tags: {tags}"
```

- [ ] **Step 3: Verify function works**

Run:
```bash
cd /synosrc/misc/cortex && PYTHONPATH=cortex-vec/src python3 -c "
from cortex_vec.store import _generate_summary
result = _generate_summary('Certificate', 'nginx,dsm,security', 'DSM certificate architecture, synocrtregister, mkcert, self-signed cert tutorial with openssl.')
print(result)
print(f'Length: {len(result)}')
"
```

Expected: A bilingual summary under ~200 chars mentioning both Chinese and English terms.

- [ ] **Step 4: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): add bilingual summary generation via gpt-5-mini"
```

---

## Task 3: Modify rebuild to exclude Weekly and add summary vectors

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`

- [ ] **Step 1: Change scan_dirs in cmd_rebuild**

In `cmd_rebuild()` (line 116), change:

```python
    scan_dirs = ["Notes", "Projects", "Weekly"]
```

to:

```python
    scan_dirs = ["Notes", "Projects"]
```

- [ ] **Step 2: Add summary embedding after the repo loop**

In `cmd_rebuild()`, after the `for repo in repos:` loop that upserts full body entries (after line 158), add summary embedding. Replace the full `for scan_dir in scan_dirs:` loop body (lines 119-158) with:

```python
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

            # Generate bilingual summary
            summary_text = _generate_summary(title, tags, body)

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

                # Full body vector
                col.upsert(
                    ids=[doc_id],
                    documents=[embed_content],
                    metadatas=[metadata],
                )
                doc_count += 1

                # Summary vector
                summary_id = f"{doc_id}::summary"
                summary_metadata = {**metadata, "entry_type": "summary"}
                col.upsert(
                    ids=[summary_id],
                    documents=[summary_text],
                    metadatas=[summary_metadata],
                )
                doc_count += 1
```

- [ ] **Step 3: Verify rebuild works**

Run: `cortex-vec rebuild`

Expected: `Rebuilt: N documents indexed` where N is roughly double the old count (each doc gets 2 entries). Old count was 91 (with weekly). New count should be ~100 (50 note+project docs × 2 entries, plus multi-repo extras).

- [ ] **Step 4: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): dual-vector rebuild with summary, exclude Weekly"
```

---

## Task 4: Modify upsert to add summary vector

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`

- [ ] **Step 1: Add summary embedding to cmd_upsert**

In `cmd_upsert()`, after the line `embed_content = f"{title}\n\n{body}".strip()` (line 189), add summary generation:

```python
    embed_content = f"{title}\n\n{body}".strip()

    # Generate bilingual summary
    summary_text = _generate_summary(title, tags, body)
```

Then replace the `for repo in repos:` loop (lines 191-205) with:

```python
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

        # Full body vector
        col.upsert(
            ids=[doc_id],
            documents=[embed_content],
            metadatas=[metadata],
        )

        # Summary vector
        summary_id = f"{doc_id}::summary"
        summary_metadata = {**metadata, "entry_type": "summary"}
        col.upsert(
            ids=[summary_id],
            documents=[summary_text],
            metadatas=[summary_metadata],
        )
```

- [ ] **Step 2: Verify upsert works**

Run: `cortex-vec upsert Notes/Nginx/Certificate.md`

Expected: `Upserted: Notes/Nginx/Certificate.md`

- [ ] **Step 3: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): add summary vector to upsert"
```

---

## Task 5: Add search deduplication

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`

- [ ] **Step 1: Add _base_path helper**

Add after `_delete_stale_entries()` function (after line 85):

```python
def _base_path(doc_id):
    """Extract base file path from a doc ID, stripping ::repo and ::summary suffixes."""
    return doc_id.split("::")[0]
```

- [ ] **Step 2: Modify cmd_search to request more results and deduplicate**

Replace the entire `cmd_search()` function (lines 224-288) with:

```python
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

    # Request extra results to account for deduplication
    kwargs = {
        "query_texts": [query],
        "n_results": n * 3,
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

    # Deduplicate: keep highest score per base path
    seen = {}
    for doc, meta, dist in zip(docs, metas, dists):
        score = round(1 - dist, 4)
        source = meta.get("source_path", "")
        try:
            rel_id = str(Path(source).relative_to(vault))
        except (ValueError, TypeError):
            rel_id = source

        base = _base_path(rel_id)
        if base not in seen or score > seen[base]["score"]:
            seen[base] = {
                "id": base,
                "score": score,
                "title": meta.get("title", ""),
                "type": meta.get("type", ""),
                "repo": meta.get("repo", ""),
                "category": meta.get("category", ""),
                "tags": meta.get("tags", ""),
                "summary": extract_summary(doc),
            }

    # Sort by score descending and limit to n
    deduped = sorted(seen.values(), key=lambda x: -x["score"])[:n]

    for entry in deduped:
        print(json.dumps(entry, ensure_ascii=False))
```

- [ ] **Step 3: Verify search with the problematic query**

Run: `cortex-vec search "憑證怎麼設定" --n 5`

Expected: Certificate.md should now appear in results with a higher score (matched via the bilingual summary vector).

- [ ] **Step 4: Verify deduplication works**

Run: `cortex-vec search "nginx certificate" --n 5`

Expected: Each file appears only once (no duplicate entries from full body + summary).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): add search deduplication for multi-vector results"
```

---

## Task 6: Update status command

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`

- [ ] **Step 1: Update cmd_status to show entry breakdown**

Replace the `cmd_status()` function (lines 88-102) with:

```python
def cmd_status(_args):
    """Show index health."""
    vault = get_vault_path()
    client = get_client()
    try:
        col = client.get_collection(COLLECTION_NAME)
        total = col.count()
        all_metas = col.get(include=["metadatas"])["metadatas"]
        summaries = sum(1 for m in all_metas if m.get("entry_type") == "summary")
        bodies = total - summaries
    except Exception:
        total = 0
        bodies = 0
        summaries = 0

    print(f"Collection: {COLLECTION_NAME}")
    print(f"Entries:    {total} ({bodies} body + {summaries} summary)")
    print(f"Embedding:  {EMBEDDING_MODEL} (OpenAI)")
    print(f"Summary:    {SUMMARY_MODEL} (OpenAI)")
    print(f"DB path:    {VECTORSTORE_DIR}")
    print(f"Vault:      {vault}")
```

- [ ] **Step 2: Verify status output**

Run: `cortex-vec status`

Expected:
```
Collection: cortex
Entries:    ~100 (50 body + 50 summary)
Embedding:  text-embedding-3-small (OpenAI)
Summary:    gpt-5-mini (OpenAI)
DB path:    /root/.cortex/vectorstore
Vault:      /synosrc/cortex
```

- [ ] **Step 3: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py
git commit -m "feat(cortex-vec): show entry breakdown in status"
```

---

## Task 7: End-to-end verification

- [ ] **Step 1: Full rebuild**

Run: `cortex-vec rebuild`

Expected: Successful rebuild with roughly double the old entry count.

- [ ] **Step 2: Test the original failing query**

Run: `cortex-vec search "憑證怎麼設定" --n 5`

Expected: Certificate.md appears in results, ideally in top 3.

- [ ] **Step 3: Test English query still works**

Run: `cortex-vec search "certificate setup self-signed openssl" --n 3`

Expected: Certificate.md ranks #1.

- [ ] **Step 4: Test repo filter**

Run: `cortex-vec search "nginx config" --repo libsynow3 --n 3`

Expected: Only libsynow3-tagged results.

- [ ] **Step 5: Verify no Weekly entries**

Run:
```bash
cortex-vec search "weekly report" --type weekly --n 3 2>&1 || echo "Expected: no results or error"
```

Expected: No results (weekly is no longer indexed).

- [ ] **Step 6: Check status**

Run: `cortex-vec status`

Expected: Shows body + summary counts.

- [ ] **Step 7: Commit if any fixes needed**

```bash
git add -A
git commit -m "fix(cortex-vec): address issues found during verification"
```
