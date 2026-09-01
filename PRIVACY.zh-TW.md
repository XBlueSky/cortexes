<sub>[English](PRIVACY.md) · [繁體中文](PRIVACY.zh-TW.md)</sub>

# 隱私政策

**最後更新：2026-09-01**

Cortexes 是一個 local-first 的 Claude Code plugin。你的知識庫就是你指定
目錄下的純 Markdown 檔案，索引也建在本機。**Cortexes 的作者不會收到你的
任何資料——沒有伺服器、沒有帳號、沒有 telemetry。** 會離開你機器的資料，
只流向你本來就在用或自己設定的服務——透過你自己的 Claude Code 到
Anthropic、設了 key 才會用到的 OpenAI，以及你若開啟推送才會用到的 git
remote——下面會完整說明。

本文件涵蓋 plugin 本身（commands、skills、hooks）以及它依賴的
`cortex-vec` CLI。

## 一眼看完

| 資料 | 流向 | 預設 |
|---|---|---|
| Session 逐字記錄 | 你的本機 vault（`Raw/`） | **開啟** |
| 過濾時超過 12 KB 的文字區塊 | Anthropic，透過你自己的 Claude Code | **開啟**（可關閉） |
| Session 開始時注入的 vault metadata（repo 名稱、vault 路徑、主題名稱、baton 摘要） | Anthropic，透過你自己的 Claude Code | **開啟**（可關閉） |
| query／distill／broadcast／takeoff resume 過程中讀取的 vault 頁面 | Anthropic，透過你自己的 Claude Code | 使用這些流程時**必然發生** |
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

### Session 開始時注入的 vault metadata

通往 Anthropic 的路徑不只分類器這一條。另外，`SessionStart` hook 會在你的
第一則訊息被回答之前，**把 vault metadata 加進該 session 的 context**。它
注入的內容包括：

- 目前的 **repo 名稱**（由 `origin` git remote 推導）；
- 你的 **vault 在磁碟上的絕對路徑**；
- `Notes/` 與 `Projects/` 底下每一個頂層項目的**主題名稱** —— 只有目錄與
  檔案名稱，不含頁面內容；
- 此 repo 每一份待處理 takeoff baton 的 **topic** 與單行 **`summary:`**；
  另外，當 baton 的 **`workdir:`** 與目前 repo 的 toplevel 不同時，該路徑
  也會一併注入（同名 clone 的 baton 會標示來源）。

這就是一般的 session context，所以只要該 session 與模型互動，這些內容就會
連同對話其餘部分一起送往 Anthropic —— 透過**你自己的 Claude Code 安裝與你
自己的 Anthropic 憑證**，適用你帳號 session 的一般處理方式。Cortexes 不會
把它送到別的地方。

頁面**內容**不會在 session 開始時被注入。但它們仍可能在同一個 session
稍後被載入——在你選了選單選項、執行了 `/cortexes:query` 之類的指令，或提
出符合 `using-cortex` 四個訊號之一的請求之後——屆時適用上一節的說明。

**注入發生在選單顯示之前，所以無法在選單階段拒絕。** 選擇選項 4
（「直接開始工作」）會停止後續載入任何 vault 內容，並在該 session 後續不再
主動搜尋，但它**無法收回已經進入 context 的 metadata**。如果 repo 名稱、
vault 路徑，或某個主題／baton 摘要本身就是敏感資訊，請直接停用該 hook，
不要倚賴選單 —— 見 [§7](#7-如何關閉各項功能)。

### 一般使用中被載入的 vault 內容

Cortexes 是一個 Claude Code plugin，它的 skill 就是靠**把 vault 檔案讀進
對話**來運作的。只要你跑 query、distill、broadcast，或 resume 一份 takeoff
baton，這些流程開啟的頁面——位於 `Notes/`、`Projects/`、`Raw/`、
`.takeoff/`——就會成為當前 Claude Code context 的一部分，並隨 session 其餘
內容一起送往 Anthropic，就跟你在 Claude Code 裡打開任何檔案一樣。

這是**在你自己帳號底下的一般 Claude Code 處理**，用的是你自己的安裝與你
自己的憑證，適用你 Claude Code session 本來就適用的資料處理方式。它**不是**
Cortexes 的伺服器、不是 telemetry 通道、也不是另外一次上傳；Cortexes 沒有
伺服器，也收不到任何東西。但這確實表示「我的 vault 內容會不會進到模型？」
的誠實答案是：**會——只要 Cortexes 的流程讀到它**。這正是本 plugin 的用途：
被檢索出來的那一頁，就是答案的依據。

範圍是「該流程實際讀到什麼」，不是整個 vault：

- **query**（`/cortexes:query`，或 `using-cortex` 的訊號）——它呈現的搜尋
  命中，以及你接著要求它打開的頁面。
- **distill**——正在提煉的 `Raw/` 記錄（map-first，能只讀片段就不讀整檔）
  以及它寫出的頁面。
- **broadcast**——正在融合的 `Raw/` 記錄，以及它開啟或編輯的每個候選頁面。
- **takeoff resume**——該工作線的 `.takeoff/` baton 檔。

如果一頁內容敏感到不該送進模型，那它也敏感到不該放在一個會被模型搜尋的
vault 裡。請把它放到別的地方。

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

沒有。Cortexes 不做任何分析回報、使用統計、當機回報或更新檢查，作者也
收不到任何東西。

由 plugin 自身程式碼發出的對外網路流量只到三個目的地：Anthropic，用於
過濾器的分類呼叫（[§2](#2-送往-anthropic-的資料)）；OpenAI，用於
[§3](#3-送往-openai-的資料) 描述的 embedding、摘要產生與選用的重排序；
以及你在 `git.auto_push` 開啟時所設定的 git remote
（[§5](#5-git-行為)）。

另外——這不是 Cortexes 的網路通道——由於本 plugin 跑在 Claude Code **內**，
每一個把 vault 內容讀進對話的流程，都是由 **Claude Code 自己送往 Anthropic
的 session 請求**承載的，在你的帳號底下。見
[§2](#一般使用中被載入的-vault-內容)。

## 7. 如何關閉各項功能

| 目的 | 做法 |
|---|---|
| 跳過某一次 session 的錄製 | 在該 session 環境設定 `CORTEX_SKIP_RECORD=1` |
| 完全停止錄製 | 從 `hooks/hooks.json` 移除 `SessionEnd` 項目，或停用整個 plugin |
| 停止過濾器對 Anthropic 的分類呼叫 | 設定 `CORTEX_NO_CLASSIFIER=1` |
| 停止在 session 開始時注入 vault metadata | 從 `hooks/hooks.json` 移除 `SessionStart` 項目，或停用整個 plugin |
| 停止送任何資料給 OpenAI | 取消設定 `OPENAI_API_KEY`——檢索退回本機 BM25 |
| 停止自動 commit | 把 `~/.cortex/config.json` 的 `git.auto_commit` 設為 `false` |
| 停止推送到 remote | 把 `git.auto_push` 設為 `false`（此為預設值） |

把上述項目都關掉之後，錄製、建索引與詞彙搜尋會完全在本機進行。但這
**不會**讓 plugin 變成離線：query、distill、broadcast 與 takeoff resume
都是由 Claude 驅動的流程，使用它們就必然會把讀到的 vault 內容放進你的
Claude Code session，並由 Anthropic 處理
（[§2](#一般使用中被載入的-vault-內容)）。`CORTEX_NO_CLASSIFIER=1` 只會
停掉過濾器那組巢狀分類呼叫，對一般 Claude session 的處理沒有任何影響。

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
