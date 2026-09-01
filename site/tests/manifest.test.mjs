import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadManifest, getPlugin } from '../lib/manifest.mjs';

function tmpManifest(obj) {
  const dir = mkdtempSync(join(tmpdir(), 'cortexes-mf-'));
  const p = join(dir, 'manifest.json');
  writeFileSync(p, JSON.stringify(obj));
  return p;
}

test('loads a valid manifest', () => {
  const p = tmpManifest({ plugins: [{ id: 'cortexes', name: 'cortexes', version: '2.0.0' }] });
  const m = loadManifest(p);
  assert.equal(getPlugin(m).id, 'cortexes');
  assert.equal(getPlugin(m).version, '2.0.0');
});

test('throws when no plugins', () => {
  const p = tmpManifest({ plugins: [] });
  assert.throws(() => loadManifest(p), /no plugins/i);
});

test('throws when file missing', () => {
  assert.throws(() => loadManifest('/nope/manifest.json'));
});
