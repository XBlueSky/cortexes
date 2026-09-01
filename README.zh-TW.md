<p align="center">
  <img src="docs/images/logo.png" alt="Cortexes" width="200">
</p>

<h1 align="center">Cortexes</h1>

<p align="center">
  Personal knowledge vault plugin for Claude Code — session recording, memory distillation, semantic retrieval.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://cortexes.pages.dev"><img alt="Website" src="https://img.shields.io/badge/website-cortexes.pages.dev-000"></a>
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-d97757">
  <a href="CONTRIBUTING.zh-TW.md"><img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

<p align="center">
  <sub><a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a></sub>
</p>

## What It Does

Cortexes 把你的工作記憶變成可搜尋的知識庫。每次 Claude Code session 結束時自動記錄，之後可以提煉、檢索。

- **自動記錄** — session 結束時產出完整報告（commits、發現、決策），存到 vault
- **語意搜尋** — 用 OpenAI embedding + ChromaDB，中英文混合搜尋
- **知識提煉** — 從 Raw session dump 萃取踩坑知識、內部慣例、關鍵決策
- **Memory Injection** — 開 session 時偵測當前 repo，詢問是否載入相關記憶

**設計哲學：** Vault 是 source of truth（純 markdown + git），vector store 是可重建的衍生索引。

## Quick Start

### 1. 安裝 plugin

```bash
# 先加 marketplace，再從中安裝 plugin
/plugin marketplace add https://github.com/XBlueSky/cortexes.git#plugin
/plugin install cortexes@cortex
```

Marketplace 名稱是 `cortex`，其中的 plugin 是 `cortexes`，所以安裝 id 是
`cortexes@cortex`。Marketplace 名稱刻意沿用 1.x，既有的 `marketplace add`
註冊才不會失效。

### 2. 安裝 cortex-vec CLI

