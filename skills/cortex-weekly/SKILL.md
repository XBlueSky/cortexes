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

## Runtime Requirements & Graceful Degradation

This skill pulls from external MCP plugins that cortex does **not** declare as
hard dependencies — cortex stays a standalone vault, so the source steps below
must degrade gracefully when a plugin is absent or unauthenticated:

| Source | Provided by | Minimum |
|--------|-------------|---------|
| B / C / D — GitLab MRs, reviews, wit issues | `synology-workflows` (gitlab MCP) | installed |
| Workplus issue type/title (Step 5) | `synology-workflows` (workplus MCP) | installed |
| E — CSS tickets | `syno-robinhood` | enlisted |
| F — ChatPlus posts | `syno-robinhood` | enlisted |
| G — MailPlus mail | `syno-robinhood` | enlisted |

robinhood needs its binary installed and a live SSO session (see the robinhood
`enlist` skill) — a registered plugin whose session is dead returns auth
errors, which count as "unavailable" below.

**Degradation policy — skip, note, never abort:**

- If a source's MCP tool is not in the tool list (plugin not installed) or
  returns an unknown-tool / auth / enlistment error, **skip that source**.
- Accumulate skipped sources and surface them **once**, as a note at the top
  of the Step 6 draft preamble (not inline per bullet), e.g.
  `> ⚠ Skipped sources: CSS, Chat, Mail (syno-robinhood not enlisted).`
- Never abort the whole report because one source is unavailable. A report
  built from `Summary/` + GitLab alone is still useful.

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

**Why this is a hard precondition for Source A:** Source A reads from `Summary/`, and a Summary file is only written as a side effect of distill (cortex-distill Step 5.5). Skipping Step 2 means Source A sees fewer sessions than actually happened. If distill fails or is skipped for any Raw, Source A surfaces those orphans explicitly and refuses to silently fall back to reading the Raw body.

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
- `issue:` from frontmatter (optional) → the Workplus issue this
  session contributes to, as judged by distill Step 5.6. When absent
  or empty, the session is treated as repo-level work with no issue
  attribution (this is the normal case for repos not listed in
  `weekly.repo_issue_map`).
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

**Then, for surviving DM threads, resolve participants.** Each `chat_my_recent_activity` post carries a `channel_id` field — pass that to `chat_list_posts(channel_id=...)` to enumerate the thread's posts, collect distinct `creator_id` values that are not self, then call `chat_list(kind="users")` once per run to map ids → usernames. Cache the lookup table for the rest of the run.

Surviving threads go into `inbound.`. **Bullet shape is defined in
`references/draft-template.md` § `inbound.` chat rules.** Do not
duplicate the shape here — formatting drift between SKILL.md and
the template caused the 2026-05-22 GFM-rendering regression. Two
load-bearing reminders that are easy to lose:

- ChatPlus has no canonical thread URL exposed by the MCP — do
  **not** invent one. The `[chat] …` bracket carries only the
  source tag; no link.
- Usernames are wrapped in single backticks so GitLab does not ping
  the user when the report is pasted into a wiki / MR / issue.
- Never include customer info or external personal identifiers
  (phone numbers, emails, addresses). Internal Synology usernames
  (resolved via `chat_list(kind="users")`) are allowed.

### Source G — MailPlus work mail

Use the **Sent folder as the primary source**, not INBOX. The user's INBOX is dominated by automated notifications (Gandalf / CI Report / Build System / Bug Tracker — tens of thousands of unread); filtering INBOX is impractical. The Sent folder directly answers "which threads did I reply to this week".

Procedure:

1. Call `mailplus_list_threads` with `mailbox_id = -4` (Sent) and `since_epoch = start_seconds`. Note the unit: this API uses **seconds**, not milliseconds (differs from `chat_my_recent_activity`).
2. For each returned thread, call `mailplus_get` with `kind = "thread"` and the `thread_id` to fetch the full conversation. Read the user's own messages within the week window.
3. **Filter strictly — keep only work-substantive threads.**
   - Drop: HR / recruiting / interview coordination, calendar invites, social mail, mass company-wide announcements, mailing-list digests, anything where the user's reply is purely logistical ("ok", "received", scheduling).
   - Keep: build/release/patch escalations (e.g. "[Bad Version]" patch bad fixes), cross-team technical RFC discussions, vendor/partner technical exchanges, post-mortem coordination, escalations where the user gave a substantive technical response.

