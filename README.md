# Cortex

Personal knowledge vault plugin for Claude Code — session recording, memory distillation, weekly reports, indexed retrieval.

## Overview

Cortex 是一個 Obsidian vault + Claude Code plugin。vault 儲存工作記憶，plugin 提供自動記錄、提煉、檢索等功能。

**設計哲學：** Vault 是 source of truth（純 markdown + git），vector store 是可重建的衍生索引。

## Architecture

```
cortex repo
├── plugin branch (orphan)     ← Claude Code plugin（本檔案所在）
└── main branch                ← Obsidian vault 資料

~/.cortex/
├── config.json                ← genesis 產生的設定
├── distill-state.json         ← distill 處理狀態快取
└── vectorstore/               ← ChromaDB 語意索引（local only，不在 git）
```

### Vault Structure (main branch)

```
Raw/YYYY/MM/DD/                ← session dumps（完整，按需提煉）
Notes/<category>/              ← 提煉後的技術知識
Projects/<repo-name>/          ← 以 repo 為主的專案筆記
Weekly/YYYY/                   ← 整理後的週報
_index.md                      ← 全 vault 摘要索引（分層檢索用）
```

## Install

```bash
# 從 GitLab
/plugin marketplace add git@git.synology.inc:tonyhu/cortex.git#plugin

# 從 GitHub
/plugin marketplace add https://github.com/XBlueSky/cortex.git#plugin
```

安裝後執行初始化：

```bash
/cortex:genesis /path/to/your/vault
```

## Commands

| Command | Description |
|---------|-------------|
| `/cortex:genesis` | 初始化 vault — 設定路徑、author、重建 index 和 distill state |
| `/cortex:evolve` | 手動存入知識到 Notes 或 Projects |
| `/cortex:distill` | 提煉 Raw/ session 記錄到 Notes/Projects |
| `/cortex:weekly` | 整理週報（distill + GitLab activity + CSS tickets） |

## Skills

| Skill | Trigger |
|-------|---------|
| cortex-evolve | 「存到 cortex」「記一下」「save to cortex」 |
| cortex-distill | 「提煉」「整理 raw」「distill」 |
| cortex-weekly | 「整理週報」「產生週報」「weekly report」 |
| cortex-query | 「查 cortex」「之前有記過」「cortex 裡有沒有」 |

## Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| Session Report | Stop | session 結束時產出完整報告（含 commits、發現、決策），確認後寫到 Raw/ |
| Memory Injection | SessionStart | 偵測當前 repo，詢問使用者是否載入 cortex memory |

## Data Flow

```
每個 session:
  SessionStart → 提示有 memory 可用 → 使用者決定是否載入
  工作...
  session 結束 → Stop hook → 確認 → Raw/

隨時:
  /cortex:evolve → Notes/Projects + _index.md
  /cortex:query → _index.md → 精確讀檔

定期:
  /cortex:distill → Raw → Notes/Projects + _index.md
  /cortex:weekly → distill + GitLab + CSS → Weekly/
```

## Retrieval Strategy

分層檢索，避免 token 浪費：

1. **Vector Search**（主要）— `cortex-vec search` 語意搜尋，ranked results
2. **Grep Fallback**（補充）— 精確字串搜尋 Notes/Projects
3. **Raw Search**（按需）— 只在追溯時查詢原始 session 記錄

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

## Dependencies

- Python 3.8+
- [ChromaDB](https://www.trychroma.com/) — 語意向量索引
- [python-frontmatter](https://python-frontmatter.readthedocs.io/) — YAML frontmatter 解析
- pysqlite3-binary — SQLite 3.35+ 相容（系統 SQLite 太舊時需要）

安裝：`pip install -e ./cortex-vec`

## License

Private — for personal use.
