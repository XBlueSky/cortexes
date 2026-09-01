<sub>[English](SECURITY.md) · [繁體中文](SECURITY.zh-TW.md)</sub>

# Security Policy

## Reporting a Vulnerability

If you discover a security issue, **please do not open a public issue**.

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/XBlueSky/cortexes/security/advisories/new).
We'll respond as quickly as we can and coordinate a fix and disclosure.

When reporting, please include:

- The type of issue and the affected component (`cortex-vec`, hooks, the
  website, etc.)
- Steps to reproduce, or a proof of concept
- Potential impact

## What You Should Know

Cortexes handles your personal knowledge vault and API credentials. Keep in
mind:

- **`OPENAI_API_KEY`** comes from an environment variable and is never
  written to the vault or the index. Don't commit it to any repository.
- **Vault content** is your raw session records and notes. The index
  (ChromaDB / BM25) lives locally under `~/.cortex/` and is not committed or
  uploaded by default.
- **Semantic search** sends the content being indexed to OpenAI to generate
  embeddings. If your vault contains sensitive data, evaluate that trade-off
  yourself — without `OPENAI_API_KEY` set, **no vault content is sent to
  OpenAI** and search runs on the local BM25 index.
- **Retrieved content still reaches Anthropic.** Cortexes is a Claude Code
  plugin: whatever a query, distill, broadcast, or takeoff resume reads out
  of `Notes/`, `Projects/`, `Raw/`, or `.takeoff/` enters the current Claude
  Code session and is processed by Anthropic under your own account. That is
  true in BM25-only mode too. It is ordinary Claude Code processing, not a
  Cortexes server or telemetry channel — see [PRIVACY.md](PRIVACY.md).

## Supported Versions

This project ships on a rolling release. Security fixes target the latest
version — please update before reporting an issue.
