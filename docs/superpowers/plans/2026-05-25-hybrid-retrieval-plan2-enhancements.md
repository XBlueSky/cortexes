# Hybrid 檢索強化（Plan 2：Phase 3-5 + 多樣化）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Plan 1 的 BM25+vector RRF hybrid 之上，加入四個可選、預設關閉、各自可被 eval 量測的檢索強化：synonym 展開、wikilink graph-boost、LLM rerank、max-per-repo 多樣化。

**Architecture:** 全部疊在 `cortex-vec` 的 `fusion.search()` pipeline 上：streams → RRF → graph-boost → diversify → rerank → top-n。新增 `synonyms.py`（靜態同義詞表）、`graph.py`（從 vault `[[wikilinks]]` lazy 建鄰接 + BFS boost）、`rerank.py`（LLM 重排，複用 OpenAI）。每個 feature 由 `~/.cortex/config.json` 的 `retrieval` flag 或 CLI flag 開關，預設全關 → 行為與 Plan 1 完全相同。

**Tech Stack:** Python 3.8+、既有 cortex-vec 模組（fusion/bm25/store/tokenize/parser/config）、OpenAI（rerank，複用既有 client）、pytest。

**Spec:** `docs/superpowers/specs/2026-05-25-hybrid-retrieval-eval-design.md`（§4 pipeline、§7 config、Plan 2 deferred 清單）。

**前置：** Plan 1 已完成於 branch `feat/hybrid-retrieval-eval`（HEAD f013565，36 tests passing）。本 plan 直接疊在其上。

**eval-gating 註記：** 這四個 feature 在 spec 中是 eval-gated；使用者已知悉目前尚無 scorecard 數據而選擇先實作。因此每個 feature 都做成獨立可開關、可被 `cortex-vec eval` 量測 lift，實作後請逐一量測、lift 不顯著者保持預設關閉或回退。

---

## File Structure

| 檔案 | 動作 | 職責 |
|---|---|---|
| `src/cortex_vec/config.py` | Modify | `_RETRIEVAL_DEFAULTS` 加 Plan 2 keys |
| `src/cortex_vec/synonyms.py` | Create | `SYNONYM_GROUPS` 資料 + `synonyms_for(tokens)` |
| `src/cortex_vec/bm25.py` | Modify | `search()` 加 `synonym_weight` 參數 |
| `src/cortex_vec/parser.py` | Modify | 加 `extract_wikilinks(text)` |
| `src/cortex_vec/graph.py` | Create | 從 vault 建 wikilink 鄰接 + `boost()` |
| `src/cortex_vec/rerank.py` | Create | LLM rerank（複用 OpenAI），預設關 |
| `src/cortex_vec/fusion.py` | Modify | pipeline 串接 synonym/diversify/graph/rerank + flags |
| `src/cortex_vec/cli.py` | Modify | search 加 `--rerank` / `--graph` flags |
| `README.md` | Modify | 文件更新 |
| `tests/test_*.py` | Create | 各 feature 單元測試 |

整合後 `fusion.search` 的 pipeline：
```
streams(vector + bm25[+synonym]) → rrf_fuse → [graph-boost] → diversify(max_per_repo) → [rerank top-window] → top-n
```

---

## Task 1: config — Plan 2 retrieval 設定鍵

**Files:**
- Modify: `cortex-vec/src/cortex_vec/config.py`
- Test: `cortex-vec/tests/test_config_plan2.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_config_plan2.py`:

```python
from cortex_vec import config


def test_plan2_retrieval_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    rc = config.get_retrieval_config()
    assert rc["synonym_weight"] == 0.0
    assert rc["graph"] is False
    assert rc["graph_hops"] == 1
    assert rc["graph_weight"] == 0.1
    assert rc["graph_top_k"] == 5
    assert rc["rerank"] is False
    assert rc["rerank_model"] == "gpt-5.4-mini"
    assert rc["rerank_window"] == 15
    # Plan 1 keys still present
    assert rc["rrf_k"] == 60
    assert rc["max_per_repo"] == 0


def test_plan2_override(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {"retrieval": {"graph": True, "synonym_weight": 0.7}})
    rc = config.get_retrieval_config()
    assert rc["graph"] is True
    assert rc["synonym_weight"] == 0.7
    assert rc["rerank"] is False  # untouched default
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_config_plan2.py -v` → FAIL (keys absent).

- [ ] **Step 3: 改 config.py** — 把 `_RETRIEVAL_DEFAULTS` 字典（Plan 1 建立的）整個替換為（保留 Plan 1 的四個鍵、加入 Plan 2 的鍵）：

