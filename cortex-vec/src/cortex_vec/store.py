"""ChromaDB vector store operations."""

# pysqlite3 patch: system SQLite (3.22) is too old for ChromaDB (needs >= 3.35)
__import__("pysqlite3")
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import os

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from .config import COLLECTION_NAME, SUMMARY_MODEL, VECTORSTORE_DIR, get_vault_path
from .parser import classify_path, extract_summary, parse_document

EMBEDDING_MODEL = "text-embedding-3-small"


def _get_embedding_function():
    """Return OpenAI embedding function."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    return OpenAIEmbeddingFunction(model_name=EMBEDDING_MODEL, api_key=api_key)


_SUMMARY_PROMPT = """為這份技術筆記產生摘要，用於語意搜尋索引。

規則：
1. 用繁體中文寫 2-3 句摘要，描述核心知識
2. 重要概念同時列出中英文（例如：憑證 certificate）
3. 最後加「關鍵詞：」列出中英文關鍵詞
4. 總長度不超過 300 字

標題：{title}
標籤：{tags}
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
            max_completion_tokens=400,
            reasoning_effort="none",
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return f"{title}. Tags: {tags}"


def get_client():
    """Return a persistent ChromaDB client."""
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTORSTORE_DIR))


def get_collection(client):
    """Get or create the cortex collection."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
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


def _base_path(doc_id):
    """Extract base file path from a doc ID, stripping ::repo and ::summary suffixes."""
    return doc_id.split("::")[0]


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


def cmd_rebuild(_args):
    """Full rebuild of vector store from vault."""
    vault = get_vault_path()
    client = get_client()

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    col = get_collection(client)
    scan_dirs = ["Notes", "Projects"]
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


def _build_where(repo=None, type=None, category=None):
    clauses = []
    if repo:
        clauses.append({"repo": repo})
    if type:
        clauses.append({"type": type})
    if category:
        clauses.append({"category": category})
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) > 1:
        return {"$and": clauses}
    return None


def vector_stream(query, n, where=None):
    """Vector retrieval stream: dedup by base path, return display dicts sorted desc.

    Returns the full deduped list (not sliced to n) so the fusion layer can rank it.
    """
    from pathlib import Path

    client = get_client()
    col = get_collection(client)
    vault = get_vault_path()

    kwargs = {
        "query_texts": [query],
        "n_results": n * 3,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

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
    return sorted(seen.values(), key=lambda x: -x["score"])


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
