import { esc, layout } from '../lib/html.mjs';

function versionBlock(v) {
  const sections = v.sections.map(s => {
    const items = s.items.map(it => `<li>${esc(it)}</li>`).join('');
    return `<div class="cl-section"><h3 class="cl-type mono">${esc(s.type)}</h3><ul>${items}</ul></div>`;
  }).join('');
  return `<article class="cl-version">
    <div class="cl-head"><span class="cl-ver mono">${esc(v.version)}</span><span class="cl-date mono">${esc(v.date)}</span></div>
    ${sections}
  </article>`;
}

export function renderChangelog(versions) {
  const body = `<section class="block"><div class="wrap narrow">
    <div class="sec-head"><div><span class="eyebrow">changelog</span><h2>版本紀錄</h2></div></div>
    ${versions.length ? versions.map(versionBlock).join('') : '<p class="muted">暫無紀錄。</p>'}
  </div></section>`;
  return layout({ title: 'Cortex — Changelog', body, activeNav: 'changelog' });
}
