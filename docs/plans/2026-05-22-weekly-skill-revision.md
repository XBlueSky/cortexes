# Weekly Skill Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the nine decisions in `docs/specs/2026-05-22-weekly-skill-revision-design.md` to the `cortex-weekly` and `cortex-distill` skills, plus their shared `draft-template.md` reference, so the auto-generated weekly is closer to what gets pasted into the team meeting.

**Architecture:** Skills are pure markdown — no compiled code. Each task edits a numbered section of `SKILL.md` or `references/draft-template.md`. Verification is by reading the edited section back and (at the end) re-running the weekly skill against 2026-05-22 data and eyeballing against the spec's "After" excerpt.

**Tech Stack:** Markdown (Obsidian + GFM). Skill files live under `skills/<skill-name>/`. Config at `~/.cortex/config.json`.

---

## File Structure

Files modified by this plan:

| Path | Responsibility | Tasks |
|---|---|---|
| `skills/cortex-distill/SKILL.md` | Per-Raw distillation, Summary sidecar writeback | T2, T3 |
| `skills/cortex-weekly/SKILL.md` | Weekly compilation pipeline (7 steps) | T4, T5, T6, T7, T8 |
| `skills/cortex-weekly/references/draft-template.md` | Draft format reference loaded in Step 6 | T9, T10, T11, T12 |
| `CHANGELOG.md` | Version bump entry | T14 |
| `plugin.json` (or wherever version lives) | Version bump | T14 |

No new files. No deletions. All changes are in-place edits.

`~/.cortex/config.json` schema is documented in `skills/cortex-genesis/SKILL.md`; T1 updates that doc but the live config file is the user's, not in-repo.

---

## Verification Model

Skill bodies are documents read by an LLM at runtime, not code parsed by a compiler. The "tests" in this plan are read-back verifications: after each edit, Read the modified section and confirm the wording matches the spec. The final task (T13) re-runs the weekly skill end-to-end against this week's vault and eyeballs against the spec's "After" example.

No pytest suite covers skill markdown. The existing `tests/test_rtk_*.py` files are for unrelated runtime tooling and stay untouched.

---

## Task 1: Document `repo_issue_map` in cortex-genesis

**Files:**
- Modify: `commands/genesis.md` (find the config-writing section around lines 40–58; add the new field to the JSON template and document it after the JSON block)

**Why first:** The new field is referenced by both distill (T2) and weekly (T4–T8). Documenting it in genesis means future `/cortex:genesis` runs prompt for it when relevant, and existing users can grep the skill to learn the field exists.

- [ ] **Step 1.1: Locate the config-writing section in genesis**

```bash
grep -n "weekly\|gitlab_username" /synosrc/misc/cortex/commands/genesis.md
```

Expected: matches around line 53 where the JSON template lists `"weekly": { "gitlab_username": ... }`.

- [ ] **Step 1.2: Add `repo_issue_map` field documentation**

After the line documenting `experimental_repos`, append the following block (verbatim — adjust list indentation to match the surrounding markdown):

````markdown
- `weekly.repo_issue_map` (optional, object): map from bare repo name
  (matches `repo:` frontmatter in Raw/Summary) to a list of Workplus
  issue keys. Lets repos whose work has no `Ref:` trailer be promoted
  from `misc.` into `feat.` / `fix.` under a Workplus issue.

  ```json
  "repo_issue_map": {
    "morpheus": ["DSM-172916"]
  }
  ```

  - Key form: bare repo name. When matching a GitLab MR target like
    `wit/morpheus`, weekly takes the last path segment.
  - Value form: list of issue keys (1:N — a repo can host work for
    multiple concurrent features).
  - When a MR has a `Ref:` trailer, the trailer wins; the map is a
    fallback for MRs without `Ref:` and for vault-only Summary
    entries (no MR merged this week).
  - When the map is absent or empty, weekly behaves as before — no
    vault-only promotion, no warning.
````

- [ ] **Step 1.3: Read back and verify**

```bash
sed -n '/repo_issue_map/,/empty/p' /synosrc/misc/cortex/commands/genesis.md
```

Expected: the documentation block above appears, plus the JSON template now lists `"repo_issue_map": {}` as an empty placeholder.

- [ ] **Step 1.4: Commit**

```bash
cd /synosrc/misc/cortex
git add commands/genesis.md
git commit -m "docs(genesis): document weekly.repo_issue_map config field"
```

---

## Task 2: Extend Summary frontmatter schema in cortex-distill

**Files:**
- Modify: `skills/cortex-distill/SKILL.md` lines 180–190 (Step 5.5.2 "Compose the frontmatter")

**Why:** Step 5.6 (T3) writes `issue:` into Summary frontmatter; weekly Step 3 (T4) reads it. The schema doc must list the field before the writer step does.

- [ ] **Step 2.1: Replace the frontmatter block**

Current block (line 184–190):

