# Hybrid 檢索 + 檢索評測框架 — 設計文件

- **日期**：2026-05-25
- **狀態**：Approved design（待 writing-plans）
- **範圍**：`cortex-vec` 檢索層重構為 hybrid（BM25 + vector，RRF 融合，含 CJK 分詞、synonym、可選 LLM rerank、可選 wikilink graph-boost）+ 一套可重現的檢索評測 harness
- **借鏡來源**：agentmemory（`rohitg00/agentmemory`）的 search 子系統與 eval/benchmark 框架

---

## 1. 背景與動機

cortex 目前的檢索（`cortex-vec`，518 行）是**純 vector**：ChromaDB + OpenAI `text-embedding-3-small`，每篇 note 存 body 向量 + LLM 產的雙語 summary 向量（dual-vector），search 時取 `n×3` 後按 base-path 去重取最高分。grep fallback 在 `cortex-query` skill 層。

兩個問題：

1. **精確詞召回弱**：函式名、repo 名（`libsynow3`）、Synology 黑話、issue ID（`DSM-123456`）這類 anchor 會被 embedding 語意化模糊掉，而這正是 vault 裡最常被當查詢錨點的東西。
2. **無法量測**：沒有任何檢索品質評測，無法回答「dual-vector 有沒有用」「加 BM25 後變好還變壞」。改檢索等於盲改。

agentmemory 的對應子系統提供成熟解法：BM25 + vector + RRF 融合（中英混合 CJK 分詞）、以及 pluggable-adapter 的小型可重現 eval harness。本設計把這兩者移植進 cortex，**並用 eval 當貫穿主線**，每加一層檢索能力就量一次 lift。

### 哲學邊界（明確不做）

cortex 是人工策展、markdown source-of-truth、distill 刻意 human-in-loop 的個人知識 vault。因此本設計**只移植檢索與量測基礎設施（哲學中立）**，不移植 agentmemory 的生命週期自動化（auto-consolidation / decay / auto-forget / 自動 insight 合成）——那些與 human-in-loop 直接衝突，明確排除。

---

## 2. 目標與非目標

### 目標
- `cortex-vec search` 回傳 **BM25 + vector 經 RRF 融合**的單一 ranking，輸出格式與現在完全相容。
- 中英混合 query 的 BM25 分詞正確（保留英文詞邊界）。
- 沒有 `OPENAI_API_KEY` / 沒網路時自動退化為 BM25-only（取代現有 grep fallback）。
- 一套 `cortex-vec eval` 子命令：四種 adapter（grep / vector / bm25 / hybrid）在相同內容上比較，輸出 P@5 / R@5 / MRR / hit + markdown scorecard。
- 可選的 synonym 展開、LLM reranker、wikilink graph-boost，各自可被 eval 量測 lift，預設關閉。

### 非目標
- 不換掉 ChromaDB（不動 markdown source-of-truth 模型）。
- 不做 auto-consolidation / decay / auto-forget / 自動 insight 合成。
- 不改 `cortex-query` skill 的對外行為（輸出相容）；skill 層 grep fallback 的簡化列為後續、不在本 scope。
- 不引入 torch / 本地 cross-encoder（reranker 走既有 OpenAI）。

---

## 3. 架構與檔案佈局（方案 A）

把 `store.py` 拆成單一職責模組，每個可獨立測試：

```
cortex_vec/
  cli.py          # argparse 分派（擴充：+ eval 子命令、+ --no-bm25 / --rerank / --graph flags）
  config.py       # 既有 + BM25 路徑、RRF 權重與 k、各 feature flag 預設
  parser.py       # 既有 + 新增 wikilink 抽取 [[...]]
  store.py        # 瘦身：只留 ChromaDB（vector 索引生命週期 + vector 查詢）
  tokenize.py     # CJK-aware tokenizer（jieba + Porter stemmer，保留英文詞邊界）
  bm25.py         # BM25 索引：build / persist / load / search，與 vault lockstep
  fusion.py       # RRF 融合 + 多樣化；對外 hybrid search() 進入點
  synonyms.py     # synonym groups（資料）+ 展開
  rerank.py       # 可選 LLM reranker（複用 OpenAI），預設關
  graph.py        # wikilink 鄰接表 + BFS boost，預設關
  eval/
    __init__.py
    adapters.py   # Adapter protocol：grep / vector / bm25 / hybrid 四種可互比
    corpus.py     # 載入 corpus 快照 + queries(gold)
    score.py      # P@k / R@k / MRR / hit；NDJSON + summary 聚合
    report.py     # markdown scorecard 產生器
    data/<corpus>/queries.jsonl   # 手標 gold（checked into git）
```

