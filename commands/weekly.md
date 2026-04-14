---
name: weekly
description: Compile weekly report from Raw/, GitLab activity, and CSS tickets
argument-hint: "[week, e.g. 2026-W15 or 'last week']"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Agent
skills:
  - cortex-weekly
  - cortex-distill
---

Use the cortex-weekly skill to compile the weekly report.

If the user provided a week argument, use that week.
Otherwise, default to the current week.

Follow the cortex-weekly skill's full process: run distill first,
collect sources, merge, deduplicate, classify, generate draft,
get user confirmation, then write the final report.