```yaml
---
raw: <vault-relative path to the source Raw file>
repo: <value from Raw frontmatter `repo:` field, or `(none)` if absent>
distilled: <today, YYYY-MM-DD>
---
```

Replace with:

```yaml
---
raw: <vault-relative path to the source Raw file>
repo: <value from Raw frontmatter `repo:` field, or `(none)` if absent>
issue: <Workplus issue key (e.g. DSM-172916), only when distill judged a match — see Step 5.6>
distilled: <today, YYYY-MM-DD>
---
```

Also replace the line above (line 182):

> Fixed 3-field schema, no other fields:

with:

> Fixed 4-field schema (one optional), no other fields:

- [ ] **Step 2.2: Read back and verify**

```bash
sed -n '180,196p' /synosrc/misc/cortex/skills/cortex-distill/SKILL.md
```

Expected: 4 fields listed, with `issue:` marked optional and pointing to Step 5.6.

- [ ] **Step 2.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git commit -m "docs(distill): add optional issue field to Summary frontmatter schema"
```

---

## Task 3: Add Step 5.6 to cortex-distill (judge Workplus issue)

**Files:**
- Modify: `skills/cortex-distill/SKILL.md` — insert a new Step 5.6 immediately after Step 5.5 (after line 202 in the current file)

**Why:** This is where the distillation step actually decides which Workplus issue a vault session belongs to, using the candidate list from `repo_issue_map`.

- [ ] **Step 3.1: Insert the new step**

After the current Step 5.5.3 block (ending around line 202), and before any subsequent step heading (likely "## Step 6"), insert:

````markdown
## Step 5.6: Judge Workplus Issue (optional)

Skip this step when:

- `~/.cortex/config.json` has no `weekly.repo_issue_map` field, OR
- The Raw's `repo:` is not a key in the map, OR
- The outcome is `pending-merge` or `skip-routine` (these don't get a
  fresh Summary rewrite for issue judgment).

Otherwise:

1. Let `candidates = repo_issue_map[repo]` (a non-empty list).
2. If `len(candidates) == 1`:
   - `issue = candidates[0]` — no LLM call needed.
3. Else (`len(candidates) >= 2`):
   - Read the Raw body (the full `### User` / `### Claude` exchange,
     not just the frontmatter).
   - For each candidate key, fetch `workplus_get_issue(key).title`
     (cache across distill runs in this batch).
   - Prompt the LLM (one call): "Given the Raw body below and the
     candidate Workplus issues with their titles, which single
     candidate best fits this session's work? Reply with the issue
     key or `null` if no candidate fits."
   - `issue = LLM response` (either a key from `candidates` or `null`).
4. Update the Summary sidecar's frontmatter:
   - When `issue` is a key → write `issue: <KEY>`.
   - When `issue` is `null` or step skipped → **omit** the `issue:`
     field entirely (do not write `issue: null` or `issue: ""`).

### Cost

At most one extra LLM call per Raw, only for Raws whose `repo:` is
in the map AND has 2+ candidates. Repos with 1 candidate take no
extra LLM call.
````

- [ ] **Step 3.2: Read back and verify**

```bash
grep -n "^## Step" /synosrc/misc/cortex/skills/cortex-distill/SKILL.md
```

Expected: `## Step 5.6: Judge Workplus Issue (optional)` appears between Step 5.5 and the next step.

- [ ] **Step 3.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git commit -m "feat(distill): Step 5.6 judges Workplus issue from repo_issue_map"
```

---

## Task 4: Weekly Step 3 Source A — read `issue:` field

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` Source A block (around lines 65–108)

**Why:** Source A surfaces Summary content into the weekly draft. With T2/T3 in place, the `issue:` field exists; weekly must read and propagate it.

- [ ] **Step 4.1: Locate the "for each surviving Summary file" paragraph**

Around line 78:

> For each surviving Summary file, read frontmatter + body:
>
> - `repo:` from frontmatter → the session's target repo (use directly;
>   do NOT open the corresponding Raw file).
> - Body prose → the session description.

- [ ] **Step 4.2: Replace with the issue-aware version**

```markdown
For each surviving Summary file, read frontmatter + body:

- `repo:` from frontmatter → the session's target repo (use directly;
  do NOT open the corresponding Raw file).
- `issue:` from frontmatter (optional) → the Workplus issue this
  session contributes to, as judged by distill Step 5.6. When absent
  or empty, the session is treated as repo-level work with no issue
  attribution (this is the normal case for repos not listed in
  `weekly.repo_issue_map`).
- Body prose → the session description.
```

- [ ] **Step 4.3: Read back and verify**

```bash
sed -n '78,92p' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: the issue field bullet appears between `repo:` and Body prose.

- [ ] **Step 4.4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): Source A reads issue field from Summary frontmatter"
```

---

