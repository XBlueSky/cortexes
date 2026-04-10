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

Default to the current week. Ask if the user wants a different week.
Calculate:
- ISO week: `YYYY-WXX`
- Week Monday date: `YYYY-MM-DD` (used for the output filename)
- Date range for queries

## Step 2: Run Distill

Invoke the cortex-distill skill to process any unprocessed Raw/ files
from the target week before compiling the weekly report.

## Step 3: Collect Sources

### Source A: Raw/

Glob `<vault_path>/Raw/YYYY/MM/DD/` for files within the target week's date range.
Read each file — extract commits, discoveries, decisions, other work.

### Source B: GitLab Activity

Use GitLab MCP tools to fetch the user's (from config `weekly.gitlab_username`) activity:
- Merged MRs
- Commits pushed
- MR reviews done

For each MR, collect: title, URL, target repo.

### Source C: CSS Tickets

Use robinhood MCP `css_get_activities` to fetch CSS ticket activity for the week.
For each ticket: ticket number, URL, brief description, resolution/status.

## Step 4: Merge and Deduplicate

1. Start with Raw/ entries as the base
2. For each GitLab MR:
   - If same MR URL exists in Raw → keep Raw's description
   - If MR not in Raw → add it
3. Add CSS tickets to misc section

## Step 5: Classify

| Category | Criteria |
|----------|----------|
| `fix.` | Commit type = fix, or MR title starts with fix |
| `feat.` | Commit type = feat, or MR title starts with feat |
| `misc.` | Everything else: CSS tickets, reviews, chore, refactor, docs, helping colleagues |

## Step 6: Generate Draft

Format as:

```markdown
---
title: "YYYY-MM-DD"
date: YYYY-MM-DD
source: cortex
---

- fix.
	- [commit-or-MR-title](MR-URL)
- feat.
	- [commit-or-MR-title](MR-URL)
- misc.
	- [css#XXXXXXX](https://cssnew.synology.com/ticket/XXXXXXX): description → conclusion
	- colleague(topic): what was done
```

**Present the draft to the user for review.** Do not write until user confirms.

## Step 7: Write and Commit

1. Write to `<vault_path>/Weekly/YYYY/YYYY-MM-DD.md`
2. Update `_index.md` Weekly section
3. `git add Weekly/ _index.md && git commit -m "weekly: YYYY-MM-DD"`
