# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-08-04

### Removed
- The internal-name leftovers that the 0.23.0 de-branding sweep missed —
  including, unnoticed until now, the ones that reach the public website. The
  landing page's demo vault graph (`site/assets/graph.js`) labelled three
  project nodes with an internal repo name and two internal product names, and
  the marketplace presentation entry shipped an internal vault path plus a
  product-name search example; both render on the site. Also swept: the
  `genesis` argument hint and prompt, four skill docs (`cortex-query`,
  `cortex-evolve`, `cortex-broadcast`, `using-cortex`) whose category lists,
  trigger descriptions, and example paths still named internal products, one
  `parser.py` docstring, the README CLI example in both languages, and five
  `cortex-vec` test fixtures. Replacements follow 0.23.0's own mapping
  (`acme-core`/`acme-web` repos, `Nginx`/`Linux` categories, `/srv/cortex`
  paths).
- Internal product and system names from this file's own history entries:
  team chat / mail / issue tracker / support tickets in place of the product
  names, internal MCP plugins described by role instead of named, and one
  colleague's username replaced with a placeholder. Entry structure and claims
  are unchanged — only the identifiers are generalized. This is a
  forward-only edit: it keeps the working tree and the published changelog page
  clean, and deliberately does not rewrite history, so the strings remain in
  older commits' blobs.

Kept as-is: the maintainer's own name/email, as in 0.23.0.

## [1.2.0] - 2026-08-04

### Removed
- The `entries:` count in `_index.md` frontmatter. Three instructions
  incremented it — genesis, distill, evolve — and none ever decremented, so it
  drifted to 280 against a true 238 index rows. Page reorganization is the only
  path that removes a row and the only path with no skill behind it (distill and
  evolve append; broadcast merges content into an existing page without removing
  one), which is why the count could only grow. Nothing reads the field — not
  the CLI, not the hooks, not the skills — and `cortex-vec status` already
  reports the live count, so it is gone rather than propped up by new machinery
  to keep a derived value honest.

### Fixed
- The `/cortex:genesis` index template had drifted from the vault it
  rebuilds, in the direction nobody notices because the steps fail silently.
  It still emitted `## Weekly` and `## Raw (未提煉)` sections that the vault
  deliberately dropped in April 2026, and flat Projects/Notes tables where
  the vault groups rows into `###` sub-sections by repo and by topic — so
  running genesis produced a structurally wrong index. It also counted the
  legacy `Projects/<repo>/_index.md` files as pages.
- `cortex-evolve` documented Projects index rows as one row per repo. They
  are one row per page, under a `###` sub-section named for the repo.

### Added
- `docs/index-audit.md` — how to check `_index.md` against the files on disk
  now that no field claims to, including the regex traps that let a naive
  check pass while reporting the wrong set: an unanchored wikilink pattern
  matches prose and end-of-cell cross-links, `[^\]]+` cannot cross a `]`
  inside a title, and keying by `Path.stem` collapses the per-repo
  `_index.md` files.

## [1.1.0] - 2026-07-28

