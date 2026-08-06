<sub>[English](PRIVACY.md) · [繁體中文](PRIVACY.zh-TW.md)</sub>

# 隱私政策

**最後更新：2026-08-06**

Cortexes 是一個 local-first 的 Claude Code plugin。你的知識庫就是你指定
目錄下的純 Markdown 檔案，索引也建在本機。**Cortexes 的作者不會收到你的
任何資料——沒有伺服器、沒有帳號、沒有 telemetry。** 唯一會離開你機器的
資料，只流向你自己設定的服務，下面會完整說明。

本文件涵蓋 plugin 本身（commands、skills、hooks）以及它依賴的
`cortex-vec` CLI。

## 一眼看完

| 資料 | 流向 | 預設 |
|---|---|---|
| Session 逐字記錄 | 你的本機 vault（`Raw/`） | **開啟** |
| 過濾時超過 12 KB 的文字區塊 | Anthropic，透過你自己的 Claude Code | **開啟**（可關閉） |
| Vault 頁面內容，用於建索引 | OpenAI | 僅在設有 `OPENAI_API_KEY` 時 |
| Vault commit | 你的本機 git repo | **開啟** |
| Vault push 到 git remote | 你設定的那個 remote | **關閉**（需自行開啟） |
| 任何資料 | Cortexes 作者 | 永不 |

## 1. Session 錄製

