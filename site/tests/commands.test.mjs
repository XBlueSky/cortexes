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

// Slash-command frontmatter is the skill frontmatter set. `skills:` is a
// subagent field, not one of these — declaring it in a command file parses
// fine and does nothing, which is worse than an error because it reads like
// the skill is wired up. Source: code.claude.com/docs/en/slash-commands.
const FRONTMATTER_FIELDS = new Set([
  'name', 'description', 'when_to_use', 'argument-hint', 'arguments',
  'disable-model-invocation', 'user-invocable', 'allowed-tools',
  'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background',
  'hooks', 'paths', 'shell', 'metadata', 'license', 'compatibility',
]);

function frontmatterKeys(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---/);
  assert.ok(m, 'no frontmatter block');
  return [...m[1].matchAll(/^([A-Za-z_][A-Za-z0-9_-]*):/gm)].map(x => x[1]);
}

test('no command declares a frontmatter field Claude Code does not support', () => {
  for (const f of readdirSync(COMMANDS_DIR).filter(x => x.endsWith('.md'))) {
    for (const key of frontmatterKeys(readFileSync(join(COMMANDS_DIR, f), 'utf8'))) {
      assert.ok(FRONTMATTER_FIELDS.has(key), `${f}: unsupported frontmatter field "${key}"`);
    }
  }
});

test('no command relies on a skills: frontmatter field', () => {
  for (const f of readdirSync(COMMANDS_DIR).filter(x => x.endsWith('.md'))) {
    const md = readFileSync(join(COMMANDS_DIR, f), 'utf8');
    assert.doesNotMatch(md, /^skills:/m, `${f} declares a no-op skills: field`);
  }
});

// With `skills:` gone, the body is the only thing that wires a command to its
// skill, so a delegating command must name the skill in its fully qualified
// `cortexes:<skill>` form at least once. Later prose may use the short name.
test('commands that delegate name their skill fully qualified at least once', () => {
  const DELEGATES = {
    'query.md': 'cortexes:cortex-query',
    'evolve.md': 'cortexes:cortex-evolve',
    'distill.md': 'cortexes:cortex-distill',
    'broadcast.md': 'cortexes:cortex-broadcast',
    'takeoff.md': 'cortexes:cortex-takeoff',
  };
  for (const [file, skill] of Object.entries(DELEGATES)) {
    const md = readFileSync(join(COMMANDS_DIR, file), 'utf8');
    assert.ok(md.includes(skill), `${file} must invoke ${skill} by its fully qualified name`);
  }
});

test('query is user-invoked only', () => {
  const md = readFileSync(join(COMMANDS_DIR, 'query.md'), 'utf8');
  assert.match(md, /^disable-model-invocation: true$/m,
    'query.md must set disable-model-invocation: true so only the user can run it');
  assert.match(md, /^description: Manually search/m,
    'query.md description must begin with "Manually search"');
});