```python
_RETRIEVAL_DEFAULTS = {
    # Plan 1
    "rrf_k": 60,
    "w_bm25": 0.4,
    "w_vec": 0.6,
    "max_per_repo": 0,
    # Plan 2
    "synonym_weight": 0.0,      # 0 = synonym expansion off
    "graph": False,
    "graph_hops": 1,
    "graph_weight": 0.1,
    "graph_top_k": 5,
    "rerank": False,
    "rerank_model": "gpt-5.4-mini",
    "rerank_window": 15,
}
```

(`get_retrieval_config()` 不需改——它已 merge `cfg["retrieval"]` over 這個 dict。)

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_config_plan2.py -v` → PASS (2 passed). 也跑 `pytest tests/test_config.py` 確認 Plan 1 config 測試仍綠。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/config.py cortex-vec/tests/test_config_plan2.py
git commit -m "$(printf 'feat(cortex-vec): add Plan 2 retrieval config keys (synonym/graph/rerank)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 2: synonyms.py — 同義詞表 + 展開

**Files:**
- Create: `cortex-vec/src/cortex_vec/synonyms.py`
- Test: `cortex-vec/tests/test_synonyms.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_synonyms.py`:

```python
from cortex_vec import synonyms
from cortex_vec.tokenize import tokenize


def test_synonyms_bidirectional():
    res = set(synonyms.synonyms_for(tokenize("dsm")))
    # whatever "diskstation" tokenizes to should be among dsm's synonyms
    assert set(tokenize("diskstation")) <= res
    res2 = set(synonyms.synonyms_for(tokenize("diskstation")))
    assert "dsm" in res2


def test_synonyms_excludes_originals():
    toks = tokenize("cert")
    res = synonyms.synonyms_for(toks)
    assert "cert" not in res          # original token excluded
    assert set(tokenize("certificate")) <= set(res)


def test_synonyms_unknown_token_empty():
    assert synonyms.synonyms_for(tokenize("zzzznotaword")) == []
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_synonyms.py -v` → FAIL (no module).

- [ ] **Step 3: 實作 synonyms.py** — Create `cortex-vec/src/cortex_vec/synonyms.py`:

```python
"""Static synonym groups (Synology jargon + common zh/en tech terms).

Groups are written in human-readable form; at first use each term is run
through the same tokenizer as the index/query, so the synonym lookup lives in
the SAME token space as BM25 (lowercased, stemmed, jieba-segmented).
"""
from .tokenize import tokenize

SYNONYM_GROUPS = [
    ["dsm", "diskstation"],
    ["srm", "router manager"],
    ["套件", "package", "spk"],
    ["憑證", "certificate", "cert", "tls", "ssl"],
    ["週報", "weekly report"],
    ["登入", "login", "signin", "authentication", "auth"],
    ["記憶體", "memory", "ram"],
    ["效能", "performance", "perf"],
    ["編譯", "build", "compile"],
    ["測試", "test", "unittest"],
    ["設定", "config", "configuration", "設定檔"],
]

_index = None  # token -> set of synonym tokens (built lazily)


def _build_index():
    global _index
    _index = {}
    for group in SYNONYM_GROUPS:
        group_tokens = set()
        for term in group:
            group_tokens.update(tokenize(term))
        for tok in group_tokens:
            _index.setdefault(tok, set()).update(group_tokens - {tok})


def synonyms_for(tokens):
    """Return extra synonym tokens for the given query tokens (sorted, originals excluded)."""
    if _index is None:
        _build_index()
    originals = set(tokens)
    extra = set()
    for tok in originals:
        extra.update(_index.get(tok, set()))
    return sorted(extra - originals)
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_synonyms.py -v` → PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/synonyms.py cortex-vec/tests/test_synonyms.py
git commit -m "$(printf 'feat(cortex-vec): add synonym groups + token-space expansion\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 3: bm25.search — synonym_weight 參數

**Files:**
- Modify: `cortex-vec/src/cortex_vec/bm25.py`
- Test: `cortex-vec/tests/test_bm25_synonym.py`

READ `bm25.py` first. Its `search(self, query, n=5, where=None)` currently: tokenizes query once (`q_toks = tokenize(query)`, `q_tokens = set(q_toks)`), computes `scores = self._bm25.get_scores(q_toks)`, ranks, gates by token overlap (`set(rec["tokens"]) & q_tokens`), filters by `_matches`, builds display dicts. You are adding an optional `synonym_weight=0.0` param.

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_bm25_synonym.py`:

```python
from cortex_vec import bm25


def _docs():
    return [
        {"id": "Notes/A/dsm.md", "title": "DSM 設定",
         "body": "diskstation manager 設定教學", "summary": "dsm",
         "tags": "", "repos": [], "type": "note", "category": "A"},
        {"id": "Notes/B/cert.md", "title": "憑證更新",
         "body": "certificate renew 教學", "summary": "cert",
         "tags": "", "repos": [], "type": "note", "category": "B"},
    ]


def test_synonym_weight_surfaces_synonym_only_match(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    # query "dsm" without synonyms: only the dsm doc (which literally contains "dsm"? it has DSM in title)
    plain = [h["id"] for h in idx.search("diskstation", n=5, synonym_weight=0.0)]
    withsyn = [h["id"] for h in idx.search("diskstation", n=5, synonym_weight=0.7)]
    # "diskstation" already in the dsm doc body, so it's found either way; assert synonym path
    # at least still returns the dsm doc and does not crash
    assert "Notes/A/dsm.md" in withsyn
    # a query that only matches via synonym: "cert" is a synonym of 憑證/certificate
    syn_hits = [h["id"] for h in idx.search("cert", n=5, synonym_weight=0.7)]
    assert "Notes/B/cert.md" in syn_hits


def test_synonym_weight_zero_is_plain(tmp_path):
    idx = bm25.BM25Index(tmp_path / "bm25")
    idx.build_from_docs(_docs())
    a = idx.search("certificate", n=5, synonym_weight=0.0)
    b = idx.search("certificate", n=5)  # default
    assert [h["id"] for h in a] == [h["id"] for h in b]
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_bm25_synonym.py -v` → FAIL (`search() got unexpected keyword 'synonym_weight'`).

- [ ] **Step 3: 改 bm25.search** — 在 `bm25.py` 的 `search` 方法簽章加 `synonym_weight=0.0`，並在算分後、gate 前加入同義詞分數合併。將 `search` 方法的開頭（取得 `q_toks`/`q_tokens`/`scores` 的部分）改為：

```python
    def search(self, query, n=5, where=None, synonym_weight=0.0):
        """Return up to n display dicts, best-first, filtered by `where`.

        If synonym_weight > 0, synonym tokens (from synonyms.synonyms_for) are
        scored separately and added at the given weight, and are also admitted
        to the token-overlap gate so synonym-only matches can surface.
        """
        if not self.docs:
            return []
        if self._bm25 is None:
            self._reindex()
        q_toks = tokenize(query)
        q_tokens = set(q_toks)
        scores = self._bm25.get_scores(q_toks)
        if synonym_weight > 0:
            from .synonyms import synonyms_for
            syn_toks = synonyms_for(q_toks)
            if syn_toks:
                scores = scores + synonym_weight * self._bm25.get_scores(syn_toks)
                q_tokens |= set(syn_toks)
```

(The rest of the method — `ranked = sorted(zip(self.docs, scores), ...)`, the token-overlap gate `if not (set(rec["tokens"]) & q_tokens): continue`, `_matches`, display dict build, `if len(out) >= n: break` — stays exactly as-is. `scores` is a numpy array from rank_bm25, so `scores + weight * other_scores` is a valid elementwise op.)

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_bm25_synonym.py tests/test_bm25.py -v` → PASS (Plan 1 bm25 tests still pass; 2 new pass).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/bm25.py cortex-vec/tests/test_bm25_synonym.py
git commit -m "$(printf 'feat(cortex-vec): bm25.search synonym_weight (weighted synonym expansion)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 4: fusion — thread synonym_weight into BM25 stream

**Files:**
- Modify: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_synonym.py`

READ `fusion.py`. `_bm25_stream(query, n, where)` currently does `idx = bm25.BM25Index(BM25_DIR); idx.load(); return idx.search(query, n, where)`. `search()` reads `rc = get_retrieval_config()`. You will pass `synonym_weight` from config through to `bm25.search`.

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_fusion_synonym.py`:

```python
from cortex_vec import fusion, store, bm25


def test_bm25_stream_passes_synonym_weight(monkeypatch):
    captured = {}

    class _Idx:
        def __init__(self, *a, **k):
            pass

        def load(self):
            pass

        def search(self, query, n, where=None, synonym_weight=0.0):
            captured["synonym_weight"] = synonym_weight
            return []

    monkeypatch.setattr(bm25, "BM25Index", _Idx)
    fusion._bm25_stream("q", 5, None, synonym_weight=0.7)
    assert captured["synonym_weight"] == 0.7
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_fusion_synonym.py -v` → FAIL (`_bm25_stream` takes 3 args).

- [ ] **Step 3: 改 fusion._bm25_stream 與 search** — 把 `_bm25_stream` 改為接受並轉傳 `synonym_weight`：

```python
def _bm25_stream(query, n, where, synonym_weight=0.0):
    """Load the persisted BM25 index and search; return [] on any failure."""
    from . import bm25
    try:
        idx = bm25.BM25Index(BM25_DIR)
        idx.load()
        return idx.search(query, n, where, synonym_weight=synonym_weight)
    except Exception:
        return []
```

並在 `search()` 中把 config 的 `synonym_weight` 傳進去——找到 `streams["bm25"] = _bm25_stream(query, n, where)` 這行，改為：

```python
        streams["bm25"] = _bm25_stream(query, n, where, synonym_weight=rc["synonym_weight"])
