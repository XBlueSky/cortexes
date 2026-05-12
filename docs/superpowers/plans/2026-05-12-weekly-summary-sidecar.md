# Weekly Summary Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `cortex-weekly` Source A from reading full Raw bodies to reading per-Raw summary sidecars, written by `cortex-distill` into a new top-level `Summary/` vault directory.

**Architecture:** `cortex-distill` gains a Step 5.5 that writes a small prose-only sidecar file per processed Raw (mirroring Raw's date tree under `Summary/`). `cortex-weekly` Source A globs `Summary/` instead of `Raw/`, joins MRs to summaries by repo+date instead of URL string matching. Raw remains immutable. No code — both deliverables are markdown SKILL.md edits.

**Tech Stack:** Markdown / YAML frontmatter. The skills are LLM-consumed instruction documents; "tests" are spec-coverage and reading correctness checks, not pytest.

**Spec:** `docs/superpowers/specs/2026-05-12-weekly-summary-sidecar-design.md`

---

## File Structure

Files modified:
- `skills/cortex-distill/SKILL.md` — insert Step 5.5 between existing Step 5 and Step 6; update Step 8 commit list
- `skills/cortex-weekly/SKILL.md` — rewrite Source A (lines 63–76); update Step 2 to mention summary precondition + fallback; rewrite Step 4 dedup to repo+date join
- `CHANGELOG.md` — add 0.11.0 entry
- `.claude-plugin/plugin.json` — bump version to 0.11.0

No new files in the repo. The `Summary/` directory itself is created in the user's vault at runtime by distill — not committed to this repo.

---

### Task 1: Add Step 5.5 (Write Summary File) to cortex-distill

**Files:**
- Modify: `skills/cortex-distill/SKILL.md` — insert new section between current Step 5 ("Mark Raw as Processed", ends around line 130) and current Step 6 ("Update Index (only for `new` outcome)", begins around line 132).

- [ ] **Step 1: Read the current Step 5 / Step 6 boundary**

Read `skills/cortex-distill/SKILL.md` to locate the exact `## Step 6: Update Index (only for \`new\` outcome)` heading. Verify Step 5 ends with the marker table and that no Step 5.5 currently exists.

- [ ] **Step 2: Insert the new Step 5.5 section**

Use the Edit tool. `old_string` is the `## Step 6: Update Index (only for \`new\` outcome)` heading (with one line of context above to keep uniqueness). `new_string` prepends the following section before that heading, followed by a blank line and the original heading.

New section content:

```markdown
## Step 5.5: Write Summary File

For **every** Raw processed in this run — regardless of outcome (`new`,
`pending-merge`, `skip-routine`, `no-insight`) — write a summary sidecar
file. The summary is consumed by `cortex-weekly` Source A; it is NOT
indexed by `cortex-vec` and NOT listed in `_index.md`.

### 5.5.1 Compose the summary

The summary is a prose-only paragraph describing what the session was
about — work done, what shipped, non-obvious findings. Guideline:

- 1–5 sentences, roughly 60–300 characters (soft target; a session that
  genuinely needs 400 characters to be coherent gets 400).
- **Do NOT** enumerate commits, MR URLs, or issue keys. Those are
  GitLab's canonical territory (`cortex-weekly` Source B). Weekly joins
  MRs to summaries by repo + date, not by URL-string matching inside
  the summary prose.
- **Do NOT** repeat deep-dive content that this distill run wrote into
  Notes/Projects. Summary is "session view"; Notes/Projects is
  "topic view".
- For sessions with no commits / no shipped output, describe honestly
  ("探索 X 的行為、未產出代碼" / "reviewed Y MR, no self-authored
  commits").
- For `no-insight` outcome: still produce a summary. Weekly cares about
  sessions that didn't yield insights but still represent work hours.

### 5.5.2 Compose the frontmatter

Fixed 3-field schema, no other fields:

```yaml
---
raw: <vault-relative path to the source Raw file>
repo: <value from Raw frontmatter `repo:` field, or `(none)` if absent>
distilled: <today, YYYY-MM-DD>
---
```

### 5.5.3 Write the sidecar file

Destination path: `<vault_path>/Summary/YYYY/MM/DD/<same-filename-as-Raw>.md`
(mirror Raw's date tree, identical filename).

Use the Write tool. If the file already exists (re-distill case),
**overwrite** it — no merge, no append. The Write tool's overwrite
semantics are the intended behavior here.

Create parent directories as needed (the Write tool handles this).

### 5.5.4 Stage for commit

The sidecar file is added to git in Step 8's `git add` list (see Step 8).
No extra commit here.
```

After this insertion, the section ordering becomes:

```
Step 5: Mark Raw as Processed
Step 5.5: Write Summary File         ← NEW
Step 6: Update Index (only for `new` outcome)
Step 7: Append Log Entry
Step 8: Commit
Step 9: Ask — Broadcast Now?
```

- [ ] **Step 3: Verify the inserted section**

Read back `skills/cortex-distill/SKILL.md` starting from where Step 5's marker table ends. Confirm:

1. Step 5.5 heading is present and properly formatted.
2. Sub-sections 5.5.1 through 5.5.4 are in order.
3. Step 6 heading immediately follows Step 5.5.4 (with one blank line separating).
4. No duplicate Step 5 or Step 5.5 was created.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(distill): write Summary/ sidecar per processed Raw

New Step 5.5 writes a prose-only summary file at
Summary/YYYY/MM/DD/<filename>.md for every Raw distill processes
(regardless of outcome). Sidecar has 3-field frontmatter (raw, repo,
distilled) and a 1-5 sentence body. Consumed by cortex-weekly Source A
in a follow-up commit; not indexed by cortex-vec; not listed in
_index.md.

Ref: docs/superpowers/specs/2026-05-12-weekly-summary-sidecar-design.md

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 2: Update cortex-distill Step 8 commit list

**Files:**
- Modify: `skills/cortex-distill/SKILL.md` — Step 8's `git add` command (currently `git add Raw/ Notes/ Projects/ _index.md log.md`)

- [ ] **Step 1: Locate Step 8's git add line**

Read the Step 8 section. Confirm current content:

```bash
cd <vault>
git add Raw/ Notes/ Projects/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

- [ ] **Step 2: Replace the git add line to include Summary/**

Edit tool. `old_string`:

```
git add Raw/ Notes/ Projects/ _index.md log.md
```

`new_string`:

```
git add Raw/ Notes/ Projects/ Summary/ _index.md log.md
```

- [ ] **Step 3: Verify**

Read back Step 8. Confirm `Summary/` is between `Projects/` and `_index.md` in the `git add` argument list.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-distill/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(distill): stage Summary/ in batch commit

Step 8's git add now includes Summary/ so sidecar files written in
Step 5.5 land in the same atomic distill commit.

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 3: Rewrite cortex-weekly Source A to read Summary/

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` — Source A section (currently lines 63–76, `### Source A — Raw/`)

- [ ] **Step 1: Locate the current Source A block**

Read `skills/cortex-weekly/SKILL.md` lines 60–80. Confirm the section starts with `### Source A — Raw/` and ends just before `### Source B — GitLab MRs authored by the user`.

- [ ] **Step 2: Replace Source A content**

Edit tool. `old_string` is the entire current Source A section, from `### Source A — Raw/` through the blank line before `### Source B`. `new_string`:

```markdown
### Source A — Summary/

Glob `<vault_path>/Summary/YYYY/MM/DD/*.md` for every date the range
touches (start Friday through end Friday, inclusive — typically 8 days).

Summary filenames mirror Raw filenames exactly (`HHMMSS_session_<repo>.md`),
so the boundary-Friday HHMMSS filter ports verbatim:

- **Start Friday:** keep files where `HHMMSS >= "110000"`
- **End Friday:** keep files where `HHMMSS < "110000"`
- **Days in between:** keep all files

(`110000` = cutoff hour 11 as `HHMMSS`. Regenerate this literal if
`weekly.cutoff.hour` changes.)

For each surviving Summary file, read frontmatter + body:

- `repo:` from frontmatter → the session's target repo (use directly;
  do NOT open the corresponding Raw file).
- Body prose → the session description.

**Weekly never opens the corresponding Raw file.** The Summary is a
self-contained record for weekly's purposes; Raw remains immutable
source. If repo or other context is missing from the Summary, that is
a bug in distill's Step 5.5, not a reason to fall back to reading Raw.

#### Fallback — Raw with no Summary

Should not happen, because Step 2 (Run Distill) ensures every pending
Raw is distilled (and therefore has a Summary written) before Source A
runs.

If a Raw in the week's window still has no corresponding Summary file
after Step 2:

1. Collect the list of orphan Raws (Raw files whose mirrored Summary
   path does not exist).
2. Tell the user: "N Raw files in this window have no Summary. Distill
   may have failed or been skipped. Resolve before continuing: (1)
   re-run distill on these files, or (2) explicitly opt to read full
   Raw bodies as a one-off."
3. Do **not** silently read the Raw body. Silent fallback hides
   pipeline bugs and defeats the token-savings purpose of this source.

```

- [ ] **Step 3: Verify**

Read back the new Source A section. Confirm:

1. Heading is `### Source A — Summary/` (not the old `### Source A — Raw/`).
2. Glob path is `<vault_path>/Summary/YYYY/MM/DD/*.md`.
3. HHMMSS filter rules are preserved unchanged.
4. The "Weekly never opens the corresponding Raw file" sentence is
   present.
5. The fallback subsection enumerates the three resolution steps.
6. Source B (next section) is unchanged and immediately follows.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(weekly): Source A reads Summary/ sidecars instead of Raw bodies

Source A now globs Summary/YYYY/MM/DD/*.md and reads each sidecar's
frontmatter (repo) and prose body (session description). Weekly never
opens the corresponding Raw file. Boundary-Friday HHMMSS filter ports
verbatim because Summary filenames mirror Raw filenames.

Orphan Raws (no Summary present after Step 2 distill) trigger a hard
prompt to the user — no silent fallback to reading Raw bodies, so
distill pipeline failures stay visible.

Ref: docs/superpowers/specs/2026-05-12-weekly-summary-sidecar-design.md

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 4: Update cortex-weekly Step 4 dedup to repo+date join

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` — Step 4 (`## Step 4: Merge and Deduplicate`), specifically the rule "For each GitLab MR: same URL in Raw → keep Raw's description; MR absent from Raw → add it".

- [ ] **Step 1: Locate Step 4**

Read `skills/cortex-weekly/SKILL.md` around the `## Step 4: Merge and Deduplicate` heading (currently around line 190). Confirm the numbered list contains the URL-based dedup rule as item 2:

```
2. For each GitLab MR: same URL in Raw → keep Raw's description; MR absent from Raw → add it
```

- [ ] **Step 2: Replace item 2 with the repo+date join rule**

Edit tool. `old_string`:

```
2. For each GitLab MR: same URL in Raw → keep Raw's description; MR absent from Raw → add it
```

`new_string`:

```
2. For each GitLab MR, join to Source A summaries by **repo + date**, not by URL string matching:
   - Find Summary files where `repo:` matches the MR's target repo AND the Summary's date is either the same date as the MR's `merged_at` or the immediately preceding date (to capture sessions that ran late and crossed midnight before the MR was merged the next morning).
   - Exactly one match → use that Summary's prose body as the MR's session-context description text in the weekly draft.
   - Multiple matches → choose the Summary whose `HHMMSS` is closest to the MR's `merged_at` timestamp. If still ambiguous, concatenate them, each as its own session contribution.
   - No match → the MR stands alone; commit title + Workplus issue title carry the description (same as the previous "MR absent from Raw" branch).

   Rationale: Summary prose intentionally does NOT enumerate MR URLs (see `cortex-distill` Step 5.5 guideline), so URL-string matching breaks. Repo + date is the structural replacement.
```

- [ ] **Step 3: Verify**

Read back the modified Step 4. Confirm:

1. Item 2 now describes the repo+date join with four bullets (exactly one / multiple / no match / rationale).
2. Items 1, 3, 4 (Raw entries as base, inbound items, ChatPlus/MailPlus cross-source dedup) are unchanged.
3. The phrase "same URL in Raw" no longer appears.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(weekly): Step 4 dedup joins MR↔Summary by repo+date

URL-string matching against Summary prose would break — Summary
guideline forbids enumerating MR URLs in the body. New rule joins
each GitLab MR to a Summary by matching `repo:` and a date window of
[merged_at - 1 day, merged_at]. Single match feeds the Summary prose
into the MR's bullet; multi-match picks closest HHMMSS or concatenates;
no match leaves the MR standalone.

Ref: docs/superpowers/specs/2026-05-12-weekly-summary-sidecar-design.md

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 5: Update cortex-weekly Step 2 (Run Distill) to mention summary precondition

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` — `## Step 2: Run Distill` section (around line 58)

- [ ] **Step 1: Locate Step 2**

Read the current Step 2 content:

```
## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files from the target week before compiling the report.
```

- [ ] **Step 2: Replace with the summary-aware version**

Edit tool. `old_string`:

```
## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files from the target week before compiling the report.
```

`new_string`:

```
## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files from the target week before compiling the report.

**Why this is a hard precondition for Source A:** Source A reads from `Summary/`, and a Summary file is only written as a side effect of distill (cortex-distill Step 5.5). Skipping Step 2 means Source A sees fewer sessions than actually happened. If distill fails or is skipped for any Raw, Source A surfaces those orphans explicitly and refuses to silently fall back to reading the Raw body.
```

- [ ] **Step 3: Verify**

Read back Step 2. Confirm the new "Why this is a hard precondition" paragraph follows the original sentence with one blank line between them.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(weekly): explain Step 2 as Source A's hard precondition

Source A now depends on Summary/ files that distill writes in its
Step 5.5. The note in Step 2 makes the dependency explicit so future
edits don't accidentally weaken or move the distill invocation.

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 6: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md` — add `## [0.11.0] - 2026-05-12` entry above the existing `## [0.10.3]` entry.

- [ ] **Step 1: Read the current CHANGELOG header**

Confirm the file starts with the header block (lines 1–6) followed by `## [0.10.3] - 2026-05-08`.

- [ ] **Step 2: Insert the new 0.11.0 entry**

Edit tool. `old_string`:

```
## [0.10.3] - 2026-05-08
```

`new_string`:

```
## [0.11.0] - 2026-05-12

### Added
- `cortex-distill` Step 5.5: writes a per-Raw summary sidecar at
  `Summary/YYYY/MM/DD/<filename>.md` for every processed Raw,
  regardless of outcome (`new`, `pending-merge`, `skip-routine`,
  `no-insight`). Sidecar has 3-field frontmatter (`raw`, `repo`,
  `distilled`) and a 1–5 sentence prose body. The body deliberately
  does NOT enumerate commits, MR URLs, or issue keys — those are
  GitLab's canonical territory.
- New top-level vault directory `Summary/` mirrors `Raw/`'s date
  tree. Tracked in git alongside Notes/Projects. Not indexed by
  `cortex-vec`, not listed in `_index.md` (it is `cortex-weekly`'s
  internal cache, not user-browsable content).

### Changed
- `cortex-weekly` Source A reads from `Summary/` instead of `Raw/`.
  Per-Raw token cost for the weekly compile drops by roughly the
  ratio between full Raw body size and the ~60–300 char summary.
  Boundary-Friday HHMMSS filter rules carry over unchanged (Summary
  filenames mirror Raw filenames exactly).
- `cortex-weekly` Step 4 dedup against GitLab MRs (Source B) now
  joins MR ↔ Summary by **repo + date** instead of URL-string
  matching inside Raw body. The date window is `[merged_at - 1 day,
  merged_at]` to capture sessions that ran late and crossed midnight
  before the MR was merged the next morning.
- `cortex-weekly` Step 2 (Run Distill) now documented as a hard
  precondition for Source A — if a Raw in the window has no
  corresponding Summary after Step 2 runs, weekly surfaces the
  orphan list to the user and does NOT silently fall back to reading
  the Raw body.

### Notes
- Raw remains immutable. This change adds an additional derived
  artifact (the sidecar), it does not modify any Raw content,
  frontmatter, or existing `<!-- distilled: ... -->` marker.
- No backfill: only Raws distilled after 0.11.0 ships get a Summary.
  Older Raws appearing in a weekly window will trigger the orphan
  prompt; resolution is to re-run distill on those specific files.
- `cortex-broadcast` and `cortex-query` are unaffected — both still
  read full Raw / Notes / Projects respectively.

## [0.10.3] - 2026-05-08
```

- [ ] **Step 3: Verify**

Read back CHANGELOG lines 1–60. Confirm `## [0.11.0] - 2026-05-12` appears between the header preamble and the `## [0.10.3]` entry, with all four subsections (Added / Changed / Notes — no Fixed since this is purely additive).

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add CHANGELOG.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(changelog): 0.11.0 — weekly summary sidecar

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 7: Bump plugin.json version to 0.11.0

**Files:**
- Modify: `.claude-plugin/plugin.json` — `"version": "0.10.3"` → `"version": "0.11.0"`

- [ ] **Step 1: Read current plugin.json**

Confirm current content:

```json
{
  "name": "cortex",
  "version": "0.10.3",
  "description": "Personal knowledge vault plugin — session recording, memory distillation, weekly reports, indexed retrieval",
  "author": {
    "name": "tonyhu",
    "email": "tonyhu@synology.com"
  }
}
```

- [ ] **Step 2: Replace version**

Edit tool. `old_string`: `"version": "0.10.3",`. `new_string`: `"version": "0.11.0",`.

- [ ] **Step 3: Verify**

Read back the file. Confirm version is `0.11.0` and no other field changed.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add .claude-plugin/plugin.json
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(plugin): bump version to 0.11.0 — weekly summary sidecar

Signed-off-by: tonyhu <tonyhu@synology.com>
EOF
)"
```

---

### Task 8: End-to-end sanity verification

**Files:** None modified. This task is a read-only verification pass to confirm the six committed changes hang together.

- [ ] **Step 1: Confirm cortex-distill section order**

Read `skills/cortex-distill/SKILL.md`. Grep for `## Step ` headings. Expected order:

```
## Step 1: Find Unprocessed Raw Files
## Step 2: Stage 1 — Has Insight
## Step 3: Stage 2 — Decide Placement
## Step 4: Create Refined Note
## Step 5: Mark Raw as Processed
## Step 5.5: Write Summary File
## Step 6: Update Index (only for `new` outcome)
## Step 7: Append Log Entry
## Step 8: Commit
## Step 9: Ask — Broadcast Now?
```

Command:

```bash
grep -n '^## Step' /synosrc/misc/cortex/skills/cortex-distill/SKILL.md
```

Expected: 10 lines in the order above.

- [ ] **Step 2: Confirm cortex-distill Step 8 git add list**

```bash
grep -A 1 'git add Raw/' /synosrc/misc/cortex/skills/cortex-distill/SKILL.md
```

Expected: line contains `git add Raw/ Notes/ Projects/ Summary/ _index.md log.md`.

- [ ] **Step 3: Confirm cortex-weekly Source A reads Summary/**

```bash
grep -n -E '^### Source [A-G]' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: Source A line reads `### Source A — Summary/` (not `Raw/`).

```bash
grep -c 'Weekly never opens the corresponding Raw file' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: `1`.

- [ ] **Step 4: Confirm cortex-weekly Step 4 dedup wording**

```bash
grep -c 'same URL in Raw' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: `0` (old wording gone).

```bash
grep -c 'join to Source A summaries by \*\*repo + date\*\*' /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md
```

Expected: `1`.

- [ ] **Step 5: Confirm version bump**

```bash
grep '"version"' /synosrc/misc/cortex/.claude-plugin/plugin.json
```

Expected: `"version": "0.11.0",`.

- [ ] **Step 6: Confirm CHANGELOG entry**

```bash
grep -A 1 '^## \[0\.11\.0\]' /synosrc/misc/cortex/CHANGELOG.md
```

Expected: heading present with date `2026-05-12`.

- [ ] **Step 7: Confirm clean git state**

```bash
cd /synosrc/misc/cortex && git status
```

Expected: working tree clean. All seven commits (Tasks 1–7) on the branch.

```bash
cd /synosrc/misc/cortex && git log --oneline -10
```

Expected: latest seven commits are the Task 1–7 commits in order, all signed off by tonyhu.

If any check fails, return to the corresponding Task and address the gap with a targeted edit + commit.

---

## Spec Coverage Self-Check

| Spec section | Task(s) |
|---|---|
| Goal — eliminate weekly double-read of Raw | 3, 5 |
| Sidecar (not append) decision | 1 (spec recap in inserted text) |
| File layout under `Summary/` mirroring `Raw/` | 1 (Step 5.5.3 path) |
| Summary frontmatter 3-field schema | 1 (Step 5.5.2) |
| Summary body prose-only, 60–300 chars soft target, no commits/MRs/refs | 1 (Step 5.5.1) |
| Summary written for ALL outcomes incl. no-insight | 1 (Step 5.5 opening paragraph) |
| Distill Step 5.5 insertion | 1 |
| Distill Step 8 staging Summary/ | 2 |
| Weekly Source A reads Summary/, never opens Raw | 3 |
| Boundary-Friday HHMMSS filter ports verbatim | 3 |
| Orphan-Raw fallback (hard prompt, no silent Raw read) | 3, 5 |
| Step 4 dedup repo+date join replacing URL-string matching | 4 |
| Date window: same day or immediately preceding | 4 |
| Step 2 documented as hard precondition for Source A | 5 |
| `Summary/` not indexed by cortex-vec, not in `_index.md` | 1 (Step 5.5 opening paragraph) |
| No retroactive backfill | 6 (Notes subsection) |
| Broadcast / query unaffected | 6 (Notes subsection) |
| Version bump | 7 |
| End-to-end verification | 8 |

All spec sections map to at least one task. No gaps.
