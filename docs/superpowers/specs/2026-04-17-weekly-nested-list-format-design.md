# Weekly Report — Nested Bullet List Format

**Date:** 2026-04-17
**Status:** Approved

## Problem

Commit `e7f0cfa feat(weekly): align to friday-meeting cycle and tighten draft format` (2026-04-17) rewrote `skills/cortex-weekly/SKILL.md` to use H2/H3 headings plus a 2–4 sentence prose narrative requirement per `feat.` group.

Actual vault convention (see `Weekly/2026/2026-03-16.md`, `2026-03-23.md`, `2026-03-30.md`, `2026-04-06.md`) is a single nested bullet list: `- fix.` / `- feat.` / `- misc.` at top, tab-indented sub-bullets, no headings, no prose.

The tightened format diverges from the user's established scanning habit in weekly meetings.

## Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Top-level structure | Single nested bullet list (`- fix.` / `- feat.` / `- inbound.` / `- misc.`) | Matches vault convention and is faster to scan in weekly meeting |
| Indent | Tab | Matches all pre-existing weekly files |
| `fix.` layout | Flat list of MR links, no Workplus grouping | User directive: "fix 應該只要有 mr 即可" |
| `fix.` MR format | `[mr-title](mr-url)` (pure link, no description) | One feature per row, click through for detail |
| `feat.` layout | Group by Workplus issue: `<title> - ([<KEY>](url))` | A feat typically spans multiple MRs; grouping tells the story |
| `feat.` MR format | `[mr-title](mr-url): one-line description` | A big MR deserves a summary; extra tab-indented sub-bullets allowed when change is large |
| `feat.` narrative | Removed | User directive: "feature 裡的也要是條例一項一項簡單說明" |
| New section `inbound.` | Added | Separates "things others kicked to you" (reviews, wit, CSS) from your own side projects (misc.) |
| `inbound.` scope | Items with actual action **within the week cutoff window** | wit issue must have a tonyhu note in `[start, end)`; MR reviews use `list_events action=approved`; CSS uses `css_get_activities` |
| `misc.` layout | Flat list; two shapes — version bump (`[repo vX.Y.Z](repo-url)`) or scattered MRs (`project: summary ([!NN](url), ...)`) | Matches user hybrid preference (option F) |
| `[draft]` prefix | Preserved for `feat.` / `fix.` groups whose MRs all live in `experimental_repos` | Same as previous SKILL; now attached to bullet instead of H3 |

## Final Layout

```markdown
---
title: "YYYY-MM-DD"
date: YYYY-MM-DD
source: cortex
---

- fix.
	- [mr-title](mr-url)
	- [mr-title](mr-url)
- feat.
	- <Workplus title> - ([<KEY>](<issue-url>))
		- [mr-title](mr-url): one-line description
		- [mr-title](mr-url): one-line description
			- detail item 1 (when MR change is large)
			- detail item 2
	- **[draft]** <experimental Workplus title> - ([<KEY>](<issue-url>))
		- [mr-title](mr-url): description
- inbound.
	- [mr-title](mr-url) / [<KEY>](<issue-url>)
	- [wit#NNNN](wit-url): topic → responded
	- [css#NNNNNNN](css-url): symptom → outcome
- misc.
	- [side-project vX.Y.Z](repo-url)
	- project: summary ([!NN](url), [!MM](url))
```

## Classification Rules

| Section | Criteria |
|---------|----------|
| `fix.` | Self-authored MR, commit type = fix; flat list regardless of issue ref |
| `feat.` | Self-authored MR, commit type = feat with issue ref; grouped by Workplus issue, includes supporting chore/docs MRs of the same issue |
| `inbound.` | Others' MR you approved this week / wit issue you replied this week / CSS ticket you acted on this week |
| `misc.` | Self-authored side project (typically no issue ref); one line per project |

## wit Issue Filter (New)

Before listing a wit issue:

1. Fetch `list_issue_discussions` for the issue
2. Keep only if tonyhu posted at least one note in `[start, end)`
3. Otherwise drop (a past-week assignment that auto-updated should not re-appear)

## Non-Goals

- Keeping the rewritten H2/H3 + narrative format
- Introducing tooling to auto-generate issue narratives
- Changing the underlying source collection logic (Raw/, GitLab MRs, CSS) — only presentation changes

## Files to Change

1. `skills/cortex-weekly/SKILL.md` — replace Step 6 (Generate Draft) section with new layout + rules
