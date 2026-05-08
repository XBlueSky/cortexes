# cortex-weekly — Chat/Mail Inclusion + Same-Title MR Dedup

**Date:** 2026-05-08
**Status:** Approved
**Touches:** `skills/cortex-weekly/SKILL.md`, `skills/cortex-weekly/references/draft-template.md`

## Problem

Two pain points surfaced when generating `Weekly/2026/2026-05-08.md`:

1. **ChatPlus/MailPlus rules are too restrictive.** Current SKILL.md says:
   - "Direct-message channels … DMs default to drop"
   - "Never include other participants' names, user IDs, or personal identifiers"
   - "Never include sender, recipient, customer, or colleague names"

   These rules collapsed all 4 substantive 1:1 DM threads into anonymous `[chat: DM]` placeholders. The user wanted those threads attributed to the colleague involved (`@yannyliu`, `@lifonghsu`, `@danielyeh`, `@redhuang`). The rules were authored to avoid leaking customer / external identifiers, but they swept up internal Synology usernames as collateral.

2. **Same-title MRs cherry-picked to multiple branches list as separate bullets.** This week's `inbound.` had three MRs all titled `fix(api-upload): strip all _tmp params and repair upload Attr wiring` (cherry-picked to APM2 / BSM1-0-dev / BSM-master-DSM7-3-new). Each ate one line, repeating the same title. The same problem will recur in `fix.` / `feat.` when the user authors a fix that ships to multiple release branches.

## Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| DM default | DMs no longer auto-drop; substance filter is the only gate | User wants DM substantive threads represented. Same-substance treatment as public channels. |
| Internal usernames | Allowed in `[chat: ...]` and `[mail: ...]` bullets | Synology colleagues' usernames are not personal data in the user's weekly context. |
| Customer info / external identifiers | Still forbidden | Customer names, phones, emails, addresses remain redacted regardless of source. |
| ChatPlus format — public channel | `[chat: <channel-name>]: topic → 我的貢獻` | Unchanged. |
| ChatPlus format — 1:1 DM | `[chat: @username]: topic → 我的貢獻` | New. Resolve via `chat_list_posts(channel_id)` → other `creator_id` → `chat_list_users`. |
| ChatPlus format — group DM (multi-member) | `[chat: @user_a, @user_b, @user_c]: topic → 我的貢獻` — cap at 3 other participants. 4+ others falls back to `[chat: DM]`. | Names get unwieldy past 3; fall back keeps the format scannable. |
| MailPlus format — 1-on-1 thread | `[mail: <subject>] (@username): topic → 我的回應` | New. Resolve from From / To headers. |
| MailPlus format — multi-recipient / mailing list | `[mail: <subject>]: topic → 我的回應` | Unchanged when 3+ participants or mailing list. |
| Same-title MR dedup scope | Universal — applies to `fix.`, `feat.`, `inbound.` | User: "不限於 inbound 因為之後 fix 我也有機會做類似 cherry pick" |
| Same-title MR dedup format | `<title> — [!N1](url) / [KEY1](url)、[!N2](url) / [KEY2](url)、...` | Plain-text title (clickable MR links inline). Dash separator avoids "cherry-pick" framing the user rejected. |
| Same-title MR dedup ordering | `merged_at` ascending | Master/earliest first; backports follow chronologically. |
| Single-MR shape | Unchanged: `[title](url) / [KEY](url)` (or `[title](url)` if no Ref:) | No collapse triggers when only one MR shares a title. |
| Cross-Workplus-issue dedup in fix./feat. | Yes — collapsed bullet sits at section's top level alongside any remaining issue groups | Telling "same fix landed on N branches" as one line is clearer than splitting across N issue groups each containing one MR. |

## Final Layout

### Updated `inbound.` shapes (template)

```
- inbound.
	- [mr-title](mr-url) / [<KEY>](<issue-url>)
	- [mr-title](mr-url)
	- <title> — [!N1](url) / [KEY1](url)、[!N2](url) / [KEY2](url)、...   ← same-title dedup
	- [wit#NNNN](url): topic → responded
	- [css#NNNNNNN](url): symptom → root cause → response
	- [chat: <channel-name>]: topic → 我的貢獻
	- [chat: @username]: topic → 我的貢獻
	- [chat: @user_a, @user_b]: topic → 我的貢獻
	- [mail: <subject>]: topic → 我的回應
	- [mail: <subject>] (@username): topic → 我的回應
```

### Updated `fix.` / `feat.` example (with mixed groups + dedup)