### Fixed
- **SessionEnd no longer leaves a trail of redundant Raw snapshots.** The hook
  fires more than once per conversation (`/clear`, exit + `--resume`) and the
  transcript it filters is one continuously growing jsonl, but the Raw filename
  was keyed on wall-clock alone — so every firing re-filtered the whole
  transcript into a new file and the earlier ones survived as strict prefixes
  of the latest. Each of those prefixes then sat in the distill queue as its
  own entry, so one conversation was distilled several times over and landed
  duplicate Notes. The newly written Raw now reclaims the undistilled queue
  entries whose conversation body is a prefix of it. Candidates come only from
  `distill_queue()`, so a Raw that already carries a `<!-- distilled: -->`
  marker (and is pointed at by a Note's `source:`) is never touched, and
  comparison starts at the first turn header, skipping the frontmatter clock
  and the audit trailer. Removal is staged with `git rm` so it rides the
  existing vault auto-commit, whose message records the count. Fail-open: any
  error leaves the duplicate in place. Applies to newly recorded Raws; an
  existing backlog needs one manual run.

### Added
- `cortex-vec reclaim-superseded` (no-chromadb fast path) — lists, or with
  `--apply` removes, undistilled Raw snapshots that a longer recording of the
  same session already covers. `--keep <raw>` is the session-end form; omitting
  it scans the whole queue pairwise for backlog cleanup, keeping the later path
  when two bodies are byte-identical.
- `cortex-vec` bumped to 0.7.0.

## [1.0.0] - 2026-07-17

### Added
- **Map-first distillation.** `/cortex:distill` no longer reads whole Raw
  files into context. A Raw is parsed once into a gap-free, overlap-free
  source partition (`cortex-vec raw-source`) that becomes the single parsing
  authority, then navigated through bounded pages: `raw-map` emits navigation
  cards (kind / size / source range / preview / deterministic lexical
  anchors), `raw-span` returns exact original text one bounded page at a
  time, and `raw-view` renders a budget-bounded L0–L3 projection that keeps
  analysis prose while eliding verbatim tool output. A per-Raw `distill-plan`
  tracks coverage intervals and a session-budget ledger, enforcing one active
  Raw at a time with fail-closed, user-only cache state — so large sessions
  distill deterministically across budget-bounded continuations instead of
  overflowing context.
- New `cortex-vec` subcommands: `raw-map`, `raw-span`, `raw-view`, and
  `distill-plan` (`start` / `status` / `resume` / `evidence-add` / `seal` /
  `complete` / `list` / `clear`), plus `distill-queue --stat` (`--json`) for
  per-level projected sizes when scheduling a batch.
- `scripts/raw-map-corpus-check.py` — mechanical map-first corpus validation
  (gap-free partition, page/session budget guarantees) over a vault's Raw/.
- **Record opt-out.** Setting `CORTEX_SKIP_RECORD=1` suppresses recording a
  session into Raw/ — for launcher/probe sessions that carry no
  distill-worthy content — checked before any file or queue work in the
  SessionEnd hook.

### Changed
- The `cortex-distill` skill is rewritten around the map-first navigation
  flow with coverage-gated verdicts. The `no-insight` verdict is now
  mechanical: it requires the whole map traversed and every semantic /
  ambiguous span expanded before it can be proposed.
- `cortex-vec` bumped to 0.6.0.

## [0.23.0] - 2026-07-02

### Removed
- The remaining internal-tool-specific MCP output filters from the
  `rtk_cmd` transcript filter framework: three internal company plugins — a
  diagnostics plugin (its whole `rtk_cmd` module), a chat/mail/support plugin
  (two filter functions in `mcp_tools.py`), and a build plugin (one filter
  function in `mcp_tools.py`) — plus their `_MCP_REGISTRY` entries in
  `dispatch.py` and dedicated tests. These recognized specific internal MCP
  plugins by name to compress their output shape in recorded transcripts —
  useless to an external user who doesn't have those plugins installed, and
  named an internal system by their mere presence. The generic parts of the
  framework (Bash command filters: git/cargo/pytest/eslint/etc., and the
  `zoekt`/`_gitlab__`/`_playwright__` MCP filters, none of which are
  company-specific by name or behavior) are unaffected.
- Illustrative internal-looking strings in test fixtures and skill docs: the
  internal GitLab host in example URLs → `git.example.com`; internal MCP
  tool-name prefixes → generic placeholders; internal example repo names in
  `cortex-vec` tests → `acme-core`/`acme-web`; "internal <company> tooling" →
  "internal company tooling" in `cortex-query`/`using-cortex` skill trigger
  descriptions; the `cortex-distill` convention-tag example row no longer names
  real internal product/file names.

- The two product-name synonym groups (a NAS OS and a router OS, each with its
  product-line alias) and `spk` from the package synonym group, in
  `cortex-vec/src/cortex_vec/synonyms.py`. Test fixtures that exercised those
  groups (`test_synonyms.py`, `test_bm25_synonym.py`) now use non-product
  synonym pairs instead (`perf`/`performance`,
  `login`/`signin`+`authentication`).

Kept as-is: the maintainer's own name/email (`tonyhu@synology.com`) as
plugin author metadata.

## [0.22.0] - 2026-07-02

### Removed
- `cortex-weekly` skill, its `/cortex:weekly` command, and the
  `weekly-compiler` agent. This is the public OSS mirror, and the weekly
  report feature's data sources (E: support tickets, F: team-chat posts, G:
  mail) called an internal company-only MCP plugin external users cannot
  install; Sources B–D and the `Ref:`/issue routing similarly depended on a
  second internal plugin (the company GitLab + issue-tracker MCPs). The skill's
  reference docs also embedded real internal hostnames and example data (the
  GitLab and issue-tracker hosts, internal repo names and issue numbers) that
  don't belong in a public repo.
