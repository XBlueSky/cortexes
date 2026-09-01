# cortex-vec

Vector store CLI for the [cortexes](https://github.com/XBlueSky/cortexes)
knowledge vault — hybrid retrieval over a plain-markdown vault, fusing a
persistent BM25 index with OpenAI-embedding vector search (ChromaDB) via
Reciprocal Rank Fusion. Handles mixed Chinese/English content.

The vault is the source of truth (markdown + git); everything this tool
builds is a rebuildable derived index.

## Install

```bash
# Recommended: isolated tool install via uv
uv tool install cortex-vec

# Or with pip
pip install cortex-vec
```

## Usage

```bash
cortex-vec rebuild                # full rebuild (embeddings, needs OPENAI_API_KEY)
cortex-vec rebuild --bm25-only    # rebuild just the BM25 index — free, no API key
cortex-vec search "nginx certificate" --n 5
cortex-vec status                 # index health: vector + BM25 entry counts
```

Configuration lives in `~/.cortex/config.json` (created by the Cortexes
plugin's `/cortexes:genesis` command). `OPENAI_API_KEY` is required for
embeddings; without it, `search` automatically degrades to BM25-only.

This package is the retrieval backend of the
[Cortexes Claude Code plugin](https://github.com/XBlueSky/cortexes) — session
recording, memory distillation, and indexed retrieval for Claude Code. See
the repository for the full documentation.
