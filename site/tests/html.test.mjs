import { test } from 'node:test';
import assert from 'node:assert/strict';
import { esc, layout } from '../lib/html.mjs';

test('esc escapes html-sensitive chars', () => {
  assert.equal(esc('a & b < c > "d" \'e\''), 'a &amp; b &lt; c &gt; &quot;d&quot; &#39;e&#39;');
});

test('layout wraps body and sets title', () => {
  const html = layout({ title: 'T', body: '<main>X</main>', activeNav: 'home' });
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<title>T<\/title>/);
  assert.match(html, /<main>X<\/main>/);
  assert.match(html, /assets\/style\.css/);
});

test('layout marks active nav', () => {
  const html = layout({ title: 'T', body: '', activeNav: 'changelog' });
  assert.match(html, /aria-current="page"[^>]*>changelog|changelog<\/a>/);
});
