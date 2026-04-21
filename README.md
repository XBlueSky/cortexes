# Cortex

Personal knowledge vault plugin for Claude Code — session recording, memory distillation, semantic retrieval, weekly reports.

![Cortex architecture](docs/images/architecture.png)

## What It Does

Cortex 把你的工作記憶變成可搜尋的知識庫。每次 Claude Code session 結束時自動記錄，之後可以提煉、檢索、產生週報。

- **自動記錄** — session 結束時產出完整報告（commits、發現、決策），存到 vault
- **語意搜尋** — 用 OpenAI embedding + ChromaDB，中英文混合搜尋
- **知識提煉** — 從 Raw session dump 萃取踩坑知識、內部慣例、關鍵決策
- **Memory Injection** — 開 session 時偵測當前 repo，詢問是否載入相關記憶

**設計哲學：** Vault 是 source of truth（純 markdown + git），vector store 是可重建的衍生索引。

## Quick Start

### 1. 安裝 plugin

```bash
# 從 GitLab
/plugin marketplace add git@git.synology.inc:tonyhu/cortex.git#plugin

# 從 GitHub
/plugin marketplace add https://github.com/XBlueSky/cortex.git#plugin
```

### 2. 安裝 cortex-vec CLI

```bash
pip install -e "$(claude plugin root cortex)/cortex-vec"
```

需要 `OPENAI_API_KEY` 環境變數（用於 embedding）。

### 3. 初始化

```bash
/cortex:genesis /path/to/your/vault
```

這會設定 vault 路徑、author 資訊，並建立語意索引。

### 4. 開始使用

```
「存到 cortex」     → 手動存入知識
「查 cortex」       → 語意搜尋 vault
「提煉」           → 從 Raw/ 萃取知識
「broadcast」      → 把新 Raw 融合進既有頁面
「整理週報」       → 產生週報
```

## Commands & Skills

### Commands

| Command | Description |
|---------|-------------|
| `/cortex:genesis` | 初始化 vault — 設定路徑、author、重建索引 |
| `/cortex:evolve` | 手動存入知識到 Notes 或 Projects（同時寫 `log.md`） |
| `/cortex:distill` | 提煉 Raw/ session 記錄到 Notes/Projects（兩階段評估 + pending-merge 出口） |
| `/cortex:broadcast` | 把新 distill 的內容融合進相關既有頁面（llm-wiki 式 ingest） |
| `/cortex:weekly` | 產 Friday 週報（distill + GitLab activity + CSS tickets） |

### Skills（自動觸發）

| Skill | Trigger |
|-------|---------|
| cortex-evolve | 「存到 cortex」「記一下」「save to cortex」 |
| cortex-distill | 「提煉」「整理 raw」「distill」 |
| cortex-broadcast | 「broadcast」「merge pending-merge」「把這個融入 vault」 |
| cortex-weekly | 「整理週報」「產生週報」「weekly report」 |
| cortex-query | 「查 cortex」「之前有記過」「cortex 裡有沒有」 |

### Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| Session Report | Stop | session 結束時先經 TOML transcript filter 過濾，再寫到 Raw/ |
| Memory Injection | SessionStart | 互動式選單：偵測 vault 狀態（週報/backlog）後詢問下一步 |

#### Transcript Filter（0.9.0+）

Stop hook 在寫進 Raw/ 前會跑一條 TOML-driven filter pipeline，把不具知識價值的
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
Weekly/YYYY/                   ← 整理後的週報
_index.md                      ← 全 vault 摘要索引
log.md                         ← evolve/distill 的時序歷程
```

### Data Flow

```
每個 session:
  SessionStart → 提示有 memory 可用 → 使用者決定是否載入
  工作...
  session 結束 → Stop hook → 確認 → Raw/

隨時:
  /cortex:evolve    → Notes/Projects + _index.md + log.md + vector store
  /cortex:query     → vector search → 精確讀檔

定期:
  /cortex:distill   → Raw → Notes/Projects (+ pending-merge → broadcast)
  /cortex:broadcast → pending-merge → 融合進既有 Notes/Projects
  /cortex:weekly    → distill + GitLab + CSS → Weekly/
```

### Retrieval Strategy

分層檢索，避免 token 浪費：

1. **Vector Search**（主要）— `cortex-vec search` 語意搜尋，ranked results
2. **Grep Fallback**（補充）— 精確字串搜尋 Notes/Projects
3. **Raw Search**（按需）— 只在追溯時查詢原始 session 記錄

## cortex-vec CLI

Vault 的語意索引工具，用 ChromaDB + OpenAI `text-embedding-3-small`，搭配
`gpt-4o-mini` 產雙語 summary 作為第二組 embedding（dual-vector）以提升中英混合
查詢的 recall。

```bash
cortex-vec status                          # 查看索引狀態
cortex-vec rebuild                         # 完整重建索引
cortex-vec search "nginx certificate"      # 語意搜尋
cortex-vec search "oauth" --repo libsynow3 # 按 repo 過濾
cortex-vec search "sharing" --type project # 按類型過濾
cortex-vec upsert Notes/Nginx/new.md       # 新增/更新單一文件
cortex-vec delete Notes/Nginx/old.md       # 刪除文件
```

## Configuration

`~/.cortex/config.json`（由 genesis 產生）：

```json
{
  "vault_path": "/path/to/vault",
  "author": "tonyhu",
  "author_email": "tonyhu@synology.com",
  "git": {
    "auto_commit": true,
    "auto_push": false
  },
  "weekly": {
    "gitlab_username": "tonyhu",
    "categories": ["fix", "feat", "misc"]
  }
}
```

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key，用於 text-embedding-3-small |
| `CORTEX_VAULT_PATH` | No | 覆蓋 config.json 的 vault_path |

## Dependencies

| Package | Purpose |
|---------|---------|
| [ChromaDB](https://www.trychroma.com/) | 語意向量索引 |
| [OpenAI](https://platform.openai.com/) | text-embedding-3-small embedding model |
| [python-frontmatter](https://python-frontmatter.readthedocs.io/) | YAML frontmatter 解析 |
| pysqlite3-binary | SQLite 3.35+ 相容（系統 SQLite 太舊時需要） |

安裝：

```bash
pip install -e ./cortex-vec
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

Licensed under the [Apache License 2.0](LICENSE) — see `LICENSE` for full text.
