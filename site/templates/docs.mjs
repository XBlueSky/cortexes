// site/templates/docs.mjs
import { esc, layout } from '../lib/html.mjs';

function chips(arr) {
  return (arr ?? []).map(e => `<span class="chip">${esc(e)}</span>`).join('');
}

function skillBlock(s) {
  return `<article class="doc-item" id="skill-${esc(s.name)}">
    <h3 class="doc-name mono">${esc(s.name)} <span class="tag auto">auto</span></h3>
    ${s.trigger ? `<p class="doc-trigger"><strong>Trigger:</strong> ${esc(s.trigger)}</p>` : ''}
    ${s.description ? `<p class="doc-desc">${esc(s.description)}</p>` : ''}
    <div class="card-ex">${chips(s.examples)}</div>
  </article>`;
}

function cmdBlock(c) {
  return `<article class="doc-item" id="cmd-${esc(c.name)}">
    <h3 class="doc-name mono">/cortexes:${esc(c.name)}</h3>
    <p class="doc-desc">${esc(c.summary ?? c.description ?? '')}</p>
    <div class="card-ex">${chips(c.examples)}</div>
  </article>`;
}

function noteList(title, arr) {
  if (!arr || !arr.length) return '';
  const items = arr.map(n => `<li>${esc(n.text ?? n)}</li>`).join('');
  return `<div class="doc-notes"><h3 class="mono">${esc(title)}</h3><ul>${items}</ul></div>`;
}

export function renderDocs(plugin) {
  const hooks = (plugin.hooks ?? []).map(h =>
    `<li><span class="mono">${esc(h.event)}</span>${h.why ? ` — ${esc(h.why)}` : ''}</li>`).join('');

  const body = `<section class="block"><div class="wrap narrow">
    <div class="sec-head"><div><span class="eyebrow">docs</span><h2>Skills &amp; Commands</h2></div></div>

    <h2 class="doc-group mono">Skills</h2>
    ${(plugin.skills ?? []).map(skillBlock).join('')}

    <h2 class="doc-group mono">Commands</h2>
    ${(plugin.commands ?? []).map(cmdBlock).join('')}

    ${hooks ? `<h2 class="doc-group mono">Hooks</h2><ul class="doc-hooks">${hooks}</ul>` : ''}
    ${noteList('Tips', plugin.tips)}
    ${noteList('Watch out', plugin.traps)}
  </div></section>`;

  return layout({ title: 'Cortexes — Docs', body, activeNav: 'docs' });
}