## Task 5: Weekly Step 4 — issue-aware merge join

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` Step 4 (around lines 222–233)

**Why:** Today's merge joins MR ↔ Summary by repo + date. When both sides carry an issue key, joining by issue is more precise — it avoids merging an unrelated Summary with an MR that happens to share repo + date.

- [ ] **Step 5.1: Replace bullet 2 of Step 4**

Current bullet 2 (lines 225–231) describes the repo+date join. Replace it with:

````markdown
2. For each GitLab MR, join to Source A summaries:
   - **Preferred: issue-aware join.** If the MR has a `Ref: KEY`
     trailer (or its repo is in `repo_issue_map` and only one
     candidate, see Step 5 Classification fallback), and the Summary
     has `issue: KEY` matching, that's the join. Date is no longer
     consulted in this branch — issue is canonical.
   - **Fallback: repo + date.** When either side lacks the issue
     field, fall back to the original join: Summary's `repo:` matches
     the MR's last-segment repo AND the Summary's date is the same
     date as the MR's `merged_at` or the immediately preceding date.
   - Exactly one match → use that Summary's prose body as the MR's
     session-context description text in the weekly draft.
   - Multiple matches (issue or repo+date branch) → choose the
     Summary whose `HHMMSS` is closest to the MR's `merged_at`
     timestamp. If still ambiguous, concatenate them, each as its own
     session contribution.
   - No match → the MR stands alone; commit title + Workplus issue
     title carry the description.

   Rationale: Summary prose intentionally does NOT enumerate MR URLs
   (see `cortex-distill` Step 5.5 guideline). When distill knows the
   issue (Step 5.6) we can join structurally on that, which is
   sharper than the repo+date heuristic.
````

- [ ] **Step 5.2: Read back and verify**

```bash
sed -n '222,250p' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: bullet 2 has both branches documented (issue-aware preferred, repo+date fallback).

- [ ] **Step 5.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): Step 4 prefers issue-aware MR/Summary join with repo+date fallback"
```

---

## Task 6: Weekly Step 5 — classification with `repo_issue_map` fallback

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` Step 5 Classification procedure (around lines 246–258)

**Why:** Today's rule says "no `Ref:` → misc." Spec adds: "if no `Ref:` AND repo is in `repo_issue_map` with exactly one candidate, treat as if that candidate were the `Ref:`." Also explicitly normalises that commit type does NOT decide section.

- [ ] **Step 6.1: Replace the Classification procedure block**

Lines 246–258 currently read:

```
### Classification procedure

For each self-authored MR:

1. If the MR's commit messages contain a `Ref: <KEY>` trailer:
   - Call Workplus `get_issue` on the key; cache the returned `title` **and** `type`
   - `type == "BUG"` → `fix.` under that issue
   - `type == "FEATURE"` → `feat.` under that issue
   - Any other type (rare — e.g. `TASK`) → treat as `FEATURE` for layout purposes
2. If no `Ref:` trailer:
   - Send to `misc.` regardless of commit type. Side-project work does not belong with issue-driven fix/feat.

This rule is intentionally simple: **Workplus owns the semantics**. A DSM-169641 cleanup that ships seven `chore` MRs is a bug fix because the issue says so, not because any individual commit says `fix(...)`.
```

Replace with:

````markdown
### Classification procedure

For each self-authored MR, determine its **effective issue key**:

1. If the MR's commit messages contain a `Ref: <KEY>` trailer → effective key = `<KEY>`.
2. Else, if the MR's repo (last path segment of `references.full`) is
   a key in `weekly.repo_issue_map` AND the value list contains
   **exactly one** candidate → effective key = that candidate.
3. Else, if the repo is in `repo_issue_map` with **two or more**
   candidates → ambiguous; treat as no effective key (the MR cannot
   be auto-attributed because the per-MR signal — `Ref:` — is missing
   and the map cannot disambiguate). Send to `misc.`.
4. Else → no effective key. Send to `misc.`.

Then, when there IS an effective key:

- Call Workplus `get_issue` on the key; cache the returned `title` and `type`.
- `type == "BUG"` → `fix.` under that issue.
- `type == "FEATURE"` → `feat.` under that issue.
- Any other type (rare — e.g. `TASK`) → treat as `FEATURE` for layout purposes.

This rule is intentionally simple: **Workplus issue type owns the
section choice**. A DSM-169641 cleanup that ships seven `chore` MRs
is a bug fix because the issue says so, not because any individual
commit says `fix(...)`. Conversely, an MR with `fix:` commit title
referencing a FEATURE issue goes to `feat.` — commit type is
irrelevant to section selection.

`fix.` is always flat (no group headings). Workplus-title group
headings appear only in `feat.`.
````

- [ ] **Step 6.2: Read back and verify**

```bash
sed -n '246,285p' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: the new effective-key procedure (4 numbered cases), then the BUG/FEATURE routing, then the fix.-is-flat sentence.

- [ ] **Step 6.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): classification falls back to repo_issue_map when no Ref: trailer"
```

---

