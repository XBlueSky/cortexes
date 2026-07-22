// site/tests/build.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build } from '../build.mjs';

function fixtureRoot() {
  const root = mkdtempSync(join(tmpdir(), 'cortex-build-'));
  mkdirSync(join(root, '.cc-marketspec', 'dist'), { recursive: true });
  writeFileSync(join(root, '.cc-marketspec', 'dist', 'manifest.json'), JSON.stringify({
    plugins: [{
      id: 'cortex', name: 'cortex', tagline: 'T', intro: 'I',
      skills: [{ name: 'cortex-query', trigger: '查', examples: ['查 cortex'] }],
      commands: [{ name: 'genesis', summary: '初始化' }],
      hooks: [{ event: 'SessionEnd', why: '記錄' }],
      tips: [{ text: 'tip1' }], traps: [{ text: 'trap1' }],
    }],
  }));
  writeFileSync(join(root, 'CHANGELOG.md'), '# Changelog\n\n## [0.23.0] - 2026-07-02\n\n### Removed\n- x\n');
  // 讓 build 找得到 site/assets：測試用最小 assets
  mkdirSync(join(root, 'site', 'assets'), { recursive: true });
  writeFileSync(join(root, 'site', 'assets', 'style.css'), '/* css */');
  return root;
}

test('build writes all pages', async () => {
  const root = fixtureRoot();
  const outDir = join(root, 'out');
  const { files } = await build({ root, outDir });
  assert.ok(existsSync(join(outDir, 'index.html')));
  assert.ok(existsSync(join(outDir, 'docs', 'index.html')));
  assert.ok(existsSync(join(outDir, 'changelog.html')));
  assert.ok(existsSync(join(outDir, 'assets', 'style.css')));
  assert.ok(files.length >= 4);
});

test('landing contains skill and tagline', async () => {
  const root = fixtureRoot();
  const outDir = join(root, 'out');
  await build({ root, outDir });
  const html = readFileSync(join(outDir, 'index.html'), 'utf8');
  assert.match(html, /cortex-query/);
  assert.match(html, /T</); // tagline
});

test('docs page rewrites asset path to ../assets', async () => {
  const root = fixtureRoot();
  const outDir = join(root, 'out');
  await build({ root, outDir });
  const html = readFileSync(join(outDir, 'docs', 'index.html'), 'utf8');
  assert.match(html, /\.\.\/assets\/style\.css/);
});

test('throws on missing manifest', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cortex-empty-'));
  await assert.rejects(() => build({ root, outDir: join(root, 'out') }));
});
