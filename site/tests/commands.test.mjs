// site/tests/commands.test.mjs
//
// The marketplace entry and the site both advertise slash commands. Before
// 2.0.0 the docs referenced /cortex:query while no commands/query.md existed,
// so the public page documented a command users could not run. These tests
// keep authored command references tied to real files.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, '../..');
const ENTRY = join(ROOT, '.cc-marketspec/entries/plugin-cortexes.yaml');
const COMMANDS_DIR = join(ROOT, 'commands');

function entryText() {
  return readFileSync(ENTRY, 'utf8');
}

function referencedCommands(text) {
  return [...new Set([...text.matchAll(/\/cortexes:([a-z][a-z0-9-]*)/g)].map(m => m[1]))];
}

test('every /cortexes: command the entry references exists in commands/', () => {
  const names = referencedCommands(entryText());
  assert.ok(names.length > 0, 'entry references no commands');
  for (const name of names) {
    assert.ok(
      existsSync(join(COMMANDS_DIR, `${name}.md`)),
      `entry documents /cortexes:${name} but commands/${name}.md does not exist`,
    );
  }
});

test('the entry uses no bare /cortex: prefix', () => {
  assert.doesNotMatch(entryText(), /\/cortex:/);
});

test('query is a real command, not just a doc reference', () => {
  const names = referencedCommands(entryText());
  assert.ok(names.includes('query'), 'entry does not document /cortexes:query');
  const md = readFileSync(join(COMMANDS_DIR, 'query.md'), 'utf8');
  assert.match(md, /^name: query$/m);
  assert.match(md, /cortex-query/, 'query.md must delegate to the cortex-query skill');
  assert.match(md, /\$ARGUMENTS/, 'query.md must accept $ARGUMENTS');
  assert.match(md, /No arguments/i, 'query.md must say what to do with no arguments');
});

test('every commands/*.md declares a name matching its filename', () => {
  const files = readdirSync(COMMANDS_DIR).filter(f => f.endsWith('.md'));
  assert.ok(files.length >= 6, `expected the full command set, got ${files.length}`);
  for (const f of files) {
    const md = readFileSync(join(COMMANDS_DIR, f), 'utf8');
    assert.match(md, new RegExp(`^name: ${f.replace(/\.md$/, '')}$`, 'm'), `${f} name mismatch`);
  }
});