## Task 7: Weekly Step 5 — same-title dedup respects issue groups

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` "Same-title MR dedup (universal)" subsection (lines 294–313)

**Why:** Today's dedup unconditionally pulls MRs out of any group. New rule keeps them inside the group when they all ref the same issue.

- [ ] **Step 7.1: Replace the Same-title MR dedup block**

Lines 294–313 currently:

```
### Same-title MR dedup (universal)

After classification (above) but before composing the draft, scan MRs across `fix.`, `feat.`, and `inbound.` for exact-title duplicates.

Procedure:

1. Group MRs by exact `title` string.
2. If 2+ MRs share a title, the cluster collapses into one bullet:
   - Pull the cluster MRs out of any Workplus-issue grouping (they no longer participate in the `fix.` / `feat.` per-issue layout).
   - Render the cluster as one top-level bullet inside its section:
     ```
     - <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...
     ```
   - Pair each MR with its own `Ref:` issue when present. If an MR has no `Ref:` trailer, drop only the `/ [KEY](url)` segment for that one entry.
   - Order MRs by `merged_at` ascending (master / earliest first; backports follow).
3. Single MRs (no duplicate title) keep their existing flat shape:
   - With `Ref:`: `[mr-title](mr-url) / [KEY](issue-url)`
   - Without `Ref:`: `[mr-title](mr-url)`

The dedup bullet always sits at its section's top level — never nested under a Workplus-issue heading. This means a `fix.` section that previously contained two single-MR Workplus groups with the same title now shows one collapsed bullet instead.
```

Replace with:

````markdown
### Same-title MR dedup (universal)

After classification (above) but before composing the draft, scan MRs across `fix.`, `feat.`, and `inbound.` for exact-title duplicates.

Procedure:

1. Group MRs by exact `title` string.
2. If 2+ MRs share a title, the cluster collapses into **one** bullet.
   The bullet's position depends on the cluster's effective-issue
   distribution:
   - **All cluster MRs share the same effective issue AND that issue
     has a group heading** (the `feat.` section will render a
     Workplus-title heading because the issue holds ≥2 MRs total,
     including or excluding the dedup'd ones — count the unique MR
     count under the issue): render the dedup'd cluster as **one
     indented bullet inside the group**, with no per-MR `/ [KEY](url)`
     segments (the group heading already carries the issue):

     ```
     - <Workplus-title> - ([<KEY>](<issue-url>))
     	- [other-mr-title](url): description
     	- <dedup-title> — [!N1](mr-url)、[!N2](mr-url)
     ```

   - **Cluster MRs reference different issues** (or some have no
     effective issue): render as one **flat top-level bullet** in the
     section, pairing each MR with its own issue ref:

     ```
     - <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...
     ```

     Drop the `/ [KEY](url)` segment for entries whose MR has no
     effective issue.

   - In both cases, order MRs by `merged_at` ascending (master /
     earliest first; backports follow).
3. Single MRs (no duplicate title) keep their existing flat shape:
   - With effective issue: `[mr-title](mr-url) / [KEY](issue-url)`
   - Without: `[mr-title](mr-url)`

The new in-group rule fixes the case where `fix(renderer): route
no-app desktop request through AllChunks` was rendered as a flat
bullet beside the `NextGen-Web-Core` group even though both MRs
ref'd DSM-167678 — it now sits inside the group as one indented
dedup bullet.
````

- [ ] **Step 7.2: Read back and verify**

```bash
sed -n '294,340p' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: dedup section has two clear branches (in-group vs flat) and concrete examples.

- [ ] **Step 7.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): same-title dedup keeps cluster inside group when all MRs share issue"
```

---

## Task 8: Weekly Step 5b — vault-only entries

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` — insert a new "Step 5b" subsection between Step 5 (Same-title dedup ends around line 313) and Step 6 (line 315).

**Why:** When a repo has vault Summaries this week but no merged MR, and the repo is in `repo_issue_map`, surface the work in `feat.` / `fix.` under the Workplus issue heading (per spec §8).

- [ ] **Step 8.1: Insert the new step**

Immediately before `## Step 6: Generate Draft` (currently line 315), insert:

````markdown
## Step 5b: Vault-only Entries

After Step 5 classification + dedup completes (and before Step 6
draft generation), surface Workplus-tracked work that has Summaries
this week but no merged MR.

Procedure:

1. Collect the set of effective issue keys already attributed to
   MRs in `fix.` / `feat.` (call this `mr_covered_issues`).
2. For each `(repo, issue_key)` pair derived from this week's
   Summary files:
   - Skip if `issue_key` is absent / null (the Summary covers
     off-topic / general maintenance work — it falls through to
     `misc.` aggregation, same as repos not in the map).
   - Skip if `issue_key` is already in `mr_covered_issues` — the
     MR-derived entry already represents this work, and Step 4's
     issue-aware join has already merged the Summary's body into
     that MR's description.
