# Distill & Query Redesign — Leveraging Vector Store

**Date:** 2026-04-14
**Status:** Draft
**Depends on:** cortex-vec (Spec A)

## Problem

### Distill

1. **No trigger mechanism** — Raw files accumulate but nothing reminds the user to distill. Context fades over time, making late distillation less effective.
2. **No smart filtering** — Distill reads every unprocessed Raw file and asks the user about each one. No way to automatically assess which Raw files contain valuable knowledge.
3. **No deduplication** — Distill can create a new note about something that's already documented in the vault. No mechanism to detect overlap.
4. **Glob doesn't find nested files** — Raw files are stored as `Raw/YYYY/MM/DD/*.md` but the skill's glob pattern doesn't recurse.

### Query

1. **Keyword-only search** — `_index.md` scanning and grep miss semantically similar content ("nginx config path" won't find "Service config").
2. **No `_repo_index.json` awareness** — The query skill doesn't know about repo-based associations.
3. **No ranking** — Grep returns unranked results. No way to know which result is most relevant.

## Goals

### Distill
1. Trigger distill automatically as part of weekly workflow, with manual trigger available anytime
2. Use the three-filter criteria to assess Raw value:踩坑知識 (gotchas), 內部慣例 (internal conventions), 關鍵決策 (key decisions)
3. Use vector search to detect duplicate/overlapping content before creating new notes
4. Fix the nested glob issue

### Query
1. Semantic search via `cortex-vec search` as the primary search method
2. Support filtering by repo, type, tags, category
3. Return ranked results with scores
4. Preserve fallback to grep for exact string matches

## Design

### 1. Distill Redesign

#### 1.1 Trigger mechanism

**Weekly auto-trigger:** The `cortex:weekly` skill already exists. Add a distill step at the beginning of weekly compilation:

```
/cortex:weekly
  → Step 0: cortex-distill (process pending Raw files)
  → Step 1: collect data from Raw/, GitLab, CSS
  → Step 2: compile weekly report
```

**Manual trigger:** `/cortex:distill` continues to work anytime.

No new hooks or cron jobs needed — weekly is the natural cadence, and manual is always available.

#### 1.2 Find unprocessed Raw files (fix glob)

Current skill says: `Glob <vault_path>/Raw/ for all .md files`

Change to use `find` via bash (or recursive glob `Raw/**/*.md`):

```bash
find <vault_path>/Raw -name "*.md" -type f
```

The rest of the unprocessed detection stays the same:
- Check `distill-state.json` for already-processed paths (fast skip)
- Check `<!-- distilled: -->` marker in file (fallback)

#### 1.3 Value assessment

For each unprocessed Raw file, the AI assesses whether it contains knowledge worth persisting using these three criteria:

| Category | Signal | Example |
|----------|--------|---------|
| **踩坑知識 (Gotchas)** | Non-obvious behavior, hidden traps, root causes that aren't apparent | "jsoncpp returns null for oversized doubles instead of throwing" |
| **內部慣例 (Internal conventions)** | Synology-specific practices, internal API quirks, things that differ from external conventions | "subdomain feature users: Drive uses AppPortal.json, MailClient uses API" |
| **關鍵決策 (Key decisions)** | Why A was chosen over B, trade-offs considered, decisions that will be forgotten | "Use build-history.json for completion detection (vs PID check) because..." |

**Assessment process:**

1. Read the Raw file
2. Check if it has `## Discoveries` or `## Decisions` sections with content
   - No such sections → **skip** (mark as processed, no extractable content)
   - Has sections → proceed to value check
3. For each discovery/decision, apply the three-filter criteria
   - Matches any → **extract** (draft note, present to user)
   - Matches none → **skip** (routine knowledge already in code/commits)

**What to skip (not worth extracting):**
- Routine commits (the fix is in the code, the commit message has the context)
- General programming knowledge (Google-able)
- Tool/plugin configuration (changes frequently, lives in config files)
- Work that only records "what was done" without insight into "why" or "how it works"

#### 1.4 Deduplication via vector search

Before creating a new note from distilled content:

1. Run `cortex-vec search "<discovery text>" --n 3`
2. Check results:
   - **Score > 0.85** → High overlap. Show the existing note to the user. Suggest:
     - Merge into existing note (append/update)
     - Skip (already documented)
     - Create anyway (user judges it's different enough)
   - **Score 0.70-0.85** → Possible overlap. Show to user for judgment.
   - **Score < 0.70** → New knowledge. Proceed to create note.

This prevents the vault from accumulating redundant entries about the same topic.

#### 1.5 Post-distill actions

After creating a new note/project:

1. `cortex-vec upsert <path>` — add to vector store
2. `cortex-vec export-repo-index` — update `_repo_index.json`
3. Update `_index.md` — append row to appropriate table
4. Mark Raw file as processed — append `<!-- distilled: -->` marker
5. Update `distill-state.json`
6. Git commit + push (if auto_push enabled)

#### 1.6 Placement heuristics

When creating a refined note, determine where to put it:

| Content type | Target | How to determine |
|-------------|--------|-----------------|
| Technical knowledge about a repo's internals | `Projects/<repo>/` | Raw file has `repo:` in frontmatter |
| General technical knowledge | `Notes/<category>/` | Match to existing categories (C++, DSM, Linux, Nginx, Web, FSDN) |
| New category needed | `Notes/<new-category>/` | Ask user |

For repo-specific content, add `repos:` to frontmatter so it appears in vector store with repo metadata.

### 2. Query Redesign

#### 2.1 Search strategy (new layered approach)

```
Layer 1: Vector search (primary)
    cortex-vec search "<query>" [--repo] [--type] [--tags]
    → ranked results with scores

Layer 2: Exact match (supplement)
    grep -ri "<query>" Notes/ Projects/
    → for exact string/code/command lookup

Layer 3: Raw search (archive, on request)
    grep -ri "<query>" Raw/
    → only when user explicitly asks about recent sessions
```

Layer 1 replaces the old `_index.md` keyword scan. Layer 2 becomes a supplement for exact matches (e.g., searching for a specific command or config path). Layer 3 stays the same.

#### 2.2 Query flow

1. User asks a question or invokes `/cortex:query`
2. Run `cortex-vec search "<query>" --n 5`
3. If `--repo` context is available (from session cwd), add `--repo` filter
4. Present results:
   - Show title, score, type, and summary for each result
   - If score > 0.80: high confidence match
   - If score 0.60-0.80: possible match
   - If all scores < 0.60: suggest Layer 2 grep fallback
5. User picks a result → read full file content
6. If no vector results and user wants exact match → fall through to grep

#### 2.3 Context-aware query

When the user is in a git repo, query can automatically scope results:

```bash
# User is in /synosrc/curr/ds.base/source/libsynow3
# Query: "certificate"
# → cortex-vec search "certificate" --repo libsynow3
```

The skill detects cwd → repo name (same logic as session-start hook) and uses it as a default filter. User can override with explicit flags.

#### 2.4 Output format

Results presented to user:

```
Found 3 results for "certificate 設定":

1. [0.91] Certificate (Note, Nginx)
   → 憑證架構, synocrtregister, self-signed cert 教程

2. [0.78] check site server (Note, Nginx)
   → Check site is connected to right server via openssl

3. [0.65] synooauth flow chart (Project, libsynosysnotify)
   → Gmail notification flow: login.php => oauth2/auth

Which one would you like to read? (1-3, or 'grep' for exact match)
```

### 3. Skill file changes

#### `skills/cortex-distill/SKILL.md`

Update:
- Step 1: Fix glob to use recursive find
- Step 2: Add value assessment with three-filter criteria
- New Step 2.5: Vector dedup check before creating notes
- Step 4: Add `cortex-vec upsert` and `export-repo-index` after writing
- Add placement heuristics section

#### `skills/cortex-query/SKILL.md`

Rewrite:
- Layer 1 becomes vector search via `cortex-vec search`
- Layer 2 becomes grep fallback
- Add context-aware repo filtering
- Add output format specification

#### `skills/cortex-weekly/SKILL.md`

Update:
- Add Step 0: run distill before compilation

#### `skills/cortex-evolve/SKILL.md`

Update:
- After writing file: run `cortex-vec upsert` and `export-repo-index`

## Migration

1. Complete Spec A (cortex-vec CLI) first
2. Update skill files in order: evolve → distill → query → weekly
3. Run `cortex-vec rebuild` to ensure index is current
4. Test query with known content
5. Test distill with existing Raw files

## Out of scope

- Automatic distill trigger outside of weekly (e.g., SessionEnd hook) — weekly cadence is sufficient
- UI for browsing vector search results — terminal output is enough
- Embedding Raw files into vector store — Raw files are transient, only refined Notes/Projects are indexed
- Automatic merging of duplicate notes — only suggest, let user decide
