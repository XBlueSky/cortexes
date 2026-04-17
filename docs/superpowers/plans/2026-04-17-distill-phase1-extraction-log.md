# Distill Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace distill's single-gate assessment with a two-stage pipeline (has_insight → decide_placement), introduce a `pending-merge` outcome backed by configurable dedup thresholds, and establish an append-only `log.md` timeline that records every distill/evolve action.

**Architecture:** Phase 1 touches only markdown skill/command files plus two bootstrap assets (config key + log.md). Skills are pure markdown — Claude interprets them at runtime, so "implementation" here means rewriting prose in `skills/*/SKILL.md` and `commands/genesis.md`, plus one-off vault-side initialization. Phase 1 **never** modifies existing Notes/Projects pages; that boundary is preserved for Phase 2.

**Tech Stack:** Markdown (Claude skill/command format), `~/.cortex/config.json` (JSON), `cortex-vec search` CLI for dedup queries, bash one-liners for log append.

**Related spec:** `docs/superpowers/specs/2026-04-17-distill-phase1-extraction-log-design.md`

---

## File Structure

### Modified (plugin repo — `/synosrc/misc/cortex/`)

| File | Purpose of change |
|------|-------------------|
| `skills/cortex-distill/SKILL.md` | Split Step 2 into Stage 1 / Stage 2; rewrite Step 3 dedup handling; add four canonical marker shapes; add Step 7 log append; add `log.md` to Step 8 commit |
| `skills/cortex-evolve/SKILL.md` | Insert "Append Log Entry" step before Commit; add `log.md` to `git add` |
| `commands/genesis.md` | Add Step 4b to create `<vault>/log.md` with canonical header during vault init |

### Modified / created (outside plugin repo — one-off)

| File | Purpose |
|------|---------|
| `~/.cortex/config.json` | Add `distill.dedup_threshold_new` (0.45) and `distill.dedup_threshold_pending` (0.60) |
| `/synosrc/cortex/log.md` | Vault-side new file; initial header |

### No-change guarantee

- `commands/distill.md`, `commands/evolve.md` — command files unchanged (they just delegate to skills)
- `skills/cortex-query/SKILL.md`, `skills/cortex-weekly/SKILL.md` — untouched
- `cortex-vec` Python package — untouched
- Existing vault content in `Notes/`, `Projects/`, `Weekly/` — untouched

---

## Task Ordering

Tasks must run in order because later tasks reference artifacts built earlier:

```
Task 1 (config)  ──┐
Task 2 (log.md)  ──┼──> Task 4 (distill SKILL)   ──> Task 6 (distill acceptance)
                   │
                   └──> Task 5 (evolve SKILL)    ──> Task 7 (evolve acceptance)

Task 3 (genesis)   ──> independent; backports Task 2 into genesis workflow
```

---

## Task 1: Add dedup thresholds to `~/.cortex/config.json`

**Files:**
- Modify: `~/.cortex/config.json`

This is user-machine state, not a repo commit. Do this before skill edits so skill instructions can reference config keys.

- [ ] **Step 1: Show current config**

Run: `cat ~/.cortex/config.json`

Verify: file exists and is valid JSON. Note the current top-level keys (`vault_path`, `author`, `author_email`, `git`, `weekly`).

- [ ] **Step 2: Add `distill` section**

Use the Edit tool to insert a new top-level `distill` key after the `weekly` block. Final file content:

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
  }
}
```

- [ ] **Step 3: Verify**

Run: `jq '.distill' ~/.cortex/config.json`

Expected output:
```json
{
  "dedup_threshold_new": 0.45,
  "dedup_threshold_pending": 0.6
}
```

No commit — this is user-machine state.

---

## Task 2: Initialize `/synosrc/cortex/log.md`

**Files:**
- Create: `/synosrc/cortex/log.md` (vault repo)

- [ ] **Step 1: Verify log.md does not exist**

Run: `test -f /synosrc/cortex/log.md && echo "EXISTS" || echo "MISSING"`

Expected: `MISSING`

If `EXISTS`, stop and inspect the file before continuing — something already wrote to it.

- [ ] **Step 2: Create the file**

Use the Write tool to create `/synosrc/cortex/log.md` with exactly this content:

```markdown
---
created: 2026-04-17
---

