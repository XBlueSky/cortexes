import { esc, layout } from '../lib/html.mjs';

const PIPELINE = [
  { num: '01 · SessionEnd hook', title: '記錄', desc: 'session 結束自動產出完整報告，存進 vault 的 Raw/。' },
  { num: '02 · /cortex:distill', title: '提煉', desc: '從 Raw 萃取踩坑知識、慣例與關鍵決策成 Notes。' },
  { num: '03 · broadcast', title: '融合', desc: '把新知識 compound 進相關既有頁面，llm-wiki 式。' },
  { num: '04 · /cortex:query', title: '檢索', desc: '中英混合語意搜尋，回答問題前先查 vault。' },
];

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
    <span class="eyebrow">Claude Code plugin · knowledge &amp; memory</span>
    <h1 class="hero-title">${esc(plugin.tagline ?? '')}</h1>
    <p class="hero-sub">${esc(plugin.intro ?? '')}</p>
    <div class="cta-row">
      <a class="btn btn-primary" href="docs/index.html">看它怎麼運作 →</a>
      <a class="btn btn-ghost" href="https://github.com/XBlueSky/cortexes">github ↗</a>
    </div>
    <div class="pipeline">${stages}</div>
  </div></section>
  <section class="block" id="skills"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">${(plugin.skills ?? []).length} skills</span><h2>自動觸發的技能</h2></div></div>
    <div class="grid">${skills}</div>
  </div></section>
  <section class="block" id="commands"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">${(plugin.commands ?? []).length} commands</span><h2>Slash 指令</h2></div></div>
    <div class="cmd-list">${cmds}</div>
  </div></section>
  <section class="block" id="changelog"><div class="wrap">
    <div class="sec-head"><div><span class="eyebrow">changelog</span><h2>版本紀錄</h2></div><p><a href="changelog.html">看完整紀錄 →</a></p></div>
    <div class="log">${logs}</div>
  </div></section>`;

  return layout({ title: 'Cortex — 外接記憶層', body, activeNav: 'home' });
}
