# Cortex 官網

以 `manifest.json` + `CHANGELOG.md` 為 single source of truth 的靜態官網。

## Build

    node site/build.mjs

產物在 `site/dist/`（gitignored）。零 npm 依賴，只用 Node 內建。

## 測試

    node --test site/tests/*.test.mjs

## 部署（Cloudflare Pages）

Cloudflare Pages 後台連 GitHub repo：
- Production branch: `plugin`
- Build command: `node site/build.mjs`
- Build output directory: `site/dist`

CI 不負責部署，只重產 `manifest.json` 與跑 `cc-marketspec --check`。
