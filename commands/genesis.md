---
name: genesis
description: Initialize cortex vault — set up config, vault structure, rebuild index and distill state
argument-hint: "[vault path, e.g. /synosrc/misc/cortex or ~/cortex]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
---

Initialize or reconfigure the cortex memory vault. Run once per machine,
or again after switching machines to rebuild local state.

## Steps

### 1. Check for existing config

Read `~/.cortex/config.json`. If it exists, show current config and ask if the
user wants to reconfigure or abort.

### 2. Ask for vault path

If the user provided an argument, use that as the vault path.
Otherwise, ask: "Where is the cortex vault? (e.g. /synosrc/misc/cortex, ~/cortex)"

If the path exists and contains Notes/ or Weekly/ or Raw/, recognize it as an existing vault.
If the path doesn't exist, ask if they want to create it.

### 3. Ask for author info

Ask for:
- Author name (for git commits)
- Author email (for git commits)
- GitLab username (for weekly report compilation)

### 4. Write config

Create `~/.cortex/` directory if needed, then write `~/.cortex/config.json`:

```json
{
  "vault_path": "<user's answer>",
  "author": "<name>",
  "author_email": "<email>",
  "git": {
    "auto_commit": true,
    "auto_push": false
  },
  "weekly": {
    "gitlab_username": "<username>",
    "categories": ["fix", "feat", "misc"]
  }
}
```

### 5. Initialize vault structure

Ensure these directories exist in the vault:
- `Raw/`
- `Notes/`
- `Projects/`
- `Weekly/`

### 6. Initialize git

If the vault is not a git repo, run `git init` and create an initial commit.

### 7. Rebuild distill-state.json

Scan all files in `Raw/` for `<!-- distilled:` markers.
Build `~/.cortex/distill-state.json`:

```json
{
  "last_distill": "<current timestamp>",
  "processed": [
    "Raw/2026/04/08/151032_session_dsm-AdminCenter.md",
    ...
  ]
}
```

If Raw/ is empty or doesn't exist, create an empty state:

```json
{
  "last_distill": "<current timestamp>",
  "processed": []
}
```

### 8. Rebuild _index.md

Scan all files in Notes/, Projects/, and Weekly/:
- For each Notes file: extract title, tags from frontmatter, first line of content as summary
- For each Projects directory: extract _index.md title, tags
- For each Weekly file: extract date, first few items as highlights

Write `<vault_path>/_index.md` with the full index table format:

```markdown
---
updated: <today>
entries: <count>
---

# Cortex Index

## Projects

| Repo | Tags | Summary |
|------|------|---------|
| [[repo-name]] | tags | summary |

## Notes

| Note | Tags | Summary |
|------|------|---------|
| [[note-title]] | tags | summary |

## Weekly

| Week | Highlights |
|------|------------|
| [[YYYY-MM-DD]] | highlights |

## Raw (未提煉)

| Date | Count | Topics |
|------|-------|--------|
| YYYY-MM-DD | N | topics |
```

### 9. Show summary

Display:
```
✓ Cortex vault initialized
  Vault: <path>
  Config: ~/.cortex/config.json
  Author: <name> <email>
  GitLab: <username>
  Index: <N> entries in _index.md
  Distill state: <N> processed files

  Next steps:
  - Sessions auto-record to Raw/ on exit
  - /cortex:evolve → save notes or project info
  - /cortex:distill → refine raw records
  - /cortex:weekly → compile weekly report
  - /cortex:query → search your vault
```
