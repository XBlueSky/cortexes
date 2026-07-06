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

// A single spiral thread that runs the full page height as ambient texture,
// echoing the hero art and the logo's interlocking-spiral mark. Fixed
// position + very low opacity: it should read as grain, not decoration.
const PAGE_THREAD_SVG = `<div class="page-thread" aria-hidden="true"><svg viewBox="0 0 1440 6400" preserveAspectRatio="none">
  <path d="M1250,60 C1460,280 1300,540 1030,590 C820,630 710,470 870,390 C980,338 1085,412 1050,495
           C1005,610 760,705 600,915 C475,1080 550,1280 760,1330 C965,1380 1120,1220 1065,1060
           C1020,935 880,905 815,1010 C752,1112 848,1235 985,1245
           C1160,1260 1315,1420 1210,1630 C1125,1795 895,1815 770,1680
           C665,1565 708,1418 845,1398 C960,1378 1022,1502 950,1585
           C875,1668 742,1645 690,1780 C638,1935 795,2090 1000,2038
           C1155,2000 1210,2190 1055,2295 C930,2378 795,2325 775,2450
           C758,2555 900,2660 1055,2608 C1180,2565 1280,2680 1180,2790
           C1100,2878 950,2860 905,2960 C868,3040 950,3120 1050,3090
           C1180,3050 1320,3220 1150,3400 C1010,3550 780,3520 720,3660
           C665,3790 800,3920 970,3870 C1110,3830 1220,3960 1080,4080
           C960,4185 800,4130 730,4260 C665,4380 780,4520 950,4480
           C1090,4448 1180,4580 1030,4680 C900,4767 760,4700 700,4830
           C645,4950 770,5080 940,5030 C1090,4985 1200,5120 1040,5230
           C905,5323 760,5250 700,5390 C648,5515 780,5640 950,5590
           C1090,5548 1180,5680 1020,5780 C880,5867 730,5790 680,5930
           C632,6060 760,6180 930,6130"
        fill="none" stroke="#E8664E" stroke-width="1.6" opacity="0.9"/>
</svg></div>`;

// `body` is TRUSTED RAW HTML — callers pass template-generated markup that has
// already escaped its own leaf data via esc(). Never pass unescaped user/manifest
// data straight into `body`; escape it in the calling template first.
export function layout({ title, body, activeNav = 'home' }) {
  const links = NAV.map(n => {
    const active = n.key === activeNav ? ' aria-current="page"' : '';
    return `<a href="${n.href}"${active}>${esc(n.label)}</a>`;
  }).join('');
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<link rel="icon" type="image/png" href="assets/logo.png">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
${PAGE_THREAD_SVG}
<header><div class="wrap nav">
  <a class="brand" href="index.html"><img class="glyph" src="assets/logo.png" alt="" width="22" height="22">cortexes</a>
  <nav class="nav-links">${links}</nav>
</div></header>
<main>
${body}
</main>
<footer><div class="wrap foot-row">
  <div>© 2026 tonyhu · cortex — personal knowledge base plugin for Claude Code</div>
</div></footer>
</body>
</html>
`;
}
