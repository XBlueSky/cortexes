#!/bin/bash
# Shared deck-file path for cortex hooks/scripts.
#
# session-start-inject.sh writes each session's deck here and
# session-end-record.sh removes it; the cortex mod (hooks/deck.tsx, deckPath in
# hooks/deck-core.ts) reads the same path where an organization's policy plugin
# keeps session.append from the person's plugins. All three MUST agree on it.

# cortex_deck_file <session_id>
#   Prints $CLAUDE_PLUGIN_ROOT/.deck/<session_id>.json. Prints nothing and
#   returns 1 when CLAUDE_PLUGIN_ROOT is unset or the id is not a plain file
#   name (letters, digits, `_`, `-`), so no id can leave the folder.
cortex_deck_file() {
  local id="$1"
  [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] || return 1
  [[ "$id" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
  printf '%s/.deck/%s.json\n' "$CLAUDE_PLUGIN_ROOT" "$id"
}
