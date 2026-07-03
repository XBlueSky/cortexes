// 解析 Keep a Changelog 格式：## [x.y.z] - date，其下 ### Type + "- item" 清單。
const VERSION_RE = /^##\s+\[([^\]]+)\]\s*-\s*(.+?)\s*$/;
const SECTION_RE = /^###\s+(.+?)\s*$/;
const ITEM_RE = /^-\s+(.+?)\s*$/;

export function parseChangelog(md) {
  const versions = [];
  let cur = null;
  let sec = null;
  for (const raw of md.split('\n')) {
    const vm = raw.match(VERSION_RE);
    if (vm) {
      cur = { version: vm[1], date: vm[2], sections: [] };
      versions.push(cur);
      sec = null;
      continue;
    }
    if (!cur) continue;
    const sm = raw.match(SECTION_RE);
    if (sm) {
      sec = { type: sm[1], items: [] };
      cur.sections.push(sec);
      continue;
    }
    const im = raw.match(ITEM_RE);
    if (im && sec) sec.items.push(im[1]);
  }
  return versions;
}
