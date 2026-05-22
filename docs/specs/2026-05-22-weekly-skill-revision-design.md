# Weekly Skill Revision (2026-05-22)

Trims the weekly report for "team-facing" use and fixes a handful of
classification and rendering bugs surfaced when reviewing the
2026-05-22 report.

## Background

Today's auto-generated weekly (`Weekly/2026/2026-05-22.md`) is too
verbose to paste into the team's weekly report — group-MR descriptions
quote root-cause/file-path/test detail, `misc.` entries are
multi-clause, `inbound.` items dump full investigation notes. The
intent of weekly is "what shipped / what landed this week", not "the
vault distilled". A team reader doesn't need the latter.

Three additional defects came out of the same review:

1. **Markdown rendering** — `[mail: subject]: description` collides
   with the GFM reference-link-definition syntax (`[label]: url`) and
   the line either gets eaten or renders mangled. Same hazard on
   `[chat: ...]:`.
2. **Same-title MR dedup pulls out of issue groups** — when two
   backports of the same fix both `Ref:` the same Workplus issue, the
   dedup rule renders them as a flat top-level bullet *outside* the
   issue group, breaking the visual "this fix is part of that
   feature" narrative.
3. **Vault-only work isn't surfaced** — when a repo has an active
   Workplus issue but no MR merged this week (e.g. morpheus →
   DSM-172916), the work shows up in `misc.` with the bare repo name,
   not under `feat.` with the Workplus title and issue link. The
   reader can't tell what feature it was part of.

## Decisions

### 1. Description length budget (five surfaces)

| Surface | Budget | Style |
|---|---|---|
| `feat.` group-MR description | ≤40 chars | "做了什麼" — outcome, not root cause / file path / test count |
| `misc.` entry with MR | ≤10 chars tag | `repo: <tag> ([!N](url))` |
| `misc.` entry, vault-only (no MR) | one-clause | `repo: <短語>` — **no link** |
| `inbound.` mail | ≤30 chars | `[mail] <subject>: topic → 我的回應` |
| `inbound.` wit | one-clause | main answer only, drop follow-up detail |

### 2. `inbound.` chat / mail bracket format (markdown fix)

The bracket now carries **only the source tag**; the subject and
participants move outside the bracket. This avoids the `]:` sequence
that triggers GFM's reference-link-definition parser.

```
- [mail] <subject>: topic → 我的回應
- [mail] <subject> (`@user`): topic → 我的回應        ← 1-on-1 thread
- [chat] <channel-name>: topic → 我的貢獻
- [chat] `@user`: topic → 我的貢獻                     ← 1:1 DM
- [chat] `@user_a`、`@user_b`: topic → 我的貢獻        ← group DM / same-topic dedup
```

`@username` stays in backticks so GitLab does not turn it into a
mention.

### 3. `inbound.` chat same-topic dedup

When two or more chat threads cover the **same topic** (LLM judgment
based on thread subject — e.g. today's nginx CVE discussion split
across `@redhuang` and `@chocoyeh` is one topic), collapse to one
bullet listing all participants.

```
Before:
  - [chat: `@redhuang`]: nginx CVE 影響評估 → ...
  - [chat: `@chocoyeh`]: nginx CVE 與 framework 範圍釐清 → ...

After:
  - [chat] `@redhuang`、`@chocoyeh`: nginx CVE 影響評估與 framework 範圍釐清 → ...
```

Validation-only / acknowledgement-only threads stay dropped (current
substance filter).

### 4. Same-title MR dedup respects issue groups

Current rule unconditionally pulls same-title MRs out of any
Workplus-issue grouping. New rule:

| Dedup'd MRs' issue distribution | Render |
|---|---|
| All `Ref:` the **same** issue AND that issue has a group heading (≥2 MRs total under it) | Indented inside the group as **one** dedup bullet, **no per-MR issue ref** (heading already carries it) |
| `Ref:` **different** issues | Flat at section top level (current behaviour) |

Result on today's report:

```
- feat.
    - NextGen-Web-Core - ([DSM-167678](url))
        - [fix(vite): make AppId→chunk lookup 1-to-1](url): ≤40 字
        - [revert(vite): drop ... template slot](url): ≤40 字
        - [feat(vite): add AllChunks tag for ...](url): ≤40 字
        - fix(renderer): route no-app desktop request through AllChunks — [!337](url)、[!20](url)
                                                                ↑ indented in, no issue ref repeat
```

