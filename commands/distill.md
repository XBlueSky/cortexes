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

Invoke the `cortexes:cortex-distill` skill and follow it for the whole run.
Command frontmatter cannot load a skill for you, so invoke it explicitly with
its fully qualified name via the Skill tool.

If the user provided a date argument, filter Raw files to that date range.
Otherwise, process all unprocessed files.

Follow the cortex-distill skill's full process: find unprocessed,
assess content, draft refined notes, get confirmation, mark processed,
update _index.md.
