# Phase 2 — Broadcast Ingest (llm-wiki style compounding)

**Date:** 2026-04-17
**Status:** Draft
**Builds on:**
- `docs/superpowers/specs/2026-04-17-distill-phase1-extraction-log-design.md`
- `docs/specs/2026-04-14-distill-query-redesign.md`
**Related future phase:** Phase 3 (lint)

## Problem

Phase 1 fixed the false-negative rate of distill's single-gate assessment and
established `pending-merge` as a "defer to Phase 2" work queue. But Phase 1
never updates existing Notes/Projects pages — every distill action is either
"create new page" or "write no file at all". This misses the compounding
benefit that the llm-wiki pattern promises:

> When you add a new source, the LLM reads it, extracts the key information,
> and integrates it into the existing wiki — updating entity pages, revising
> topic summaries, noting where new data contradicts old claims, strengthening
> or challenging the evolving synthesis.

Without cross-page integration, a vault accumulates disconnected new pages
alongside stale existing pages. The knowledge layer fragments over time.

## Goals

1. Every `has_insight=Yes` Raw eventually produces **updates to related
   existing pages**, not just one new page or a deferred marker.
2. The update mechanism accepts full prose rewrites, contradiction flagging,
   and summary revisions — not just append-only supplements. This is required
   because append-only approaches turn pages into time-ordered logs, losing
   the "current best understanding" property that concept pages need.
3. Human-in-loop per change: LLM proposes, human approves (or iterates).
   Auto-apply is never the default.
4. Per-page atomic commits for auditable history and surgical rollback.
5. Existing Phase 1 `pending-merge` queue is consumed naturally — no
   manual migration required.

## Non-goals

- **Auto-apply without user review.** The whole point of Phase 2 is human
  curation; the design deliberately trades batch throughput for quality.
- **Ingest atomicity across distill and broadcast.** llm-wiki's ideal is
  "source comes in, all pages updated in one go." Our conversational review
  UX makes that impractical for batches of Raws. Broadcast is a separate
  deferrable step.
- **State file tracking of partially-broadcast Raws.** Per-page commits
  stand; if user aborts mid-Raw, re-invocation does a fresh vec search and
  the user manually skips already-edited pages. Accepting the resume friction
  avoids state machine complexity.
- **Lint / health check.** That remains Phase 3.
- **Multi-Raw → same target page merging.** If two pending Raws both want
  to touch `Notes/Web benchmark.md`, Phase 2 handles them as two separate
  broadcast sessions. No batched merge optimization.

## Design

### 1. Scope

Broadcast = conversational update to 0–5 existing pages per Raw, invoked
either inline with distill (`y` / `later`) or explicitly via
`/cortex:broadcast`. Scope per session is one Raw. Each eligible page
receives full-fusion edits: prose rewrite, wikilink additions, contradiction
flags, summary revisions — whatever the LLM proposes and the user approves.

### 2. Entry points

**`/cortex:distill` (Phase 1, extended):** After completing per-Raw
processing in Step 5–8, the skill presents one more question:

> "Broadcast this Raw now? (y)es / (n)o / (l)ater"

- `y` → immediately enter the broadcast flow for this Raw.
- `n` → Raw marker gets an appended `| no-broadcast: YYYY-MM-DD` segment
  marking the Raw as "intentionally declined"; it will not appear in the
  eligible queue. No log entry (nothing was broadcast).
- `l` → distill completes normally; Raw becomes eligible for later
  invocation of `/cortex:broadcast`.

**`/cortex:broadcast` (new):**

- `/cortex:broadcast` (no args) — process the next broadcast-eligible Raw
  in FIFO order (oldest pending first).
- `/cortex:broadcast <raw-relative-path>` — target a specific Raw.
- `/cortex:broadcast --list` — print the eligible queue (Raw filename +
  original outcome + vault-relative path) so the user can estimate how
  much work remains before committing to a session.

### 3. Eligibility

A Raw is broadcast-eligible if and only if all of:

- Its marker contains `<!-- distilled: YYYY-MM-DD → ... -->` (Phase 1
  processed it).
- Its outcome is `new` or `pending-merge` (not `skip-routine`, not
  `no-insight`). Interactive choices that mapped to `new` or `pending-merge`
  are implicitly included — the marker reflects the terminal outcome.