### 設計原則
- **`fusion.py` 是唯一對外檢索進入點**。`cmd_search` 改呼叫 `fusion.search(query, ...)`，由它內部協調 vector(`store`) + bm25(`bm25`) + 可選 rerank/graph，回傳單一融合 ranking。
- **`store.py` / `bm25.py` 介面對稱**：都提供 `build()` / `upsert(path)` / `delete(path)` / `search(query, k) -> [(doc_id, score)]`。`cmd_rebuild` / `cmd_upsert` / `cmd_delete` 同時驅動兩者，保證 lockstep。
- **eval 重用 production 模組**：`hybrid` adapter 直接呼叫 `fusion.search`，所以 eval 量的就是真實檢索；`grep` / `vector` / `bm25` adapter 是隔離單路，用來看每一路各自貢獻多少。

### 既定技術選型
- **BM25 lib**：`rank_bm25`（`BM25Okapi`，純 Python，小 vault 夠用）。
- **BM25 持久化**：pickle 存 `~/.cortex/bm25/`（index + doc metadata），由 `rebuild`/`upsert`/`delete` 與 vector store 同步維護。
- **Tokenizer**：jieba（中文，新依賴）+ 輕量 Porter stemmer（英文），保留英文詞邊界（照搬 agentmemory 中英混合切法）。
- **去重/多樣化**：沿用 base-path 去重，加可選 `max_per_repo` 多樣化。

---

## 4. Hybrid 檢索 pipeline 與資料流

`cortex-vec search "query" [--repo/--type/--category] [--rerank] [--graph]`：

```
query
 ├─ synonyms.expand()             # 只給 BM25 路加同義詞（權重 0.7），vector 不動
 │
 ├─ Vector stream  store.search(q, k×3)     → dedup 到 base-path → rank
 ├─ BM25 stream    bm25.search(tokens, k×3) → dedup 到 base-path → rank
 │      tokenize = jieba(中文) + PorterStemmer(英文)，保留英文邊界
 │
 ├─ RRF 融合  combined = w_bm25·1/(k+rank_bm25) + w_vec·1/(k+rank_vec)
 │      預設 k=60, w_bm25=0.4, w_vec=0.6；缺一路就歸一化重分配
 │
 ├─ dedup(base-path) + 可選 max_per_repo 多樣化
 ├─ [--graph]  從 top hits BFS 1-2 hop 走 wikilink 鄰接，boost 鄰居後重排
 ├─ [--rerank] top-15 丟 OpenAI 便宜模型重排，尾段不動
 └─ 輸出 JSONL（id/score/title/type/repo/category/tags/summary）← 與現在相容
```

### 關鍵語意
- **融合在 base-path 層 join**：兩路各自先 dedup 到 base-path 再給 rank，RRF 用 base-path 當 key。避免 ChromaDB 的 body/summary/`::repo` 多 entry 與 BM25 對不上。
- **BM25 一篇 note 一筆**（內容 = `title\n\nbody`，與現有 `embed_content` 一致）；repo/type/category 當 metadata 供過濾；filter 同時套用兩路。
- **degradation 取代舊 grep fallback**（見 §6）。
- **rerank/graph 預設關**，由 flag 或 config 開。

### RRF 權重重分配
缺某一路（如 vector 路空）時，把該路權重設 0，剩餘權重歸一化：`w_i /= Σw`。確保只剩 BM25 時 BM25 拿到全權重。

---

## 5. 評測 harness（eval）

### corpus 快照
eval runner 從目前 vault（或 `--vault-ref <git-commit>`）建一個**隔離索引**（獨立 ChromaDB path + BM25），讓四種 adapter 看到**完全相同的內容**。gold 用穩定 note 路徑記；runner 開跑前檢查 gold 路徑是否還在、不在就警告（避免 vault 演化造成 gold 失效卻無聲）。

### queries.jsonl（手標 gold）
```json
{"id":"q-001","query":"nginx 憑證自動更新","gold":["Notes/Nginx/cert-renew.md"],"type":"single-note","note":"中英混合查詢"}
```
- 規模目標：15–30 題，涵蓋多種類型（single-note / cross-note / 概念 / 精確詞錨點 / 中英混合）。
- 輔助命令 `cortex-vec eval propose`：用 OpenAI 從 notes 提**候選 query**，使用者編輯/確認 gold 後寫入 `queries.jsonl`（human-in-loop，省力但使用者拍板）。