- `cortex-distill` Step 5.5 ("Write Summary File") and Step 5.6 ("Judge
  Tracker Issue"), including the `Summary/` vault directory and the
  `weekly.repo_issue_map` config field. Both existed solely to feed the
  now-removed `cortex-weekly` Source A/B — the sidecar was never indexed by
  `cortex-vec` or listed in `_index.md`, so with the consumer gone it was
  dead code making an internal issue-tracker MCP call for no reason.
- The `weekly` block from `genesis`'s generated config template (`gitlab_username`,
  `categories`, `repo_issue_map`) and the SessionStart menu's weekly-report
  status line, now that nothing produces or consumes them.

Note: the `Weekly/` vault folder concept and `cortex-vec`'s `weekly` content
type are kept — they're generic vault taxonomy (a user can still manually
drop notes under `Weekly/` and have them indexed), not part of the removed
feature.

## [0.21.1] - 2026-06-30

### Fixed
- README: the cortex-vec install command used `$(claude plugin root cortex)`,
  but `claude plugin` has no `root` subcommand, so the path resolved empty.
  Resolve the installed plugin's `cortex-vec` from the plugin cache (latest
  version) instead.

## [0.21.0] - 2026-06-30

### Added
- `/cortex:takeoff` — a session hand-off "baton". When a long session's
  context fills up, it curates an ephemeral, git-ignored note at
  `<vault>/.takeoff/<repo>.md`; the next session's SessionStart menu surfaces
  it (option 5) for opt-in loading. Repo-scoped (one active baton per repo,
  new overwrites old); cleared on `done` or overwrite, not on load. The baton
  is scaffolding, not knowledge — never committed, distilled, broadcast, or
  indexed. A new `hooks/scripts/lib/repo-slug.sh` shares the repo-slug
  derivation between the create-side helper (`hooks/scripts/takeoff.sh`) and
  the SessionStart detect-side so their paths always agree; the create path
  verifies `.takeoff/` is git-ignored with `git check-ignore` before writing.

## [0.20.0] - 2026-06-22

### Changed
- Weekly Source F (team chat) now collects self-authored contributions via
  `chat_search_posts(from=[self], after, before)` instead of
  `chat_my_recent_activity`. The old tool fetched top-level posts only
  (it called `chat_list_posts` per channel), so the user's replies inside
  other people's threads — root-cause answers, workarounds, technical Q&A —
  were silently dropped from the report. The server-side search is indexed
  over all messages (replies included) and honors both window bounds, so the
  cutoff upper bound is now enforced (the old tool had no `before` param).

### Added
- Optional `weekly.chat_username` config (defaults to `weekly.gitlab_username`)
  to resolve the user's Chat user_id when it differs from their GitLab
  username — mirrors the existing `weekly.css_username` override.

## [0.19.0] - 2026-06-12

### Fixed
- Distill/broadcast queue detection no longer trusts a body-substring scan
  (`grep -rL '<!-- distilled:'`) to decide whether a Raw was processed. A
  pipeline meta-session's body quotes the marker dozens of times (it printfs
  markers onto *other* files; the captured output lands in the transcript), so
  the old scan silently excluded any Raw that merely mentioned the marker once
  — including genuine cross-repo work sessions. Detection is now
  position-anchored: a marker counts only when it appears in the header (before
  the first `### User` turn) or as the last non-empty line. On the maintainer's
  vault this recovered 26 genuinely-undistilled Raw files the old scan had been
  hiding, while correctly continuing to skip the 28 already-distilled
  (header-marker) files.

### Added
- `cortex-vec` subcommands for position-anchored vault-maintenance queries,
  all skipping the heavy vector-store import: `distill-queue` (Raw awaiting
  distillation), `broadcast-queue` (distilled Raw eligible for broadcast), and
  `raw-state <file>` (authoritative single-file classification).

### Changed
- `cortex-distill` Step 1, `cortex-broadcast` Step 2, and the SessionStart
  option-3 hint now call the `cortex-vec` queue commands instead of grepping
  the marker string; the skills document why grepping is unsafe.

