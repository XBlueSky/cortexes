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
  請自行評估；未設定 `OPENAI_API_KEY` 時可完全走本機 BM25-only，不外送任何內容。

## 支援版本

本專案採滾動釋出，安全修復針對最新版本。請更新到最新版再回報。
