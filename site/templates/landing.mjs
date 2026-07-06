import { esc, layout } from '../lib/html.mjs';

const PIPELINE = [
  { num: '01 · SessionEnd hook', title: 'Capture', desc: 'Every session ends with a full report, saved to the vault’s Raw/.' },
  { num: '02 · /cortex:distill', title: 'Distill', desc: 'Extract hard-won lessons, conventions, and key decisions into Notes.' },
  { num: '03 · broadcast', title: 'Fuse', desc: 'Compound new knowledge into related existing pages, llm-wiki style.' },
  { num: '04 · /cortex:query', title: 'Recall', desc: 'Mixed-language semantic search, checked before every answer.' },
];

// Generated abstract fluid/smoke spiral (see site/assets/hero-spiral.webp).
const HERO_SPIRAL_IMG = `<img class="hero-spiral" src="assets/hero-spiral.webp" alt="" width="1254" height="1254">`;

function skillCard(s) {
  const chips = (s.examples ?? []).map(e => `<span class="chip">${esc(e)}</span>`).join('');
  return `<div class="card">
    <div class="card-top"><span class="card-name">${esc(s.name)}</span><span class="tag auto">auto</span></div>
    <p class="card-trigger">${esc(s.trigger ?? s.description ?? '')}</p>
    <div class="card-ex">${chips}</div>
  </div>`;
}

function cmdRow(c) {
  return `<div class="cmd-row"><span class="cmd-name">/cortex:${esc(c.name)}</span><span class="cmd-desc">${esc(c.summary ?? c.description ?? '')}</span></div>`;
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
function fusionDiffDemo() {
  return `<div class="diff-demo">
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
  </div>`;
}

// Illustrative fixture for the search UX — not a live query against a real vault.
function searchDemoSection() {
  return `<section class="block" id="search"><div class="wrap">
    <div class="grid2">
      <div>
        <span class="eyebrow">cortex-vec search</span>
        <h2>Ask, don't dig</h2>
        <p>Hybrid retrieval (BM25 + vector) — mixed-language queries hit the right passage directly, without you remembering which file it's in.</p>
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
// since Cortex writes directly into Obsidian vault format.
function graphSection() {
  return `<section class="block" id="graph"><div class="wrap">
    <span class="eyebrow">obsidian-native</span>
    <h2>Your vault is a living graph</h2>
    <p>Cortex writes straight into Obsidian vault format — this is the shape wikilinks actually grow into. Try dragging a node.</p>
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

  const skills = (plugin.skills ?? []).map(skillCard).join('');
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
    ${fusionDiffDemo()}
  </div></section>
  ${searchDemoSection()}
  ${graphSection()}
  <section class="block" id="skills"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">${(plugin.skills ?? []).length} skills</span><h2>Skills that trigger themselves</h2></div></div>
    <div class="grid">${skills}</div>
  </div></section>
  <section class="block" id="commands"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">${(plugin.commands ?? []).length} commands</span><h2>Slash commands</h2></div></div>
    <div class="cmd-list">${cmds}</div>
  </div></section>
  <section class="block" id="changelog"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">changelog</span><h2>Version history</h2></div><p><a href="changelog.html">Full history →</a></p></div>
    <div class="log">${logs}</div>
  </div></section>`;

  return layout({ title: 'Cortex — external memory layer', body, activeNav: 'home' });
}