## [0.18.1] - 2026-06-09

### Fixed
- `rtk_filter` no longer crashes the SessionEnd filter pipeline when no TOML
  parser is available. It imported `tomllib` unconditionally, so under a
  Python < 3.11 interpreter (e.g. the hook launched with an ambient
  `/usr/bin/python3`) the whole `filter-transcript` run failed at import and
  every Raw record degraded to `(filter failed)`. Now falls back
  `tomllib` → `tomli` → none, and `load_filters()` returns an empty filter
  set (tool output kept verbatim) instead of crashing.

### Added
- Developer test gate: `scripts/run-checks.sh` (ruff + both pytest suites),
  a local `.pre-commit-config.yaml`, and `ruff.toml` pinning the lint rule
  set (`E4`/`E7`/`E9`/`F`, ignoring `E741`, with `E402` per-file-ignored for
  the `pysqlite3` swap in `store.py` and the `sys.path` shim in hook tests).

## [0.18.0] - 2026-06-04

### Added
- SessionEnd hook now detects cortex maintenance-pipeline sessions
  (distill/weekly/broadcast/genesis) and pre-stamps the recorded Raw with a
  `<!-- distilled: ... (skip: meta-session) -->` marker, so these
  self-referential sessions never re-enter their own distill queue — the queue
  can finally reach empty. The Raw is still written as an audit trail; only the
  `grep -rL '<!-- distilled:'` queue scan skips it.
  Detection (`hooks/scripts/meta_session.py`) matches both the `cortex:distill`
  slash-command alias and the dominant `cortex:cortex-distill` plugin:skill id,
  via a structured `Skill` tool_use. `evolve`/`query`/`using-cortex` are
  deliberately excluded — they fire inside real work sessions worth recording.
  (cortex-vec is unaffected: it only indexes `Notes/` + `Projects/`, never
  `Raw/`.)

## [0.17.0] - 2026-06-02

### Added
- SessionEnd filter: the diagnostics plugin's `exec_command` outputs are
  unwrapped from their JSON envelope to a compact `$ <command>` frame, and the
  remote stdout is recursed through the existing `rtk_cmd` Bash filters — so
  every git/ls/grep/cargo/... filter now applies to remote NAS execution too.
- SessionEnd filter: the internal plugin's `codesearch` (shares the zoekt
  result shape) and its support-system activity log (audit-log flatten) are
  now filtered.

### Fixed
- `_MCP_REGISTRY` now matches by server-token substring instead of a full
  plugin-qualified prefix, fixing the silent no-op of already-written filters
  when a plugin is repackaged: `kaer-morhen` playwright, the `build-toolkit`
  build MCP, and the internal diagnostics MCP namespace were all being missed.

## [0.15.1] - 2026-05-28

### Fixed
- `cortex-vec`: `--repo X` no longer excludes cross-repo `Notes/` pages.
  The previous strict-equality semantic (vector: `metadata["repo"]`;
  BM25: list-membership on `rec["repos"]`) hid Notes/ entries entirely
  whenever a repo filter was set, which caused `cortex:distill` dedup
  to return false `new` verdicts on Raws whose true duplicate lived in
  a cross-repo Note (concrete failure: an `acme-web` session-token Raw
  nearly duplicating `Notes/Auth/session token 注入機制 …`). The filter now
  narrows the `Projects/` partition only; `type=note` documents always
  pass through. `cortex-distill` SKILL Step 3.2 gets a one-line
  clarifier documenting the new semantic.
  Spec: `docs/specs/2026-05-27-distill-dedup-repo-filter-blindspot.md`.

## [0.15.0] - 2026-05-27

### Added
- `cortex-weekly`: GitLab activity sweep. The weekly report now captures MR
  review comments (non-approve), non-tracker issue comments, in-review (opened)
  MRs, and no-MR pushes — via a single paginated per-user `list_events` sweep
  that replaces the approvals-only Source C. Reactive items route to `inbound.`;
  authored items route through the existing `fix.`/`feat.`/`misc.` classifier
  (Source A + Step 5b) with an `(in review)` tag for unmerged MRs. Same
  substance bar as the chat/mail sources; overlap/cross-week dedup
  prevents double-listing against Source B/D.

