<sub>[English](CONTRIBUTING.md) · [繁體中文](CONTRIBUTING.zh-TW.md)</sub>

# Contributing to Cortexes

Thanks for your interest in contributing. This document covers how to set up
a dev environment, run the tests, and submit changes.

By participating in this project you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Project Structure

Cortexes splits work across two branches:

| Branch | Contents |
|--------|----------|
| `plugin` (default) | The Claude Code plugin — commands, skills, hooks, the `cortex-vec` CLI, and the website source |
| `main` | Personal Obsidian vault data (not open to outside contributions) |

**All PRs target `plugin`.**

Main subsystems:

- `commands/`, `skills/`, `hooks/` — the plugin's slash commands,
  self-triggering skills, and lifecycle hooks
- `cortex-vec/` — the Python semantic indexing CLI (ChromaDB + OpenAI
  embeddings + BM25 hybrid retrieval)
- `site/` — the static site generator for the website (zero dependencies,
  Node built-ins only)

## Development Setup

### cortex-vec (Python)

```bash
pip install -e ./cortex-vec
```

Requires Python 3.11+. Semantic-search features need `OPENAI_API_KEY`; without
it, everything falls back to BM25-only. Tests don't require an API key.

### Website (Node)

Zero npm dependencies, just Node 18+:

```bash
node site/build.mjs                    # outputs to site/dist/
node --test site/tests/*.test.mjs      # run tests
```

## Running Tests

Make sure tests pass before submitting a PR.

**Python (cortex-vec)** — the project's test gate runs ruff lint + pytest in
one shot:

```bash
./scripts/run-checks.sh
```

We recommend installing the pre-commit hook so this gate runs automatically
on every `git commit`:

```bash
pip install pre-commit
pre-commit install
```

**Website** —

```bash
node --test site/tests/*.test.mjs
```

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.
Scope is the subsystem name, e.g. `feat(takeoff):`, `fix(cortex-vec):`,
`ci(site):`.

## Submitting a PR

1. Branch off `plugin`.
2. Make your changes and confirm the relevant tests pass.
3. Open a PR targeting `plugin`, describing **what** you changed and **how
   you verified it**.
4. CI runs the tests; website changes also get a Cloudflare Pages preview
   deployment.

## Reporting Issues

- **Bugs** and **feature requests** go through the matching
  [issue template](https://github.com/XBlueSky/cortexes/issues/new/choose).
- **Security issues** should not be filed as public issues — see
  [SECURITY.md](SECURITY.md).

## License

By submitting a contribution, you agree to license it under the project's
[Apache License 2.0](LICENSE).
