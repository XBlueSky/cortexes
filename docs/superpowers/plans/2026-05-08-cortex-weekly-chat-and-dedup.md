# cortex-weekly Chat/Mail @username + Same-Title MR Dedup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the `cortex-weekly` skill so DM threads attribute to `@username`, mail threads attribute to `@username` for 1-on-1 cases, and same-title MRs collapse into one bullet wherever they appear.

**Architecture:** Documentation-only change. The skill is a markdown spec read by an LLM at `/cortex:weekly` runtime — no executable code paths to refactor. Updates land in `skills/cortex-weekly/SKILL.md` (Source F / Source G / new sub-section after Step 5) and `skills/cortex-weekly/references/draft-template.md` (inbound shapes, chat rules, mail rules, new dedup section). Acceptance is a re-run of `/cortex:weekly` against the same week window, confirming the new shapes render.

**Tech Stack:** Markdown only. No build, no compile, no unit tests. Spec at `docs/superpowers/specs/2026-05-08-cortex-weekly-chat-and-dedup-design.md`.

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `skills/cortex-weekly/SKILL.md` | Modify | Top-level skill spec — Source F (ChatPlus), Source G (MailPlus), new "Same-title MR dedup" sub-section after Step 5. |
| `skills/cortex-weekly/references/draft-template.md` | Modify | Format reference loaded at draft-step — inbound shapes block, ChatPlus rules block, MailPlus rules block, new "Same-title MR dedup (universal)" section. |
| `CHANGELOG.md` | Modify | New `## [0.10.2]` entry under "Changed" describing the rule shifts and new format shapes. |

No test files to add — the skill is LLM-interpreted markdown. Acceptance is manual regeneration (Task 6).

The order is: SKILL.md edits → draft-template.md edits → CHANGELOG → acceptance run. SKILL.md and draft-template.md changes can land in any order but MUST land before regeneration; we put SKILL.md first because it is the source of truth that draft-template.md elaborates.

---

## Task 1: Update SKILL.md Source F (ChatPlus rules)

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` (lines covering Source F, around lines 126–150)

- [ ] **Step 1: Read the current Source F block to confirm exact wording**

Run: `grep -n "Source F" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: line number for `### Source F — ChatPlus self-authored posts` header.

Then read lines from that header through the next `### Source` to capture exact context.

- [ ] **Step 2: Replace the DM-drop bullet (under "Drop hard-default categories")**

Find this line in `skills/cortex-weekly/SKILL.md`:

```
   - Direct-message channels (`channel_name == ""`, `team_id == 0`) unless the content is clearly a substantive technical exchange — DMs default to drop.
```

Replace with:

```
   - (DMs are NOT auto-dropped — they go through the substance filter below, the same as public channels. The MR-link / meeting-link / social-chatter rules above still apply.)
```

- [ ] **Step 3: Add a new "Resolve participant" sub-step after item 3 ("One bullet per thread")**

Find:

```
3. **One bullet per thread**, not per post. If the user posted multiple messages in the same thread, summarize the overall contribution in one clause.
```

Insert immediately after (as item 4):

```
4. **Resolve participants for DMs.** When a surviving thread has `channel_name == ""`, call `chat_list_posts(channel_id)` to enumerate posts, collect distinct `creator_id` values that are not self, then call `chat_list_users` once per run to map ids → usernames. Cache the lookup table for the rest of the run.
```

- [ ] **Step 4: Replace the format-and-redaction bullets at the end of Source F**

Find:

```
- ChatPlus has no canonical thread URL exposed by the MCP — do **not** invent one. Use plain text `[chat: <channel>]` (no link).
- For public channels use `channel_name`; for DMs (`channel_name == ""`) use `DM`.
- `topic`: what the thread is about (very short, no participant names).
- `我的貢獻`: paraphrased one-clause summary of what the user contributed.
- Never include other participants' names, user IDs, or personal identifiers.
```

Replace with:

