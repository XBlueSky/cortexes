---
name: cortex-query
description: >
  Search and retrieve content from the cortex vault. Use when the user says
  "查 cortex", "之前有記過", "cortex 裡有沒有", "check my notes",
  "what did I write about", or needs to find previously saved knowledge.
---

# Cortex Query — Search the Vault

Search the cortex Obsidian vault for relevant content.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Search Strategy (Layered)

### Layer 1: Index Search (fast, preferred)

1. Read `<vault_path>/_index.md`
2. Search the table rows for matching keywords in Note/Project names, tags, or summaries
3. Present matching entries to the user
4. If user wants details → read the linked file

### Layer 2: Full-Text Search (fallback)

If _index.md search finds nothing relevant:

1. Use Grep on `<vault_path>/Notes/` and `<vault_path>/Projects/` with `-i` for case-insensitive
2. Show matching files with brief excerpts
3. If user wants details → read the file

### Layer 3: Raw Search (archive)

If the user specifically asks about recent work or raw session data:

1. Grep `<vault_path>/Raw/` for the query
2. Show matches with date and repo context

## Response Format

- Use wikilink format when referencing notes: `[[note-name]]`
- If multiple matches, list them and ask which one the user wants to read
- For Weekly entries, show the date and summary line
