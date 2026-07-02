---
name: cortex-distill
description: >
  Distill raw session records into refined Notes and Projects. Use when
  the user says "提煉", "整理 raw", "distill", or "distill raw records".
---

# Cortex Distill — Refine Raw Records

Extract valuable knowledge from Raw/ session dumps into Notes/ and Projects/.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Step 1: Find Unprocessed Raw Files

List the distill queue:

```bash
cortex-vec distill-queue --root <vault_path>/Raw
```

This is **position-anchored**: a Raw counts as distilled only if a
`<!-- distilled: ... -->` marker appears in its header (before the first
`### User` turn) **or** as its last non-empty line. Do **NOT** `grep` the
marker string — a pipeline meta-session's body quotes it dozens of times
(it printfs markers onto other files), so `grep -rL '<!-- distilled:'`
silently drops genuine work from the queue. To check one file, use
`cortex-vec raw-state <file>`.

Show the pending list count and ask to proceed.

## Step 2: Stage 1 — Has Insight

For each unprocessed Raw file:

1. Read the full content (frontmatter + transcript + any inline analysis).
2. Apply `has_insight()` judgment to the **entire body**. Do NOT gate on
   the presence of specific section headers — insight may live anywhere
   in the Raw.

### `has_insight()` rule

Answer **Yes** iff at least one passage anywhere in the Raw contains one of:

- A specific symbol / file path / line number (e.g. `src/main.rs:226`, `checkDockerImage()`, `SynoBuildConf/unit-test`).
- A specific bug mechanism or root-cause statement (e.g. "filter must fully match repository, substring not supported").
- A specific decision rationale in the form "X over Y because Z" — not bare "use X".

Insight commonly appears in any of these locations; treat them all as
first-class:

- `★ Insight ─────` callouts inside `### Claude` blocks (Claude Code
  learning-mode output).
- Tables comparing options, summarizing a bug, or laying out an attack
  chain.
- Prose paragraphs that walk through analysis, root cause, or
  trade-off rationale.
- Legacy `## Discoveries` / `## Decisions` sections (manually-edited
  Raws — still valid but not required).

Answer **No** only when the entire Raw genuinely lacks concrete
referents — e.g., commands executed with no surrounding analysis, or
vague statements like "fixed it" / "works now" / "tested successfully"
without any mechanism / file / symbol / decision rationale anywhere in
the body.

### Present judgment to user (mandatory)

The `has_insight()` result above is a **candidate verdict**, not a
dispatch decision. **Always present the candidate to the user and wait
for confirmation**, even when the verdict feels obvious. The user's
answer is binding regardless of the agent's tilt.

Use `AskUserQuestion` with:

- **Evidence**: 1–3 concrete excerpts from the Raw supporting the
  candidate (file:line, ★ Insight callout, decision rationale, table,
  etc.). When the candidate is `No`, note explicitly that no concrete
  referent was found anywhere in the body.
- **Candidate verdict**: `Yes (has insight)` or `No (no insight)`.
- **Options**:
  - `(y)es — agree with candidate`
  - `(n)o — override to opposite`
  - `(s)kip-routine — Raw not worth dedup nor recording` (use when the
    Raw is essentially a tool-recap / git-log dump that technically
    passed `has_insight` on a symbol but has no surrounding analysis)

### Dispatch on user's answer

- User confirms `Yes` → proceed to Step 3 (Stage 2).
- User confirms `No` → `no-insight`, go to Step 5 (mark) + Step 7 (log).
- User picks `skip-routine` → `skip-routine`, go to Step 5 + 7 + 8.
  No broadcast prompt (Step 9 is skipped for skip-routine).

### Three-filter tags (categorization hint, not a gate)

When has_insight is Yes, optionally tag the extracted content for later lint:

| Tag | Signal | Example |
|-----|--------|---------|
| 踩坑 (gotcha) | Non-obvious behavior, hidden trap | "jsoncpp returns null for oversized doubles" |
| 慣例 (convention) | Project-specific or internal practice | "Service A reads config.json, Service B reads env vars" |
| 決策 (decision) | Why A over B, trade-off rationale | "build-history.json over PID check because..." |

