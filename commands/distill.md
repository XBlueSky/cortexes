---
name: distill
description: Distill raw session records into refined Notes and Projects
argument-hint: "[date range, e.g. 'this week' or '2026-04-08']"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

Use the cortex-distill skill to process unprocessed Raw/ files.

If the user provided a date argument, filter Raw files to that date range.
Otherwise, process all unprocessed files.

Follow the cortex-distill skill's full process: find unprocessed,
assess content, draft refined notes, get confirmation, mark processed,
update _index.md.
