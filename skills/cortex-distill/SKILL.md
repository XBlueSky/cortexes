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

These tags no longer gate extraction — they are metadata that helps Phase 3 lint query "show me all 決策 with no xref".

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
| Pure commit dump / tool recap with no analysis | `skip-routine` (escape hatch) |

Use `skip-routine` sparingly — only when Stage 1 passed on a symbol that turned out to be only a commit line with no surrounding analysis.

### 3.4 Dispatch

- `new` → go to Step 4 (create) + Step 5 + 6 + 7 + 8.
- `pending-merge` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only. **Do not write any new file or touch existing pages.**
- `skip-routine` → skip Steps 4 and 6; go to Step 5 + 7 + 8 only.
- Interactive: user's choice governs the branch above.

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

Append using:

```bash
cat >> <vault>/log.md <<'EOF'

## [$(date '+%Y-%m-%d %H:%M')] distill | <raw-filename>
- outcome: <outcome>
- target: <path>
- dedup_top1: <score> → [[<title>]]
- repo: <repo>
EOF
```

Note the leading blank line inside the heredoc — preserves separation from the previous entry.

Field rules:

- `target`: present for `new` and `pending-merge`. Omit the line for `skip-routine` and `no-insight`.
- `dedup_top1`: omit for `no-insight` (Stage 2 did not run). For `pending-merge` and interactive → pending, include the score and wikilink of the matched page. For `skip-routine`, include the score even though no write happened.
- `repo`: use `(none)` if the Raw has no `repo:` frontmatter field.

## Step 8: Commit

```bash
cd <vault>
git add Raw/ Notes/ Projects/ _index.md log.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`.
