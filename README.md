<p align="center">
  <img src="docs/images/logo.png" alt="Cortexes" width="200">
</p>

<h1 align="center">Cortexes</h1>

<p align="center">
  A personal knowledge vault plugin for Claude Code — session recording, memory distillation, semantic retrieval.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://cortexes.pages.dev"><img alt="Website" src="https://img.shields.io/badge/website-cortexes.pages.dev-000"></a>
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-d97757">
  <a href="CONTRIBUTING.md"><img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

<p align="center">
  <sub><a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a></sub>
</p>

## What It Does

Cortexes turns your working memory into a searchable knowledge base. Every
Claude Code session gets automatically recorded when it ends, then can be
distilled and retrieved later.

- **Automatic capture** — a full report (commits, findings, decisions) is
  generated when a session ends and saved to the vault
- **Semantic search** — OpenAI embeddings + ChromaDB, with mixed Chinese/English
  query support
- **Knowledge distillation** — extracts hard-won lessons, internal
  conventions, and key decisions from raw session dumps
- **Memory injection** — detects the current repo at session start and offers
  to load related memory

**Design philosophy:** the vault is the source of truth (plain markdown +
git); the vector store is just a rebuildable derived index.

## Quick Start

### 1. Install the plugin

```bash
# Add the marketplace, then install the plugin from it
/plugin marketplace add https://github.com/XBlueSky/cortexes.git#plugin
/plugin install cortexes@cortex
```

The marketplace is named `cortex` and the plugin inside it is `cortexes` —
hence `cortexes@cortex`. The marketplace name is kept from 1.x on purpose so
that existing `marketplace add` registrations keep working.

### 2. Install the cortex-vec CLI

