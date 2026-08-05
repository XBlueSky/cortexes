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

# Detect repo slug via the shared derivation (lib/repo-slug.sh) so the
# pending-baton path here matches the path the takeoff helper writes.
# shellcheck source=lib/repo-slug.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/repo-slug.sh"
repo_name="$(cortex_repo_slug "$cwd" || true)"
[[ -z "$repo_name" ]] && exit 0

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

# --- Pending takeoff batons (repo-scoped, topic-keyed, opt-in load) ---
# One menu line per baton, numbered from 5, mtime-newest first. Legacy
# single-baton files (<slug>.md) surface with topic "legacy". A baton whose
# workdir differs from the current repo toplevel gets an origin marker —
# same-slug clones (vault repo vs tool repo) see each other's lines.
takeoff_option=""
takeoff_rule=""
shopt -s nullglob
baton_files=("$CORTEX_DIR/.takeoff/$repo_name"/*.md)
legacy_baton="$CORTEX_DIR/.takeoff/$repo_name.md"
[[ -f "$legacy_baton" ]] && baton_files+=("$legacy_baton")
if ((${#baton_files[@]})); then
  cur_workdir="$(realpath "$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || true)"
  opt_num=5
  while IFS= read -r baton_file; do
    if [[ "$baton_file" == "$legacy_baton" ]]; then
      baton_topic="legacy"
    else
      baton_topic="$(basename "$baton_file" .md)"
    fi
    baton_summary="$(sed -n 's/^summary:[[:space:]]*//p' "$baton_file" | head -1)"
    [[ -z "$baton_summary" ]] && baton_summary="(無摘要)"
    baton_workdir="$(sed -n 's/^workdir:[[:space:]]*//p' "$baton_file" | head -1)"
    origin_marker=""
    if [[ -n "$baton_workdir" && -n "$cur_workdir" && "$baton_workdir" != "$cur_workdir" ]]; then
      origin_marker="（來自 ${baton_workdir}）"
    fi
    takeoff_option+=$'\n'"$opt_num. 載入交接［${baton_topic}］：$baton_summary$origin_marker"
    opt_num=$((opt_num + 1))
  done < <(ls -t -- "${baton_files[@]}")
  takeoff_rule=$'\n- 選項 5 起的「載入交接」選項被選中時：用 cortex-takeoff skill 的 resume 流程讀取該選項標示 topic 的交接文件全文，採納為續傳脈絡接續工作；不要刪除該檔。'
fi

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

列出選項：
1. 載入此 repo 的記憶筆記（執行 cortex-vec search --repo __REPO__）
2. 查看最近的 session 紀錄（列出 __VAULT__/Raw/ 中最近幾筆）
3. 處理待辦事項（提煉未處理的紀錄）
4. 直接開始工作__TAKEOFF_OPTION__

規則：
- 選項 3 被選中時，才去掃描 __VAULT__/Raw/ 找未提煉的紀錄（cortex-vec distill-queue --root __VAULT__/Raw）。不要用 grep 找 marker：meta-session 內文會引用該字串騙過 grep。
- 不要在使用者選擇前預先掃描 Raw/
- 使用者可以回覆編號或直接說需求
- 保持簡短，不要過度解釋每個選項
- 即使使用者選 4「直接開始工作」，主動查詢規則仍生效__TAKEOFF_RULE__
PROMPT_TEMPLATE

# Substitute placeholders
context="${context//__REPO__/$repo_name}"
context="${context//__VAULT__/$CORTEX_DIR}"
context="${context//__NOTES_TOPICS__/$notes_topics}"
context="${context//__PROJECTS_TOPICS__/$projects_topics}"
context="${context//__TAKEOFF_OPTION__/$takeoff_option}"
context="${context//__TAKEOFF_RULE__/$takeoff_rule}"

# Use jq for safe JSON encoding
jq -n --arg ctx "$context" \
  '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'

exit 0
