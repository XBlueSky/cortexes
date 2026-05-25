# Hybrid 檢索 + 評測框架（Plan 1：Phase 0–2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `cortex-vec` 從純 vector 檢索升級為 BM25 + vector 的 RRF hybrid（含中英混合 CJK 分詞），並建立可重現的檢索評測 harness，用 eval 量出 baseline → hybrid 的 lift。

**Architecture:** 方案 A——所有檢索邏輯收進 `cortex-vec` Python 套件，拆成單一職責模組（`tokenize` / `bm25` / `fusion` / `store`）。`fusion.search()` 是唯一對外檢索進入點，內部協調 vector(`store`) + bm25(`bm25`) 兩路並用 RRF 融合。eval harness 以 pluggable adapter（grep / vector / bm25 / hybrid）在相同內容上比較，重用 production 模組。不動 ChromaDB / markdown source-of-truth 模型。

**Tech Stack:** Python 3.8+、ChromaDB、OpenAI embedding（既有）、`rank-bm25`（BM25Okapi）、`jieba`（中文分詞）、`snowballstemmer`（英文 Porter stemmer）、`pytest`。

**Scope note:** 本 plan 只涵蓋 spec 的 Phase 0–2。Phase 3–5（synonym 展開、wikilink graph-boost、LLM rerank）刻意延後到 Plan 2，等本 plan 的 eval 數據判斷是否值得做（符合 spec §5 的 eval-gating / YAGNI 原則）。

**Spec:** `docs/superpowers/specs/2026-05-25-hybrid-retrieval-eval-design.md`

---

## File Structure

新增 / 修改的檔案與職責（路徑相對 repo root，`cortex-vec/` 下）：

| 檔案 | 動作 | 職責 |
|---|---|---|
| `pyproject.toml` | Modify | 加 `rank-bm25` / `jieba` / `snowballstemmer` 依賴；加 `[project.optional-dependencies] dev = ["pytest"]`；加 pytest 設定 |
| `src/cortex_vec/config.py` | Modify | 加 `BM25_DIR`、`get_retrieval_config()` |
| `src/cortex_vec/tokenize.py` | Create | CJK-aware tokenizer（jieba + stemmer，保留英文詞邊界） |
| `src/cortex_vec/bm25.py` | Create | BM25 索引：build / upsert / delete / search / persist / load |
| `src/cortex_vec/store.py` | Modify | 抽出 `vector_stream()`；`cmd_*` 改與 bm25 lockstep；`cmd_search` 改呼叫 fusion |
| `src/cortex_vec/fusion.py` | Create | `rrf_fuse()` + `search()`（hybrid 進入點 + degradation） |
| `src/cortex_vec/cli.py` | Modify | 加 `eval` 子命令、search 的 `--no-bm25` / `--no-vector` debug flags |
| `src/cortex_vec/eval/__init__.py` | Create | 空套件標記 |
| `src/cortex_vec/eval/score.py` | Create | P@k / R@k / MRR / hit + 聚合 |
| `src/cortex_vec/eval/corpus.py` | Create | 載入 + 驗證 `queries.jsonl` |
| `src/cortex_vec/eval/adapters.py` | Create | Adapter protocol + grep / vector / bm25 / hybrid |
| `src/cortex_vec/eval/report.py` | Create | markdown scorecard 產生器 |
| `src/cortex_vec/eval/run.py` | Create | runner：跑各 adapter → NDJSON + summary + scorecard；`propose` helper |
| `tests/conftest.py` | Create | 共用 fixtures（fixture 文件集、tmp 索引路徑） |
| `tests/test_*.py` | Create | 各模組單元測試 |

---

## Task 1: 專案設定 — 依賴、pytest、tests 骨架

**Files:**
- Modify: `cortex-vec/pyproject.toml`
- Create: `cortex-vec/tests/__init__.py`
- Create: `cortex-vec/tests/conftest.py`
- Create: `cortex-vec/tests/test_smoke.py`

- [ ] **Step 1: 改 pyproject.toml 加依賴與 pytest 設定**

把 `cortex-vec/pyproject.toml` 改成：

```toml
[project]
name = "cortex-vec"
version = "0.4.0"
description = "Vector store CLI for the cortex vault"
requires-python = ">=3.8"
dependencies = [
    "chromadb",
    "openai",
    "python-frontmatter",
    "pysqlite3-binary",
    "rank-bm25",
    "jieba",
    "snowballstemmer",
]

[project.optional-dependencies]
dev = ["pytest"]

[project.scripts]
cortex-vec = "cortex_vec.cli:main"

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: 建 tests 骨架**

Create `cortex-vec/tests/__init__.py`（空檔）。

Create `cortex-vec/tests/test_smoke.py`：

```python
def test_package_imports():
    import cortex_vec  # noqa: F401
```

- [ ] **Step 3: 安裝 dev 依賴並跑 smoke test**

Run:
```bash
cd cortex-vec && pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: PASS（1 passed）。若 `rank-bm25` / `jieba` / `snowballstemmer` 安裝失敗則先解決安裝再繼續。

- [ ] **Step 4: 建共用 fixtures**

Create `cortex-vec/tests/conftest.py`：

```python
"""Shared pytest fixtures."""
import pytest


@pytest.fixture
def fixture_docs():
    """A tiny in-memory corpus: list of (base_path, title, body, repo, type, category)."""
    return [
        ("Notes/Nginx/cert-renew.md", "Nginx 憑證自動更新",
         "用 certbot 設定 nginx 的 TLS certificate 自動 renew。", "", "note", "Nginx"),
        ("Notes/Linux/oom.md", "Linux OOM killer 排查",
         "dmesg 看 out of memory，調整 oom_score_adj。", "", "note", "Linux"),
        ("Projects/libsynow3/oauth.md", "libsynow3 OAuth 流程",
         "libsynow3 的 token refresh 與 OAuth 授權實作。", "libsynow3", "project", "libsynow3"),
    ]
```

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/pyproject.toml cortex-vec/tests/
git commit -m "chore(cortex-vec): add hybrid/eval deps + pytest scaffold"
```

---

## Task 2: eval/score.py — 檢索指標

**Files:**
- Create: `cortex-vec/src/cortex_vec/eval/__init__.py`
- Create: `cortex-vec/src/cortex_vec/eval/score.py`
- Test: `cortex-vec/tests/test_score.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_score.py`：

```python
from cortex_vec.eval import score


def test_precision_recall_hit():
    ranked = ["a", "b", "c", "d", "e"]
    gold = {"a", "x"}
    r = score.score_query(ranked, gold, k=5)
    assert r["precision_at_k"] == 1 / 5
    assert r["recall_at_k"] == 1 / 2
    assert r["hit"] is True
    assert r["reciprocal_rank"] == 1.0  # gold "a" at rank 1


def test_first_gold_rank_two():
    ranked = ["b", "a", "c"]
    r = score.score_query(ranked, {"a"}, k=3)
    assert r["reciprocal_rank"] == 0.5


def test_no_hit():
    r = score.score_query(["b", "c"], {"a"}, k=2)
    assert r["hit"] is False
    assert r["reciprocal_rank"] == 0.0
    assert r["precision_at_k"] == 0.0