# Cortex Log

Append-only record of vault operations (distill, evolve).

---
```

- [ ] **Step 3: Verify content**

Run: `head -10 /synosrc/cortex/log.md`

Expected: matches the content written in Step 2 exactly (7 lines including trailing `---`).

- [ ] **Step 4: Commit in vault repo**

```bash
cd /synosrc/cortex
git add log.md
git commit -m "chore: initialize log.md for distill/evolve timeline

Phase 1 of distill redesign — append-only record feeding future lint
(Phase 3) and providing visibility for pending-merge work queue
accumulation.
"
```

Note: vault's `auto_push: true` may push automatically via post-commit hook or skill-managed flow. Let it happen.

---

## Task 3: Extend `commands/genesis.md` with log.md creation

**Files:**
- Modify: `commands/genesis.md:57-62` (the "Initialize vault structure" step area)

Backport Task 2's log.md creation into the vault initialization flow so a new user running `/cortex:genesis` gets log.md for free.

- [ ] **Step 1: Read current Step 5 in genesis.md**

Current Step 5 (lines 57-62):

```markdown
### 5. Initialize vault structure

Ensure these directories exist in the vault:
- `Raw/`
- `Notes/`
- `Projects/`
- `Weekly/`
```

- [ ] **Step 2: Extend Step 5 to include log.md**

Replace the current Step 5 with:

```markdown
### 5. Initialize vault structure

Ensure these directories exist in the vault:
- `Raw/`
- `Notes/`
- `Projects/`
- `Weekly/`

Ensure `log.md` exists at the vault root. If missing, create it with:

```markdown
---
created: <today>
---

# Cortex Log

Append-only record of vault operations (distill, evolve).

---
```

The file is append-only; do not overwrite if it exists.
```

- [ ] **Step 3: Verify edit**

Run: `grep -A 2 "log.md exists at the vault root" commands/genesis.md`

Expected: three lines showing the new sentence + following lines.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add commands/genesis.md
git commit -m "feat(genesis): create log.md during vault init

Part of distill Phase 1 — new vaults now scaffold log.md alongside
the directory tree. Existing vaults unaffected (idempotent: skip if
present).
"
```

---

## Task 4: Rewrite `skills/cortex-distill/SKILL.md` for two-stage assessment

**Files:**
- Modify: `skills/cortex-distill/SKILL.md` (full rewrite of Steps 2–7)

This is the largest task. Split into sub-steps with a commit after each logical group.

- [ ] **Step 1: Read current SKILL.md**

Run: `wc -l skills/cortex-distill/SKILL.md`

Expected: ~100 lines.

Read the file to confirm current structure matches the spec's "current state": Steps 1–7 in that order.

- [ ] **Step 2: Replace Step 2 "Assess Value" with Stage 1**

Use Edit tool. Find the block from `## Step 2: Assess Value` down to (but not including) `## Step 3: Deduplication Check`. Replace with:

````markdown
## Step 2: Stage 1 — Has Insight

For each unprocessed Raw file:

1. Read the full content.
2. Check `## Discoveries` or `## Decisions` sections.
   - No such sections → `no-insight`, go to Step 5 (mark) + Step 7 (log).
   - Sections exist → apply the **has_insight** rule below.

### `has_insight()` rule

Answer **Yes** iff at least one bullet in Discoveries or Decisions contains one of:

- A specific symbol / file path / line number (e.g. `src/main.rs:226`, `checkDockerImage()`, `SynoBuildConf/unit-test`).
- A specific bug mechanism or root-cause statement (e.g. "filter must fully match repository, substring not supported").
- A specific decision rationale in the form "X over Y because Z" — not bare "use X".

