<sub>[English](PRIVACY.md) · [繁體中文](PRIVACY.zh-TW.md)</sub>

# Privacy Policy

**Last updated: 2026-09-01**

Cortexes is a local-first Claude Code plugin. Your knowledge vault is plain
Markdown in a directory you choose, indexed locally. **The authors of
Cortexes receive no data from you — there is no server, no account, and no
telemetry.** Data that leaves your machine goes to services you already use
or configure yourself — Anthropic through your own Claude Code, OpenAI if
you set a key, and a git remote if you turn pushing on — described in full
below.

This document covers the plugin (commands, skills, hooks) and the
`cortex-vec` CLI it depends on.

## At a glance

| Data | Where it goes | Default |
|---|---|---|
| Session transcripts | Your local vault (`Raw/`) | **On** |
| Large text blocks (>12 KB) during filtering | Anthropic, via your own Claude Code | **On** (opt-out) |
| Vault metadata at session start (repo name, vault path, topic names, baton summaries) | Anthropic, via your own Claude Code | **On** (opt-out) |
| Vault pages read during query / distill / broadcast / takeoff resume | Anthropic, via your own Claude Code | **On** whenever you use those flows |
| Vault page content, for indexing | OpenAI | Only with `OPENAI_API_KEY` |
| Vault commits | Your local git repo | **On** |
| Vault pushes to a git remote | The remote you configured | **Off** (opt-in) |
| Anything at all | The Cortexes authors | Never |

## 1. Session recording

