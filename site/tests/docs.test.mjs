// site/tests/docs.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderDocs } from '../templates/docs.mjs';

const PLUGIN = {
  skills: [{ name: 'cortex-query', trigger: '查 vault', description: 'search vault', examples: ['查 cortex'] }],
  commands: [{ name: 'genesis', summary: '初始化 vault', examples: ['/cortex:genesis ~/v'] }],
  hooks: [{ event: 'SessionEnd', why: '自動記錄' }],
  tips: [{ text: '先搜尋再回答' }],
  traps: [{ text: 'baton 不進 git' }],
};

test('renders skill trigger and examples', () => {
  const html = renderDocs(PLUGIN);
  assert.match(html, /cortex-query/);
  assert.match(html, /查 vault/);
  assert.match(html, /查 cortex/);
});

test('renders hooks, tips, traps', () => {
  const html = renderDocs(PLUGIN);
  assert.match(html, /SessionEnd/);
  assert.match(html, /自動記錄/);
  assert.match(html, /先搜尋再回答/);
  assert.match(html, /baton 不進 git/);
});

test('uses ../assets prefix note is handled by build, not here', () => {
  // docs 模板本身用 layout() 產生 assets/ 相對路徑；build 會改寫成 ../assets（見 Task 8）。
  const html = renderDocs(PLUGIN);
  assert.match(html, /assets\/style\.css/);
});