```
- ChatPlus has no canonical thread URL exposed by the MCP — do **not** invent one. Use plain text `[chat: ...]` (no link).
- Channel label rules:
  - Public channel (`channel_name != ""`): `[chat: <channel-name>]`.
  - 1:1 DM (exactly one non-self `creator_id` in the thread): `[chat: @username]`.
  - Group DM with 2–3 other participants: `[chat: @user_a, @user_b]` or `[chat: @user_a, @user_b, @user_c]`.
  - 4+ other participants: `[chat: DM]` (fall back; participant list too long to be useful).
- `topic`: what the thread is about (very short).
- `我的貢獻`: paraphrased one-clause summary of what the user contributed.
- Never include customer info or external personal identifiers (phone numbers, emails, addresses). Internal Synology usernames (resolved via `chat_list_users`) are allowed.
```

- [ ] **Step 5: Update the inline shape line in the "Surviving threads go into `inbound.` as" block**

Find:

```
[chat: <channel-name-or-"DM">]: topic → 我的貢獻
```

Replace with:

```
[chat: <channel-or-@username(s)>]: topic → 我的貢獻
```

- [ ] **Step 6: Verify the edits**

Run: `grep -n "DMs are NOT auto-dropped\|Resolve participants for DMs\|Channel label rules\|chat: <channel-or-@username" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: 4 matching line numbers (one per phrase).

- [ ] **Step 7: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): allow DM @username in chat bullets; drop DM auto-drop"
```

---

## Task 2: Update SKILL.md Source G (MailPlus rules)

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` (Source G section, after Source F)

- [ ] **Step 1: Locate the format-and-redaction block at the end of Source G**

Run: `grep -n "Source G\|Never include sender" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: line numbers for the Source G header and the redaction sentence.

- [ ] **Step 2: Add a "Resolve counterparty" sub-step before the "Surviving threads go into `inbound.` as" block**

Find:

```
Surviving threads go into `inbound.` as:

```
[mail: <subject>]: topic → 我的回應
```
```

Replace with:

```
4. **Resolve counterparty for 1-on-1 threads.** Aggregate every distinct address across `From` and `To` headers in the thread (excluding the user's own address). If exactly one non-self address remains, extract `@username` (strip `<>` form, take the local-part of the email or the bracketed display name `@<id>` if MailPlus exposes one). If 2+ non-self addresses remain, treat as multi-recipient.

Surviving threads go into `inbound.` as:

```
[mail: <subject>] (@username): topic → 我的回應    ← 1-on-1 thread
[mail: <subject>]: topic → 我的回應                ← multi-recipient / mailing list
```
```

- [ ] **Step 3: Replace the format-and-redaction bullets at the end of Source G**

Find:

```
- **Strip reply prefixes** (`Re:`, `Fwd:`, `RE:`, `FW:`, including repeated stacks like `Re: Re: Fwd:`) from `<subject>`.
- MailPlus has no canonical public thread URL — do **not** invent one. Use plain text `[mail: <subject>]` (no link).
- `topic`: paraphrased thread subject / context.
- `我的回應`: one-clause summary of what the user replied / decided / coordinated.
- Never include sender, recipient, customer, or colleague names.
```

Replace with:

```
- **Strip reply prefixes** (`Re:`, `Fwd:`, `RE:`, `FW:`, including repeated stacks like `Re: Re: Fwd:`) from `<subject>`.
- MailPlus has no canonical public thread URL — do **not** invent one. Use plain text `[mail: ...]` (no link).
- `topic`: paraphrased thread subject / context.
- `我的回應`: one-clause summary of what the user replied / decided / coordinated.
- Never include customer info or external personal identifiers (phone, email, address). Internal Synology usernames (resolved via the From / To headers) are allowed.
```

- [ ] **Step 4: Verify the edits**

Run: `grep -n "Resolve counterparty for 1-on-1\|1-on-1 thread\|multi-recipient / mailing list\|Internal Synology usernames" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: 4 matching line numbers.

- [ ] **Step 5: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): allow @username in mail bullets for 1-on-1 threads"
```

