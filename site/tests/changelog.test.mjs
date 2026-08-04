// site/tests/changelog.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseChangelog } from '../lib/changelog.mjs';

const SAMPLE = `# Changelog

Some intro text.

## [0.23.0] - 2026-07-02

### Removed
- item A
- item B

### Fixed
- item C

## [0.21.0] - 2026-06-30

### Added
- item D
`;

test('parses versions in order', () => {
  const out = parseChangelog(SAMPLE);
  assert.equal(out.length, 2);
  assert.equal(out[0].version, '0.23.0');
  assert.equal(out[0].date, '2026-07-02');
  assert.equal(out[1].version, '0.21.0');
});

test('parses sections and items', () => {
  const out = parseChangelog(SAMPLE);
  assert.deepEqual(out[0].sections.map(s => s.type), ['Removed', 'Fixed']);
  assert.deepEqual(out[0].sections[0].items, ['item A', 'item B']);
  assert.equal(out[1].sections[0].type, 'Added');
});

test('returns empty array on no versions', () => {
  assert.deepEqual(parseChangelog('# Changelog\n\nnothing here'), []);
});

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

test('parses the real CHANGELOG.md', () => {
  const md = readFileSync(join(here, '../../CHANGELOG.md'), 'utf8');
  const out = parseChangelog(md);
  assert.ok(out.length >= 10, 'expected many versions');
  assert.equal(out[0].version, '1.2.0');
});
