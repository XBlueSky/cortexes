"""Filter git output (status, log, diff).

Port of selected pure functions from rtk-ai/rtk's `src/cmds/git/` (MIT,
© rtk-ai):

- format_status_output  (from git.rs, for `git status --porcelain`)
- filter_status_with_args (from git.rs, for human-readable `git status`)
- filter_log_output (from git.rs, commit-block aware)
- parse_user_limit (from git.rs, detect user-supplied -N)
- condense_unified_diff (from diff_cmd.rs, summarise `git diff` by file)

These filters receive the already-captured tool_result; they don't spawn git
themselves. The entry points take (output, command) so they can branch on
command-line flags (--oneline, -N, etc.) without assuming rtk injected the
`---END---` commit markers — our captured output is plain git, not rtk-wrapped.
"""
from __future__ import annotations

import re

# rtk's config defaults (from src/core/config.rs)
_STATUS_MAX_FILES = 15
_STATUS_MAX_UNTRACKED = 10
_LOG_DEFAULT_LIMIT = 10


def _truncate_line(line: str, width: int) -> str:
    if len(line) > width:
        return line[: width - 3] + "..."
    return line


# ---------------------------------------------------------------------------
# git status

def format_status_output(porcelain: str) -> str:
    """Format `git status --porcelain=v1 --branch` output."""
    lines = porcelain.splitlines()
    if not lines:
        return "Clean working tree"

    parts: list[str] = []
    if lines and lines[0].startswith("##"):
        branch = lines[0].removeprefix("## ")
        parts.append(f"* {branch}")

    staged_files: list[str] = []
    modified_files: list[str] = []
    untracked_files: list[str] = []
    staged = modified = untracked = conflicts = 0

    for line in lines[1:]:
        if len(line) < 3:
            continue
        status = line[0:2]
        file = line[3:]

        c0 = status[0] if len(status) > 0 else " "
        c1 = status[1] if len(status) > 1 else " "

        if c0 in ("M", "A", "D", "R", "C"):
            staged += 1
            staged_files.append(file)
        elif c0 == "U":
            conflicts += 1

        if c1 in ("M", "D"):
            modified += 1
            modified_files.append(file)

        if status == "??":
            untracked += 1
            untracked_files.append(file)

    def _emit(label: str, count: int, files: list[str], cap: int) -> None:
        parts.append(f"{label}: {count} files")
        for f in files[:cap]:
            parts.append(f"   {f}")
        if len(files) > cap:
            parts.append(f"   ... +{len(files) - cap} more")

    if staged > 0:
        _emit("+ Staged", staged, staged_files, _STATUS_MAX_FILES)
    if modified > 0:
        _emit("~ Modified", modified, modified_files, _STATUS_MAX_FILES)
    if untracked > 0:
        _emit("? Untracked", untracked, untracked_files, _STATUS_MAX_UNTRACKED)
    if conflicts > 0:
        parts.append(f"conflicts: {conflicts} files")

    if staged == 0 and modified == 0 and untracked == 0 and conflicts == 0:
        parts.append("clean — nothing to commit")

    return "\n".join(parts).rstrip()


def filter_status_with_args(output: str) -> str:
    """Minimal filter for human-readable `git status` output."""
    result: list[str] = []
    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if (
            trimmed.startswith('(use "git')
            or trimmed.startswith("(create/copy files")
            or '(use "git add' in trimmed
            or '(use "git restore' in trimmed
        ):
            continue
        if "nothing to commit" in trimmed and "working tree clean" in trimmed:
            result.append(trimmed)
            break
        result.append(line)
    return "\n".join(result) if result else "ok"


_PORCELAIN_STATUS_RE = re.compile(r"^[ MADRCU?!]{2} ")


def filter_git_status(output: str, command: str) -> str:
    """Entry point — routes to porcelain or human-readable filter."""
    lines = output.splitlines()
    # Detect porcelain form: starts with "## branch..." or a 2-char status code
    is_porcelain = bool(lines) and (
        lines[0].startswith("##") or _PORCELAIN_STATUS_RE.match(lines[0]) is not None
    )
    if is_porcelain:
        return format_status_output(output)
    return filter_status_with_args(output)


# ---------------------------------------------------------------------------
# git log