Answer **No** if the section contains only vague statements like "fixed it", "works now", "tested successfully" without concrete referents.

- Yes → proceed to Step 3 (Stage 2).
- No → `no-insight`, go to Step 5 (mark) + Step 7 (log).

### Three-filter tags (categorization hint, not a gate)

When has_insight is Yes, optionally tag the extracted content for later lint:

| Tag | Signal | Example |
|-----|--------|---------|
| 踩坑 (gotcha) | Non-obvious behavior, hidden trap | "jsoncpp returns null for oversized doubles" |
| 慣例 (convention) | Synology-specific or internal practice | "Drive uses AppPortal.json, MailClient uses API" |
| 決策 (decision) | Why A over B, trade-off rationale | "build-history.json over PID check because..." |

These tags no longer gate extraction — they are metadata that helps Phase 3 lint query "show me all 決策 with no xref".
````

- [ ] **Step 3: Replace Step 3 "Deduplication Check" with Stage 2**

Find the block `## Step 3: Deduplication Check` down to (but not including) `## Step 4: Create Refined Note`. Replace with:

````markdown
## Step 3: Stage 2 — Decide Placement

Only runs when Stage 1 returned Yes.

### 3.1 Load thresholds

Read `~/.cortex/config.json`:

```bash
jq -r '.distill.dedup_threshold_new // 0.45' ~/.cortex/config.json
jq -r '.distill.dedup_threshold_pending // 0.60' ~/.cortex/config.json
```

Defaults: `new = 0.45`, `pending = 0.60`.

### 3.2 Query dedup

Pick the **most content-ful Discovery or Decision bullet** as the query text (longest bullet with concrete referents). Run:

```bash
cortex-vec search "<bullet text>" --n 3
```

If the repo is known from Raw frontmatter, add `--repo <name>` when searching Projects-bound content.

Extract top-1 `score` from the JSON output.

If `cortex-vec` is unavailable (command errors, ECONNREFUSED, etc.): treat as `score = 0.0`, log `dedup_top1: unavailable`, prefer false-positive `new` over losing the insight.

### 3.3 Decide outcome

| Condition | Outcome |
|-----------|---------|
| score < `dedup_threshold_new` | `new` |
| `dedup_threshold_new` ≤ score < `dedup_threshold_pending` | interactive — ask user `(n)ew / (p)ending / (s)kip` |
| score ≥ `dedup_threshold_pending` | `pending-merge` |
| Pure commit dump / tool recap with no analysis | `skip-routine` (escape hatch) |

Use `skip-routine` sparingly — only when Stage 1 passed on a symbol that turned out to be only a commit line with no surrounding analysis.

### 3.4 Dispatch

- `new` → go to Step 4 (create) + Step 5 + 6 + 7 + 8.
- `pending-merge` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only. **Do not write any new file or touch existing pages.**
- `skip-routine` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only.
- Interactive: user's choice governs the branch above.
````

- [ ] **Step 4: Replace Step 5 "Mark as Processed"**

Find `## Step 5: Mark as Processed` down to (but not including) `## Step 6: Update Index`. Replace with:

````markdown
## Step 5: Mark Raw as Processed

Append exactly one marker to the Raw file, chosen by Step 3 outcome:

| Outcome | Marker |
|---------|--------|
| `new` | `<!-- distilled: YYYY-MM-DD → <target-relative-path> -->` |
| `pending-merge` | `<!-- distilled: YYYY-MM-DD → pending-merge: <existing-path> (<score>) -->` |
| `skip-routine` | `<!-- distilled: YYYY-MM-DD → (skip: routine) -->` |
| `no-insight` | `<!-- distilled: YYYY-MM-DD → (no insight) -->` |

Score formatting: two decimal places (e.g., `0.62`, not `0.62345`).
Date: today, `YYYY-MM-DD`.
````

- [ ] **Step 5: Leave Step 6 largely intact, add outcome guard**

