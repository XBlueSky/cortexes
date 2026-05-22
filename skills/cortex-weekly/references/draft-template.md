# Weekly Draft Template

Detailed format rules and worked example for the weekly report draft.

Reference this file whenever composing Step 6 output (Generate Draft).

## Base principles

- **Output is GitLab Flavored Markdown** — copy-pasted into a GitLab issue/MR description. No Obsidian-only syntax (`[[wikilink]]`, `![[embed]]`, `> [!note]`). Plain `-` bullets only; no Unicode markers.
- **Tab indent** each nested bullet one level. Matches vault convention (`Weekly/2026/2026-03-16.md` and later).
- **Frontmatter is required** at the top. Obsidian consumes it; GitLab renders it as a table or ignores it silently.
- **Meeting Friday date** drives the `title` / `date` fields and the filename.
- **Omit empty sections entirely** — do not print `- fix.` with no children.

```markdown
---
title: "YYYY-MM-DD"
date: YYYY-MM-DD
source: cortex
---
```

## Description budgets

The weekly is consumed by team meeting attendees who skim, not by
vault readers who want depth. Keep descriptions short. Hard ceilings
per surface:

| Surface | Cap | Style |
|---|---|---|
| `feat.` group-MR description | ≤40 chars (Chinese characters or English words counted as 1 each) | "做了什麼" — outcome only. No file paths, no test counts, no benchmark numbers unless they're the punchline. |
| `feat.` / `fix.` vault-only entry description | ≤60 chars | One sentence summarising the issue's progress this week. |
| `inbound.` mail | ≤30 chars after `<subject>: ` | `topic → 我的回應` form. Drop investigation steps, root-cause walkthroughs. |
| `inbound.` wit | ≤60 chars after `: ` | Main answer only. Drop follow-up details and stretch-goal additions. |
| `inbound.` CSS | ≤60 chars after `: ` | Three-segment `symptom → root cause → response` still applies; just keep each segment short. |
| `inbound.` chat | ≤60 chars after `: ` | One-clause `topic → 我的貢獻`. |
| `misc.` per-project | ≤10 chars short tag + MR link, OR a short prose summary when no MR exists (no link in that case). |

When a session genuinely needs more, prefer a sub-bullet under the
MR / group heading rather than blowing the cap on the main line.

## Top-level structure

Four top-level bullet items, not headings:

```
- fix.
- feat.
- inbound.
- misc.
```

Any section with no content is omitted.

## `fix.` and `feat.` — grouped by Workplus issue

Both sections follow the **same layout rules**. The only difference is what lands in each: `fix.` for Workplus issues with `type = BUG`, `feat.` for `type = FEATURE`.

### Single MR per issue → flat bullet

```
- fix.
	- [mr-title](mr-url)
- feat.
	- [mr-title](mr-url)
```

No description, no group heading. The MR title carries the story.

### Multiple MRs per issue → group heading + indented bullets

```
- fix.
	- <Workplus-title-verbatim> - ([<ISSUE-KEY>](<issue-url>))
		- [mr-title](mr-url): one-line description of what the MR does
		- [mr-title](mr-url): one-line description
- feat.
	- <Workplus-title-verbatim> - ([<ISSUE-KEY>](<issue-url>))
		- [mr-title](mr-url): one-line description
		- [mr-title](mr-url): one-line description
			- sub-detail when the MR change is genuinely large
			- sub-detail
	- **[draft]** <experimental title> - ([<ISSUE-KEY>](<issue-url>))
		- [mr-title](mr-url): description
```

Rules (apply to both `fix.` and `feat.`):
- Group-heading bullet is plain text followed by parenthesized issue link. Title is **not** wrapped in `[...]` — intentional so titles like `[webapi] morpheus: ...` do not collide with markdown link syntax.
- **Backtick-escape group titles** that start with `[` or contain `][` (e.g. `[thread+fork][synoscgi] ...`). GFM can mis-parse these as reference-style links:
  ```
  - `[thread+fork][synoscgi] 替換 redis cpp client 實作` - ([DSM-169641](url))
  ```
