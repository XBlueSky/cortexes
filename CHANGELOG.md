# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0] - 2026-05-22

### Added
- `weekly.repo_issue_map` config field (1:N repo → Workplus issue
  mapping). Backward compatible — absent / empty defaults to no
  promotion.
- `cortex-distill` Step 5.6: judges which mapped issue a Raw
  contributes to and writes `issue:` into Summary frontmatter
  (optional 4th field).
- `cortex-weekly` Step 5b: surfaces vault-only Workplus-tracked
  progress as `<Workplus-title> - ([KEY](url)): <one-line>` under
  `feat.` / `fix.`. Lets repos like morpheus (vault-only work,
  no MR this week) appear in the right section instead of `misc.`.
- Per-surface description budgets in `references/draft-template.md`:
  `feat.` group-MR ≤40 chars, `misc.` tag ≤10, `inbound.` mail ≤30,
  others ≤60. Trim weekly for team-meeting paste.

### Changed
- `cortex-weekly` Source A now reads `issue:` from Summary
  frontmatter (when present).
- `cortex-weekly` Step 4 prefers issue-aware MR ↔ Summary join,
  falls back to repo + date when either side lacks the issue field.
- `cortex-weekly` Step 5 classification: `repo_issue_map` is a
  `Ref:` fallback; commit type explicitly does NOT decide section.
- `cortex-weekly` Same-title MR dedup: when all cluster MRs share
  the same effective issue AND that issue has a group heading, the
  dedup bullet now sits **indented inside the group** instead of
  flat at the section top level. Different-issue clusters still go
  flat (current behaviour).
- `[chat]` / `[mail]` brackets in `inbound.` no longer wrap the
  subject — the bracket carries only the source tag, subject moves
  outside. Fixes GFM reference-link-definition collision that
  mangled rendering.
- Same-topic chat thread dedup rule documented: 2+ threads on the
  same topic collapse to one bullet listing all participants.

### Notes
- See `docs/specs/2026-05-22-weekly-skill-revision-design.md` for
  full rationale and `docs/plans/2026-05-22-weekly-skill-revision.md`
  for the per-task implementation history.
- All new fields are optional; existing `~/.cortex/config.json`
  files without `repo_issue_map` continue to work unchanged.

## [0.11.1] - 2026-05-18

### Fixed
- `cortex-distill` Stage 1 `has_insight()` no longer gates on the
  presence of `## Discoveries` / `## Decisions` sections. The
  SessionEnd capture pipeline never produces those sections — it
  writes frontmatter plus filtered transcript — so ~92% of real Raws
  were false-negative `(no insight)` (verified against
  `/synosrc/cortex/Raw/2026/05/`: 10/125 had structured sections,
  91/125 had inline `★ Insight ─────` callouts). The rule now applies
  to the entire Raw body and recognizes insight in `★ Insight`
  callouts, tables, prose analysis, or legacy structured sections
  alike.
- `cortex-distill` Step 3.2 dedup query text picker correspondingly
  scans the entire Raw for the most content-ful insight passage
  instead of restricting to Discovery/Decision bullets.

### Notes
- Existing Raws marked `(no insight)` under the old rule are NOT
  auto-reprocessed. The fix applies forward from 2026-05-18.
- Spec: see `docs/superpowers/specs/2026-04-17-distill-phase1-extraction-log-design.md`
  "Revision 2026-05-18" section.

## [0.11.0] - 2026-05-12

### Added
- `cortex-distill` Step 5.5: writes a per-Raw summary sidecar at
  `Summary/YYYY/MM/DD/<filename>.md` for every processed Raw,
  regardless of outcome (`new`, `pending-merge`, `skip-routine`,
  `no-insight`). Sidecar has 3-field frontmatter (`raw`, `repo`,
  `distilled`) and a 1–5 sentence prose body. The body deliberately
  does NOT enumerate commits, MR URLs, or issue keys — those are
  GitLab's canonical territory.
- New top-level vault directory `Summary/` mirrors `Raw/`'s date
  tree. Tracked in git alongside Notes/Projects. Not indexed by
  `cortex-vec`, not listed in `_index.md` (it is `cortex-weekly`'s
  internal cache, not user-browsable content).

### Changed
- `cortex-weekly` Source A reads from `Summary/` instead of `Raw/`.
  Per-Raw token cost for the weekly compile drops by roughly the
  ratio between full Raw body size and the ~60–300 char summary.
  Boundary-Friday HHMMSS filter rules carry over unchanged (Summary
  filenames mirror Raw filenames exactly).
- `cortex-weekly` Step 4 dedup against GitLab MRs (Source B) now
  joins MR ↔ Summary by **repo + date** instead of URL-string
  matching inside Raw body. The date window is `[merged_at - 1 day,
  merged_at]` to capture sessions that ran late and crossed midnight
  before the MR was merged the next morning.
- `cortex-weekly` Step 2 (Run Distill) now documented as a hard
  precondition for Source A — if a Raw in the window has no
  corresponding Summary after Step 2 runs, weekly surfaces the
  orphan list to the user and does NOT silently fall back to reading
  the Raw body.

### Notes
- Raw remains immutable. This change adds an additional derived
  artifact (the sidecar), it does not modify any Raw content,
  frontmatter, or existing `<!-- distilled: ... -->` marker.
- No backfill: only Raws distilled after 0.11.0 ships get a Summary.
  Older Raws appearing in a weekly window will trigger the orphan
  prompt; resolution is to re-run distill on those specific files.
