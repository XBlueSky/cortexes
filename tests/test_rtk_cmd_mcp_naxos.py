"""syno-naxos MCP filter tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from rtk_cmd.mcp_naxos import filter_naxos  # noqa: E402

EXEC = "mcp__plugin_synology-dev-suite_syno-naxos__exec_command"


def _env(command, stdout="", stderr="", exit_code=0, target="benchnas"):
    return json.dumps({
        "success": exit_code == 0,
        "target": target,
        "command": command,
        "command_safety": "safe",
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "execution_time_ms": 12,
    })


class NaxosExecCommand(unittest.TestCase):
    def test_unwraps_envelope(self):
        raw = _env("nproc", stdout="4\n")
        result = filter_naxos(raw, EXEC)
        self.assertIn("$ nproc", result)
        self.assertIn("4", result)
        self.assertNotIn("execution_time_ms", result)
        self.assertNotIn("command_safety", result)
        self.assertLess(len(result), len(raw))

    def test_shows_target(self):
        raw = _env("uname -a", stdout="Linux benchnas\n", target="benchnas")
        self.assertIn("[benchnas]", filter_naxos(raw, EXEC))

    def test_nonzero_exit_and_stderr(self):
        raw = _env("pgrep -a nginx", stderr="ash: pgrep: command not found\n", exit_code=127)
        result = filter_naxos(raw, EXEC)
        self.assertIn("$ pgrep -a nginx", result)
        self.assertIn("exit 127", result)
        self.assertIn("[stderr] ash: pgrep: command not found", result)

    def test_zero_exit_has_no_exit_line(self):
        result = filter_naxos(_env("true", stdout="ok\n"), EXEC)
        self.assertNotIn("exit ", result)

    def test_recurses_into_rtk_filter(self):
        # 100-line `ls` stdout must be reduced by filter_ls (head=70/tail=10 cap),
        # proving exec_command stdout is routed through find_cmd_filter.
        entries = "\n".join(f"file_{i:03d}.txt" for i in range(100)) + "\n"
        result = filter_naxos(_env("ls -la /var/log", stdout=entries), EXEC)
        self.assertIn("$ ls -la /var/log", result)
        self.assertIn("file_000.txt", result)   # head kept
        self.assertIn("file_099.txt", result)   # tail kept
        self.assertNotIn("file_080.txt", result)  # middle dropped by cap

    def test_file_read_left_verbatim(self):
        raw = json.dumps({"success": True, "content": "a\nb\n", "path": "/etc/hosts"})
        name = "mcp__plugin_synology-dev-suite_syno-naxos__file_read"
        self.assertEqual(filter_naxos(raw, name), raw)

    def test_parse_failure_passthrough(self):
        self.assertEqual(filter_naxos("not json", EXEC), "not json")

    def test_missing_keys_passthrough(self):
        raw = json.dumps({"success": True, "note": "no command/stdout"})
        self.assertEqual(filter_naxos(raw, EXEC), raw)


if __name__ == "__main__":
    unittest.main()
