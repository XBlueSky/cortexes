#!/usr/bin/env python3
"""Mechanical map-first corpus validation. Aggregate-only output.

Runs the partition parser + simulated map/span paging over every pending
Raw plus the N largest Raws in the vault. No semantic classification, no
Raw content in the report."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "cortex-vec" / "src"))

from cortex_vec import distill_queue as dq          # noqa: E402
from cortex_vec import raw_map as rm                # noqa: E402
from cortex_vec import raw_page as rp               # noqa: E402
from cortex_vec import raw_source as rs             # noqa: E402

PAGE = rp.PAGE_BUDGET_DEFAULT


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1) + 0.5))
    return sorted_vals[i]


def simulate(path):
    ident, text = rs.load(path)
    spans = rs.parse(text)  # raises PartitionError on invariant break
    map_chars = 0
    page = 0
    for s in spans:
        card = len(rp.render_page(rm.build_card(s, text))) + 2
        if page + card > PAGE - 400:  # 400 ~ envelope overhead
            map_chars += page + 400
            page = 0
        page += card
    map_chars += page + 400 if page else 0
    span_chars = sum(
        s.char_end - s.char_start + 600  # per-page envelope amortized
        for s in spans
        if s.kind in rs.SPAN_REVIEW_KINDS or s.kind in rs.PREVIEW_REVIEW_KINDS)
    amb = [s for s in spans if s.kind in ("ambiguous", "opaque")]
    return {
        "chars": ident.char_count,
        "spans": len(spans),
        "ambiguous_spans": len(amb),
        "map_chars": map_chars,
        "full_review_chars": map_chars + span_chars,
    }


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if root is None:
        from cortex_vec.config import get_vault_path
        root = get_vault_path() / "Raw"
    pending = dq.distill_queue(root)
    all_raws = sorted(root.rglob("*.md"),
                      key=lambda p: p.stat().st_size, reverse=True)
    targets = list(dict.fromkeys(list(pending) + all_raws[:8]))
    rows, failures = [], []
    for p in targets:
        try:
            rows.append(simulate(p))
        except Exception as e:  # PartitionError / DecodeError
            failures.append({"file": str(p), "error": type(e).__name__})
    maps = sorted(r["map_chars"] for r in rows)
    full = sorted(r["full_review_chars"] for r in rows)
    print(json.dumps({
        "targets": len(targets),
        "partition_failures": failures,
        "ambiguous_span_total": sum(r["ambiguous_spans"] for r in rows),
        "raws_with_ambiguous": sum(1 for r in rows if r["ambiguous_spans"]),
        "map_chars": {"p50": pct(maps, .5), "p90": pct(maps, .9),
                      "max": maps[-1] if maps else 0},
        "full_review_chars": {"p50": pct(full, .5), "p90": pct(full, .9),
                              "max": full[-1] if full else 0},
        "needs_continuation": sum(
            1 for r in rows
            if r["full_review_chars"] > rp.SESSION_BUDGET_DEFAULT),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
