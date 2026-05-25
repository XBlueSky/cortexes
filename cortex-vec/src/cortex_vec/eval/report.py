"""Render an eval summary into a markdown scorecard."""
from datetime import date


def _fmt(x):
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def render(summary, meta):
    """meta: dict with corpus, k, n (and optional commit/hardware)."""
    lines = []
    lines.append(f"# {date.today().isoformat()} — {meta.get('corpus', 'corpus')}")
    lines.append("")
    lines.append(f"- **Corpus:** {meta.get('corpus', '')}")
    lines.append(f"- **N (queries):** {meta.get('n', '')}")
    lines.append(f"- **K:** {meta.get('k', '')}")
    if meta.get("commit"):
        lines.append(f"- **Commit:** `{meta['commit']}`")
    lines.append("")

    lines.append("## Per-adapter")
    lines.append("")
    lines.append("| Adapter | P@K | R@K | MRR | Hit rate | p50 latency (ms) |")
    lines.append("|---|---|---|---|---|---|")
    for adapter, s in summary["by_adapter"].items():
        lines.append(
            f"| {adapter} | {_fmt(s['p'])} | {_fmt(s['r'])} | {_fmt(s['mrr'])} "
            f"| {_fmt(s['hit_rate'])} | {_fmt(s['latency_p50'])} |"
        )
    lines.append("")

    if summary.get("by_type"):
        lines.append("## Per-adapter/type")
        lines.append("")
        lines.append("| Adapter/Type | n | P@K | R@K | MRR | Hit rate |")
        lines.append("|---|---|---|---|---|---|")
        for key, s in summary["by_type"].items():
            lines.append(
                f"| {key} | {s['n']} | {_fmt(s['p'])} | {_fmt(s['r'])} "
                f"| {_fmt(s['mrr'])} | {_fmt(s['hit_rate'])} |"
            )
        lines.append("")

    return "\n".join(lines)
