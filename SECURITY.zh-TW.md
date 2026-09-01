<sub>[English](SECURITY.md) · [繁體中文](SECURITY.zh-TW.md)</sub>

# 安全政策

## 回報漏洞

若你發現安全性問題，**請勿開公開 issue**。

請透過 GitHub 的 [private vulnerability reporting](https://github.com/XBlueSky/cortexes/security/advisories/new)
私下回報。我們會盡快回覆並協調修復與揭露。

回報時請盡量包含：

- 問題類型與受影響的元件（`cortex-vec`、hooks、官網等）
- 重現步驟或概念驗證
- 潛在影響

## 使用者須知

Cortexes 會處理你的個人知識 vault 與 API 憑證，請留意：

- **`OPENAI_API_KEY`** 由環境變數提供，不會被寫進 vault 或索引。請勿把它 commit 進任何 repo。
- **Vault 內容** 是你的原始 session 記錄與筆記。索引（ChromaDB / BM25）儲存在本機 `~/.cortex/`，
  預設不進 git、不上傳。
- **語意搜尋** 會把待索引的文件內容送到 OpenAI 產生 embedding。若你的 vault 含敏感資料，
  請自行評估；未設定 `OPENAI_API_KEY` 時**不會有任何 vault 內容送往 OpenAI**，搜尋改走
  本機 BM25 索引。
- **被檢索到的內容仍然會進到 Anthropic。** Cortexes 是 Claude Code plugin：query、distill、
  broadcast 或 takeoff resume 從 `Notes/`、`Projects/`、`Raw/`、`.takeoff/` 讀出來的內容，
  都會進入當前 Claude Code session，並在你自己的帳號底下由 Anthropic 處理。即使在
  BM25-only 模式也是如此。這是一般的 Claude Code 處理，不是 Cortexes 的伺服器或 telemetry
  通道——見 [PRIVACY.zh-TW.md](PRIVACY.zh-TW.md)。

## 支援版本

本專案採滾動釋出，安全修復針對最新版本。請更新到最新版再回報。
