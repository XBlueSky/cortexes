# Cortex 官網

以 `manifest.json` + `CHANGELOG.md` 為 single source of truth 的靜態官網。

## Build

    node site/build.mjs

產物在 `site/dist/`（gitignored）。零 npm 依賴，只用 Node 內建。

## 測試

    node --test site/tests/*.test.mjs

## 部署（Cloudflare Pages）

由 Cloudflare Pages 的 **Git 整合**負責 —— CF 後台連本 repo，監聽 push 後在 CF
環境自行 build 並發佈。GitHub Actions 不部署，只跑測試 + smoke build 當品質關卡。

一次性設定（在 Cloudflare 後台）：

1. Workers & Pages → Create → Pages → **Connect to Git**，授權並選 `XBlueSky/cortexes`。
2. Build 設定：
   - **Production branch**：`plugin`
   - **Framework preset**：None
   - **Build command**：`node site/build.mjs`
   - **Build output directory**：`site/dist`
   - **Root directory**：留空
3. Save and Deploy。

之後 push 到 `plugin` 會發佈到正式站，其他 branch / PR 會產生 preview 部署。
無需任何 API token 或 GitHub secret。
