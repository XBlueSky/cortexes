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
