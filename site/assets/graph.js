// Lightweight force-directed graph for the "your vault is a living graph"
// section. Zero dependencies, mirrors the Obsidian graph-view look since
// Cortex writes directly into Obsidian vault format. Demo topology only.
(function () {
  const canvas = document.getElementById('cortex-graph');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width = canvas.clientWidth * devicePixelRatio;
    canvas.height = canvas.clientHeight * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }
  const W = () => canvas.clientWidth;
  const H = () => canvas.clientHeight;

  const COLORS = { note: '#E8664E', project: '#6FCF97', raw: '#8A867D' };
  const DATA = [
    ['Nginx SSL', 'note'], ['Nginx Reload', 'note'], ['OAuth Flow', 'note'], ['acme-core', 'project'],
    ['Cortex Vault', 'project'], ['Session 07-05', 'raw'], ['Session 07-06', 'raw'], ['BM25 Retrieval', 'note'],
    ['ChromaDB', 'note'], ['Broadcast', 'note'], ['Auth Service', 'project'], ['Session 07-01', 'raw'],
    ['Hybrid Search', 'note'], ['CI Workflows', 'project'], ['Plugin Dev', 'project'], ['Session 06-28', 'raw'],
    ['SessionStart Hook', 'note'], ['Vault Schema', 'note'],
  ];
  const LINKS = [
    [0, 1], [0, 7], [1, 9], [7, 8], [9, 0], [9, 1], [9, 2], [3, 4],
    [4, 0], [4, 7], [5, 0], [5, 9], [6, 1], [6, 9], [2, 10], [10, 4], [11, 4], [4, 8],
    [7, 12], [12, 8], [12, 9], [13, 10], [13, 3], [14, 4], [14, 9], [15, 6], [15, 13],
    [16, 4], [16, 9], [17, 4], [17, 8], [17, 0],
  ];

  let nodes = [];
  function seedNodes() {
    nodes = DATA.map((n, i) => ({
      id: i, label: n[0], type: n[1],
      x: W() / 2 + (Math.random() - 0.5) * W() * 0.7,
      y: H() / 2 + (Math.random() - 0.5) * H() * 0.7,
      vx: 0, vy: 0, r: n[1] === 'project' ? 9 : 6,
    }));
  }

  let dragging = null;
  let hover = null;

  function mousePos(e) {
    const r = canvas.getBoundingClientRect();
    const p = e.touches ? e.touches[0] : e;
    return { x: p.clientX - r.left, y: p.clientY - r.top };
  }
  function nodeAt(x, y) {
    return nodes.find(n => Math.hypot(n.x - x, n.y - y) < n.r + 6) || null;
  }
  canvas.addEventListener('mousedown', e => {
    const { x, y } = mousePos(e);
    dragging = nodeAt(x, y);
    canvas.style.cursor = dragging ? 'grabbing' : 'grab';
  });
  window.addEventListener('mouseup', () => { dragging = null; canvas.style.cursor = 'grab'; });
  canvas.addEventListener('mousemove', e => {
    const { x, y } = mousePos(e);
    if (dragging) { dragging.x = x; dragging.y = y; dragging.vx = 0; dragging.vy = 0; }
    hover = nodeAt(x, y);
  });
  canvas.addEventListener('mouseleave', () => { hover = null; });

  function step() {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      if (a === dragging) continue;
      let fx = 0, fy = 0;
      for (let j = 0; j < nodes.length; j++) {
        if (i === j) continue;
        const b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy + 0.01;
        const f = 2600 / d2;
        fx += dx * f; fy += dy * f;
      }
      fx += (W() / 2 - a.x) * 0.0009;
      fy += (H() / 2 - a.y) * 0.0009;
      a.vx = (a.vx + fx * 0.02) * 0.85;
      a.vy = (a.vy + fy * 0.02) * 0.85;
    }
    LINKS.forEach(([i, j]) => {
      const a = nodes[i], b = nodes[j];
      const dx = b.x - a.x, dy = b.y - a.y, dist = Math.hypot(dx, dy) || 1;
      const target = 130, k = 0.02;
      const f = (dist - target) * k;
      const fx = dx / dist * f, fy = dy / dist * f;
      if (a !== dragging) { a.vx += fx; a.vy += fy; }
      if (b !== dragging) { b.vx -= fx; b.vy -= fy; }
    });
    nodes.forEach(n => { if (n !== dragging) { n.x += n.vx; n.y += n.vy; } });
  }

  function draw() {
    ctx.clearRect(0, 0, W(), H());
    const activeLinks = hover ? LINKS.filter(([i, j]) => i === hover.id || j === hover.id) : [];
    LINKS.forEach(([i, j]) => {
      const a = nodes[i], b = nodes[j];
      const active = hover && (i === hover.id || j === hover.id);
      ctx.strokeStyle = active ? 'rgba(232,102,78,0.7)' : 'rgba(255,255,255,0.09)';
      ctx.lineWidth = active ? 1.6 : 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    nodes.forEach(n => {
      const active = hover === n || activeLinks.some(([i, j]) => i === n.id || j === n.id);
      ctx.beginPath();
      ctx.arc(n.x, n.y, active ? n.r + 2 : n.r, 0, Math.PI * 2);
      ctx.fillStyle = COLORS[n.type];
      ctx.globalAlpha = hover && !active ? 0.35 : 1;
      ctx.fill();
      ctx.globalAlpha = 1;
      if (active) {
        ctx.font = '11px monospace';
        ctx.fillStyle = '#EDEBE6';
        ctx.fillText(n.label, n.x + n.r + 6, n.y + 3);
      }
    });
  }

  let running = true;
  function tick() {
    if (!running) return;
    step();
    draw();
    requestAnimationFrame(tick);
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  resize();
  seedNodes();
  window.addEventListener('resize', () => { resize(); });
  if (reduceMotion) {
    // Settle the layout without a continuous animation loop.
    for (let i = 0; i < 200; i++) step();
    draw();
  } else {
    tick();
  }
})();
