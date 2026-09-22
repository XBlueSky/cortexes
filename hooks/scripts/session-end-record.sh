#!/bin/bash
set -euo pipefail

# SessionEnd hook — filters transcript into Raw/ with context-preservation priority.
# Pipeline: regex cleanup → rtk-style per-command filter → LLM classifier for
# >12KB residue (fail-open). See hooks/scripts/filter-transcript.py for details.
#
# Recursion guard: classifier invokes `claude -p` which triggers its own
# SessionEnd. The CORTEX_SESSION_RECORDING env var short-circuits nested calls.
# nohup+disown: Claude Code kills SessionEnd hooks early, so heavy work is
# detached to survive parent exit.

if [[ -n "${CORTEX_SESSION_RECORDING:-}" ]]; then
  exit 0
fi
export CORTEX_SESSION_RECORDING=1

# Opt-out: a launcher can set CORTEX_SKIP_RECORD=1 to suppress recording this
# session into Raw/. Used by cc-loadout probe sessions (which exist only to
# tick the 5h usage window and carry no distill-worthy content) so they do not
# litter the vault with empty Raws. Checked before any file/queue work.
if [[ -n "${CORTEX_SKIP_RECORD:-}" ]]; then
  exit 0
fi

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // ""')
cwd=$(echo "$input" | jq -r '.cwd // ""')

if [[ -z "$transcript_path" || ! -f "$transcript_path" ]]; then
  exit 0
fi

# Headless guard: `claude -p` stamps entrypoint "sdk-cli" into its transcript,
# interactive sessions stamp "cli". Programmatic invocations are eval harnesses,
# probes and helper calls whose transcripts are not work sessions, and the
# size gate below does not catch them: a one-turn probe body is a few hundred
# bytes, but the jsonl carries the whole system prompt and clears 4 KB easily.
# This is a net for launchers that never learned about CORTEX_SKIP_RECORD --
# one such batch driver filed 122 junk Raws before this guard existed.
# CORTEX_FORCE_RECORD=1 overrides it, for headless runs that ARE real work --
# cc-loadout sets it on scheduled tasks, which are meant to stay recorded.
# Absent/unreadable entrypoint falls through to recording (fail-open).
if [[ -z "${CORTEX_FORCE_RECORD:-}" ]]; then
  entrypoint=$(head -50 "$transcript_path" \
    | grep -o -m1 '"entrypoint":"[^"]*"' | cut -d'"' -f4 || true)
  if [[ "$entrypoint" == "sdk-cli" ]]; then
    exit 0
  fi
fi

file_size=$(stat -c%s "$transcript_path" 2>/dev/null || stat -f%z "$transcript_path" 2>/dev/null || echo 0)
if [[ "$file_size" -lt 4096 ]]; then
  exit 0
fi

CORTEX_CONFIG="$HOME/.cortex/config.json"
if [[ ! -f "$CORTEX_CONFIG" ]]; then
  exit 0
fi

vault_path=$(jq -r '.vault_path // ""' "$CORTEX_CONFIG" 2>/dev/null)
if [[ -z "$vault_path" || ! -d "$vault_path" ]]; then
  exit 0
fi

repo_name="unknown"
if [[ -n "$cwd" ]] && git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  repo_name=$(git -C "$cwd" remote get-url origin 2>/dev/null \
    | sed 's|.*/||;s|\.git$||' || basename "$cwd")
fi
repo_name="${repo_name:-unknown}"

date_dir=$(date +%Y/%m/%d)
timestamp=$(date +%H%M%S)
filename="${timestamp}_session_${repo_name}.md"
target_dir="${vault_path}/Raw/${date_dir}"
target_file="${target_dir}/${filename}"
mkdir -p "$target_dir"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER="${SCRIPT_DIR}/filter-transcript.py"
META="${SCRIPT_DIR}/meta_session.py"

