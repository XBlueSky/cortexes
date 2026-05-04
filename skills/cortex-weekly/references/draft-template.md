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

## `inbound.` — externally-initiated work this week

```
- inbound.
	- [mr-title](mr-url) / [<ISSUE-KEY>](<issue-url>)
	- [mr-title](mr-url)
	- [wit#NNNN](https://git.synology.inc/wit/wit_issues/-/issues/NNNN): topic → responded
	- [css#NNNNNNN](https://cssnew.synology.com/ticket/NNNNNNN): symptom → root cause → response
	- [chat: <channel-or-DM>]: topic → 我的貢獻
	- [mail: <subject>]: topic → 我的回應
```

Rules:
- **MR review**: `[mr-title](mr-url)`. Append ` / [KEY](issue-url)` only when the MR's commit messages carry a `Ref:` trailer.
- **wit issue**: `[wit#iid](url): topic → responded` (or `→ resolved`). List only when the configured user posted a note within the week window (see Source D filter).
- **CSS ticket**: `[css#ticket-id](url): symptom → root cause → response` — three-segment form based on reading the actual ticket thread, not an `outcome` summary.
  - `symptom`: what the customer reported
  - `root cause`: what the user diagnosed in their reply (paraphrased, one clause)
  - `response`: what the user did or routed the ticket to
  - Never include customer, colleague, or personal identifiers.
- **ChatPlus thread**: `[chat: <channel>]: topic → 我的貢獻` — plain text, no URL (the MCP exposes no canonical thread URL). Use `DM` for direct-message channels (`channel_name == ""`). One bullet per `thread_id`, summarizing the user's overall contribution. Drop social chatter, MR-link broadcasts, and meeting-link coordination.
- **MailPlus thread**: `[mail: <subject>]: topic → 我的回應` — plain text, no URL. Strip `Re:` / `Fwd:` (and stacked variants) from `<subject>`. List only threads the user replied to in the Sent folder this week with substantive technical content. Drop HR / recruiting / calendar / mailing-list / pure-logistics replies.
- For chat and mail, **never include other participants' names, user IDs, customer info, or personal identifiers.**
- Do not prefix items with `(reviewed)`. The link / prefix shape already disambiguates the source (`mr-url` vs `wit#` vs `css#` vs `[chat:` vs `[mail:`).

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
	- [chat: WIT]: nextwebd routing for /sharing → confirmed exact-match upstream wiring, pointed to libsynow3!263
	- [mail: [Bad Version] DSM v120060 patch bad (master)]: patch bad on master → identified offending commit, replied with fix sha and rebuild scope
- misc.
	- cortex: cortex-vec Python package migration, session-start interactive menu, weekly Friday alignment
	- synology-dev-kit: Monitor tool for build progress, build workflow skill extraction, hardlink breakage docs
	- morpheus: app.cpp split into dispatcher/runners/bootstrap
	- syno-naxos: SSH ExitStatus handling fix
	- syno-robinhood: css ticket response template
```

Note: `fix.` omitted because no stand-alone fix existed this week (`synowebbenchmark!26` was folded into the `DSM-167678` feat group).
