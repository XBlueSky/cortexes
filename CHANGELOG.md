# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.1] - 2026-04-21

### Changed
- Transcript filter renders Raw/ with plain-text section markers
  (`### Claude`, `### User`, `> [tool]`) instead of emoji, aligning Raw
  output with user preference for emoji-free content. Marker strings are
  factored into `TOOL_HDR` / `CLAUDE_HDR` / `USER_HDR` constants so render
  and detection stay in sync.

## [0.9.0] - 2026-04-17

### Added
- **Transcript filter engine** — TOML-driven pipeline that scrubs session
  transcripts before they are written to `Raw/` (`feat(filter): add TOML-driven
  transcript filter engine`).
- Command-specific transcript filters so noisy tool outputs from a given
  slash-command don't pollute Raw records.
- Bash volume-analysis helpers for inspecting filter rejection ratios.

### Changed
- `Stop` hook now runs the filter pipeline between session capture and Raw
  export, so Raw files stay closer to real signal.

## [0.8.0] - 2026-04-16

### Added
- **`/cortex:broadcast` command + `cortex-broadcast` skill** — llm-wiki style
  ingest that conversationally updates related existing pages when a Raw has
  been distilled.
- `distill` gained a *Step 9 — Ask broadcast now?* so a finished distill can
  chain into broadcast without leaving the flow.
- `evolve` now appends an entry to `log.md` before committing.
- `genesis` creates `log.md` during vault initialization.

### Changed
- `distill` upgraded to two-stage assessment with a `pending-merge` outcome
  for content that needs broadcast reconciliation.

### Fixed
- `broadcast`: zero-candidate branch and pending-merge append clarified.
- `distill`: log-append mechanism and interactive outcome mapping clarified.

## [0.7.0] - 2026-04-15

### Added
- `/cortex:weekly` aligned to the Friday-meeting cycle with a tighter draft
  format and new `inbound.` section alongside `fix.` / `feat.` / `misc.`.
- `references/draft-template.md` plus a leaner `SKILL.md`.

### Changed
- Weekly classifies by **Workplus issue type**, not commit type — matches how
  the Friday meeting is actually structured.
- `distill` removed `distill-state.json`; the `<!-- distilled: -->` marker is
  now the single source of truth.

### Performance
- `SessionStart` hook defers `Raw/` scanning until the user explicitly picks
  the "process backlog" option.

### Fixed
- Session-start prompt now correctly injects the vault path.

## [0.6.0] - 2026-04-14

### Added
- Interactive menu on `SessionStart` with vault status detection (weekly
  present? backlog in `Raw/`? etc.) so the first reply can offer concrete
  choices instead of a static greeting.

## [0.5.0] - 2026-04-13

### Added
- **Dual-vector embedding** in `cortex-vec` — stores both the raw document
  embedding and a bilingual summary embedding, improving recall for mixed
  zh/en queries.
- Bilingual summary generation via `gpt-4o-mini`.
- Search dedup across the two vector spaces.

### Changed
- `Weekly/` excluded from the vector index (it's derived output, not source
  knowledge).
- Summary prompt switched to Traditional Chinese output for Chinese-context
  notes.

## [0.4.1] - 2026-04-12

### Fixed
- `SessionStart` hook now prompts the model to ask about memory loading in
  its first reply, instead of relying on the user to remember to mention it.

## [0.4.0] - 2026-04-11

### Added
- **`cortex-vec` as a proper Python package** (was an ad-hoc shell script):
  config, parser, store, and CLI modules; editable install via
  `pip install -e ./cortex-vec`.
- ChromaDB-backed vector store with OpenAI `text-embedding-3-small`.
- `/cortex:query` rewritten around vector-first search with grep fallback.
- `/cortex:distill` gained value assessment and dedup checks.
- `/cortex:evolve` now upserts into the vector store after writing markdown.

### Changed
- `SessionStart` hook rewritten as a lazy-loading prompt — memories are
  surfaced on demand rather than eagerly injected at every session start.
- Switched embedding model from local sentence-transformers to OpenAI
  `text-embedding-3-small`.

### Removed
- Legacy `build-repo-index.sh` script, replaced by `cortex-vec export-repo-index`.
- Old monolithic `cortex-vec` shell script.

## [Earlier versions]

Pre-0.4.0 history lived in individual commits without a formal changelog.
Major themes:
- 0.3.x — first `_repo_index.json` for session-start repo lookup.
- 0.2.x — vault structure split into `Raw/`, `Notes/`, `Projects/`, `Weekly/`.
- 0.1.x — initial plugin skeleton with `evolve`, `distill`, and `weekly`
  commands running against flat markdown.

