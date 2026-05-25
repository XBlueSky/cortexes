"""Frontmatter parsing and content classification."""

import re
from pathlib import Path

import frontmatter


def parse_document(text):
    """Parse frontmatter and body from markdown text.

    Returns (dict, str) — metadata dict and body content.
    Lists in tags/repos are normalized to comma-separated strings
    (ChromaDB metadata only accepts scalar values).
    """
    post = frontmatter.loads(text)
    fm = dict(post.metadata)

    for key in ("tags", "repos"):
        if key in fm and isinstance(fm[key], list):
            fm[key] = ",".join(str(v) for v in fm[key])

    return fm, post.content


def extract_summary(body, max_len=120):
    """Extract first non-empty, non-heading line from body."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"^>\s*(\[![a-zA-Z]+\])?\s*", "", stripped)
        if stripped:
            return stripped[:max_len]
    return ""


def classify_path(rel_path):
    """Determine (type, category) from vault-relative path.

    Returns:
        tuple: (doc_type, category) e.g. ("note", "Nginx"), ("project", "libsynow3")
    """
    parts = Path(rel_path).parts
    if not parts:
        return "unknown", ""

    top = parts[0]
    if top == "Notes":
        category = parts[1] if len(parts) > 2 else ""
        return "note", category
    elif top == "Projects":
        if len(parts) > 1 and parts[1] == "_archive":
            return "archive", ""
        repo = parts[1] if len(parts) > 1 else ""
        return "project", repo
    elif top == "Weekly":
        return "weekly", ""
    elif top == "Raw":
        return "raw", ""
    return "unknown", ""


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text):
    """Return unique wikilink targets from text. Strips surrounding whitespace
    and drops any `|alias` suffix (Obsidian alias syntax)."""
    targets = []
    seen = set()
    for raw in _WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].strip()
        if target and target not in seen:
            seen.add(target)
            targets.append(target)
    return targets
