import { readFileSync } from 'node:fs';

export function loadManifest(path) {
  const raw = readFileSync(path, 'utf8'); // 檔案缺失時自然 throw
  const m = JSON.parse(raw);
  if (!Array.isArray(m.plugins) || m.plugins.length === 0) {
    throw new Error(`manifest has no plugins: ${path}`);
  }
  return m;
}

export function getPlugin(manifest) {
  return manifest.plugins[0];
}
