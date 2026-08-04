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

Cortex turns your working memory into a searchable knowledge base. Every
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
# From GitHub
/plugin marketplace add https://github.com/XBlueSky/cortexes.git#plugin
```

### 2. Install the cortex-vec CLI

```bash
# cortex-vec ships inside the installed plugin; install from the latest cached version
pip install -e "$(ls -d ~/.claude/plugins/cache/cortex/cortex/*/cortex-vec | sort -V | tail -1)"
```

Requires the `OPENAI_API_KEY` environment variable (used for embeddings).

### 3. Initialize

```bash
/cortex:genesis /path/to/your/vault
```

This sets the vault path and author info, and builds the semantic index.

### 4. Start using it

```
"save to cortex"     → manually save knowledge
"check cortex"       → semantic search over the vault
"distill"            → extract knowledge from Raw/
"broadcast"          → fuse new Raw content into existing pages
```

## Website

Live docs and changelog: <https://cortexes.pages.dev> (Cloudflare Pages,
generated from `.cc-marketspec/dist/manifest.json`).
See [`site/README.md`](site/README.md) for local builds.

## Commands & Skills

### Commands

| Command | Description |
|---------|-------------|
| `/cortex:genesis` | Initialize the vault — set path, author, rebuild the index |
| `/cortex:evolve` | Manually save knowledge to Notes or Projects (also writes `log.md`) |
| `/cortex:distill` | Distill Raw/ session records into Notes/Projects (map-first navigation + two-stage evaluation + pending-merge exit) |
| `/cortex:broadcast` | Fuse newly distilled content into related existing pages (llm-wiki-style ingest) |
| `/cortex:takeoff` | Hand-off baton — curate a temporary, non-git hand-off for the next session to resume (`resume`/`done` subcommands) |

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
  session ends → SessionEnd hook → confirmation → Raw/

Anytime:
  /cortex:evolve    → Notes/Projects + _index.md + log.md + vector store
  /cortex:query     → vector search → precise file reads

Periodically:
  /cortex:distill   → Raw → Notes/Projects (+ pending-merge → broadcast)
  /cortex:broadcast → pending-merge → fused into existing Notes/Projects
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

`/cortex:distill` drives these read-only commands to walk a Raw **without
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
  "author": "tonyhu",
  "author_email": "tonyhu@synology.com",
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
| `CORTEX_VAULT_PATH` | No | Overrides `vault_path` from config.json |
| `CORTEX_SKIP_RECORD` | No | When set (e.g. `=1`), the SessionEnd hook skips recording this session into Raw/ — for launcher/probe sessions that carry no distill-worthy content |

## Dependencies

| Package | Purpose |
|---------|---------|
| [ChromaDB](https://www.trychroma.com/) | Semantic vector index |
| [OpenAI](https://platform.openai.com/) | text-embedding-3-small embedding model |
| [python-frontmatter](https://python-frontmatter.readthedocs.io/) | YAML frontmatter parsing |
| pysqlite3-binary | SQLite 3.35+ compatibility (needed when the system SQLite is too old) |

Install:

```bash
pip install -e ./cortex-vec
```

## Project Structure

```
commands/       Slash commands (/cortex:*)
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
Copyright 2026 tonyhu (see [NOTICE](NOTICE)).