The CLI is published on PyPI as
[`cortex-vec`](https://pypi.org/project/cortex-vec/):

```bash
# Recommended: isolated tool install via uv
uv tool install cortex-vec

# Or with pip
pip install cortex-vec
```

Upgrade with `uv tool upgrade cortex-vec` (or `pip install -U cortex-vec`)
after a plugin update. `/cortexes:genesis` checks for the CLI and offers this
install when it is missing. To run the unreleased development version
instead, install from the repo:

```bash
uv tool install "git+https://github.com/XBlueSky/cortexes.git@plugin#subdirectory=cortex-vec"
```

`OPENAI_API_KEY` is **optional**. Setting it enables embeddings, and with
them semantic (vector) search. Without it nothing breaks: `search` runs on
the local BM25 index, entirely on your machine and with nothing sent to
OpenAI — see [Environment Variables](#environment-variables).

### 3. Initialize

```bash
/cortexes:genesis /path/to/your/vault
```

This sets the vault path and author info, and builds the semantic index.

### 4. Start using it

```
"save to cortex"     → manually save knowledge
"check cortex"       → semantic search over the vault
"distill"            → extract knowledge from Raw/
"broadcast"          → fuse new Raw content into existing pages
```

## Upgrading from 1.x to 2.0

2.0.0 renames the **plugin** from `cortex` to `cortexes`. Your vault, config
and indexes are untouched — there is no data migration.

1. **Update the marketplace.** In Claude Code run
   `/plugin marketplace update cortex` (or remove and re-add it).
2. **Start a new session.** The marketplace manifest ships a `renames`
   mapping (`cortex` → `cortexes`), so the rename is carried for you: the
   update re-points your enabled plugin at `cortexes@cortex`, and the next
   session start materializes it at 2.0.0. You do **not** need to uninstall
   and reinstall. In between the two steps `/plugin` may still list the old
   `cortex` row annotated `Renamed to "cortexes" in the "cortex"
   marketplace` — that is the migration staged, not an error. If you ever do
   reinstall from scratch, the id is `/plugin install cortexes@cortex`.
3. **Use the new command prefix.** `/cortex:*` no longer resolves; every
   command moved to `/cortexes:*` (`/cortexes:genesis`, `/cortexes:evolve`,
   `/cortexes:distill`, `/cortexes:query`, `/cortexes:broadcast`,
   `/cortexes:takeoff`). Natural-language triggers are unchanged — "存到
   cortex" and "查 cortex" still work.
4. **If your vault has a `Weekly/` directory, move what you still want.**
   `Weekly/` is no longer part of the vault taxonomy: 2.0 does not create it,
   index it, search it, or list it. It was already unreachable — the weekly
   report skill went in 0.22.0 and `Weekly/` left the index back in 0.5.0 —
   so this changes nothing about what you can find. Cortexes will **not**
   move, rewrite, or delete an existing `Weekly/`; copy anything still worth
   keeping into `Notes/` or `Projects/` yourself, at your own pace, and
   whatever you leave stays where it is.
5. **Upgrade the CLI too.**

   ```bash
   uv tool upgrade cortex-vec    # or: pip install -U cortex-vec
   ```

   `cortex-vec` 0.8.0 is what carries the Weekly removal into the CLI —
   `--type weekly` is gone from `search --help` and `Weekly/` is no longer
   classified as a content type. The plugin works with 0.7.0, so this is not
   urgent, but until you upgrade the CLI's own help still advertises the
   retired filter.
6. **Nothing else changes.** `~/.cortex/config.json`, the vector/BM25 indexes
   and caches, and the `CORTEX_*` environment variables all keep their names
   and paths. No rebuild, no re-index, no config edit.

## Website

Live docs and changelog: <https://cortexes.pages.dev> (Cloudflare Pages,
generated from `.cc-marketspec/dist/manifest.json`).
See [`site/README.md`](site/README.md) for local builds.

## Commands & Skills

### Commands

| Command | Description |
|---------|-------------|
| `/cortexes:genesis` | Initialize the vault — set path, author, rebuild the index |
| `/cortexes:evolve` | Manually save knowledge to Notes or Projects (also writes `log.md`) |
| `/cortexes:distill` | Distill Raw/ session records into Notes/Projects (map-first navigation + two-stage evaluation + pending-merge exit) |
| `/cortexes:query` | Search the vault — semantic (`cortex-vec`) with grep and BM25 fallbacks. Running it counts as an explicit request, so it searches even when the session opted out |
| `/cortexes:broadcast` | Fuse newly distilled content into related existing pages (llm-wiki-style ingest) |
| `/cortexes:takeoff` | Hand-off batons — curate temporary, non-git hand-offs for a later session to resume, one per work line (`[topic]` / `resume [topic]` / `done [topic]` subcommands) |

### Skills (auto-triggered)

| Skill | Trigger |
|-------|---------|
| cortex-evolve | "save to cortex", "note this down", "remember this" |
| cortex-distill | "distill", "clean up raw", "distill raw records" |
| cortex-broadcast | "broadcast", "merge pending-merge", "fuse this into the vault" |
| cortex-takeoff | "hand off", "takeoff", "hand off to next session", "context is running low" |
| cortex-query | "check cortex", "have I noted this before", "is this in cortex" |

### Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| Session Report | SessionEnd | On session end, filters the transcript through a TOML pipeline before writing to Raw/ |
| Memory Injection | SessionStart | Interactive menu — checks vault backlog status and asks what to do next |

> **Recording is automatic.** Every session over 4 KB is written to your
> vault when it ends — there is no per-session prompt. Set
> `CORTEX_SKIP_RECORD=1` to skip a session, and see
> [`PRIVACY.md`](PRIVACY.md) for exactly what is captured, what is
> excluded, and what (if anything) leaves your machine.

#### Transcript Filter (0.9.0+)

Before writing to Raw/, the SessionEnd hook runs a TOML-driven filter pipeline that
strips tool output with no knowledge value (e.g. `ls`, volume listings,
repetitive build logs) — you can write custom filters per slash command so
what lands in Raw/ actually carries signal.

## Architecture

```
cortex repo
├── plugin branch (orphan)     ← the Claude Code plugin (this file lives here)
└── main branch                ← Obsidian vault data

~/.cortex/
├── config.json                ← settings produced by genesis
└── vectorstore/                ← ChromaDB semantic index (local only, not in git)
```

### Vault Structure

```
Raw/YYYY/MM/DD/                ← session dumps (complete, distilled on demand)
Notes/<category>/              ← distilled technical knowledge
Projects/<repo-name>/          ← project notes organized by repo
_index.md                      ← vault-wide summary index
log.md                         ← chronological history of evolve/distill
```

Nothing machine-checks `_index.md` for consistency (reorganizing pages is the
one path that changes the index with no skill involved). See
[`docs/index-audit.md`](docs/index-audit.md) for the audit, and for the regex
traps that let a naive check pass while reporting the wrong set.

### Data Flow

```
Every session:
  SessionStart → surfaces available memory → user decides whether to load it
  ...work happens...
  session ends → SessionEnd hook → filter → Raw/   (automatic, no prompt)

Anytime:
  /cortexes:evolve    → Notes/Projects + _index.md + log.md + vector store
  /cortexes:query     → vector search → precise file reads

Periodically:
  /cortexes:distill   → Raw → Notes/Projects (+ pending-merge → broadcast)
  /cortexes:broadcast → pending-merge → fused into existing Notes/Projects
```

### Retrieval Strategy

**Hybrid retrieval** (0.4.0+) — BM25 + vector dual streams, fused with
Reciprocal Rank Fusion (RRF, k=60), default weights w_bm25=0.4 / w_vec=0.6:

- **BM25 stream** — exact lexical matching (function names, repo names,
  issue IDs), with jieba CJK segmentation for mixed Chinese/English queries.
  The index persists at `~/.cortex/bm25/`, kept in sync with ChromaDB by
  `rebuild`/`upsert`/`delete`.
- **Vector stream** — OpenAI `text-embedding-3-small` semantic search,
  dual-vector (document body + bilingual summary), covering cases that are
  semantically close but lexically different.
- **Degradation strategy** — without `OPENAI_API_KEY`, or offline, this
  automatically falls back to BM25-only, with no dependency on the
  skill-layer grep fallback.

Other layers:

1. **Raw search** (on demand) — only queries original session records when
   tracing history

## cortex-vec CLI

The vault's semantic indexing tool, built on ChromaDB + OpenAI
`text-embedding-3-small`, paired with `gpt-5.4-mini` to generate a bilingual
summary as a second embedding (dual-vector) to improve recall for mixed
Chinese/English queries.

```bash
cortex-vec status                          # view index status
cortex-vec rebuild                         # full index rebuild
cortex-vec search "nginx certificate"      # semantic search
cortex-vec search "oauth" --repo acme-core # filter by repo
cortex-vec search "sharing" --type project # filter by type
cortex-vec upsert Notes/Nginx/new.md       # add/update a single document
cortex-vec delete Notes/Nginx/old.md       # delete a document
```

### Hybrid Retrieval (0.4.0+)

`cortex-vec search` now defaults to BM25 + vector RRF hybrid, balancing exact
lexical matches with semantic similarity:

```bash
cortex-vec search "nginx certificate"           # hybrid (default)
cortex-vec search "nginx certificate" --no-bm25 # vector only (debug/eval)
cortex-vec search "nginx certificate" --no-vector # BM25 only (debug/eval)
cortex-vec status                               # shows both vector and BM25 entry counts
```

### Distillation navigation (1.0.0+)

`/cortexes:distill` drives these read-only commands to walk a Raw **without
ever loading the whole file into context**. A Raw is parsed once into a
gap-free, overlap-free source partition; `raw-span` is the only reader that
returns original text, and every page is hard-capped so an oversized session
distills across bounded continuations instead of overflowing context:

```bash
cortex-vec distill-queue --root <vault>/Raw --stat        # per-Raw projected sizes before a batch
cortex-vec raw-view <raw.md>                              # budget-bounded L0–L3 projection
cortex-vec distill-plan start <raw.md>                    # open a coverage/budget plan → plan_id
cortex-vec raw-map  <raw.md> --plan-id <id>               # navigation cards (kind/size/range/anchors)
cortex-vec raw-span <raw.md> --plan-id <id> --span-id <n> # exact original text, one bounded page
cortex-vec distill-plan status --plan-id <id>             # coverage + no-insight gate state
```

The per-Raw plan lives under `$XDG_CACHE_HOME/cortex/distill-plans/` with an
`active.json` pointer enforcing one active Raw at a time (atomic writes,
user-only permissions, fail-closed on corruption or identity drift).

### Raw snapshot reclaim (1.1.0+)

SessionEnd fires more than once per conversation (`/clear`, exit + `--resume`)
and re-filters the same growing transcript each time, so the earlier Raws are
strict prefixes of the latest one. The hook now removes those automatically;
this command is the manual form, and the only way to clean up a backlog
recorded before 1.1.0:

```bash
cortex-vec reclaim-superseded --root <vault>/Raw            # list the whole queue's duplicates
cortex-vec reclaim-superseded --root <vault>/Raw --apply \
  --vault <vault>                                           # remove them (staged with git rm)
```

Only files in the undistilled queue are candidates — a Raw already carrying a
`<!-- distilled: -->` marker is never touched — and a candidate must be a
prefix of its survivor, so the failure mode is "duplicate stays", never
"content lost".

### Retrieval Evaluation

```bash
# Step 1: have an LLM draft candidate queries; a human reviews and confirms
# gold paths before they can be used
cortex-vec eval propose --queries eval-data/cortex-vault-v1.jsonl

# Step 2: run all adapters, print NDJSON results, and write a markdown scorecard
cortex-vec eval run \
  --queries eval-data/cortex-vault-v1.jsonl \
  --adapters grep,vector,bm25,hybrid \
  --k 5 \
  --out docs/benchmarks/$(date +%Y-%m-%d)-cortex-vault-v1.md
```

Supported adapters: `grep` / `vector` / `bm25` / `hybrid`.
Metrics: P@5 / R@5 / MRR / hit.

### Advanced Retrieval (off by default)

The four enhancements below are all disabled by default and require explicit
configuration to enable. **Always measure the P@5 / R@5 / MRR lift with
`cortex-vec eval run`** before and after enabling any of them, before
deciding what's worth defaulting to on and what should be reverted.

#### Synonym expansion

Controlled by config `retrieval.synonym_weight` (`0` = off; try `0.7`). The
BM25 stream boosts documents that match a synonym by that weight, so "OAuth"
can match synonyms like "SSO / auth / authorization."

The synonym table lives at `cortex-vec/src/cortex_vec/synonyms.py`
(common Chinese/English technical terms included) and can be extended.

#### Wikilink graph-boost

Enabled via `cortex-vec search --graph` (or config `retrieval.graph: true`).
Treats "wikilink neighbors of matched results" as a **third RRF stream**
fused into the ranking — surfacing notes that are clearly linked from a hit
but don't directly match the query themselves (recovering neighbors that
vector/BM25 alone would miss).