- Its marker does not already contain a `broadcast:`, `merged:`, or
  `no-broadcast:` segment (deduplication — a Raw is broadcast at most once,
  and a declined Raw is not re-offered).

### 4. Per-Raw broadcast flow

1. **Read Raw + marker.** Note the outcome (`new` vs `pending-merge`) and,
   for `pending-merge`, the original target path and score.
2. **Find candidates.** Run `cortex-vec search` on the longest
   Discovery/Decision bullet (same heuristic as Phase 1 Stage 2). Keep top-N
   where `N = broadcast.target_top_n` (default 5) and score ≥
   `broadcast.target_min_score` (default 0.40). Both read from
   `~/.cortex/config.json`.
3. **Pre-selection.** If the Raw was `pending-merge`, its original
   `pending-merge` target is pre-checked `[x]` in the menu. All other
   candidates are unchecked.
4. **Present menu.**
   ```
   Candidates for broadcast (toggle by number, or 'a' for all, 'n' for none):
   [x] 1. Notes/DSM/Web benchmark.md (0.59)    ← pending-merge target
   [ ] 2. Notes/Linux/tcpdump.md (0.52)
   [ ] 3. Notes/DSM/Support FAQ.md (0.41)
   Confirm selection? (y/n)
   ```
5. **Per-page conversation.** For each selected page, in order:
   - LLM reads the page and the Raw.
   - LLM proposes change #1 (one of: prose rewrite of a specific section,
     wikilink insertion, contradiction flag, summary revision).
   - User responds: `yes` / `no` / free-form modification request.
   - If accepted or modified: LLM applies to a working copy of the page.
   - LLM proposes change #2. Iterate.
   - When LLM has no more proposals, it explicitly says so. User can also
     type `done` at any time to stop.
   - Once the conversation ends, LLM writes the final content to the page.
   - `cortex-vec upsert <page>` refreshes the embedding.
   - Single `git commit` (vault repo) with message:
     `broadcast: update <page-title> from <raw-filename>`
6. **Finalize Raw.** After all selected pages are committed:
   - For `new` Raws: append `| broadcast: YYYY-MM-DD → [[A]], [[B]]` to the
     existing marker.
   - For `pending-merge` Raws: replace the `pending-merge: ... (score)`
     segment with `merged: YYYY-MM-DD → [[A]], [[B]]`. The leading
     `distilled:` segment stays untouched.
   - Append one `broadcast` log entry.
   - Single commit for marker + log.
7. **Offer next Raw.** If the session was triggered via `/cortex:broadcast`
   (not distill inline), ask: "Process next eligible Raw? (y/n)". If user
   chose inline via distill, return to distill flow.

### 5. Raw marker format

Phase 1's marker body is preserved; Phase 2 appends a segment after ` | `.

**Before broadcast (Phase 1 outputs):**

```
<!-- distilled: 2026-04-17 → Projects/foo.md -->
<!-- distilled: 2026-04-17 → pending-merge: Notes/X.md (0.87) -->
```

**After broadcast:**

```
<!-- distilled: 2026-04-17 → Projects/foo.md | broadcast: 2026-04-18 → [[A]], [[B]] -->
<!-- distilled: 2026-04-17 → pending-merge: Notes/X.md (0.87) | merged: 2026-04-18 → [[X]], [[Y]], [[Z]] -->
```

**If no pages were changed (user unchecked all, or LLM found no useful
edits on any selected page):**

```
<!-- distilled: 2026-04-17 → Projects/foo.md | broadcast: 2026-04-18 → (no changes) -->
```

**If user declined inline at distill time (`n` answer):**

```
<!-- distilled: 2026-04-17 → Projects/foo.md | no-broadcast: 2026-04-18 -->
```

The wikilink list in `broadcast:` markers reflects **actually committed**
pages — not candidates shown in the menu. This distinction is important
for Phase 3 lint, which will validate consistency between `broadcast:`
marker content and real page backlinks.

Summary of terminal marker shapes (all mutually exclusive):

| Segment | Meaning |
|---------|---------|
| `broadcast: <date> → [[...]]` | Broadcast completed; pages listed |
| `broadcast: <date> → (no changes)` | Broadcast ran, no page edits |
| `broadcast: <date> → (no candidates)` | vec search found nothing ≥ threshold |
| `merged: <date> → [[...]]` | Pending-merge Raw, broadcast completed |
| `no-broadcast: <date>` | User declined inline during distill |