These tags no longer gate extraction — they are reserved metadata for future lint capability. Safe to omit if the use case is unclear; downstream tooling treats absence as untagged.

## Step 3: Stage 2 — Decide Placement

Only runs when Stage 1 returned Yes.

### 3.1 Load thresholds

Read `~/.cortex/config.json`:

```bash
jq -r '.distill.dedup_threshold_new // 0.45' ~/.cortex/config.json
jq -r '.distill.dedup_threshold_pending // 0.60' ~/.cortex/config.json
```

Defaults: `new = 0.45`, `pending = 0.60`.

### 3.2 Query dedup

Pick the **most content-ful insight passage** anywhere in the Raw as the
query text — typically the densest `★ Insight ─────` callout, the
clearest analysis paragraph naming specific referents, or (for legacy
Raws) the longest Discovery/Decision bullet. Aim for one self-contained
chunk that mentions the concrete symbol / mechanism / decision; trim
to roughly one paragraph. Run:

```bash
cortex-vec search "<bullet text>" --n 3
```

If the repo is known from Raw frontmatter, add `--repo <name>` when searching Projects-bound content.
`--repo` narrows the `Projects/` partition only; cross-repo `Notes/` always appear in results regardless of the filter. Safe to add when the Raw is repo-specific.

Extract top-1 `score` from the JSON output.

If `cortex-vec` is unavailable (command errors, ECONNREFUSED, etc.): treat as `score = 0.0`, log `dedup_top1: unavailable`, prefer false-positive `new` over losing the insight.

### 3.3 Present score + candidate outcome to user (mandatory)

**Always ask the user**, regardless of where score falls. The threshold
table below degrades from gate to *candidate-outcome heuristic* — it
shapes the recommendation the agent surfaces, but never decides
unilaterally.

Use `AskUserQuestion` with:

- **Score**: two decimals (e.g. `0.62`).
- **Top-1 hit**: `[[wikilink]]` + ≤1-line excerpt from that page.
- **Candidate outcome**: chosen per the heuristic table below.
- **Options**: `(n)ew / (p)ending-merge / (s)kip-routine`.

| Score band | Candidate outcome to propose |
|------------|------------------------------|
| `score < dedup_threshold_new` | `new` (low overlap with existing pages) |
| `dedup_threshold_new ≤ score < dedup_threshold_pending` | describe both `new` and `pending-merge` neutrally; no strong tilt |
| `score ≥ dedup_threshold_pending` | `pending-merge` (strong overlap with top-1) |

**When to tilt toward `skip-routine`** (independent of score): the Raw
passed Stage 1 only because of an isolated symbol mention with no
surrounding analysis — e.g., a git-log dump that happens to name a file
path. Surface `(s)kip-routine` as a real candidate in such cases rather
than forcing `new` / `pending-merge`.

### 3.4 Dispatch on user's answer

- `(n)ew` → go to Step 4 (create) + Step 5 + 6 + 7 + 8.
- `(p)ending-merge` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only.
  **Do not write any new file or touch existing pages.**
- `(s)kip-routine` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only.
  Marker writes as `(skip: routine)`.

## Step 4: Create Refined Note

