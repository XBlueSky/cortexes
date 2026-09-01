---
name: broadcast
description: Run broadcast on a distilled Raw — update related existing pages conversationally
argument-hint: "[raw-path | --list]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

Invoke the `cortexes:cortex-broadcast` skill and follow it for the whole run.
Command frontmatter cannot load a skill for you, so invoke it explicitly with
its fully qualified name via the Skill tool.

Argument handling:

- No argument → process the oldest eligible Raw (FIFO from the queue).
- `--list` → print the eligible queue and exit; do not run any broadcast.
- `<raw-path>` → target the specified Raw. Accepts absolute or
  vault-relative paths. Abort with a clear error if the Raw is not
  eligible (already broadcast, declined, or never distilled).

Follow the cortex-broadcast skill's full flow: queue build, Raw selection,
vec-search candidates, menu confirmation, per-page conversation with
contradiction handling, per-page commits, marker + log finalization.