Claude Code session 結束時，`SessionEnd` hook 會把該次 session 過濾後寫進
你的 vault。**這是自動發生的，不會逐次詢問確認。** 這是本 plugin 的核心
功能；在啟用 cortex 的環境裡，除非你主動停用（見
[§7](#7-如何關閉各項功能)），否則應該假設每一次 session 都會被記錄。

**讀取什麼。** Claude Code 會把當次 session 的 transcript 路徑傳給 hook，
hook 讀取該檔案。它也會讀取工作目錄，從 `origin` git remote 推導出
repository 名稱，僅用於標記與分組該筆記錄。

**寫入什麼。** 一個位於
`<vault>/Raw/YYYY/MM/DD/HHMMSS_session_<repo>.md` 的 Markdown 檔，內容
包含你的訊息、Claude 的回覆，以及工具活動——工具呼叫會被縮減成簡短的
參數預覽，工具輸出則由
[§2](#2-送往-anthropic-的資料) 描述的過濾管線壓縮。

**寫入前會排除什麼。** 型別為 `attachment`、`file-history-snapshot`、
`permission-mode`、`system`、`last-prompt` 的記錄，以及
`<local-command-stdout>`、`<local-command-stderr>`、
`<local-command-caveat>`、`<system-reminder>`、`<command-message>`、
`<command-args>` 這些標籤的內容。

**何時會跳過錄製。** 符合下列任一條件就不會寫入：transcript 小於 4096
bytes、`~/.cortex/config.json` 不存在或其中的 `vault_path` 無效、設有
`CORTEX_SKIP_RECORD=1`、或該 session 本身就是過濾器發出的巢狀
`claude -p` 呼叫。

**不會偵測或遮蔽敏感內容。** 如果 session 裡出現了密鑰、憑證或個人資料，
它就會出現在記錄裡。請以看待原始 session 的同等謹慎來看待你的 vault。

## 2. 送往 Anthropic 的資料

Transcript 過濾器會壓縮機器產生的雜訊、保留討論內容。這件事大部分由本機
的 regex 與規則式過濾完成。對於通過那幾層之後、單一區塊仍**超過
12 KB** 的文字，過濾器會請模型判斷它屬於 `log` 還是 `content`，藉此決定
該區塊能否安全地只保留頭尾。

這個分類呼叫會把**該區塊最多 8 KB 的文字**送往 Anthropic。它有**每次
session 最多 5 次呼叫**的上限，每次 20 秒逾時，並且是透過 `claude -p`
執行——也就是說，用的是**你自己的 Claude Code 安裝與你自己的 Anthropic
憑證**。Cortexes 不持有也不代理任何 Anthropic key。

若呼叫失敗、逾時或被停用，該區塊會原樣完整保留——這個功能只影響壓縮
程度，永遠不影響你的資料是否被保存。

設定 `CORTEX_NO_CLASSIFIER=1` 即可完全停用。

## 3. 送往 OpenAI 的資料

所有 OpenAI 功能都需要你自行設定 `OPENAI_API_KEY`。**沒有設定這個變數
時，不會有任何資料送往 OpenAI**，檢索會完全跑在本機的 BM25 索引上。這把
key 從環境變數讀取，永遠不會被寫進 vault、索引或任何設定檔。

有三個功能會用到它：

**Embeddings**（`text-embedding-3-small`）——當你執行 `cortex-vec
rebuild` 或 `upsert`、或進行向量搜尋時，被索引的 vault 頁面文字或你的
查詢字串會送往 OpenAI。

**摘要**——當某個頁面沒有摘要時，該頁的標題、標籤，以及**內文的前 3000
個字元**會送往 OpenAI 以產生一行摘要。

**重排序（Rerank）**——預設關閉。啟用時（`--rerank`，或設定檔的
`retrieval.rerank`），你的查詢字串加上前約 15 筆結果的標題與摘要會送往
OpenAI 進行重新排序。

請注意，`Raw/` 的 session 記錄**預設不會被索引**——向量與 BM25 索引只
涵蓋 `Notes/` 與 `Projects/`。Raw 內容只有在你把它提煉成筆記之後，才
可能到達 OpenAI。

## 4. 資料存在哪裡、保存多久

全部都在你自己的機器上：

| 路徑 | 內容 |
|---|---|
| `<vault>/` | 你的筆記、專案，以及 `Raw/` session 記錄（Markdown + git） |
| `~/.cortex/config.json` | Vault 路徑、作者姓名與 email、git 旗標 |
| `~/.cortex/vectorstore/` | ChromaDB 向量索引 |
| `~/.cortex/bm25/` | BM25 詞彙索引 |
| `${XDG_CACHE_HOME:-~/.cache}/cortex/distill-plans/` | 提煉流程的工作狀態 |

**保存期限無限，且完全由你控制。** Cortexes 不會自行讓資料過期、輪替或
刪除。唯一的例外是 `reclaim-superseded`，它會移除那些「內容是同一段對話
較長記錄之嚴格前綴」的冗餘 `Raw/` 記錄——刪掉的是重複品，永遠不是獨有
內容。

## 5. Git 行為

你的 vault 是一個 git repository。`~/.cortex/config.json` 裡有兩個旗標
控制 plugin 對它做什麼：

- **`git.auto_commit`**——預設 **`true`**。寫入 session 記錄後，plugin
  會把它 commit 進你的本機 repository。
- **`git.auto_push`**——預設 **`false`**。若你開啟它，plugin 會在 commit
  之後執行 `git push`，把你的 vault 送往你設定的那個 remote。

**一旦啟用 `auto_push`，你的 session 記錄就會離開你的機器。** 去到哪裡
完全取決於你的 git remote——請確認那是一個你控制、且可見性符合你預期的
repository。推到公開 repository 的 vault 就是公開的。

由於 commit 是自動的，從 vault 刪掉檔案並不會把它從 git 歷史中抹除。
見 [§8](#8-刪除你的資料)。

## 6. Telemetry

沒有。Cortexes 不做任何分析回報、使用統計、當機回報或更新檢查。整個
程式庫裡唯一的對外網路請求，就是上面描述的 OpenAI 與 Anthropic 呼叫。

## 7. 如何關閉各項功能

| 目的 | 做法 |
|---|---|
| 跳過某一次 session 的錄製 | 在該 session 環境設定 `CORTEX_SKIP_RECORD=1` |
| 完全停止錄製 | 從 `hooks/hooks.json` 移除 `SessionEnd` 項目，或停用整個 plugin |
| 停止送任何資料給 Anthropic | 設定 `CORTEX_NO_CLASSIFIER=1` |
| 停止送任何資料給 OpenAI | 取消設定 `OPENAI_API_KEY`——檢索退回本機 BM25 |
| 停止自動 commit | 把 `~/.cortex/config.json` 的 `git.auto_commit` 設為 `false` |
| 停止推送到 remote | 把 `git.auto_push` 設為 `false`（此為預設值） |

把所有遠端功能都關閉後，剩下的是一個完全離線、完全本機的 plugin，而
錄製、提煉與詞彙搜尋的功能不會有任何縮水。

## 8. 刪除你的資料

- **個別記錄**——刪除 `<vault>/Raw/` 底下的檔案。若當時 `auto_commit`
  是開啟的，還需要改寫 git 歷史（例如用 `git filter-repo`），有 remote
  的話要 force-push；單純 `rm` 再 commit 會讓內容仍可從歷史中復原。
- **整個索引**——`rm -rf ~/.cortex/vectorstore ~/.cortex/bm25`。索引是
  衍生資料，隨時可以用 `cortex-vec rebuild` 從 vault 重建。
- **所有本機資料**——`rm -rf ~/.cortex` 並刪除你的 vault 目錄。
- **已經送往第三方的資料**——請依下列各家政策，直接向 OpenAI 或
  Anthropic 申請刪除。Cortexes 無法代你收回。

## 9. 第三方服務

當你啟用上述功能時，你的資料會依這些供應商的政策處理：

- [OpenAI 隱私政策](https://openai.com/policies/privacy-policy) 與
  [API 資料使用政策](https://openai.com/policies/api-data-usage-policies)
- [Anthropic 隱私政策](https://www.anthropic.com/legal/privacy)

除了作為其 API 的使用端之外，Cortexes 與這兩家公司沒有任何從屬關係。

## 10. 變更與聯絡方式

本政策的實質變更會記錄在 [`CHANGELOG.md`](CHANGELOG.md)。隱私相關問題
可以開 [GitHub issue](https://github.com/XBlueSky/cortexes/issues)；安全
漏洞請改依 [`SECURITY.md`](SECURITY.md) 的流程回報。