### Adapter 介面
```python
class Adapter(Protocol):
    def init(self, corpus) -> State: ...
    def query(self, q: str, k: int) -> list[tuple[str, float]]: ...  # [(base_path, score)]
    def teardown(self) -> None: ...
```
- `grep`：tokenize + 子字串/詞頻計分（零依賴 baseline）。
- `vector`：只走 `store`（ChromaDB）。embedding 依 content-hash 快取到本地 cache → 重跑免費。
- `bm25`：只走 `bm25`。
- `hybrid`：直接呼叫 `fusion.search`（含當前開啟的 feature flags）。

### 指標與輸出
- `score.py`：`P@k = hits/k`、`R@k = hits/|gold|`、`MRR = 1/rank_of_first_gold`、`hit = 是否 top-k 內至少一個 gold`。
- 逐題輸出 NDJSON；聚合成 `summary.json`（`byAdapter`、`byType`）。
- `report.py`：產 markdown scorecard 進 `docs/benchmarks/`（沿用 agentmemory 範本：標題結論 + per-adapter 表 + per-type 表 + methodology + reproduction）。

### 分層上線（eval 當貫穿主線，lift 不正就 YAGNI 砍）
| Phase | 內容 | 量什麼 |
|---|---|---|
| 0 | eval harness + grep/vector adapter + 手標 corpus | 現有 vector **baseline** |
| 1 | BM25 索引 + tokenizer + bm25 adapter | BM25 單路 |
| 2 | **RRF 融合（hybrid）** | **hybrid vs vector 的 lift ← 主菜** |
| 3 | synonym 展開 | 加同義詞的 lift |
| 4 | wikilink graph-boost | graph 的 lift |
| 5 | LLM rerank | precision lift |

每個 Phase：實作 → 跑 eval → 記 scorecard → lift 正才保留。

---

## 6. 錯誤處理與 graceful degradation

| 失效 | 行為 |
|---|---|
| 無 `OPENAI_API_KEY` / 無網路 | vector 路 + rerank 停用，自動 **BM25-only**（取代舊 grep fallback）；stderr 一次性提示 |
| jieba 未安裝 | 中文整段當單一 token（soft-fall），索引/查詢仍可跑，印一次安裝提示 |
| BM25 索引不存在/損毀 | 退回 vector-only；提示跑 `rebuild` |
| rerank LLM 呼叫失敗 | 吞例外，回融合後原序（reranker 永不讓查詢失敗） |
| graph BFS 遇斷掉的 wikilink | 略過該邊，不中斷 |

---

## 7. 設定

`~/.cortex/config.json` 新增 `retrieval` 區塊；CLI flag 蓋過 config；feature 預設關（先量再開）：
```jsonc
"retrieval": {
  "rrf_k": 60, "w_bm25": 0.4, "w_vec": 0.6,
  "max_per_repo": 0,            // 0 = 不限
  "rerank": false, "graph": false,
  "rerank_model": "gpt-4o-mini", "rerank_window": 15
}
```

---

## 8. 向後相容

- `cortex-vec search` 輸出 JSONL 格式不變 → `cortex-query` skill 不用改。
- `cortex-vec status` 擴充：同時顯示 vector 與 BM25 entry 數，不一致則警告。
- skill 層 grep fallback 的簡化／退役列為後續，不在本 scope。

---

## 9. 測試

每模組 pytest 單元測試（cortex-vec 目前無測試，本設計順帶建 pytest 基礎）：
- `tokenize`：中英混合（`機器學習ML技術 → [機器,學習,ML,技術]`）、純中、純英、stemming、jieba 缺席 soft-fall。
- `bm25`：IDF/BM25 算分、prefix、synonym 權重、persist/load round-trip。
- `fusion`：RRF 數學、缺一路權重重分配、base-path join、`max_per_repo` 多樣化。
- `graph`：BFS 深度限制、斷鏈處理。
- `store`：lockstep（rebuild/upsert/delete 後兩索引一致）。
- eval harness 本身即 integration test。

---

## 10. 風險與取捨

- **scope 偏大（Tier 1-3 全包）**：用嚴格分層 + 每層 eval lift 把關緩解；任一層 lift 不顯著即砍。
- **BM25 lockstep 維護成本**：兩套索引要同步，靠對稱介面 + status 一致性檢查 + 測試覆蓋。
- **手標 corpus 的工作量與偏誤**：15–30 題、LLM 提候選降低人力；gold 由人確認確保效度；類型多樣化降低偏誤。
- **rerank/graph 的邊際效益不確定**：預設關 + eval 量測決定是否值得開。
