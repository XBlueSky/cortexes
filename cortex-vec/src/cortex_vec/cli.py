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
    p_search.add_argument("--no-bm25", action="store_true", help="Disable BM25 stream")
    p_search.add_argument("--no-vector", action="store_true", help="Disable vector stream")

    p_eval = sub.add_parser("eval", help="Run retrieval eval / propose queries")
    p_eval.add_argument("action", choices=["run", "propose"], help="run scorecard or propose queries")
    p_eval.add_argument("--queries", required=True, help="Path to queries.jsonl")
    p_eval.add_argument("--adapters", default="grep,vector,bm25,hybrid",
                        help="Comma-separated adapters to run")
    p_eval.add_argument("--k", type=int, default=5, help="Cutoff K")
    p_eval.add_argument("--out", help="Scorecard output path (markdown)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

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
