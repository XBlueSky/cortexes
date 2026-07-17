"""CLI entry point for cortex-vec."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="cortex-vec — Vector store CLI for cortex vault"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show index health")
    p_rebuild = sub.add_parser("rebuild", help="Full rebuild from vault")
    p_rebuild.add_argument(
        "--bm25-only",
        action="store_true",
        help="Rebuild only the BM25 index from the vault (no re-embedding, free)",
    )

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
    p_search.add_argument("--no-bm25", action="store_true", help="Disable BM25 stream")
    p_search.add_argument("--no-vector", action="store_true", help="Disable vector stream")
    p_search.add_argument("--rerank", action="store_true", help="Enable LLM rerank of top results")
    p_search.add_argument("--graph", action="store_true", help="Enable wikilink graph-boost")

    p_eval = sub.add_parser("eval", help="Run retrieval eval / propose queries")
    p_eval.add_argument("action", choices=["run", "propose"], help="run scorecard or propose queries")
    p_eval.add_argument("--queries", required=True, help="Path to queries.jsonl")
    p_eval.add_argument("--adapters", default="grep,vector,bm25,hybrid",
                        help="Comma-separated adapters to run")
    p_eval.add_argument("--k", type=int, default=5, help="Cutoff K")
    p_eval.add_argument("--out", help="Scorecard output path (markdown)")

    # Trailer-anchored vault-maintenance queries (no vector store needed).
    p_dq = sub.add_parser(
        "distill-queue", help="List Raw files awaiting distillation"
    )
    p_dq.add_argument("--root", help="Raw directory (default: <vault>/Raw)")
    p_dq.add_argument("--stat", action="store_true",
                      help="Show per-level projected sizes instead of paths")
    p_dq.add_argument("--json", action="store_true",
                      help="With --stat: emit JSON rows")
    p_bq = sub.add_parser(
        "broadcast-queue", help="List distilled Raw eligible for broadcast"
    )
    p_bq.add_argument("--root", help="Raw directory (default: <vault>/Raw)")
    p_rs = sub.add_parser(
        "raw-state", help="Classify a single Raw file's distilled state"
    )
    p_rs.add_argument("path", help="Path to a Raw .md file")
    p_rv = sub.add_parser(
        "raw-view", help="Projected (budget-bounded) view of a Raw file"
    )
    p_rv.add_argument("path", help="Path to a Raw .md file")
    p_rv.add_argument("--budget", type=int, help="Max output chars (default: config)")
    p_rv.add_argument("--level", choices=["L0", "L1", "L2", "L3"],
                      help="Force a level (default: auto by budget)")
    p_rv.add_argument("--stat", action="store_true",
                      help="Emit per-level size JSON instead of the view")

    p_rm = sub.add_parser(
        "raw-map", help="Bounded navigation cards over a Raw (map-first)"
    )
    p_rm.add_argument("path", help="Path to a Raw .md file")
    p_rm.add_argument("--plan-id", required=True, dest="plan_id")
    p_rm.add_argument("--cursor", help="Continuation cursor from a prior page")
    p_rm.add_argument("--max-chars", type=int, dest="max_chars",
                      help="Page stdout cap (default: config, 12000)")
    p_rm.add_argument("--find", help="Exact literal to locate in the Raw")

    p_rsp = sub.add_parser(
        "raw-span", help="Bounded original-source page of one span"
    )
    p_rsp.add_argument("path", help="Path to a Raw .md file")
    p_rsp.add_argument("--plan-id", required=True, dest="plan_id")
    p_rsp.add_argument("--span-id", type=int, dest="span_id")
    p_rsp.add_argument("--cursor")
    p_rsp.add_argument("--max-chars", type=int, dest="max_chars")

    p_dp = sub.add_parser(
        "distill-plan", help="Single-raw distill plan lifecycle"
    )
    p_dp.add_argument("action", choices=["start", "status", "resume",
                                         "evidence-add", "seal", "complete",
                                         "list", "clear"])
    p_dp.add_argument("path", nargs="?", help="Raw path (start only)")
    p_dp.add_argument("--plan-id", dest="plan_id")
    p_dp.add_argument("--page-budget", type=int, dest="page_budget")
    p_dp.add_argument("--session-budget", type=int, dest="session_budget")
    p_dp.add_argument("--char-start", type=int, dest="char_start")
    p_dp.add_argument("--char-end", type=int, dest="char_end")
    p_dp.add_argument("--label", default="")
    p_dp.add_argument("--expected-outcome", dest="expected_outcome",
                      choices=["new", "pending-merge", "skip-routine",
                               "no-insight"])
    p_dp.add_argument("--new-session", action="store_true",
                      dest="new_session")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Fast path: trailer-anchored queue scans skip the heavy store import
    # (chromadb ~2.7s). They read only each Raw's last non-empty line.
    if args.command in ("distill-queue", "broadcast-queue", "raw-state",
                        "raw-view", "raw-map", "raw-span", "distill-plan"):
        from . import distill_queue as dq

        if args.command == "raw-state":
            dq.dispatch_raw_state(args.path)
            return
        if args.command == "raw-view":
            from . import raw_view as rv

            rv.dispatch_raw_view(args)
            return
        if args.command == "raw-map":
            from . import raw_map as rm

            rm.dispatch(args)
            return
        if args.command == "raw-span":
            from . import raw_span as rsp

            rsp.dispatch(args)
            return
        if args.command == "distill-plan":
            from . import distill_plan as dpl

            dpl.dispatch(args)
            return
        from .config import get_vault_path

        root = args.root or (get_vault_path() / "Raw")
        if args.command == "distill-queue":
            dq.dispatch_distill_queue(root, stat=args.stat, as_json=args.json)
        else:
            dq.dispatch_broadcast_queue(root)
        return

    # Lazy import: chromadb (~2.7s) only loaded when store is needed
    from . import store

    def _dispatch_eval(args):
        from .eval import run
        run.dispatch(args)

    commands = {
        "status": store.cmd_status,
        "rebuild": store.cmd_rebuild,
        "upsert": store.cmd_upsert,
        "delete": store.cmd_delete,
        "search": store.cmd_search,
        "eval": _dispatch_eval,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