### 6. Log format

New op type `broadcast`:

```markdown
## [2026-04-18 14:32] broadcast | 141013_session_webapi-Notification.md
- source_outcome: pending-merge
- pages_touched: [[Web benchmark]], [[Support FAQ]]
- contradictions_flagged: 1
- repo: webapi-Notification
```

Field rules:

- `source_outcome`: the terminal Phase 1 outcome (`new`, `pending-merge`).
  Interactive-branch mappings are reflected (`interactive-(p)` logs as
  `pending-merge`).
- `pages_touched`: bulleted list of wikilinks of actually committed pages.
  Empty array case: write `pages_touched: (none)` and omit
  `contradictions_flagged`.
- `contradictions_flagged`: integer ≥ 1 if any contradiction flags were
  added; omit line if zero.
- `repo`: Raw frontmatter `repo:` field or `(none)`.

### 7. Contradiction handling

When the LLM detects a claim in the Raw that contradicts a claim in the
target page:

1. LLM proposes an inline flag at the relevant location in the page:

   ```
   ⚠️ Contradicts [[<raw-filename>]]: <one-line statement of the conflict>
   ```

2. This proposal enters the conversational flow like any other change.
3. User response determines the outcome:
   - `yes` — accept; the `⚠️` stays in the page, flagging the tension for
     future resolution.
   - `no` — skip; flag is not added. Page keeps its original claim.
   - Free-form (`"the new info is correct, delete the old claim"`) — LLM
     rewrites the old claim with the new one, no `⚠️` flag.
4. Each accepted flag increments the `contradictions_flagged` counter for
   that broadcast session.

### 8. Rollback

No special mechanism. Each page edit is its own git commit with a clear
subject line (`broadcast: update <page> from <raw>`). Regret a specific
change → `git revert <sha>` in the vault repo. Because edits are per-page,
revert impact is confined to one page. The Raw marker and log still record
the attempted broadcast, which is correct — history stays honest.

### 9. Resume safety (mid-Raw abort)

If the user aborts mid-Raw (ctrl-C, or types `abort` during conversation):

- All already-committed page edits stand.
- Raw marker is **not** updated — it stays pre-broadcast.
- Log entry is **not** written.
- Re-running `/cortex:broadcast <raw>` performs a fresh vec search and
  presents the menu again. The user manually unchecks pages already edited
  (visual check in Obsidian or `git log` inspection).
- During conversation, if the LLM reads a page that already has prior-session
  edits, it sees them as existing content and naturally avoids duplicating.

This is the accepted trade-off: no state file, no resume tracking complexity.
Re-runs are idempotent at the per-page granularity (pages user didn't
re-select stay untouched).

### 10. Config additions

`~/.cortex/config.json` gains:

```json
{
  "broadcast": {
    "target_top_n": 5,
    "target_min_score": 0.40
  }
}
```

Both keys optional; skill falls back to the defaults shown if missing.

### 11. Skill / command changes

**New files:**

- `skills/cortex-broadcast/SKILL.md` — full broadcast flow per Section 4.
- `commands/broadcast.md` — delegates to skill, handles `--list` and
  `<raw-path>` arguments.

**Modified file:**

- `skills/cortex-distill/SKILL.md` — insert new Step 9 "Ask: Broadcast
  now?" between current Step 8 (Commit) and end of flow. The `l`/`later`
  path is a no-op (log entry already written; nothing else changes). The
  `y`/`now` path dispatches to the broadcast skill for this Raw.

## Success criteria

1. **Compounding visible in vault**: after processing the existing
   `webapi-Notification` pending-merge (`Projects/libsynosysnotify/synooauth
   flow chart.md` target), that target page shows new content sourced from
   the Raw — not just a backlink.
2. **Every broadcast produces log + marker**: per-Raw completion always
   results in exactly one new `## [...] broadcast` entry in `log.md` and
   exactly one `broadcast:` or `merged:` segment appended to the Raw marker.
3. **Per-page commit audit trail**: `git log --oneline --grep='^broadcast:'`
   in the vault shows one commit per page edit.
4. **`--list` works**: `/cortex:broadcast --list` prints the eligible queue
   sorted oldest-first.
