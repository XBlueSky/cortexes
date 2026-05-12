# Weekly Summary Sidecar — Design

**Date:** 2026-05-12
**Status:** Approved, pending implementation plan
**Scope:** `cortex-distill` skill, `cortex-weekly` skill, new top-level `Summary/` directory in the vault.

## Problem

`cortex-weekly` Source A globs `Raw/YYYY/MM/DD/*.md` for the target week and reads **each Raw file in full** to extract commits / discoveries / decisions / other work (`cortex-weekly/SKILL.md` L63–76). A typical week has 10–30 Raw files at a few KB each — tens to hundreds of KB pulled into context just for Source A. Most of that content is verbose session prose, command output, and exploratory dead-ends; the weekly compiler only needs to know "what was this session about" to compose its bullets.

`cortex-distill` already reads each Raw in full when it processes the pending queue, so the per-Raw read happens twice per week (once for distill, once for weekly). The distill pass currently emits a `<!-- distilled: ... -->` marker in Raw, but the marker only records outcome / target / dedup score — it does **not** capture a human-readable summary of the session.

## Goal

Eliminate weekly's double-read of Raw by having `cortex-distill` write a per-Raw summary at distill time, and having `cortex-weekly` Source A consume those summaries instead of Raw bodies.

Non-goals:
- No change to Raw content, structure, or frontmatter — Raw remains immutable source.
- No retroactive summary generation for historical Raws — summaries only exist for Raws distilled after this change ships.
- No change to `cortex-broadcast` (still reads full Raw — it needs original context).
- No change to `cortex-query` or `cortex-vec` (they operate on Notes/Projects, not Raw).
- No new index file, search tool, or embedding pipeline for summaries — summaries are weekly's internal cache, not user-browsable knowledge content.

## Architecture decision: sidecar, not appended block

Two candidate forms were considered:

**Rejected: append `<!-- weekly-summary: ... -->` block to Raw.** Same file as Raw, hidden from Obsidian preview, single-file simplicity. Rejected because it conflates source and derived artifact in one file: Raw is human-authored / LLM-read; summary is LLM-authored / Raw-derived. Keeping them in the same file means distill mutates Raw on every run beyond the existing one-line marker, which weakens the "Raw is immutable" invariant.

**Chosen: sidecar files under a new `Summary/` directory** mirroring `Raw/`'s date tree. Raw stays untouched beyond its existing distilled marker. Summary owns its own filesystem namespace, parallel to `Notes/`, `Projects/`, `Weekly/`.

## File layout

```
<vault>/
├── Raw/2026/05/12/143022_session_cortex.md       ← unchanged
├── Summary/2026/05/12/143022_session_cortex.md   ← NEW, written by distill
├── Notes/...                                      ← unchanged
├── Projects/...                                   ← unchanged
└── Weekly/...                                     ← unchanged
```

The mirror is exact: same date path, same filename. Raw ↔ Summary correspondence is encoded by the path, not by any cross-reference table.

## Summary file format

```markdown
---
raw: Raw/2026/05/12/143022_session_cortex.md
repo: cortex
distilled: 2026-05-12
---

修 cortex-vec dedup threshold 預設值。發現短 Notes 的 cosine 相似度
被誇大（高頻詞主導 vector），改用文長加權版本，預設門檻 0.45 → 0.55。
順便把 _index.md 兩個 orphan link 清掉。
```

**Frontmatter (fixed schema, 3 fields only):**
- `raw:` — vault-relative path back to the source Raw file. Audit / "I want to see the source".
- `repo:` — copied verbatim from the source Raw's `repo:` frontmatter (or `(none)` if Raw has none). Lets `cortex-weekly` resolve the session's repo without opening the Raw file.
- `distilled:` — date the summary was written, `YYYY-MM-DD`. Audit only.

No other fields. No `commits:`, `mrs:`, `refs:`, `outcome:`, etc. Those are either available canonically elsewhere (GitLab Source B for commits/MRs/refs) or live in the distilled marker on Raw (outcome).

**Body (free prose, no schema):**
- Soft target: 1–5 sentences, roughly 60–300 characters (Chinese or English). These are guidance for the distill agent, not hard limits — a session that genuinely needs 400 characters to be coherent gets 400.
- Describes "what this session was about" — work done, what shipped, non-obvious findings.
- **Do NOT** enumerate commits, MR URLs, or issue keys — those are GitLab's job. The weekly compiler will join MRs to summaries by repo + date, not by URL string matching inside the summary prose.
- **Do NOT** repeat the deep-dive content that distill already wrote into Notes/Projects. Summary is "session view"; Notes/Projects is "topic view".
- Sessions with no commits / no shipped output get described honestly: "explored X behavior, no code produced" / "reviewed Y MR, no self-authored commits".
- Sessions producing the `no-insight` distill outcome still get a summary — weekly cares about sessions that didn't yield insights but still represent work hours.

## `cortex-distill` changes

Insert a new **Step 5.5: Write Summary File**, after the existing Step 5 (Mark Raw as Processed) and before Step 6 (Update Index).

```
For every Raw processed in this run (regardless of outcome — new, pending-merge,
skip-routine, or no-insight):

1. Compose summary frontmatter:
   - raw: <vault-relative path to the Raw file>
   - repo: <value from Raw frontmatter `repo:` field, or `(none)`>
   - distilled: <today, YYYY-MM-DD>

2. Compose summary body per guideline above (1–5 sentences, 60–300 chars,
   prose, no bullets, no field enumeration).

3. Write to <vault>/Summary/YYYY/MM/DD/<same-filename-as-Raw>.md using the
   Write tool. Overwrite if the file already exists (re-distill case).

4. Stage the new/updated Summary file for commit.
```

