# Cortex

Personal knowledge vault plugin for Claude Code — session recording, memory distillation, weekly reports, indexed retrieval.

## Overview

Cortex 是一個 Obsidian vault + Claude Code plugin。vault 儲存工作記憶，plugin 提供自動記錄、提煉、檢索等功能。

**設計哲學：** 零外部依賴，純 markdown + JSON + git。

## Architecture

```
cortex repo
├── plugin branch (orphan)     ← Claude Code plugin（本檔案所在）
└── main branch                ← Obsidian vault 資料

~/.cortex/
├── config.json                ← genesis 產生的設定
└── distill-state.json         ← distill 處理狀態快取
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
| Memory Injection | SessionStart | 讀 `_index.md`，match 當前 repo，注入相關記憶到 context |

## Data Flow

```
每個 session:
  SessionStart → 注入相關記憶
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

1. **_index.md**（快）— 每個檔案一行摘要 + tags，SessionStart 自動注入
2. **Notes/Projects**（中）— grep 搜尋精煉後的完整內容
3. **Raw/**（慢）— 只在追溯時查詢原始 session 記錄

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

## License

Private — for personal use.