### Fixed
- `weekly-compiler` agent now resolves team-chat DM participants (adds
  `chat_list_posts` + `chat_list` to its allow-list and the Source F
  resolution step), so DMs render as `` [chat] `@username`: … `` instead of a
  bare `[chat] DM:`. Aligns the agent with SKILL.md Source F.

## [0.14.2] - 2026-05-27

### Fixed
- `cortex-weekly`: resolve team-chat DM participants via
  `chat_list(kind="users")`, tracking the consolidated internal
  Chat tool surface.

### Added
- `cortex-weekly`: Runtime Requirements + graceful-degradation policy.
  When a source's internal MCP plugin (chat/mail/support, or GitLab +
  issue tracker) is missing or unauthenticated, it is skipped and surfaced as
  a note atop the draft instead of aborting the report. The
  `weekly-compiler` agent now returns `skipped_sources`.

## [0.14.1] - 2026-05-26

### Changed
- Wikilink graph-boost reworked from an additive score boost into a
  third RRF stream (rank-based). The additive form added a boost onto
  RRF's compressed score band (~0.001–0.016) and corrupted ordering at
  every weight (measured: MRR 0.875 → 0.49). As a rank-based stream it
  composes cleanly — neutral on normal queries (no change on the
  20-query eval corpus) and recovers wikilink-only-reachable notes
  (R@5 0.50 → 0.667 on a wikilink-stress set), and can now surface
  neighbors that vector/BM25 missed entirely.
- Config key `retrieval.graph_weight` (additive strength) replaced by
  `retrieval.w_graph` (graph RRF-stream weight, default 0.3).

### Fixed
- Test isolation: a `conftest` autouse fixture pins
  `get_retrieval_config` to code defaults, so a local
  `~/.cortex/config.json` (e.g. `rerank: true`) no longer leaks into
  the test suite and breaks default-behavior assertions.

## [0.14.0] - 2026-05-26

### Added
- **Hybrid retrieval** — `cortex-vec search` now fuses BM25 + vector
  via Reciprocal Rank Fusion (RRF, k=60). BM25 restores exact-term
  recall (function names, repo names, issue IDs) that dense embeddings
  blur; CJK-aware tokenization (jieba) handles mixed zh/en queries.
- BM25 index persisted at `~/.cortex/bm25/`, kept in lockstep with the
  vector store on `rebuild` / `upsert` / `delete`. `cortex-vec status`
  now reports both vector and BM25 entry counts.
- `cortex-vec rebuild --bm25-only` — rebuild just the BM25 index from
  the vault in seconds, with no ChromaDB delete and no re-embedding.
- **Retrieval eval harness** — `cortex-vec eval run` compares
  grep / vector / bm25 / hybrid adapters on a hand-labeled query set,
  emitting P@5 / R@5 / MRR / hit + an NDJSON log and a markdown
  scorecard (`docs/benchmarks/`). `cortex-vec eval propose` drafts
  candidate queries (LLM) for the user to confirm.
- Optional, **default-off** retrieval enhancements (each independently
  toggleable and eval-measurable): synonym expansion
  (`retrieval.synonym_weight`), wikilink graph-boost (`--graph` /
  `retrieval.graph`), LLM rerank (`--rerank` / `retrieval.rerank`),
  and max-per-repo diversification (`retrieval.max_per_repo`).

### Fixed
- `cortex-vec search` reports the vector cosine similarity (0–1) as
  `score`, not the RRF fusion score (~0.01). The RRF scale had
  collapsed distill/broadcast dedup, whose thresholds
  (`dedup_threshold_new` 0.45, `..._pending` 0.60,
  `broadcast.target_min_score` 0.40) are calibrated for cosine — every
  Raw was scoring far below threshold. RRF now only orders results.
- `cortex-vec search` degrades to BM25-only when `OPENAI_API_KEY` is
  absent (the embedding function's `sys.exit` no longer escapes the
  stream guard and crashes the query).

### Notes
- `cortex-vec` package bumped to 0.4.0; new deps `rank-bm25`, `jieba`,
  `snowballstemmer`. Search output JSON shape is unchanged.
- With all enhancements off, `cortex-vec search` behaves as before
  (vector-ranked). Run `cortex-vec eval run` to measure lift before
  enabling synonym / graph / rerank as defaults.