- Each MR bullet: `[mr-title](mr-url): one-line description`.
- **No prose narrative.** If something needs more explanation, indent another level and list sub-items. Do not write paragraphs.
- Group includes **every** MR sharing the issue ref, regardless of individual commit type (`feat`, `fix`, `chore`, `docs`, `refactor`, `test`). The Workplus issue type decides `fix.` vs `feat.`; the group pulls in all the MRs that serve that issue.
- Prefix a group heading with `**[draft]** ` (bold, trailing space) when every MR in the group targets a repo listed in `weekly.experimental_repos`. Single-MR flat bullets are never draft-labelled.

### Vault-only entry (no MR this week)

When a repo in `weekly.repo_issue_map` has Summary entries this week
but no merged MR ref'ing the issue, the weekly emits a one-line
"vault-only" bullet under `feat.` (if Workplus type is FEATURE) or
`fix.` (if BUG). The format extends the group-heading form with a
trailing `: description`:

````
- feat.
	- [webapi] morpheus: webapi http server framework - ([DSM-172916](url)): prefork worker SIGUSR1 死鎖加 setup_graceful_drain 修
````

Rules:
- Same backtick-escape applies as for group headings — wrap the
  title in backticks when it starts with `[` or contains `][`.
- Description budget: ≤60 chars (see Description budgets).
- The vault-only bullet co-exists with the MR-group form; visually
  distinct by the trailing `: description`.
- See `cortex-weekly` Step 5b for when this shape is emitted.

## `inbound.` — externally-initiated work this week

```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...   ← same-title dedup
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat] <channel-name>: topic → 我的貢獻
	- [chat] `@username`: topic → 我的貢獻
	- [chat] `@user_a`、`@user_b`: topic → 我的貢獻
	- [mail] <subject>: topic → 我的回應
	- [mail] <subject> (`@username`): topic → 我的回應
```

Rules:
- **MR review**: `[mr-title](mr-url)`. Append ` / [KEY](issue-url)` only when the MR's commit messages carry a `Ref:` trailer.
- **wit issue**: `[wit#iid](url): topic → responded` (or `→ resolved`). List only when the configured user posted a note within the week window (see Source D filter).
- **CSS ticket**: `[css#ticket-id](url): symptom → root cause → response` — three-segment form based on reading the actual ticket thread, not an `outcome` summary.
  - `symptom`: what the customer reported
  - `root cause`: what the user diagnosed in their reply (paraphrased, one clause)
  - `response`: what the user did or routed the ticket to
  - Never include customer, colleague, or personal identifiers.
- **ChatPlus thread**: plain text, no URL (the MCP exposes no canonical thread URL). One bullet per `thread_id`, summarizing the user's overall contribution. Drop social chatter, MR-link broadcasts, and meeting-link coordination.
  - Public channel (`channel_name != ""`): `` [chat] <channel-name>: topic → 我的貢獻 ``.
  - 1:1 DM (one non-self participant): `` [chat] `@username`: topic → 我的貢獻 ``.
  - Group DM with 2 other participants: `` [chat] `@user_a`、`@user_b`: topic → 我的貢獻 ``.
  - Group DM with 3 other participants: `` [chat] `@user_a`、`@user_b`、`@user_c`: topic → 我的貢獻 ``.
  - 4+ other participants: `` [chat] DM: topic → 我的貢獻 `` (fall back).
- **Same-topic dedup across threads**: when 2+ chat threads cover
  the same topic (judged by thread subject — e.g. multiple
  conversations about the same CVE, the same MR, the same feature),
  collapse them into one bullet listing all participants:

  ```
  - [chat] `@user_a`、`@user_b`: <topic> → 我的貢獻
  ```

  The order of usernames follows the chronological order of when
  each thread started. The contribution clause merges the
  user-facing answer across threads — don't repeat the same
  technical point twice. Validation-only / acknowledgement-only
  threads stay dropped (substance filter from Source F).
