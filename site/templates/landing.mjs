import { esc, layout } from '../lib/html.mjs';

const PIPELINE = [
  { num: '01 · SessionEnd hook', title: 'Capture', desc: 'Every session ends with a full report, saved to the vault’s Raw/.' },
  { num: '02 · /cortexes:distill', title: 'Distill', desc: 'Extract hard-won lessons, conventions, and key decisions into Notes.' },
  { num: '03 · broadcast', title: 'Fuse', desc: 'Compound new knowledge into related existing pages, llm-wiki style.' },
  { num: '04 · /cortexes:query', title: 'Recall', desc: 'Mixed-language semantic search, run when a request points back at prior work.' },
];

// Generated abstract fluid/smoke spiral (see site/assets/hero-spiral.webp).
const HERO_SPIRAL_IMG = `<img class="hero-spiral" src="assets/hero-spiral.webp" alt="" width="1254" height="1254">`;

// Bento weighting: cortex-query gets the "lead" slot because it's the skill
// that makes memory actually get used, not just stored — the strongest proof
// of the "compounds" pitch. using-cortex/cortex-takeoff are quiet background
// scaffolding, so they share a low-emphasis dashed tile instead of competing
// visually with the skills a user actively invokes.
const LEAD_SKILL = 'cortex-query';
const QUIET_SKILLS = new Set(['using-cortex', 'cortex-takeoff']);

function skillTile(s, variant) {
  const chips = (s.examples ?? []).map(e => `<span class="tile-chip">${esc(e)}</span>`).join('');
  return `<div class="tile ${variant}">
    <div class="tile-top"><span class="tile-dot"></span><span class="tile-name">${esc(s.name)}</span></div>
    <p class="tile-desc">${esc(s.trigger ?? s.description ?? '')}</p>
    <div class="tile-ex">${chips}</div>
  </div>`;
}

function skillsBento(skills) {
  const lead = skills.find(s => s.name === LEAD_SKILL);
  const quiet = skills.filter(s => QUIET_SKILLS.has(s.name));
  const mid = skills.filter(s => s !== lead && !QUIET_SKILLS.has(s.name));

  // Explicit slot classes rather than relying on :nth-of-type — the grid
  // positions (lead spans col 1 / both rows, mid tiles fill col 2-3 row 1
  // then col 2 row 2, quiet backfills the remaining col 3 row 2) depend on
  // DOM order matching this exact layout, so make that dependency visible.
  const midSlotted = mid.map((s, i) => skillTile(s, `mid slot-${i + 1}`));

  const quietTile = quiet.length ? `<div class="tile quiet">
    <div class="tile-top"><span class="tile-name" style="color:var(--muted)">${quiet.map(s => esc(s.name)).join(' · ')}</span></div>
    <p class="tile-desc">${quiet.map(s => esc(s.trigger ?? s.description ?? '')).join(' ')}</p>
  </div>` : '';

  const tiles = [
    lead ? skillTile(lead, 'lead') : '',
    ...midSlotted,
    quietTile,
  ].join('');

  return `<div class="skills-bento">${tiles}</div>`;
}

function cmdRow(c) {
  return `<div class="cmd-row"><span class="cmd-name">/cortexes:${esc(c.name)}</span><span class="cmd-desc">${esc(c.summary ?? c.description ?? '')}</span></div>`;
}

function logItem(v, i) {
  const first = v.sections[0];
  const body = first ? `${esc(first.type)} — ${esc(first.items[0] ?? '')}` : '';
  return `<div class="log-item${i === 0 ? '' : ' dim'}">
    <span class="log-ver mono">${esc(v.version)}</span><span class="log-date mono">${esc(v.date)}</span>
    <div class="log-body">${body}</div>
  </div>`;
}

// Illustrative fixture — shows what a broadcast fusion pass looks like. Not
// live data; kept in sync by hand with the flow described in the pipeline.
// Paired asymmetrically with a big claim rather than a matching sec-head, so
// this doesn't read as "yet another eyebrow+h2+card" block.
function fusionSection() {
  return `<section class="fusion-sec"><div class="wrap">
    <div class="fusion-grid">
      <div class="fusion-claim">
        <span class="eyebrow">03 · broadcast</span>
        <h2>Notes don't wait to be asked.<br>They rewrite themselves.</h2>
        <p>When a session surfaces something that touches an existing page, broadcast fuses it in place — new sections, corrected assumptions, sharpened caveats. The vault edits itself the way a wiki does, not the way a folder does.</p>
      </div>
      <div class="diff-demo">
        <div class="diff-header"><span class="fname mono">Notes/Nginx/ssl-renewal.md</span><span>broadcast · today</span></div>
        <div class="diff-body">
          <div class="diff-line ctx">## SSL certificate management</div>
          <div class="diff-line ctx">Certs expire every 90 days, auto-renewed via certbot.</div>
          <div class="diff-line add">## Reload gotchas</div>
          <div class="diff-line add">Always run \`nginx -t\` before \`nginx -s reload\` —</div>
          <div class="diff-line add">a bad config makes reload fail silently (incident 2026-07-05).</div>
          <div class="diff-line ctx">## Common errors</div>
        </div>
        <div class="diff-foot"><span class="diff-tag">This note just rewrote itself from a new session</span></div>
      </div>
    </div>
  </div></section>`;
}