When a Claude Code session ends, the `SessionEnd` hook writes a filtered
record of that session into your vault. **This happens automatically, with
no per-session confirmation prompt.** It is the plugin's core function, and
you should assume every session in a cortex-enabled environment is recorded
unless you disable it (see [§7](#7-how-to-turn-things-off)).

**What is read.** Claude Code passes the hook the path of the current
session's transcript; the hook reads that file. It also reads the working
directory to derive a repository name from the `origin` git remote, used
only to label and group the record.

**What is written.** A Markdown file at
`<vault>/Raw/YYYY/MM/DD/HHMMSS_session_<repo>.md` containing your messages,
Claude's replies, and tool activity — tool invocations are reduced to a
short argument preview, and tool output is compressed by the filter
pipeline described in [§2](#2-data-sent-to-anthropic).

**What is excluded before writing.** Records of type `attachment`,
`file-history-snapshot`, `permission-mode`, `system` and `last-prompt`, plus
the contents of `<local-command-stdout>`, `<local-command-stderr>`,
`<local-command-caveat>`, `<system-reminder>`, `<command-message>` and
`<command-args>` tags.

**When recording is skipped.** Nothing is written if any of these hold: the
transcript is smaller than 4096 bytes; `~/.cortex/config.json` does not
exist or its `vault_path` is missing; `CORTEX_SKIP_RECORD=1` is set; or the
session is itself a nested `claude -p` call made by the filter.

**Sensitive content is not detected or redacted.** If a secret, credential,
or personal detail appears in a session, it will appear in the record. Treat
your vault with the same care as the sessions that produced it.

## 2. Data sent to Anthropic

The transcript filter compresses machine-generated noise while preserving
discussion. Most of that work is local regex and rule-based filtering. For
any single text block **larger than 12 KB** that survives those layers, the
filter asks a model to classify it as `log` or `content` so it knows whether
the block can be safely sampled.

That classification call sends **up to 8 KB of the block's text** to
Anthropic. It is capped at **5 calls per session** with a 20-second timeout
each, and runs through `claude -p` — that is, **your own Claude Code
installation and your own Anthropic credentials**. Cortexes does not hold or
proxy any Anthropic key.

If the call fails, times out, or is disabled, the block is kept verbatim —
the feature only ever affects compression, never whether your data is
preserved.

Set `CORTEX_NO_CLASSIFIER=1` to disable it entirely.

### Vault metadata injected at session start

The classifier is not the only path to Anthropic. Separately, the
`SessionStart` hook **adds vault metadata to the session's context** before
your first message is answered. It injects:

- the current **repository name**, derived from the `origin` git remote;
- the **absolute path of your vault** on disk;
- the **topic names** of every top-level entry under `Notes/` and
  `Projects/` — directory and file names only, not page contents;
- for each pending takeoff baton in this repository, its **topic** and its
  one-line **`summary:`** — plus the baton's **`workdir:`** path whenever
  that path differs from the current repository's toplevel (batons from a
  same-named clone are labelled with their origin).

This is ordinary session context, so it is sent to Anthropic along with the
rest of the conversation whenever the session talks to the model — through
**your own Claude Code installation and your own Anthropic credentials**,
under the normal handling that applies to your account's sessions. Cortexes
does not send it anywhere else. 
Page **contents** are not injected at session start. They may still be
loaded later in the same session — after you pick a menu option, run a
command such as `/cortexes:query`, or make a request that matches one of
`using-cortex`'s four signals — at which point the section above applies.

**The injection happens before the menu is shown, so it cannot be declined
at the menu.** Choosing option 4 ("直接開始工作") stops any further vault
content from being loaded and suppresses proactive searches for the rest of
the session, but it **cannot retract metadata that is already in context**.
If a repository name, a vault path, or a topic or baton summary is itself
sensitive, disable the hook rather than relying on the menu — see
[§7](#7-how-to-turn-things-off).

### Vault content loaded during normal use

Cortexes is a Claude Code plugin, and its skills work by **reading vault
files into the conversation**. Whenever you run a query, a distill, a
broadcast, or resume a takeoff baton, the pages those flows open — under
`Notes/`, `Projects/`, `Raw/`, and `.takeoff/` — become part of the active
Claude Code context and are sent to Anthropic with the rest of the session,
exactly as any file you open in Claude Code is.

This is **ordinary Claude Code processing under your own account**, using
your own installation and your own credentials, governed by whatever data
handling already applies to your Claude Code sessions. It is **not** a
Cortexes server, a telemetry channel, or a separate upload; Cortexes has no
server and receives nothing. It does mean the honest answer to "does my
vault content reach a model?" is **yes — whenever a Cortexes flow reads
it**. That is the point of the plugin: the retrieved page is what grounds
the answer.

The scope is what a flow actually reads, not the whole vault:

- **query** (`/cortexes:query`, or a `using-cortex` signal) — the search
  hits it presents, plus any page you then ask it to open.
- **distill** — the `Raw/` record being distilled (map-first, so spans
  rather than whole files where it can) and the pages it writes.
- **broadcast** — the `Raw/` record being fused and each candidate page it
  opens or edits.
- **takeoff resume** — the `.takeoff/` baton for that work line.

If a page is too sensitive to send to a model, it is too sensitive to keep
in a vault that a model searches. Keep it somewhere else.

## 3. Data sent to OpenAI

All OpenAI features require you to set `OPENAI_API_KEY` yourself. **Without
that variable, no data is ever sent to OpenAI** and retrieval runs entirely
on the local BM25 index. The key is read from the environment and is never
written to the vault, the index, or any config file.

Three features use it:

**Embeddings** (`text-embedding-3-small`) — when you run `cortex-vec
rebuild` or `upsert`, or perform a vector search, the text of the vault
pages being indexed, or your search query, is sent to OpenAI.

**Summaries** — when a page has no summary, the page title, its tags, and
**the first 3000 characters of its body** are sent to OpenAI to generate a
one-line summary.

**Reranking** — off by default. When enabled (`--rerank`, or
`retrieval.rerank` in config), your search query plus the titles and
summaries of roughly the top 15 results are sent to OpenAI for reordering.

Note that `Raw/` session records are **not** indexed by default — the vector
and BM25 indexes cover `Notes/` and `Projects/`. Raw content reaches OpenAI
only after you distill it into a note.

## 4. Where data is stored, and for how long

Everything is on your own machine:

| Path | Contents |
|---|---|
| `<vault>/` | Your notes, projects, and `Raw/` session records (Markdown + git) |
| `~/.cortex/config.json` | Vault path, author name and email, git flags |
| `~/.cortex/vectorstore/` | ChromaDB vector index |
| `~/.cortex/bm25/` | BM25 lexical index |
| `${XDG_CACHE_HOME:-~/.cache}/cortex/distill-plans/` | Distillation working state |

**Retention is indefinite and entirely under your control.** Cortexes never
expires, rotates, or deletes your data on its own. The one exception is
`reclaim-superseded`, which removes redundant `Raw/` records that are strict
prefixes of a longer record of the same conversation — this deletes
duplicates, never unique content.

## 5. Git behaviour

Your vault is a git repository. Two flags in `~/.cortex/config.json` control
what the plugin does with it:

- **`git.auto_commit`** — default **`true`**. After writing a session
  record, the plugin commits it to your local repository.
- **`git.auto_push`** — default **`false`**. If you turn it on, the plugin
  runs `git push` after committing, sending your vault to whatever remote
  you configured.

**If you enable `auto_push`, your session records leave your machine.**
Where they go is entirely determined by your git remote — make sure it is a
repository you control and whose visibility you intend. A vault pushed to a
public repository is public.

Because commits are automatic, deleting a file from the vault does not erase
it from git history. See [§8](#8-deleting-your-data).

## 6. Telemetry

There is none. Cortexes makes no analytics calls, no usage reporting, no
crash reporting and no update checks, and the authors receive nothing.

Outbound network traffic originated by the plugin's own code goes to three
destinations: Anthropic for the filter's classifier calls
([§2](#2-data-sent-to-anthropic)); OpenAI for the embeddings, summary
generation, and optional reranking described in
[§3](#3-data-sent-to-openai); and the git remote you configured when
`git.auto_push` is enabled ([§5](#5-git-behaviour)).

Separately — and this is not a Cortexes network channel — because the plugin
runs *inside* Claude Code, every flow that reads vault content into the
conversation is carried by **Claude Code's own session requests to
Anthropic**, under your account. See
[§2](#vault-content-loaded-during-normal-use).

## 7. How to turn things off

| Goal | How |
|---|---|
| Skip recording one session | Set `CORTEX_SKIP_RECORD=1` in that session's environment |
| Stop all recording | Remove the `SessionEnd` entry from `hooks/hooks.json`, or disable the plugin |
| Stop the filter's classifier calls to Anthropic | Set `CORTEX_NO_CLASSIFIER=1` |
| Stop injecting vault metadata at session start | Remove the `SessionStart` entry from `hooks/hooks.json`, or disable the plugin |
| Stop sending anything to OpenAI | Unset `OPENAI_API_KEY` — retrieval falls back to local BM25 |
| Stop automatic commits | Set `git.auto_commit` to `false` in `~/.cortex/config.json` |
| Stop pushing to a remote | Set `git.auto_push` to `false` (this is the default) |

Turning all of these off keeps recording, indexing and lexical search fully
local. It does **not** make the plugin offline: query, distill, broadcast
and takeoff resume are Claude-driven flows, so using them necessarily puts
the vault content they read into your Claude Code session, which Anthropic
processes ([§2](#vault-content-loaded-during-normal-use)).
`CORTEX_NO_CLASSIFIER=1` stops the filter's nested classifier calls only —
it has no effect on normal Claude session processing.

## 8. Deleting your data

- **Individual records** — delete the file under `<vault>/Raw/`. If
  `auto_commit` was on, also rewrite git history (for example with
  `git filter-repo`) and force-push if you have a remote; a plain `rm` plus
  commit leaves the content recoverable in history.
- **The whole index** — `rm -rf ~/.cortex/vectorstore ~/.cortex/bm25`. The
  index is derived data and can always be rebuilt from the vault with
  `cortex-vec rebuild`.
- **Everything local** — `rm -rf ~/.cortex` and delete your vault
  directory.
- **Data already sent to a third party** — request deletion through OpenAI
  or Anthropic directly, under their policies below. Cortexes cannot recall
  it for you.

## 9. Third-party services

When you enable the features above, your data is handled under those
providers' policies:

- [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy) and
  [API data usage policies](https://openai.com/policies/api-data-usage-policies)
- [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy)

Cortexes is not affiliated with either company beyond being a client of
their APIs.

## 10. Changes and contact

Material changes to this policy will be recorded in
[`CHANGELOG.md`](CHANGELOG.md). Questions about privacy can be raised as a
[GitHub issue](https://github.com/XBlueSky/cortexes/issues); for security
vulnerabilities please follow [`SECURITY.md`](SECURITY.md) instead.