- **MailPlus thread**: plain text, no URL. Strip `Re:` / `Fwd:` (and stacked variants) from `<subject>`. List only threads the user replied to in the Sent folder this week with substantive technical content. Drop HR / recruiting / calendar / mailing-list / pure-logistics replies.
  - 1-on-1 thread (one non-self address across all messages): `` [mail] <subject> (`@username`): topic → 我的回應 ``.
  - Multi-recipient / mailing list (2+ non-self addresses): `` [mail] <subject>: topic → 我的回應 ``.
- **Wrap `@username` in single backticks** in chat/mail bullets — `` `@yannyliu` `` instead of `@yannyliu`. GitLab parses the bare form as a mention and pings the user when the weekly is pasted into a wiki / MR / issue.
- For chat and mail, **never include customer info or external personal identifiers** (phone numbers, emails, addresses). Internal Synology usernames are allowed and encouraged for 1-on-1 attribution.
- Do not prefix items with `(reviewed)`. The link / prefix shape already disambiguates the source (`mr-url` vs `wit#` vs `css#` vs `[chat]` vs `[mail]`).
- **Why `[chat]` / `[mail]` instead of `[chat: ...]` / `[mail: ...]`?** GFM
  treats `[label]: <text>` as a reference-link-definition (where
  `<text>` is interpreted as a URL + optional title). When the
  bracket contains both the tag *and* the subject, the trailing `:`
  triggers that parser and the bullet renders mangled. Putting only
  the source tag inside the bracket keeps the `]:` sequence outside
  the bracket, where it parses cleanly as inline text.

## `misc.` — self side projects, flat list

Three acceptable shapes per project — pick the one that fits the actual activity. Keep each bullet scannable.

```
- misc.
	- [side-project vX.Y.Z](repo-root-url)                           ← version bump
	- project-name: short, comma-separated summary of themes         ← scattered work, no link
	- project-name: summary ([!NN](mr-url), [!MM](mr-url))            ← scattered MRs with links
```

Rules:
- **Version bump shape**: Use when the side project released a tag this week. Link to the repo root; put the version in the link text.
- **Pure-prose shape**: 3–5 short comma-separated themes. Use when no meaningful MR links exist or when listing links would clutter the line. Matches `2026-04-06.md` pattern.
- **Prose + inline MR links**: Use when specific MRs are worth pointing to. Comma-separated `[!NN](url)` after the summary in parentheses.
- One bullet per project. Never split one project's MRs across multiple top-level bullets.
- No MR-title dumps, no nested sub-bullets, no narrative paragraphs.

## Worked example — 2026-04-17

```markdown
---
title: "2026-04-17"
date: 2026-04-17
source: cortex
---

- feat.
	- NextGen-Web-Core - ([DSM-167678](https://workplus.synology.inc/key/DSM/issues/167678))
		- [feat(nginx): add nextweb upstream and routing](https://git.synology.inc/synology/libsynow3/-/merge_requests/263): add nextweb.pass partial, change `@continue` from `try_files → index.cgi` to `proxy_pass → nextweb`, add `= /sharing` exact match, register `127.0.0.1:6667` upstream
		- [chore(projects): register syno-nextweb in build list](https://git.synology.inc/synology/lnxscripts/-/merge_requests/1962): add syno-nextweb to include/projects so BuildAll recognizes it
		- [chore(conf): enable vite cache systemd service](https://git.synology.inc/synology/libdsm/-/merge_requests/244): enable the Vite cache systemd unit for nextwebd
		- [docs: add README with architecture diagram](https://git.synology.inc/synology/syno-nextweb/-/merge_requests/1): architecture overview for nextwebd
		- [fix(benchmark): target nextwebd root path instead of legacy index.cgi](https://git.synology.inc/synology/synowebbenchmark/-/merge_requests/26): DSMIndex benchmark now hits `/` (nextwebd) instead of `/index.cgi` (legacy CGI)
- inbound.
	- [fix(fsdn): recover spk backup from remote when identity mismatch](https://git.synology.inc/synology/synopkg/-/merge_requests/1458) / [DSM-173132](https://workplus.synology.inc/key/DSM/issues/173132)
	- [docs(synology-coverity): note project -gandalf postfix in stream inference](https://git.synology.inc/wit/synology-dev-kit/-/merge_requests/26)
	- [css#3978941](https://cssnew.synology.com/ticket/3978941): package install/start failure → improper shutdown wiped /var/log/nginx, nginx cascade → restart nginx, back to L1
	- [chat] WIT: nextwebd routing for /sharing → confirmed exact-match upstream wiring, pointed to libsynow3!263
	- [mail] [Bad Version] DSM v120060 patch bad (master): patch bad on master → identified offending commit, replied with fix sha and rebuild scope
- misc.
	- cortex: cortex-vec Python package migration, session-start interactive menu, weekly Friday alignment
	- synology-dev-kit: Monitor tool for build progress, build workflow skill extraction, hardlink breakage docs
	- morpheus: app.cpp split into dispatcher/runners/bootstrap
	- syno-naxos: SSH ExitStatus handling fix
	- syno-robinhood: css ticket response template
```

