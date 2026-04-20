# Phase 2 Broadcast Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `cortex-broadcast` skill + `/cortex:broadcast` command that runs a conversational update pass across 0–5 related existing pages per Raw, with inline trigger from distill (`y/n/later`) and marker/log extensions that absorb Phase 1's `pending-merge` queue.

**Architecture:** Phase 2 is additive to Phase 1 — no Phase 1 behavior changes. Three file additions (new skill, new command) plus one surgical extension to `cortex-distill/SKILL.md` (Step 9). The broadcast skill is markdown instructions for Claude interpreting per-page conversational flow; the vault writes are per-page git commits. The `pending-merge` marker from Phase 1 becomes a pre-check hint in the broadcast menu — no separate migration.

**Tech Stack:** Markdown (Claude skill/command format), `~/.cortex/config.json` (JSON), `cortex-vec search` CLI for candidate page selection, per-page git commits in vault repo, `cat >>` / Edit tool for log append (same pattern as Phase 1).

**Related spec:** `docs/superpowers/specs/2026-04-17-phase2-broadcast-ingest-design.md`

---

## File Structure

### Added (plugin repo — `/synosrc/misc/cortex/`)

| File | Purpose |
|------|---------|
| `skills/cortex-broadcast/SKILL.md` | Full broadcast flow: queue resolution, vec search, menu, per-page conversation, marker finalization, log append. |
| `commands/broadcast.md` | Delegates to `cortex-broadcast` skill. Handles no-arg / `--list` / `<raw-path>` variants. |

### Modified (plugin repo)

| File | Purpose |
|------|---------|
| `skills/cortex-distill/SKILL.md` | Add Step 9 "Ask: broadcast now?" at end of per-Raw flow. Handles `y`/`n`/`l` answers per spec Section 2. |

### Modified (user machine, not a repo commit)

| File | Purpose |
|------|---------|
| `~/.cortex/config.json` | Add top-level `broadcast` key with `target_top_n: 5` and `target_min_score: 0.40`. |

### No-change guarantee

- `skills/cortex-evolve/SKILL.md`, `skills/cortex-query/SKILL.md`, `skills/cortex-weekly/SKILL.md` — untouched
- `commands/distill.md`, `commands/evolve.md`, `commands/genesis.md` — untouched
- `cortex-vec` Python package — untouched
- Vault content (`Notes/`, `Projects/`, `_index.md`) — untouched by the plan; only touched by end-to-end acceptance tests in Task 7

---

## Task Ordering

```
Task 1 (config) ──┐
                  │
                  ├─> Task 2 (cortex-broadcast SKILL.md)  ──┬──> Task 5 (accept: broadcast existing pending-merge)
                  │                                         │
                  ├─> Task 3 (commands/broadcast.md)  ──────┤
                  │                                         │
                  └─> Task 4 (distill SKILL.md Step 9) ─────┴──> Task 6 (accept: distill→later→broadcast)
                                                            │
                                                            └──> Task 7 (accept: distill→n→no-broadcast marker)
```

Tasks 1–4 are all independent of each other (different files) and can be done in any order. Tasks 5–7 require all of 1–4 complete.

---

## Task 1: Add `broadcast` config section

**Files:**
- Modify: `~/.cortex/config.json` (user-machine state, not a repo commit)

- [ ] **Step 1: Show current config**

Run: `cat ~/.cortex/config.json`

Verify top-level keys include `vault_path`, `author`, `author_email`, `git`, `weekly`, `distill`. If `broadcast` already exists, stop and report — Phase 2 may be partially applied.

- [ ] **Step 2: Append `broadcast` section**

Use the Edit tool on `~/.cortex/config.json`. Insert a new top-level `broadcast` key after the `distill` block. Final file content:

```json
{
  "vault_path": "/synosrc/cortex",
  "author": "tonyhu",
  "author_email": "tonyhu@synology.com",
  "git": {
    "auto_commit": true,
    "auto_push": true
  },
  "weekly": {
    "gitlab_username": "tonyhu",
    "categories": ["fix", "feat", "misc"],
    "cutoff": {
      "day": "friday",
      "hour": 11
    },
    "experimental_repos": [
      "wit/morpheus"
    ]
  },
  "distill": {
    "dedup_threshold_new": 0.45,
    "dedup_threshold_pending": 0.60
  },
  "broadcast": {
    "target_top_n": 5,
    "target_min_score": 0.40
  }
}
```

- [ ] **Step 3: Verify**

Run: `jq '.broadcast' ~/.cortex/config.json`

Expected output:
```json
{
  "target_top_n": 5,
  "target_min_score": 0.4
}
```

No commit — this is user-machine state.

---

## Task 2: Create `skills/cortex-broadcast/SKILL.md`

**Files:**
- Create: `/synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md`

