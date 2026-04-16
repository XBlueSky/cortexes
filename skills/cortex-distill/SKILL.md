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

## Step 2: Assess Value

For each unprocessed Raw file:

1. Read the full content
2. Check if it has `## Discoveries` or `## Decisions` sections with content
   - No such sections → **skip** (mark as processed with no extractable content)
   - Has sections → apply the three-filter criteria

### Three-Filter Criteria

| Category | What to look for | Example |
|----------|-----------------|---------|
| **踩坑知識 (Gotchas)** | Non-obvious behavior, hidden traps, root causes | "jsoncpp returns null for oversized doubles instead of throwing" |
| **內部慣例 (Internal conventions)** | Synology-specific practices, internal API quirks | "subdomain: Drive uses AppPortal.json, MailClient uses API" |
| **關鍵決策 (Key decisions)** | Why A over B, trade-offs, decisions that will be forgotten | "Use build-history.json vs PID check because..." |

- Matches any criterion → **extract** (proceed to Step 3)
- Matches none → **skip** (routine knowledge already in code/commits)

### What to skip (not worth extracting)

- Routine commits (fix is in the code, commit message has context)
- General programming knowledge (Google-able)
- Tool/plugin configuration (changes frequently, in config files)
- Records that only say "what was done" without insight

## Step 3: Deduplication Check

Before creating a new note:

1. Run: `cortex-vec search "<discovery text>" --n 3`
2. Check results:
   - **Score > 0.85** → High overlap. Show existing note. Suggest: merge, skip, or create anyway.
   - **Score 0.70-0.85** → Possible overlap. Show to user for judgment.
   - **Score < 0.70** → New knowledge. Proceed to create.

## Step 4: Create Refined Note

1. Draft the refined content
2. Determine placement:
   - Repo-specific knowledge → `Projects/<repo>/` (repo from Raw file's `repo:` frontmatter)
   - General technical knowledge → `Notes/<category>/` (match existing categories)
3. Add `repos:` to frontmatter if repo-specific
4. Present draft to user for confirmation
5. Write to vault using Obsidian Flavored Markdown (wikilinks, frontmatter, callouts)

## Step 5: Mark as Processed

1. Append marker to Raw file:
   ```
   <!-- distilled: YYYY-MM-DD → Notes/path.md -->
   ```
   or if skipped:
   ```
   <!-- distilled: YYYY-MM-DD → (no extractable content) -->
   ```

## Step 6: Update Index

For each new file created:

1. Run: `cortex-vec upsert <relative-path>`
2. Update `_index.md`: append row, update entries count and date

## Step 7: Commit

```
git add Raw/ Notes/ Projects/ _index.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`
