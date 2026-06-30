---
name: takeoff
description: Create, resume, or clear a session hand-off baton for this repo
argument-hint: "[resume|done]"
allowed-tools:
  - Read
  - Write
  - Bash
skills:
  - cortex-takeoff
---

Use the cortex-takeoff skill.

- No argument: create (curate the current session into this repo's baton).
- `resume`: load this repo's pending baton and continue (do not delete it).
- `done`: clear this repo's baton.

Follow the skill's full process, including the `takeoff.sh prepare` git-safety
preflight before writing.