3. Group the surviving Summaries by `issue_key`.
4. For each `issue_key`:
   - `title, type = workplus_get_issue(issue_key)`.
   - Section = `feat.` if `type == FEATURE`, else `fix.`.
   - Compose a one-line description ≤60 characters, derived from
     the aggregated body prose of all Summaries in this group.
     Style: outcome-focused ("做了什麼"), not session-by-session
     log. Drop file paths, test counts, benchmark numbers unless
     they're the punchline.
   - Emit under the chosen section as:

     ```
     - <Workplus-title> - ([<KEY>](<issue-url>)): <description>
     ```

     Apply the same backtick-escape rule as group headings: if
     `<title>` starts with `[` or contains `][`, wrap in backticks.

5. Summaries whose `issue_key` is null (or whose repo is not in
   `repo_issue_map`) flow through to `misc.` aggregation (Step 6
   handles that, but they're collected here as the pool from
   which misc. draws vault-only bullets).

The vault-only bullet form (`<title> - ([KEY](url)): description`)
co-exists with the MR-group form (`<title> - ([KEY](url))` with
indented MR children) in the same section. They're visually
distinct: vault-only ends with `: description`, MR-group ends with
`)` followed by nested bullets.
````

- [ ] **Step 8.2: Read back and verify**

```bash
grep -n "^## Step\|^### " /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: `## Step 5b: Vault-only Entries` between Step 5's same-title dedup and `## Step 6: Generate Draft`.

- [ ] **Step 8.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): Step 5b surfaces vault-only progress under Workplus title"
```

---

## Task 9: draft-template.md — description length budgets

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md`

**Why:** Spec §1 caps descriptions at 5 surfaces. The template is the document Step 6 loads to compose output; the budgets must live there.

- [ ] **Step 9.1: Insert a "Description budgets" subsection after Base principles**

After the "## Base principles" block (ends around line 21), insert a new subsection:

````markdown
## Description budgets

The weekly is consumed by team meeting attendees who skim, not by
vault readers who want depth. Keep descriptions short. Hard ceilings
per surface:

| Surface | Cap | Style |
|---|---|---|
| `feat.` group-MR description | ≤40 chars (Chinese characters or English words counted as 1 each) | "做了什麼" — outcome only. No file paths, no test counts, no benchmark numbers unless they're the punchline. |
| `feat.` / `fix.` vault-only entry description | ≤60 chars | One sentence summarising the issue's progress this week. |
| `inbound.` mail | ≤30 chars after `<subject>: ` | `topic → 我的回應` form. Drop investigation steps, root-cause walkthroughs. |
| `inbound.` wit | ≤60 chars after `: ` | Main answer only. Drop follow-up details and stretch-goal additions. |
| `inbound.` CSS | ≤60 chars after `: ` | Three-segment `symptom → root cause → response` still applies; just keep each segment short. |
| `inbound.` chat | ≤60 chars after `: ` | One-clause `topic → 我的貢獻`. |
| `misc.` per-project | ≤10 chars short tag + MR link, OR a short prose summary when no MR exists (no link in that case). |

When a session genuinely needs more, prefer a sub-bullet under the
MR / group heading rather than blowing the cap on the main line.
````

- [ ] **Step 9.2: Read back and verify**

```bash
grep -n "^## " /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md | head
```

Expected: `## Description budgets` appears between `## Base principles` and the next major section (`## Top-level structure`).

- [ ] **Step 9.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "docs(weekly): cap descriptions per surface in draft-template"
```

---

## Task 10: draft-template.md — chat / mail bracket reshape

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md` — the `inbound.` block (lines 79–114) and the worked example (line 154–155).

**Why:** Spec §2 — `[mail: subject]:` collides with GFM reference-link-definition. Reshape so the bracket holds only the source tag.

- [ ] **Step 10.1: Replace the `inbound.` shapes block (lines 79–93)**

Current:

```
```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...   ← same-title dedup
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat: <channel-name>]: topic → 我的貢獻
	- [chat: `@username`]: topic → 我的貢獻
	- [chat: `@user_a`, `@user_b`]: topic → 我的貢獻
	- [mail: <subject>]: topic → 我的回應
	- [mail: <subject>] (`@username`): topic → 我的回應
```
```

Replace with:

```
```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...   ← same-title dedup
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat] <channel-name>: topic → 我的貢獻
	- [chat] `@username`: topic → 我的貢獻
	- [chat] `@user_a`、`@user_b`: topic → 我的貢獻
	- [mail] <subject>: topic → 我的回應
	- [mail] <subject> (`@username`): topic → 我的回應
```
```

- [ ] **Step 10.2: Update the chat / mail rule paragraphs (lines 104–111)**

Replace the chat sub-bullets (currently `[chat: <channel-name>]: topic → 我的貢獻` etc.) with:

```markdown
  - Public channel (`channel_name != ""`): `` [chat] <channel-name>: topic → 我的貢獻 ``.
  - 1:1 DM (one non-self participant): `` [chat] `@username`: topic → 我的貢獻 ``.
  - Group DM with 2 other participants: `` [chat] `@user_a`、`@user_b`: topic → 我的貢獻 ``.
  - Group DM with 3 other participants: `` [chat] `@user_a`、`@user_b`、`@user_c`: topic → 我的貢獻 ``.
  - 4+ other participants: `` [chat] DM: topic → 我的貢獻 `` (fall back).
```

And the mail sub-bullets:

```markdown
  - 1-on-1 thread (one non-self address across all messages): `` [mail] <subject> (`@username`): topic → 我的回應 ``.
  - Multi-recipient / mailing list (2+ non-self addresses): `` [mail] <subject>: topic → 我的回應 ``.
```

- [ ] **Step 10.3: Add a rationale note under the chat/mail rules**

After the username-backticks bullet (line 112), insert:

```markdown
- **Why `[chat]` / `[mail]` instead of `[chat: ...]` / `[mail: ...]`?** GFM
  treats `[label]: <text>` as a reference-link-definition (where
  `<text>` is interpreted as a URL + optional title). When the
  bracket contains both the tag *and* the subject, the trailing `:`
  triggers that parser and the bullet renders mangled. Putting only
  the source tag inside the bracket keeps the `]:` sequence outside
  the bracket, where it parses cleanly as inline text.
```

- [ ] **Step 10.4: Update the worked example (lines 154–155)**

Replace:

```
	- [chat: WIT]: nextwebd routing for /sharing → confirmed exact-match upstream wiring, pointed to libsynow3!263
	- [mail: [Bad Version] DSM v120060 patch bad (master)]: patch bad on master → identified offending commit, replied with fix sha and rebuild scope
```

With:

```
	- [chat] WIT: nextwebd routing for /sharing → confirmed exact-match upstream wiring, pointed to libsynow3!263
	- [mail] [Bad Version] DSM v120060 patch bad (master): patch bad on master → identified offending commit, replied with fix sha and rebuild scope
```

- [ ] **Step 10.5: Read back and verify**

```bash
grep -nE "\[chat:|\[mail:" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md
```

Expected: **no matches**. All `[chat: ...]` / `[mail: ...]` rewritten.