Find `## Step 6: Update Index`. Replace with:

````markdown
## Step 6: Update Index (only for `new` outcome)

Skip this step entirely for `pending-merge`, `skip-routine`, `no-insight`.

For each newly created file:

1. Run: `cortex-vec upsert <relative-path>`
2. Update `_index.md`: append row to the appropriate table (Notes or Projects section), update `entries` count and `updated` date in frontmatter.
````

- [ ] **Step 6: Add new Step 7 "Append Log Entry"**

After Step 6, insert a new section (before Step 7 Commit). Use Edit tool to find `## Step 7: Commit` and replace with:

````markdown
## Step 7: Append Log Entry

For each Raw processed (regardless of outcome), append exactly one entry to `<vault>/log.md`:

```markdown
## [YYYY-MM-DD HH:MM] distill | <raw-filename>
- outcome: <new|pending-merge|skip-routine|no-insight>
- target: <vault-relative path | omit for skip-routine and no-insight>
- dedup_top1: <score → [[wikilink]] | "unavailable" | omit for no-insight>
- repo: <value from Raw frontmatter repo: field | "(none)">
```

Append using:

```bash
cat >> <vault>/log.md <<'EOF'

## [$(date '+%Y-%m-%d %H:%M')] distill | <raw-filename>
- outcome: <outcome>
- target: <path>
- dedup_top1: <score> → [[<title>]]
- repo: <repo>
EOF
```

Note the leading blank line inside the heredoc — preserves separation from the previous entry.

Field rules:

- `target`: present for `new` and `pending-merge`. Omit the line for `skip-routine` and `no-insight`.
- `dedup_top1`: omit for `no-insight` (Stage 2 did not run). For `pending-merge` and interactive → pending, include the score and wikilink of the matched page. For `skip-routine`, include the score even though no write happened.
- `repo`: use `(none)` if the Raw has no `repo:` frontmatter field.

## Step 8: Commit

```bash
cd <vault>
git add Raw/ Notes/ Projects/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`.
````

- [ ] **Step 7: Verify edits**

Run: `wc -l skills/cortex-distill/SKILL.md`

Expected: between 150 and 200 lines (up from ~100).

Run: `grep -c "^## Step" skills/cortex-distill/SKILL.md`

Expected: `8` (Steps 1, 2, 3, 3.1/3.2/3.3/3.4 subsections are H3, main steps are H2 — so 8 Step headers: 1, 2, 3, 4, 5, 6, 7, 8).

Wait — recount: Steps are 1, 2, 3, 4, 5, 6, 7, 8 → 8 H2 `## Step` headers. Confirm with grep.

Run: `grep "^## Step" skills/cortex-distill/SKILL.md`

Expected 8 lines:
```
## Step 1: Find Unprocessed Raw Files
## Step 2: Stage 1 — Has Insight
## Step 3: Stage 2 — Decide Placement
## Step 4: Create Refined Note
## Step 5: Mark Raw as Processed
## Step 6: Update Index (only for `new` outcome)
## Step 7: Append Log Entry
## Step 8: Commit
```

- [ ] **Step 8: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git commit -m "feat(distill): two-stage assessment with pending-merge outcome

Splits the single-gate assess_value into Stage 1 (has_insight) and
Stage 2 (decide_placement). Introduces pending-merge as a Phase 2
work queue marker, guarded by configurable dedup thresholds
(distill.dedup_threshold_new, distill.dedup_threshold_pending).
Adds log.md append as a required post-assessment step.
Extraction no longer gates on three-filter matches — those become
categorization tags.