---

## Task 3: Add Same-title MR dedup sub-section to SKILL.md after Step 5

**Files:**
- Modify: `skills/cortex-weekly/SKILL.md` (insert new sub-section between Step 5 and Step 6)

- [ ] **Step 1: Locate the boundary between Step 5 and Step 6**

Run: `grep -n "## Step 5\|## Step 6\|### Experimental repos" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: line numbers for `## Step 5: Classify`, `### Experimental repos (draft label)`, and `## Step 6: Generate Draft`. The new sub-section goes BEFORE `## Step 6`, AFTER `### Experimental repos (draft label)` (so it lives at the end of Step 5).

- [ ] **Step 2: Insert the new sub-section after the "Experimental repos (draft label)" block**

Find the last line of the Experimental repos block (the paragraph ending with `Single-MR flat bullets are never draft-labelled.`).

Insert immediately after that paragraph (before the `## Step 6: Generate Draft` heading) the following block:

```markdown
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

- [ ] **Step 3: Verify the insertion**

Run: `grep -n "### Same-title MR dedup\|## Step 6: Generate Draft" /synosrc/misc/cortex/skills/cortex-weekly/SKILL.md`
Expected: Same-title MR dedup line number is LESS than the Step 6 line number.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/SKILL.md
git commit -m "feat(weekly): add same-title MR dedup sub-section"
```

---

## Task 4: Update references/draft-template.md inbound shapes block

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md` (the inbound shapes code block, around the `## inbound. — externally-initiated work this week` section)

- [ ] **Step 1: Locate the inbound shapes block**

Run: `grep -n "## .inbound\.\|<channel-or-DM>\|<subject>" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md`
Expected: line number for the inbound section header, plus matches inside the example block.

- [ ] **Step 2: Replace the inbound shapes code block**

Find this block:

```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat: <channel-or-DM>]: topic → 我的貢獻
	- [mail: <subject>]: topic → 我的回應
```

Replace with:

```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...   ← same-title dedup
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat: <channel-name>]: topic → 我的貢獻
	- [chat: @username]: topic → 我的貢獻
	- [chat: @user_a, @user_b]: topic → 我的貢獻
	- [mail: <subject>]: topic → 我的回應
	- [mail: <subject>] (@username): topic → 我的回應
```

- [ ] **Step 3: Verify**

Run: `grep -n "same-title dedup\|chat: @username\|mail: <subject>] (@username)" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md`
Expected: 3 matching line numbers.

- [ ] **Step 4: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "feat(weekly-template): expand inbound shapes for chat/mail @username + dedup"
```

---

## Task 5: Update references/draft-template.md ChatPlus + MailPlus rules + add dedup section

**Files:**
- Modify: `skills/cortex-weekly/references/draft-template.md` (ChatPlus and MailPlus rule bullets in the "Rules" sub-section under inbound, plus a new section after the worked example)

- [ ] **Step 1: Replace the ChatPlus rule bullet**

Find this bullet (currently in the Rules block under inbound):

```
- **ChatPlus thread**: `[chat: <channel>]: topic → 我的貢獻` — plain text, no URL (the MCP exposes no canonical thread URL). Use `DM` for direct-message channels (`channel_name == ""`). One bullet per `thread_id`, summarizing the user's overall contribution. Drop social chatter, MR-link broadcasts, and meeting-link coordination.
```

Replace with:

```
- **ChatPlus thread**: plain text, no URL (the MCP exposes no canonical thread URL). One bullet per `thread_id`, summarizing the user's overall contribution. Drop social chatter, MR-link broadcasts, and meeting-link coordination.
  - Public channel (`channel_name != ""`): `[chat: <channel-name>]: topic → 我的貢獻`.
  - 1:1 DM (one non-self participant): `[chat: @username]: topic → 我的貢獻`.
  - Group DM with 2–3 other participants: `[chat: @user_a, @user_b[, @user_c]]: topic → 我的貢獻`.
  - 4+ other participants: `[chat: DM]: topic → 我的貢獻` (fall back).
