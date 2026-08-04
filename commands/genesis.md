---
name: genesis
description: Initialize cortex vault — set up config, vault structure, and rebuild index
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
  }
}
```

### 5. Initialize vault structure

Ensure these directories exist in the vault:
- `Raw/`
- `Notes/`
- `Projects/`
- `Weekly/`

Ensure `log.md` exists at the vault root. If missing, create it with:

````markdown
---
created: <today>
---

# Cortex Log

Append-only record of vault operations (distill, evolve).

---
````

The file is append-only; do not overwrite if it exists.

### 6. Initialize git

If the vault is not a git repo, run `git init` and create an initial commit.

### 7. Rebuild _index.md

Scan every page under `Notes/<topic>/` and `Projects/<repo>/`, skipping any path
containing `_archive`. For each page extract the title, the tags from
frontmatter, and a one-line summary.

`Weekly/` and `Raw/` are deliberately NOT indexed — they are chronological and
navigated by date, so an index table would only duplicate the directory listing.

Write `<vault_path>/_index.md`. Both top-level sections group their rows into
`###` sub-sections — by topic under Notes, by repo under Projects — so the
index mirrors the on-disk layout:

```markdown
---
updated: <today>
---

# Cortex Index

## Projects

### <repo-name>

| Project | Tags | Summary |
|---------|------|---------|
| [[topic-title]] | tags | summary |

## Notes

### <topic>

| Note | Tags | Summary |
|------|------|---------|
| [[note-title]] | tags | summary |
```

Do NOT add an `entries:` count to the frontmatter. It is a derived value with no
reader, and a hand-maintained copy of it drifts the moment a page is merged away
or renamed. `cortex-vec status` reports the live count instead.

Legacy `Projects/<repo>/_index.md` files are not index rows — skip them. To check
an existing index against the files on disk (and for the regex traps that make a
naive check silently wrong), see `docs/index-audit.md`.

### 8. Show summary

Display:
```
✓ Cortex vault initialized
  Vault: <path>
  Config: ~/.cortex/config.json
  Author: <name> <email>
  Index: <N> pages in _index.md

  Next steps:
  - Sessions auto-record to Raw/ on exit
  - /cortex:evolve → save notes or project info
  - /cortex:distill → refine raw records
  - /cortex:query → search your vault
```
