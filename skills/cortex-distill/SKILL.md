---
name: cortex-distill
description: >
  Distill raw session records into refined Notes and Projects. Use when
  the user says "提煉", "整理 raw", "distill", "distill raw records",
  or when cortex-weekly invokes distill before compiling.
---

# Cortex Distill — Refine Raw Records

Extract valuable knowledge from Raw/ session dumps into Notes/ and Projects/.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Step 1: Find Unprocessed Raw Files

Find all Raw files that lack a `<!-- distilled:` marker:

```bash
grep -rL '<!-- distilled:' <vault_path>/Raw/ --include='*.md'
```

Show the pending list count and ask to proceed.

## Step 2: Stage 1 — Has Insight

For each unprocessed Raw file:

1. Read the full content.
2. Check `## Discoveries` or `## Decisions` sections.
   - No such sections → `no-insight`, go to Step 5 (mark) + Step 7 (log).
   - Sections exist → apply the **has_insight** rule below.

### `has_insight()` rule

Answer **Yes** iff at least one bullet in Discoveries or Decisions contains one of:

- A specific symbol / file path / line number (e.g. `src/main.rs:226`, `checkDockerImage()`, `SynoBuildConf/unit-test`).
- A specific bug mechanism or root-cause statement (e.g. "filter must fully match repository, substring not supported").
- A specific decision rationale in the form "X over Y because Z" — not bare "use X".

Answer **No** if the section contains only vague statements like "fixed it", "works now", "tested successfully" without concrete referents.

- Yes → proceed to Step 3 (Stage 2).
- No → `no-insight`, go to Step 5 (mark) + Step 7 (log).

### Three-filter tags (categorization hint, not a gate)

When has_insight is Yes, optionally tag the extracted content for later lint:

| Tag | Signal | Example |
|-----|--------|---------|
| 踩坑 (gotcha) | Non-obvious behavior, hidden trap | "jsoncpp returns null for oversized doubles" |
| 慣例 (convention) | Synology-specific or internal practice | "Drive uses AppPortal.json, MailClient uses API" |
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

Pick the **most content-ful Discovery or Decision bullet** as the query text (longest bullet with concrete referents). Run:

```bash
cortex-vec search "<bullet text>" --n 3
```

If the repo is known from Raw frontmatter, add `--repo <name>` when searching Projects-bound content.

Extract top-1 `score` from the JSON output.

If `cortex-vec` is unavailable (command errors, ECONNREFUSED, etc.): treat as `score = 0.0`, log `dedup_top1: unavailable`, prefer false-positive `new` over losing the insight.

### 3.3 Decide outcome

| Condition | Outcome |
|-----------|---------|
| score < `dedup_threshold_new` | `new` |
| `dedup_threshold_new` ≤ score < `dedup_threshold_pending` | interactive — ask user `(n)ew / (p)ending / (s)kip` |
| score ≥ `dedup_threshold_pending` | `pending-merge` |

**Escape hatch — `skip-routine`:** Independent of score. Triggered when Stage 1 passed on a symbol that turns out to be only a commit line with no surrounding analysis (e.g., a Raw that is essentially a git log dump plus a `"Discoveries"` bullet mentioning one file path). Use sparingly.

### 3.4 Dispatch

- `new` → go to Step 4 (create) + Step 5 + 6 + 7 + 8.
- `pending-merge` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only. **Do not write any new file or touch existing pages.**
- `skip-routine` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only.
- Interactive: user's choice governs the branch above. Specifically: `(n)ew` → `new`, `(p)ending` → `pending-merge`, `(s)kip` → `skip-routine` (treat as escape-hatch equivalent; marker is `(skip: routine)`).

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

## Step 5.5: Write Summary File

For **every** Raw processed in this run — regardless of outcome (`new`,
`pending-merge`, `skip-routine`, `no-insight`) — write a summary sidecar
file. The summary is consumed by `cortex-weekly` Source A; it is NOT
indexed by `cortex-vec` and NOT listed in `_index.md`.

### 5.5.1 Compose the summary

The summary is a prose-only paragraph describing what the session was
about — work done, what shipped, non-obvious findings. Guideline:

- 1–5 sentences, roughly 60–300 characters (soft target; a session that
  genuinely needs 400 characters to be coherent gets 400).
- **Do NOT** enumerate commits, MR URLs, or issue keys. Those are
  GitLab's canonical territory (`cortex-weekly` Source B). Weekly joins
  MRs to summaries by repo + date, not by URL-string matching inside
  the summary prose.
- **Do NOT** repeat deep-dive content that this distill run wrote into
  Notes/Projects. Summary is "session view"; Notes/Projects is
  "topic view".
- For sessions with no commits / no shipped output, describe honestly
  ("探索 X 的行為、未產出代碼" / "reviewed Y MR, no self-authored
  commits").
- For `no-insight` outcome: still produce a summary. Weekly cares about
  sessions that didn't yield insights but still represent work hours.

### 5.5.2 Compose the frontmatter

Fixed 3-field schema, no other fields:

```yaml
---
raw: <vault-relative path to the source Raw file>
repo: <value from Raw frontmatter `repo:` field, or `(none)` if absent>
distilled: <today, YYYY-MM-DD>
---
```

### 5.5.3 Write the sidecar file

Destination path: `<vault_path>/Summary/YYYY/MM/DD/<same-filename-as-Raw>.md`
(mirror Raw's date tree, identical filename).

Use the Write tool. If the file already exists (re-distill case),
**overwrite** it — no merge, no append. The Write tool's overwrite
semantics are the intended behavior here.

Create parent directories as needed (the Write tool handles this).

### 5.5.4 Stage for commit

The sidecar file is added to git in Step 8's `git add` list (see Step 8).
No extra commit here.

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
git add Raw/ Notes/ Projects/ Summary/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`.

## Step 9: Ask — Broadcast Now?

For each Raw where the terminal outcome was `new` or `pending-merge` (i.e.,
broadcast-eligible), prompt the user once before moving to the next Raw:

```
Raw <filename> processed (outcome: <outcome>). Broadcast now? (y/n/l)
  y = enter broadcast conversation immediately
  n = decline (mark as no-broadcast; will not re-prompt later)
  l = later (stays in broadcast-eligible queue)
```

### Dispatch

- **y** → dispatch to the `cortex-broadcast` skill for this single Raw. When
  broadcast completes, return here and move to the next unprocessed Raw.
- **l** → no action. The Raw's Phase 1 marker is unchanged; it is
  automatically eligible for later `/cortex:broadcast` invocation.
- **n** → append a terminal segment to the Raw's marker using the Edit
  tool. Transform:
  - `<!-- distilled: YYYY-MM-DD → <path> -->`
    becomes
    `<!-- distilled: YYYY-MM-DD → <path> | no-broadcast: <today> -->`
  - `<!-- distilled: YYYY-MM-DD → pending-merge: <path> (<score>) -->`
    becomes
    `<!-- distilled: YYYY-MM-DD → pending-merge: <path> (<score>) | no-broadcast: <today> -->`

Date format: `YYYY-MM-DD`.

For outcomes `skip-routine` and `no-insight`, do not prompt — those Raws
are ineligible by definition.

If the `n` path ran, stage the Raw and amend into the existing batch commit
for this distill run (or, if the commit already closed, make a follow-up
commit `chore(distill): record no-broadcast declines`).