def test_aggregate_by_adapter():
    rows = [
        {"adapter": "grep", "type": "x", "precision_at_k": 0.2, "recall_at_k": 1.0,
         "reciprocal_rank": 1.0, "hit": True, "latency_ms": 1.0},
        {"adapter": "grep", "type": "y", "precision_at_k": 0.4, "recall_at_k": 0.5,
         "reciprocal_rank": 0.5, "hit": True, "latency_ms": 3.0},
    ]
    agg = score.aggregate(rows)
    g = agg["by_adapter"]["grep"]
    assert g["n"] == 2
    assert abs(g["p"] - 0.3) < 1e-9
    assert abs(g["r"] - 0.75) < 1e-9
    assert abs(g["mrr"] - 0.75) < 1e-9
    assert g["hit_rate"] == 1.0
    assert g["latency_p50"] == 2.0
```

- [ ] **Step 2: 跑測試確認失敗**

Create `cortex-vec/src/cortex_vec/eval/__init__.py`（空檔）。

Run: `cd cortex-vec && pytest tests/test_score.py -v`
Expected: FAIL（`module 'cortex_vec.eval.score' has no attribute ...` 或 import error）。

- [ ] **Step 3: 實作 score.py**

Create `cortex-vec/src/cortex_vec/eval/score.py`：

```python
"""Retrieval metrics: P@k, R@k, MRR, hit, and aggregation."""
from statistics import median


def score_query(ranked, gold, k):
    """Score one query's ranked base-path list against a gold set.

    ranked: list[str] of base paths, best-first.
    gold:   set[str] of relevant base paths.
    Returns dict with precision_at_k, recall_at_k, reciprocal_rank, hit.
    """
    gold = set(gold)
    top_k = ranked[:k]
    hits = sum(1 for p in top_k if p in gold)
    precision = hits / k if k else 0.0
    recall = hits / len(gold) if gold else 0.0

    reciprocal_rank = 0.0
    for idx, p in enumerate(top_k):
        if p in gold:
            reciprocal_rank = 1.0 / (idx + 1)
            break

    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "reciprocal_rank": reciprocal_rank,
        "hit": hits > 0,
    }


def aggregate(rows):
    """Aggregate per-query score rows into by_adapter and by_type summaries.

    Each row must have: adapter, type, precision_at_k, recall_at_k,
    reciprocal_rank, hit, latency_ms.
    """
    by_adapter = {}
    by_type = {}

    def _bucket(d, key):
        return d.setdefault(key, [])

    for row in rows:
        _bucket(by_adapter, row["adapter"]).append(row)
        _bucket(by_type, (row["adapter"], row["type"])).append(row)

    def _summary(group):
        n = len(group)
        return {
            "n": n,
            "p": sum(g["precision_at_k"] for g in group) / n,
            "r": sum(g["recall_at_k"] for g in group) / n,
            "mrr": sum(g["reciprocal_rank"] for g in group) / n,
            "hit_rate": sum(1 for g in group if g["hit"]) / n,
            "latency_p50": median(g["latency_ms"] for g in group),
        }

    return {
        "by_adapter": {a: _summary(g) for a, g in by_adapter.items()},
        "by_type": {f"{a}/{t}": _summary(g) for (a, t), g in by_type.items()},
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_score.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/eval/__init__.py cortex-vec/src/cortex_vec/eval/score.py cortex-vec/tests/test_score.py
git commit -m "feat(cortex-vec): add eval scoring metrics (P@k/R@k/MRR/hit)"
```

---

## Task 3: eval/corpus.py — 載入與驗證 queries.jsonl

**Files:**
- Create: `cortex-vec/src/cortex_vec/eval/corpus.py`
- Test: `cortex-vec/tests/test_corpus.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_corpus.py`：

```python
import json
import pytest
from cortex_vec.eval import corpus


def _write(tmp_path, rows):
    p = tmp_path / "queries.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    p = _write(tmp_path, [
        {"id": "q-001", "query": "nginx 憑證", "gold": ["Notes/Nginx/cert-renew.md"], "type": "single-note"},
        {"id": "q-002", "query": "oom", "gold": ["Notes/Linux/oom.md"], "type": "single-note"},
    ])
    queries = corpus.load_queries(p)
    assert len(queries) == 2
    assert queries[0]["id"] == "q-001"
    assert queries[0]["gold"] == ["Notes/Nginx/cert-renew.md"]


def test_missing_field_raises(tmp_path):
    p = _write(tmp_path, [{"id": "q-001", "query": "x"}])  # no gold
    with pytest.raises(ValueError, match="gold"):
        corpus.load_queries(p)


def test_check_gold_paths_exist(tmp_path):
    existing = {"Notes/Nginx/cert-renew.md"}
    queries = [
        {"id": "q-001", "query": "x", "gold": ["Notes/Nginx/cert-renew.md"], "type": "t"},
        {"id": "q-002", "query": "y", "gold": ["Notes/Gone/missing.md"], "type": "t"},
    ]
    missing = corpus.check_gold_paths(queries, existing)
    assert missing == {"q-002": ["Notes/Gone/missing.md"]}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_corpus.py -v`
Expected: FAIL（import error / no attribute）。

- [ ] **Step 3: 實作 corpus.py**

Create `cortex-vec/src/cortex_vec/eval/corpus.py`：

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_corpus.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/eval/corpus.py cortex-vec/tests/test_corpus.py
git commit -m "feat(cortex-vec): add eval corpus loader + gold-path validation"
```

---

## Task 4: tokenize.py — CJK-aware tokenizer

**Files:**
- Create: `cortex-vec/src/cortex_vec/tokenize.py`
- Test: `cortex-vec/tests/test_tokenize.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_tokenize.py`：

```python
from cortex_vec import tokenize


def test_pure_english_lowercased_and_stemmed():
    toks = tokenize.tokenize("Renewing Certificates")
    # snowball porter: renewing->renew, certificates->certif
    assert "renew" in toks
    assert all(t == t.lower() for t in toks)


def test_pure_chinese_segmented():
    toks = tokenize.tokenize("憑證自動更新")
    # jieba should split into multiple words; whole-run fallback also acceptable
    assert "".join(toks).replace(" ", "") == "憑證自動更新"
    assert len(toks) >= 1


def test_mixed_cjk_english_preserves_english_boundary():
    toks = tokenize.tokenize("機器學習ML技術")
    assert "ml" in toks  # latin run preserved as a whole token, lowercased
    assert "機器" in toks or "機器學習" in toks  # depends on jieba availability


def test_punctuation_stripped_but_path_chars_kept():
    toks = tokenize.tokenize("src/middleware/auth.ts, jose!")
    assert "jose" in toks
    assert any("auth" in t for t in toks)


def test_short_query_nonempty():
    assert tokenize.tokenize("DSM-123456")  # issue id should survive as tokens
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_tokenize.py -v`
Expected: FAIL（no module `cortex_vec.tokenize`）。

- [ ] **Step 3: 實作 tokenize.py**

Create `cortex-vec/src/cortex_vec/tokenize.py`：