CLI 已發佈在 PyPI，套件名
[`cortex-vec`](https://pypi.org/project/cortex-vec/)：

```bash
# 建議：用 uv 做隔離的工具安裝
uv tool install cortex-vec

# 或用 pip
pip install cortex-vec
```

plugin 更新後用 `uv tool upgrade cortex-vec`（或 `pip install -U
cortex-vec`）升級。`/cortexes:genesis` 會檢查 CLI 是否已安裝，缺少時主動
提供安裝指令。想跑尚未釋出的開發版，可改從 repo 安裝：

```bash
uv tool install "git+https://github.com/XBlueSky/cortexes.git@plugin#subdirectory=cortex-vec"
```

`OPENAI_API_KEY` 是**選用的**。設定它會啟用 embedding，也就啟用語意
（向量）搜尋。不設定也不會壞掉：`search` 會走本機 BM25 索引，完全在你的
機器上跑，不會有任何資料送往 OpenAI。

### 3. 初始化

```bash
/cortexes:genesis /path/to/your/vault
```

這會設定 vault 路徑、author 資訊，並建立語意索引。

### 4. 開始使用

```
「存到 cortex」     → 手動存入知識
「查 cortex」       → 語意搜尋 vault
「提煉」           → 從 Raw/ 萃取知識
「broadcast」      → 把新 Raw 融合進既有頁面
```

## 從 1.x 升級到 2.0

2.0.0 把 **plugin** 從 `cortex` 改名為 `cortexes`。你的 vault、設定與索引都
不動 — 沒有任何資料需要遷移。

1. **更新 marketplace。** 在 Claude Code 執行
   `/plugin marketplace update cortex`（或移除後重新 add）。
2. **開一個新 session。** Marketplace manifest 帶了 `renames` 映射
   （`cortex` → `cortexes`），改名會自動接續：update 會把你已啟用的 plugin
   重新指向 `cortexes@cortex`，下一次 session 啟動時就會實體化為 2.0.0，
   **不需要**先解除安裝再裝一次。這兩步之間，`/plugin` 可能還會列出舊的
   `cortex` 那一列並標註 `Renamed to "cortexes" in the "cortex" marketplace`
   —— 那是 migration 已排定，不是錯誤。真的要從頭重裝時，id 是
   `/plugin install cortexes@cortex`。
3. **改用新的指令前綴。** `/cortex:*` 已不再解析，全部移到 `/cortexes:*`
   （`/cortexes:genesis`、`/cortexes:evolve`、`/cortexes:distill`、
   `/cortexes:query`、`/cortexes:broadcast`、`/cortexes:takeoff`）。自然語言
   觸發詞不變 —「存到 cortex」「查 cortex」照常可用。
4. **vault 裡若還有 `Weekly/`，把還要用的內容搬走。** `Weekly/` 已不再屬於
   vault 分類：2.0 不會建立、不索引、不搜尋、也不列出它。它其實早就到不了了
   —— 週報 skill 在 0.22.0 移除，`Weekly/` 更早在 0.5.0 就退出索引 —— 所以
   這不影響你搜得到的東西。Cortexes **不會**搬動、改寫或刪除既有的
   `Weekly/`；還想留的內容請自己複製到 `Notes/` 或 `Projects/`，慢慢來就好，
   沒搬的檔案會原封不動留在原地。
5. **其他都沒變。** `cortex-vec`、`~/.cortex/config.json`、vector/BM25 索引與
   快取、`CORTEX_*` 環境變數，名稱與路徑全部保留。不用重建、不用重新索引、
   不用改設定。

## 官網

線上文件與 changelog：<https://cortexes.pages.dev>（Cloudflare Pages，從 `.cc-marketspec/dist/manifest.json` 自動生成）。
本地 build 見 [`site/README.md`](site/README.md)。

## Commands & Skills

### Commands

| Command | Description |
|---------|-------------|
| `/cortexes:genesis` | 初始化 vault — 設定路徑、author、重建索引 |
| `/cortexes:evolve` | 手動存入知識到 Notes 或 Projects（同時寫 `log.md`） |
| `/cortexes:distill` | 提煉 Raw/ session 記錄到 Notes/Projects（map-first 導覽 + 兩階段評估 + pending-merge 出口） |
| `/cortexes:query` | 搜尋 vault — 語意搜尋（`cortex-vec`），並有 grep 與 BM25 fallback。執行這個指令本身就算明確要求，即使該 session 已選「直接開始工作」也會查 |
| `/cortexes:broadcast` | 把新 distill 的內容融合進相關既有頁面（llm-wiki 式 ingest） |
| `/cortexes:takeoff` | 交接接力棒 — curate 暫時、不進 git 的 hand-off,讓之後的 session 接續;一條工作線一支(`[topic]` / `resume [topic]` / `done [topic]` 子指令) |

### Skills（自動觸發）

| Skill | Trigger |
|-------|---------|
| cortex-evolve | 「存到 cortex」「記一下」「save to cortex」 |
| cortex-distill | 「提煉」「整理 raw」「distill」 |
| cortex-broadcast | 「broadcast」「merge pending-merge」「把這個融入 vault」 |
| cortex-takeoff | 「交接」「takeoff」「交棒給下個 session」「context 快滿了」 |
| cortex-query | 「查 cortex」「之前有記過」「cortex 裡有沒有」 |

### Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| Session Report | SessionEnd | session 結束時先經 TOML transcript filter 過濾，再寫到 Raw/ |
| Memory Injection | SessionStart | 互動式選單：偵測 vault backlog 狀態後詢問下一步 |

> **錄製是自動的。** 每個超過 4 KB 的 session 在結束時都會寫進你的
> vault，不會逐次詢問。設定 `CORTEX_SKIP_RECORD=1` 可跳過某次 session；
> 完整的擷取內容、排除項目，以及哪些資料會離開你的機器，見
> [`PRIVACY.zh-TW.md`](PRIVACY.zh-TW.md)。

#### Transcript Filter（0.9.0+）

SessionEnd hook 在寫進 Raw/ 前會跑一條 TOML-driven filter pipeline，把不具知識價值的
tool 輸出（例如 `ls`、卷冊清單、重複的 build log）過濾掉——你可以針對個別 slash
command 寫客製 filter，讓 Raw 存下來的是真正有訊號的內容。

## Architecture

```
cortex repo
├── plugin branch (orphan)     ← Claude Code plugin（本檔案所在）
└── main branch                ← Obsidian vault 資料

~/.cortex/
├── config.json                ← genesis 產生的設定
└── vectorstore/               ← ChromaDB 語意索引（local only，不在 git）
```

### Vault Structure

```
Raw/YYYY/MM/DD/                ← session dumps（完整，按需提煉）
Notes/<category>/              ← 提煉後的技術知識
Projects/<repo-name>/          ← 以 repo 為主的專案筆記
_index.md                      ← 全 vault 摘要索引
log.md                         ← evolve/distill 的時序歷程
```

`_index.md` 的一致性沒有機器保證（頁面重整是唯一不經 skill 的路徑），稽核方法與
幾個會讓檢查靜默失效的 regex 陷阱見 [`docs/index-audit.md`](docs/index-audit.md)。

### Data Flow

```
每個 session:
  SessionStart → 提示有 memory 可用 → 使用者決定是否載入
  工作...
  session 結束 → SessionEnd hook → 過濾 → Raw/   （自動，不會詢問）

隨時:
  /cortexes:evolve    → Notes/Projects + _index.md + log.md + vector store
  /cortexes:query     → vector search → 精確讀檔

定期:
  /cortexes:distill   → Raw → Notes/Projects (+ pending-merge → broadcast)
  /cortexes:broadcast → pending-merge → 融合進既有 Notes/Projects
```

### Retrieval Strategy

**Hybrid 檢索**（0.4.0+）— BM25 + vector 雙流，以 Reciprocal Rank Fusion（RRF, k=60）融合，預設權重 w_bm25=0.4 / w_vec=0.6：

- **BM25 流** — 精確詞彙匹配（函數名、repo 名、issue ID 等），搭配 jieba CJK 分詞支援中英混合查詢。索引持久化於 `~/.cortex/bm25/`，由 `rebuild`/`upsert`/`delete` 與 ChromaDB 保持同步。
- **Vector 流** — OpenAI `text-embedding-3-small` 語意搜尋，dual-vector（文件 body + 雙語 summary），覆蓋語意相近但詞彙不同的場景。
- **降級策略** — 未設定 `OPENAI_API_KEY` 或離線時，自動退化為 BM25-only，不再依賴 skill-layer grep fallback。

其他分層：

1. **Raw Search**（按需）— 只在追溯時查詢原始 session 記錄

## cortex-vec CLI

Vault 的語意索引工具，用 ChromaDB + OpenAI `text-embedding-3-small`，搭配
`gpt-5.4-mini` 產雙語 summary 作為第二組 embedding（dual-vector）以提升中英混合
查詢的 recall。

```bash
cortex-vec status                          # 查看索引狀態
cortex-vec rebuild                         # 完整重建索引
cortex-vec search "nginx certificate"      # 語意搜尋
cortex-vec search "oauth" --repo acme-core # 按 repo 過濾
cortex-vec search "sharing" --type project # 按類型過濾
cortex-vec upsert Notes/Nginx/new.md       # 新增/更新單一文件
cortex-vec delete Notes/Nginx/old.md       # 刪除文件
```

### Hybrid 檢索（0.4.0+）

`cortex-vec search` 現在預設走 BM25 + vector RRF hybrid，兼顧精確詞彙與語意相似度：

```bash
cortex-vec search "nginx certificate"           # hybrid（預設）
cortex-vec search "nginx certificate" --no-bm25 # 只走 vector（debug/eval 用）
cortex-vec search "nginx certificate" --no-vector # 只走 BM25（debug/eval 用）
cortex-vec status                               # 同時顯示 vector 與 BM25 entry 數量
```

### 提煉導覽指令（1.0.0+）

`/cortexes:distill` 靠這組唯讀指令走訪一份 Raw,**全程不把整個檔案載入 context**。
每份 Raw 只被解析一次成為 gap-free、無重疊的 source partition;`raw-span` 是唯一
會回傳原始文字的 reader,每一頁都有硬上限,因此超大 session 會以 bounded 續頁分批
提煉,而不會撐爆 context:

```bash
cortex-vec distill-queue --root <vault>/Raw --stat        # 開批次前先看每份 Raw 的各級投影大小
cortex-vec raw-view <raw.md>                              # budget-bounded 的 L0–L3 投影
cortex-vec distill-plan start <raw.md>                    # 開一個 coverage/budget plan → plan_id
cortex-vec raw-map  <raw.md> --plan-id <id>               # 導覽卡片(kind/大小/範圍/anchors)
cortex-vec raw-span <raw.md> --plan-id <id> --span-id <n> # 精確原始文字,一次一頁 bounded
cortex-vec distill-plan status --plan-id <id>             # coverage 與 no-insight gate 狀態
```

每份 Raw 的 plan 存於 `$XDG_CACHE_HOME/cortex/distill-plans/`,由 `active.json`
指標強制同一時間只有一份 active Raw(atomic write、user-only 權限,遇到損毀或身分
漂移時 fail-closed)。

### 回收重複的 Raw 快照(1.1.0+)

SessionEnd 在同一場對話裡會觸發多次(`/clear`、離開後 `--resume`),每次都重新過濾
同一份持續增長的 transcript,因此較早的 Raw 都是最新那份的嚴格前綴。現在 hook 會自動
移除它們;這個指令是手動版本,也是清理 1.1.0 之前留下的積壓的唯一方式:

```bash
cortex-vec reclaim-superseded --root <vault>/Raw            # 列出整個 queue 裡的重複快照
cortex-vec reclaim-superseded --root <vault>/Raw --apply \
  --vault <vault>                                           # 移除它們(以 git rm 進 staging)
```

候選只來自未提煉的 queue——已帶 `<!-- distilled: -->` marker 的 Raw 絕不會被動到——
而且候選必須是存活者的前綴,所以失敗模式永遠是「重複的留下來」,不會是「內容遺失」。

### 檢索評測

```bash
# Step 1：讓 LLM 草擬候選查詢，人工審閱並確認 gold paths 後才能使用
cortex-vec eval propose --queries eval-data/cortex-vault-v1.jsonl

# Step 2：跑所有 adapter，印出 NDJSON 結果，並寫 markdown 評分表
cortex-vec eval run \
  --queries eval-data/cortex-vault-v1.jsonl \
  --adapters grep,vector,bm25,hybrid \
  --k 5 \
  --out docs/benchmarks/$(date +%Y-%m-%d)-cortex-vault-v1.md
```

支援的 adapter：`grep` / `vector` / `bm25` / `hybrid`。
評測指標：P@5 / R@5 / MRR / hit。

### 進階檢索（預設關閉）

以下四項增強功能預設全部關閉，需明確設定才會啟用。**開啟前後請務必用 `cortex-vec eval run` 量測 P@5 / R@5 / MRR 的 lift**，再決定哪些值得設為預設開啟、哪些應該回退。

#### Synonym 展開

由 config `retrieval.synonym_weight`（`0` = 關閉；建議試 `0.7`）控制。BM25 流會把命中同義詞的文件以該權重加分，讓「OAuth」可以命中「SSO / 授權 / auth」等同義詞。

同義詞表位於 `cortex-vec/src/cortex_vec/synonyms.py`（內含常見中英技術詞），可自行擴充。

#### Wikilink graph-boost

透過 `cortex-vec search --graph`（或 config `retrieval.graph: true`）啟用。把「命中結果的 `[[wikilink]]` 鄰居」當成**第三條 RRF 串流**融合進來——可把「被明顯命中的筆記連到、自己卻不直接匹配 query」的相關筆記浮上來（連 vector/BM25 漏掉的鄰居也能補進結果）。

可調整的細部參數：`retrieval.graph_hops`（傳播跳數）、`retrieval.w_graph`（graph 串流在 RRF 的權重，預設 `0.3`）、`retrieval.graph_top_k`（取前幾筆命中當 BFS 種子）。

> 採 rank-based RRF 融合（非加法 boost），所以**對一般查詢中性、不傷排序**，只在「連結型」查詢補 recall。eval 量過：20 題一般 corpus 開/關無差、wikilink-stress corpus R@5 0.50→0.667。

#### LLM rerank

透過 `cortex-vec search --rerank`（或 config `retrieval.rerank: true`）啟用。對初步 hybrid 結果的前 `retrieval.rerank_window`（預設 15）筆，呼叫 OpenAI（model 由 `retrieval.rerank_model` 指定，預設 `gpt-5.4-mini`）重新排序，以 LLM 判斷相關性取代純分數排名。任何失敗（API error / timeout）均自動回退原 RRF 順序，不影響搜尋可用性。

#### max-per-repo 多樣化

由 config `retrieval.max_per_repo`（`0` = 不限）控制，限制同一 repo 在前 k 結果中最多出現幾筆，避免某個大型 repo 淹沒其他來源的結果。

#### 完整 `retrieval` 設定範例

以下為 `~/.cortex/config.json` 中 `retrieval` 區塊的進階鍵與其預設值：

```json
{
  "retrieval": {
    "synonym_weight": 0,
    "graph": false,
    "graph_hops": 1,
    "w_graph": 0.3,
    "graph_top_k": 5,
    "rerank": false,
    "rerank_model": "gpt-5.4-mini",
    "rerank_window": 15,
    "max_per_repo": 0
  }
}
```

搭配 CLI flag 的用法：

```bash
# 開啟 graph-boost + rerank（一次性測試）
cortex-vec search "OAuth token" --graph --rerank

# 設定 synonym_weight 後跑 eval 確認 lift
cortex-vec eval run \
  --queries eval-data/cortex-vault-v1.jsonl \
  --adapters hybrid \
  --k 5 \
  --out docs/benchmarks/$(date +%Y-%m-%d)-synonym-0.7.md
```

## Configuration

`~/.cortex/config.json`（由 genesis 產生）：

```json
{
  "vault_path": "/path/to/vault",
  "author": "your-name",
  "author_email": "you@example.com",
  "git": {
    "auto_commit": true,
    "auto_push": false
  }
}
```

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `OPENAI_API_KEY` | No* | OpenAI API key，用於 text-embedding-3-small。`rebuild`/`upsert`/vector 搜尋時必填；未設定時 `search` 自動降級為 BM25-only |
| `CORTEX_VAULT_PATH` | No | 覆蓋 config.json 的 vault_path |
| `CORTEX_SKIP_RECORD` | No | 設定時(例如 `=1`),SessionEnd hook 會跳過把此 session 記錄進 Raw/ — 供沒有提煉價值的 launcher/probe session 使用 |
| `CORTEX_NO_CLASSIFIER` | No | 設為 `1` 時,transcript filter 不會呼叫 LLM classifier,過大的區塊改為原樣保留。不會有任何資料送往 Anthropic |

## Dependencies

| Package | Purpose |
|---------|---------|
| [ChromaDB](https://www.trychroma.com/) | 語意向量索引 |
| [OpenAI](https://platform.openai.com/) | text-embedding-3-small embedding model |
| [python-frontmatter](https://python-frontmatter.readthedocs.io/) | YAML frontmatter 解析 |
| pysqlite3-binary | SQLite 3.35+ 相容（系統 SQLite 太舊時需要） |

安裝：

```bash
uv tool install cortex-vec
```

## 隱私

Cortexes 是 local-first：vault 是你自己硬碟上的 Markdown，索引建在本機，
作者收不到任何東西——沒有伺服器、沒有帳號、沒有 telemetry。

但這跟「沒有任何資料離開你的機器」不是同一回事。Cortexes 是 Claude Code
plugin，所以 query、distill、broadcast 或 takeoff resume 讀到的 vault 頁面
會成為當前 session 的一部分，並在你自己的帳號底下由 Anthropic 處理——這是
一般的 Claude Code 處理，不是 Cortexes 的通道。SessionStart hook 另外會在
選單出現之前，把 repo 名稱、vault 路徑，以及你的 `Notes/`／`Projects/`
主題名稱放進該 context；頁面內容不會在那時被注入，但可能在你選了選單選項、
執行指令，或提出符合 `using-cortex` 訊號的請求之後才被載入。

由 plugin 自身程式碼發起的流程有三個，全部由你控制：Transcript filter 會
把過大的區塊（>12 KB，每次 session 最多 5 次）透過你自己的 Claude Code 送
給 Anthropic 做壓縮分類——`CORTEX_NO_CLASSIFIER=1` 可停用它，而它只停掉這
組巢狀呼叫，不影響一般 session 處理；語意索引會把 vault 頁面內容送往
OpenAI 產生 embedding，只在你設定 `OPENAI_API_KEY` 時發生，未設定時檢索走
本機 BM25 索引；以及 `git push` 到你設定的 remote，只在你自行開啟時發生
（預設關閉）。

[`PRIVACY.zh-TW.md`](PRIVACY.zh-TW.md) 完整記錄了每一條資料流：session
記錄包含什麼、寫入前排除什麼、檔案存在哪裡、git commit 與 push 行為、
如何逐項關閉，以及如何刪除你的資料。

## Project Structure

```
commands/       Slash commands（/cortexes:*）
skills/         自動觸發的 skills
hooks/          SessionStart/SessionEnd lifecycle hooks
cortex-vec/     Python 語意索引 CLI
site/           cortexes.pages.dev 的靜態網站產生器
docs/           設計文件、計畫與評測報告
scripts/        開發工具（例如 run-checks.sh）
tests/          Plugin 層級測試
```

## Contributing

歡迎貢獻 —— 開發環境、測試與 PR 流程見 [CONTRIBUTING.zh-TW.md](CONTRIBUTING.zh-TW.md)。
請一併閱讀[行為準則](CODE_OF_CONDUCT.zh-TW.md)。
安全性問題請勿公開回報，見 [SECURITY.zh-TW.md](SECURITY.zh-TW.md)。

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

Licensed under the [Apache License 2.0](LICENSE) — see `LICENSE` for full text.
Copyright 2026 XBlueSky（見 [NOTICE](NOTICE)）。