Ref: docs/superpowers/specs/2026-04-17-distill-phase1-extraction-log-design.md
"
```

---

## Task 5: Extend `skills/cortex-evolve/SKILL.md` with log append

**Files:**
- Modify: `skills/cortex-evolve/SKILL.md`

Evolve always produces a `new` outcome (user-driven save). Only two changes: add log append, and ensure `log.md` is included in the git add list.

- [ ] **Step 1: Locate the Commit section**

Run: `grep -n "^## Commit" skills/cortex-evolve/SKILL.md`

Expected: single line number, around line 84.

Read the surrounding context (±5 lines) to confirm the structure.

- [ ] **Step 2: Insert "Append Log Entry" before Commit**

Use Edit tool. Find the line:

```markdown
## Commit
```

Replace with:

````markdown
## Append Log Entry

Append one entry to `<vault>/log.md` (evolve-flavored):

```bash
cat >> <vault>/log.md <<'EOF'

## [$(date '+%Y-%m-%d %H:%M')] evolve | user-initiated
- outcome: new
- target: <vault-relative path of saved file>
- repo: <repo name or "(none)">
EOF
```

The `dedup_top1` field is omitted for evolve entries (evolve does not
perform a dedup check in Phase 1; the user explicitly chose to save).

## Commit
````

- [ ] **Step 3: Update the git add line to include log.md**

Find the existing commit block in `## Commit`:

```bash
git add <file> _index.md
git commit -m "cortex: <type> <brief>"
```

Replace with:

```bash
git add <file> _index.md log.md
git commit -m "cortex: <type> <brief>"
```

- [ ] **Step 4: Verify**

Run: `grep -n "log.md" skills/cortex-evolve/SKILL.md`

Expected: at least 3 matches — two in the Append Log Entry section (one in the heredoc comment, one in the `>>` redirect), one in the `git add` line.

- [ ] **Step 5: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-evolve/SKILL.md
git commit -m "feat(evolve): append log.md entry before commit

Part of distill Phase 1 — evolve now contributes to the shared
timeline. outcome is always 'new' (evolve never produces pending
or skip cases).

