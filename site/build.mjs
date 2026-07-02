// site/build.mjs
import { readFileSync, writeFileSync, mkdirSync, cpSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadManifest, getPlugin } from './lib/manifest.mjs';
import { parseChangelog } from './lib/changelog.mjs';
import { renderLanding } from './templates/landing.mjs';
import { renderDocs } from './templates/docs.mjs';
import { renderChangelog } from './templates/changelog.mjs';

export async function build({ root, outDir }) {
  const manifest = loadManifest(join(root, 'manifest.json'));
  const plugin = getPlugin(manifest);

  let changelog = [];
  const clPath = join(root, 'CHANGELOG.md');
  if (existsSync(clPath)) {
    changelog = parseChangelog(readFileSync(clPath, 'utf8'));
  } else {
    console.warn('warn: CHANGELOG.md not found — changelog page will be empty');
  }

  mkdirSync(outDir, { recursive: true });
  mkdirSync(join(outDir, 'docs'), { recursive: true });

  const files = [];
  const write = (rel, html) => { const p = join(outDir, rel); mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, html); files.push(rel); };

  write('index.html', renderLanding({ plugin, changelog }));
  write('changelog.html', renderChangelog(changelog));
  // docs 頁在子目錄，asset/nav 相對路徑要往上一層。
  // 順序 load-bearing：'index.html'→'../index.html' 必須在 'docs/index.html'→'index.html' 之前，
  // 否則 docs 自連結會被二次改寫（先變成 index.html、再被前一條吃掉變 ../index.html）。勿重排。
  const docsHtml = renderDocs(plugin).replaceAll('href="assets/', 'href="../assets/').replaceAll('href="index.html"', 'href="../index.html"').replaceAll('href="changelog.html"', 'href="../changelog.html"').replaceAll('href="docs/index.html"', 'href="index.html"');
  write('docs/index.html', docsHtml);

  // 複製 assets
  const siteAssets = join(root, 'site', 'assets');
  if (existsSync(siteAssets)) { cpSync(siteAssets, join(outDir, 'assets'), { recursive: true }); files.push('assets/'); }
  const arch = join(root, 'docs', 'images', 'architecture.png');
  if (existsSync(arch)) { mkdirSync(join(outDir, 'assets'), { recursive: true }); cpSync(arch, join(outDir, 'assets', 'architecture.png')); files.push('assets/architecture.png'); }

  return { files };
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const here = dirname(fileURLToPath(import.meta.url));
  const root = join(here, '..');
  build({ root, outDir: join(here, 'dist') })
    .then(({ files }) => console.log(`built ${files.length} files → site/dist`))
    .catch((e) => { console.error(e.message); process.exit(1); });
}