1. Draft the refined content
2. Determine placement:
   - Repo-specific knowledge → `Projects/<repo>/` (repo from Raw file's `repo:` frontmatter)
   - General technical knowledge → `Notes/<category>/` (match existing categories)
3. Add `repos:` to frontmatter if repo-specific
4. Present draft to user for confirmation
5. Write to vault using Obsidian Flavored Markdown (wikilinks, frontmatter, callouts)

## Step 5: Mark Raw as Processed

Append exactly one marker to the Raw file, chosen by Step 3 outcome:

| Outcome | Marker |
|---------|--------|
| `new` | `<!-- distilled: YYYY-MM-DD → <target-relative-path> -->` |
| `pending-merge` | `<!-- distilled: YYYY-MM-DD → pending-merge: <existing-path> (<score>) -->` |
| `skip-routine` | `<!-- distilled: YYYY-MM-DD → (skip: routine) -->` |
| `no-insight` | `<!-- distilled: YYYY-MM-DD → (no insight) -->` |

Score formatting: two decimal places (e.g., `0.62`, not `0.62345`).
Date: today, `YYYY-MM-DD`.

## Step 6: Update Index (only for `new` outcome)

Skip this step entirely for `pending-merge`, `skip-routine`, `no-insight`.

For each newly created file:

1. Run: `cortex-vec upsert <relative-path>`
2. Update `_index.md`: append row to the appropriate table (Notes or Projects section), update `entries` count and `updated` date in frontmatter.

## Step 7: Append Log Entry

For each Raw processed (regardless of outcome), append exactly one entry to `<vault>/log.md`:

```markdown
## [YYYY-MM-DD HH:MM] distill | <raw-filename>
- outcome: <new|pending-merge|skip-routine|no-insight>
- target: <vault-relative path | omit for skip-routine and no-insight>
- dedup_top1: <score → [[wikilink]] | "unavailable" | omit for no-insight>
- repo: <value from Raw frontmatter repo: field | "(none)">
```

The agent should:

1. Compose the entry text with all placeholders substituted (today's date/time, the raw filename, the outcome, the target path, the score, the wikilink, the repo).
2. Append it to `<vault>/log.md` using either the Edit tool (preferred — adds the entry and preserves file integrity) or bash:

```bash
printf '\n%s\n' "$ENTRY" >> "<vault>/log.md"
```

Where `$ENTRY` is the fully-substituted markdown entry.

Preserve exactly one blank line between entries (achieved by the leading `\n` in the printf above, or by ensuring the Edit tool's new content starts with a blank line when appending).

Field rules:

- `target`: present for `new` and `pending-merge`. Omit the line for `skip-routine` and `no-insight`.
- `dedup_top1`: include the score and top-1 page wikilink whenever Stage 2 ran (outcomes: `new` when score was computed, `pending-merge`, all interactive choices, `skip-routine`). Omit only for `no-insight` (Stage 2 did not run). For `cortex-vec` unavailable, write `dedup_top1: unavailable`.
- `repo`: use `(none)` if the Raw has no `repo:` frontmatter field.

## Step 8: Commit

```bash
cd <vault>
git add Raw/ Notes/ Projects/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`.

## Step 9: Broadcast (always, inline)

For each Raw whose terminal outcome was `new` or `pending-merge`,
**dispatch to the `cortex-broadcast` skill inline** immediately after
Step 8's commit. Do not prompt the user — every broadcast-eligible Raw
is broadcast.

Announce before dispatching:

```
Dispatching broadcast for <raw-filename>...
```

When broadcast completes, return here and move to the next unprocessed
Raw.

For outcomes `skip-routine` and `no-insight`, broadcast is skipped by
definition (those Raws are ineligible).

### Escape hatch lives inside broadcast, not here

The broadcast skill carries its own abort semantics — there is no gate
at this layer:

- Inside broadcast Step 7 (candidate menu): user types `quit` to abort
  before any page commits. The Raw stays in the broadcast-eligible
  queue (no `| broadcast:` marker is written), so it can be picked up
  by a future standalone `/cortex:broadcast` run.
- Inside broadcast Step 8 (per-page conversation): user types `abort`
  / `cancel` to end the session. Prior committed pages stand; the Raw
  marker is left unchanged.

To opt out entirely at the very first prompt broadcast surfaces, the
user just types `quit` at the Step 7 menu.

### Backward compatibility

Raws historically marked `| no-broadcast: <date>` (from the previous
prompt-based gate design) are still filtered out by cortex-broadcast
Step 2's queue builder. This skill no longer produces that marker, but
it remains a recognized legacy opt-out signal.
