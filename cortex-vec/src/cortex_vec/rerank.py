"""Optional LLM reranker over the top window of results (reuses OpenAI).

Off by default. Any failure (no key, bad JSON, API error) returns the input
order unchanged — reranking must never make a search fail.
"""
import json

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


def rerank(query, results, model, window=15):
    """Reorder the top `window` of `results` by LLM relevance; tail unchanged."""
    if not results:
        return results
    head = results[:window]
    tail = results[window:]
    try:
        import openai
        client = openai.OpenAI()
        candidates = "\n".join(
            f'{i}: {r.get("title", "")} — {r.get("summary", "")}' for i, r in enumerate(head)
        )
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
        order = {int(s["index"]): float(s["score"]) for s in scored}
        ranked_idx = sorted(range(len(head)), key=lambda i: order.get(i, -1.0), reverse=True)
        head = [head[i] for i in ranked_idx]
    except Exception:
        return results
    return head + tail