- [ ] **Step 10.6: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "fix(weekly): reshape chat/mail brackets to avoid GFM reference-link-definition collision"
```

---

## Task 11: draft-template.md — chat same-topic dedup rule

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md` — the ChatPlus rules paragraph (around lines 103–108 after T10's edits).

**Why:** Spec §3 — when multiple chat threads cover the same topic (LLM judgment), collapse to one bullet listing all participants.

- [ ] **Step 11.1: Insert the same-topic dedup rule**

After the "Group DM with 3 other participants" bullet (added by T10), and before "4+ other participants", insert a new top-level bullet under the ChatPlus rules paragraph:

```markdown
- **Same-topic dedup across threads**: when 2+ chat threads cover
  the same topic (judged by thread subject — e.g. multiple
  conversations about the same CVE, the same MR, the same feature),
  collapse them into one bullet listing all participants:

  ```
  - [chat] `@user_a`、`@user_b`: <topic> → 我的貢獻
  ```

  The order of usernames follows the chronological order of when
  each thread started. The contribution clause merges the
  user-facing answer across threads — don't repeat the same
  technical point twice. Validation-only / acknowledgement-only
  threads stay dropped (substance filter from Source F).
```

- [ ] **Step 11.2: Read back and verify**

```bash
grep -n "Same-topic dedup" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md
```

Expected: one match.

- [ ] **Step 11.3: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "docs(weekly): document same-topic chat thread dedup rule"
```

---

## Task 12: draft-template.md — same-title dedup respects group + vault-only example

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md` — the "Same-title MR dedup (universal)" section (lines 166–199) AND the `feat.` worked example.

**Why:** Mirror T7's SKILL.md change here, plus add a worked example of the new vault-only `feat.` entry shape (T8).

- [ ] **Step 12.1: Update the Same-title dedup section to add the in-group branch**

Replace the bullets under "Rules:" (lines 173–179):

```markdown
- Plain-text title (not a link); each MR remains individually clickable.
- Pair each MR with its own `Ref:` issue when present. If an MR has no `Ref:` trailer, drop only the `/ [KEY](url)` segment for that entry.
- Order MRs by `merged_at` ascending — master / earliest first; backports follow.
- The dedup bullet sits at the section's top level. MRs that participate in dedup are pulled out of any Workplus-issue group they would otherwise belong to.
- Single-MR cases (no duplicate title) are not affected — they keep `[title](url)` (with `/ [KEY](url)` if applicable).
```

With:

```markdown
- Plain-text title (not a link); each MR remains individually clickable.
- **Placement depends on issue distribution**:
  - All cluster MRs share the same effective issue AND that issue
    has a group heading → the dedup bullet sits **indented inside
    the group**, with no per-MR `/ [KEY](url)` segments (the group
    heading already carries the issue).
  - Cluster MRs reference different issues (or some have no
    effective issue) → the dedup bullet sits **flat at the section's
    top level**, with each MR paired to its own `/ [KEY](url)` (drop
    the segment when the MR has no effective issue).
- Order MRs by `merged_at` ascending — master / earliest first; backports follow.
- Single-MR cases (no duplicate title) are not affected — they keep `[title](url)` (with `/ [KEY](url)` if applicable).
```

- [ ] **Step 12.2: Add a worked example for in-group dedup**

After the existing "Worked example (`fix.` group with cross-issue cherry-picks):" block (around line 196), append:

````markdown
Worked example (`feat.` group with same-issue dedup pulled inside):

```
- feat.
	- NextGen-Web-Core - ([DSM-167678](https://workplus.synology.inc/key/DSM/issues/167678))
		- [fix(vite): make AppId→chunk lookup 1-to-1](url): 加 schema version + 1-to-1 lookup 修白屏
		- [revert(vite): drop ... template slot](url): importmap 必須最先 fetch、slot 害 module 被 ignore
		- [feat(vite): add AllChunks tag for ...](url): 加 AllChunks tag 處理 no-app desktop CSS
		- fix(renderer): route no-app desktop request through AllChunks — [!337](url)、[!20](url)
```

The last bullet is a same-title dedup (`!337` and `!20` both titled
"fix(renderer): route no-app desktop request through AllChunks"),
indented inside the NextGen-Web-Core group because both MRs ref
DSM-167678. The per-MR `/ [DSM-167678](url)` segments are dropped
since the group heading carries the issue.
````

- [ ] **Step 12.3: Add a "vault-only entry" shape to the `feat.` / `fix.` rules**

In the "## `fix.` and `feat.` — grouped by Workplus issue" section, after the "Multiple MRs per issue → group heading + indented bullets" block (around line 66), insert:

````markdown
### Vault-only entry (no MR this week)

When a repo in `weekly.repo_issue_map` has Summary entries this week
but no merged MR ref'ing the issue, the weekly emits a one-line
"vault-only" bullet under `feat.` (if Workplus type is FEATURE) or
`fix.` (if BUG). The format extends the group-heading form with a
trailing `: description`:

```
- feat.
	- [webapi] morpheus: webapi http server framework - ([DSM-172916](url)): prefork worker SIGUSR1 死鎖加 setup_graceful_drain 修
```

Rules:
- Same backtick-escape applies as for group headings — wrap the
  title in backticks when it starts with `[` or contains `][`.
- Description budget: ≤60 chars (see Description budgets).
- The vault-only bullet co-exists with the MR-group form; visually
  distinct by the trailing `: description`.
- See `cortex-weekly` Step 5b for when this shape is emitted.
````

- [ ] **Step 12.4: Read back and verify**

```bash
grep -nE "Vault-only entry|fix\(renderer\): route no-app desktop request through AllChunks" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md
```

Expected: the new "Vault-only entry" subsection and the worked-example dedup line both appear.

- [ ] **Step 12.5: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "docs(weekly): same-title dedup placement rules + vault-only feat. entry shape"
```

---

## Task 13: End-to-end verification on 2026-05-22 data

**Files:**
- No edits expected. If divergences are found, this task spawns follow-up commits against the relevant SKILL.md / template file.

**Why:** This is the integration test. Re-run the weekly skill with the same 2026-05-22 inputs and compare against the spec's "After" excerpt (`docs/specs/2026-05-22-weekly-skill-revision-design.md` final section).

- [ ] **Step 13.1: Add `morpheus → DSM-172916` to test config**

The user's `~/.cortex/config.json` doesn't yet have `repo_issue_map`. Before re-running, ensure it does — but **do not** edit the user's live config in this plan. Instead, document the expected entry in the verification report:

```json
"weekly": {
  ...,
  "repo_issue_map": {
    "morpheus": ["DSM-172916"]
  }
}
```

- [ ] **Step 13.2: Re-run weekly for 2026-05-22**

```bash
# In Claude Code session:
/cortex:weekly 2026-W21
```

(Or whatever ISO-week arg corresponds to 2026-05-22 — let the skill resolve it.)

- [ ] **Step 13.3: Compare output to the spec's "After" excerpt**

Open both side by side:

```bash
diff <(sed -n '/^### After/,/^## Implementation order/p' /synosrc/misc/cortex/docs/specs/2026-05-22-weekly-skill-revision-design.md) /synosrc/cortex/Weekly/2026/2026-05-22.md
```

Expected divergences are OK if they're cosmetic (whitespace, exact wording of ≤40 char descriptions). Structural divergences (a section missing, wrong nesting, `[mail: ...]:` still showing up, morpheus still in `misc.`) are bugs — file a follow-up TODO and patch the relevant skill section.

- [ ] **Step 13.4: Write a short verification note**

Append a "Verification" section to `docs/specs/2026-05-22-weekly-skill-revision-design.md` summarising what matched / what diverged. Keep it under 30 lines.

- [ ] **Step 13.5: Commit the verification note** (only if Step 13.4 actually wrote something)

```bash
cd /synosrc/misc/cortex
git add docs/specs/2026-05-22-weekly-skill-revision-design.md
git commit -m "docs(spec): record 2026-05-22 verification of weekly skill revision"
```

---

## Task 14: Version bump + changelog

**Files:**
- Modify: `CHANGELOG.md`
- Modify: whatever file holds the plugin version (`plugin.json` or `package.json` — check)

**Why:** The cortex plugin uses semver via the changelog (`0.11.1` is the latest entry per session start). This is a non-trivial behaviour change for weekly + distill; warrants a minor bump.

- [ ] **Step 14.1: Determine current version**

```bash
grep -m1 "^## " /synosrc/misc/cortex/CHANGELOG.md
```

Expected: latest line like `## 0.11.1 — 2026-...`.

- [ ] **Step 14.2: Find the version-bearing manifest file**

```bash
grep -rln '"version"' /synosrc/misc/cortex/ --include='*.json' | head
```

Expected: probably `plugin.json` or `package.json` at the repo root.

- [ ] **Step 14.3: Bump version (minor → e.g. 0.12.0)**

Edit the version field in the manifest. Reason: this revision adds a new config field (`repo_issue_map`), a new distill step (5.6), and a new weekly step (5b) — minor-version behaviour additions.

- [ ] **Step 14.4: Add a changelog entry**

Prepend to `CHANGELOG.md` (after the title, before the previous entry):

````markdown
## 0.12.0 — 2026-05-22

Weekly skill revision: trim for team-meeting paste, fix markdown
rendering, surface vault-only progress.

- **Config**: new `weekly.repo_issue_map` field (1:N repo → Workplus
  issue mapping). Backward compatible — absent = no change in
  behaviour.
- **Distill**: new Step 5.6 judges which mapped issue a Raw belongs to
  and writes `issue:` into Summary frontmatter.
- **Weekly**:
  - Source A reads `issue:`.
  - Step 4 prefers issue-aware MR ↔ Summary join, falls back to
    repo + date.
  - Step 5 classification: `repo_issue_map` is a Ref: fallback;
    commit type explicitly does not decide section.
  - Same-title MR dedup keeps cluster indented inside the group when
    all MRs share the issue.
  - New Step 5b surfaces vault-only progress as
    `<Workplus-title> - ([KEY](url)): <one-line>` in `feat.` / `fix.`.
- **Draft template**:
  - Per-surface description budgets (`feat.` group-MR ≤40, `misc.`
    tag ≤10, `inbound.` mail ≤30, others ≤60).
  - `[chat]` / `[mail]` brackets carry only the source tag; subject
    moves outside. Fixes GFM reference-link-definition collision.
  - Same-topic chat thread dedup rule documented.

See `docs/specs/2026-05-22-weekly-skill-revision-design.md` for
rationale and `docs/plans/2026-05-22-weekly-skill-revision.md` for
the per-task implementation history.
````

- [ ] **Step 14.5: Commit**

```bash
cd /synosrc/misc/cortex
git add CHANGELOG.md plugin.json   # or whichever manifest
git commit -m "chore: bump version to 0.12.0 — weekly skill revision"
```

---

## Self-Review (post-write)

Run through these checks before handing off to executing-plans:

1. **Spec coverage** — every decision in the spec has at least one task:
   - §1 Description budgets → T9 (budgets) + T11 (chat dedup note) + T12 (template examples).
   - §2 chat/mail bracket reshape → T10.
   - §3 chat same-topic dedup → T11.
   - §4 same-title dedup respects group → T7 (skill) + T12 (template).
   - §5 Classification normalisation → T6.
   - §6 `repo_issue_map` → T1 (genesis docs) + T6 (weekly fallback).
   - §7 Distill per-Summary `issue:` → T2 (schema) + T3 (Step 5.6).
   - §8 Weekly Step 5b → T8 (skill) + T12 (template vault-only example).
   - §9 Step 4 issue-aware join → T5.
   - Migration / backward compat → covered implicitly (all fields optional, all fallbacks documented).

2. **Placeholder scan** — no TBDs, TODOs, "implement later", "appropriate error handling", or unspecific stubs.

3. **Type / wording consistency**:
   - `repo_issue_map` (snake_case) used consistently across T1, T2, T3, T6, T8.
   - `issue:` (lowercase, no prefix) used consistently as the Summary frontmatter field name.
   - "effective issue key" introduced in T6 is referenced (without redefinition) by T7 and T8 — accepting that as a local term inside the weekly skill body.
   - "vault-only" used consistently to describe Summary-but-no-MR cases.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-05-22-weekly-skill-revision.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