```

(`rc = get_retrieval_config()` 已在 `search()` 開頭取得。)

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_fusion_synonym.py tests/test_fusion_search.py -v` → PASS (new + Plan 1 fusion tests).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_synonym.py
git commit -m "$(printf 'feat(cortex-vec): thread synonym_weight from config into BM25 stream\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 5: fusion._diversify — max-per-repo 多樣化

**Files:**
- Modify: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_diversify.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_fusion_diversify.py`:

```python
from cortex_vec import fusion


def test_diversify_caps_per_repo():
    fused = [("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.6)]
    display = {
        "a": {"repo": "X"}, "b": {"repo": "X"}, "c": {"repo": "X"}, "d": {"repo": "Y"},
    }
    out = fusion._diversify(fused, display, max_per_repo=2)
    ids = [i for i, _ in out]
    # X capped at 2 (a,b kept; c demoted), d (repo Y) surfaces; c appended after
    assert ids[:3] == ["a", "b", "d"]
    assert set(ids) == {"a", "b", "c", "d"}  # nothing dropped, only reordered


def test_diversify_zero_is_noop():
    fused = [("a", 0.9), ("b", 0.8)]
    display = {"a": {"repo": "X"}, "b": {"repo": "X"}}
    assert fusion._diversify(fused, display, max_per_repo=0) == fused
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_fusion_diversify.py -v` → FAIL (no `_diversify`).

- [ ] **Step 3: 加 _diversify 並接入 search** — 在 `fusion.py` 的 `search` 函式之前加：

```python
def _diversify(fused, display, max_per_repo):
    """Cap results per repo: keep best-`max_per_repo` per repo first, then append
    the rest in original order (nothing dropped, only reordered). 0 = no-op.
    Docs with an empty repo are never capped.
    """
    if not max_per_repo:
        return fused
    counts = {}
    primary, overflow = [], []
    for doc_id, score in fused:
        repo = (display.get(doc_id) or {}).get("repo", "")
        if not repo:
            primary.append((doc_id, score))
            continue
        if counts.get(repo, 0) < max_per_repo:
            counts[repo] = counts.get(repo, 0) + 1
            primary.append((doc_id, score))
        else:
            overflow.append((doc_id, score))
    return primary + overflow
```

並在 `search()` 中，`fused = rrf_fuse(...)` 之後、建立 `out` 的迴圈之前加：

```python
    fused = _diversify(fused, display, rc["max_per_repo"])
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_fusion_diversify.py tests/test_fusion_search.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_diversify.py
git commit -m "$(printf 'feat(cortex-vec): max-per-repo diversification in fusion\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 6: parser.extract_wikilinks

**Files:**
- Modify: `cortex-vec/src/cortex_vec/parser.py`
- Test: `cortex-vec/tests/test_wikilinks.py`

READ `parser.py` (has `parse_document`, `extract_summary`, `classify_path`; `import re` already present). Add `extract_wikilinks`.

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_wikilinks.py`:

```python
from cortex_vec import parser


def test_extract_wikilinks_basic():
    text = "see [[Web benchmark]] and [[ SYNOTOKEN ]] plus [[A|alias]]."
    links = parser.extract_wikilinks(text)
    assert "Web benchmark" in links
    assert "SYNOTOKEN" in links       # surrounding whitespace stripped
    assert "A" in links               # alias part dropped


def test_extract_wikilinks_none():
    assert parser.extract_wikilinks("no links here") == []


def test_extract_wikilinks_dedup():
    links = parser.extract_wikilinks("[[X]] [[X]] [[Y]]")
    assert sorted(links) == ["X", "Y"]
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_wikilinks.py -v` → FAIL (no `extract_wikilinks`).

- [ ] **Step 3: 加 extract_wikilinks** — 在 `parser.py` 檔尾加：

```python
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text):
    """Return unique wikilink targets from text. Strips surrounding whitespace
    and drops any `|alias` suffix (Obsidian alias syntax)."""
    targets = []
    seen = set()
    for raw in _WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].strip()
        if target and target not in seen:
            seen.add(target)
            targets.append(target)
    return targets
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_wikilinks.py -v` → PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/parser.py cortex-vec/tests/test_wikilinks.py
git commit -m "$(printf 'feat(cortex-vec): parser.extract_wikilinks (Obsidian links + alias)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 7: graph.py — 從 vault 建 wikilink 鄰接

**Files:**
- Create: `cortex-vec/src/cortex_vec/graph.py`
- Test: `cortex-vec/tests/test_graph_build.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_graph_build.py`:

```python
from cortex_vec import graph


