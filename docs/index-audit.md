# Auditing `_index.md` consistency

`_index.md` carries no machine-checked invariant. It used to have an `entries:`
frontmatter count, but that was a hand-incremented copy of a derived value with
no reader, so it drifted every time a page was renamed or reorganized (280 vs a
true 238 by the time it was removed). The field is gone; this runbook is the
replacement — run it when you suspect the index has fallen out of step with the
files on disk.

## The invariant

One index row per page under `Notes/<topic>/` and `Projects/<repo>/`, excluding
any path containing `_archive`, and excluding the legacy per-repo
`Projects/<repo>/_index.md` files (a leftover from an older layout; only a
handful of repos still have one).

## The audit

Run from the vault root:

```python
import pathlib, re

idx = pathlib.Path("_index.md").read_text(encoding="utf-8")
indexed = re.findall(r"^\| \[\[(.+?)\]\] \|", idx, re.M)

files = [
    f
    for f in list(pathlib.Path("Notes").rglob("*.md"))
    + list(pathlib.Path("Projects").rglob("*.md"))
    if "_archive" not in f.parts and f.name != "_index.md"
]
stems = [f.stem for f in files]

print(f"index rows: {len(indexed)}   pages: {len(files)}")
print("dead links (indexed, no file):", sorted(set(indexed) - set(stems)))
print("orphans (file, not indexed):", sorted(set(stems) - set(indexed)))
print("duplicate rows:", [t for t in set(indexed) if indexed.count(t) > 1])
print("colliding stems:", [s for s in set(stems) if stems.count(s) > 1])
```

A clean vault reports equal counts and four empty lists. `cortex-vec status`
independently reports the BM25 document count, which includes the `_index.md`
files this audit excludes — so expect it to read a few higher.

## Three traps

**Anchor the row regex at the start of the line.** Counting bare `\[\[...\]\]`
occurrences does not count index rows; it counts anything that looks like a
wikilink. Two ways that bites:

- A summary cell may contain a literal wikilink-shaped token as prose — a page
  documenting a config template describes its placeholder as `[[ AUTH_TOKEN ]]`,
  which an unanchored pattern happily reports as an indexed page.
- A summary cell may cross-link to another page, and if that link sits at the
  end of the cell it is followed by ` |`, so even the `\]\] \|` form picks it up
  as a second row on a single line.

`^\| \[\[(.+?)\]\] \|` with `re.M` counts rows. Nothing else does.

**Do not write the title character class as `[^\]]+`.** Page titles may contain
a closing bracket — one is literally about `[label]` being eaten by a markdown
renderer. `[^\]]+` cannot cross that bracket, so the row is skipped. Use a
non-greedy `.+?`.

These two traps compose into the worst case: the unanchored `[^\]]+` form loses
the `[label]` row and gains the `[[ AUTH_TOKEN ]]` prose hit, so the **total
stays the same** while the set is wrong. A count-only check passes; the orphan
comparison then reports one phantom orphan and one phantom dead link. Compare
sets, not sizes.

**Do not key a dict by `Path.stem` to count files.** Several repos keep a
`Projects/<repo>/_index.md`, so `{f.stem: f for f in files}` silently collapses
them into one entry and undercounts. Keep a list (or key by full path) and
filter `_index.md` out explicitly, as above.

## Repairing drift

`/cortexes:genesis` rebuilds `_index.md` from the files on disk, which is the
remediation for a structurally broken index. For a handful of missing or stale
rows, edit them in place — genesis rewrites the whole file and will discard any
hand-tuned ordering.

Renaming or moving a page is the one operation with no skill behind it, and is
therefore where drift originates: `cortex-distill` and `cortex-evolve` only ever
append rows, and `cortex-broadcast` merges content into an existing page without
removing one. After any manual reorganization, run the audit above and
`cortex-vec upsert` / `delete` the affected paths, since vector-store document
ids are paths.

**Normalize `/` in a title to `-` before using it as a filename.** Writing
`Notes/Tools/a/b.md` for a page titled `a/b` creates a phantom directory. This
fails silently because Obsidian resolves `[[a/b]]` as a path-form wikilink, so
the link still opens and only the on-disk structure is polluted. Keep the
original `/` in the frontmatter `title`; normalize only the filename and the
wikilink.
