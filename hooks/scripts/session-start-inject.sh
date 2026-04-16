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

# --- Vault status detection ---

# Count unprocessed Raw files (no <!-- distilled: marker)
undistilled=0
if [[ -d "$CORTEX_DIR/Raw" ]]; then
  while IFS= read -r -d '' f; do
    grep -q '<!-- distilled:' "$f" 2>/dev/null || undistilled=$((undistilled + 1))
  done < <(find "$CORTEX_DIR/Raw" -name '*.md' -type f -print0 2>/dev/null)
fi

# Check if this week's weekly report exists
# Weekly file uses Monday date: Weekly/YYYY/YYYY-MM-DD.md
today_dow=$(date +%u)  # 1=Mon .. 7=Sun
days_since_monday=$(( (today_dow - 1) % 7 ))
week_monday=$(date -d "-${days_since_monday} days" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
week_year="${week_monday%%-*}"
weekly_file="$CORTEX_DIR/Weekly/$week_year/$week_monday.md"

if [[ -f "$weekly_file" ]]; then
  weekly_status="已產生"
else
  weekly_status="尚未產生"
fi

# Build status items array
status_items=()
if [[ "$undistilled" -gt 0 ]]; then
  status_items+=("${undistilled} 筆未提煉的 session 紀錄")
fi
status_items+=("本週週報${weekly_status}")

# Format status as bullet list
status_block=""
for item in "${status_items[@]}"; do
  status_block="${status_block}  - ${item}"$'\n'
done

# --- Build interactive menu prompt ---
read -r -d '' context <<'PROMPT_TEMPLATE' || true
[Cortex] 你目前在 __REPO__ repo。Cortex vault 位於 __VAULT__（非 CWD），所有 vault 操作請使用此路徑。在你第一次回覆使用者時，呈現以下格式：

先顯示 vault 狀態：
__STATUS__
然後列出選項：
1. 載入此 repo 的記憶筆記（執行 cortex-vec search --repo __REPO__）
2. 查看最近的 session 紀錄（列出 __VAULT__/Raw/ 中最近幾筆）
3. 處理待辦事項（提煉未處理的紀錄 或 產生週報）
4. 直接開始工作

規則：
- 如果沒有未提煉的紀錄且週報已產生，選項 3 顯示「✓ 已完成」而非待辦
- 使用者可以回覆編號或直接說需求
- 保持簡短，不要過度解釋每個選項
PROMPT_TEMPLATE

# Substitute placeholders
context="${context//__REPO__/$repo_name}"
context="${context//__VAULT__/$CORTEX_DIR}"
context="${context//__STATUS__/$status_block}"

# Use jq for safe JSON encoding
jq -n --arg ctx "$context" \
  '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'

exit 0