```

- [ ] **Step 2: Replace the MailPlus rule bullet**

Find this bullet:

```
- **MailPlus thread**: `[mail: <subject>]: topic → 我的回應` — plain text, no URL. Strip `Re:` / `Fwd:` (and stacked variants) from `<subject>`. List only threads the user replied to in the Sent folder this week with substantive technical content. Drop HR / recruiting / calendar / mailing-list / pure-logistics replies.
```

Replace with:

```
- **MailPlus thread**: plain text, no URL. Strip `Re:` / `Fwd:` (and stacked variants) from `<subject>`. List only threads the user replied to in the Sent folder this week with substantive technical content. Drop HR / recruiting / calendar / mailing-list / pure-logistics replies.
  - 1-on-1 thread (one non-self address across all messages): `[mail: <subject>] (@username): topic → 我的回應`.
  - Multi-recipient / mailing list (2+ non-self addresses): `[mail: <subject>]: topic → 我的回應`.
```

- [ ] **Step 3: Replace the redaction bullet**

Find this bullet:

```
- For chat and mail, **never include other participants' names, user IDs, customer info, or personal identifiers.**
```

Replace with:

```
- For chat and mail, **never include customer info or external personal identifiers** (phone numbers, emails, addresses). Internal Synology usernames are allowed and encouraged for 1-on-1 attribution.
```

- [ ] **Step 4: Add the same-title dedup section after the worked example**

Locate the end of the file (after the `Note: ...` line that closes the worked example). Append the following new section:

```markdown

## Same-title MR dedup (universal)

When 2+ MRs share an exact title within `fix.`, `feat.`, or `inbound.`, collapse them into a single top-level bullet inside that section:

```
- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...
```

Rules:
- Plain-text title (not a link); each MR remains individually clickable.
- Pair each MR with its own `Ref:` issue when present. If an MR has no `Ref:` trailer, drop only the `/ [KEY](url)` segment for that entry.
- Order MRs by `merged_at` ascending — master / earliest first; backports follow.
- The dedup bullet sits at the section's top level. MRs that participate in dedup are pulled out of any Workplus-issue group they would otherwise belong to.
- Single-MR cases (no duplicate title) are not affected — they keep `[title](url)` (with `/ [KEY](url)` if applicable).

Worked example (`inbound.` cherry-pick cluster):

```
- inbound.
	- fix(api-upload): strip all _tmp params and repair upload Attr wiring — [!695](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/695) / [BSM-1375](https://workplus.synology.inc/key/BSM/issues/1375)、[!696](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/696) / [BSM-1376](https://workplus.synology.inc/key/BSM/issues/1376)、[!698](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/698) / [AEM-22355](https://workplus.synology.inc/key/AEM/issues/22355)
```

Worked example (`fix.` group with cross-issue cherry-picks):

```
- fix.
	- <Workplus title for issue-X> - ([DSM-X](https://workplus.synology.inc/key/DSM/issues/X))
		- [mr-title-A](url): description
		- [mr-title-B](url): description
	- fix(<scope>): same-title fix on 3 branches — [!N1](url) / [DSM-Y](url)、[!N2](url) / [BSM-Z](url)、[!N3](url) / [AEM-W](url)
```

