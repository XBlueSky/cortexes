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

Include issues where the user responded or resolved them.
Format: `[wit#issue-iid](issue-url): question topic → responded / resolved`
- Concise, one line per issue
- Goes into `misc.`

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
3. Add GitLab issues (responded/resolved) to misc section
4. Add CSS tickets to misc section

## Step 5: Classify

Classification is based on **whether the commit/MR has a Workplus issue ref**:

| Category | Criteria |
|----------|----------|
| `fix.` | Has issue ref + commit type = fix |
| `feat.` | Has issue ref + commit type = feat |
| `misc.` | No issue ref (side projects), CSS tickets, reviews, chore, docs |

Key rules:
- **Issue ref present** → always `fix.` or `feat.` (these are Synology work)
- **No issue ref** → always `misc.` (side projects like syno-build-mcp, etc.)
- **CSS tickets** → always `misc.`
- `feat.` entries are **grouped by theme/Workplus issue**, not listed individually

### Resolve Workplus issue titles

For every unique issue key found in `fix.` and `feat.`, call the Workplus
MCP tool `get_issue` to fetch the real `title`. Use this exact title
verbatim in the group heading — **do not paraphrase, summarize, or
invent a "short theme name"**. See Step 6 for the exact heading format.

Cache the title → reuse for all MRs under the same issue.

### Experimental repos (draft label)

Read `weekly.experimental_repos` from `~/.cortex/config.json`. This is a
list of `namespace/project` strings (e.g. `["wit/morpheus"]`).

Rule for the `[draft]` label:
- Build the group of MRs for each issue ref
- If **every** MR in the group has its target repo in `experimental_repos`
  → prefix the group heading with `**[draft]**` (bold, literal text)
- If the group mixes experimental and non-experimental repos → no label
  (it is already a real feature)
- Same rule applies to `fix.` entries if they are experimental

## Step 6: Generate Draft

The draft is **copy-pasted into a GitLab issue/MR description**
(e.g. wit/reports), so output must be **valid GitLab Flavored Markdown
(GFM)**. Do NOT use:
- Obsidian wikilinks `[[Title]]` — use plain `[text](url)` instead
- Obsidian embeds `![[file]]`
- Obsidian callouts `> [!note]`
- Tabs for indentation — use **2 spaces** per nesting level
- Unicode bullets (`•`, `▪`) — use plain `-`

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

### Group heading format (`fix.` and `feat.`)

```
<Workplus-title-verbatim> - ([<ISSUE-KEY>](<issue-url>))
```

- Title is **plain text**, not wrapped in `[...]` — intentional, so
  titles like `[webapi] morpheus: webapi http server framework` do
  not collide with markdown link syntax
- Issue key + URL sit inside `[...](...)` wrapped in parentheses
- If the group qualifies for the draft label (Step 5 "Experimental
  repos"), prefix the heading with `**[draft]** ` (bold, trailing space)

Examples:
```
### NextGen-Web-Core - ([DSM-167678](https://workplus.synology.inc/key/DSM/issues/167678))

### **[draft]** [webapi] morpheus: webapi http server framework - ([DSM-172916](https://workplus.synology.inc/key/DSM/issues/172916))
```

### `feat.` narrative requirement

Each `feat.` group **must** begin with a 2–4 sentence prose summary
describing what was achieved at the feature level — not just a list
of MRs. The narrative should:

- Name the theme/goal (what is this feature actually doing?)
- Summarize how the MRs collectively achieve the goal
- Flag anything unusual (trade-offs, deferred work, what it unblocks)

Think "I'm standing up in the weekly meeting and have 30 seconds to
explain what we did for this feature." The MR list underneath is
supporting evidence, not the headline.

`fix.` groups do **not** require narrative — one-line MR description
per item is enough.

### Full draft layout

```markdown
---
title: "YYYY-MM-DD"
date: YYYY-MM-DD
source: cortex
---

## fix.

### <Group heading format>

- [MR-title](MR-URL): one-line what was fixed

## feat.

### <Group heading format>

<2–4 sentence narrative: what this feature achieves, how the MRs
combine, any trade-offs or deferred work>

- [MR-title](MR-URL): specific change
- [MR-title](MR-URL): specific change

### **[draft]** <Group heading format for experimental group>

<narrative — same 2–4 sentence requirement even for draft>

- [MR-title](MR-URL): specific change

## misc.

- side-project-name: one-line summary of recent changes across
  [!NN](MR-url), [!MM](MR-url)
- [project#issue-id](issue-url): question topic → responded / resolved
- [css#XXXXXXX](https://cssnew.synology.com/ticket/XXXXXXX): symptom → outcome
```

### `misc.` rules

`misc.` is a **flat bullet list** — no H3 sub-headings, no narrative
paragraphs, no nested MR lists. Each line stands alone.

- Side projects: **one line per project** summarizing all activity.
  **Do not list individual commits or MRs on separate lines.** Include
  comma-separated MR links inline if merged, e.g.
  `synology-dev-kit: replaced polling with Monitor tool, added shared reference ([!27](url), [!29](url), [!30](url))`
- GitLab issues (responded/resolved): `[project#iid](url): topic → action`
- CSS tickets: `[css#XXXXXXX](url): symptom → outcome` — no names

The rationale: `misc.` is the "side stuff" bucket — it should scan
quickly in the weekly meeting, not compete for attention with the real
features in `feat.`. Anything that deserves its own narrative belongs
in `feat.` or `fix.`, not here.

**Present the draft to the user for review.** Do not write until user confirms.

## Step 7: Write and Commit

1. Write to `<vault_path>/Weekly/YYYY/YYYY-MM-DD.md`
2. Update `_index.md` Weekly section
3. `git add Weekly/ _index.md && git commit -m "weekly: YYYY-MM-DD"`
4. If `auto_push` is true in config: `git push`