Ref: docs/superpowers/specs/2026-04-17-distill-phase1-extraction-log-design.md
"
```

---

## Task 6: Acceptance test — re-distill known-broken Raws

**Files read (not modified by this task's code; skill may modify them):**
- `/synosrc/cortex/Raw/2026/04/16/170916_session_syno-build-mcp.md`
- `/synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md`

Success criterion #1 in the spec: neither Raw should be marked `(no extractable content)` after Phase 1.

- [ ] **Step 1: Snapshot current state**

Run:

```bash
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/170916_session_syno-build-mcp.md
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md
```

Expected: both show `<!-- distilled: 2026-04-17 → (no extractable content) -->` (the legacy marker).

- [ ] **Step 2: Remove the legacy markers**

Legacy marker's text does not match any of Phase 1's four canonical shapes, so we remove it manually rather than auto-upgrading (per spec Open Question #1).

Edit both files: delete the `<!-- distilled: ... → (no extractable content) -->` line and any trailing blank line so the Raw is unmarked.

Verify:

```bash
grep -c "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/170916_session_syno-build-mcp.md
grep -c "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md
```

Expected: both print `0`.

- [ ] **Step 3: Invoke distill skill on these two files**

Dispatch to the cortex-distill skill. For each Raw, the skill should:

1. Run Stage 1 `has_insight` — both Raws contain concrete symbols (`checkDockerImage()`, `src/main.rs:226`) → return Yes.
2. Run Stage 2 dedup. Expected top-1 scores are low (< 0.45) based on earlier probe — outcome likely `new`.
3. Create a new file under `Projects/syno-build-mcp/` and `Projects/syno-naxos/` respectively.
4. Append the new marker to each Raw.
5. Append a log entry per Raw.

- [ ] **Step 4: Verify Raw markers**

Run:

```bash
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/170916_session_syno-build-mcp.md
grep "<!-- distilled:" /synosrc/cortex/Raw/2026/04/16/180605_session_syno-naxos.md
```

Expected: each shows one of:
- `<!-- distilled: 2026-04-17 → Projects/<repo>/<topic>.md -->` (new)
- `<!-- distilled: 2026-04-17 → pending-merge: <existing> (0.XX) -->` (unlikely given low expected dedup)

**Neither should contain `(no extractable content)` nor `(no insight)`** — those would indicate the Phase 1 fix failed.

- [ ] **Step 5: Verify log.md entries**

Run: `grep -A 4 "170916_session_syno-build-mcp\|180605_session_syno-naxos" /synosrc/cortex/log.md`

Expected: two distinct entries (one per Raw), each with H2 heading, `outcome`, `target`, `dedup_top1`, `repo` fields.

- [ ] **Step 6: Verify chroma count matches new-outcome count**

Run: `cortex-vec status`

Note the `Entries:` line. It should have increased by `2 × (count of 'new' outcomes from this batch)` since each new file contributes a body chunk + a summary chunk.

If any outcome was `pending-merge` or `skip-routine`, those contribute **zero** new chroma entries — that's success criterion #4.

- [ ] **Step 7: Record result**

No commit — the vault's auto-commit via distill skill's Step 8 handles vault-side. Document the acceptance result (pass/fail) for the plan wrap-up.

---

## Task 7: Acceptance test — evolve smoke test

**Files potentially created by test:**
- A throwaway note to be saved via evolve

- [ ] **Step 1: Trigger evolve**

Invoke `/cortex:evolve` with a tiny known piece of content (e.g., save a one-line note like "test: phase 1 evolve log smoke test"). Use a vanilla topic that will not collide with existing vault content (e.g., Notes/Web/phase1-smoke-test.md).

- [ ] **Step 2: Verify log.md has an evolve entry**

Run: `grep -A 3 "evolve | user-initiated" /synosrc/cortex/log.md | tail -10`

Expected: a recent entry with shape:

```markdown
## [2026-04-17 HH:MM] evolve | user-initiated
- outcome: new
- target: Notes/Web/phase1-smoke-test.md
- repo: (none)
```

- [ ] **Step 3: Verify commit includes log.md**

Run: `cd /synosrc/cortex && git log -1 --name-only`

Expected: the file list includes `log.md` alongside the newly created note and `_index.md`.

- [ ] **Step 4: Clean up (optional)**

If the smoke test note is unwanted, remove via:

```bash
cd /synosrc/cortex
git rm Notes/Web/phase1-smoke-test.md
# log.md entry stays — it is append-only and the record is valid
# _index.md: remove the row for phase1-smoke-test
git commit -m "chore: remove phase 1 smoke test note"
cortex-vec delete Notes/Web/phase1-smoke-test.md
```

If you want to keep it as a permanent marker of Phase 1 rollout, skip cleanup.

---

## Wrap-up

- [ ] **Step 1: Confirm all success criteria**

Spec Section "Success criteria" has 5 numbered items. For each, confirm:

1. ☐ Both canonical broken Raws are no longer `(no extractable content)` — verified in Task 6 Step 4.
2. ☐ Every distill action in the test batch produced exactly one log entry — verified in Task 6 Step 5.
3. ☐ `grep -r "pending-merge" /synosrc/cortex/Raw/` returns a well-formed queue — run this command; zero results is acceptable (the two test Raws may both have been `new`).
4. ☐ Chroma count increased by `2 × count(new)` — verified in Task 6 Step 6.
5. ☐ Phase 2 hook: no signature change to `pending-merge` marker format — inspect one marker via `grep -r "pending-merge" /synosrc/cortex/Raw/` if any exist; format must be `<!-- distilled: DATE → pending-merge: PATH (SCORE) -->`.

- [ ] **Step 2: Push plugin repo**

```bash
cd /synosrc/misc/cortex
git log --oneline -5
# expected: commits from Tasks 3, 4, 5 (Task 2 is vault-side)
git push
```

- [ ] **Step 3: Document open follow-ups**

In `docs/superpowers/plans/2026-04-17-distill-phase1-extraction-log.md` (this file), append a "Phase 1 rollout notes" section summarizing:

- Acceptance test outcomes (concrete markers + log entries seen)
- Observed top-1 scores for the two test Raws (data for future threshold calibration)
- Any marker format deviations that surfaced (unexpected escapes, quoting)

Commit:

```bash
cd /synosrc/misc/cortex
git add docs/superpowers/plans/2026-04-17-distill-phase1-extraction-log.md
git commit -m "docs(plan): append Phase 1 rollout notes"
```

---

## Known deviations from spec

1. **`skills/cortex-genesis/` does not exist.** Spec referred to updating this skill; actual file is `commands/genesis.md`. Task 3 targets the command instead.
2. **Acceptance testing is manual.** No pytest harness in this repo. Tasks 6 and 7 rely on manual invocation + grep verification. This is acceptable for markdown-skill projects and is documented in the spec's "Migration" section.
3. **Legacy marker handling is manual.** Per spec Open Question #1, the plan removes old `(no extractable content)` markers by hand in Task 6 Step 2 rather than teaching the skill to auto-upgrade.

---

## Phase 1 rollout notes (2026-04-17)

### Execution summary

All 7 planned tasks executed via subagent-driven development in a single session. Four plugin-repo commits + three vault-repo commits. Rollout took ~90 minutes end-to-end including two review iterations.

### Commits

**Plugin repo (`/synosrc/misc/cortex/`):**
- `d8b107f` feat(genesis): create log.md during vault init — Task 3
- `07d8156` feat(distill): two-stage assessment with pending-merge outcome — Task 4 initial
- `82f26d7` fix(distill): clarify log-append mechanism — Task 4 fix after code review
- `13d7e8b` feat(evolve): append log.md entry before commit — Task 5

**Vault repo (`/synosrc/cortex/`):**
- `8fcb638` chore: initialize log.md — Task 2
- `8d3ab10` distill: extract 2 entries from Raw — Task 6 acceptance
- `e0c8c09` cortex: note embedding score profile — Task 7 acceptance

### Acceptance test outcomes

Both previously-broken Raws produced `outcome: new` under the new skill:

| Raw | Score | Target | Comment |
|---|---|---|---|
| `170916_session_syno-build-mcp.md` | **0.37** → `[[3rdparty misc]]` | `Projects/syno-build-mcp/checkDockerImage-bug.md` | Previously `(no extractable content)` — false negative eliminated |
| `180605_session_syno-naxos.md` | **0.32** → `[[status code limit]]` | `Projects/syno-naxos/lifecycle-hook-bugs.md` | Three bug analyses preserved as separate sections |

Top-1 matches were semantically unrelated (scores well below 0.45 `new` threshold), confirming that the old `(no extractable content)` verdict was indeed a false negative driven by the "one-layer-glued" assessment rather than any genuine overlap.

### Success criteria — all pass

1. ✅ Neither test Raw ended up as `(no insight)` — both got valid `→ Projects/...` targets
2. ✅ Three log entries total (2 distill + 1 evolve) — one per source processed
3. ✅ `grep -r "pending-merge" Raw/` returned 0 — neither test Raw had high enough score to trigger pending-merge (both fell well below 0.45 threshold; queue remains empty from this batch)
4. ✅ Chroma count 100 → 104 after Task 6 (`2 × count(new) = 2 × 2 = 4`), then 104 → 106 after Task 7 (`1 new`)
5. ✅ pending-merge marker format stable — no Phase 1 signature change required for Phase 2

### Review iterations captured

Task 4's initial commit `07d8156` passed spec review but failed code quality review with 1 Critical + 3 Important + 3 Minor issues. The Critical was a `<<'EOF'` quoted heredoc that would have written `$(date ...)` literally into log.md. Fix commit `82f26d7` replaced it with an agent-composed-entry + `printf '\n%s\n'` pattern. Task 5's evolve instructions were written from the start using this fixed pattern, so Task 5 needed no follow-up.

### Observed embedding score reality

Phase 1 recalibrated thresholds (0.45/0.60) based on four probe queries against a 50-doc vault:

- Exact title match ceiling: **0.75**
- Typical same-topic overlap: **0.55–0.65**
- Weak relevance: **0.30–0.45**
- Noise: **0.15–0.30**

The two test Raws landed in the 0.30–0.37 band, consistent with "weak relevance / unrelated" rather than overlap. Recorded as a permanent Note at `Notes/Web/embedding score profile.md` for future calibration reference.

### Spec open questions — closed by implementation

All three open questions from the original spec are now effectively resolved:

1. **Legacy marker re-handling**: manual removal, not auto-upgrade (Task 6 Step 2).
2. **What text to pass to `cortex-vec search`**: skill now says "longest Discovery/Decision bullet with concrete referents" (distill SKILL.md Step 3.2).
3. **Exact log.md append bash snippet**: agent-composed-entry + `printf '\n%s\n' "$ENTRY" >> <log>` (both distill and evolve skill files).

### Minor deferred items (not blocking Phase 1)

- Distill SKILL.md Step 7 template shows `dedup_top1` unconditionally; prose rules correctly state when to omit. Minor prose clarity improvement deferred.
- Spec file itself could be annotated "Open questions closed in plan rollout notes" for future readers.
- `.gitignore` extended to cover `__pycache__/` and `*.pyc` from cortex-vec Python package. Housekeeping — not tied to Phase 1 scope.

### 補測 round — extending Task 6 coverage (vault commit `b80b074`)

Initial Task 6 only exercised the `new` outcome (both test Raws scored
< 0.45). A follow-up round covered the remaining outcome paths using
a mix of real and synthetic Raws. Results:

| 補測 | Raw | Score | Path exercised | Verified |
|---|---|---|---|---|
| 1 | webapi-Notification (141013) | 0.48 | interactive → `(p)` → `pending-merge` | marker + log + queue seeded |
| 2 | libsynosysnotify (142115) | 0.45 | interactive → `(s)` → `skip-routine` | marker + log, no file written |
| 3 | test-no-insight (170000, synthetic) | n/a | Stage 1 fail → `no-insight` | marker + log (target and dedup_top1 omitted) |

Chroma count unchanged (106 → 106): none of the three paths writes a
file, matching spec chroma-rule. `grep -r "pending-merge" Raw/`
returns exactly 1 entry now, demonstrating the Phase 2 work queue is
functional.

### cortex-vec unavailable fallback

Live probe:

```
env -i HOME=$HOME PATH=/usr/bin:/bin cortex-vec search "any query"
→ env: 「cortex-vec」: 沒有此一檔案或目錄  (exit nonzero)
```

In production, the skill's Step 3.2 catches this (`treat as score = 0.0,
log dedup_top1: unavailable, prefer false-positive new`). Full
end-to-end of this path was not triggered by any real Raw in this
session; the fallback is covered by the skill instructions but not
yet by a live log entry. First natural occurrence (e.g. during a
network outage) will populate the pattern.

### Paths not covered by live test

- **Auto-dispatch `pending-merge` (score ≥ 0.60)**: never triggered
  with natural vault content (0.48 was the highest observed). Marker
  format and log pattern verified via the interactive-(p) path, which
  shares the same write logic. First real auto-dispatch case will
  appear organically as vault grows.
- **`cortex-vec` unavailable at runtime**: skill instructions complete,
  fallback command paths tested independently, but no live log entry
  produced. Acceptable for Phase 1.

### Final commit trail

Plugin repo (`/synosrc/misc/cortex/`): 5 implementation commits (`d8b107f`,
`07d8156`, `82f26d7`, `13d7e8b`, `d18c29a`) plus 3 design commits (`639ef11`,
`ac978a8`, `8de977e`).

Vault repo (`/synosrc/cortex/`): 4 commits (`8fcb638`, `8d3ab10`, `e0c8c09`,
`b80b074`). Neither repo pushed yet — awaiting user.