def _make_vault(tmp_path):
    notes = tmp_path / "Notes" / "X"
    notes.mkdir(parents=True)
    (notes / "a.md").write_text(
        "---\ntitle: Alpha\n---\nlinks to [[Beta]]\n", encoding="utf-8")
    (notes / "b.md").write_text(
        "---\ntitle: Beta\n---\nlinks to [[Alpha]] and [[Ghost]]\n", encoding="utf-8")
    return tmp_path


def test_build_graph_resolves_titles_to_paths(tmp_path):
    vault = _make_vault(tmp_path)
    adjacency = graph.build_graph(vault)
    assert "Notes/X/b.md" in adjacency["Notes/X/a.md"]   # a -> Beta(b)
    assert "Notes/X/a.md" in adjacency["Notes/X/b.md"]   # b -> Alpha(a)
    # [[Ghost]] is unresolved (no such title) -> skipped, not an error
    assert all("Ghost" not in v for v in adjacency.values())


def test_build_graph_cached(tmp_path):
    vault = _make_vault(tmp_path)
    g1 = graph.build_graph(vault)
    g2 = graph.build_graph(vault)
    assert g1 is g2  # same cached object for same vault path
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_graph_build.py -v` → FAIL (no module).

- [ ] **Step 3: 實作 graph.py（建圖部分）** — Create `cortex-vec/src/cortex_vec/graph.py`:

```python
"""Wikilink graph over the vault, built lazily from markdown and cached per vault.

The vault's `[[Title]]` links form a human-curated graph. We resolve each link
target (a note title) to a base path via a title index (frontmatter `title`
plus the filename stem), then expose adjacency for graph-boosted retrieval.
Unresolved links are skipped (a dangling link is not an error).
"""
from pathlib import Path

from .parser import extract_wikilinks, parse_document

_cache = {}  # str(vault) -> adjacency dict


def build_graph(vault):
    """Return {base_path: set(neighbor_base_path)} for the vault. Cached by path."""
    key = str(vault)
    if key in _cache:
        return _cache[key]

    vault = Path(vault)
    title_to_path = {}
    raw = []  # (base_path, [link targets])

    for scan_dir in ("Notes", "Projects"):
        base = vault / scan_dir
        if not base.is_dir():
            continue
        for md in base.rglob("*.md"):
            rel = str(md.relative_to(vault))
            if "_archive" in rel:
                continue
            text = md.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_document(text)
            stem = md.stem
            title = fm.get("title", stem)
            # Index by both frontmatter title and filename stem.
            title_to_path.setdefault(title, rel)
            title_to_path.setdefault(stem, rel)
            raw.append((rel, extract_wikilinks(body)))

    adjacency = {rel: set() for rel, _ in raw}
    for rel, targets in raw:
        for t in targets:
            dest = title_to_path.get(t)
            if dest and dest != rel:
                adjacency[rel].add(dest)
                adjacency.setdefault(dest, set()).add(rel)  # treat links as bidirectional

    _cache[key] = adjacency
    return adjacency
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_graph_build.py -v` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/graph.py cortex-vec/tests/test_graph_build.py
git commit -m "$(printf 'feat(cortex-vec): build wikilink adjacency graph from vault (cached)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 8: graph.boost — BFS boost over fused candidates

**Files:**
- Modify: `cortex-vec/src/cortex_vec/graph.py`
- Test: `cortex-vec/tests/test_graph_boost.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_graph_boost.py`:

```python
from cortex_vec import graph


def test_boost_promotes_graph_neighbor():
    # candidates: a (top), c (low). adjacency: a <-> c. c is a neighbor of top hit a.
    fused = [("a", 0.50), ("b", 0.40), ("c", 0.10)]
    adjacency = {"a": {"c"}, "c": {"a"}, "b": set()}
    out = graph.boost(fused, adjacency, top_k=1, hops=1, weight=0.5)
    scores = dict(out)
    assert scores["c"] > 0.10           # c boosted (neighbor of top hit a)
    assert scores["a"] == 0.50          # top hit itself unchanged
    # c should now outrank b
    ids = [i for i, _ in out]
    assert ids.index("c") < ids.index("b")


def test_boost_no_neighbors_noop():
    fused = [("a", 0.5), ("b", 0.4)]
    adjacency = {"a": set(), "b": set()}
    assert graph.boost(fused, adjacency, top_k=1, hops=1, weight=0.5) == fused
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_graph_boost.py -v` → FAIL (no `boost`).

- [ ] **Step 3: 加 graph.boost** — 在 `graph.py` 檔尾加：

```python
def _bfs_neighbors(adjacency, seeds, hops):
    """Return {base_path: distance} reachable within `hops` from seeds (excluding seeds)."""
    frontier = set(seeds)
    visited = set(seeds)
    dist = {}
    for d in range(1, hops + 1):
        nxt = set()
        for node in frontier:
            for nb in adjacency.get(node, ()):
                if nb not in visited:
                    visited.add(nb)
                    dist[nb] = d
                    nxt.add(nb)
        frontier = nxt
        if not frontier:
            break
    return dist


