"""ChromaDB vector store operations."""

# pysqlite3 patch: system SQLite (3.22) is too old for ChromaDB (needs >= 3.35)
__import__("pysqlite3")
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import os

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from .bm25 import BM25Index
from .config import BM25_DIR, COLLECTION_NAME, SUMMARY_MODEL, VECTORSTORE_DIR, get_vault_path
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

    try:
        bm25_index = BM25Index(BM25_DIR)
        bm25_index.load()
        bm25_count = bm25_index.count()
    except Exception:
        bm25_count = 0
    print(f"BM25:       {bm25_count} notes")
    if total and not bm25_count:
        print("  WARNING: BM25 index empty — run rebuild", file=sys.stderr)
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Entries:    {total} ({bodies} body + {summaries} summary)")
    print(f"Embedding:  {EMBEDDING_MODEL} (OpenAI)")
    print(f"Summary:    {SUMMARY_MODEL} (OpenAI)")
    print(f"DB path:    {VECTORSTORE_DIR}")
    print(f"Vault:      {vault}")


def _build_bm25_from_vault(vault):
    """Build the BM25 index from all Notes/ + Projects/ notes (skip _archive).

    Returns the note count. Does NOT touch ChromaDB or call any embedding API —
    safe and free to run when only the BM25 index is stale.
    """
    bm25_docs = []
    for scan_dir in ("Notes", "Projects"):
        scan_path = vault / scan_dir
        if not scan_path.is_dir():
            continue
        for md_file in scan_path.rglob("*.md"):
            rel_path = str(md_file.relative_to(vault))
            if "_archive" in rel_path:
                continue
            text = md_file.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_document(text)
            bm25_docs.append(bm25_doc_from_fields(rel_path, fm, body))
    bm25_index = BM25Index(BM25_DIR)
    bm25_index.build_from_docs(bm25_docs)
    bm25_index.save()
    return bm25_index.count()


def cmd_rebuild(args):
    """Rebuild from vault. `--bm25-only` rebuilds just the BM25 index (no re-embed)."""
    vault = get_vault_path()

    if getattr(args, "bm25_only", False):
        count = _build_bm25_from_vault(vault)
        print(f"BM25: {count} notes indexed (vector store untouched)")
        return

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

    bm25_count = _build_bm25_from_vault(vault)
    print(f"BM25: {bm25_count} notes indexed")
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

    bm25_index = BM25Index(BM25_DIR)
    try:
        bm25_index.load()
    except FileNotFoundError:
        bm25_index.build_from_docs([])
    bm25_index.upsert(bm25_doc_from_fields(rel_path, fm, body))
    bm25_index.save()
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

    bm25_index = BM25Index(BM25_DIR)
    try:
        bm25_index.load()
        bm25_index.delete(rel_path)
        bm25_index.save()
    except FileNotFoundError:
        pass

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


def bm25_doc_from_fields(rel_path, fm, body):
    """Build a BM25 doc record dict from a parsed note."""
    doc_type, category = classify_path(rel_path)
    repos_str = fm.get("repos", "")
    repos = [r.strip() for r in repos_str.split(",") if r.strip()] if repos_str else []
    if doc_type == "project" and category and category not in repos:
        repos.insert(0, category)
    return {
        "id": rel_path,
        "title": fm.get("title", rel_path.rsplit("/", 1)[-1].removesuffix(".md")),
        "body": body,
        "summary": extract_summary(body),
        "tags": fm.get("tags", ""),
        "repos": repos,
        "type": doc_type,
        "category": category,
    }


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
    """Hybrid search across the vault (vector + BM25, RRF-fused)."""
    import json

    from . import fusion

    where = _build_where(
        repo=getattr(args, "repo", None),
        type=getattr(args, "type", None),
        category=getattr(args, "category", None),
    )
    results = fusion.search(
        args.query,
        n=args.n or 5,
        where=where,
        use_bm25=not getattr(args, "no_bm25", False),
        use_vector=not getattr(args, "no_vector", False),
        rerank=getattr(args, "rerank", False) or None,
        graph=getattr(args, "graph", False) or None,
    )
    for entry in results:
        print(json.dumps(entry, ensure_ascii=False))