def parse_user_limit(args: list[str]) -> int | None:
    i = 0
    while i < len(args):
        arg = args[i]
        # -20 combined digit form
        if len(arg) > 1 and arg[0] == "-" and arg[1].isdigit():
            try:
                return int(arg[1:])
            except ValueError:
                pass
        # -n 20
        if arg == "-n" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
            i += 1
        # --max-count=20
        if arg.startswith("--max-count="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
        # --max-count 20
        if arg == "--max-count" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
            i += 1
        i += 1
    return None


_USER_FORMAT_FLAGS = ("--oneline", "--pretty", "--format", "--graph")


def _detect_user_format(args: list[str]) -> bool:
    for a in args:
        for flag in _USER_FORMAT_FLAGS:
            if a == flag or a.startswith(flag + "="):
                return True
    return False


def filter_log_output(
    output: str, limit: int, user_set_limit: bool, user_format: bool
) -> str:
    truncate_width = 120 if user_set_limit else 80

    if user_format or "---END---" not in output:
        # Simple line truncation. We treat marker-less input as user_format
        # because our capture path never injects the rtk marker.
        lines = output.splitlines()
        max_lines = len(lines) if user_set_limit else limit
        return "\n".join(_truncate_line(l, truncate_width) for l in lines[:max_lines])

    commits = output.split("---END---")
    max_commits = len(commits) if user_set_limit else limit

    result: list[str] = []
    for block in commits[:max_commits]:
        block = block.strip()
        if not block:
            continue
        block_lines = block.splitlines()
        if not block_lines:
            continue
        header = _truncate_line(block_lines[0].strip(), truncate_width)
        all_body = [
            l.strip()
            for l in block_lines[1:]
            if l.strip()
            and not l.strip().startswith("Signed-off-by:")
            and not l.strip().startswith("Co-authored-by:")
        ]
        body_omitted = max(0, len(all_body) - 3)
        body_lines = all_body[:3]

        if not body_lines:
            result.append(header)
        else:
            entry = header
            for body in body_lines:
                entry += f"\n  {_truncate_line(body, truncate_width)}"
            if body_omitted > 0:
                entry += f"\n  [+{body_omitted} lines omitted]"
            result.append(entry)

    return "\n".join(result).strip()


# ---------------------------------------------------------------------------
# git diff

def condense_unified_diff(diff: str) -> str:
    """Summarise a unified diff by file, preserving all +/- lines.

    Port of rtk's `condense_unified_diff` — strips diff metadata (diff --git,
    --- / +++ headers, @@ hunks) and emits `[file] path (+A -R)` followed
    by the actual +/- lines. Preserves the rtk quirk where the `+N more`
    label can still appear even though content is not truncated (we match
    rtk behaviour so tests stay meaningful).
    """
    result: list[str] = []
    current_file = ""
    added = 0
    removed = 0
    changes: list[str] = []

    def _flush() -> None:
        if current_file and (added > 0 or removed > 0):
            result.append(f"[file] {current_file} (+{added} -{removed})")
            for c in changes:
                result.append(f"  {c}")
            total = added + removed
            if total > 10:
                result.append(f"  ... +{total - 10} more")

    for line in diff.splitlines():
        if (
            line.startswith("diff --git")
            or line.startswith("--- ")
            or line.startswith("+++ ")
        ):
            if line.startswith("+++ "):
                _flush()
                path = line.removeprefix("+++ ")
                if path.startswith("b/"):
                    path = path[2:]
                current_file = path
                added = 0
                removed = 0
                changes = []
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
            changes.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            changes.append(line)

    _flush()
    return "\n".join(result)


def filter_git_diff(output: str, command: str) -> str:
    return condense_unified_diff(output)


def filter_git_log(output: str, command: str) -> str:
    tokens = command.split()
    # drop the leading `git` and `log` tokens for arg parsing
    args: list[str] = []
    seen_log = False
    for t in tokens:
        if not seen_log:
            if t == "log":
                seen_log = True
            continue
        args.append(t)

    user_limit = parse_user_limit(args)
    user_format = _detect_user_format(args)
    limit = user_limit if user_limit is not None else _LOG_DEFAULT_LIMIT
    return filter_log_output(
        output,
        limit=limit,
        user_set_limit=user_limit is not None,
        user_format=user_format,
    )