Step 5 (Mark Raw as Processed) is unchanged — the `<!-- distilled: ... -->` marker on Raw remains the source of truth for the pending list (`grep -rL '<!-- distilled:'`). The summary sidecar is additive.

Step 8 (Commit) adds `Summary/` to the `git add` list:

```bash
git add Raw/ Notes/ Projects/ Summary/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

Re-distill semantics:
- The distilled marker on Raw is append-once (Edit tool replaces existing marker — current behavior preserved).
- The Summary file is **overwrite-on-rewrite** — Write tool replaces the entire file with the latest distill's content. There is no merge / append logic on the summary itself.

## `cortex-weekly` changes

### Source A rewrite (`cortex-weekly/SKILL.md` L63–76)

Current behavior: glob `Raw/YYYY/MM/DD/*.md`, read each file in full, extract commits / discoveries / decisions / other work.

New behavior:

1. Glob `Summary/YYYY/MM/DD/*.md` for every date the range touches (start Friday through end Friday).
2. Apply the existing HHMMSS boundary-Friday filter to the **filenames** (Summary filenames mirror Raw filenames, so the filter ports verbatim):
   - Start Friday: keep files where `HHMMSS >= "110000"`
   - End Friday: keep files where `HHMMSS < "110000"`
   - Days in between: keep all files
3. For each surviving Summary file: read it (frontmatter + body). Use `repo:` from frontmatter to know the session's repo; use the body prose as the session description.
4. Weekly never opens the corresponding Raw file. All Source A data — repo, description — comes from the Summary.

### Fallback: Raw with no Summary

Should not happen in normal operation, because Step 2 (Run Distill) at the start of weekly ensures every pending Raw is distilled (and therefore has a Summary written) before Source A runs.

If a Raw in the week's window still has no Summary after Step 2:

- Treat this as a pipeline failure, not a silent fallback.
- Weekly reports the list of orphan Raws to the user with the message: "N Raw files in this window have no Summary. Distill may have failed or been skipped. Resolve before continuing: (1) re-run distill on these files, or (2) explicitly opt to read full Raw bodies as a one-off."
- Do not silently read the Raw body. Silent fallback would hide pipeline bugs and defeat the token-savings purpose.

### Step 4 (Merge & Dedup) impact

Current Step 4 dedup against Source B (GitLab MRs) is described as: "same URL in Raw → keep Raw's description; MR absent from Raw → add it". This relies on the Raw body containing the MR URL as a string.

Summary bodies are explicitly forbidden from enumerating MR URLs (see "Summary file format" above), so URL-string matching breaks. Replace with a structural join:

- For each Source B MR, find Summary files where `repo:` matches the MR's target repo AND the Summary's date is either the same date as the MR's `merged_at` or the immediately preceding date (to capture sessions that ran late and crossed midnight before the MR was merged the next morning).
- If exactly one Summary matches: treat the Summary as the MR's "session context" — its prose body becomes the description text for the MR's bullet in the weekly draft (subject to the existing format rules in `references/draft-template.md`).
- If multiple Summaries match the same repo+date: weekly chooses the closest Summary by HHMMSS to the MR's merge timestamp, or, if ambiguous, concatenates them (each as its own session contribution).
- If no Summary matches: the MR stands alone — title + Workplus issue title carry the description, same as today's "MR absent from Raw" branch.

This is a semantic change worth flagging: weekly's dedup is now repo-and-time-based rather than URL-string-based. The trade-off is intentional — URL string matching was already brittle (Raws often paraphrased URLs or referenced MR numbers without full URLs), and pushing the join structure outside the prose keeps the summary body free to describe the session naturally.

## Vault-level boundaries

- `Summary/` is a new top-level vault directory, peer of `Raw/`, `Notes/`, `Projects/`, `Weekly/`.
- `Summary/` is tracked in git — not gitignored. Treated identically to `Notes/` and `Projects/` for backup / sync purposes.
- `Summary/` is **not** listed in `_index.md`. Index is for user-browsable knowledge content; summaries are weekly's internal cache. Listing them in the index would inflate it with hundreds of entries that have no standalone reading value.
- No new entries in `log.md` for summary writes — they piggyback on the existing distill log entry per Raw. Summary write is a side effect of distill, not a distinct operation.
- `cortex-vec` does NOT index `Summary/`. Summaries are by design redundant with Notes/Projects (which are indexed); indexing summaries would dilute search results.

## Migration / backfill

None. The change is forward-only:
- New distill runs write Summary files for the Raws they process.
- Old Raws that were distilled before this change has no corresponding Summary file.
- When weekly's window happens to include old Raws (e.g., the very first week after deployment), those Raws will trigger the fallback path described above. The user resolves them by re-running distill on those specific files (which is idempotent — the marker re-resolves to the same outcome, and the Summary file is freshly written).

Within a few weeks of the change shipping, the active weekly window will contain only Raws produced after deployment, and the fallback path will go cold.

## Rollback

If this design proves wrong:
1. Revert `cortex-weekly/SKILL.md` Source A to read Raw bodies.
2. Revert `cortex-distill/SKILL.md` to remove Step 5.5.
3. Existing `Summary/` files become dead — they can be left in place (harmless) or `rm -rf Summary/` removed. They do not interfere with any other vault operation.

No data loss, no migration unwind. The Raw layer was never modified by this design.

## Implementation surface

Files touched:
- `cortex-distill/SKILL.md` — add Step 5.5; update Step 8 commit list.
- `cortex-weekly/SKILL.md` — rewrite Source A (L63–76); update Step 4 dedup to use repo+date join; document the fallback behavior.

No code (cortex skills are markdown instructions). No new tools, no config schema changes, no `~/.cortex/config.json` keys.