def boost(fused, adjacency, top_k=5, hops=1, weight=0.1):
    """Boost candidates that are wikilink-neighbors of the top-`top_k` hits.

    fused: [(doc_id, score)] best-first. Only candidates already in `fused` are
    boosted (no new docs introduced). Boost = weight / (distance + 1). Re-sorted.
    """
    if not fused or weight <= 0:
        return fused
    seeds = [doc_id for doc_id, _ in fused[:top_k]]
    dist = _bfs_neighbors(adjacency, seeds, hops)
    if not dist:
        return fused
    boosted = []
    for doc_id, score in fused:
        if doc_id in dist:
            score = score + weight / (dist[doc_id] + 1)
        boosted.append((doc_id, score))
    boosted.sort(key=lambda kv: kv[1], reverse=True)
    return boosted
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_graph_boost.py -v` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/graph.py cortex-vec/tests/test_graph_boost.py
git commit -m "$(printf 'feat(cortex-vec): graph.boost via BFS over wikilink neighbors\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 9: fusion — integrate graph-boost

**Files:**
- Modify: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_graph.py`

READ `fusion.py`. `search()` currently: builds `fused = rrf_fuse(...)`, then `fused = _diversify(...)`, then builds `out`. You add an optional graph-boost step BETWEEN `rrf_fuse` and `_diversify`, gated by config/param, importing `graph` and `get_vault_path` lazily (graph reads the vault).

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_fusion_graph.py`:

```python
from cortex_vec import fusion, store, bm25, graph