The dedup bullet sits alongside the regular issue group; it is not nested under any heading.
```

- [ ] **Step 5: Verify**

Run: `grep -n "Same-title MR dedup\|chat: @username\|chat: @user_a\|mail: <subject>] (@username)\|Internal Synology usernames" /synosrc/misc/cortex/skills/cortex-weekly/references/draft-template.md`
Expected: at least 5 matching line numbers covering all the inserted shapes/rules.

- [ ] **Step 6: Commit**

```bash
cd /synosrc/misc/cortex
git add skills/cortex-weekly/references/draft-template.md
git commit -m "feat(weekly-template): chat/mail @username rules + same-title dedup section"
```

---

## Task 6: Acceptance run — regenerate Weekly/2026/2026-05-08.md and confirm new shapes

**Files:**
- Read-only verification: `~/.cortex/config.json` (vault path), `/synosrc/cortex/Weekly/2026/2026-05-08.md` (current rendering)
- The cortex repo for `/cortex:weekly` execution must point at the locally-edited plugin (the user runs Claude Code with the `plugin` branch loaded).

This task is a manual acceptance pass. The implementer asks the user to re-run `/cortex:weekly` (with no argument so it defaults to the same Friday cycle) and visually confirm:

- [ ] **Step 1: Reload the plugin so the edited skill is in effect**

In Claude Code, run `/reload-plugins`. Confirm the cortex-weekly skill description still loads (no syntax error).

- [ ] **Step 2: Re-run /cortex:weekly for the current Friday cycle**

The user invokes `/cortex:weekly` with no argument. The skill should:
- collect Source A–G as before
- in Source F, NOT auto-drop the 4 substantive 1:1 DMs (with @yannyliu, @lifonghsu, @danielyeh, @redhuang)
- attribute each DM bullet with `[chat: @<username>]`
- in Source B/C output, collapse the 3 `fix(api-upload):` cherry-pick MRs into one bullet under `inbound.`
- keep the `fix(synoscgi):` MR as a single-MR bullet (no dedup trigger)

- [ ] **Step 3: Compare the draft output against the expected v5 layout**

Expected `inbound.` section (top-relevant lines):

```
- inbound.
	- fix(api-upload): strip all _tmp params and repair upload Attr wiring — [!695](.../merge_requests/695) / [BSM-1375](.../BSM/issues/1375)、[!696](.../merge_requests/696) / [BSM-1376](.../BSM/issues/1376)、[!698](.../merge_requests/698) / [AEM-22355](.../AEM/issues/22355)
	- [fix(synoscgi): block LD_* env vars from SCGI headers](.../merge_requests/697) / [AEM-21849](.../AEM/issues/21849)
	...
	- [chat: @yannyliu]: ...
	- [chat: @lifonghsu]: ...
	- [chat: @danielyeh]: ...
	- [chat: @redhuang]: ...
```

If the draft matches in shape (allowing wording differences in the prose summaries), acceptance passes.

- [ ] **Step 4: If acceptance fails, file the discrepancy as a follow-up**

Note any shape mismatch (e.g. `[chat: DM]` reappearing, or 3 separate api-upload bullets) and file it against this plan; do NOT proceed to Task 7. Loop back to whichever Task 1–5 introduced the bug.

- [ ] **Step 5: If acceptance passes, no commit (verification-only task)**

The vault-side weekly is not regenerated as part of this plan — the user already has `Weekly/2026/2026-05-08.md` from the manual session. Acceptance run is a dry verification.

---

## Task 7: Update CHANGELOG with version bump

**Files:**
- Modify: `CHANGELOG.md` (insert new `## [0.10.2]` block above `## [0.10.1]`)

- [ ] **Step 1: Insert new changelog entry**

Open `/synosrc/misc/cortex/CHANGELOG.md`. Find the line `## [0.10.1] - 2026-05-06`. Immediately above it, insert:

```markdown
## [0.10.2] - 2026-05-08

### Changed
- `cortex-weekly` (Source F — ChatPlus): DM threads no longer auto-drop —
  they go through the same substance filter as public channels. Surviving
  DM threads attribute to `@username` (1:1) or `@user_a, @user_b[, @user_c]`
  (group DM with 2–3 others). 4+ other participants fall back to
  `[chat: DM]`.
- `cortex-weekly` (Source G — MailPlus): 1-on-1 threads attribute to
  `@username` via the `[mail: <subject>] (@username)` shape. Multi-recipient
  threads keep `[mail: <subject>]`.
- `cortex-weekly` redaction rule scoped to customer info / external personal
  identifiers only. Internal Synology usernames are now allowed (and
  recommended for 1-on-1 attribution).
- `cortex-weekly`: same-title MR dedup. Within `fix.`, `feat.`, or `inbound.`,
  2+ MRs sharing an exact title collapse into one bullet of the form
  `<title> — [!N1](url) / [KEY1](url)、[!N2](url) / [KEY2](url)、...`.
  Single-MR cases keep their existing shape.

### Notes
- Past weekly reports are not regenerated.
- Plugin consumers who relied on the strict-redaction rule (e.g., publishing
  weeklies externally) should review before publishing or fork the skill.
```

- [ ] **Step 2: Verify**

Run: `head -40 /synosrc/misc/cortex/CHANGELOG.md`
Expected: the new `## [0.10.2] - 2026-05-08` block appears above `## [0.10.1]`.

- [ ] **Step 3: Commit**

```bash
cd /synosrc/misc/cortex
git add CHANGELOG.md
git commit -m "chore: bump cortex-weekly to 0.10.2 — chat/mail @username + dedup"
```

---

## Self-Review Notes

**Spec coverage check:**
- DM default = include with substance filter → Task 1 (Step 2 + Step 4 channel label rules)
- Internal usernames allowed → Task 1 (Step 4 final bullet) + Task 2 (Step 3 final bullet) + Task 5 (Step 3)
- Customer info still forbidden → Task 1 (Step 4) + Task 2 (Step 3) + Task 5 (Step 3)
- Public channel format unchanged → Task 1 (Step 4 first sub-bullet) + Task 5 (Step 1)
- 1:1 DM `[chat: @username]` → Task 1 (Step 4) + Task 4 (Step 2) + Task 5 (Step 1)
- Group DM 2–3 names cap → Task 1 (Step 4) + Task 5 (Step 1)
- 4+ DM fallback → Task 1 (Step 4) + Task 5 (Step 1)
- 1-on-1 mail `[mail: <subject>] (@username)` → Task 2 (Step 2 + Step 3) + Task 4 (Step 2) + Task 5 (Step 2)
- Multi-recipient mail unchanged → Task 2 (Step 2) + Task 5 (Step 2)
- Same-title dedup universal → Task 3 + Task 4 (Step 2) + Task 5 (Step 4)
- Plain-text title in dedup bullet → Task 3 (Step 2) + Task 5 (Step 4)
- merged_at ascending order → Task 3 (Step 2) + Task 5 (Step 4)
- Dedup bullet at section top level → Task 3 (Step 2) + Task 5 (Step 4)
- Single-MR shape unchanged → Task 3 (Step 2 item 3) + Task 5 (Step 4)
- Cross-issue dedup in fix./feat. (worked example) → Task 5 (Step 4 final example)
- No new config flags → addressed by absence (no config schema edit)

**Placeholder scan:** No "TBD", "TODO", "appropriate", "etc." in any task. Every step shows the literal markdown to replace.

**Type/symbol consistency:** Skill uses no code symbols. The literal strings (`@username`, `<channel-name>`, `[chat: ...]`, etc.) match across all tasks.

**Out-of-scope items honored:** No config flags introduced. No retroactive weekly regeneration. No participant-resolve cache layer beyond per-run memoization (described in Task 1 Step 3).

**One known soft spot:** `mailplus_get` returns `From` / `To` as raw RFC822 headers; extracting `@username` requires either a known display-name pattern (`"Tony Hu (@tonyhu) <tonyhu@synology.com>"`) or falling back to the local-part of the email. Task 2 Step 2 instructs the LLM to "strip `<>` form, take the local-part of the email or the bracketed display name `@<id>` if MailPlus exposes one" — this is a heuristic, not a guaranteed parse. If a real run produces an unrecognized address shape, the skill should fall back to multi-recipient form. This is acceptable for a markdown spec; document it in CHANGELOG if it surfaces in practice.
