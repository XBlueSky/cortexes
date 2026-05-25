"""Load and validate the hand-labeled eval corpus (queries.jsonl)."""
import json

REQUIRED_FIELDS = ("id", "query", "gold", "type")


def load_queries(path):
    """Load queries.jsonl. Each line must have id/query/gold/type.

    Returns list[dict]. Raises ValueError on a malformed entry.
    """
    queries = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for field in REQUIRED_FIELDS:
                if field not in row:
                    raise ValueError(f"line {lineno}: missing required field '{field}'")
            if not isinstance(row["gold"], list) or not row["gold"]:
                raise ValueError(f"line {lineno}: 'gold' must be a non-empty list")
            queries.append(row)
    return queries


def check_gold_paths(queries, existing_paths):
    """Return {query_id: [missing_gold_paths]} for gold entries not in existing_paths."""
    existing = set(existing_paths)
    missing = {}
    for q in queries:
        gone = [g for g in q["gold"] if g not in existing]
        if gone:
            missing[q["id"]] = gone
    return missing