def _vec(): return [
    {"id": "a.md", "score": 0.9, "title": "A", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
    {"id": "c.md", "score": 0.1, "title": "C", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
]


def test_graph_boost_applied_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    monkeypatch.setattr(graph, "build_graph", lambda vault: {"a.md": {"c.md"}, "c.md": {"a.md"}})
    monkeypatch.setattr(fusion, "get_vault_path", lambda: "/fake/vault", raising=False)
    out = fusion.search("q", n=2, graph=True)
    # c.md is a neighbor of top hit a.md -> boosted above its raw rank
    assert [o["id"] for o in out][0] == "a.md"
    assert "c.md" in [o["id"] for o in out]


def test_graph_off_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    called = {"build": False}
    def _build(vault):
        called["build"] = True
        return {}
    monkeypatch.setattr(graph, "build_graph", _build)
    fusion.search("q", n=2)  # graph defaults off
    assert called["build"] is False


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_fusion_graph.py -v` → FAIL (`search` has no `graph` kwarg / no boost).

- [ ] **Step 3: 整合 graph-boost** — 在 `fusion.py` 頂部 import 區加 `from .config import BM25_DIR, get_retrieval_config, get_vault_path`（把 `get_vault_path` 併入既有的 config import；它已存在於 config.py）。把 `search` 的簽章與 graph 步驟改為：

把簽章 `def search(query, n=5, where=None, use_bm25=True, use_vector=True):` 改為：

```python
def search(query, n=5, where=None, use_bm25=True, use_vector=True, graph=None, rerank=None):
```

在 `fused = rrf_fuse(ranked, weights, k=rc["rrf_k"])` 之後、`fused = _diversify(...)` 之前加：

```python
    use_graph = rc["graph"] if graph is None else graph
    if use_graph:
        fused = _graph_boost(fused, rc)
```

並在 `search` 函式之前加 helper：

```python
def _graph_boost(fused, rc):
    """Boost fused candidates by wikilink proximity to the top hits. [] on failure."""
    from . import graph as graph_mod
    try:
        adjacency = graph_mod.build_graph(get_vault_path())
        return graph_mod.boost(
            fused, adjacency,
            top_k=rc["graph_top_k"], hops=rc["graph_hops"], weight=rc["graph_weight"],
        )
    except Exception:
        return fused
```

(NOTE: the test monkeypatches `fusion.get_vault_path` and `graph.build_graph`; importing `graph as graph_mod` inside the function still resolves to the same `cortex_vec.graph` module object the test patched. `get_vault_path` must be importable at module top from `.config`.)

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_fusion_graph.py tests/test_fusion_search.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_graph.py
git commit -m "$(printf 'feat(cortex-vec): integrate optional wikilink graph-boost into fusion\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 10: rerank.py — LLM 重排（複用 OpenAI）

**Files:**
- Create: `cortex-vec/src/cortex_vec/rerank.py`
- Test: `cortex-vec/tests/test_rerank.py`

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_rerank.py`:

```python
import openai
from cortex_vec import rerank


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        return _FakeResp(self._content)


def _results():
    return [{"id": "a", "title": "A", "summary": ""}, {"id": "b", "title": "B", "summary": ""}]


def test_rerank_reorders_by_llm(monkeypatch):
    monkeypatch.setattr(openai, "OpenAI",
                        lambda: _FakeClient('[{"index": 1, "score": 9}, {"index": 0, "score": 2}]'))
    out = rerank.rerank("q", _results(), model="m", window=15)
    assert [r["id"] for r in out] == ["b", "a"]


def test_rerank_failure_returns_unchanged(monkeypatch):
    def _boom():
        raise RuntimeError("no key")
    monkeypatch.setattr(openai, "OpenAI", _boom)
    res = _results()
    assert rerank.rerank("q", res, model="m", window=15) == res


def test_rerank_empty_results():
    assert rerank.rerank("q", [], model="m", window=15) == []
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_rerank.py -v` → FAIL (no module).

- [ ] **Step 3: 實作 rerank.py** — Create `cortex-vec/src/cortex_vec/rerank.py`:

```python
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
```

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_rerank.py -v` → PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/rerank.py cortex-vec/tests/test_rerank.py
git commit -m "$(printf 'feat(cortex-vec): add optional LLM reranker (reuses OpenAI)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 11: fusion — integrate rerank

**Files:**
- Modify: `cortex-vec/src/cortex_vec/fusion.py`
- Test: `cortex-vec/tests/test_fusion_rerank.py`

READ `fusion.py`. `search()` now ends by building `out` (list of top-n display dicts) and returning it. Rerank operates on the FINAL output window. To let rerank reorder more than `n`, build the output to `max(n, rerank_window)` candidates when rerank is on, rerank, then slice to `n`.

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_fusion_rerank.py`:

```python
from cortex_vec import fusion, store, bm25, rerank


def _vec(): return [
    {"id": "a", "score": 0.9, "title": "A", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
    {"id": "b", "score": 0.5, "title": "B", "type": "note", "repo": "",
     "category": "", "tags": "", "summary": ""},
]


class _NoBM25:
    def __init__(self, *a, **k): pass
    def load(self): pass
    def search(self, *a, **k): return []


def test_rerank_invoked_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    # fake rerank reverses the list
    monkeypatch.setattr(rerank, "rerank", lambda query, results, model, window: list(reversed(results)))
    out = fusion.search("q", n=2, rerank=True)
    assert [o["id"] for o in out] == ["b", "a"]


def test_rerank_off_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(store, "vector_stream", lambda q, n, where=None: _vec())
    monkeypatch.setattr(bm25, "BM25Index", _NoBM25)
    called = {"r": False}
    def _r(*a, **k):
        called["r"] = True
        return a[1]
    monkeypatch.setattr(rerank, "rerank", _r)
    fusion.search("q", n=2)
    assert called["r"] is False
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_fusion_rerank.py -v` → FAIL (no rerank wiring).

- [ ] **Step 3: 整合 rerank** — 在 `fusion.py` 的 `search()`，找到結尾建立 `out` 的段落（目前是 `out = []` + `for doc_id, score in fused[:n]:` 迴圈 + `return out`）。把它替換為：

```python
    use_rerank = rc["rerank"] if rerank is None else rerank
    take = max(n, rc["rerank_window"]) if use_rerank else n

    out = []
    for doc_id, score in fused[:take]:
        entry = dict(display.get(doc_id, {}))
        entry["id"] = doc_id
        entry["score"] = round(score, 6)
        out.append(entry)

    if use_rerank:
        from . import rerank as rerank_mod
        out = rerank_mod.rerank(query, out, model=rc["rerank_model"], window=rc["rerank_window"])

    return out[:n]
```

(IMPORTANT: there is a name clash — the `search` parameter is named `rerank` and the module is also `rerank`. That's why we import it locally as `rerank_mod`. The test monkeypatches `rerank.rerank` on the module; the local `from . import rerank as rerank_mod` binds the patched module, so `rerank_mod.rerank` is the patched function. Do NOT add a top-level `from . import rerank`.)

- [ ] **Step 4: 跑測試確認通過** — Run: `cd cortex-vec && pytest tests/test_fusion_rerank.py tests/test_fusion_search.py tests/test_fusion_graph.py tests/test_fusion_diversify.py -v` → PASS (all fusion tests).

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/fusion.py cortex-vec/tests/test_fusion_rerank.py
git commit -m "$(printf 'feat(cortex-vec): integrate optional LLM rerank into fusion pipeline\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 12: cli — search 加 --rerank / --graph flags

**Files:**
- Modify: `cortex-vec/src/cortex_vec/cli.py`
- Modify: `cortex-vec/src/cortex_vec/store.py`
- Test: `cortex-vec/tests/test_cmd_search_flags.py`

READ `cli.py` (search subparser) and `store.cmd_search` (calls `fusion.search(..., use_bm25=..., use_vector=...)`). Add `--rerank`/`--graph` store_true flags and thread them to `fusion.search(rerank=..., graph=...)`.

- [ ] **Step 1: 寫失敗測試** — Create `cortex-vec/tests/test_cmd_search_flags.py`:

```python
from types import SimpleNamespace
from cortex_vec import store, fusion


def test_cmd_search_threads_rerank_graph(monkeypatch):
    captured = {}
    monkeypatch.setattr(fusion, "search",
                        lambda query, n=5, where=None, use_bm25=True, use_vector=True,
                               rerank=None, graph=None:
                        captured.update(rerank=rerank, graph=graph) or [])
    args = SimpleNamespace(query="q", repo=None, type=None, category=None, n=5,
                           no_bm25=False, no_vector=False, rerank=True, graph=True)
    store.cmd_search(args)
    assert captured["rerank"] is True
    assert captured["graph"] is True
```

- [ ] **Step 2: 跑測試確認失敗** — Run: `cd cortex-vec && pytest tests/test_cmd_search_flags.py -v` → FAIL (cmd_search doesn't pass rerank/graph).

- [ ] **Step 3: 改 store.cmd_search 與 cli.py** —

在 `store.cmd_search` 的 `fusion.search(...)` 呼叫，加入 `rerank`/`graph` 參數：

```python
    results = fusion.search(
        args.query,
        n=args.n or 5,
        where=where,
        use_bm25=not getattr(args, "no_bm25", False),
        use_vector=not getattr(args, "no_vector", False),
        rerank=getattr(args, "rerank", False) or None,
        graph=getattr(args, "graph", False) or None,
    )
```

(`or None` 讓未指定 flag 時傳 `None`，使 `fusion.search` 回退到 config 預設；指定 `--rerank` 時傳 `True`。)

在 `cli.py` 的 search subparser，於 `--no-vector` 之後加：

```python
    p_search.add_argument("--rerank", action="store_true", help="Enable LLM rerank of top results")
    p_search.add_argument("--graph", action="store_true", help="Enable wikilink graph-boost")
```

- [ ] **Step 4: 跑測試確認通過 + 全套** — Run: `cd cortex-vec && pytest tests/test_cmd_search_flags.py -v && pytest -q` → PASS（new + full suite green）。也驗證 `python -m cortex_vec.cli search --help` 列出 `--rerank`/`--graph`。

- [ ] **Step 5: Commit**

```bash
git add cortex-vec/src/cortex_vec/cli.py cortex-vec/src/cortex_vec/store.py cortex-vec/tests/test_cmd_search_flags.py
git commit -m "$(printf 'feat(cortex-vec): search --rerank/--graph flags thread to fusion\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## Task 13: 文件更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README** — 在 `### Hybrid 檢索` 段落（Plan 1 加的）後面，加一個 `### 進階檢索（Plan 2，預設關閉）` 小節，用 ```bash 區塊說明：
  - synonym 展開：config `retrieval.synonym_weight`（0 = off；建議 0.7），BM25 路加入同義詞（Synology 黑話表在 `synonyms.py`，可擴充）。
  - graph-boost：`--graph` 或 config `retrieval.graph: true`，用 vault 既有 `[[wikilinks]]` 把 top hits 的鄰居加分（`graph_hops`/`graph_weight`/`graph_top_k` 可調）。
  - LLM rerank：`--rerank` 或 config `retrieval.rerank: true`，用 OpenAI 重排 top-`rerank_window`（預設 15），失敗自動回退原序。
  - 強調：四者預設全關，開啟前後建議用 `cortex-vec eval run` 量測 lift。

- [ ] **Step 2: 跑全套測試** — Run: `cd cortex-vec && pytest -q` → all green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(printf 'docs(cortex-vec): document Plan 2 advanced retrieval (synonym/graph/rerank)\n\nSigned-off-by: %s <%s>' "$(git config user.name)" "$(git config user.email)")"
```

---

## 完成定義（Plan 2）

- `cortex-vec search` pipeline：streams(+synonym) → RRF → graph-boost → diversify → rerank → top-n，四個強化**預設全關**，開啟後行為由 config/CLI flag 控制。
- synonym 展開（BM25 路，加權）、max-per-repo 多樣化、wikilink graph-boost（`--graph`）、LLM rerank（`--rerank`）皆可獨立開關。
- 預設關閉時，`fusion.search` 輸出與 Plan 1 完全相同（向後相容）。
- 全套 pytest 綠。
- 每個強化都能用 `cortex-vec eval run` 量測 lift（開/關對比）。

**後續（使用者手動，human-in-loop）：** 跑 `cortex-vec eval run` 對比各 flag 開關的 P@5/R@5/MRR，決定哪些強化值得設為預設開啟、哪些回退。synonym 表（`synonyms.py`）依實際 vault 用語擴充。
