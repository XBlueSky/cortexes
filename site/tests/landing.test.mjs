import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderLanding } from '../templates/landing.mjs';

const PLUGIN = {
  tagline: '把每次 session 變成可搜尋的記憶',
  intro: 'Cortex 是外接記憶層。',
  skills: [
    { name: 'cortex-evolve', trigger: '存到 vault', examples: ['存到 cortex'] },
    { name: 'cortex-query', trigger: '查 vault', examples: ['查 cortex'] },
  ],
  commands: [
    { name: 'genesis', summary: '初始化 vault' },
    { name: 'distill', summary: '提煉 Raw' },
  ],
};
const CHANGELOG = [
  { version: '0.23.0', date: '2026-07-02', sections: [{ type: 'Removed', items: ['x'] }] },
];

test('renders tagline and all skill names', () => {
  const html = renderLanding({ plugin: PLUGIN, changelog: CHANGELOG });
  assert.match(html, /可搜尋的記憶/);
  assert.match(html, /cortex-evolve/);
  assert.match(html, /cortex-query/);
});

test('renders command summaries', () => {
  const html = renderLanding({ plugin: PLUGIN, changelog: CHANGELOG });
  assert.match(html, /初始化 vault/);
  assert.match(html, /提煉 Raw/);
});

test('renders commands under the /cortexes: namespace', () => {
  const html = renderLanding({ plugin: PLUGIN, changelog: CHANGELOG });
  assert.match(html, /\/cortexes:genesis/);
  assert.match(html, /\/cortexes:distill/);
  assert.doesNotMatch(html, /\/cortex:/);
});

test('renders latest changelog version', () => {
  const html = renderLanding({ plugin: PLUGIN, changelog: CHANGELOG });
  assert.match(html, /0\.23\.0/);
});

test('escapes html in data', () => {
  const html = renderLanding({ plugin: { ...PLUGIN, tagline: '<script>' }, changelog: [] });
  assert.doesNotMatch(html, /<script>/);
});
