export function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const NAV = [
  { key: 'docs', href: 'docs/index.html', label: 'skills & commands' },
  { key: 'changelog', href: 'changelog.html', label: 'changelog' },
  { key: 'github', href: 'https://github.com/XBlueSky/cortexes', label: 'github ↗' },
];

export function layout({ title, body, activeNav = 'home' }) {
  const links = NAV.map(n => {
    const active = n.key === activeNav ? ' aria-current="page"' : '';
    return `<a href="${n.href}"${active}>${esc(n.label)}</a>`;
  }).join('');
  return `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header><div class="wrap nav">
  <a class="brand" href="index.html"><span class="glyph mono">C</span>cortex</a>
  <nav class="nav-links">${links}</nav>
</div></header>
${body}
<footer><div class="wrap foot-row">
  <div>© 2026 tonyhu · cortex — Claude Code 個人知識庫 plugin</div>
</div></footer>
</body>
</html>
`;
}
