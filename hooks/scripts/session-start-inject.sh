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
# SessionStart's .source (startup|resume|clear|compact) rides into the deck
# so the mod keeps the band down after a compaction; hosts that omit it start.
start_source=$(echo "$input" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")
session_id=$(echo "$input" | jq -r '.session_id // ""' 2>/dev/null || echo "")

# Detect repo slug via the shared derivation (lib/repo-slug.sh) so the
# pending-baton path here matches the path the takeoff helper writes.
# shellcheck source=lib/repo-slug.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/repo-slug.sh"
repo_name="$(cortex_repo_slug "$cwd" || true)"
[[ -z "$repo_name" ]] && exit 0

# --- Unpushed commits: the one signal auto-push failures leave behind ---
# session-end-record.sh logs a rejected push to push-failures.log but stays
# silent otherwise; without this line the vault could trail its remote for
# weeks. Only counted when the vault branch has an upstream at all.
unpushed_status=""
unpushed_text=""
unpushed=$(git -C "$CORTEX_DIR" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
if [[ "${unpushed:-0}" -gt 0 ]]; then
  unpushed_text="有 ${unpushed} 個 commit 尚未推送到 origin（失敗原因見 $(dirname "$CORTEX_CONFIG")/push-failures.log）"
  unpushed_status="先顯示 vault 狀態："$'\n'"  - ${unpushed_text}"$'\n\n'
fi

# --- Vault topic summary (top-level Notes/ and Projects/ entries) ---
# This is metadata, not content: it lists the topic names that exist so the
# model can tell whether a later request actually matches one (using-cortex
# signal 3). It never loads note bodies — that is opt-in via menu option 1.
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
baton_json=""
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
    baton_workdir="$(sed -n 's/^workdir:[[:space:]]*//p' "$baton_file" | head -1)"
    origin_marker=""
    if [[ -n "$baton_workdir" && -n "$cur_workdir" && "$baton_workdir" != "$cur_workdir" ]]; then
      origin_marker="（來自 ${baton_workdir}）"
    fi
    # The band shows a summary only when the baton has one: no placeholder.
    baton_json+="$(jq -cn --arg name "${baton_topic}${origin_marker}" --arg topic "$baton_topic" \
      --arg summary "$baton_summary" \
      '{label: $name}
       + (if $summary == "" then {} else {summary: $summary} end)
       + {prompt: "載入交接［\($topic)］：用 cortex-takeoff skill 的 resume 流程讀取 topic \($topic) 的交接文件全文，採納為續傳脈絡接續工作；不要刪除該檔。"}')"$'\n'
    [[ -z "$baton_summary" ]] && baton_summary="(無摘要)"
    takeoff_option+=$'\n'"$opt_num. 載入交接［${baton_topic}］：${baton_summary}${origin_marker}"
    opt_num=$((opt_num + 1))
  done < <(ls -t -- "${baton_files[@]}")
  takeoff_rule=$'\n- 選項 5 起的「載入交接」選項被選中時：用 cortex-takeoff skill 的 resume 流程讀取該選項標示 topic 的交接文件全文，採納為續傳脈絡接續工作；不要刪除該檔。'
fi

# --- Deck: the menu as data, for the cortexes mod's band (hooks/deck.tsx) ---
# The same facts as the text menu below, plus each button's whole prompt: the
# mod cuts the fenced block from the model's context, so a button cannot send
# a bare number. `<` and `>` become \u003c / \u003e: JSON syntax uses neither,
# so each sits inside a string, and no path or label holding `-->` can close
# the HTML comment early.
deck_status=$(jq -cn --arg unpushed "$unpushed_text" \
  'if $unpushed == "" then [] else [{text: $unpushed, warn: true}] end')
deck_batons=$(printf '%s' "$baton_json" | jq -cs '.')
# The stamp marks this run, so the mod takes a deck that reaches it through
# both the context and the deck file once.
deck_stamp="$(date +%s%N)-$$"
deck_json=$(jq -cn \
  --arg source "$start_source" --arg repo "$repo_name" --arg vault "$CORTEX_DIR" \
  --arg stamp "$deck_stamp" \
  --argjson status "$deck_status" --argjson batons "$deck_batons" \
  '{v: 1, source: $source, stamp: $stamp, repo: $repo, status: $status,
    actions: [
      {label: "載入記憶", prompt: "載入此 repo 的記憶筆記（執行 cortex-vec search --repo \($repo)）"},
      {label: "最近紀錄", prompt: "查看最近的 session 紀錄（列出 \($vault)/Raw/ 中最近幾筆）"},
      {label: "處理待辦", prompt: "處理待辦事項（提煉未處理的紀錄）。找未提煉的紀錄用 cortex-vec distill-queue --root \($vault)/Raw；不要用 grep 找 marker：meta-session 內文會引用該字串騙過 grep。"}
    ],
    batons: $batons,
    handoff: "context 用量接近上限，用 cortex-takeoff skill 建立交接。"}' \
  | sed 's/</\\u003c/g; s/>/\\u003e/g')

# The deck file: where an organization seats its policy plugin, the person's
# plugins never see the context row, so the mod polls this file instead. One
# per session id, renamed into place so a poll never reads half a deck; files
# a crashed session left behind go after a day. Best effort: a failure here
# leaves the text menu, which the model still shows.
# shellcheck source=lib/deck-file.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/deck-file.sh"
if deck_file=$(cortex_deck_file "$session_id"); then
  deck_dir=$(dirname "$deck_file")
  if mkdir -p "$deck_dir" 2>/dev/null; then
    find "$deck_dir" -maxdepth 1 -name '*.json' -mtime +0 -delete 2>/dev/null || true
    deck_tmp="$deck_file.$$.tmp"
    { printf '%s\n' "$deck_json" > "$deck_tmp" && mv -f "$deck_tmp" "$deck_file"; } 2>/dev/null \
      || rm -f "$deck_tmp"
  fi
fi

# --- Build interactive menu prompt ---
read -r -d '' context <<'PROMPT_TEMPLATE' || true
[Cortexes] 你目前在 __REPO__ repo。Cortexes vault 位於 __VAULT__（非 CWD），所有 vault 操作請使用此路徑。

Vault 目前涵蓋的主題（僅為主題名稱清單，不是內容；用來判斷請求是否命中訊號 3）：
  - Notes/: __NOTES_TOPICS__
  - Projects/: __PROJECTS_TOPICS__

何時查 vault（由 using-cortex skill 定義；只有以下四個訊號之一成立時才查）：
1. 使用者明確要求：「查 cortex」「之前有記過嗎」「check my notes」。
2. 使用者指涉先前的工作：「之前那個」「上次的」「我們討論過」「continue where we left off」。
3. 使用者的請求命中上面**實際列出**的主題 — 以這份清單為準，不要用猜的。
4. 使用者要求接續、交接或延續先前 session 的工作。

四個訊號都不成立就直接回答，也不要提到 vault。問題困難、技術性強、開放式，或屬於 ongoing project／內部工具，**都不是**訊號。詳細規則見 using-cortex skill。

<!-- cortex:menu -->
__DECK__
在你第一次回覆使用者時，呈現以下格式：

__UNPUSHED_STATUS__列出選項：
1. 載入此 repo 的記憶筆記（執行 cortex-vec search --repo __REPO__）
2. 查看最近的 session 紀錄（列出 __VAULT__/Raw/ 中最近幾筆）
3. 處理待辦事項（提煉未處理的紀錄）
4. 直接開始工作__TAKEOFF_OPTION__

規則：
- 選項 3 被選中時，才去掃描 __VAULT__/Raw/ 找未提煉的紀錄（cortex-vec distill-queue --root __VAULT__/Raw）。不要用 grep 找 marker：meta-session 內文會引用該字串騙過 grep。
- 不要在使用者選擇前預先掃描 Raw/
- 使用者可以回覆編號或直接說需求
- 保持簡短，不要過度解釋每個選項
- 使用者選 4「直接開始工作」或略過此選單時：本 session 後續**不再**主動查 vault，訊號 2-4 一律不觸發；只有使用者之後明確要求（訊號 1）才查__TAKEOFF_RULE__
<!-- /cortex:menu -->
PROMPT_TEMPLATE

# Substitute placeholders
context="${context//__REPO__/$repo_name}"
context="${context//__VAULT__/$CORTEX_DIR}"
context="${context//__UNPUSHED_STATUS__/$unpushed_status}"
context="${context//__NOTES_TOPICS__/$notes_topics}"
context="${context//__PROJECTS_TOPICS__/$projects_topics}"
context="${context//__TAKEOFF_OPTION__/$takeoff_option}"
context="${context//__TAKEOFF_RULE__/$takeoff_rule}"
# The deck goes in by splitting, not ${//}: bash 5.2's patsub_replacement
# reads `&` in a replacement as the matched text.
context="${context%%__DECK__*}<!-- cortex:deck ${deck_json} -->${context#*__DECK__}"

# Use jq for safe JSON encoding
jq -n --arg ctx "$context" \
  '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'

exit 0