Tunable parameters: `retrieval.graph_hops` (propagation hops),
`retrieval.w_graph` (the graph stream's weight in RRF, default `0.3`),
`retrieval.graph_top_k` (how many top hits seed the BFS).

> Uses rank-based RRF fusion (not additive boosting), so it's **neutral for
> typical queries and doesn't hurt ranking** — it only adds recall for
> "linked" queries. Measured: no difference on a 20-query general corpus
> with it on/off; R@5 0.50→0.667 on a wikilink-stress corpus.

#### LLM rerank

Enabled via `cortex-vec search --rerank` (or config `retrieval.rerank:
true`). Calls OpenAI (model set by `retrieval.rerank_model`, default
`gpt-5.4-mini`) to re-rank the top `retrieval.rerank_window` (default 15)
hybrid results, replacing pure score ranking with LLM relevance judgment. Any
failure (API error / timeout) automatically falls back to the original RRF
order without affecting search availability.

#### max-per-repo diversification

Controlled by config `retrieval.max_per_repo` (`0` = unlimited), caps how
many results from the same repo can appear in the top-k, preventing one
large repo from drowning out results from other sources.

#### Full `retrieval` config example

The advanced keys under `retrieval` in `~/.cortex/config.json` and their
defaults:

```json
{
  "retrieval": {
    "synonym_weight": 0,
    "graph": false,
    "graph_hops": 1,
    "w_graph": 0.3,
    "graph_top_k": 5,
    "rerank": false,
    "rerank_model": "gpt-5.4-mini",
    "rerank_window": 15,
    "max_per_repo": 0
  }
}
```

Using it with CLI flags:

```bash
# Enable graph-boost + rerank (one-off test)
cortex-vec search "OAuth token" --graph --rerank

# Set synonym_weight, then run eval to confirm the lift
cortex-vec eval run \
  --queries eval-data/cortex-vault-v1.jsonl \
  --adapters hybrid \
  --k 5 \
  --out docs/benchmarks/$(date +%Y-%m-%d)-synonym-0.7.md
```

## Configuration

`~/.cortex/config.json` (generated by genesis):

```json
{
  "vault_path": "/path/to/vault",
  "author": "your-name",
  "author_email": "you@example.com",
  "git": {
    "auto_commit": true,
    "auto_push": false
  }
}
```

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `OPENAI_API_KEY` | No* | OpenAI API key for text-embedding-3-small. Required for `rebuild`/`upsert`/vector search; `search` automatically falls back to BM25-only without it |
| `CORTEX_VAULT_PATH` | No | Read by the SessionStart and takeoff **shell hooks** only. It is **not** a general vault switch: `cortex-vec`, the SessionEnd recorder, and the evolve/distill/broadcast skills all resolve the vault from `config.json`, and the BM25/vector indexes live at a fixed `~/.cortex/` path either way — so pointing it at a second vault would split reads from writes across one shared index. A real multi-vault design is deferred; see [#20](https://github.com/XBlueSky/cortexes/pull/20) |
| `CORTEX_SKIP_RECORD` | No | When set (e.g. `=1`), the SessionEnd hook skips recording this session into Raw/ — for launcher/probe sessions that carry no distill-worthy content |
| `CORTEX_NO_CLASSIFIER` | No | When set to `1`, the transcript filter never calls the LLM classifier; oversized blocks are kept verbatim instead. Disables **only** the filter's nested classifier calls — it does not affect normal Claude Code session processing, including SessionStart metadata and vault content loaded by commands and skills |

## Dependencies

| Package | Purpose |
|---------|---------|
| [ChromaDB](https://www.trychroma.com/) | Semantic vector index |
| [OpenAI](https://platform.openai.com/) | text-embedding-3-small embedding model |
| [python-frontmatter](https://python-frontmatter.readthedocs.io/) | YAML frontmatter parsing |
| pysqlite3-binary | SQLite 3.35+ compatibility (needed when the system SQLite is too old) |

Install:

```bash
uv tool install cortex-vec
```

## Privacy

Cortexes is local-first: your vault is Markdown on your own disk, the index
is local, and the authors receive nothing — there is no server, no account,
and no telemetry.

That is not the same as "nothing leaves your machine". Cortexes is a Claude
Code plugin, so the vault pages a query, distill, broadcast, or takeoff
resume reads become part of the active session and are processed by
Anthropic under your own account — ordinary Claude Code processing, not a
Cortexes channel. The SessionStart hook additionally puts the repo name, the
vault path, and your `Notes/`/`Projects/` topic names into that context
before the menu appears; page contents are not injected there, but may be
loaded later once you pick a menu option, run a command, or make a request
that matches a `using-cortex` signal.

Three flows are initiated by the plugin's own code, all under your control:
the transcript filter sends oversized blocks (>12 KB, capped at 5 per
session) to Anthropic through your own Claude Code to classify them for
compression — `CORTEX_NO_CLASSIFIER=1` disables it, and stops only those
nested calls, not normal session processing; semantic indexing sends vault
page content to OpenAI for embeddings, only if you set `OPENAI_API_KEY`, and
without it retrieval runs on the local BM25 index; and `git push` to a
remote you configured, only if you turn it on (off by default).

[`PRIVACY.md`](PRIVACY.md) documents every data flow in full: what a session
record contains, what is stripped before writing, where files live, git
commit and push behaviour, how to turn each feature off, and how to delete
your data.

## Project Structure

```
commands/       Slash commands (/cortexes:*)
skills/         Self-triggering skills
hooks/          SessionStart/SessionEnd lifecycle hooks
cortex-vec/     Python semantic indexing CLI
site/           Static site generator for cortexes.pages.dev
docs/           Design specs, plans, and benchmark reports
scripts/        Dev tooling (e.g. run-checks.sh)
tests/          Plugin-level tests
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for dev
setup, tests, and the PR process. Please also read the
[Code of Conduct](CODE_OF_CONDUCT.md). Security issues should be reported
privately — see [SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

Licensed under the [Apache License 2.0](LICENSE) — see `LICENSE` for the
full text.
Copyright 2026 XBlueSky (see [NOTICE](NOTICE)).