### 5. Classification rule — normalised (no behaviour change)

Section assignment depends **only** on Workplus issue type:

```
For each self-authored MR:
  if MR commit messages contain "Ref: KEY" trailer OR repo is in repo_issue_map:
    type = workplus_get_issue(KEY).type
    if type == "BUG"      → fix.   under that issue
    if type == "FEATURE"  → feat.  under that issue
    else                  → feat.  (TASK etc.)
  else (no Ref: AND repo not mapped):
    → misc.   (commit type ignored)
```

Commit type (`fix:` / `feat:` / `refactor:` / ...) does **not** decide
section. A `fix:` MR ref'ing a FEATURE issue still goes to `feat.`.

`fix.` is **always flat** — no group headings. The Workplus-title
group-heading format (`<title> - ([KEY](url))`) appears **only** in
`feat.`.

If an MR ends up in `fix.` without an issue ref segment, that's a
rendering / Ref-extraction bug, not a classification choice. Today's
`[fix: silence coverity ...]` line in `fix.` is one such case — its
MR almost certainly carries `Ref: <KEY>` for a BUG issue and the
issue ref segment was dropped. Investigated as part of implementation.

### 6. Repo → issue mapping (new config field)

A new field in `~/.cortex/config.json` lets repos that don't carry
`Ref:` trailers (or that produce vault-only work) be tied to one or
more Workplus issues:

```json
{
  "weekly": {
    "repo_issue_map": {
      "morpheus": ["DSM-172916", "DSM-180000"]
    }
  }
}
```

**Key form**: bare repo name (matches `repo:` frontmatter in
Raw/Summary). When matching GitLab MRs, take the last path segment
(`wit/morpheus` → `morpheus`).

**Value form**: list of Workplus issue keys (1:N — one repo can map
to multiple concurrent features).

**Precedence**:

| Situation | Behaviour |
|---|---|
| MR has `Ref: KEY` trailer | `Ref:` wins; map is not consulted |
| MR has no `Ref:` AND repo is in map | Per-MR issue ambiguous (1:N), classifier falls back: drop the MR to `misc.` unless distill / weekly can disambiguate from commit body |
| Vault-only (Summary, no MR) AND repo is in map | Use per-Summary `issue:` (written by distill, see §7) |
| Vault-only AND repo not in map | Aggregate into `misc.` with bare name, no link (current behaviour for cortex / kaer-morhen) |

**Backward compat**: when `repo_issue_map` is absent or empty, weekly
behaves exactly as before. No warning, no nag.

### 7. Distill writes per-Summary `issue:`

Today, `Summary/.../*.md` frontmatter carries `raw / repo / distilled`
but no `issue:`. With 1:N mapping, weekly needs to know which of the
candidate issues a given Summary covers. The cleanest place to make
that judgment is at distill time, with the Raw body in context.

**New distill step** (after the existing `repo:` write, before
broadcast):

```
If config.weekly.repo_issue_map[repo] is non-empty:
    candidates = repo_issue_map[repo]
    if len(candidates) == 1:
        issue = candidates[0]
    else:
        # LLM judgment: read Raw body, choose best-fitting candidate
        # or null (off-topic / general maintenance)
        issue = llm_classify(raw_body, candidates) | null
    Write issue: <KEY> into Summary frontmatter (or omit if null).
```

Cost: ≤1 extra LLM call per distilled Raw, only for repos in the
map. Not all Raws.

### 8. Weekly Step 5b — vault-only entries

A new step between current Step 5 (classify) and Step 6 (compose
draft):

```
For each repo in repo_issue_map:
    week_summaries = Summary files for this repo in [start, end)
    group week_summaries by `issue:` field

    for issue_key, summaries in groups:
        if issue_key is null:
            # off-topic / maintenance — fall through to misc.
            continue
        if any MR ref'ing issue_key has been merged this week:
            # already covered by Step 5 MR grouping
            continue
        # vault-only progress
        title, type = workplus_get_issue(issue_key)
        section = "feat." if type == "FEATURE" else "fix."
        description = llm_compress(summaries, ≤60 chars)
        emit under section as:
            - <title> - ([<KEY>](<url>)): <description>
```

For `issue_key: null` summaries, fall through into the existing
`misc.` aggregator with bare repo name, no link.

### 9. Step 4 merge join key change

Current Step 4 joins MR ↔ Summary by **repo + date**. With per-Summary
`issue:`, the join becomes more precise:

- If the MR has `Ref:` and the Summary has `issue:` matching → join.
- If the MR has `Ref:` but the Summary `issue:` is null or different
  → no join; the MR stands alone (or under its own Workplus title).
- Fallback to repo+date when either side lacks the issue field
  (backward compat with Summaries written before this change).

## Migration

- Old Summaries without `issue:` frontmatter remain valid; weekly
  treats their `issue:` as undefined and falls back to repo+date.
- A future `cortex-distill --rewrite-issue` pass could backfill the
  field, but not in this revision.
- `~/.cortex/config.json` without `repo_issue_map` continues to work;
  Step 5b is a no-op.

## Out of scope (explicit non-goals)

- Auto-derivation of issue refs from commit-message scanning across
  the whole repo history (heuristic — too fragile).
- Promoting `fix.` to have group headings (decided: `fix.` stays flat).
- Surfacing vault-only BUG progress in `fix.` — possible later, but
  morpheus case is FEATURE only; no current example demands it.

## Today's report — before vs after (excerpt)

### Before

```
- feat.
    - NextGen-Web-Core - ([DSM-167678](url))
        - [fix(vite): make AppId→chunk lookup 1-to-1](url): vite redis cache 缺 schema version + reflection 對缺鍵 silent skip → 升 libdsm.so 後舊 snapshot 反序列化「成功」但 app_id_to_chunk_map 為空 → AppId lookup 回傳空 → SDS launcher 白屏；改成 1-to-1 owning chunk lookup + first-wins collision + 2 個新 unit test，cache key prefix 加版本字串作結構性 fix
        - [revert(vite): ...](url): (300+ char description)
        - [feat(vite): ...](url): (300+ char description)
    - fix(renderer): route no-app desktop request through AllChunks — [!337] / DSM-167678、[!20] / DSM-167678
    [... no morpheus ...]
- misc.
    - syno-build-mcp: resolveTarballPath 預設改 debug variant ... (multi-clause)
    - syno-naxos: workspace_config 加 source_dir_name virtual-suffix stripper ... (multi-clause)
    - morpheus: prefork worker SIGUSR1/SIGUSR2 signal_set::async_wait 永生重 arm 卡 child_io.run() → ...
    - kaer-morhen: morpheus benchmark 重組為 trilogy ...
    - cortex: distill has_insight() 從 string-match ...
```

### After

```
- feat.
    - NextGen-Web-Core - ([DSM-167678](url))
        - [fix(vite): make AppId→chunk lookup 1-to-1](url): 加 schema version + 1-to-1 lookup 修白屏
        - [revert(vite): drop ... template slot](url): importmap 必須最先 fetch、slot 害 module 被 ignore
        - [feat(vite): add AllChunks tag for ...](url): 加 AllChunks tag 處理 no-app desktop CSS
        - fix(renderer): route no-app desktop request through AllChunks — [!337](url)、[!20](url)
    - [webapi] morpheus: webapi http server framework - ([DSM-172916](url)): prefork worker SIGUSR1 死鎖加 setup_graceful_drain 修
- misc.
    - syno-build-mcp: dev-patch debug variant ([!24](url))
    - syno-naxos: workspace_config + targets.json ([!17](url))
    - synology-dev-kit: schema doc Variants 章節 ([!41](url))
    - syno-robinhood: plugin env pass-through ([#12](url))
    - cortex: distill has_insight 重寫 + weekly Step 5.5
    - kaer-morhen: morpheus benchmark trilogy + plugin 0.3.0
```

## Implementation order

1. **Schema + parsing** — add `repo_issue_map` to config, plumb into
   weekly and distill skills. No behaviour change unless field
   populated.
2. **Distill `issue:` writeback** — new step in distill, gated on
   `repo_issue_map`.
3. **Weekly Step 5b** — vault-only entries.
4. **Step 4 join change** — use issue field when present.
5. **Description budgets** — update `references/draft-template.md`
   with the new lengths and apply them in Step 6.
6. **chat / mail bracket reshape** — update template and Source F / G
   formatters.
7. **Same-title dedup group-aware** — refine Step 5 dedup logic.
8. **Classification normalisation** — re-state Step 5 to remove
   ambiguity; investigate the `coverity` line as a likely
   Ref-extraction bug.

Steps 1-4 share infrastructure (issue field plumbing) and should
land together. Steps 5-8 are independent template / classifier
tweaks and can be split into smaller commits.
