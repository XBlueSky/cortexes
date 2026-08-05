---
name: takeoff
description: Create, resume, or clear a session hand-off baton (one per work line)
argument-hint: "[topic | resume [topic] | done [topic]]"
allowed-tools:
  - Read
  - Write
  - Bash
skills:
  - cortex-takeoff
---

Use the cortex-takeoff skill.

- No argument or `<topic>`: create — curate the current session into that
  work line's baton (without a topic the skill reuses or derives one).
- `resume [topic]`: load a pending baton and continue (do not delete it).
- `done [topic]`: clear a baton (soft-delete; defaults to the baton this
  session resumed, otherwise refuses and lists the candidates).

Follow the skill's full process, including the `takeoff.sh prepare`
git-safety preflight before writing and the explicit-cwd rule for every
takeoff.sh call.
