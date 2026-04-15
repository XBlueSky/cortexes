---
name: cortex-query
description: >
  Search and retrieve content from the cortex vault. Use when the user says
  "查 cortex", "之前有記過", "cortex 裡有沒有", "check my notes",
  "what did I write about", or needs to find previously saved knowledge.
---

# Cortex Query — Search the Vault

Search the cortex Obsidian vault using semantic search.

## Resolve Vault Path

Read `~/.cortex/config.json` to get `vault_path`.
If the file doesn't exist, tell the user to run `/cortex:genesis` first.

## Search Strategy (Layered)

### Layer 1: Vector Search (primary)

Use `cortex-vec` for semantic search:

```bash
cortex-vec search "<query>" --n 5
```

`cortex-vec` is installed as a CLI tool (via pip).

**Context-aware filtering:** If the current session is inside a git repo,
detect the repo name and add `--repo` filter as default scope:

```bash
cortex-vec search "<query>" --repo <detected-repo> --n 5
```

The user can override this by saying "search all" or "search across everything".

**Additional filters:** Apply when the user specifies:
- `--type note|project|weekly` — filter by content type
- `--category Nginx|DSM|...` — filter by category

**Interpreting scores:**
- Score > 0.80: High confidence match — present prominently
- Score 0.60-0.80: Possible match — present as suggestions
- Score < 0.60: Weak match — mention only if nothing better found

### Layer 2: Exact Match (supplement)

If Layer 1 returns no strong results (all scores < 0.60), or if the user
is searching for an exact string (command, config path, error message):

```bash
grep -ri "<query>" <vault_path>/Notes/ <vault_path>/Projects/
```

Show matching files with brief excerpts.

### Layer 3: Raw Search (archive, on request)

Only when the user specifically asks about recent sessions or raw data:

```bash
grep -ri "<query>" <vault_path>/Raw/
```

Show matches with date and repo context.

## Response Format

Present results to the user:

```
Found N results for "<query>":

1. [score] Title (Type, Category/Repo)
   → one-line summary

2. [score] Title (Type, Category/Repo)
   → one-line summary
```

- Use wikilink format when referencing notes: `[[note-name]]`
- If multiple matches, list them and ask which one to read
- If user wants details → read the full file
- For Weekly entries, show the date and summary line