// Illustrative fixture for the search UX — not a live query against a real vault.
function searchDemoSection() {
  return `<section class="search-sec"><div class="wrap">
    <div class="grid2">
      <div>
        <span class="eyebrow">cortex-vec search</span>
        <h2 class="sec-title-sm">Ask, don't dig</h2>
        <p class="sec-p">Hybrid retrieval (BM25 + vector) — mixed-language queries hit the right passage directly, without you remembering which file it's in.</p>
      </div>
      <div class="term">
        <div class="term-bar"><span class="term-dot"></span><span class="term-dot"></span><span class="term-dot"></span></div>
        <div class="term-body">
          <div><span class="term-prompt">❯</span> <span class="term-cmd">cortex-vec search "nginx reload fails silently"</span></div>
          <div class="term-result">
            <span class="path">Notes/Nginx/ssl-renewal.md</span><span class="score">0.91</span>
            <div class="snippet">...always run <mark>nginx -t</mark> before reload — a bad config makes <mark>reload</mark> fail <mark>silently</mark>...</div>
          </div>
          <div class="term-result">
            <span class="path">Raw/2026/07/05/session.md</span><span class="score">0.78</span>
            <div class="snippet">...nginx reload at 3am didn't take effect, traced to a leftover server block in config...</div>
          </div>
        </div>
      </div>
    </div>
  </div></section>`;
}

// Illustrative vault topology — not the user's real graph. A lightweight,
// dependency-free force-directed layout in the Obsidian graph-view style,
// since Cortexes writes directly into Obsidian vault format. Full-bleed and
// darker than surrounding sections so it reads as the page's visual anchor.
function graphSection() {
  return `<section class="graph-sec"><div class="wrap">
    <span class="eyebrow">obsidian-native</span>
    <h2>Your vault is a living graph,<br>not a filing cabinet.</h2>
    <p>Cortexes writes straight into Obsidian vault format — this is the shape wikilinks actually grow into. Try dragging a node.</p>
    <div class="graph-wrap">
      <span class="graph-hint">drag nodes · hover to highlight links</span>
      <div class="graph-legend">
        <span><i class="dot" style="background:#E8664E"></i>Notes</span>
        <span><i class="dot" style="background:#6FCF97"></i>Projects</span>
        <span><i class="dot" style="background:#8A867D"></i>Raw</span>
      </div>
      <canvas id="cortex-graph"></canvas>
    </div>
  </div></section>
  <script src="assets/graph.js" defer></script>`;
}

export function renderLanding({ plugin, changelog }) {
  const stages = PIPELINE.map((s, i) => `<div class="stage">
    <div class="num mono">${esc(s.num)}</div>
    <div class="st-title">${esc(s.title)}</div>
    <div class="st-desc">${esc(s.desc)}</div>
    ${i < PIPELINE.length - 1 ? '<span class="arrow mono">→</span>' : ''}
  </div>`).join('');

  const skills = plugin.skills ?? [];
  const cmds = (plugin.commands ?? []).map(cmdRow).join('');
  const logs = changelog.slice(0, 3).map(logItem).join('');

  const body = `<section class="hero"><div class="wrap">
    ${HERO_SPIRAL_IMG}
    <img class="hero-logo" src="assets/logo.png" alt="Cortexes" width="96" height="96">
    <span class="eyebrow">Claude Code plugin · self-compounding memory</span>
    <h1 class="hero-title">${esc(plugin.tagline ?? '')}</h1>
    <p class="hero-sub">${esc(plugin.intro ?? '')}</p>
    <div class="cta-row">
      <a class="btn btn-primary" href="docs/index.html">See how it works →</a>
      <a class="btn btn-ghost" href="https://github.com/XBlueSky/cortexes">github ↗</a>
    </div>
    <div class="pipeline">${stages}</div>
  </div></section>
  ${fusionSection()}
  ${searchDemoSection()}
  ${graphSection()}
  <section class="block" id="skills"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">${skills.length} skills</span><h2>Skills that trigger themselves</h2></div></div>
    ${skillsBento(skills)}
  </div></section>
  <section class="block" id="commands"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">reference</span><h2>Commands &amp; history</h2></div></div>
    <div class="ledger">
      <div class="ledger-col">
        <h3>${(plugin.commands ?? []).length} slash commands</h3>
        <div class="cmd-list">${cmds}</div>
      </div>
      <div class="ledger-col">
        <h3>changelog</h3>
        <div class="log">${logs}</div>
        <a class="log-more" href="changelog.html">Full history →</a>
      </div>
    </div>
  </div></section>`;

  return layout({ title: 'Cortexes — external memory layer', body, activeNav: 'home' });
}
