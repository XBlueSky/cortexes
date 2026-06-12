#!/bin/bash
set -euo pipefail

# Resolve vault path: env var > config.json > skip
CORTEX_CONFIG="$HOME/.cortex/config.json"
CORTEX_DIR=""

if [[ -n "${CORTEX_VAULT_PATH:-}" ]]; then
  CORTEX_DIR="$CORTEX_VAULT_PATH"
elif [[ -f "$CORTEX_CONFIG" ]]; then
  CORTEX_DIR=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null || echo "")
fi

# No vault configured, skip silently
if [[ -z "$CORTEX_DIR" || ! -d "$CORTEX_DIR" ]]; then
  exit 0
fi

# Read stdin JSON, extract .cwd
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd // ""' 2>/dev/null || echo "")
[[ -z "$cwd" ]] && exit 0

# Detect repo name from cwd via git remote
repo_name=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || true)
fi
[[ -z "$repo_name" ]] && exit 0

# --- Lightweight status: only check weekly report (no Raw scanning) ---

today_dow=$(date +%u)  # 1=Mon .. 7=Sun
days_since_monday=$(( (today_dow - 1) % 7 ))
week_monday=$(date -d "-${days_since_monday} days" +%Y-%m-%d 2>/dev/null \
  || date -v-"${days_since_monday}"d +%Y-%m-%d 2>/dev/null \
  || date +%Y-%m-%d)
week_year="${week_monday%%-*}"
weekly_file="$CORTEX_DIR/Weekly/$week_year/$week_monday.md"

if [[ -f "$weekly_file" ]]; then
  weekly_status="已產生"
else
  weekly_status="尚未產生"
fi

# --- Vault topic summary (top-level Notes/ and Projects/ entries) ---
# Gives the model grounding to recognize when an incoming user request
# matches an existing vault topic, so cortex-query triggers proactively.
notes_topics=""
projects_topics=""
if [[ -d "$CORTEX_DIR/Notes" ]]; then
  notes_topics=$(find "$CORTEX_DIR/Notes" -mindepth 1 -maxdepth 1 \
    \( -type d -o -name '*.md' \) 2>/dev/null \
    | sed 's#.*/##; s/\.md$//' | grep -v '^_' | sort | paste -sd',' - | sed 's/,/, /g' || true)
fi
if [[ -d "$CORTEX_DIR/Projects" ]]; then
  projects_topics=$(find "$CORTEX_DIR/Projects" -mindepth 1 -maxdepth 1 \
    \( -type d -o -name '*.md' \) 2>/dev/null \
    | sed 's#.*/##; s/\.md$//' | grep -v '^_' | sort | paste -sd',' - | sed 's/,/, /g' || true)
fi
[[ -z "$notes_topics" ]] && notes_topics="(空)"
[[ -z "$projects_topics" ]] && projects_topics="(空)"

# --- Build interactive menu prompt ---
read -r -d '' context <<'PROMPT_TEMPLATE' || true
[Cortex] 你目前在 __REPO__ repo。Cortex vault 位於 __VAULT__（非 CWD），所有 vault 操作請使用此路徑。

Vault 目前涵蓋的主題（重要 — 用來判斷是否要主動查 cortex）：
  - Notes/: __NOTES_TOPICS__
  - Projects/: __PROJECTS_TOPICS__

主動查詢規則（由 using-cortex skill 強制執行，無論使用者是否選 1-4 都生效）：
- 若使用者後續的請求**命中**上述任一主題，**先**用 cortex-query 查 vault 再回答，不要憑印象或重新探索。
- 若使用者問的是 ongoing project / 內部工具 / 重複出現過的領域，預設假設 vault 有 prior context，先查再說。
- 「主動查」的成本遠低於「答錯後重來」。寧可多查一次。
- 詳細規則見 using-cortex skill。

在你第一次回覆使用者時，呈現以下格式：

先顯示 vault 狀態：
  - 本週週報__WEEKLY_STATUS__

然後列出選項：
1. 載入此 repo 的記憶筆記（執行 cortex-vec search --repo __REPO__）
2. 查看最近的 session 紀錄（列出 __VAULT__/Raw/ 中最近幾筆）
3. 處理待辦事項（提煉未處理的紀錄 或 產生週報）
4. 直接開始工作

規則：
- 選項 3 被選中時，才去掃描 __VAULT__/Raw/ 找未提煉的紀錄（cortex-vec distill-queue --root __VAULT__/Raw）。不要用 grep 找 marker：meta-session 內文會引用該字串騙過 grep。
- 不要在使用者選擇前預先掃描 Raw/
- 使用者可以回覆編號或直接說需求
- 保持簡短，不要過度解釋每個選項
- 即使使用者選 4「直接開始工作」，主動查詢規則仍生效
PROMPT_TEMPLATE

# Substitute placeholders
context="${context//__REPO__/$repo_name}"
context="${context//__VAULT__/$CORTEX_DIR}"
context="${context//__WEEKLY_STATUS__/$weekly_status}"
context="${context//__NOTES_TOPICS__/$notes_topics}"
context="${context//__PROJECTS_TOPICS__/$projects_topics}"

# Use jq for safe JSON encoding
jq -n --arg ctx "$context" \
  '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'

exit 0
