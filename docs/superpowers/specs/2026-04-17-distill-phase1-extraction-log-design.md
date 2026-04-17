# Distill Phase 1 — Extraction Quality + Log Foundation

**Date:** 2026-04-17
**Status:** Draft
**Builds on:** `docs/specs/2026-04-14-distill-query-redesign.md`
**Related future phases:** Phase 2 (broadcast ingest), Phase 3 (lint)

## Problem

The existing distill skill (2026-04-14 redesign) uses a single-stage
三濾鏡 (gotchas / conventions / decisions) as a binary gate. In practice
this produces **false negatives**: Raw files with clearly valuable
content get marked `(no extractable content)`.

Observed examples from `/synosrc/cortex/Raw/2026/04/16/`:

- `170916_session_syno-build-mcp.md` — contains a concrete bug analysis
  (hardcoded `"synoci_tool"` filter vs real image name
  `registry.synology.inc/synology/synoci/synoci:master`) plus a fix
  strategy (list-all + substring match). Marked `(no extractable content)`.
- `180605_session_syno-naxos.md` — three distinct bug analyses with
  root causes (shutdown timeout truncation, missing finally semantics,
  discarded warning). Marked `(no extractable content)`.

Root cause: the existing `assess_value()` answers two questions as
one — "does this Raw have insight?" and "is the insight different
enough from existing vault content to justify a new note?". When the
second answer is No, the first collapses to No too, and the Raw is
silently dropped.

A secondary problem: there is no timeline of what distill / evolve has
done. `_index.md` is a catalog; there is no append-only log. This blocks
future lint capabilities (finding stale pages, orphan pages, tracking
which Raws contributed to which refined page).

## Goals

1. Eliminate false-negative `(no extractable content)` for Raws with
   concrete insight.
2. Keep `chroma` index focused on refined Notes/Projects — never index
   Raws.
3. Establish an append-only `log.md` that records every distill /
   evolve action, to support Phase 2 (broadcast) and Phase 3 (lint).
4. Preserve a clean boundary: **Phase 1 never modifies existing
   Notes/Projects pages.** It only writes new pages, marks Raws, and
   appends to log.

## Non-goals

- Cross-page updates (Phase 2).
- Lint / health-check operations (Phase 3).
- Per-bullet granularity. A Raw with 3 Discoveries, 1 high-dedup + 2
  low-dedup, gets a single placement decision using top-1 score.
- Backfilling `log.md` from already-distilled Raws.
- Changing `cortex-query` or `cortex:weekly` behavior (only distill and
  evolve skills are touched).

## Design

### 1. Two-stage assessment

Split the single-gate `assess_value()` into two stages with independent
criteria.

#### Stage 1 — `has_insight()`

Pure content check. Does the Raw contain substance worth preserving,
regardless of vault state?

**Yes iff** the Raw's `## Discoveries` or `## Decisions` section
contains at least one of:

- A specific symbol / file path / line number
  (e.g. `src/main.rs:226`, `checkDockerImage()`,
  `SynoBuildConf/unit-test`).
- A specific bug mechanism or root-cause statement
  (e.g. "filter must fully match repository, substring not supported").
- A specific decision rationale in the form "X over Y because Z"
  (not bare "use X").

**No** if:

- Section is missing.
- Section exists but only contains vague statements ("fixed it", "works
  now", "tested successfully") without concrete referents.

Output:

- `Y` → proceed to Stage 2.
- `N` → mark Raw `(no insight)`, write log entry, done.

#### Stage 2 — `decide_placement()`

Only runs when Stage 1 returned Y. Decides where (or whether) to
materialize the insight, using dedup score as the primary signal.

Input: `cortex-vec search "<top discovery text>" --n 3` → top-1 score.

| Condition | Outcome | Raw marker |
|-----------|---------|------------|
| top-1 score < 0.70 | `new` | `→ <target-path>` |
| top-1 score 0.70–0.85 | interactive: ask user `(n)ew / (p)ending / (s)kip` | per choice |
| top-1 score ≥ 0.85 | `pending-merge` | `→ pending-merge: <existing-path> (<score>)` |
| Stage 1 Y but content is pure commit dump / tool recap | `skip-routine` | `→ (skip: routine)` |

Notes:

- `skip-routine` is a Stage 2 escape hatch for cases where Stage 1's
  "has specific symbol" passes but the symbol is only in a commit line
  with no analysis. Use sparingly.
- For interactive 0.70–0.85: the user answer governs the marker. If they
  pick `pending`, it behaves like the ≥0.85 case.
- `cortex-vec` unavailable → log `dedup_top1: unavailable`, fall back to
  LLM reading `_index.md` for rough dedup, treat as < 0.70 if uncertain
  (prefer false-positive new-page over losing the insight).

### 2. Raw marker formats

Extend the existing `<!-- distilled: YYYY-MM-DD → ... -->` convention
with four canonical shapes:

```
<!-- distilled: 2026-04-17 → Notes/DSM/foo.md -->
<!-- distilled: 2026-04-17 → pending-merge: Notes/Linux/tcpdump.md (0.87) -->
<!-- distilled: 2026-04-17 → (skip: routine) -->
<!-- distilled: 2026-04-17 → (no insight) -->
```

The `pending-merge` marker carries the existing target path and the
dedup score. Phase 2 reads these markers to build its work queue.

### 3. log.md

#### Location

`<vault>/log.md` — vault root, alongside `_index.md`.

#### Header (at file creation)

```markdown
---
created: 2026-04-17
---

# Cortex Log

Append-only record of vault operations (distill, evolve).

---
```

#### Entry format

One H2-prefixed entry per source processed (per Raw for distill, per
user action for evolve). Bullets carry structured metadata.

Distill entry (new outcome):

```markdown
## [2026-04-17 14:30] distill | 170916_session_syno-build-mcp.md
- outcome: new
- target: Projects/syno-build-mcp/dockerimage-filter-bug.md
- dedup_top1: 0.62 → [[Package Center guide]]
- repo: syno-build-mcp
```

Distill entry (pending-merge outcome; target points to an existing
vault page that overlaps above threshold):

```markdown
## [2026-04-17 14:35] distill | 181129_session_webapi-Web.md
- outcome: pending-merge
- target: Notes/DSM/Web benchmark.md
- dedup_top1: 0.89 → [[Web benchmark]]
- repo: webapi-Web
```

Evolve entry:

```markdown
## [2026-04-17 15:12] evolve | user-initiated
- outcome: new
- target: Notes/Web/fetch-vs-ajax.md
- repo: (none)
```

Field semantics:

- `outcome`: one of `new | pending-merge | skip-routine | no-insight`
  (distill) or `new` (evolve; evolve only creates new files).
- `target`: for `new` and `pending-merge`, the vault-relative path. For
  `skip-routine` and `no-insight`, the field is omitted.
- `dedup_top1`: present only when Stage 2 ran. Omitted for
  `no-insight`. Uses `unavailable` when vec service is down.
- `repo`: from Raw's `repo:` frontmatter, or `(none)` for
  repo-independent entries.

#### Scope in Phase 1

- Logged: `distill`, `evolve`.
- Not logged: `query` (too noisy at this stage).
- Not yet: `lint` (Phase 3).
- No backfill.

#### Parseability

- `grep "^## \[" log.md | tail -20` lists recent entries.
- `grep "pending-merge" log.md` lists all pending work queue entries
  (complements `grep -r "pending-merge" Raw/`).
- `grep "^## \[2026-04" log.md` filters by month.

### 4. Chroma rules

| Outcome | Write file? | Update `_index.md`? | `cortex-vec upsert`? |
|---------|-------------|---------------------|----------------------|
| `new` | yes | yes | yes (new file) |
| `pending-merge` | no | no | no |
| `skip-routine` | no | no | no |
| `no-insight` | no | no | no |

Rule: **"Write new file" iff "upsert to chroma".** Raws never enter
chroma. pending-merge stays cold until Phase 2 completes the merge,
at which point Phase 2 is responsible for re-upserting the updated
existing page.

### 5. Skill file changes

#### `skills/cortex-distill/SKILL.md`

- Replace Step 2 "Assess Value" with the two-stage structure above.
  Keep the three-filter table as *categorization hint* (not gate)
  inside Stage 1 guidance.
- Step 3 "Deduplication Check" folds into Stage 2. Preserve
  0.70–0.85 interactive flow; extend ≥0.85 to emit `pending-merge`
  marker instead of "suggest merge/skip/create anyway".
- Update Step 5 "Mark as Processed" with the four canonical marker
  shapes.
- Insert new Step 5.5 "Append Log Entry" before the commit step.
- Step 6 "Update Index" stays (only runs when outcome is `new`).
- Step 7 "Commit" — add `log.md` to `git add`.

#### `skills/cortex-evolve/SKILL.md`

- Before "Commit", insert "Append Log Entry" step with the evolve entry
  format.
- Add `log.md` to `git add`.

#### `skills/cortex-genesis/SKILL.md`

- When scaffolding a new vault, create `log.md` with the initial
  header. Existing vaults: no action (genesis should be idempotent
  and detect existing structure).

### 6. Workflow end-to-end

```
Raw file
  │
  ▼
Stage 1: has_insight()
  │
  ├─ N ──> mark (no insight) ──> log ──> commit
  │
  Y
  ▼
cortex-vec search top-3 (or fallback)
  │
  ▼
Stage 2: decide_placement()
  │
  ├─ <0.70 ──────> new ────────> write page + _index + vec upsert
  ├─ 0.70-0.85 ─> ask user ────> (new | pending | skip) branches
  ├─ ≥0.85 ─────> pending-merge ─> (no write)
  └─ commit-only/recap ─> skip-routine ─> (no write)
                │
                ▼
              mark Raw
                │
                ▼
            log.md append
                │
                ▼
              git commit
```

## Success criteria

1. The two canonical test cases (`170916_session_syno-build-mcp.md` and
   `180605_session_syno-naxos.md`) are **not** marked `(no insight)`.
   They should produce `new`, `pending-merge`, or interactive outcomes
   with visible reasoning.
2. Every distill action — including `no-insight` and `skip-routine` —
   produces exactly one `log.md` entry.
3. `grep -r "pending-merge" /synosrc/cortex/Raw/` returns a
   well-formed Phase 2 work queue (path, target page, score, all
   parseable).
4. `chroma` vector count after a distill batch equals the count of
   `new` outcomes in that batch (no pending-merge or skip contributions).
5. Phase 2's forthcoming design can implement broadcast by reading the
   existing `pending-merge` markers — **no Phase 1 signature change
   required** to support Phase 2.

## Edge cases

- **Raw with multiple Discoveries, mixed dedup scores.** Use top-1
  score for the entire Raw's placement decision. Bullet-level splits
  are Phase 2's concern.
- **`cortex-vec` unavailable at distill time.** Stage 2 logs
  `dedup_top1: unavailable`; LLM reads `_index.md` for rough
  dedup; defaults to `new` when uncertain (prefer over-collect).
- **Raw has Discoveries but all bullets are `"fixed"` / `"works"`
  style.** Stage 1 returns N → `(no insight)`.
- **pending-merge backlog grows large** (e.g. 60+ entries before
  Phase 2 lands). Acceptable. Users can inspect via
  `grep -r "pending-merge" Raw/` or `grep "pending-merge" log.md`.
- **Evolve called without a Raw source** (user types "save this to
  cortex" mid-conversation). log subject = `user-initiated`.
- **Interactive 0.70–0.85 declined (user picks `skip`).** Marker =
  `(skip: routine)`, same as the automated skip-routine path; log
  `outcome: skip-routine`.

## Migration

1. Create `/synosrc/cortex/log.md` with the initial header (one-off
   manual or via updated `cortex-genesis`).
2. Update `cortex-distill/SKILL.md` per Section 5.
3. Update `cortex-evolve/SKILL.md` per Section 5.
4. Re-run distill on the two known-broken Raws
   (`170916_session_syno-build-mcp.md`,
   `180605_session_syno-naxos.md`) to verify the fix.
   These Raws currently carry `(no extractable content)` markers from
   a previous distill — the skill needs to treat them as unprocessed
   if the marker value matches the legacy pattern; otherwise the user
   manually removes the stale marker. Implementation plan decides.
5. Verify `log.md` contains the expected entries.
6. Verify chroma count before/after matches success criterion 4.

## Open questions for implementation plan

- When re-running distill on a Raw with a legacy `(no extractable
  content)` marker, does the skill auto-upgrade (re-assess) or require
  manual marker removal? Recommendation: manual removal — migration is
  a one-time event, and auto-upgrade adds complexity for little value.
- What text does Stage 2 pass to `cortex-vec search`? Candidates: the
  Raw's title, the first Discovery bullet, or a concatenation of all
  Discoveries + Decisions. Existing skill is under-specified; the
  implementation plan should pick one and document it.
- Exact bash snippet for `log.md` append (ensure atomic, handles missing
  file, preserves trailing newline). Implementation plan decides.

## Out of scope (reinforcement)

- Broadcast / multi-page updates → Phase 2.
- Lint / health-check → Phase 3.
- Per-bullet granularity → Phase 2 may revisit.
- Raw-layer vector indexing → explicitly rejected (see Section 4).
- Query flow changes → unchanged from 2026-04-14 redesign.