```python
"""CJK-aware tokenizer for BM25.

Splits Han runs with jieba (soft-falls to whole-run if jieba missing),
stems Latin words with a Porter stemmer, and preserves Latin word
boundaries embedded inside CJK text (e.g. "機器學習ML技術").
"""
import re
import sys

# Han, Hiragana/Katakana, Hangul ranges. cortex content is zh+en; non-Han CJK
# runs are kept whole (jieba targets Han).
CJK_RUN_RE = re.compile(r"[㐀-鿿぀-ヿ가-힯]+")
HAN_RE = re.compile(r"[㐀-鿿]")
# Keep alphanumerics, CJK, and path-ish chars; everything else -> space.
_CLEAN_RE = re.compile(r"[^\w\s/.\\\-㐀-鿿぀-ヿ가-힯]", re.UNICODE)

_stemmer = None
_jieba_ok = None


def _stem(word):
    global _stemmer
    if _stemmer is None:
        import snowballstemmer
        _stemmer = snowballstemmer.stemmer("porter")
    return _stemmer.stemWord(word)


def _seg_han(run):
    global _jieba_ok
    if _jieba_ok is None:
        try:
            import jieba  # noqa: F401
            _jieba_ok = True
        except Exception:
            _jieba_ok = False
            print("cortex-vec: jieba not installed; CJK runs kept whole "
                  "(install jieba for word-level CJK recall)", file=sys.stderr)
    if not _jieba_ok:
        return [run]
    import jieba
    return [w for w in jieba.lcut(run, HMM=True) if w.strip()]


def _segment_token(token):
    """Split one whitespace-delimited token that contains CJK into parts,
    preserving embedded Latin runs."""
    parts = []
    cursor = 0
    for m in CJK_RUN_RE.finditer(token):
        if m.start() > cursor:
            latin = token[cursor:m.start()].strip()
            if latin:
                parts.append(_stem(latin))
        run = m.group()
        if HAN_RE.search(run):
            parts.extend(_seg_han(run))
        else:
            parts.append(run)
        cursor = m.end()
    if cursor < len(token):
        latin = token[cursor:].strip()
        if latin:
            parts.append(_stem(latin))
    return parts


def tokenize(text):
    """Return a list of lowercased tokens for BM25 indexing/querying."""
    cleaned = _CLEAN_RE.sub(" ", text.lower())
    out = []
    for raw in cleaned.split():
        if not raw:
            continue
        if CJK_RUN_RE.search(raw):
            out.extend(t for t in _segment_token(raw) if t)
        else:
            out.append(_stem(raw))
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_tokenize.py -v`
Expected: PASS（5 passed）。若 `test_mixed_cjk_english_preserves_english_boundary` 因 jieba 切詞結果不同而失敗，確認 `"ml"` 在結果中即可（中文切法兩種斷言已用 `or` 容錯）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/tokenize.py cortex-vec/tests/test_tokenize.py
git commit -m "feat(cortex-vec): add CJK-aware tokenizer (jieba + porter, mixed zh/en)"
```

---

## Task 5: config.py — BM25 路徑與 retrieval 設定

**Files:**
- Modify: `cortex-vec/src/cortex_vec/config.py`
- Test: `cortex-vec/tests/test_config.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_config.py`：

```python
from cortex_vec import config


def test_retrieval_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    rc = config.get_retrieval_config()
    assert rc["rrf_k"] == 60
    assert rc["w_bm25"] == 0.4
    assert rc["w_vec"] == 0.6
    assert rc["max_per_repo"] == 0


def test_retrieval_override(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {"retrieval": {"w_bm25": 0.7}})
    rc = config.get_retrieval_config()
    assert rc["w_bm25"] == 0.7
    assert rc["w_vec"] == 0.6  # untouched default preserved


def test_bm25_dir_exists():
    assert str(config.BM25_DIR).endswith("/.cortex/bm25")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_config.py -v`
Expected: FAIL（no attribute `BM25_DIR` / `get_retrieval_config`）。

- [ ] **Step 3: 改 config.py**

在 `cortex-vec/src/cortex_vec/config.py` 的常數區（`SUMMARY_MODEL = "gpt-5.4-mini"` 之後）加：

```python
BM25_DIR = Path.home() / ".cortex" / "bm25"

_RETRIEVAL_DEFAULTS = {
    "rrf_k": 60,
    "w_bm25": 0.4,
    "w_vec": 0.6,
    "max_per_repo": 0,
}
```

並在檔尾加函式：

```python
def get_retrieval_config():
    """Return retrieval settings merged over defaults."""
    cfg = load_config()
    rc = dict(_RETRIEVAL_DEFAULTS)
    rc.update(cfg.get("retrieval", {}))
    return rc
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_config.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/config.py cortex-vec/tests/test_config.py
git commit -m "feat(cortex-vec): add BM25_DIR + retrieval config with defaults"
```

---

## Task 6: bm25.py — BM25 索引 build / search / 持久化

**Files:**
- Create: `cortex-vec/src/cortex_vec/bm25.py`
- Test: `cortex-vec/tests/test_bm25.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_bm25.py`：

```python
from cortex_vec import bm25


def _docs():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "title": "Nginx 憑證自動更新",
         "body": "用 certbot 設定 nginx TLS certificate 自動 renew", "summary": "certbot renew",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Notes/Linux/oom.md", "title": "Linux OOM",
         "body": "out of memory killer dmesg", "summary": "oom",
         "tags": "", "repos": [], "type": "note", "category": "Linux"},
        {"id": "Projects/libsynow3/oauth.md", "title": "libsynow3 OAuth",
         "body": "token refresh oauth", "summary": "oauth",
         "tags": "", "repos": ["libsynow3"], "type": "project", "category": "libsynow3"},
    ]


