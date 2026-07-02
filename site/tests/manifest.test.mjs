import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadManifest, getPlugin } from '../lib/manifest.mjs';

function tmpManifest(obj) {
  const dir = mkdtempSync(join(tmpdir(), 'cortex-mf-'));
  const p = join(dir, 'manifest.json');
  writeFileSync(p, JSON.stringify(obj));
  return p;
}

test('loads a valid manifest', () => {
  const p = tmpManifest({ plugins: [{ id: 'cortex', name: 'cortex' }] });
  const m = loadManifest(p);
  assert.equal(getPlugin(m).id, 'cortex');
});

test('throws when no plugins', () => {
  const p = tmpManifest({ plugins: [] });
  assert.throws(() => loadManifest(p), /no plugins/i);
});

test('throws when file missing', () => {
  assert.throws(() => loadManifest('/nope/manifest.json'));
});
