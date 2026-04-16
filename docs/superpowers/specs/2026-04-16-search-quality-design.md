# Search Quality Improvement — Multi-Representation Embedding

**Date:** 2026-04-16
**Status:** Approved
**Depends on:** cortex-vec refactor (2026-04-15, completed)

## Problem

`cortex-vec search "憑證怎麼設定"` fails to find Certificate.md (score < 0.30, not in top 10) because:

1. **Cross-language mismatch** — Chinese query vs English document content. Even with OpenAI's multilingual embedding, cosine similarity across languages is inherently lower.
2. **Long document dilution** — A 2730-char document with code blocks, tables, and paths dilutes the semantic signal of its core concepts into a single embedding vector.

Evidence:

| Query | Certificate.md Score | Rank |
|-------|:---:|:---:|
| `憑證怎麼設定` (Chinese) | not in top 10 | — |
| `certificate` (English keyword) | 0.29 | #2 |
| `SSL 憑證 nginx` (mixed) | 0.41 | #4 |
| `certificate setup self-signed openssl` (English detailed) | 0.46 | #1 |

## Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Strategy | Multi-representation embedding (2 vectors per doc) | Directly solves cross-language + dilution. Simpler than hybrid search. |
| Summary LLM | gpt-5-mini | Cheap, fast, good Chinese/English quality |
| Weekly indexing | Exclude from vector store | Only note + project are useful for retrieval |
| BM25 hybrid | Not now | Layer 2 grep fallback already covers exact-match. YAGNI. |
| Cost concern | None at 200-1000 doc scale | Rebuild ~$0.01-0.15 |

## Design

### Dual-Vector Embedding

Each document gets 2 entries in ChromaDB:

**1. Full body** (existing behavior):
```
ID:       "Notes/Nginx/Certificate.md"
Document: "Certificate\n\n# Certificate\n\n## Architecture..."
```

**2. LLM summary** (new):
```
ID:       "Notes/Nginx/Certificate.md::summary"
Document: "DSM 憑證架構：service config 位於 /usr/syno/share/certificate.d/，
           用 synocrtregister 動態註冊。mkcert 在 nginx pre-start 時自動產生憑證。
           包含 self-signed certificate 教學。
           Keywords: 憑證, certificate, SSL, nginx, openssl, 自簽憑證, mkcert, DSM"
```

### ID Convention

| Entry type | ID format | Example |
|-----------|---------|---------|
| Full body | `<path>` | `Notes/Nginx/Certificate.md` |
| Full body (multi-repo) | `<path>::<repo>` | `Notes/Nginx/Certificate.md::libsynow3` |
| Summary | `<path>::summary` | `Notes/Nginx/Certificate.md::summary` |
| Summary (multi-repo) | `<path>::<repo>::summary` | `Notes/Nginx/Certificate.md::libsynow3::summary` |

### Summary Generation

**Model:** gpt-5-mini

**Prompt:**
```
Summarize this markdown note in 2-3 sentences, capturing the core knowledge.
Include both Chinese and English terms for key concepts.
End with "Keywords:" listing the most important terms in both languages.
Keep total output under 200 characters.

Title: {title}
Tags: {tags}
---
{body}
```

**Fallback:** If API call fails, use `f"{title}. Tags: {tags}"` instead.

### Search Deduplication

Search results may return both full body and summary for the same file. Dedup logic:

```python
def _base_path(doc_id):
    return doc_id.split("::")[0]

# Group by base_path, keep highest score per file
seen = {}
for result in results:
    base = _base_path(result.id)
    if base not in seen or result.score > seen[base].score:
        seen[base] = result
```

### Weekly Exclusion

`cmd_rebuild` scan_dirs changes from `["Notes", "Projects", "Weekly"]` to `["Notes", "Projects"]`.

### Stale Cleanup Compatibility

`_delete_stale_entries` already uses `startswith(f"{rel_path}::")` prefix matching, so `::summary` entries are automatically cleaned up during upsert/delete. No changes needed.

## Files Changed

| File | Change |
|------|--------|
| `cortex-vec/src/cortex_vec/store.py` | Add `_generate_summary()`, dual-vector in rebuild/upsert, dedup in search, exclude Weekly |
| `cortex-vec/src/cortex_vec/config.py` | Add `SUMMARY_MODEL` constant |
| `docs/specs/2026-04-14-cortex-vec-design.md` | Update embedding strategy docs |

### Not changed

- `cli.py` — interface unchanged
- `parser.py` — parsing logic unchanged
- `pyproject.toml` — `openai` already a dependency
- `session-start-inject.sh` — unrelated
- Skills — `cortex-vec search` interface unchanged
