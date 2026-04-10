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

1. Read `~/.cortex/distill-state.json` (local cache)
2. Glob `<vault_path>/Raw/` for all `.md` files
3. For each file:
   - In distill-state.json → skip (fast path)
   - Not in distill-state.json → read file, grep `<!-- distilled:`
     - Has marker → already processed, add to distill-state.json
     - No marker → unprocessed, add to pending list
4. Show user the pending list count and ask to proceed

## Step 2: Process Each Raw File

For each unprocessed Raw file:

1. Read the full content
2. Assess: does it contain knowledge worth persisting in Notes or Projects?
   - Technical discovery, root cause, debugging insight → Notes
   - Architecture decision, project progress → Projects
   - Routine commits with no notable insight → skip (just mark as processed)
3. If worth persisting:
   - Draft the refined content
   - Present to user for confirmation
   - Write to Notes/<category>/<title>.md or Projects/<repo>/<title>.md
   - Use Obsidian Flavored Markdown (wikilinks, frontmatter, callouts)

## Step 3: Mark as Processed

After processing (whether content was extracted or skipped):

1. Append marker to the Raw file (works with any format):
   ```
   <!-- distilled: YYYY-MM-DD → Notes/path.md -->
   ```
   or if nothing was extracted:
   ```
   <!-- distilled: YYYY-MM-DD → (no extractable content) -->
   ```
2. Update `~/.cortex/distill-state.json`:
   - Add file path to `processed` array
   - Update `last_distill` timestamp

## Step 4: Update _index.md

For each new Note or Project file created:

1. Read `<vault_path>/_index.md`
2. Append a row to the appropriate table section (Projects or Notes)
3. Format: `| [[title]] | tags | one-line summary |`
4. Update the `entries` count in frontmatter
5. Update the `updated` date in frontmatter

## Step 5: Commit

```
git add Raw/ Notes/ Projects/ _index.md
git commit -m "distill: extract N entries from Raw"
```

If `auto_push` is true in config: `git push`
