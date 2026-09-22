"""redact_secrets: credentials never land in Raw/ in the first place.

The 2026-09-07 vault migration found a GitLab PAT, OpenAI keys, an OAuth app
secret and a pile of *_TOKEN= environment values sitting in Raw/ transcripts,
plus strings that are not secrets but that git hosting secret-check hooks
still reject (masked CI URLs, AKIA-shaped runs inside base64). Redacting at
capture time removes both problems for every hosting, without turning the
hook's scanning off.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"
_SCRIPT = _SCRIPTS_DIR / "filter-transcript.py"
sys.path.insert(0, str(_SCRIPTS_DIR))
_spec = importlib.util.spec_from_file_location("filter_transcript", _SCRIPT)
filter_transcript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_transcript)
redact_secrets = filter_transcript.redact_secrets


class RedactSecretsTest(unittest.TestCase):
    # (input, expected output) pairs; expected values are hand-written literals.
    CASES = [
        # GitLab personal access token
        ("token=glpat-AbCdEfGhIjKlMnOpQrSt more",
         "token=glpat-REDACTED more"),
        # GitLab OAuth application secret (gloas- + 64 chars)
        ("secret gloas-" + "a1" * 32 + " end",
         "secret gloas-REDACTED end"),
        # AWS access key id, exactly the hook's pattern
        ("AWS_KEY AKIAIOSFODNN7EXAMPLE",
         "AWS_KEY AKIA-REDACTED"),
        # the host's check is case-insensitive: an AKIA-shaped run inside base64
        ("CwCgAAAAAAALAKIAbCdEfGhIjKlMnOpQB4AgAAAAAAAI",
         "CwCgAAAAAAALAKIA-REDACTEDB4AgAAAAAAAI"),
        # OpenAI project key
        ("OPENAI_API_KEY=sk-proj-7MatQJ7wDaV4tYBVabcdefghijklmnop1234",
         "OPENAI_API_KEY=sk-REDACTED"),
        # Anthropic key
        ("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
         "key sk-ant-REDACTED"),
        # GitLab session cookie
        ("Cookie: _gitlab_session=0123456789abcdef0123456789abcdef; path=/",
         "Cookie: _gitlab_session=REDACTED; path=/"),
        # JWT
        ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
         "Bearer eyJ.REDACTED.JWT"),
        # curl basic auth
        ("curl -u admin:S3cretPass https://nas/webapi",
         "curl -u admin:REDACTED https://nas/webapi"),
        # Authorization header value
        ("Authorization: Bearer abcdef0123456789",
         "Authorization: Bearer REDACTED"),
        # GitLab PRIVATE-TOKEN header
        ('-H "PRIVATE-TOKEN: glpat-AbCdEfGhIjKlMnOpQrSt"',
         '-H "PRIVATE-TOKEN: glpat-REDACTED"'),
        # password in URL, the host's own false-positive magnet
        ("git clone https://gitlab-ci-token:[secure]@git.example.com/x/y.git",
         "git clone https://gitlab-ci-token:${REDACTED}@git.example.com/x/y.git"),
        # generic KEY=VALUE environment dump
        ("TRACKER_ACCESS_TOKEN=277cd358-c1a2-4b3c-9d8e-0f1a2b3c4d5e",
         "TRACKER_ACCESS_TOKEN=REDACTED"),
        ('"CONTEXT7_API_KEY": "ctx7sk-0123456789abcdef"',
         '"CONTEXT7_API_KEY": "REDACTED"'),
        ("//registry.npmjs.org/:_authToken=YzVlNGE2ZjItMTIzNC00NTY3",
         "//registry.npmjs.org/:_authToken=REDACTED"),
    ]

    def test_each_credential_class_is_replaced(self):
        for src, want in self.CASES:
            with self.subTest(src=src):
                got, _ = redact_secrets(src)
                self.assertEqual(got, want)

    def test_count_reports_number_of_replacements(self):
        text = ("a glpat-AbCdEfGhIjKlMnOpQrSt b glpat-ZyXwVuTsRqPoNmLkJiHg "
                "c TRACKER_ACCESS_TOKEN=277cd358-c1a2-4b3c-9d8e-0f1a2b3c4d5e")
        _, n = redact_secrets(text)
        self.assertEqual(n, 3)

    def test_ordinary_transcript_text_is_untouched(self):
        # Things that look vaguely secret-shaped but are not, plus a redacted
        # URL that already uses the host's "$" escape hatch.
        lines = [
            "Ref: PROJ-4521",
            "created: 2026-04-30",
            "https://git.example.com/org/project.git",
            'keyboard = "ctrl+shift+alt+x"',
            "MAX_TOKENS=4096",
            "postgres://akashic:${DB_PASSWORD}@postgres:5432/akashic",
            "commit 449ce929bf17ba2d7e4844db9290df2c700f5e39",
            "sk-learn is a python package",
            "Authorization header must be set",
        ]
        text = "\n".join(lines)
        got, n = redact_secrets(text)
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_redacted_output_no_longer_matches_host_password_in_url_rule(self):
        # The regex a git host's pre-receive hook applies (Password in URL).
        import re
        host_rule = re.compile(
            r"[a-zA-Z]{3,10}://[^$][^:@/\n]{3,20}:[^$][^:@\n/]{3,40}@.{1,100}")
        got, _ = redact_secrets(
            "https://gitlab-ci-token:[secure]@git.example.com/x/y.git")
        self.assertIsNone(host_rule.search(got))


class FilterTranscriptEndToEndTest(unittest.TestCase):
    """Run the real script on a transcript that carries a token."""

    def test_token_in_assistant_text_does_not_reach_stdout(self):
        import tempfile
        token = "glpat-AbCdEfGhIjKlMnOpQrSt"
        with tempfile.TemporaryDirectory() as td:
            tx = Path(td) / "transcript.jsonl"
            line = json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text",
                                         "text": f"the MCP config holds {token} for gitlab"}]},
            })
            tx.write_text(line + "\n")
            r = subprocess.run([sys.executable, str(_SCRIPT), str(tx)],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(token, r.stdout)
        self.assertIn("glpat-REDACTED", r.stdout)
        self.assertIn("redactions=1", r.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
