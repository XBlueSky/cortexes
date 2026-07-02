import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderChangelog } from '../templates/changelog.mjs';

const V = [
  { version: '0.23.0', date: '2026-07-02', sections: [
    { type: 'Removed', items: ['drop coupling', 'drop synonyms'] },
  ] },
  { version: '0.21.0', date: '2026-06-30', sections: [
    { type: 'Added', items: ['takeoff baton'] },
  ] },
];

test('renders all versions and items', () => {
  const html = renderChangelog(V);
  assert.match(html, /0\.23\.0/);
  assert.match(html, /0\.21\.0/);
  assert.match(html, /drop coupling/);
  assert.match(html, /takeoff baton/);
});

test('renders empty state', () => {
  const html = renderChangelog([]);
  assert.match(html, /暫無紀錄/);
});
