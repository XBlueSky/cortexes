# Cortex 官網

以 `manifest.json` + `CHANGELOG.md` 為 single source of truth 的靜態官網。

## Build

    node site/build.mjs

產物在 `site/dist/`（gitignored）。零 npm 依賴，只用 Node 內建。

## 測試

    node --test site/tests/*.test.mjs

## 部署（Cloudflare Pages）

由 GitHub Actions（`.github/workflows/site.yml`）build 後用 wrangler 推到
Cloudflare Pages 的 **Direct Upload** 專案 —— CF 後台不連 Git，部署邏輯全在 workflow 內。

一次性設定：

1. Cloudflare 後台 → Workers & Pages → 建 **Direct Upload** 專案，名稱 `cortex`
   （對齊 workflow 裡的 `--project-name=cortex`；改名兩處都要改）。
   在專案 Settings → Builds & deployments 把 **Production branch** 設為 `plugin`。
2. GitHub repo → Settings → Secrets and variables → Actions 新增：
   - `CLOUDFLARE_API_TOKEN`（權限 Account → Cloudflare Pages → Edit）
   - `CLOUDFLARE_ACCOUNT_ID`

workflow 觸發：push 到 `plugin` / `feat/website-site`、對應 PR，或手動 dispatch。
`test` job 跑單元測試 + smoke build；`deploy` job 只在 push 到部署 branch 時執行
（PR 不部署，避免 secret 外洩）。wrangler 以 `--branch=<推送的 branch>` 部署，
CF 依 Production branch 設定判定該次為 production 或 preview。
