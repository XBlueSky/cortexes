---
name: using-cortex
description: >
  Use when starting any task or answering any non-trivial question in a
  cortex-enabled session — establishes that the cortex vault is the user's
  external memory and should be consulted BEFORE guessing, asking
  clarifying questions, or doing fresh exploration. Trigger unconditionally
  on conversation start, on every new user request that touches a domain
  the user has worked on before, and whenever the request mentions an
  ongoing project, internal company tooling, recurring topic, or anything
  that smells like prior work. If the SessionStart hook surfaced vault
  topics and the request matches one — search first.
---

# Using Cortex — Vault-First Operating Discipline

The cortex vault at the path provided by the SessionStart hook is the
user's **external memory**. It contains distilled Notes, Projects, Weekly
reports, and Raw session transcripts accumulated over months of work. The
user's questions are usually grounded in that prior context — even when
they don't say so.

## The Prime Rule

**Before answering any non-trivial question, scan whether the cortex vault
might already contain relevant prior knowledge. If yes, search it FIRST
via `cortex-query` — before reasoning from scratch, before asking
clarifying questions, before exploring the codebase.**

The cost of an unnecessary cortex query is ~2 seconds. The cost of
re-deriving an answer the user already wrote down is much higher: wasted
turns, drift from the user's actual mental model, and the implicit message
"I didn't bother to check what you told me last week."

## When to Search Cortex Proactively

Trigger `cortex-query` BEFORE responding when ANY of these are true:

1. **Topic match.** The user's request mentions a topic that appears in
   the SessionStart hook's vault topic list (Notes/ or Projects/ entries).
2. **Domain match.** The request touches an ongoing project, internal
   company tooling, plugin development, NAS debugging, infrastructure workflows,
   or any domain the user is known to work in.
3. **Reference signal.** The user says things like "之前那個", "上次的",
   "我記得有", "我們討論過", "那個 ticket", "the project", "the issue" —
   these are explicit pointers to prior context.
4. **Repeated topic.** The current conversation already touched a topic
   that might have a Notes/ or Projects/ page.
5. **Uncertainty.** About to ask a clarifying question — first check if
   the vault answers it.

## When NOT to Search

- Pure code editing in the current repo with no domain ambiguity.
- Trivial questions answerable from the current turn (e.g. "what's 2+2",
  "rename this variable").
- The user explicitly says "don't check cortex" or "just answer directly".

## How to Apply

1. **Acknowledge the vault context** the SessionStart hook provided —
   note the topic list mentally.
2. On each user message, ask yourself: "Could the answer or relevant
   prior context live in the vault?" If 1% chance yes → query.
3. Invoke the `cortex-query` skill (do not grep the vault directly —
   that skill knows the search infrastructure including `cortex-vec`).
4. If results return relevant content, ground your answer in it and cite
   the source page. If not, proceed without it but you've ruled it out.

## Interaction with SessionStart Menu

The SessionStart hook surfaces a 1-4 menu. Even when the user picks
**option 4 ("直接開始工作")** or skips the menu entirely, this skill's
proactive query rule remains in effect. Option 4 means "skip the
introduction ritual" — it does **not** mean "ignore the vault".

## Anti-patterns

- ❌ "Let me think about this from first principles" before checking if
  the user already documented their reasoning.
- ❌ Asking "do you have notes on X?" — just search.
- ❌ Treating cortex as a manual search tool the user must invoke.
- ❌ Skipping query because "the topic isn't in the SessionStart list" —
  the list is top-level only; sub-topics may exist.

## Why This Skill Exists

Without this skill, every cortex skill (`cortex-query`, `cortex-evolve`,
etc.) only fires on explicit user phrases. That makes the vault behave
like a passive filing cabinet instead of a live extension of the user's
working memory. This skill exists to flip the default: **vault-first,
fresh-reasoning second.**