Note: `fix.` omitted because no stand-alone fix existed this week (`synowebbenchmark!26` was folded into the `DSM-167678` feat group).

## Same-title MR dedup (universal)

When 2+ MRs share an exact title within `fix.`, `feat.`, or `inbound.`, collapse them into a single top-level bullet inside that section:

```
- <title> — [!N1](mr-url) / [KEY1](issue-url)、[!N2](mr-url) / [KEY2](issue-url)、...
```

Rules:
- Plain-text title (not a link); each MR remains individually clickable.
- **Placement depends on issue distribution**:
  - All cluster MRs share the same effective issue AND that issue
    has a group heading → the dedup bullet sits **indented inside
    the group**, with no per-MR `/ [KEY](url)` segments (the group
    heading already carries the issue).
  - Cluster MRs reference different issues (or some have no
    effective issue) → the dedup bullet sits **flat at the section's
    top level**, with each MR paired to its own `/ [KEY](url)` (drop
    the segment when the MR has no effective issue).
- Order MRs by `merged_at` ascending — master / earliest first; backports follow.
- Single-MR cases (no duplicate title) are not affected — they keep `[title](url)` (with `/ [KEY](url)` if applicable).

Worked example (`inbound.` cherry-pick cluster):

```
- inbound.
	- fix(api-upload): strip all _tmp params and repair upload Attr wiring — [!695](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/695) / [BSM-1375](https://workplus.synology.inc/key/BSM/issues/1375)、[!696](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/696) / [BSM-1376](https://workplus.synology.inc/key/BSM/issues/1376)、[!698](https://git.synology.inc/synology/webapi-DSM5/-/merge_requests/698) / [AEM-22355](https://workplus.synology.inc/key/AEM/issues/22355)
```

Worked example (`fix.` group with cross-issue cherry-picks):

```
- fix.
	- <Workplus title for issue-X> - ([DSM-X](https://workplus.synology.inc/key/DSM/issues/X))
		- [mr-title-A](url): description
		- [mr-title-B](url): description
	- fix(<scope>): same-title fix on 3 branches — [!N1](url) / [DSM-Y](url)、[!N2](url) / [BSM-Z](url)、[!N3](url) / [AEM-W](url)
```

The dedup bullet sits alongside the regular issue group; it is not nested under any heading.

Worked example (`feat.` group with same-issue dedup pulled inside):

````
- feat.
	- NextGen-Web-Core - ([DSM-167678](https://workplus.synology.inc/key/DSM/issues/167678))
		- [fix(vite): make AppId→chunk lookup 1-to-1](url): 加 schema version + 1-to-1 lookup 修白屏
		- [revert(vite): drop ... template slot](url): importmap 必須最先 fetch、slot 害 module 被 ignore
		- [feat(vite): add AllChunks tag for ...](url): 加 AllChunks tag 處理 no-app desktop CSS
		- fix(renderer): route no-app desktop request through AllChunks — [!337](url)、[!20](url)
````

The last bullet is a same-title dedup (`!337` and `!20` both titled
"fix(renderer): route no-app desktop request through AllChunks"),
indented inside the NextGen-Web-Core group because both MRs ref
DSM-167678. The per-MR `/ [DSM-167678](url)` segments are dropped
since the group heading carries the issue.
