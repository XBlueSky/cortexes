---
name: cortex-weekly
description: >
  Compile the weekly report. Use when the user says "整理週報",
  "產生週報", "generate weekly", "weekly report", or invokes
  /cortex:weekly. Pulls from Raw/, GitLab activity, and
  CSS tickets to produce a formatted weekly report.
---

# Cortex Weekly — Compile Weekly Report

Compile the weekly report from multiple sources into the standard format.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path` and `weekly.gitlab_username`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Step 1: Determine Target Week

The weekly report is written **for a Friday meeting** and covers one
meeting cycle. The meeting day and cutoff hour come from
`~/.cortex/config.json` → `weekly.cutoff`:

```json
"weekly": {
  "cutoff": { "day": "friday", "hour": 11 }
}
```

With `day: friday, hour: 11`, each report covers the datetime range
**[previous Friday 11:00, meeting Friday 11:00)** — start inclusive,
end exclusive.

### Resolve the meeting Friday

Let `now` be the current datetime. Find the meeting Friday:

- If today is Friday **and** `now < 11:00` → meeting = **today**
- If today is Friday **and** `now >= 11:00` → meeting = **next Friday**
  (this morning's meeting is already done; start the next cycle)
- Otherwise → meeting = the **next Friday** in the calendar

Then:
- **End** = meeting Friday at cutoff hour (e.g. `2026-04-17 11:00`)
- **Start** = end minus 7 days (e.g. `2026-04-10 11:00`)

### User arguments

- `last week` → shift the range back 7 days (both start and end)
- `YYYY-WXX` → use the Friday of that ISO week as the meeting Friday
- No argument → use the resolved meeting Friday above

### Output filename

Use the **meeting Friday date**, not the Monday:
`Weekly/YYYY/YYYY-MM-DD.md` where `YYYY-MM-DD` = meeting Friday.

## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files
from the target week before compiling the weekly report.

## Step 3: Collect Sources

### Source A: Raw/

Glob `<vault_path>/Raw/YYYY/MM/DD/*.md` for every date the range
touches (start Friday through end Friday, inclusive — typically 8 days).

Raw filenames are `HHMMSS_session_<repo>.md`. Apply timestamp filters
on the two boundary days using the filename prefix:

- **Start Friday:** keep files whose first 6 chars `>= "110000"` (zero-padded)
- **End Friday:** keep files whose first 6 chars `< "110000"`
- **All days in between:** keep every file

(`110000` = cutoff hour 11 expressed as `HHMMSS`. If you change
`weekly.cutoff.hour` in config, regenerate this literal accordingly.)

Read each matched file — extract commits, discoveries, decisions, other work.

### Source B: GitLab Activity

Use GitLab MCP tools to fetch the user's (from config `weekly.gitlab_username`) activity:
- Merged MRs
- Commits pushed
- MR reviews done

For each MR, collect: title, URL, target repo (namespace/project form),
commit type (first word of MR title before `:` or `(scope):`).

**Extract issue refs from commit messages.** Do not rely only on Raw/.
For every merged MR, fetch its commit messages and grep for:

```
Ref:\s*([A-Z]+-\d+)
```

Attach any matching issue key(s) to the MR. This is how MRs that were
never written up in Raw/ still get grouped under their parent Workplus
issue (e.g. MRs in repos that have no session notes).

### Source C: GitLab Issues (wit/wit_issues)

Use GitLab MCP tools (`list_issues` with project_id `wit/wit_issues`) to fetch
issues assigned to or participated by the user during the target week.

This is the cross-department issue tracker (project ID: `31865`,
URL: `https://git.synology.inc/wit/wit_issues`). Colleagues from various teams
(sp, pm, qa, techw, etc.) open tickets here — some get assigned to the user.

**Filter rule — only include issues the user actually replied to this week.**
`updated_at` in the week range is not enough: bots, label changes, and other
people's comments all bump `updated_at` and would re-surface old issues.

For each candidate issue:

1. Call `list_issue_discussions` (or equivalent) to fetch notes
2. Keep the issue only if at least one note is authored by the configured
   `weekly.gitlab_username` AND `created_at` falls in `[start, end)`
3. Otherwise drop it

Format: `[wit#issue-iid](issue-url): question topic → responded / resolved`
- Concise, one line per issue
- Goes into `inbound.`

### Source D: CSS Tickets

Use robinhood MCP `css_get_activities` to fetch CSS ticket activity for the week.
For each ticket, extract:
- Ticket number and URL
- Root cause (what was wrong)
- Resolution (how it was fixed, or issue link if a bug was filed)

Rules for CSS entries:
- **No names** — no customer names, colleague names, or personal identifiers
- **Concise** — one line: symptom → outcome (e.g., "→ can not reproduce", "→ config error, guided user to fix")
- If a Workplus issue was filed, append the link: `[DSM-123456](https://workplus.synology.inc/key/DSM/issues/123456)`

## Step 4: Merge and Deduplicate

1. Start with Raw/ entries as the base
2. For each GitLab MR:
   - If same MR URL exists in Raw → keep Raw's description
   - If MR not in Raw → add it
3. Add wit issues (this-week replied only) to `inbound.`
4. Add CSS tickets (this-week activity only) to `inbound.`
5. Add MR reviews (this-week approved only) to `inbound.`

## Step 5: Classify

Four sections, selected by **who authored the work** and **what kind of
work it is**:

| Section | Criteria |
|---------|----------|
| `fix.` | Self-authored MR, commit type = fix (flat list — no issue grouping) |
| `feat.` | Self-authored MR, commit type = feat with issue ref (grouped by Workplus issue; includes supporting chore/docs MRs of the same issue) |
| `inbound.` | Others' MR you approved / wit issue you replied to / CSS ticket you worked — all within the week cutoff window |
| `misc.` | Self-authored side project (typically no issue ref) |

Key rules:
- **fix. is flat** — do NOT group under Workplus issue. A bug fix tells its story
  in its MR title; grouping adds noise. If a fix MR happens to share a Workplus
  issue with a feat group, still list it under `fix.` (not merged into the feat
  group).
- **feat. is grouped** — a feature typically spans many MRs (feat/chore/docs),
  so grouping under the Workplus issue + title tells the story. Supporting
  chore/docs MRs of the same issue go under the feat group, not misc.
- **inbound. filters strictly** — only this-week approvals / replies / CSS
  activity. `updated_at` in-range is NOT sufficient for wit issues (see
  Source C for the reply-check rule).
- **misc. is flat** — one line per side project.

### Resolve Workplus issue titles (for `feat.` groups only)

For every unique issue key that anchors a `feat.` group, call the Workplus
MCP tool `get_issue` to fetch the real `title`. Use this exact title
verbatim in the group heading — **do not paraphrase, summarize, or
invent a "short theme name"**. See Step 6 for the exact heading format.

Cache the title → reuse for all MRs under the same issue.

`fix.` and `inbound.` MR-review items do not need Workplus title resolution
(they show the MR title directly).

### Experimental repos (draft label)

Read `weekly.experimental_repos` from `~/.cortex/config.json`. This is a
list of `namespace/project` strings (e.g. `["wit/morpheus"]`).

Rule for the `**[draft]**` prefix (applies to `feat.` group bullets):
- Build the group of MRs for each issue ref
- If **every** MR in the group has its target repo in `experimental_repos`
  → prefix the group-heading bullet with `**[draft]** `
  (bold, trailing space)
- If the group mixes experimental and non-experimental repos → no label
  (it is already a real feature)

## Step 6: Generate Draft

The draft is **copy-pasted into a GitLab issue/MR description**
(e.g. wit/reports), so output must be **valid GitLab Flavored Markdown
(GFM)**. Do NOT use:
- Obsidian wikilinks `[[Title]]` — use plain `[text](url)` instead
- Obsidian embeds `![[file]]`
- Obsidian callouts `> [!note]`
- Unicode bullets (`•`, `▪`) — use plain `-`

Indent nested bullets with **tabs** (matches vault convention — see
`Weekly/2026/2026-03-16.md` etc.).

**Frontmatter block is required** at the top of every draft (for
Obsidian vault compatibility — the same file is committed to the
vault). GitLab renders it as a table or ignores it silently,
so it does not break the copy-paste flow.

```markdown
---
title: "YYYY-MM-DD"
date: YYYY-MM-DD
source: cortex
---
```

Where `YYYY-MM-DD` is the **meeting Friday date** (same as filename).

### Top-level structure

All four sections are top-level bullet items, not headings:

```
- fix.
- feat.
- inbound.
- misc.
```

Tab-indent each sub-item one level under its section. Omit any empty
section entirely (do not print `- fix.` with no children).

### `fix.` format — flat list, MR link only

```
- fix.
	- [mr-title](mr-url)
	- [mr-title](mr-url)
```

No descriptions, no grouping. The MR title already says what was fixed.

### `feat.` format — grouped by Workplus issue, with descriptions

```
- feat.
	- <Workplus-title-verbatim> - ([<ISSUE-KEY>](<issue-url>))
		- [mr-title](mr-url): one-line description of what the MR does
		- [mr-title](mr-url): one-line description
			- sub-detail when the MR change is large
			- sub-detail
	- **[draft]** <experimental title> - ([<ISSUE-KEY>](<issue-url>))
		- [mr-title](mr-url): description
```

Rules:
- Group-heading bullet is plain text + parenthesized issue link.
  Title is **not** wrapped in `[...]` — intentional, so titles like
  `[webapi] morpheus: ...` don't collide with markdown link syntax.
- Each MR bullet: link + `:` + one-line description.
- **No prose narrative.** A bulleted list of MRs with descriptions is
  enough — if something needs more explanation, indent another level
  and list sub-items, don't write paragraphs.
- When a MR's change is genuinely large, tab-indent one more level and
  list the key sub-changes.

### `inbound.` format — this-week external work

```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → outcome
```

Rules:
- **MR review**: `[mr-title](mr-url)` — append ` / [KEY](issue-url)`
  only when the MR's commit messages carry a `Ref:` trailer.
- **wit issue**: `[wit#iid](url): topic → responded` (or `→ resolved`).
  Only list issues with a tonyhu note in this week's window (see
  Source C filter).
- **CSS ticket**: `[css#ticket-id](url): symptom → outcome`. Never
  include customer, colleague, or personal identifiers.
- No `(reviewed)` prefix — the link shape (MR URL vs `wit#` vs `css#`)
  already disambiguates.

### `misc.` format — your side projects, flat list

Two shapes depending on activity:

```
- misc.
	- [side-project vX.Y.Z](repo-root-url)               ← version bump
	- project-name: summary ([!NN](mr-url), [!MM](mr-url))  ← scattered MRs
```

Rules:
- If the side project had a version tag / release this week → link the
  repo root with the version as the title.
- If the side project only has scattered MRs (no release) → one line:
  `project: one-sentence summary` followed by comma-separated MR links
  in parentheses.
- One line per project. Do not break individual MRs onto their own
  top-level bullets.

### Full skeleton example

```markdown
---
title: "2026-04-17"
date: 2026-04-17
source: cortex
---

- fix.
	- [fix(...): ...](mr-url)
	- [fix(...): ...](mr-url)
- feat.
	- NextGen-Web-Core - ([DSM-167678](https://workplus.synology.inc/key/DSM/issues/167678))
		- [feat(nginx): ...](mr-url): adds nextweb upstream and flips `/` to proxy_pass
		- [chore(projects): ...](mr-url): register syno-nextweb in build list
	- **[draft]** [webapi] morpheus: webapi http server framework - ([DSM-172916](https://workplus.synology.inc/key/DSM/issues/172916))
		- [refactor(core): ...](mr-url): split god file into focused modules
- inbound.
	- [fix(fsdn): ...](mr-url) / [DSM-173132](https://workplus.synology.inc/key/DSM/issues/173132)
	- [wit#4432](wit-url): upgrade session-clear behaviour → responded
	- [css#3977379](css-url): db missing entry → repaired, closed
- misc.
	- [syno-build-mcp v0.9.0](https://git.synology.inc/tonyhu/syno-build-mcp)
	- synology-dev-kit: replaced polling with Monitor tool, extracted build workflow into skill ([!27](url), [!29](url), [!30](url))
```

**Present the draft to the user for review.** Do not write until user confirms.

## Step 7: Write and Commit

1. Write to `<vault_path>/Weekly/YYYY/YYYY-MM-DD.md`
2. Update `_index.md` Weekly section
3. `git add Weekly/ _index.md && git commit -m "weekly: YYYY-MM-DD"`
4. If `auto_push` is true in config: `git push`
