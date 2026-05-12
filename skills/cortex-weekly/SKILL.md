---
name: cortex-weekly
description: >
  This skill should be used when the user says "整理週報",
  "產生週報", "generate weekly", "weekly report", or invokes
  /cortex:weekly. Compiles the Friday-meeting weekly report by
  pulling from Raw/, GitLab activity (authored MRs, MR reviews,
  wit issue replies), CSS tickets, ChatPlus self-authored posts,
  and MailPlus Sent threads, then merges and classifies entries
  into fix./feat./inbound./misc. sections.
---

# Cortex Weekly — Compile Weekly Report

Compile the weekly report from multiple sources into the standard nested-bullet format.

For the exact draft layout and every format rule, load `references/draft-template.md` before composing Step 6 output.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path` and `weekly.gitlab_username`.
If the file does not exist, tell the user to run `/cortex:genesis` first.

## Step 1: Determine Target Week

The report is written **for a Friday meeting** and covers one meeting cycle.
The meeting day and cutoff hour live at `~/.cortex/config.json` → `weekly.cutoff`:

```json
"weekly": { "cutoff": { "day": "friday", "hour": 11 } }
```

With `day: friday, hour: 11`, each report covers
**[previous Friday 11:00, meeting Friday 11:00)** — start inclusive, end exclusive.

### Resolve the meeting Friday

Let `now` be the current datetime:

- Today is Friday and `now < 11:00` → meeting = **today**
- Today is Friday and `now >= 11:00` → meeting = **next Friday**
  (this morning's meeting is done; start the next cycle)
- Otherwise → meeting = the **next Friday** in the calendar

Then: `End = meeting Friday @ cutoff hour`, `Start = End − 7 days`.

### User arguments

- `last week` → shift the range back 7 days (both endpoints)
- `YYYY-WXX` → use the Friday of that ISO week as the meeting Friday
- No argument → use the resolved meeting Friday above

### Output filename

`Weekly/YYYY/YYYY-MM-DD.md` where `YYYY-MM-DD` = meeting Friday (not the Monday).

## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files from the target week before compiling the report.

## Step 3: Collect Sources

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

### Source B — GitLab MRs authored by the user

Fetch merged MRs authored by the configured `weekly.gitlab_username` within the range. For each MR record: title, URL, target repo (`namespace/project`), commit type (first word of the title before `:` or `(scope):`).

**Extract issue refs from commit messages, not only from Raw/.** For every merged MR, fetch its commit messages and grep:

```
Ref:\s*([A-Z]+-\d+)
```

Attach any matching issue keys to the MR. This grouping hook is what connects MRs that had no Raw/ session note to their parent Workplus issue.

### Source C — GitLab MR reviews (approvals)

Use `list_events` with `action=approved, target_type=merge_request` in the date range. For each, fetch the MR to get its title and any `Ref:` issue key. These go into `inbound.`.

### Source D — wit/wit_issues (cross-department tickets)

Use `list_issues` with `project_id: "wit/wit_issues"` (project ID 31865) to find candidate issues assigned to or touching the user.

**Filter strictly — `updated_at` in range is insufficient.** Bots, label changes, and others' comments all bump `updated_at`. For each candidate:

1. Call `list_issue_discussions` to fetch notes
2. Keep the issue only if at least one note has `author.username == weekly.gitlab_username` (**literal string match** — no inference of alternate identities or substring matches) AND `created_at ∈ [start, end)`
3. Otherwise drop

Matching issues go into `inbound.`.

### Source E — CSS tickets

CSS tickets you merely own do NOT all count — the report lists only tickets you acted on this week. A ticket you never owned but routed back to L1 still counts. `css_list_tickets` alone cannot distinguish these cases.

Use this flow:

1. **Widen the candidate pool.** Call `css_list_tickets` with multiple `list_type` values (`user_all`, `agent_all`) filtered by `last_update_from`/`last_update_to` spanning the week.
2. **Filter by actual action.** For each candidate, call `css_get_activities` and keep the ticket only if there is at least one entry with `user == <css_username>` (defined below) and `datetime ∈ [start, end)`.
   - `<css_username>` defaults to `weekly.gitlab_username`. Override via `weekly.css_username` in `~/.cortex/config.json` when the user's CSS SSO differs from their GitLab username.
   - **Literal string match only.** Do not infer alternate usernames (e.g. don't treat `jhu` as a variant of `tonyhu` because both end in `hu`). Substring overlap is not a match. If no activity entry has `user` exactly equal to the configured username, the user has no CSS activity in the window — return zero CSS bullets.
3. **Read the reply content.** For every surviving ticket, call `css_get_ticket` and read the thread. Locate the user's own message(s) within the week window.
4. **Refine to three segments.** From the message content, compose the `inbound.` line as:

   ```
   [css#ID](url): <symptom> → <root cause> → <response>
   ```

   - `symptom`: what the customer reported (very short)
   - `root cause`: what the user diagnosed in their reply (paraphrased, one clause)
   - `response`: what the user did or routed the ticket to
   - Never include customer, colleague, or personal identifiers.
   - If a Workplus issue was filed, append ` / [KEY](issue-url)` after the response segment.

### Source F — ChatPlus self-authored posts

Use `chat_my_recent_activity` with `since_epoch_ms = start_ms` (start of the week window in epoch milliseconds). The tool returns posts the configured user authored across all active channels.

**ChatPlus is high-noise; default behavior is to drop.** Aggregate posts by `thread_id` (use `post_id` itself when `thread_id == 0`) so that a back-and-forth conversation is one bullet, not many. For each thread, evaluate:

1. **Drop hard-default categories.**
   - Pure social / status chatter ("kk", "ok", "thanks", "晚點看", greetings, lunch coordination, meeting links).
   - **MR-link broadcasts** — posts whose body is one or more `git.synology.inc/.../merge_requests/N` URLs and nothing else. These duplicate Source B; the MR is already in `fix.` / `feat.` / `inbound.`.
   - Shared meeting / Google Meet links, calendar coordination.
2. **Keep substantive technical contributions.** Threads where the user diagnosed an issue, gave a root-cause explanation, made a design decision, answered a technical question, shared a workaround, flagged a regression, or coordinated a cross-team technical action.
3. **One bullet per thread**, not per post. If the user posted multiple messages in the same thread, summarize the overall contribution in one clause.

> **Note:** DMs (`channel_name == ""`, `team_id == 0`) are NOT auto-dropped — they go through the same substance filter above as public channels. The MR-link / meeting-link / social-chatter drops still apply.

**Then, for surviving DM threads, resolve participants.** Each `chat_my_recent_activity` post carries a `channel_id` field — pass that to `chat_list_posts(channel_id=...)` to enumerate the thread's posts, collect distinct `creator_id` values that are not self, then call `chat_list_users` once per run to map ids → usernames. Cache the lookup table for the rest of the run.

Surviving threads go into `inbound.` as:

```
[chat: <channel-or-@username(s)>]: topic → 我的貢獻
```

- ChatPlus has no canonical thread URL exposed by the MCP — do **not** invent one. Use plain text `[chat: ...]` (no link).
- Channel label rules (note: usernames are wrapped in backticks so GitLab does not ping the user when the report is pasted into a wiki / MR / issue):
  - Public channel (`channel_name != ""`): `` [chat: <channel-name>] ``.
  - 1:1 DM (exactly one non-self `creator_id` in the thread): `` [chat: `@username`] ``.
  - Group DM with 2 other participants: `` [chat: `@user_a`, `@user_b`] ``.
  - Group DM with 3 other participants: `` [chat: `@user_a`, `@user_b`, `@user_c`] ``.
  - 4+ other participants: `` [chat: DM] `` (fall back; participant list too long to be useful).
- `topic`: what the thread is about (very short).
- `我的貢獻`: paraphrased one-clause summary of what the user contributed.
- Never include customer info or external personal identifiers (phone numbers, emails, addresses). Internal Synology usernames (resolved via `chat_list_users`) are allowed.

### Source G — MailPlus work mail

Use the **Sent folder as the primary source**, not INBOX. The user's INBOX is dominated by automated notifications (Gandalf / CI Report / Build System / Bug Tracker — tens of thousands of unread); filtering INBOX is impractical. The Sent folder directly answers "which threads did I reply to this week".

Procedure:

1. Call `mailplus_list_threads` with `mailbox_id = -4` (Sent) and `since_epoch = start_seconds`. Note the unit: this API uses **seconds**, not milliseconds (differs from `chat_my_recent_activity`).
2. For each returned thread, call `mailplus_get` with `kind = "thread"` and the `thread_id` to fetch the full conversation. Read the user's own messages within the week window.
3. **Filter strictly — keep only work-substantive threads.**
   - Drop: HR / recruiting / interview coordination, calendar invites, social mail, mass company-wide announcements, mailing-list digests, anything where the user's reply is purely logistical ("ok", "received", scheduling).
   - Keep: build/release/patch escalations (e.g. "[Bad Version]" patch bad fixes), cross-team technical RFC discussions, vendor/partner technical exchanges, post-mortem coordination, escalations where the user gave a substantive technical response.

**Then, for surviving 1-on-1 threads, resolve the counterparty.** Aggregate every distinct address across `From` and `To` headers in the thread (excluding the user's own address). If exactly one non-self address remains, extract `@username` (strip `<>` form, take the local-part of the email or the bracketed display name `@<id>` if MailPlus exposes one). If 2+ non-self addresses remain, treat as multi-recipient.

Surviving threads go into `inbound.` as:

```
[mail: <subject>] (`@username`): topic → 我的回應    ← 1-on-1 thread
[mail: <subject>]: topic → 我的回應                  ← multi-recipient / mailing list
```

- **Strip reply prefixes** (`Re:`, `Fwd:`, `RE:`, `FW:`, including repeated stacks like `Re: Re: Fwd:`) from `<subject>`.
- MailPlus has no canonical public thread URL — do **not** invent one. Use plain text `[mail: ...]` (no link).
- **Wrap `@username` in backticks** so GitLab does not turn it into a mention/notification when the weekly is pasted into a wiki / MR / issue.
- `topic`: paraphrased thread subject / context.
- `我的回應`: one-clause summary of what the user replied / decided / coordinated.
- Never include customer info or external personal identifiers (phone numbers, emails, addresses). Internal Synology usernames (resolved via the From / To headers) are allowed.

## Step 4: Merge and Deduplicate

1. Start with Raw/ entries as the base
2. For each GitLab MR, join to Source A summaries by **repo + date**, not by URL string matching:
   - Find Summary files where `repo:` matches the MR's target repo AND the Summary's date is either the same date as the MR's `merged_at` or the immediately preceding date (to capture sessions that ran late and crossed midnight before the MR was merged the next morning).
   - Exactly one match → use that Summary's prose body as the MR's session-context description text in the weekly draft.
   - Multiple matches → choose the Summary whose `HHMMSS` is closest to the MR's `merged_at` timestamp. If still ambiguous, concatenate them, each as its own session contribution.
   - No match → the MR stands alone; commit title + Workplus issue title carry the description (same as the previous "MR absent from Raw" branch).

   Rationale: Summary prose intentionally does NOT enumerate MR URLs (see `cortex-distill` Step 5.5 guideline), so URL-string matching breaks. Repo + date is the structural replacement.
3. Add `inbound.` items (MR reviews, wit issues filtered by reply, CSS tickets filtered by this-week action, ChatPlus threads filtered for substance, MailPlus threads filtered for substance)
4. **Cross-source dedup for ChatPlus / MailPlus.** A chat post or mail thread that merely announces or coordinates around an MR/issue already represented elsewhere in this report is redundant — drop it. Keep the chat/mail entry only when it carries information not already conveyed by a Raw/, MR, wit, or CSS entry.

## Step 5: Classify

Four sections, selected primarily by **Workplus issue type**, not commit type. Commit type is a fallback only when no issue ref exists.

| Section | Criteria |
|---------|----------|
| `fix.` | Self-authored MR whose Workplus issue has `type = BUG` (groups MRs by issue) |
| `feat.` | Self-authored MR whose Workplus issue has `type = FEATURE` (groups MRs by issue) |
| `inbound.` | Others' MR approved / wit issue replied / CSS ticket acted on / ChatPlus thread with substantive contribution / MailPlus work thread replied to — all within the cutoff window |
| `misc.` | Self-authored MR with no issue ref (side projects, infrastructure work) |

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

### Grouping rule — same for `fix.` and `feat.`

Within `fix.` and `feat.`, MRs are grouped by Workplus issue:

- **Single MR in an issue** → flat one-line bullet:
  `- [mr-title](mr-url)` (no group heading, no description)
- **Multiple MRs in an issue** → group heading + indented MR bullets:
  ```
  - <Workplus-title> - ([<KEY>](<issue-url>))
  	- [mr-title](mr-url): one-line description
  	- [mr-title](mr-url): one-line description
  ```

The group heading only appears when at least two MRs share the issue — it exists to tell the story across the MRs, not to decorate single items.

### `inbound.` and `misc.`

- **`inbound.`** is a flat list. See `references/draft-template.md` for the five shapes (MR review, wit issue, CSS ticket, ChatPlus thread, MailPlus thread).
- **`misc.`** is a flat list — one bullet per side project, short summary only.

### Resolve Workplus issue titles and types

For each unique issue key referenced by a self-authored MR, call Workplus MCP `get_issue` once and cache both `title` and `type`. Use the title **verbatim** in any group heading — do not paraphrase, summarize, or invent a "short theme name".

If the title begins with `[` or contains `][` (e.g. `[thread+fork][synoscgi] ...`), wrap the title in backticks so GFM does not misinterpret it as a reference-style link:

```
- `[thread+fork][synoscgi] 替換 redis cpp client 實作` - ([DSM-169641](url))
```

### Experimental repos (draft label)

Read `weekly.experimental_repos` from `~/.cortex/config.json` (list of `namespace/project` strings). For each group heading (in `fix.` or `feat.`), if **every** MR in the group targets a repo in that list, prefix the heading bullet with `**[draft]** ` (bold, trailing space). Mixed groups get no prefix. Single-MR flat bullets are never draft-labelled.

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

## Step 6: Generate Draft

Compose the draft using the nested-bullet format defined in `references/draft-template.md`. The reference covers:

- Base principles (GFM, tab indent, frontmatter, omit empty sections)
- Exact format for each section (`fix.`, `feat.`, `inbound.`, `misc.`)
- Worked example from `2026-04-17`

Load the reference before writing the draft — the SKILL body does not repeat the rules.

**Present the draft to the user for review. Do not write the file until the user confirms.**

## Step 7: Write and Commit

1. Write to `<vault_path>/Weekly/YYYY/YYYY-MM-DD.md`
2. Update `_index.md` Weekly section (entries count, updated date, new row under `### YYYY`)
3. `git add Weekly/ _index.md Raw/ && git commit -m "weekly: YYYY-MM-DD"`
4. If `auto_push` is `true` in config: `git push`