5. **Phase 1 `pending-merge` seed is consumed naturally**: the existing
   webapi-Notification pending-merge marker flows through broadcast without
   special handling, producing a `merged:` segment.
6. **Contradictions are flagged or resolved, never silently dropped**: any
   conflict the LLM detects produces a user-facing choice; user can rewrite
   away the old claim, but doing nothing is not an option (the default
   answer is `yes` = accept the flag).

## Edge cases

- **No candidates returned (all scores below 0.40).** Skill reports "no
  eligible targets" and offers to finalize the Raw with
  `broadcast: YYYY-MM-DD → (no candidates)`. User still sees the option so
  the Raw can be taken out of the eligible queue without leaving it in
  limbo forever.
- **User unchecks all candidates.** Treated as the "no changes" case —
  Raw marker gets `broadcast: YYYY-MM-DD → (no changes)`.
- **User aborts during page conversation.** Per Section 9.
- **Target page is modified externally between vec search and conversation.**
  LLM reads the file fresh at conversation start, so edits made outside
  the session are respected (not overwritten).
- **`cortex-vec` unavailable.** Fall back: read `_index.md`, let LLM
  suggest up to 5 candidate pages by semantic judgment rather than score
  ranking. Log `candidates_source: llm-fallback` as an extra field.
- **Two contradictions on the same claim from different Raws processed
  sequentially.** Each is flagged separately during its own broadcast
  session. Phase 3 lint can later suggest consolidation.
- **Raw has `--list` invoked but log has been truncated / rotated.**
  Fall back to scanning Raw/ directly with `grep -r '<!-- distilled:'` +
  filter for eligibility. Implementation-plan decision.

## Migration from Phase 1

**Automatic, no user action required:**

- The existing Phase 1 `pending-merge` marker on
  `/synosrc/cortex/Raw/2026/04/17/141013_session_webapi-Notification.md`
  becomes the first eligible Raw in the queue.
- When processed, it goes through the standard broadcast flow. Its original
  target (`Projects/libsynosysnotify/synooauth flow chart.md`) appears
  pre-checked in the menu.
- On completion, marker transitions from:
  ```
  <!-- distilled: 2026-04-17 → pending-merge: Projects/libsynosysnotify/synooauth flow chart.md (0.48) -->
  ```
  to:
  ```
  <!-- distilled: 2026-04-17 → pending-merge: Projects/libsynosysnotify/synooauth flow chart.md (0.48) | merged: <date> → [[synooauth flow chart]], ... -->
  ```

**One explicit Phase 2 rollout step (not migration per se):**

- Add `broadcast` keys to `~/.cortex/config.json`.
- If user has an existing Phase 1 `pending-merge` Raw they've already
  processed via ad-hoc means (e.g., manually editing the target page during
  Phase 1 acceptance tests), they can manually append a synthetic `merged:`
  segment to the marker to take it out of the queue. No tooling for this;
  low frequency.

## Open questions for implementation plan

- **Order of candidates in the menu:** highest score first, or grouped by
  directory (Notes/ vs Projects/)? Implementation plan decides. Leaning
  toward highest-score-first with a visual indicator for repo-matching
  pages.
- **Abort mechanism concrete syntax:** is `abort` typed in the
  conversation, or does ctrl-C also work cleanly? Implementation plan
  should pin this down.
- **Conversation termination heuristic:** LLM needs a rule for when to
  declare "no more proposals". Candidates: (a) after N turns without new
  material, (b) LLM self-assesses once the page's summary / concept page
  content would not benefit from further edits, (c) user always has to
  type `done`. Leaning toward (b) but open.
- **Pre-selection logic for pending-merge target scoring below threshold:**
  if the Phase 1 `pending-merge` target was recorded with score 0.48 but
  user's config has `target_min_score: 0.60`, should the target still
  pre-select despite falling below threshold? Leaning yes — original
  intent overrides current threshold. Implementation plan confirms.

## Out of scope (reinforcement)

- Auto-apply without review (see Non-goals).
- Cross-Raw merging into one target (see Non-goals).
- State file for resume tracking (see Non-goals).
- Lint and consistency checking → Phase 3.
- Automatic contradiction resolution → Phase 3 or later.
- UI / Obsidian plugin integration → not planned.