```
- fix.
	- <Workplus title for issue-X> - ([DSM-X](url))
		- [mr-title-A](url): description
		- [mr-title-B](url): description
	- fix(<scope>): same-title fix on 3 branches — [!N1](url) / [DSM-Y](url)、[!N2](url) / [BSM-Z](url)、[!N3](url) / [AEM-W](url)
```

The dedup bullet is a top-level entry alongside the regular issue group; it does not nest under any Workplus issue.

## SKILL.md changes

### Source F (ChatPlus) — replace the DM-drop and name-redaction lines

**Before:**
- "Direct-message channels (`channel_name == ""`, `team_id == 0`) unless the content is clearly a substantive technical exchange — DMs default to drop."
- "Never include other participants' names, user IDs, or personal identifiers."

**After:**
- "DMs (`channel_name == ""`, `team_id == 0`) are not auto-dropped — they go through the same substance filter as public channels."
- "Resolve participant for DMs: call `chat_list_posts(channel_id)`, find non-self `creator_id` values, then `chat_list_users` to map id → username. Cache results across the run."
- "Format: public channel → `[chat: <channel-name>]`; 1:1 DM → `[chat: @username]`; group DM with 2–3 other participants → `[chat: @user_a, @user_b[, @user_c]]`; 4+ other participants → `[chat: DM]`."
- "Never include customer info or external personal identifiers (phone, email, address); internal Synology usernames are allowed."

### Source G (MailPlus) — replace the name-redaction line

**Before:**
- "Never include sender, recipient, customer, or colleague names."

**After:**
- "Resolve counterparty:"
  - "1-on-1 thread (single non-self participant across all messages) → extract `@username` from From / To headers (strip `<email>` form, take local-part)."
  - "Multi-recipient / mailing list (3+ distinct participants) → no `@username`, subject alone identifies the thread."
- "Format: 1-on-1 → `[mail: <subject>] (@username)`; multi → `[mail: <subject>]`."
- "Never include customer info; internal Synology usernames are allowed."

### New sub-section after Step 5 — "Same-title MR dedup"

```
### Same-title MR dedup

After classification (Step 5), within each section that may contain MRs (fix., feat., inbound.):

1. Group MRs by exact title.
2. If 2+ MRs share a title:
   - Pull them out of any Workplus-issue grouping consideration.
   - Render as one top-level bullet:
     `- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...`
   - Pair each MR with its own Ref: issue (drop `/ [KEY](url)` for MRs without one).
   - Order by `merged_at` ascending.
3. Single-MR (no duplicate) keeps existing flat shape.
```

## references/draft-template.md changes

1. **Inbound shapes block:** add the same-title dedup shape and the three new chat/mail variants (see Final Layout above).
2. **ChatPlus rules:** replace the redaction sentence with the public/1:1/group-DM tri-shape spec; update the "never include … names" line to scope it to customer / external identifiers.
3. **MailPlus rules:** add the 1-on-1 vs multi-recipient distinction; same scope-shrink on the redaction line.
4. **New section "Same-title MR dedup (universal)"** with the rule + example.
5. **Worked example (2026-04-17):** unchanged — has no DM cases or same-title clusters, still illustrative for base shapes.

## Out of Scope

- No new config flags. All behavior is the new default.
- No participant-resolve caching layer beyond per-run memoization.
- No retroactive update of past weekly reports.
- No changes to fix./feat. Workplus-issue grouping rule itself; only same-title MRs are pulled out.

## Migration / Compatibility

- Existing weekly reports keep their current shape; they are not regenerated.
- Future runs immediately produce the new format. No state file or version flag.
- Plugin consumers who relied on the strict-redaction rule (e.g., publishing weeklies externally) will need to either edit before publishing or fork the skill — flagged in CHANGELOG.

## Testing

- Verify with this week's data (`Weekly/2026/2026-05-08.md`):
  - 4 chat bullets render with the resolved `@yannyliu`, `@lifonghsu`, `@danielyeh`, `@redhuang`.
  - 3 `fix(api-upload)` MRs collapse into one inbound bullet listing all three with their BSM/AEM refs.
- Add or extend a unit-style test under `tests/` covering:
  - DM thread → `[chat: @username]` resolution path
  - 3-member DM → `[chat: @a, @b]` cap
  - 4+ DM → `[chat: DM]` fallback
  - 2 MRs same title in inbound → one collapsed bullet
  - 1 MR alone → keeps flat shape

## Follow-ups (not blocking this spec)

- Consider whether `cortex:cortex-broadcast` skill should also accept username references in distilled notes (separate spec).
- Worked example refresh — when next week's weekly has a representative DM + dedup case, swap the example.
