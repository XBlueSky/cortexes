"""Filter for syno-naxos MCP outputs.

`exec_command` returns a JSON envelope wrapping a remote shell command's
output. We unwrap it to a compact `$ <command>` frame and recurse the remote
stdout through the existing rtk_cmd Bash filters — so every git/ls/grep/cargo/...
filter cortex already has applies to remote NAS execution too.

Other naxos sub-tools (file_read, gdb_*, dev_patch_*) return content the user
explicitly asked for and are left verbatim (triage rule, see mcp_tools.py).
"""
from __future__ import annotations

import json


def _apply_rtk(command: str, stdout: str) -> str:
    # Lazy import: dispatch imports this module to register filter_naxos, so a
    # top-level import would be circular. By call time dispatch is fully loaded.
    from rtk_cmd.dispatch import find_cmd_filter

    fn = find_cmd_filter(command)
    return fn(stdout, command) if fn else stdout


def _filter_exec_command(output: str) -> str:
    try:
        env = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(env, dict) or "command" not in env or "stdout" not in env:
        return output

    command = str(env.get("command", "")).strip()
    target = str(env.get("target", "")).strip()
    stdout = env.get("stdout") or ""
    stderr = env.get("stderr") or ""
    exit_code = env.get("exit_code", 0)
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        return output

    header = f"$ {command}" + (f"            [{target}]" if target else "")
    body = _apply_rtk(command, stdout)
    parts = [header, body.rstrip("\n")] if body.strip() else [header]
    if exit_code not in (0, None):
        parts.append(f"exit {exit_code}")
    if stderr.strip():
        parts.append(f"[stderr] {stderr.rstrip()}")

    result = "\n".join(parts)
    return result if len(result) < len(output) else output


def filter_naxos(output: str, tool_name: str) -> str:
    if tool_name.endswith("__exec_command"):
        return _filter_exec_command(output)
    return output  # file_read / gdb / dev_patch: content, verbatim