- Precise-term dedup scoring (boosting a low-cosine but exact-term
  match) remains intentionally deferred: a naive idf-coverage boost
  over-flags short queries, so it needs eval calibration first.

## [0.13.0] - 2026-05-24

### Changed
- `cortex-distill` Step 2 (has_insight) and Step 3.3 (placement) now
  mandate `AskUserQuestion`: the agent surfaces a candidate verdict and
  waits for user confirmation instead of dispatching unilaterally.
- `cortex-distill` Step 9 drops the (y/n/l) broadcast prompt and
  dispatches `cortex-broadcast` inline for every new / pending-merge
  Raw; escape hatches now live inside broadcast's own quit/abort paths.

## [0.12.0] - 2026-05-22

### Added
- `weekly.repo_issue_map` config field (1:N repo → tracker issue
  mapping). Backward compatible — absent / empty defaults to no
  promotion.
- `cortex-distill` Step 5.6: judges which mapped issue a Raw
  contributes to and writes `issue:` into Summary frontmatter
  (optional 4th field).
- `cortex-weekly` Step 5b: surfaces vault-only tracker-tracked
  progress as `<issue-title> - ([KEY](url)): <one-line>` under
  `feat.` / `fix.`. Lets repos like `acme-cli` (vault-only work,
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
  `/srv/cortex/Raw/2026/05/`: 10/125 had structured sections,
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
  support / issue-tracker entries from being attributed to users with
  similar-looking names.
- New optional config key `weekly.css_username` (default: same as
  `weekly.gitlab_username`) for users whose support-system SSO differs from
  their GitLab username.
- `cortex-weekly` (Source F, Source G): chat/mail bullets now wrap
  `@username` in backticks (e.g. `` `@coworker` `` instead of `@coworker`)
  so GitLab does not turn them into mention notifications when the weekly
  is pasted into a wiki / MR / issue. Same content, no surprise pings.

## [0.10.2] - 2026-05-08

### Changed
- `cortex-weekly` (Source F — team chat): DM threads no longer auto-drop —
  they go through the same substance filter as public channels. Surviving
  DM threads attribute to `@username` (1:1) or `@user_a, @user_b[, @user_c]`
  (group DM with 2–3 others). 4+ other participants fall back to
  `[chat: DM]`.
- `cortex-weekly` (Source G — mail): 1-on-1 threads attribute to
  `@username` via the `[mail: <subject>] (@username)` shape. Multi-recipient
  threads keep `[mail: <subject>]`.
- `cortex-weekly` redaction rule scoped to customer info / external personal
  identifiers only. Internal company usernames are now allowed (and
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
- **Weekly report — team-chat source** (`skills/cortex-weekly`): Source F
  pulls self-authored chat posts via `chat_my_recent_activity`,
  aggregates by `thread_id`, drops social chatter / MR-link broadcasts /
  DM noise, and emits substantive technical contributions into
  `inbound.` as `[chat: <channel>]: topic → 我的貢獻`.
- **Weekly report — mail source** (`skills/cortex-weekly`): Source G
  reads the Sent folder (`mailbox_id = -4`) instead of the unfilterable
  INBOX, fetches each thread via the mail MCP, drops HR / calendar /
  mass-announcement / logistics replies, and emits work-substantive
  threads into `inbound.` as `[mail: <subject>]: topic → 我的回應`
  (with `Re:` / `Fwd:` prefix stripping).
- `agents/weekly-compiler` allowed-tools extended with
  `chat_my_recent_activity` plus the mail-mailbox, mail-thread, mail-fetch,
  and support-ticket MCP tools.

### Changed
- `references/draft-template.md` documents the inbound shapes for
  chat and mail, with a worked example covering both sources.
- Cross-source dedup rule added to Step 4: chat/mail entries that merely
  announce or coordinate around an MR / issue / support ticket already
  represented elsewhere are dropped.
- Frontmatter description for `cortex-weekly` lists chat and mail
  alongside Raw/, GitLab, and support tickets as report inputs.

### Fixed
- `references/draft-template.md` previously cross-referenced "Source C
  filter" for the tracker-issue reply rule; corrected to "Source D filter".

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
- Weekly classifies by **tracker issue type**, not commit type — matches how
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