nohup bash -c '
  # Everything below is the single-quoted body of `bash -c '...'`, so it must
  # stay free of apostrophes — one in a comment closes the quote and breaks the
  # whole detached writer.
  CORTEX_SESSION_RECORDING=1
  export CORTEX_SESSION_RECORDING

  target_file="$1"
  transcript_path="$2"
  repo_name="$3"
  vault_path="$4"
  CORTEX_CONFIG="$5"
  FILTER="$6"
  META="$7"

  # The filter used to run as `2>/dev/null || echo "(filter failed)"`: the
  # traceback naming the offending filter and line was discarded, and the
  # 100-byte stub left behind did not even record which transcript produced
  # it. A 2026-09-02 payload shape change crashed one filter and destroyed 21
  # session records that way before anyone noticed. Now stderr is captured,
  # redacted, and appended to filter-failures.log next to push-failures.log.
  # (This block lives inside a single-quoted bash -c string: no apostrophes.)
  filter_err="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-filter-err.$$")"
  filter_rc=0

  # The Raw is assembled in a sibling temp file and renamed into place, so the
  # target path only ever holds a COMPLETE record. Writing the filter straight
  # into "$target_file" meant a SIGTERM (see the timeout below) landing mid
  # flush left frontmatter + a truncated body + "(filter failed)" at the real
  # path -- a file that is neither under the 300-byte ceiling nor has a body
  # that strips to exactly "(filter failed)", so the structural discriminator
  # in scripts/backfill-failed-raws.py can never find it. A silently corrupted
  # record with no marker is worse than a stub that says what happened.
  # The temp file sits in the target directory so the mv is a rename and
  # therefore atomic, and it is created by redirection rather than mktemp so
  # the Raw keeps the umask-derived mode it has always been written with.
  tmp_raw="${target_file}.partial.$$"
  cleanup_tmp() {
    rm -f "$filter_err" "$tmp_raw" 2>/dev/null || true
  }
  on_signal() {
    # Killed before the rename: leave nothing behind rather than an orphan
    # temp file in the vault. The target path is still untouched, which is the
    # property that matters -- there is no half-written record to find.
    cleanup_tmp
    exit 143
  }
  trap cleanup_tmp EXIT
  trap on_signal HUP INT TERM

  # A HANG is worse than a crash: a filter that never returns leaves no record
  # at all. Bound it, but only when timeout(1) is actually available -- a
  # missing binary here would fail every session.
  #
  # The bound is a backstop for a wedged process, NOT a budget for slow work:
  # everything it kills is a destroyed session record, so it has to sit far
  # above the worst legitimate run. The slowest real filter measured (a 128 KB
  # single-line blob through the redaction pass, before that pass was made
  # linear) spent ~1131s and still produced a COMPLETE Raw; 3600s keeps ~3x
  # headroom over that while still turning an infinite loop into one logged
  # failure instead of a process that outlives the session forever.
  #
  # CORTEX_FILTER_TIMEOUT overrides it, but only as a plain count of seconds.
  # timeout(1) exits 125 on a value it cannot parse -- a human-friendly
  # "10 minutes" stubs every session in every repo, and does it BEFORE python
  # runs, so the Raw never even sees the filter. Anything non-numeric or out
  # of range (including 0, which would mean no bound at all) falls back to the
  # default rather than taking the whole pipeline down.
  filter_timeout="${CORTEX_FILTER_TIMEOUT:-}"
  case "$filter_timeout" in
    ""|*[!0-9]*) filter_timeout="" ;;
  esac
  if [[ -n "$filter_timeout" ]]; then
    filter_timeout=$((10#$filter_timeout))
    if [[ "$filter_timeout" -lt 1 || "$filter_timeout" -gt 86400 ]]; then
      filter_timeout=""
    fi
  fi
  filter_timeout="${filter_timeout:-3600}"

  filter_cmd=(python3 "$FILTER" "$transcript_path")
  if command -v timeout >/dev/null 2>&1; then
    filter_cmd=(timeout "$filter_timeout" "${filter_cmd[@]}")
  fi

  raw_date="$(date +%Y-%m-%d)"
  raw_time="$(date +%H:%M:%S)"
  write_frontmatter() {
    cat <<FRONTMATTER
---
date: ${raw_date}
time: ${raw_time}
type: session
repo: ${repo_name}
transcript: ${transcript_path}
tags: [session]
---

FRONTMATTER
  }

  # filter_rc is the status of the filter itself (or the 124 timeout(1) reports
  # when it kills the filter) -- the filter is run on its own, never as a
  # pipeline stage, so no other command can mask it.
  write_frontmatter > "$tmp_raw"
  "${filter_cmd[@]}" >> "$tmp_raw" 2>"$filter_err" || filter_rc=$?

  if [[ "$filter_rc" -ne 0 ]]; then
    # Discard whatever partial body the filter managed to flush: the stub has
    # to be the WHOLE body for the backfill to recognise the record.
    { write_frontmatter; echo "(filter failed)"; } > "$tmp_raw"
  fi
  mv -f "$tmp_raw" "$target_file" 2>/dev/null \
    || cat "$tmp_raw" > "$target_file" 2>/dev/null \
    || true

  # The detail goes to the log, never into the Raw body. Anything written to
  # the Raw is committed and pushed, and an exception message can quote the
  # payload that broke the filter -- which is exactly where a credential would
  # be. But the log is not a safe sink for raw stderr either: "not committed"
  # is a weaker control than "not recorded", and a token that reaches disk in
  # cleartext has already leaked. So the captured stderr goes through the SAME
  # redact_secrets() the Raw body gets, and the log is created 0600.
  # Fail-open in the safe direction: if the redaction pass cannot run (no
  # python3, an unimportable filter, a wedged regex) the stderr is DROPPED for
  # a fixed placeholder. Losing a traceback is recoverable; logging a
  # credential is not.
  if [[ "$filter_rc" -ne 0 ]]; then
    filter_log="$(dirname "$CORTEX_CONFIG")/filter-failures.log"
    redact_py=$(cat <<"PYEOF"
import importlib.util
import os
import sys

MAX_INPUT = 1 << 20
MAX_OUTPUT = 8192

filter_path, err_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(os.path.abspath(filter_path)))
spec = importlib.util.spec_from_file_location("cortex_filter_transcript", filter_path)
if spec is None or spec.loader is None:
    raise SystemExit(1)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
redact = module.redact_secrets

with open(err_path, "rb") as handle:
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    # Redact BEFORE truncating: cutting first can bisect a credential and
    # leave a fragment no rule matches. The 1 MiB read bound keeps a runaway
    # stderr from being redacted in full.
    handle.seek(max(0, size - MAX_INPUT))
    text, _ = redact(handle.read(MAX_INPUT).decode("utf-8", "replace"))
sys.stdout.write(text[-MAX_OUTPUT:])
PYEOF
)
    redact_cmd=(python3 -c "$redact_py" "$FILTER" "$filter_err")
    if command -v timeout >/dev/null 2>&1; then
      redact_cmd=(timeout 60 "${redact_cmd[@]}")
    fi
    if ! filter_err_text="$("${redact_cmd[@]}" 2>/dev/null)"; then
      filter_err_text="(stderr dropped: redaction unavailable)"
    fi
    ( umask 077; : >> "$filter_log" ) 2>/dev/null || true
    chmod 600 "$filter_log" 2>/dev/null || true
    {
      printf "[%s] repo=%s vault=%s\n" "$(date +%Y-%m-%dT%H:%M:%S)" "$repo_name" "$vault_path"
      printf "transcript=%s\n" "$transcript_path"
      printf "raw=%s\n" "$target_file"
      printf "exit=%s\n" "$filter_rc"
      printf "%s\n" "$filter_err_text"
      printf "\n"
    } >> "$filter_log" 2>/dev/null || true
  fi
  rm -f "$filter_err" 2>/dev/null || true

  # Cortex maintenance-pipeline sessions (distill/broadcast/genesis) only
  # process the vault; recording them would re-feed Raw/ into its own distill
  # queue, so the queue could never reach empty. Keep the record as an audit
  # trail but pre-stamp a distilled marker so the grep -rL "<!-- distilled:"
  # queue scan never picks it up again. Fail-open: any error → no marker.
  # Guarded on the Raw existing so a failed rename cannot conjure a
  # marker-only file at the target path.
  if [[ -s "$target_file" ]] && python3 "$META" "$transcript_path" >/dev/null 2>&1; then
    printf "\n<!-- distilled: %s → (skip: meta-session) -->\n" "$(date +%Y-%m-%d)" >> "$target_file"
  fi

  # SessionEnd fires more than once per conversation (/clear, exit + --resume)
  # and transcript_path is ONE growing jsonl, so every firing re-filters the
  # whole thing: the earlier Raws are strict prefixes of the one just written.
  # Left alone each would sit in the distill queue as its own entry, spending
  # the distill budget several times over on the same conversation. Candidates
  # come only from the undistilled queue, so a Raw that already carries a
  # distilled marker (referenced by a Note via source:) can never be touched.
  # Fail-open: on any error the duplicate simply stays. Prefer the module form —
  # this hook already requires a python3 that can import the pipeline; the
  # console script also needs PATH.
  reclaimed=0
  cvec=""
  if python3 -c "import cortex_vec" 2>/dev/null; then
    cvec="python3 -m cortex_vec.cli"
  elif command -v cortex-vec >/dev/null 2>&1; then
    cvec="cortex-vec"
  fi
  if [[ -n "$cvec" ]]; then
    # reclaim keeps stdout as the machine-readable list of reclaimed paths (it
    # is counted just below and named in the commit message), so everything a
    # human needs to SEE goes to stderr -- in particular a cross-repo prefix
    # pair, which reclaim refuses rather than deleting because the two Raws
    # carry different `repo:` labels and each repo keeps its own record.
    # Discarding that stderr would make the refusal invisible and defeat the
    # guard, so it lands in the same log as a filter failure. It carries vault
    # paths and repo names only -- no transcript payload -- so unlike the
    # stderr of the filter it needs no redaction pass.
    reclaim_err="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-reclaim-err.$$")"
    reclaimed_out=$($cvec reclaim-superseded --root "${vault_path}/Raw" \
      --keep "$target_file" --apply --vault "$vault_path" 2>"$reclaim_err" || true)
    reclaimed=$(printf "%s" "$reclaimed_out" | grep -c . || true)
    if [[ -s "$reclaim_err" ]]; then
      reclaim_log="$(dirname "$CORTEX_CONFIG")/filter-failures.log"
      ( umask 077; : >> "$reclaim_log" ) 2>/dev/null || true
      chmod 600 "$reclaim_log" 2>/dev/null || true
      {
        printf "[%s] reclaim repo=%s vault=%s\n" \
          "$(date +%Y-%m-%dT%H:%M:%S)" "$repo_name" "$vault_path"
        tail -c 8192 "$reclaim_err"
        printf "\n"
      } >> "$reclaim_log" 2>/dev/null || true
    fi
    rm -f "$reclaim_err" 2>/dev/null || true
  fi

  auto_commit=$(jq -r ".git.auto_commit // false" "$CORTEX_CONFIG" 2>/dev/null)
  auto_push=$(jq -r ".git.auto_push // false" "$CORTEX_CONFIG" 2>/dev/null)
  if [[ "$auto_commit" == "true" ]]; then
    # The reclaim above staged its deletions, so this commit carries them too —
    # git history is the audit trail for a hook that writes no log.
    commit_msg="raw: session ${repo_name} $(date +%Y-%m-%d)"
    if [[ "${reclaimed:-0}" -gt 0 ]]; then
      commit_msg="${commit_msg} (reclaimed ${reclaimed} superseded)"
    fi
    git -C "$vault_path" add "$target_file" 2>/dev/null || true
    git -C "$vault_path" commit -m "$commit_msg" 2>/dev/null || true
    if [[ "$auto_push" == "true" ]]; then
      # A rejected push (pre-receive hook, auth, network) used to vanish into
      # /dev/null and every later push failed the same way until someone
      # noticed. Keep the hook silent on success, but leave the message from
      # the remote next to the config so the next SessionStart can point at it.
      # (This block lives inside a single-quoted bash -c string: no apostrophes.)
      if ! push_out=$(git -C "$vault_path" push 2>&1); then
        push_log="$(dirname "$CORTEX_CONFIG")/push-failures.log"
        {
          printf "[%s] repo=%s vault=%s\n" "$(date +%Y-%m-%dT%H:%M:%S)" "$repo_name" "$vault_path"
          printf "%s\n\n" "$push_out"
        } >> "$push_log" 2>/dev/null || true
      fi
    fi
  fi
' _ "$target_file" "$transcript_path" "$repo_name" "$vault_path" "$CORTEX_CONFIG" "$FILTER" "$META" >/dev/null 2>&1 &
disown

exit 0