- `cortex-broadcast` and `cortex-query` are unaffected — both still
  read full Raw / Notes / Projects respectively.

## [0.10.3] - 2026-05-08

### Fixed
- `cortex-weekly` (Source D, Source E): username matching is now strictly
  literal. The skill no longer infers alternate identities (e.g. `jhu` is
  NOT treated as a variant of `tonyhu`) or accepts substring matches. If
  no activity entry has `user` exactly equal to the configured username,
  the source returns zero bullets for that section. Prevents false-positive
  CSS / wit entries from being attributed to users with similar-looking
  names.
- New optional config key `weekly.css_username` (default: same as
  `weekly.gitlab_username`) for users whose CSS SSO differs from their
  GitLab username.
- `cortex-weekly` (Source F, Source G): chat/mail bullets now wrap
  `@username` in backticks (e.g. `` `@yannyliu` `` instead of `@yannyliu`)
  so GitLab does not turn them into mention notifications when the weekly
  is pasted into a wiki / MR / issue. Same content, no surprise pings.

## [0.10.2] - 2026-05-08

### Changed
- `cortex-weekly` (Source F — ChatPlus): DM threads no longer auto-drop —
  they go through the same substance filter as public channels. Surviving
  DM threads attribute to `@username` (1:1) or `@user_a, @user_b[, @user_c]`
  (group DM with 2–3 others). 4+ other participants fall back to
  `[chat: DM]`.
- `cortex-weekly` (Source G — MailPlus): 1-on-1 threads attribute to
  `@username` via the `[mail: <subject>] (@username)` shape. Multi-recipient
  threads keep `[mail: <subject>]`.
- `cortex-weekly` redaction rule scoped to customer info / external personal
  identifiers only. Internal Synology usernames are now allowed (and
  recommended for 1-on-1 attribution).
- `cortex-weekly`: same-title MR dedup. Within `fix.`, `feat.`, or `inbound.`,
  2+ MRs sharing an exact title collapse into one bullet of the form
  `<title> — [!N1](url) / [KEY1](url)、[!N2](url) / [KEY2](url)、...`.
  Single-MR cases keep their existing shape.

### Notes
- Past weekly reports are not regenerated.
- Plugin consumers who relied on the strict-redaction rule (e.g., publishing
  weeklies externally) should review before publishing or fork the skill.

## [0.10.1] - 2026-05-06

### Changed
- `cortex-vec`: summary model upgraded from `gpt-4o-mini` to
  `gpt-5.4-mini`. The new model produces tighter bilingual summaries
  with cleaner inline gloss (e.g. `retrieval recall（檢索召回率）`)
  and no longer leaks prompt-rule examples into output.
- `cortex-vec/store.py`: `_generate_summary()` now uses
  `max_completion_tokens=400` (replaces deprecated `max_tokens`) and
  passes `reasoning_effort="none"` — required for the gpt-5.4 family.
- `cortex-vec` bumped to `0.3.1`.

### Notes
- Existing Chroma `::summary` entries are not regenerated automatically;
  they continue to reflect summaries written by `gpt-4o-mini`. Newly
  added/updated documents will use `gpt-5.4-mini`.
- The embedding model (`text-embedding-3-small`, 1536 dim) is unchanged;
  no Chroma collection rebuild is required.

## [0.10.0] - 2026-05-04

### Added
- **Weekly report — ChatPlus source** (`skills/cortex-weekly`): Source F
  pulls self-authored ChatPlus posts via `chat_my_recent_activity`,
  aggregates by `thread_id`, drops social chatter / MR-link broadcasts /
  DM noise, and emits substantive technical contributions into
  `inbound.` as `[chat: <channel>]: topic → 我的貢獻`.
- **Weekly report — MailPlus source** (`skills/cortex-weekly`): Source G
  reads the Sent folder (`mailbox_id = -4`) instead of the unfilterable
  INBOX, fetches each thread via `mailplus_get`, drops HR / calendar /
  mass-announcement / logistics replies, and emits work-substantive
  threads into `inbound.` as `[mail: <subject>]: topic → 我的回應`
  (with `Re:` / `Fwd:` prefix stripping).
- `agents/weekly-compiler` allowed-tools extended with
  `chat_my_recent_activity`, `mailplus_list_mailboxes`,
  `mailplus_list_threads`, `mailplus_get`, and `css_get_ticket`.

### Changed
- `references/draft-template.md` documents the inbound shapes for
  ChatPlus and MailPlus, with a worked example covering both sources.
- Cross-source dedup rule added to Step 4: chat/mail entries that merely
  announce or coordinate around an MR/issue/wit/css already represented
  elsewhere are dropped.
- Frontmatter description for `cortex-weekly` lists ChatPlus and MailPlus
  alongside Raw/, GitLab, and CSS as report inputs.

### Fixed
- `references/draft-template.md` previously cross-referenced "Source C
  filter" for the wit-issue reply rule; corrected to "Source D filter".

## [0.9.2] - 2026-04-28

### Added
- **Proactive cortex triggering** — three-layer enforcement so the model
  consults the vault before guessing or asking, instead of waiting for
  explicit "查 cortex" phrases:
  - `skills/cortex-query` description gains proactive trigger clauses
    (ongoing projects, internal tooling, prior-work topics).
  - New `skills/using-cortex` meta-skill establishes vault-first
    discipline at conversation start, regardless of SessionStart menu
    choice (option 4 no longer bypasses the vault).
  - `hooks/scripts/session-start-inject.sh` injects Notes/ and Projects/
    topic list as grounding evidence so topic-match triggers fire.

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