This is the largest task. The skill encodes Sections 2, 3, 4, 5, 6, 7, 9 of the spec as executable Claude instructions.

- [ ] **Step 1: Create directory**

Run: `mkdir -p /synosrc/misc/cortex/skills/cortex-broadcast`

Verify: `test -d /synosrc/misc/cortex/skills/cortex-broadcast && echo "OK"`

- [ ] **Step 2: Write SKILL.md**

Use the Write tool on `/synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md` with this exact content:

````markdown
---
name: cortex-broadcast
description: >
  llm-wiki style broadcast ingest — conversational update of related existing
  pages when a Raw has been distilled. Use when the user says "broadcast",
  "跑 broadcast", "compound this into the vault", "merge pending-merge",
  "process broadcast queue", or when cortex-distill invokes broadcast inline
  after a per-Raw prompt (y/later answer).
---

# Cortex Broadcast — Compounding Ingest

Propagate insights from a distilled Raw into related existing Notes/Projects
pages through conversational per-page edits.

## Resolve Vault Path and Config

Read `~/.cortex/config.json`:

```bash
jq -r '.vault_path' ~/.cortex/config.json
jq -r '.broadcast.target_top_n // 5' ~/.cortex/config.json
jq -r '.broadcast.target_min_score // 0.40' ~/.cortex/config.json
```

If the config file doesn't exist, tell the user to run `/cortex:genesis` first.

## Step 1: Resolve Arguments

The command supports three invocations:

| Form | Action |
|------|--------|
| `/cortex:broadcast` (no args) | Pop the first (oldest) Raw from the eligible queue |
| `/cortex:broadcast <raw-path>` | Use the specified Raw (relative or absolute path) |
| `/cortex:broadcast --list` | Print the eligible queue and exit |

## Step 2: Build Eligible Queue

A Raw is eligible iff its marker meets **all** of:

- Contains `<!-- distilled: YYYY-MM-DD → ... -->` (Phase 1 processed).
- Outcome is `new` or `pending-merge` (the marker content after `→` is
  either a path like `Notes/X.md` / `Projects/Y/Z.md`, **or** starts with
  `pending-merge:`; anything else — `(skip: routine)`, `(no insight)` —
  is ineligible).
- Does not already contain any of: `| broadcast:`, `| merged:`,
  `| no-broadcast:`.

Build the list via:

```bash
grep -rL '| broadcast:\|| merged:\|| no-broadcast:' <vault>/Raw/ --include='*.md' \
  | xargs grep -l '<!-- distilled:' \
  | xargs grep -LE '(skip: routine|no insight)'
```

Sort by Raw filename (which starts with timestamp) for FIFO ordering.

## Step 3: Handle `--list`

If the user invoked `--list`, print each queued Raw with:

- Relative path from vault
- Outcome (extract from marker: `new` if target is a path; `pending-merge`
  if marker contains `pending-merge:`)
- Original target (for `pending-merge` Raws; `—` for `new`)

Format:

```
Eligible queue (N Raws):

  1. Raw/2026/04/17/141013_session_webapi-Notification.md
     outcome: pending-merge → Projects/libsynosysnotify/synooauth flow chart.md (0.48)

  2. Raw/2026/04/17/163941_session_libsynosdk.md
     outcome: new → Projects/libsynosdk/build-flag-semantics.md

Run /cortex:broadcast to process the first, or /cortex:broadcast <path> for a specific one.
```

Exit after listing.

## Step 4: Select Raw and Read Content

If no args: pick the first entry from the queue.
If `<raw-path>` arg: verify it's eligible; abort with a clear error if not.

Read:

1. The Raw's full content (frontmatter + all sections).
2. The Raw's distilled marker; parse the outcome and (for pending-merge)
   the original target path and score.

## Step 5: Find Candidate Pages

Pick the **longest Discovery or Decision bullet** from the Raw as the vec
search query (same heuristic as cortex-distill Stage 2).

Run:

```bash
cortex-vec search "<bullet text>" --n <target_top_n>
```

If the Raw's frontmatter has `repo:`, also pass `--repo <name>` when the
query topic looks repo-specific. Omit otherwise.

Filter results to those with `score >= target_min_score`.

### Fallback if `cortex-vec` is unavailable

If the command errors (not found, ECONNREFUSED, etc.):

1. Read `<vault>/_index.md`.
2. Use your own semantic judgment to pick up to `target_top_n` candidate
   pages that look related to the Raw.
3. Note `candidates_source: llm-fallback` for the log entry later.

## Step 6: Pre-select Pending-Merge Target

If the Raw's outcome is `pending-merge`:

- Extract the target path from the marker.
- Find that path in the candidate list.
  - If present: mark it as pre-selected `[x]`.
  - If absent (score now below threshold, or file renamed): **still
    include it** as a pre-selected entry at the top, with a note
    `(below current threshold)`. Original distill intent overrides current
    threshold.

