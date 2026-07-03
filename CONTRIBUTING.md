# 貢獻指南

歡迎為 Cortexes 貢獻。這份文件說明如何設定開發環境、跑測試、以及送出變更。

參與本專案即表示你同意遵守 [行為準則](CODE_OF_CONDUCT.md)。

## 專案結構

Cortexes 用兩個 branch 分工：

| Branch | 內容 |
|--------|------|
| `plugin`（預設） | Claude Code plugin —— commands、skills、hooks、`cortex-vec` CLI、官網原始碼 |
| `main` | 個人 Obsidian vault 資料（不接受外部貢獻） |

**所有 PR 都以 `plugin` 為目標 branch。**

主要子系統：

- `commands/`、`skills/`、`hooks/` —— plugin 的 slash command、自動觸發技能與 lifecycle hook
- `cortex-vec/` —— Python 語意索引 CLI（ChromaDB + OpenAI embedding + BM25 hybrid 檢索）
- `site/` —— 官網靜態產生器（零依賴，只用 Node 內建）

## 開發環境

### cortex-vec（Python）

```bash
pip install -e ./cortex-vec
```

需要 Python 3.11+。語意搜尋相關功能需 `OPENAI_API_KEY`；未設定時會自動降級為 BM25-only，
測試不需要 API key。

### 官網（Node）

零 npm 依賴，只需 Node 18+：

```bash
node site/build.mjs                    # 產出到 site/dist/
node --test site/tests/*.test.mjs      # 跑測試
```

## 跑測試

送 PR 前請確認測試通過。

**Python（cortex-vec）** —— 專案的測試 gate 一次跑完 ruff lint + pytest：

```bash
./scripts/run-checks.sh
```

建議安裝 pre-commit hook，讓每次 `git commit` 自動跑這道 gate：

```bash
pip install pre-commit
pre-commit install
```

**官網** ——

```bash
node --test site/tests/*.test.mjs
```

## Commit 慣例

本專案採 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <描述>
```

常見 type：`feat`、`fix`、`docs`、`chore`、`refactor`、`test`、`ci`。
scope 用子系統名，例如 `feat(takeoff):`、`fix(cortex-vec):`、`ci(site):`。

## 送出 PR

1. 從 `plugin` 開分支。
2. 做變更，確認相關測試通過。
3. 開 PR 指向 `plugin`，在描述裡說明**做了什麼**與**如何驗證**。
4. CI 會跑測試；官網變更另外會由 Cloudflare Pages 產生 preview 部署。

## 回報問題

- **Bug** 與 **功能建議** 請用對應的 [issue template](https://github.com/XBlueSky/cortexes/issues/new/choose)。
- **安全性問題** 請勿開公開 issue，見 [SECURITY.md](SECURITY.md)。

## 授權

送出貢獻即表示你同意以專案的 [Apache License 2.0](LICENSE) 授權你的貢獻。