**Then, for surviving 1-on-1 threads, resolve the counterparty.** Aggregate every distinct address across `From` and `To` headers in the thread (excluding the user's own address). If exactly one non-self address remains, extract `@username` (strip `<>` form, take the local-part of the email or the bracketed display name `@<id>` if MailPlus exposes one). If 2+ non-self addresses remain, treat as multi-recipient.

Surviving threads go into `inbound.`. **Bullet shape is defined in
`references/draft-template.md` § `inbound.` mail rules.** Two
load-bearing reminders:

- **Strip reply prefixes** (`Re:`, `Fwd:`, `RE:`, `FW:`, including
  repeated stacks like `Re: Re: Fwd:`) from `<subject>` before
  emitting.
- MailPlus has no canonical public thread URL — do **not** invent
  one. The `[mail] …` bracket carries only the source tag; no link.
- **Wrap `@username` in backticks** so GitLab does not turn it into
  a mention/notification when the weekly is pasted into a wiki /
  MR / issue.
- Never include customer info or external personal identifiers
  (phone numbers, emails, addresses). Internal Synology usernames
  (resolved via the From / To headers) are allowed.

## Step 4: Merge and Deduplicate

1. Start with Source A Summary entries as the base
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
3. Add `inbound.` items (MR reviews, wit issues filtered by reply, CSS tickets filtered by this-week action, ChatPlus threads filtered for substance, MailPlus threads filtered for substance)
4. **Cross-source dedup for ChatPlus / MailPlus.** A chat post or mail thread that merely announces or coordinates around an MR/issue already represented elsewhere in this report is redundant — drop it. Keep the chat/mail entry only when it carries information not already conveyed by a Raw/, MR, wit, or CSS entry.

## Step 5: Classify

Four sections, selected primarily by **Workplus issue type**, not commit type. Commit type is a fallback only when no issue ref exists.

| Section | Criteria | Layout |
|---------|----------|--------|
| `fix.` | Self-authored MR whose Workplus issue has `type = BUG` | Always flat — one MR per bullet, no Workplus-title group headings |
| `feat.` | Self-authored MR whose Workplus issue has `type = FEATURE` | Multiple MRs sharing one issue → grouped under Workplus-title heading; single MR → flat bullet |
| `inbound.` | Others' MR approved / wit issue replied / CSS ticket acted on / ChatPlus thread with substantive contribution / MailPlus work thread replied to — all within the cutoff window | Flat list |
| `misc.` | Self-authored MR with no issue ref (side projects, infrastructure work) | Flat list |

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

### Grouping rule (feat. only)

`fix.` is **always flat** — one bullet per MR, regardless of how
many MRs share an issue. No Workplus-title group headings in
`fix.`.

`feat.`-only: MRs are grouped by Workplus issue:

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

Read `weekly.experimental_repos` from `~/.cortex/config.json` (list of `namespace/project` strings). For each `feat.` group heading, if **every** MR in the group targets a repo in that list, prefix the heading bullet with `**[draft]** ` (bold, trailing space). Mixed groups get no prefix. Single-MR flat bullets are never draft-labelled. (Does not apply to `fix.` — `fix.` has no group headings.)

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
     number under the issue): render the dedup'd cluster as **one
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

## Step 6: Generate Draft

Compose the draft using the nested-bullet format defined in `references/draft-template.md`. The reference covers:

- Base principles (GFM, tab indent, frontmatter, omit empty sections)
- Exact format for each section (`fix.`, `feat.`, `inbound.`, `misc.`)
- Worked example from `2026-04-17`

Load the reference before writing the draft — the SKILL body does not repeat the rules.

If any source was skipped (see § Runtime Requirements & Graceful Degradation),
emit the consolidated skip note as a blockquote at the very top of the draft,
above the first section — once, never per bullet.

**Present the draft to the user for review. Do not write the file until the user confirms.**

## Step 7: Write and Commit

1. Write to `<vault_path>/Weekly/YYYY/YYYY-MM-DD.md`
2. Update `_index.md` Weekly section (entries count, updated date, new row under `### YYYY`)
3. `git add Weekly/ _index.md Raw/ && git commit -m "weekly: YYYY-MM-DD"`
4. If `auto_push` is `true` in config: `git push`