All other candidates default to unchecked `[ ]`.

## Step 7: Present Menu and Confirm

Display:

```
Broadcast target candidates for <raw-filename>:

  [x] 1. <path> (<score>)      ← pending-merge target   (if applicable)
  [ ] 2. <path> (<score>)
  [ ] 3. <path> (<score>)
  ...

Toggle: number (1–N) to flip, 'a' all, 'n' none, then Enter to confirm.
Cancel: type 'cancel' to abort without marking the Raw.
```

Read the user's toggles until they confirm. Build the final selected list.
If the list is empty after confirmation, jump directly to Step 9 with
`pages_touched = []` — this will write a `broadcast: <date> → (no changes)`
marker.

## Step 8: Per-Page Conversational Edit Loop

For each selected page, in menu order:

1. Read the target page's full content.
2. Announce the page to the user:
   ```
   === [1/3] Editing Notes/DSM/Web benchmark.md ===
   ```
3. Identify candidate change types from the Raw vs the page:
   - Prose rewrite of a section that overlaps topically
   - Wikilink insertion (add `[[raw-filename]]` or `[[new-page-from-raw]]`)
   - Contradiction flag (see Contradiction Handling below)
   - Summary / intro revision if the Raw substantially changes the page's
     framing
4. Propose change #1. Be specific: show the exact before/after for the
   affected section, not a prose description.