def test_build_and_search_finds_relevant(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    hits = idx.search("nginx certificate renew", n=3)
    assert hits[0]["id"] == "Notes/Nginx/cert-renew.md"
    assert hits[0]["title"] == "Nginx 憑證自動更新"


def test_search_with_repo_filter(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    hits = idx.search("oauth token", n=5, where={"repo": "libsynow3"})
    assert all(h["id"].startswith("Projects/libsynow3/") for h in hits)
    assert hits and hits[0]["id"] == "Projects/libsynow3/oauth.md"


def test_persist_and_load_roundtrip(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    idx.save()
    idx2 = bm25.BM25Index(tmp_path / "bm25")
    idx2.load()
    assert idx2.count() == 3
    hits = idx2.search("oom dmesg", n=2)
    assert hits[0]["id"] == "Notes/Linux/oom.md"


def test_upsert_and_delete(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    idx.upsert({"id": "Notes/New/x.md", "title": "brand new redis cache note",
                "body": "redis cache eviction", "summary": "redis",
                "tags": "", "repos": [], "type": "note", "category": "New"})
    assert idx.count() == 4
    assert idx.search("redis cache", n=1)[0]["id"] == "Notes/New/x.md"
    idx.delete("Notes/New/x.md")
    assert idx.count() == 3
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_bm25.py -v`
Expected: FAIL（no module `cortex_vec.bm25`）。

- [ ] **Step 3: 實作 bm25.py**

Create `cortex-vec/src/cortex_vec/bm25.py`：

```python
"""Persistent BM25 index over vault notes (one entry per note base path)."""
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from .tokenize import tokenize

# Display/metadata fields carried per doc (everything except the raw body).
_META_FIELDS = ("id", "title", "summary", "tags", "repos", "type", "category")


def _doc_record(doc):
    """Normalize an input doc into the stored record (tokens + metadata)."""
    text = f"{doc.get('title', '')}\n\n{doc.get('body', '')}".strip()
    rec = {f: doc.get(f) for f in _META_FIELDS}
    rec["repos"] = list(doc.get("repos") or [])
    rec["tokens"] = tokenize(text)
    return rec


def _matches(rec, where):
    if not where:
        return True
    if "repo" in where and where["repo"] not in rec.get("repos", []):
        return False
    if "type" in where and rec.get("type") != where["type"]:
        return False
    if "category" in where and rec.get("category") != where["category"]:
        return False
    return True


class BM25Index:
    """BM25 index persisted as a pickle of doc records; BM25Okapi rebuilt on load."""

    def __init__(self, dir_path):
        self.dir = Path(dir_path)
        self.docs = []          # list of stored records
        self._bm25 = None       # BM25Okapi, lazily (re)built

    @property
    def _file(self):
        return self.dir / "index.pkl"

    def count(self):
        return len(self.docs)

    def _reindex(self):
        corpus = [d["tokens"] for d in self.docs] or [[""]]
        self._bm25 = BM25Okapi(corpus)

    def build_from_docs(self, docs):
        self.docs = [_doc_record(d) for d in docs]
        self._reindex()

    def upsert(self, doc):
        rec = _doc_record(doc)
        self.docs = [d for d in self.docs if d["id"] != rec["id"]]
        self.docs.append(rec)
        self._reindex()

    def delete(self, base_path):
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["id"] != base_path]
        if len(self.docs) != before:
            self._reindex()
        return before - len(self.docs)

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._file, "wb") as f:
            pickle.dump(self.docs, f)

    def load(self):
        if not self._file.exists():
            raise FileNotFoundError(f"BM25 index not found at {self._file}; run rebuild")
        with open(self._file, "rb") as f:
            self.docs = pickle.load(f)
        self._reindex()

    def search(self, query, n=5, where=None):
        """Return up to n display dicts, best-first, filtered by `where`."""
        if not self.docs:
            return []
        if self._bm25 is None:
            self._reindex()
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(
            zip(self.docs, scores), key=lambda pair: pair[1], reverse=True
        )
        out = []
        for rec, sc in ranked:
            if sc <= 0:
                continue
            if not _matches(rec, where):
                continue
            out.append({
                "id": rec["id"],
                "score": float(sc),
                "title": rec.get("title") or "",
                "type": rec.get("type") or "",
                "repo": (rec.get("repos") or [""])[0],
                "category": rec.get("category") or "",
                "tags": rec.get("tags") or "",
                "summary": rec.get("summary") or "",
            })
            if len(out) >= n:
                break
        return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_bm25.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/bm25.py cortex-vec/tests/test_bm25.py
git commit -m "feat(cortex-vec): add persistent BM25 index (build/search/upsert/delete)"
```

---

## Task 7: store.py — 抽出 vector_stream()

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`
- Test: `cortex-vec/tests/test_vector_stream.py`

說明：把 `cmd_search` 內的「查詢 + 去重」邏輯抽成可重用的 `vector_stream(query, n, where)`，回傳「依 base-path 去重、依 score 降序」的完整 display dict 清單（不切 n）。`cmd_search` 之後會被 Task 9 改寫成呼叫 fusion，這裡先建立 stream 函式。

- [ ] **Step 1: 寫失敗測試（用 monkeypatch 假造 ChromaDB 回傳）**

Create `cortex-vec/tests/test_vector_stream.py`：

```python
from pathlib import Path
from cortex_vec import store


class _FakeCol:
    def query(self, **kwargs):
        return {
            "documents": [["# Nginx\n憑證自動更新 certbot", "OOM killer dmesg"]],
            "metadatas": [[
                {"title": "Nginx 憑證", "type": "note", "repo": "", "category": "Nginx",
                 "tags": "", "source_path": "/vault/Notes/Nginx/cert-renew.md"},
                {"title": "Linux OOM", "type": "note", "repo": "", "category": "Linux",
                 "tags": "", "source_path": "/vault/Notes/Linux/oom.md"},
            ]],
            "distances": [[0.1, 0.4]],
        }


def test_vector_stream_dedup_and_score(monkeypatch):
    monkeypatch.setattr(store, "get_client", lambda: object())
    monkeypatch.setattr(store, "get_collection", lambda client: _FakeCol())
    monkeypatch.setattr(store, "get_vault_path", lambda: Path("/vault"))

    items = store.vector_stream("nginx 憑證", n=5)
    assert items[0]["id"] == "Notes/Nginx/cert-renew.md"
    assert items[0]["score"] == 0.9  # 1 - 0.1
    assert items[1]["id"] == "Notes/Linux/oom.md"
    assert items[0]["title"] == "Nginx 憑證"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_vector_stream.py -v`
Expected: FAIL（`store` has no attribute `vector_stream`）。

- [ ] **Step 3: 在 store.py 加 vector_stream()**

在 `cortex-vec/src/cortex_vec/store.py` 的 `cmd_delete` 之後、`cmd_search` 之前，加入：

```python
def _build_where(repo=None, type=None, category=None):
    clauses = []
    if repo:
        clauses.append({"repo": repo})
    if type:
        clauses.append({"type": type})
    if category:
        clauses.append({"category": category})
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) > 1:
        return {"$and": clauses}
    return None


def vector_stream(query, n, where=None):
    """Vector retrieval stream: dedup by base path, return display dicts sorted desc.

    Returns the full deduped list (not sliced to n) so the fusion layer can rank it.
    """
    from pathlib import Path

    client = get_client()
    col = get_collection(client)
    vault = get_vault_path()

    kwargs = {
        "query_texts": [query],
        "n_results": n * 3,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    seen = {}
    for doc, meta, dist in zip(docs, metas, dists):
        score = round(1 - dist, 4)
        source = meta.get("source_path", "")
        try:
            rel_id = str(Path(source).relative_to(vault))
        except (ValueError, TypeError):
            rel_id = source
        base = _base_path(rel_id)
        if base not in seen or score > seen[base]["score"]:
            seen[base] = {
                "id": base,
                "score": score,
                "title": meta.get("title", ""),
                "type": meta.get("type", ""),
                "repo": meta.get("repo", ""),
                "category": meta.get("category", ""),
                "tags": meta.get("tags", ""),
                "summary": extract_summary(doc),
            }
    return sorted(seen.values(), key=lambda x: -x["score"])
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_vector_stream.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py cortex-vec/tests/test_vector_stream.py
git commit -m "refactor(cortex-vec): extract vector_stream() + _build_where() from cmd_search"
```

---

## Task 8: fusion.py — RRF 融合（純函式）

**Files:**
- Create: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_rrf.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_fusion_rrf.py`：

```python
from cortex_vec import fusion


def test_rrf_basic_two_streams():
    ranked = {
        "vector": [("a", 0), ("b", 1)],
        "bm25": [("b", 0), ("c", 1)],
    }
    fused = fusion.rrf_fuse(ranked, {"vector": 0.6, "bm25": 0.4}, k=60)
    ids = [i for i, _ in fused]
    assert "b" in ids and "a" in ids and "c" in ids
    # b appears in both streams near the top -> should rank first
    assert ids[0] == "b"


def test_rrf_redistributes_weight_when_stream_empty():
    ranked = {"vector": [], "bm25": [("x", 0), ("y", 1)]}
    fused = fusion.rrf_fuse(ranked, {"vector": 0.6, "bm25": 0.4}, k=60)
    # bm25 alone -> x ranks above y, scores reflect full (normalized) weight
    assert [i for i, _ in fused] == ["x", "y"]
    assert fused[0][1] > 0


def test_rrf_empty_all():
    assert fusion.rrf_fuse({"vector": [], "bm25": []}, {"vector": 0.6, "bm25": 0.4}) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_fusion_rrf.py -v`
Expected: FAIL（no module `cortex_vec.fusion`）。

- [ ] **Step 3: 實作 fusion.py 的 rrf_fuse（先只放純函式）**

Create `cortex-vec/src/cortex_vec/fusion.py`：

```python
"""Hybrid retrieval: RRF fusion of vector + BM25 streams."""
from . import store
from .config import BM25_DIR, get_retrieval_config


def rrf_fuse(ranked, weights, k=60):
    """Reciprocal Rank Fusion over named streams.

    ranked:  {stream_name: [(doc_id, rank), ...]}  (rank is 0-based, best=0)
    weights: {stream_name: weight}
    Returns [(doc_id, score)] sorted by score desc. Streams that are empty
    have their weight redistributed across the present streams.
    """
    present = [name for name, items in ranked.items() if items]
    if not present:
        return []
    total = sum(weights.get(name, 0.0) for name in present) or 1.0
    norm = {name: weights.get(name, 0.0) / total for name in present}

    scores = {}
    for name in present:
        for doc_id, rank in ranked[name]:
            scores[doc_id] = scores.get(doc_id, 0.0) + norm[name] * (1.0 / (k + rank + 1))
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_fusion_rrf.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_rrf.py
git commit -m "feat(cortex-vec): add RRF fusion with empty-stream weight redistribution"
```

---

## Task 9: fusion.search() — 協調兩路 + degradation

**Files:**
- Modify: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_search.py`

- [ ] **Step 1: 寫失敗測試（monkeypatch 兩路 stream）**

Create `cortex-vec/tests/test_fusion_search.py`：

```python
from cortex_vec import fusion, store, bm25


def _vec_items():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "score": 0.9, "title": "Nginx 憑證",
         "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
    ]


def _bm25_items():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "score": 7.2, "title": "Nginx 憑證",
         "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"},
        {"id": "Notes/Linux/oom.md", "score": 3.1, "title": "Linux OOM",
         "type": "note", "repo": "", "category": "Linux", "tags": "", "summary": "oom"},
    ]


class _FakeBM25:
    def __init__(self, *a, **k):
        pass

    def load(self):
        pass

    def search(self, query, n, where=None):
        return _bm25_items()


def test_hybrid_merges_both(monkeypatch):
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx 憑證", n=5)
    ids = [o["id"] for o in out]
    assert ids[0] == "Notes/Nginx/cert-renew.md"  # in both streams -> top
    assert "Notes/Linux/oom.md" in ids            # bm25-only hit still surfaces
    assert out[0]["summary"] == "certbot"
    assert "score" in out[0]


def test_degrades_to_bm25_when_vector_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no OPENAI_API_KEY")
    monkeypatch.setattr(store, "vector_stream", _boom)
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("oom", n=5)
    assert [o["id"] for o in out][0] in {"Notes/Nginx/cert-renew.md", "Notes/Linux/oom.md"}
    assert out  # still returns results via bm25 only


def test_no_bm25_flag(monkeypatch):
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec_items())
    monkeypatch.setattr(bm25, "BM25Index", _FakeBM25)
    out = fusion.search("nginx", n=5, use_bm25=False)
    assert [o["id"] for o in out] == ["Notes/Nginx/cert-renew.md"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_fusion_search.py -v`
Expected: FAIL（`fusion` has no attribute `search`）。

- [ ] **Step 3: 在 fusion.py 加 search()**

在 `cortex-vec/src/cortex_vec/fusion.py` 檔尾加入：

```python
def _bm25_stream(query, n, where):
    """Load the persisted BM25 index and search; return [] on any failure."""
    from . import bm25
    try:
        idx = bm25.BM25Index(BM25_DIR)
        idx.load()
        return idx.search(query, n, where)
    except Exception:
        return []


def _vector_stream(query, n, where):
    try:
        return store.vector_stream(query, n, where)
    except Exception:
        return []


# Order matters: vector first so its display fields (e.g. summary) win on merge.
_STREAM_ORDER = ("vector", "bm25")


def search(query, n=5, where=None, use_bm25=True, use_vector=True):
    """Hybrid search entry point. Returns up to n display dicts (best-first).

    Gracefully degrades: if a stream errors or is disabled, the other carries
    the query (RRF weight is redistributed in rrf_fuse).
    """
    rc = get_retrieval_config()
    weights = {"vector": rc["w_vec"], "bm25": rc["w_bm25"]}

    streams = {}
    if use_vector:
        streams["vector"] = _vector_stream(query, n, where)
    if use_bm25:
        streams["bm25"] = _bm25_stream(query, n, where)

    ranked = {}
    display = {}
    for name in _STREAM_ORDER:
        items = streams.get(name) or []
        for rank, item in enumerate(items):
            ranked.setdefault(name, []).append((item["id"], rank))
            disp = display.setdefault(item["id"], {})
            for key, val in item.items():
                if key == "score":
                    continue
                if key not in disp or not disp.get(key):
                    disp[key] = val

    fused = rrf_fuse(ranked, weights, k=rc["rrf_k"])

    out = []
    for doc_id, score in fused[:n]:
        entry = dict(display.get(doc_id, {}))
        entry["id"] = doc_id
        entry["score"] = round(score, 6)
        out.append(entry)
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_fusion_search.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_search.py
git commit -m "feat(cortex-vec): fusion.search() coordinates vector+bm25 with graceful degradation"
```

---

## Task 10: store.py — rebuild/upsert/delete 與 BM25 lockstep

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`
- Test: `cortex-vec/tests/test_lockstep.py`

說明：`cmd_rebuild` / `cmd_upsert` / `cmd_delete` 在維護 ChromaDB 的同時，同步維護 BM25 索引。抽出一個建立 bm25 doc 的 helper，避免重複。

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_lockstep.py`：

```python
from cortex_vec import store, parser


def test_bm25_doc_from_file_fields():
    text = "---\ntitle: Nginx 憑證\nrepos: [libsynow3, nginx]\n---\n# H\n憑證 certbot renew\n"
    fm, body = parser.parse_document(text)
    doc = store.bm25_doc_from_fields("Notes/Nginx/cert.md", fm, body)
    assert doc["id"] == "Notes/Nginx/cert.md"
    assert doc["title"] == "Nginx 憑證"
    assert doc["type"] == "note"
    assert doc["category"] == "Nginx"
    assert "libsynow3" in doc["repos"] and "nginx" in doc["repos"]
    assert doc["summary"]  # extracted first content line
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_lockstep.py -v`
Expected: FAIL（`store` has no attribute `bm25_doc_from_fields`）。

- [ ] **Step 3: 實作 helper 並接上生命週期**

在 `cortex-vec/src/cortex_vec/store.py` 頂部 import 區加：

```python
from .bm25 import BM25Index
from .config import BM25_DIR
```

（`config` 已 import 多個名稱，將 `BM25_DIR` 併入既有的 `from .config import ...` 行亦可。）

在 `vector_stream` 之前加 helper：

```python
def bm25_doc_from_fields(rel_path, fm, body):
    """Build a BM25 doc record dict from a parsed note."""
    doc_type, category = classify_path(rel_path)
    repos_str = fm.get("repos", "")
    repos = [r.strip() for r in repos_str.split(",") if r.strip()] if repos_str else []
    if doc_type == "project" and category and category not in repos:
        repos.insert(0, category)
    return {
        "id": rel_path,
        "title": fm.get("title", rel_path.rsplit("/", 1)[-1].removesuffix(".md")),
        "body": body,
        "summary": extract_summary(body),
        "tags": fm.get("tags", ""),
        "repos": repos,
        "type": doc_type,
        "category": category,
    }
```

在 `cmd_rebuild` 結尾（`print(f"Rebuilt: ...")` 之前）加入 BM25 全建：把每篇 note 的 doc 蒐集起來，一次 build。具體做法——在 `cmd_rebuild` 的 `for md_file in scan_path.rglob("*.md"):` 迴圈內、`fm, body = parse_document(text)` 之後，收集：

```python
            bm25_docs.append(bm25_doc_from_fields(rel_path, fm, body))
```

並在進入 `for scan_dir in scan_dirs:` 迴圈前初始化 `bm25_docs = []`，在 `print(f"Rebuilt: ...")` 之前加：

```python
    bm25_index = BM25Index(BM25_DIR)
    bm25_index.build_from_docs(bm25_docs)
    bm25_index.save()
    print(f"BM25: {bm25_index.count()} notes indexed")
```

在 `cmd_upsert` 結尾（`print(f"Upserted: ...")` 之前）加：

```python
    bm25_index = BM25Index(BM25_DIR)
    try:
        bm25_index.load()
    except FileNotFoundError:
        bm25_index.build_from_docs([])
    bm25_index.upsert(bm25_doc_from_fields(rel_path, fm, body))
    bm25_index.save()
```

在 `cmd_delete` 的 `_delete_stale_entries` 之後加：

```python
    bm25_index = BM25Index(BM25_DIR)
    try:
        bm25_index.load()
        bm25_index.delete(rel_path)
        bm25_index.save()
    except FileNotFoundError:
        pass
```

最後，更新 `cmd_status` 讓它一併顯示 BM25 索引狀態（spec §8）。在 `cmd_status` 的 `print(f"Vault:      {vault}")` 之前加：

```python
    try:
        bm25_index = BM25Index(BM25_DIR)
        bm25_index.load()
        bm25_count = bm25_index.count()
    except Exception:
        bm25_count = 0
    print(f"BM25:       {bm25_count} notes")
    if total and not bm25_count:
        print("  WARNING: BM25 index empty — run rebuild", file=sys.stderr)
```

（`total` 是 `cmd_status` 既有的 vector entry 數變數。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_lockstep.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/store.py cortex-vec/tests/test_lockstep.py
git commit -m "feat(cortex-vec): maintain BM25 index in lockstep on rebuild/upsert/delete"
```

---

## Task 11: cmd_search 改用 fusion + CLI flags + status

**Files:**
- Modify: `cortex-vec/src/cortex_vec/store.py`
- Modify: `cortex-vec/src/cortex_vec/cli.py`
- Test: `cortex-vec/tests/test_cmd_search.py`

- [ ] **Step 1: 寫失敗測試（monkeypatch fusion.search）**

Create `cortex-vec/tests/test_cmd_search.py`：

```python
import json
from types import SimpleNamespace
from cortex_vec import store, fusion


def test_cmd_search_uses_fusion(monkeypatch, capsys):
    captured = {}

    def fake_search(query, n=5, where=None, use_bm25=True, use_vector=True):
        captured["query"] = query
        captured["where"] = where
        captured["use_bm25"] = use_bm25
        return [{"id": "Notes/Nginx/cert-renew.md", "score": 0.42, "title": "Nginx 憑證",
                 "type": "note", "repo": "", "category": "Nginx", "tags": "", "summary": "certbot"}]

    monkeypatch.setattr(fusion, "search", fake_search)
    args = SimpleNamespace(query="nginx 憑證", repo=None, type=None, category=None,
                           n=5, no_bm25=False, no_vector=False)
    store.cmd_search(args)

    out = capsys.readouterr().out.strip()
    entry = json.loads(out)
    assert entry["id"] == "Notes/Nginx/cert-renew.md"
    assert captured["query"] == "nginx 憑證"
    assert captured["use_bm25"] is True


def test_cmd_search_no_bm25_flag(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(fusion, "search",
                        lambda query, n=5, where=None, use_bm25=True, use_vector=True:
                        seen.update(use_bm25=use_bm25) or [])
    args = SimpleNamespace(query="x", repo=None, type=None, category=None,
                           n=5, no_bm25=True, no_vector=False)
    store.cmd_search(args)
    assert seen["use_bm25"] is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_cmd_search.py -v`
Expected: FAIL（現有 `cmd_search` 直接打 ChromaDB，未用 fusion；且 args 無 `no_bm25`）。

- [ ] **Step 3: 改寫 store.cmd_search**

把 `cortex-vec/src/cortex_vec/store.py` 的整個 `cmd_search` 函式（目前 `def cmd_search(args):` 到檔尾）替換成：

```python
def cmd_search(args):
    """Hybrid search across the vault (vector + BM25, RRF-fused)."""
    import json

    from . import fusion

    where = _build_where(
        repo=getattr(args, "repo", None),
        type=getattr(args, "type", None),
        category=getattr(args, "category", None),
    )
    results = fusion.search(
        args.query,
        n=args.n or 5,
        where=where,
        use_bm25=not getattr(args, "no_bm25", False),
        use_vector=not getattr(args, "no_vector", False),
    )
    for entry in results:
        print(json.dumps(entry, ensure_ascii=False))
```

- [ ] **Step 4: 改 cli.py 加 flags + eval 子命令**

把 `cortex-vec/src/cortex_vec/cli.py` 的 search parser 區塊改為（在 `p_search.add_argument("--n", ...)` 之後加兩行 flag）：

```python
    p_search.add_argument("--no-bm25", action="store_true", help="Disable BM25 stream")
    p_search.add_argument("--no-vector", action="store_true", help="Disable vector stream")
```

在 `p_search` 區塊之後、`args = parser.parse_args()` 之前加 eval 子命令：

```python
    p_eval = sub.add_parser("eval", help="Run retrieval eval / propose queries")
    p_eval.add_argument("action", choices=["run", "propose"], help="run scorecard or propose queries")
    p_eval.add_argument("--queries", required=True, help="Path to queries.jsonl")
    p_eval.add_argument("--adapters", default="grep,vector,bm25,hybrid",
                        help="Comma-separated adapters to run")
    p_eval.add_argument("--k", type=int, default=5, help="Cutoff K")
    p_eval.add_argument("--out", help="Scorecard output path (markdown)")
```

把 `commands` dict 加一行（在 `"search": store.cmd_search,` 之後）：

```python
        "eval": _dispatch_eval,
```

並在 `from . import store` 之後加：

```python
    def _dispatch_eval(args):
        from .eval import run
        run.dispatch(args)
```

（`_dispatch_eval` 定義需在 `commands` dict 之前。）

- [ ] **Step 5: 跑測試 + 全套 + Commit**

Run:
```bash
cd cortex-vec && pytest tests/test_cmd_search.py -v && pytest -q
```
Expected: `test_cmd_search.py` 2 passed；全套到目前為止全綠。

```bash
git add cortex-vec/src/cortex_vec/store.py cortex-vec/src/cortex_vec/cli.py cortex-vec/tests/test_cmd_search.py
git commit -m "feat(cortex-vec): cmd_search via fusion + --no-bm25/--no-vector + eval subcommand"
```

---

## Task 12: eval/adapters.py — 四種 adapter

**Files:**
- Create: `cortex-vec/src/cortex_vec/eval/adapters.py`
- Test: `cortex-vec/tests/test_adapters.py`

說明：grep / bm25 / hybrid 三種以本地 fixture 測試（不需網路）；vector adapter 包裝 `store.vector_stream`，以 monkeypatch 測試介面契約。所有 adapter 的 `query()` 回傳 `[(base_path, score)]`。

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_adapters.py`：

```python
from cortex_vec.eval import adapters


def _docs():
    return [
        {"id": "Notes/Nginx/cert-renew.md", "title": "Nginx 憑證自動更新",
         "body": "certbot nginx TLS certificate renew", "summary": "certbot",
         "tags": "", "repos": [], "type": "note", "category": "Nginx"},
        {"id": "Notes/Linux/oom.md", "title": "Linux OOM",
         "body": "out of memory dmesg killer", "summary": "oom",
         "tags": "", "repos": [], "type": "note", "category": "Linux"},
    ]


def test_grep_adapter_ranks_by_term_overlap():
    a = adapters.GrepAdapter()
    a.init(_docs())
    ranked = a.query("certbot certificate renew", k=5)
    assert ranked[0][0] == "Notes/Nginx/cert-renew.md"
    a.teardown()


def test_bm25_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters.config, "BM25_DIR", tmp_path / "bm25")
    a = adapters.BM25Adapter()
    a.init(_docs())
    ranked = a.query("oom dmesg", k=5)
    assert ranked[0][0] == "Notes/Linux/oom.md"
    a.teardown()


def test_hybrid_adapter_calls_fusion(monkeypatch):
    monkeypatch.setattr(adapters.fusion, "search",
                        lambda query, n, where=None: [{"id": "Notes/Linux/oom.md", "score": 0.5}])
    a = adapters.HybridAdapter()
    a.init(_docs())
    ranked = a.query("oom", k=5)
    assert ranked[0][0] == "Notes/Linux/oom.md"
    a.teardown()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_adapters.py -v`
Expected: FAIL（no module `cortex_vec.eval.adapters`）。

- [ ] **Step 3: 實作 adapters.py**

Create `cortex-vec/src/cortex_vec/eval/adapters.py`：

```python
"""Pluggable retrieval adapters for eval: grep / vector / bm25 / hybrid.

Each adapter exposes init(docs) / query(q, k) -> [(base_path, score)] / teardown().
`docs` is a list of dicts with id/title/body/summary/tags/repos/type/category.
"""
from .. import bm25, config, fusion, store
from ..tokenize import tokenize


class GrepAdapter:
    """Zero-dependency keyword baseline: rank by query-term frequency in title+body."""
    name = "grep"

    def init(self, docs):
        self._docs = [(d["id"], tokenize(f"{d.get('title','')}\n{d.get('body','')}")) for d in docs]

    def query(self, q, k):
        terms = set(tokenize(q))
        scored = []
        for doc_id, toks in self._docs:
            score = sum(1 for t in toks if t in terms)
            if score > 0:
                scored.append((doc_id, float(score)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def teardown(self):
        self._docs = []


class BM25Adapter:
    """Isolated BM25 index over the corpus docs."""
    name = "bm25"

    def init(self, docs):
        self._idx = bm25.BM25Index(config.BM25_DIR.parent / "bm25_eval")
        self._idx.build_from_docs(docs)

    def query(self, q, k):
        return [(h["id"], h["score"]) for h in self._idx.search(q, n=k)]

    def teardown(self):
        self._idx = None


class VectorAdapter:
    """Production vector stream (ChromaDB + OpenAI). Requires a built index.

    init() is a no-op: it queries the live vector store the same way production does.
    Use only against a vault whose vector index is already built.
    """
    name = "vector"

    def init(self, docs):
        pass

    def query(self, q, k):
        return [(it["id"], it["score"]) for it in store.vector_stream(q, k)]

    def teardown(self):
        pass


class HybridAdapter:
    """Full production fusion.search (vector + BM25, RRF)."""
    name = "hybrid"

    def init(self, docs):
        pass

    def query(self, q, k):
        return [(it["id"], it["score"]) for it in fusion.search(q, n=k)]

    def teardown(self):
        pass


REGISTRY = {
    "grep": GrepAdapter,
    "bm25": BM25Adapter,
    "vector": VectorAdapter,
    "hybrid": HybridAdapter,
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_adapters.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/eval/adapters.py cortex-vec/tests/test_adapters.py
git commit -m "feat(cortex-vec): add eval adapters (grep/vector/bm25/hybrid)"
```

---

## Task 13: eval/report.py — markdown scorecard

**Files:**
- Create: `cortex-vec/src/cortex_vec/eval/report.py`
- Test: `cortex-vec/tests/test_report.py`

- [ ] **Step 1: 寫失敗測試**

Create `cortex-vec/tests/test_report.py`：

```python
from cortex_vec.eval import report


def test_scorecard_contains_adapter_table():
    summary = {
        "by_adapter": {
            "grep": {"n": 15, "p": 0.267, "r": 0.95, "mrr": 0.7, "hit_rate": 1.0, "latency_p50": 0.5},
            "hybrid": {"n": 15, "p": 0.578, "r": 0.967, "mrr": 0.88, "hit_rate": 1.0, "latency_p50": 14.0},
        },
        "by_type": {
            "hybrid/single-note": {"n": 10, "p": 0.6, "r": 1.0, "mrr": 0.9, "hit_rate": 1.0, "latency_p50": 13.0},
        },
    }
    md = report.render(summary, meta={"corpus": "cortex-vault-v1", "k": 5, "n": 15})
    assert "cortex-vault-v1" in md
    assert "| grep |" in md
    assert "| hybrid |" in md
    assert "0.578" in md
    assert "single-note" in md
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_report.py -v`
Expected: FAIL（no module `cortex_vec.eval.report`）。

- [ ] **Step 3: 實作 report.py**

Create `cortex-vec/src/cortex_vec/eval/report.py`：

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd cortex-vec && pytest tests/test_report.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/eval/report.py cortex-vec/tests/test_report.py
git commit -m "feat(cortex-vec): add markdown scorecard renderer"
```

---

## Task 14: eval/run.py — runner + propose + 接上 CLI

**Files:**
- Create: `cortex-vec/src/cortex_vec/eval/run.py`
- Test: `cortex-vec/tests/test_run.py`

說明：`run.dispatch(args)` 依 `args.action` 分派 `run`（跑各 adapter、印 summary、寫 scorecard）或 `propose`（用 OpenAI 從 notes 提候選 query；網路相關，只做薄封裝，不在單元測試覆蓋）。runner 用 vault 的 note 內容建 corpus docs（給 grep/bm25 用），vector/hybrid adapter 走 live 索引。

- [ ] **Step 1: 寫失敗測試（測純邏輯：run_adapters 用假 adapter）**

Create `cortex-vec/tests/test_run.py`：

```python
from cortex_vec.eval import run


class _FakeAdapter:
    name = "fake"

    def __init__(self, ranking):
        self._r = ranking

    def init(self, docs):
        pass

    def query(self, q, k):
        return self._r

    def teardown(self):
        pass


def test_run_adapters_produces_rows():
    queries = [
        {"id": "q1", "query": "nginx", "gold": ["Notes/Nginx/cert-renew.md"], "type": "single-note"},
        {"id": "q2", "query": "oom", "gold": ["Notes/Linux/oom.md"], "type": "single-note"},
    ]
    adapter = _FakeAdapter([("Notes/Nginx/cert-renew.md", 1.0), ("Notes/Linux/oom.md", 0.5)])
    rows = run.run_adapter(adapter, queries, k=5)
    assert len(rows) == 2
    assert rows[0]["adapter"] == "fake"
    assert rows[0]["hit"] is True              # q1 gold at rank 1
    assert rows[0]["reciprocal_rank"] == 1.0
    assert rows[1]["reciprocal_rank"] == 0.5   # q2 gold at rank 2
    assert "latency_ms" in rows[0]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd cortex-vec && pytest tests/test_run.py -v`
Expected: FAIL（no module `cortex_vec.eval.run`）。

- [ ] **Step 3: 實作 run.py**

Create `cortex-vec/src/cortex_vec/eval/run.py`：

```python
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
```

- [ ] **Step 4: 跑測試 + 全套**

Run:
```bash
cd cortex-vec && pytest tests/test_run.py -v && pytest -q
```
Expected: `test_run.py` 1 passed；全套全綠。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/eval/run.py cortex-vec/tests/test_run.py
git commit -m "feat(cortex-vec): add eval runner + LLM query-propose helper"
```

---

## Task 15: 端對端煙霧測試 + 文件更新

**Files:**
- Modify: `cortex-vec/README.md`（若無則 Create）
- Modify: `README.md`（repo root：更新 cortex-vec 章節）

- [ ] **Step 1: 真實 vault 煙霧測試（手動驗證）**

Run（需已 `genesis` 設好 vault 且有 `OPENAI_API_KEY`）：
```bash
cortex-vec rebuild
cortex-vec status
cortex-vec search "nginx 憑證" --n 5
cortex-vec search "nginx 憑證" --no-vector --n 5   # BM25-only
cortex-vec search "nginx 憑證" --no-bm25 --n 5     # vector-only
```
Expected:
- `status` 顯示 vector entries 與 `BM25: N notes indexed`。
- 三種 search 都回 JSONL；`--no-vector` 在沒有網路/API key 時仍可運作。

- [ ] **Step 2: 建立 eval corpus（半自動）**

Run:
```bash
cortex-vec eval propose --queries cortex-vec/eval-data/cortex-vault-v1.jsonl
# 人工編輯該檔：修正 query 措辭、確認/補 gold（可多個）、刪掉不具代表性的、補 cross-note/概念類，湊到 15–30 題
cortex-vec eval run --queries cortex-vec/eval-data/cortex-vault-v1.jsonl \
  --adapters grep,vector,bm25,hybrid --k 5 \
  --out docs/benchmarks/$(date +%F)-cortex-vault-v1.md
```
Expected: 印出逐題 NDJSON，scorecard 寫到 `docs/benchmarks/`，可見 `hybrid` vs `vector` 的 P@5 / R@5 / MRR 對比。

- [ ] **Step 3: 更新文件**

在 repo root `README.md` 的 `## cortex-vec CLI` 章節，把檢索描述更新為 hybrid，並加上：

```markdown
### Hybrid 檢索（0.4.0+）

`cortex-vec search` 現在是 BM25 + vector 的 RRF hybrid：
- BM25 補上精確詞（函式名、repo 名、issue ID）的召回；中英混合用 jieba 分詞。
- 沒有 `OPENAI_API_KEY` / 無網路時自動退化為 BM25-only。
- `--no-bm25` / `--no-vector` 可單獨測試一路。

### 檢索評測

```bash
cortex-vec eval propose --queries eval-data/cortex-vault-v1.jsonl   # LLM 提候選，人工確認
cortex-vec eval run --queries eval-data/cortex-vault-v1.jsonl \
  --adapters grep,vector,bm25,hybrid --out docs/benchmarks/<date>-cortex-vault-v1.md
```
\```

- [ ] **Step 4: 跑全套測試**

Run: `cd cortex-vec && pytest -q`
Expected: 全綠。

- [ ] **Step 5: Commit**

```bash
git add README.md cortex-vec/README.md docs/benchmarks/ cortex-vec/eval-data/ 2>/dev/null; git add -A
git commit -m "docs(cortex-vec): document hybrid retrieval + eval workflow; add first scorecard"
```

---

## 完成定義（Plan 1）

- `cortex-vec search` 走 hybrid（BM25 + vector RRF），輸出格式與舊版相容，`cortex-query` skill 無需改動。
- 沒有 API key / 網路時自動 BM25-only。
- `cortex-vec status` 顯示兩索引數量。
- `rebuild` / `upsert` / `delete` 維持兩索引 lockstep。
- `cortex-vec eval run` 能產出 grep / vector / bm25 / hybrid 的 P@5 / R@5 / MRR / hit scorecard。
- 第一份 scorecard 進 `docs/benchmarks/`，量出 hybrid vs vector 的 lift。
- 全套 pytest 綠。

**本 plan 刻意保留給 Plan 2 的項目（避免誤導）：**
- `retrieval.max_per_repo` 設定鍵已在 config 預留（預設 0 = 不限），但 `fusion.search` 的 max-N-per-repo 多樣化尚未套用——與 graph-boost 一起在 Plan 2 實作。
- eval 的 `--vault-ref <git-commit>` 快照（spec §5 的選用項）未實作；本 plan 的 eval 跑「目前 vault」，四個 adapter 看相同 live 內容即可。

**接續（Plan 2，待本 plan 的 scorecard 數據判斷是否值得）**：synonym 展開、wikilink graph-boost、LLM rerank、max_per_repo 多樣化（spec Phase 3–5 + §4 多樣化）。
