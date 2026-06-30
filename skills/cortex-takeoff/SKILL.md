---
name: cortex-takeoff
description: >
  Create or resume a session takeoff baton — a curated, ephemeral, git-ignored
  hand-off note that lets the next Claude session continue a long-running task.
  Use when the user says "交接", "takeoff", "交棒", "context 快滿了交接給下個
  session", "hand off to next session", "/cortex:takeoff", "takeoff resume",
  or "takeoff done". The baton is scaffolding, not knowledge: it is never
  committed, distilled, broadcast, or indexed.
---

# Cortex Takeoff — Session Hand-off Baton

A baton is a curated continuation note for ONE repo's work line. It lives at
`<vault>/.takeoff/<repo-slug>.md`, is git-ignored, and is consumed by the next
session. It is independent of the Raw session dump (which SessionEnd writes
automatically). Do NOT commit it, distill it, broadcast it, index it with
`cortex-vec`, or log it to `log.md`.

## Locating takeoff.sh

The repo slug and git-safety are handled by `takeoff.sh`, bundled in this plugin
at `hooks/scripts/takeoff.sh`. In every mode below, FIRST set `TK` to that helper,
resolved relative to THIS skill's base directory. The skill-load message announces
the base directory as `<...>/cortex/<version>/skills/cortex-takeoff`; `takeoff.sh`
sits two levels up. Substitute the actual announced base-dir path:

```bash
TK="<skill-base-dir>/../../hooks/scripts/takeoff.sh"
test -f "$TK" || { echo "cortex: takeoff.sh not found at $TK" >&2; exit 1; }
```

Do NOT use `claude plugin root` (no such subcommand) or `$CLAUDE_PLUGIN_ROOT`
(unset for skill-run bash).

## Mode

Determined by the command argument:

| Argument | Mode |
|----------|------|
| (none)   | **create** — write/overwrite this repo's baton |
| `resume` | **resume** — load this repo's baton (do not delete) |
| `done`   | **done** — clear this repo's baton |

## Create (no argument)

1. Set `TK` as described in "Locating takeoff.sh" above, then run the preflight
   (it also derives the slug and guarantees git-safety):

   ```bash
   baton_path="$(bash "$TK" prepare)"
   ```

   If it exits non-zero, STOP and relay the message — do not write anything.
   (Exit 2 = no vault / no repo; exit 3 = `.takeoff/` not git-ignored.)

2. Curate the current session into a hand-off. Content is free-form — write
   whatever genuinely lets a fresh session continue without re-deriving
   context. Typically worth capturing: the goal, what's done so far, the
   immediate next step, key files and locations (`path:line`), open questions,
   and gotchas. Omit anything not useful; do not pad to a template.

3. Compose one `summary` line (used verbatim as the SessionStart menu preview):
   a single sentence naming the work line and the next step.

4. Write the baton to `baton_path` with the Write tool:

   ```markdown
   ---
   repo: <slug>
   created: <YYYY-MM-DDTHH:MM:SS>
   summary: <one sentence: this work line / next step>
   ---
   <free-form curation body>
   ```

   If a baton already exists for this repo, this overwrites it (the
   "one active baton per repo, new replaces old" model).

5. Confirm to the user: baton written to `<baton_path>`, not committed.

## Resume (`resume`, or chosen from the SessionStart menu)

1. Locate it: `bash "$TK" path` → `baton_path`.
2. If the file does not exist, tell the user there is no pending baton for this
   repo and stop.
3. `Read` the baton in full, adopt it as continuation context, and pick the
   work up from its next step. **Do NOT delete it** — loading is not
   completion; this session may itself need to hand off again.

## Done (`done`)

1. Run `bash "$TK" clear` to remove this repo's baton.
2. Confirm to the user that the baton was cleared.

## Overwrite vs done

- Re-running create replaces the baton (normal re-hand-off).
- `done` is the explicit "this work line is finished, clear the baton" exit.
- Merely loading via `resume` never clears it.