5. Read the user's response:
   - `yes` / `y` → apply to working copy
   - `no` / `n` → discard this proposal
   - Free-form text (e.g. "shorter", "use the Raw's terminology", "insert
     under the Fix section instead") → revise the proposal, re-show, re-ask
6. Propose change #2. Iterate.
7. Stop condition — whichever comes first:
   - You (the LLM) have no further useful changes to propose; announce
     "No more proposals for this page." and await user confirmation.
   - User types `done` / `next` / `skip` to end this page.
   - User types `abort` / `cancel` to end the entire session (see Abort).
8. Apply the accumulated approved changes to the page file using the Edit
   tool (never overwrite wholesale; use targeted Edits).
9. Refresh embedding:
   ```bash
   cortex-vec upsert <relative-page-path>
   ```
10. Commit this page's edit in the vault repo:
    ```bash
    cd <vault>
    git add <relative-page-path>
    git commit -m "broadcast: update <page-title> from <raw-filename>"
    ```
    `<page-title>` = the `title:` from the page's frontmatter, or the H1
    heading if no frontmatter.

### Contradiction Handling

If the Raw contains a claim that directly contradicts a claim in the page:

1. Locate the conflicting claim in the page.
2. Propose inline flag at that location:
   ```
   ⚠️ Contradicts [[<raw-filename>]]: <one-line statement of the conflict>
   ```
3. This proposal enters the normal flow (Step 8.5):
   - `yes` → accept flag
   - `no` → skip
   - Free-form (e.g., "the new info is correct, delete the old claim")
     → rewrite the old claim with new info; no `⚠️` flag
4. Each accepted flag increments a counter for the log entry.

### Abort Mid-Page

If the user types `abort` / `cancel` during page conversation:

- Do **not** apply any uncommitted in-memory changes from this page.
- Already-committed prior pages from this session stand.
- Do **not** update the Raw marker or append log entry.
- Exit the skill cleanly with a message:
  ```
  Aborted. <N> pages committed, Raw marker unchanged.
  Re-run /cortex:broadcast <raw-path> to resume.
  ```

## Step 9: Finalize Raw Marker and Log

After all selected pages are committed (or the selected list was empty):

### 9.1 Update Raw marker

Read the current marker line. Determine the terminal segment to append
based on outcome and result:

| Case | New segment |
|------|-------------|
| Outcome `new`, ≥1 page committed | `\| broadcast: <today> → [[page1]], [[page2]]` |
| Outcome `new`, 0 pages (menu empty or all unchecked) | `\| broadcast: <today> → (no changes)` |
| Outcome `new`, no candidates returned | `\| broadcast: <today> → (no candidates)` |
| Outcome `pending-merge`, ≥1 page committed | replace `pending-merge: ... (score)` with `merged: <today> → [[page1]], [[page2]]`. Keep the original `→ pending-merge:` prefix *before* replacement so the line now reads `distilled: ... → pending-merge: ... (score) \| merged: ...` |
| Outcome `pending-merge`, 0 pages committed | append `\| broadcast: <today> → (no changes)` after the existing `pending-merge:` segment |

Date format: `YYYY-MM-DD`.

Use the Edit tool to replace the marker line.

### 9.2 Append log entry

Compose the entry with placeholders substituted. Append to `<vault>/log.md`
using the Edit tool (preferred) or:

```bash
printf '\n%s\n' "$ENTRY" >> "<vault>/log.md"
```

Where `$ENTRY` is:

```markdown
## [YYYY-MM-DD HH:MM] broadcast | <raw-filename>
- source_outcome: <new|pending-merge>
- pages_touched: [[page1]], [[page2]]
- contradictions_flagged: N
- repo: <repo or (none)>
```

Field rules:

- `source_outcome`: `new` or `pending-merge` (derived from pre-broadcast
  marker).
- `pages_touched`: wikilink-formatted list of actually committed pages.
  If empty: write `pages_touched: (none)`.
- `contradictions_flagged`: integer count of accepted `⚠️` flags. Omit
  the line if zero.
- `repo`: from Raw frontmatter `repo:` or `(none)`.
- If Step 5 fallback ran (cortex-vec unavailable), add
  `candidates_source: llm-fallback` as a final line.

### 9.3 Commit Raw marker + log

Single commit in the vault repo:

```bash
cd <vault>
git add <raw-relative-path> log.md
git commit -m "broadcast: finalize <raw-filename>"
```

## Step 10: Offer Next Raw

If:

- Skill was invoked by `/cortex:broadcast` without args, AND
- The eligible queue still has entries after this run,

then ask the user:

```
Process next eligible Raw (<count> remaining)? (y/n)
```

- `y` → return to Step 4 with next queue entry.
- `n` → exit with summary: "Broadcast session complete. <M> Raws processed."

If invoked via distill inline (spec Section 2 `y` answer), do not ask.
Return cleanly to distill flow.
````

- [ ] **Step 3: Verify structure**

Run: `grep "^## Step" /synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md`

Expected 10 `## Step` lines, in order:
```
## Step 1: Resolve Arguments
## Step 2: Build Eligible Queue
## Step 3: Handle `--list`
## Step 4: Select Raw and Read Content
## Step 5: Find Candidate Pages
## Step 6: Pre-select Pending-Merge Target
## Step 7: Present Menu and Confirm
## Step 8: Per-Page Conversational Edit Loop
## Step 9: Finalize Raw Marker and Log
## Step 10: Offer Next Raw
```

Run: `wc -l /synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md`

Expected: between 200 and 280 lines.

Run: `grep -c "<<'EOF'" /synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md`

Expected: `0` (no quoted heredoc — same lesson from Phase 1 Task 4 fix).

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-broadcast/SKILL.md
git commit -m "feat(broadcast): add cortex-broadcast skill

Implements Phase 2 conversational broadcast ingest: per-Raw menu of
candidate pages (top-N by vec search, ≥ target_min_score), per-page
conversational edit loop with contradiction flagging, per-page git
commits, then Raw marker + log finalization.

Skill supports:
- /cortex:broadcast (FIFO from eligible queue)
- /cortex:broadcast <raw-path>
- /cortex:broadcast --list

Marker transitions:
- new → broadcast: <date> → [[pages]]
- pending-merge → pending-merge: ... | merged: <date> → [[pages]]
- no changes / no candidates / abort variants per spec

Ref: docs/superpowers/specs/2026-04-17-phase2-broadcast-ingest-design.md
"
```

---

## Task 3: Create `commands/broadcast.md`

**Files:**
- Create: `/synosrc/misc/cortex/commands/broadcast.md`

- [ ] **Step 1: Write the command file**

Use the Write tool on `/synosrc/misc/cortex/commands/broadcast.md` with this exact content:

```markdown
---
name: broadcast
description: Run broadcast on a distilled Raw — update related existing pages conversationally
argument-hint: "[raw-path | --list]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
skills:
  - cortex-broadcast
---

Use the cortex-broadcast skill to process broadcast-eligible Raws.

Argument handling:

- No argument → process the oldest eligible Raw (FIFO from the queue).
- `--list` → print the eligible queue and exit; do not run any broadcast.
- `<raw-path>` → target the specified Raw. Accepts absolute or
  vault-relative paths. Abort with a clear error if the Raw is not
  eligible (already broadcast, declined, or never distilled).

Follow the cortex-broadcast skill's full flow: queue build, Raw selection,
vec-search candidates, menu confirmation, per-page conversation with
contradiction handling, per-page commits, marker + log finalization.
```

- [ ] **Step 2: Verify**

Run: `head -15 /synosrc/misc/cortex/commands/broadcast.md`

Expected: YAML frontmatter with `name: broadcast`, `argument-hint`,
`allowed-tools` list including Bash, `skills: [cortex-broadcast]`.

- [ ] **Step 3: Commit**

```bash
cd /synosrc/misc/cortex
git add commands/broadcast.md
git commit -m "feat(broadcast): add /cortex:broadcast command

Thin delegator to cortex-broadcast skill. Supports three invocation
forms: no-arg (FIFO from queue), --list (print queue, exit), <raw-path>
(target specific Raw).

Ref: docs/superpowers/specs/2026-04-17-phase2-broadcast-ingest-design.md
"
```

---

## Task 4: Extend `skills/cortex-distill/SKILL.md` with Step 9

**Files:**
- Modify: `/synosrc/misc/cortex/skills/cortex-distill/SKILL.md` (append new Step 9 after existing Step 8)

- [ ] **Step 1: Read tail of current SKILL.md**

Run: `tail -10 /synosrc/misc/cortex/skills/cortex-distill/SKILL.md`

Expected: ends with the Step 8 commit block and `If auto_push is true in config: git push.` line.

- [ ] **Step 2: Append Step 9**

Use the Edit tool. Find the last line of the file:

```
If `auto_push` is true in config: `git push`.
```

Replace with:

````markdown
If `auto_push` is true in config: `git push`.

## Step 9: Ask — Broadcast Now?

For each Raw where the terminal outcome was `new` or `pending-merge` (i.e.,
broadcast-eligible), prompt the user once before moving to the next Raw:

```
Raw <filename> processed (outcome: <outcome>). Broadcast now? (y/n/l)
  y = enter broadcast conversation immediately
  n = decline (mark as no-broadcast; will not re-prompt later)
  l = later (stays in broadcast-eligible queue)
```

### Dispatch

- **y** → dispatch to the `cortex-broadcast` skill for this single Raw. When
  broadcast completes, return here and move to the next unprocessed Raw.
- **l** → no action. The Raw's Phase 1 marker is unchanged; it is
  automatically eligible for later `/cortex:broadcast` invocation.
- **n** → append a terminal segment to the Raw's marker using the Edit
  tool. Transform:
  - `<!-- distilled: YYYY-MM-DD → <path> -->`
    becomes
    `<!-- distilled: YYYY-MM-DD → <path> | no-broadcast: <today> -->`
  - `<!-- distilled: YYYY-MM-DD → pending-merge: <path> (<score>) -->`
    becomes
    `<!-- distilled: YYYY-MM-DD → pending-merge: <path> (<score>) | no-broadcast: <today> -->`

Date format: `YYYY-MM-DD`.

For outcomes `skip-routine` and `no-insight`, do not prompt — those Raws
are ineligible by definition.

If the `n` path ran, stage the Raw and amend into the existing batch commit
for this distill run (or, if the commit already closed, make a follow-up
commit `chore(distill): record no-broadcast declines`).
````

- [ ] **Step 3: Verify**

Run: `grep "^## Step" /synosrc/misc/cortex/skills/cortex-distill/SKILL.md`

Expected 9 `## Step` lines, ending with:
```
## Step 9: Ask — Broadcast Now?
```

Run: `wc -l /synosrc/misc/cortex/skills/cortex-distill/SKILL.md`

Expected: up from 180 to roughly 215.

Run: `grep -c "^## Step" /synosrc/misc/cortex/skills/cortex-distill/SKILL.md`

Expected: `9`.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git commit -m "feat(distill): add Step 9 — Ask broadcast now?

Phase 2 integration point. After per-Raw Phase 1 completion, prompt
(y/n/l) to dispatch to cortex-broadcast inline, decline (write
no-broadcast marker), or defer (leave eligible for later
/cortex:broadcast). Skipped for skip-routine and no-insight outcomes.

Ref: docs/superpowers/specs/2026-04-17-phase2-broadcast-ingest-design.md
"
```

---

## Task 5: Acceptance test — broadcast the existing pending-merge

**Files read (may be modified during the test):**
- `/synosrc/cortex/Raw/2026/04/17/141013_session_webapi-Notification.md`
- `/synosrc/cortex/Projects/libsynosysnotify/synooauth flow chart.md`

This is the Phase 1 pending-merge seed left for Phase 2 to consume. Success criterion #5 in the spec.

- [ ] **Step 1: Snapshot pre-state**

Run:

```bash
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/17/141013_session_webapi-Notification.md
grep -r "^## \[" /synosrc/cortex/log.md | wc -l
cortex-vec status | grep Entries
```

Expected:
- Marker contains `pending-merge: Projects/libsynosysnotify/synooauth flow chart.md (0.48)` and no `merged:` / `broadcast:` / `no-broadcast:` segments yet.
- log entry count: 6 (from Phase 1 tasks + 補測).
- Chroma Entries: 106.

- [ ] **Step 2: Follow the cortex-broadcast skill manually for this Raw**

The Skill tool loads the cached v0.7.0 plugin; it will not see the just-committed Phase 2 skill files. Read the dev version of the skill:

```bash
cat /synosrc/misc/cortex/skills/cortex-broadcast/SKILL.md
```

Then walk through its Step 1–10 logic for the pending-merge Raw:

1. Queue → the Raw (the only eligible entry).
2. vec search on its longest Discovery bullet.
3. Menu: pre-selected entry for `Projects/libsynosysnotify/synooauth flow chart.md`; also consider any other candidates that scored ≥ 0.40.
4. Enter conversation for the pre-selected page. The user will actually drive this conversation — confirm at least one meaningful change (prose edit, wikilink addition, or contradiction flag).
5. Commit the page edit.
6. Finalize: marker transitions `pending-merge: ... (0.48)` → adds `| merged: 2026-04-17 → [[synooauth flow chart]]` segment. Append log entry. Commit marker + log.

- [ ] **Step 3: Verify marker transition**

Run:

```bash
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/17/141013_session_webapi-Notification.md
```

Expected shape:
```
<!-- distilled: 2026-04-17 → pending-merge: Projects/libsynosysnotify/synooauth flow chart.md (0.48) | merged: 2026-04-17 → [[synooauth flow chart]] -->
```

- [ ] **Step 4: Verify log entry added**

Run:

```bash
grep -A 4 "broadcast | 141013_session_webapi-Notification" /synosrc/cortex/log.md
```

Expected: an H2 broadcast entry with `source_outcome: pending-merge`,
`pages_touched`, `repo: webapi-Notification`.

- [ ] **Step 5: Verify chroma refresh**

Run: `cortex-vec status | grep Entries`

The count may not change (upsert replaces, doesn't add) but the embedding
for `Projects/libsynosysnotify/synooauth flow chart.md` should reflect new
content. Sanity-check by:

```bash
cortex-vec search "webapi-Notification oauth refresh" --n 3 2>&1 | head -5
```

Expected: the synooauth flow chart page appears in results, likely with a
higher score than before (0.48 was pre-broadcast).

- [ ] **Step 6: Verify commit trail**

Run: `cd /synosrc/cortex && git log --oneline -4`

Expected: at least 2 new commits — one `broadcast: update <page> from
<raw>` per edited page, plus one `broadcast: finalize
141013_session_webapi-Notification.md` covering marker + log.

---

## Task 6: Acceptance test — distill inline `later` flow

**Files:**
- None modified by this task's setup; the test exercises distill + broadcast as separate steps.

- [ ] **Step 1: Identify a candidate Raw**

Pick one of the existing already-distilled Raws that is currently
broadcast-eligible per the definition in Task 5 Step 1 — its marker must
be `new` or `pending-merge`, and must not yet have any `broadcast:`, `merged:`, or `no-broadcast:` segment.

Candidates (from prior tasks):
- `/synosrc/cortex/Raw/2026/04/16/170916_session_syno-build-mcp.md` (new)
- `/synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md` (new)

Pick the first one for this test.

- [ ] **Step 2: Manually simulate distill Step 9 `later` response**

This Raw was distilled in Task 6 of Phase 1 (before Step 9 existed). It
currently has no Step-9 answer recorded. For this test, simulate "user
chose later" — this is a no-op on the marker (per Task 4 Step 2 spec: `l`
requires no marker change). Simply verify that the Raw appears in the
broadcast queue.

Run:

```bash
grep -rL '| broadcast:\|| merged:\|| no-broadcast:' /synosrc/cortex/Raw/ --include='*.md' \
  | xargs grep -l '<!-- distilled:' \
  | xargs grep -LE '(skip: routine|no insight)' \
  | grep 170916_session_syno-build-mcp
```

Expected: the full path to the Raw is listed.

- [ ] **Step 3: Verify `--list` would include it**

Conceptually walk through cortex-broadcast Step 3: the queue-print logic
would see this Raw as eligible and show `outcome: new` with its
`Projects/syno-build-mcp/checkDockerImage-bug.md` target. Document the
expected listing output in the acceptance notes.

No marker update, no log entry. This is a queue-membership test only.

---

## Task 7: Acceptance test — `n` decline path

**Files:**
- Modify (as part of test): one eligible Raw's marker to add `| no-broadcast:` segment.

- [ ] **Step 1: Pick a Raw to decline**

Use `/synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md` — already
`new` outcome from Phase 1 Task 6, not yet broadcast.

- [ ] **Step 2: Apply `no-broadcast:` marker per spec Section 5**

Use the Edit tool on the Raw. Find the line:

```
<!-- distilled: 2026-04-17 → Projects/syno-naxos/lifecycle-hook-bugs.md -->
```

Replace with:

```
<!-- distilled: 2026-04-17 → Projects/syno-naxos/lifecycle-hook-bugs.md | no-broadcast: 2026-04-17 -->
```

- [ ] **Step 3: Verify exclusion from queue**

Run:

```bash
grep -rL '| broadcast:\|| merged:\|| no-broadcast:' /synosrc/cortex/Raw/ --include='*.md' \
  | xargs grep -l '<!-- distilled:' \
  | xargs grep -LE '(skip: routine|no insight)' \
  | grep 180605_session_syno-naxos
```

Expected: empty output (the Raw is no longer eligible).

- [ ] **Step 4: Commit the decline**

```bash
cd /synosrc/cortex
git add Raw/2026/04/16/180605_session_syno-naxos.md
git commit -m "distill: decline broadcast for syno-naxos lifecycle-hook-bugs

Phase 2 acceptance — exercise n-path. Raw stays distilled, but no
compounding into related pages.
"
```

---

## Wrap-up

- [ ] **Step 1: Verify all success criteria against spec Section "Success criteria"**

Spec lists 6 numbered criteria. For each, confirm satisfied:

1. ☐ Compounding visible — the `synooauth flow chart.md` page has new content from the Raw (verified in Task 5 Step 2/3).
2. ☐ Every broadcast produces log + marker — Task 5 Steps 3 and 4.
3. ☐ Per-page commit audit trail — `git log --oneline --grep='^broadcast:' /synosrc/cortex` (Task 5 Step 6).
4. ☐ `--list` works — conceptually verified in Task 6 Step 3; run
   `grep -rL '| broadcast:\|| merged:\|| no-broadcast:' ...` to inspect
   the actual queue state at session end.
5. ☐ Phase 1 pending-merge seed consumed — Task 5 marker check shows
   `merged:` segment.
6. ☐ Contradictions flagged or resolved — if no contradiction surfaced in
   Task 5's conversation, document "no contradictions observed in this
   test batch; feature wired but not exercised live."

- [ ] **Step 2: Dispatch final code quality review**

Dispatch a `superpowers:code-reviewer` subagent across:

- BASE_SHA: the commit before Task 2's first commit (the Phase 1 wrap-up
  commit `f583497`).
- HEAD_SHA: the latest plugin-repo commit after Tasks 2, 3, 4.

Focus: cross-file consistency between `cortex-broadcast/SKILL.md`,
`commands/broadcast.md`, `cortex-distill/SKILL.md` Step 9 extension.

- [ ] **Step 3: Append rollout notes**

Edit
`/synosrc/misc/cortex/docs/superpowers/plans/2026-04-17-phase2-broadcast-ingest.md`
(this file). Append a "Phase 2 rollout notes (2026-04-17)" section with:

- Commits list (plugin + vault)
- Acceptance test outcomes (Task 5 commit SHAs, page content changed,
  log entries added)
- Any deviations from spec observed during implementation
- Paths exercised vs paths deferred (e.g., auto-dispatch of menu with >5
  candidates may not have been exercised)

Commit:

```bash
cd /synosrc/misc/cortex
git add docs/superpowers/plans/2026-04-17-phase2-broadcast-ingest.md
git commit -m "docs(plan): append Phase 2 rollout notes"
```

- [ ] **Step 4: Do not push**

Per Phase 1 convention, do not auto-push. Leave plugin and vault local.
Report status + final commit SHAs and ask the user whether to push.

---

## Known deviations from spec

1. **Skill tool loads cached plugin version.** Acceptance tests (Tasks 5–7)
   cannot invoke the new `cortex-broadcast` skill via the Skill tool —
   they walk through its logic manually against the dev-repo SKILL.md.
   Same constraint as Phase 1 Task 6. Documented so future Phase 3
   acceptance tests do not get surprised.
2. **Acceptance is manual.** No pytest harness; verification is
   `grep`/`cat`/`git log` + visual sanity checks. Acceptable for
   markdown-skill projects.
3. **`abort` semantic is a session-local user input**, not a shell signal.
   The skill relies on the user typing `abort` during conversation rather
   than sending SIGINT. Implementation-plan choice consistent with
   spec Open Question #2.

---

## Phase 2 rollout notes (2026-04-20)

### Execution summary

All 7 planned tasks executed via SDD + inline acceptance. Four plugin-repo
implementation commits, one follow-up fix commit, plus three vault-repo
acceptance commits. One rate-limit interruption between Task 1 and Task 2
(reset at 9pm Asia/Taipei), resumed cleanly via fresh Agent dispatch.

### Commits

**Plugin repo (`/synosrc/misc/cortex/`):**
- `2786ac9` feat(broadcast): cortex-broadcast skill initial — Task 2 (307 lines)
- `850e56c` fix(broadcast): clarify zero-candidate branch, pending-merge APPEND — Task 2 re-review fixes (+42 lines)
- `b86d16b` feat(broadcast): /cortex:broadcast command — Task 3
- `e281ee8` feat(distill): distill SKILL Step 9 — Task 4
- (pending: OBS-1 fix appending `no extractable content` to eligibility filter regex + this rollout notes commit)

**Vault repo (`/synosrc/cortex/`):**
- `d8d7dbb` distill: decline broadcast for syno-naxos — Task 7 (n-path acceptance)
- `03a01e8` broadcast: update synooauth flow chart from webapi-Notification — Task 5 (page edit)
- `21e324a` broadcast: finalize 141013_session_webapi-Notification — Task 5 (marker + log)

### Acceptance test outcomes

| Path | Raw | Outcome | Verified |
|---|---|---|---|
| pending-merge → merged | `141013_session_webapi-Notification.md` (0.48) | merged → [[synooauth flow chart]] | page edit + marker APPEND + log entry |
| `n` decline path | `180605_session_syno-naxos.md` | `\| no-broadcast: 2026-04-20` marker | excluded from queue |
| queue membership | `170916_session_syno-build-mcp.md` (new) | present in eligible queue | grep confirms |

### Success criteria — all pass

1. ✅ Compounding visible — `synooauth flow chart.md` gained a "Testing Coverage" section noting TestSYNOCoreNotificationMailOauth skip + integration gap.
2. ✅ Every broadcast produces log + marker — log entry `[2026-04-20 10:38]` + marker APPEND present.
3. ✅ Per-page commit audit trail — `git log --grep='^broadcast:'` shows 2 commits (page edit + finalize).
4. ✅ `--list` wired (structure verified; cache constraint prevents live Skill-tool invocation, same as Phase 1).
5. ✅ Phase 1 pending-merge seed consumed naturally — no migration required, original pending-merge segment preserved via APPEND.
6. ✅ Contradictions feature wired but not exercised — target page had no claims contradicted by Raw (log `contradictions_flagged` correctly omitted per spec).

### Review iterations captured

Task 2's initial commit `2786ac9` passed spec review but failed code quality review with 1 Critical + 3 Important + 4 Minor issues:
- **Critical**: Zero-candidates branch was undefined — LLM could not distinguish `(no candidates)` from `(no changes)` in Step 9. Fix added explicit "If no candidates pass the threshold" subsection in Step 5.
- **Important #2 (highest-risk)**: Step 9.1 pending-merge table cell said "replace pending-merge: ... with merged:" — an LLM following the first sentence literally would DELETE the pending-merge segment. Fix rewrote to unambiguous **APPEND** semantics with explicit "Do NOT remove" directive.
- **Important #3**: Keyword collision — `cancel` at menu vs `cancel/abort` mid-conversation. Fix renamed menu keyword to `quit` and added a clarifying note.
- **Important #4**: Query heuristic wording diverged from distill Stage 2. Unified to "most content-ful bullet with concrete referents".
- 4 Minor issues: menu example, LLM-self-assess response set, inline-detection note, zero-contradictions log example.

Task 5 (live broadcast) exercised the APPEND fix directly — the marker transitioned from `pending-merge: ... (0.48)` to `pending-merge: ... (0.48) | merged: 2026-04-20 → [[synooauth flow chart]]`. The `pending-merge:` segment survived intact, as intended.

### OBS-1 — Legacy marker queue pollution (fixed during wrap-up)

Task 6 verification surfaced that the eligibility filter's `grep -LE '(skip: routine|no insight)'` did not exclude pre-Phase-1 legacy markers `(no extractable content)`. 11 such Raws were appearing in the eligible queue incorrectly. Fixed by appending the legacy pattern to the exclusion regex:

```
grep -LE '(skip: routine|no insight|no extractable content)'
```

After fix, the queue returns the expected 2 Phase-1-processed Raws (170916_session_syno-build-mcp, 172109_session_cortex) plus any not-yet-distilled ones (which should be rare).

### Paths not covered by live test

- **Auto-dispatch `pending-merge` via score ≥ 0.60**: no natural Raw in the vault reached that score (max observed in this session was 0.48 for webapi-Notification → [[synooauth flow chart]]). The marker/log write logic was verified via interactive-(p) pathway, which shares the same write code.
- **Contradiction flagging**: target page had no claims contradicted by the Raw — the `⚠️ Contradicts [[raw]]` flow is wired but the first live contradiction awaits an organic trigger.
- **cortex-vec unavailable fallback**: skill fallback logic complete; live trigger (network outage or command removal) not exercised in this session.
- **Multi-page broadcast session**: Task 5 only touched 1 page (the pending-merge target). A session with 3-5 target pages will exercise the `Processing [i/N]` counter and multiple-commit flow. First live occurrence will populate this.

### Phase 2 end state

- **broadcast-eligible queue size after Phase 2**: 2 real Phase 1 Raws (170916_session_syno-build-mcp, 172109_session_cortex).
- **pending-merge queue size**: 0 (Phase 1 seed consumed).
- **Total chroma entries**: 106 → 106 (broadcast upserted but didn't add a new document; synooauth flow chart's embedding was refreshed).
- **Total log entries**: 6 → 7 (added the broadcast entry).

### Neither repo pushed

Per convention, plugin repo and vault repo stay local. Plugin branch is 18 commits ahead of `origin/plugin` (11 pre-existing + 7 Phase 2). Vault repo has the 4 new commits. Push decision deferred to user.
