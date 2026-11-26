"""Optional reranker over the top window of results.

`models.rerank.type` picks how the window is scored: `llm` (the default) asks
the chat model, `endpoint` sends it to the rerank endpoint in `models.rerank`.

Off by default. Any failure (no key, bad JSON, API error) returns the input
order unchanged — reranking must never make a search fail. The failure is
reported through `notes` so the caller can tell the order is not reranked.
"""
import json

from . import providers
from .errors import brief

_SYSTEM = (
    "你是檢索結果重排器。給定查詢與若干候選筆記（每個有 index、title、summary），"
    "依與查詢的相關性為每個候選打 0-10 分。只輸出 JSON 陣列，每個元素為 "
    '{"index": <int>, "score": <number>}，不要任何其他文字或 markdown。'
)


def _parse_scores(content):
    """Parse the model's JSON array, tolerating ```json fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _document(r):
    """The text both types score a result by."""
    return f'{r.get("title", "")} — {r.get("summary", "")}'


def _llm_scores(query, head, model):
    """{position: score} from the chat model."""
    client = providers.chat_client()
    candidates = "\n".join(f"{i}: {_document(r)}" for i, r in enumerate(head))
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"查詢：{query}\n\n候選：\n{candidates}"},
        ],
        max_completion_tokens=500,
        reasoning_effort="none",
    )
    scored = _parse_scores(resp.choices[0].message.content)
    return {int(s["index"]): float(s["score"]) for s in scored}


def _ranked(count, order):
    """Positions 0..count-1: scored ones by score, highest first, then the rest in order.

    Ties keep their original order. Keys outside the range are ignored: the
    chat model may answer with any index.
    """
    scored = [i for i in range(count) if i in order]
    rest = [i for i in range(count) if i not in order]
    return sorted(scored, key=lambda i: order[i], reverse=True) + rest


def rerank(query, results, model, window=15, notes=None):
    """Reorder the top `window` of `results` by relevance; tail unchanged.

    `model` is the chat model for the `llm` type; the `endpoint` type ignores
    it. On failure the input order is returned and, when `notes` is a list,
    one line saying so is appended to it.
    """
    head = results[:window]
    if not head:            # no results, or a zero window: nothing to score, nothing to send
        return results
    tail = results[window:]
    try:
        # Inside the try: a config that cannot be read must not fail the search either.
        if providers.rerank_type() == "endpoint":
            order = providers.endpoint_rerank(query, [_document(r) for r in head])
        else:
            order = _llm_scores(query, head, model)
        head = [head[i] for i in _ranked(len(head), order)]
    except Exception as e:
        if notes is not None:
            notes.append(f"rerank failed ({brief(e)}); order unchanged")
        return results
    return head + tail
