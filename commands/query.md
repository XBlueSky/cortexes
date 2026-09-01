---
name: query
description: Search the cortex vault (Notes, Projects, Weekly, Raw) for existing notes
argument-hint: "[what to search for]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
skills:
  - cortex-query
---

Use the cortex-query skill to search the vault.

Argument handling:

- With arguments → treat `$ARGUMENTS` as the search query verbatim. Do not
  reword or narrow it; the user's phrasing is the query.
- No arguments → ask the user what to search for, then run the search with
  their answer. Do not guess a query from the conversation, and do not
  search the whole vault "to see what's there".

Running this command **is** the user's explicit request (using-cortex signal
1), so the narrow proactive-retrieval policy does not apply here: search,
even if the session earlier opted out of the vault via SessionStart option 4.

Follow the cortex-query skill's layered strategy: `cortex-vec search` first
(repo-scoped by default inside a git repo, overridable with "search all"),
grep as the exact-match supplement, and `Raw/` only on request. Present
results in the skill's response format, and read a full page only when the
user picks one.

If `cortex-vec` is not installed, say so and fall back to grep rather than
failing. Semantic scoring needs `OPENAI_API_KEY`; without it `cortex-vec`
degrades to its local BM25 index on its own, which is still a real search —
report the degraded mode, don't call retrieval unavailable.
