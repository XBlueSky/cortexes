"""Eval runner: run adapters over a query set, score, aggregate, render."""
import json
import sys
import time
from pathlib import Path

from .. import store
from ..config import get_vault_path
from ..parser import classify_path, parse_document
from . import adapters, corpus, report, score


def _load_corpus_docs():
    """Build adapter corpus docs from vault Notes/ + Projects/ (skip _archive)."""
    vault = get_vault_path()
    docs = []
    for scan_dir in ("Notes", "Projects"):
        base = vault / scan_dir
        if not base.is_dir():
            continue
        for md in base.rglob("*.md"):
            rel = str(md.relative_to(vault))
            if "_archive" in rel:
                continue
            fm, body = parse_document(md.read_text(encoding="utf-8", errors="replace"))
            docs.append(store.bm25_doc_from_fields(rel, fm, body))
    return docs


def run_adapter(adapter, queries, k):
    """Run one initialized adapter over all queries; return per-query score rows."""
    rows = []
    for q in queries:
        t0 = time.perf_counter()
        ranked = [doc_id for doc_id, _ in adapter.query(q["query"], k)]
        latency_ms = (time.perf_counter() - t0) * 1000.0
        sc = score.score_query(ranked, set(q["gold"]), k)
        rows.append({
            "query_id": q["id"],
            "adapter": adapter.name,
            "type": q["type"],
            "latency_ms": latency_ms,
            **sc,
        })
    return rows


def dispatch(args):
    if args.action == "propose":
        _propose(args)
        return
    _run(args)


def _run(args):
    queries = corpus.load_queries(Path(args.queries))
    docs = _load_corpus_docs()
    existing = {d["id"] for d in docs}
    missing = corpus.check_gold_paths(queries, existing)
    if missing:
        print(f"WARNING: gold paths missing from vault: {missing}", file=sys.stderr)

    all_rows = []
    for name in [a.strip() for a in args.adapters.split(",") if a.strip()]:
        cls = adapters.REGISTRY.get(name)
        if cls is None:
            print(f"Unknown adapter: {name}", file=sys.stderr)
            continue
        adapter = cls()
        adapter.init(docs)
        all_rows.extend(run_adapter(adapter, queries, args.k))
        adapter.teardown()

    for row in all_rows:
        print(json.dumps(row, ensure_ascii=False))

    summary = score.aggregate(all_rows)
    meta = {"corpus": Path(args.queries).stem, "k": args.k, "n": len(queries)}
    md = report.render(summary, meta)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Scorecard written to {args.out}", file=sys.stderr)
    else:
        print(md, file=sys.stderr)


def _propose(args):
    """Use OpenAI to propose candidate queries from notes for the user to confirm.

    Writes JSONL with gold pre-filled to the note path; the user edits/confirms.
    """
    from openai import OpenAI

    from ..config import SUMMARY_MODEL

    docs = _load_corpus_docs()
    client = OpenAI()
    out_path = Path(args.queries)
    proposed = []
    for d in docs:
        prompt = (
            "根據以下技術筆記，生成 1 個使用者最可能用來查到這篇筆記的搜尋 query"
            "（中英混合，貼近真實工程查詢，10 字內）。只輸出 query 文字。\n\n"
            f"標題：{d['title']}\n摘要：{d['summary']}"
        )
        try:
            resp = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=40,
                reasoning_effort="none",
            )
            query = resp.choices[0].message.content.strip()
        except Exception as e:  # noqa: BLE001
            print(f"propose failed for {d['id']}: {e}", file=sys.stderr)
            continue
        proposed.append({
            "id": f"q-{len(proposed) + 1:03d}",
            "query": query,
            "gold": [d["id"]],
            "type": "single-note",
            "note": "AUTO-PROPOSED — review query + gold before use",
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in proposed), encoding="utf-8"
    )
    print(f"Proposed {len(proposed)} queries to {out_path} — review before running eval",
          file=sys.stderr)
