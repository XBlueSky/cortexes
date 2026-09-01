---
name: query
description: Manually search the cortex vault (Notes, Projects, Weekly, Raw) for existing notes
argument-hint: "[what to search for]"
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(cortex-vec search:*)
  - Bash(cortex-vec status:*)
  - Bash(grep:*)
  - Bash(git rev-parse:*)
  - Bash(git remote:*)
---

Invoke the `cortexes:cortex-query` skill and follow it for the actual search.
Command frontmatter cannot load a skill for you, so invoke it explicitly with
its fully qualified name via the Skill tool.

Argument handling:

- With arguments → treat `$ARGUMENTS` as the search query verbatim. Do not
  reword or narrow it; the user's phrasing is the query.
- No arguments → ask the user what to search for, then run the search with
  their answer. Do not guess a query from the conversation, and do not
  search the whole vault "to see what's there".

This command is user-invoked only (`disable-model-invocation: true`), so
running it **is** the user's explicit request — using-cortex signal 1. Search
even if the session earlier picked "直接開始工作" at SessionStart.

Follow the skill's layered strategy: `cortex-vec search` first (repo-scoped by
default inside a git repo, overridable with "search all"), exact-match search
as the supplement, and `Raw/` only on request. Present results in the skill's
response format, and read a full page only when the user picks one.

This command pre-approves only the commands that flow needs — `cortex-vec`,
`grep`, and the two `git` calls used to detect the repo — rather than shell
access in general. `grep` is on that list because the vault usually sits
outside the session's working directory, where the Grep tool cannot reach.

Scoped Bash does not escape the workspace boundary the way a blanket `Bash`
approval did. `cortex-vec search` is unaffected (it takes no path argument),
so the normal path still works; only the grep fallback needs the vault to be
inside the working directory or added with `/add-dir <vault_path>`. If that
bites, say so explicitly rather than reporting an empty result.

If `cortex-vec` is not installed, say so and fall back to grep rather than
failing. Semantic scoring needs `OPENAI_API_KEY`; without it `cortex-vec`
degrades to its local BM25 index on its own, which is still a real search —
report the degraded mode, don't call retrieval unavailable.
