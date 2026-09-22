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
import textwrap
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


class RedactionAnchoringTest(unittest.TestCase):
    """The generic KEY=VALUE rule is anchored to the start of a key run now.

    That is a cost fix (see RedactionCostTest) and must not be a behaviour
    fix: a key buried inside a longer word run, or sitting right after
    punctuation, still has to be caught.
    """

    def _redacted(self, src):
        got, n = redact_secrets(src)
        return got, n

    def test_a_key_inside_a_longer_word_run_is_still_caught(self):
        for src, want in [
            ("XXXXsecret=abcdef0123456789xyz", "XXXXsecret=REDACTED"),
            ("a.b.c.my_api_key=abcdef0123456789xyz", "a.b.c.my_api_key=REDACTED"),
            ("SOME-LONG-PREFIX-TOKEN=abcdef0123456789xyz",
             "SOME-LONG-PREFIX-TOKEN=REDACTED"),
        ]:
            with self.subTest(src=src):
                self.assertEqual(self._redacted(src)[0], want)

    def test_a_key_after_punctuation_is_still_caught(self):
        for prefix in ("", " ", "\n", "{", '"', "(", ",", ";", "|", "/", "=",
                       "&", "?", "\t"):
            src = f"{prefix}API_KEY=abcdef0123456789xyz"
            with self.subTest(prefix=repr(prefix)):
                self.assertEqual(self._redacted(src)[0],
                                 f"{prefix}API_KEY=REDACTED")

    def test_every_occurrence_on_a_line_is_replaced(self):
        got, n = redact_secrets(
            "A_TOKEN=abcdef0123456789xyz B_SECRET=zyxwvu9876543210abc")
        self.assertEqual(got, "A_TOKEN=REDACTED B_SECRET=REDACTED")
        self.assertEqual(n, 2)


class RedactionCostTest(unittest.TestCase):
    """The generic KEY=VALUE rule used to be quadratic in the length of one
    contiguous [A-Za-z0-9_.-] run. Measured before the fix: 4 KB 1.2s,
    8 KB 4.7s, 16 KB 19.1s, i.e. ~4x per doubling, crossing the recorder's
    600s timeout somewhere near 90 KB. A timeout there is not a slow Raw, it
    is no Raw — the SessionEnd hook writes the "(filter failed)" stub.

    The shapes below are the ones that actually reach that run length: a bare
    alphanumeric blob, and base64URL, whose "-" and "_" (unlike classic
    base64's "+/=") stay inside the key character class and so never break the
    run. JWT payloads, URL-safe tokens, hex digests and minified identifier
    soup all land there. Classic base64 does not, which is why the vault's
    longest run (47,344 chars, Raw/2026/07/12) was never on the slow path and
    why this had stayed latent.

    Each case runs in a child process so a regression fails in seconds instead
    of hanging the suite for the several minutes the old rule would take.
    """

    BUDGET_S = 1.0
    CHILD_TIMEOUT_S = 60

    CHILD = textwrap.dedent("""
        import importlib.util, sys, time
        scripts_dir, shape, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
        sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location(
            "ft", scripts_dir + "/filter-transcript.py")
        ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ft)
        if shape == "word":
            text = "A1b2" * (size // 4)
        elif shape == "base64url":
            text = "aB3-_x" * (size // 6)
        elif shape == "repeated-key":
            text = "key=" * (size // 8) + "A" * (size // 2)
        else:
            raise SystemExit("unknown shape " + shape)
        t0 = time.perf_counter()
        ft.redact_secrets(text)
        print(time.perf_counter() - t0)
    """)

    def _elapsed(self, shape, size):
        r = subprocess.run(
            [sys.executable, "-c", self.CHILD, str(_SCRIPTS_DIR), shape,
             str(size)],
            capture_output=True, text=True, timeout=self.CHILD_TIMEOUT_S)
        self.assertEqual(r.returncode, 0, r.stderr)
        return float(r.stdout.strip())

    def test_a_64k_word_run_redacts_in_well_under_a_second(self):
        # the shape that actually exists in the vault: one long alnum run
        elapsed = self._elapsed("word", 64 * 1024)
        self.assertLess(elapsed, self.BUDGET_S,
                        f"64 KB word run took {elapsed:.3f}s "
                        f"(budget {self.BUDGET_S}s) — the KEY=VALUE rule has "
                        f"gone quadratic again")

    def test_a_64k_base64url_run_redacts_in_well_under_a_second(self):
        # "-" and "_" keep base64url inside the key class, so a JWT payload or
        # a URL-safe token is one unbroken run where classic base64 is not
        elapsed = self._elapsed("base64url", 64 * 1024)
        self.assertLess(elapsed, self.BUDGET_S,
                        f"64 KB base64url run took {elapsed:.3f}s")

    def test_many_key_separators_before_a_long_run_stay_linear(self):
        # the second quadratic: each "key=" is a candidate whose "does the
        # value mix letters and digits" lookahead used to scan to the end
        elapsed = self._elapsed("repeated-key", 64 * 1024)
        self.assertLess(elapsed, self.BUDGET_S,
                        f"repeated-key 64 KB took {elapsed:.3f}s")

    def test_cost_grows_linearly_not_quadratically(self):
        """Quadruple the input; a quadratic rule would take ~16x longer."""
        small = self._elapsed("word", 16 * 1024)
        large = self._elapsed("word", 64 * 1024)
        floor = 0.005  # keep the ratio meaningful when both are sub-ms
        self.assertLess(large / max(small, floor), 8.0,
                        f"16 KB {small:.4f}s -> 64 KB {large:.4f}s looks "
                        f"super-linear")


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
