"""The recording pipeline must degrade, never disappear.

A code-search MCP server changed its result payload: `line` stopped being the
matched text and became the line NUMBER. The filter for it did
`(m.get("line") or "").rstrip()` and started raising AttributeError on an int.
Nothing caught it, `render_transcript()` aborted, `main()` never reached its
single `sys.stdout.write`, and the SessionEnd hook turned zero bytes of stdout
into a ~100-byte Raw whose whole body was the string "(filter failed)". 21
session records were destroyed over two weeks that way.

A filter can always be fixed for the payload it broke on. These tests pin the
structural property that makes the NEXT shape drift cost a tool block instead
of a conversation:

  * a filter that raises degrades only the tool result it was handed
  * a record that cannot be rendered degrades to a visible breadcrumb
  * both are counted in the audit comment (filter_errors= / record_errors=)

The first round of that repair guarded the middle of the pipeline and left
both ends open, so the tests below also pin the ends:

  * an undecodable byte in the transcript (the hook renders a file Claude Code
    is still appending to) costs a character, not the read
  * a line json.loads cannot handle — including the RecursionError and
    MemoryError that are not JSONDecodeError — costs that line
  * the whole-body transforms in main() are optional like every other step
  * a lone surrogate, which only fails at the terminal stdout encode and so
    destroys a record that had already rendered perfectly, costs one character
  * and the terminal write has a lossy last resort, because zero bytes of
    stdout is precisely what the SessionEnd hook turns into "(filter failed)"

They also cover `--until`, the bound the backfill uses to reconstruct a Raw as
it stood when it was first written rather than as the session ended.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"
_SCRIPT = _SCRIPTS_DIR / "filter-transcript.py"
# the script imports its sibling modules (log_dedup, rtk_cmd, ...) by bare name
sys.path.insert(0, str(_SCRIPTS_DIR))
_spec = importlib.util.spec_from_file_location("filter_transcript", _SCRIPT)
filter_transcript = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_transcript)  # noqa: E402

POISON = "PAYLOAD-THE-FILTER-NO-LONGER-UNDERSTANDS"
CODESEARCH = "mcp__zoekt__search"

T_EARLY = "2026-09-16T03:00:00.000Z"
T_BOUND = "2026-09-16T04:00:00.000Z"
T_LATE = "2026-09-16T05:00:00.000Z"


def _boom(*_args, **_kwargs):
    """The exact failure that destroyed the 21 Raw files."""
    raise AttributeError("'int' object has no attribute 'rstrip'")


def _user(text, ts=None):
    rec = {"type": "user", "message": {"content": text}}
    if ts:
        rec["timestamp"] = ts
    return rec


def _assistant(text, ts=None):
    rec = {"type": "assistant",
           "message": {"content": [{"type": "text", "text": text}]}}
    if ts:
        rec["timestamp"] = ts
    return rec


def _tool_use(tid, name, inp, ts=None):
    rec = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}
    if ts:
        rec["timestamp"] = ts
    return rec


def _tool_result(tid, output, ts=None):
    rec = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": output}]}}
    if ts:
        rec["timestamp"] = ts
    return rec


class _TranscriptCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, records, name="transcript.jsonl"):
        path = Path(self._tmp.name) / name
        path.write_text("".join(json.dumps(r) + "\n" for r in records))
        return path

    def write_raw(self, blob: bytes, name="transcript.jsonl"):
        """Write transcript BYTES, for the cases a str cannot express."""
        path = Path(self._tmp.name) / name
        path.write_bytes(blob)
        return path

    def run_main(self, argv):
        """Drive main() in-process so a monkeypatched filter stays patched."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["filter-transcript.py", *argv]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = filter_transcript.main()
        return rc, out.getvalue(), err.getvalue()

    def cli(self, *args):
        """Drive the real entry point, the way the SessionEnd hook does."""
        env = {**os.environ, "CORTEX_NO_CLASSIFIER": "1"}
        return subprocess.run([sys.executable, str(_SCRIPT), *args],
                              capture_output=True, text=True, env=env)


class FilterFailOpenTest(_TranscriptCase):
    def _poisoned_transcript(self):
        return self.write([
            _user("first question"),
            _assistant("an answer before the tool call"),
            _tool_use("t1", CODESEARCH, {"query": "retry_backoff"}),
            _tool_result("t1", POISON),
            _assistant("an answer after the tool call"),
            _user("second question"),
        ])

    def test_raising_mcp_filter_costs_only_that_tool_result(self):
        path = self._poisoned_transcript()
        with mock.patch.object(filter_transcript, "find_mcp_filter",
                               lambda _name: _boom):
            body, state = filter_transcript.render_transcript(path, [])
        # every other turn survived
        self.assertIn("first question", body)
        self.assertIn("an answer before the tool call", body)
        self.assertIn("an answer after the tool call", body)
        self.assertIn("second question", body)
        # and the poisoned result is verbatim, not dropped and not a stub
        self.assertIn(POISON, body)
        self.assertEqual(state["filter_errors"], 1)
        self.assertEqual(state["mcp_hits"], 0)

    def test_healthy_filter_reports_no_degradation(self):
        """Control: the same transcript through the real registry is clean."""
        path = self._poisoned_transcript()
        body, state = filter_transcript.render_transcript(path, [])
        self.assertEqual(state["filter_errors"], 0)
        self.assertIn(POISON, body)

    def test_audit_line_reports_the_degradation_count(self):
        path = self._poisoned_transcript()
        with mock.patch.object(filter_transcript, "find_mcp_filter",
                               lambda _name: _boom):
            rc, out, _err = self.run_main([str(path)])
        self.assertEqual(rc, 0)
        self.assertIn("filter_errors=1", out)
        self.assertIn("record_errors=0", out)
        self.assertIn(POISON, out)

    def test_raising_bash_command_filter_falls_back_to_raw(self):
        path = self.write([
            _user("run the tests"),
            _tool_use("t1", "Bash", {"command": "pytest tests/ -q"}),
            _tool_result("t1", "3 passed in 0.10s"),
            _assistant("green"),
        ])
        with mock.patch.object(filter_transcript, "find_cmd_filter",
                               lambda _cmd: _boom):
            body, state = filter_transcript.render_transcript(path, [])
        self.assertIn("3 passed in 0.10s", body)
        self.assertIn("green", body)
        self.assertEqual(state["filter_errors"], 1)
        self.assertEqual(state["rtk_cmd_hits"], 0)

    def test_filter_returning_a_non_string_is_treated_as_a_failure(self):
        """It would crash fmt_tool_output() instead, one frame too late."""
        path = self.write([
            _tool_use("t1", CODESEARCH, {"query": "x"}),
            _tool_result("t1", POISON),
            _assistant("still here"),
        ])
        with mock.patch.object(filter_transcript, "find_mcp_filter",
                               lambda _name: lambda *_a: None):
            body, state = filter_transcript.render_transcript(path, [])
        self.assertIn(POISON, body)
        self.assertIn("still here", body)
        self.assertEqual(state["filter_errors"], 1)
        self.assertEqual(state["record_errors"], 0)

    def test_process_tool_result_never_raises(self):
        """The outer guard, independent of which inner step blew up."""
        state = {}
        with mock.patch.object(filter_transcript, "find_mcp_filter", _boom):
            got = filter_transcript.process_tool_result(
                {"name": CODESEARCH}, POISON, [], state)
        self.assertEqual(got, POISON)
        self.assertEqual(state["filter_errors"], 1)


class RecordFailOpenTest(_TranscriptCase):
    def test_unrenderable_record_costs_one_turn_and_leaves_a_breadcrumb(self):
        path = self.write([
            _user("before the bad record"),
            # a content LIST holding a bare string: block.get() -> AttributeError
            {"type": "assistant", "message": {"content": ["not a block"]}},
            _assistant("after the bad record"),
        ])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertIn("before the bad record", body)
        self.assertIn("after the bad record", body)
        self.assertEqual(state["record_errors"], 1)
        self.assertIn("[record skipped: AttributeError]", body)

    def test_null_message_is_tolerated_without_an_error(self):
        path = self.write([
            _user("keep me"),
            {"type": "assistant", "message": None},
            {"type": "user", "message": None},
            _assistant("keep me too"),
        ])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertIn("keep me", body)
        self.assertIn("keep me too", body)
        self.assertEqual(state["record_errors"], 0)

    def test_non_object_record_is_skipped(self):
        path = Path(self._tmp.name) / "odd.jsonl"
        path.write_text(json.dumps(_user("kept")) + "\n[1, 2, 3]\nnot json\n"
                        + json.dumps(_assistant("also kept")) + "\n")
        body, state = filter_transcript.render_transcript(path, [])
        self.assertIn("kept", body)
        self.assertIn("also kept", body)
        self.assertEqual(state["record_errors"], 0)


class RecordSkipBreadcrumbTest(_TranscriptCase):
    """The breadcrumb is a tombstone, not a tool header.

    The chunk assembler attaches a tool_result to chunks[-1] when it starts
    with TOOL_HDR. While the breadcrumb wore that prefix, the next tool result
    to arrive was glued onto it and filed under "[record skipped]" — output
    credited to a turn that was never rendered.
    """

    OUTPUT = "OUTPUT-BELONGING-TO-A-REAL-TOOL-CALL"

    @staticmethod
    def _unrenderable():
        # a content LIST holding a bare string: block.get() -> AttributeError
        return {"type": "assistant", "message": {"content": ["not a block"]}}

    def test_breadcrumb_does_not_wear_the_tool_header(self):
        path = self.write([_user("before"), self._unrenderable()])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertEqual(state["record_errors"], 1)
        self.assertIn(f"{filter_transcript.RECORD_SKIP_HDR} **[record skipped:",
                      body)
        self.assertNotIn(f"{filter_transcript.TOOL_HDR} **[record skipped:",
                         body)

    def test_breadcrumb_does_not_adopt_the_next_tool_result(self):
        path = self.write([
            _user("before the bad record"),
            self._unrenderable(),
            _tool_result("t-orphan", self.OUTPUT),
            _assistant("after"),
        ])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertEqual(state["record_errors"], 1)
        # the misattribution, spelled out: output fenced onto the breadcrumb
        self.assertNotIn("[record skipped: AttributeError]**\n```output", body)
        # ...and the output is still in the record, under a header of its own
        self.assertIn(self.OUTPUT, body)
        self.assertEqual(state["orphan_outputs"], 1)

    def test_output_with_no_header_is_kept_rather_than_dropped(self):
        """A tool_result whose tool_use never arrived (skipped record, --until
        bound, text emitted after the call) used to vanish silently."""
        path = self.write([
            _user("hello"),
            _tool_result("t-unknown", self.OUTPUT),
            _assistant("bye"),
        ])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertIn(self.OUTPUT, body)
        self.assertIn(filter_transcript.ORPHAN_TOOL_HDR, body)
        self.assertEqual(state["orphan_outputs"], 1)

    def test_a_normal_tool_call_still_attaches_and_counts_no_orphan(self):
        """Control: the ordinary pairing must not have become an orphan."""
        path = self.write([
            _tool_use("t1", "Bash", {"command": "echo hi"}),
            _tool_result("t1", self.OUTPUT),
        ])
        body, state = filter_transcript.render_transcript(path, [])
        self.assertEqual(state["orphan_outputs"], 0)
        self.assertIn(f"{filter_transcript.TOOL_HDR} **Bash**: `echo hi`\n"
                      f"```output\n{self.OUTPUT}\n```", body)


class TranscriptReadFailOpenTest(_TranscriptCase):
    """The read is the first unguarded step, and the most exposed one.

    The SessionEnd hook is detached with nohup and renders a transcript Claude
    Code may still be appending to, so a read landing inside a multibyte
    character is an ordinary race. Under a strict decode that race raised past
    every per-record guard and, because main() writes once at the end, took
    every record already accumulated with it.
    """

    def test_an_undecodable_byte_costs_a_character_not_the_session(self):
        blob = (json.dumps(_user("kept before")).encode() + b"\n"
                # a truncated multibyte sequence, mid-file
                + b'{"type":"user","message":{"content":"tor\xe4\xb8n"}}\n'
                + json.dumps(_assistant("kept after")).encode() + b"\n")
        r = self.cli(str(self.write_raw(blob)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kept before", r.stdout)
        self.assertIn("kept after", r.stdout)

    def test_a_cjk_transcript_survives_an_ascii_locale(self):
        """Both ends at once, in the environment that exposes both.

        A cron/nohup context can hand this hook a POSIX locale with C-locale
        coercion disabled, where the interpreter's default encoding is ASCII.
        The read then needs its pinned encoding= (otherwise every Chinese turn
        aborts it) AND the write needs its fallback (otherwise stdout, an
        ASCII stream, refuses the very same characters at the very end).
        """
        path = self.write([_user("提煉這個 session"), _assistant("好")])
        env = {**os.environ, "CORTEX_NO_CLASSIFIER": "1",
               "LC_ALL": "C", "LANG": "C",
               "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}
        r = subprocess.run([sys.executable, str(_SCRIPT), str(path)],
                           capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        self.assertIn("提煉這個 session", r.stdout.decode("utf-8"))
        self.assertIn("好", r.stdout.decode("utf-8"))

    class _TearingPath:
        """A Path stand-in whose read raises partway through.

        render_transcript() only ever calls path.open(), so handing it this
        exercises the read-abort path without needing a real I/O error.
        """

        def __init__(self, lines, exc):
            self._lines, self._exc = lines, exc

        def open(self, *_args, **_kwargs):
            lines, exc = self._lines, self._exc

            class _File:
                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False

                def __iter__(self):
                    yield from lines
                    raise exc

            return _File()

    def test_a_read_that_tears_keeps_the_prefix_it_already_had(self):
        """The last accumulate-then-lose window: main() writes once, so an I/O
        error on line 40 used to cost lines 1-39 as well."""
        lines = [json.dumps(_user("turn one")) + "\n",
                 json.dumps(_assistant("turn two")) + "\n"]
        torn = self._TearingPath(lines, OSError("input/output error"))
        body, state = filter_transcript.render_transcript(torn, [])
        self.assertIn("turn one", body)
        self.assertIn("turn two", body)
        self.assertEqual(state["read_errors"], 1)
        self.assertIn("[transcript read aborted: OSError]", body)

    def test_a_read_that_yields_nothing_still_fails_loudly(self):
        """No prefix means no record, and the empty stdout that makes the hook
        write "(filter failed)" is the marker the backfill searches for.
        Degrading to a two-line Raw would hide the failure instead."""
        torn = self._TearingPath([], OSError("input/output error"))
        with self.assertRaises(OSError):
            filter_transcript.render_transcript(torn, [])

    def test_an_unparseable_line_costs_only_that_line(self):
        """json.loads raises RecursionError on deep nesting and MemoryError on
        a huge document; neither is a JSONDecodeError."""
        blob = (json.dumps(_user("before the deep line")).encode() + b"\n"
                + b"[" * 200000 + b"]" * 200000 + b"\n"
                + json.dumps(_assistant("after the deep line")).encode() + b"\n")
        r = self.cli(str(self.write_raw(blob)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("before the deep line", r.stdout)
        self.assertIn("after the deep line", r.stdout)
        self.assertIn("line_errors=1", r.stdout.splitlines()[0])


class SurrogateTest(_TranscriptCase):
    """Claude Code truncates tool output on a JS string, which can split a
    surrogate PAIR; JSON.stringify emits the survivor as a "\\udXXX" escape and
    json.loads materialises it happily. Nothing notices until the terminal
    stdout encode, which raises AFTER a flawless render — so the whole session
    became the "(filter failed)" stub over half an emoji.
    """

    # U+FFFD, spelled out rather than pasted: a literal replacement character
    # in a source file is indistinguishable from mojibake in the file itself.
    REPL = chr(0xFFFD)

    def test_scrub_yields_well_formed_utf8(self):
        text, n = filter_transcript.scrub_surrogates("a\ud83db\udfffc")
        self.assertEqual(n, 2)
        self.assertEqual(text, f"a{self.REPL}b{self.REPL}c")
        text.encode("utf-8")  # must not raise

    def test_ordinary_text_including_real_emoji_is_untouched(self):
        src = "ok 🚀 中文 done"
        text, n = filter_transcript.scrub_surrogates(src)
        self.assertEqual((text, n), (src, 0))

    def test_lone_surrogate_costs_one_character_not_the_session(self):
        path = self.write([
            _user("first question"),
            _tool_use("t1", "Bash", {"command": "echo hi"}),
            _tool_result("t1", "half emoji: \ud83d and more output"),
            _user("second question"),
        ])
        r = self.cli(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("first question", r.stdout)
        self.assertIn("second question", r.stdout)
        self.assertIn(f"half emoji: {self.REPL} and more output", r.stdout)
        self.assertIn("surrogates=1", r.stdout.splitlines()[0])


class WriteOutputTest(unittest.TestCase):
    """Zero bytes of stdout IS the "(filter failed)" stub, whatever caused it.

    The scrub above should mean the plain write always works; this is the belt
    to its braces, because the cost of being wrong is a whole session.
    """

    class _Unencodable:
        """A stdout whose text write raises the way the real one does."""

        def __init__(self):
            self.buffer = io.BytesIO()

        def write(self, _text):
            raise UnicodeEncodeError(
                "utf-8", "\ud83d", 0, 1, "surrogates not allowed")

        def flush(self):
            pass

    def test_an_encoding_failure_degrades_to_a_lossy_write(self):
        fake = self._Unencodable()
        with mock.patch.object(sys, "stdout", fake):
            rc = filter_transcript.write_output("<!-- audit: x -->\nhalf \ud83d\n")
        self.assertEqual(rc, 0)
        written = fake.buffer.getvalue()
        self.assertIn(b"<!-- audit: x -->", written)
        self.assertIn(b"half ", written)
        written.decode("utf-8")  # the fallback must still be decodable

    def test_a_non_encoding_failure_is_not_retried(self):
        """A broken pipe may have written part of the text; a second write
        would duplicate it, so that one stops rather than retries."""
        fake = self._Unencodable()
        fake.write = lambda _text: (_ for _ in ()).throw(BrokenPipeError())
        with mock.patch.object(sys, "stdout", fake):
            rc = filter_transcript.write_output("anything")
        self.assertEqual(rc, 1)
        self.assertEqual(fake.buffer.getvalue(), b"")

    def test_the_ordinary_path_writes_and_returns_zero(self):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            rc = filter_transcript.write_output("hello")
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "hello")


class BodyTransformFailOpenTest(_TranscriptCase):
    """main()'s whole-body transforms were the last unguarded stretch.

    They run after every record has rendered, so a raise there is total loss
    rather than degradation — the most expensive possible place to fail.
    """

    TURNS = ("first turn", "second turn", "third turn")

    def _transcript(self):
        return self.write([_user(t) for t in self.TURNS])

    def test_a_raising_transform_costs_the_transform_not_the_record(self):
        path = self._transcript()
        for name in ("scrub_surrogates", "normalize_line_breaks",
                     "redact_secrets"):
            with self.subTest(transform=name):
                with mock.patch.object(filter_transcript, name, _boom):
                    rc, out, _err = self.run_main([str(path)])
                self.assertEqual(rc, 0)
                for turn in self.TURNS:
                    self.assertIn(turn, out)
                self.assertIn("body_errors=1", out)

    def test_a_healthy_run_reports_no_body_errors(self):
        rc, out, _err = self.run_main([str(self._transcript())])
        self.assertEqual(rc, 0)
        self.assertIn("body_errors=0", out)


class FiltersLoadErrorTest(_TranscriptCase):
    """A malformed filters/*.toml stubs every session in every repo; a drifted
    MCP payload stubs one tool block. Folding both into filter_errors= made
    the audit unable to tell the operator which one happened.
    """

    def test_a_bad_filters_directory_is_counted_on_its_own(self):
        path = self.write([_user("still recorded")])
        with mock.patch.object(filter_transcript, "load_filters", _boom):
            rc, out, _err = self.run_main([str(path)])
        self.assertEqual(rc, 0)
        self.assertIn("still recorded", out)
        self.assertIn("filters_error=1", out)
        self.assertIn("filter_errors=0", out)
        self.assertIn("filters_loaded=0", out)

    def test_a_drifted_payload_leaves_the_filters_flag_clear(self):
        path = self.write([
            _tool_use("t1", CODESEARCH, {"query": "x"}),
            _tool_result("t1", POISON),
        ])
        with mock.patch.object(filter_transcript, "find_mcp_filter",
                               lambda _name: _boom):
            rc, out, _err = self.run_main([str(path)])
        self.assertEqual(rc, 0)
        self.assertIn("filter_errors=1", out)
        self.assertIn("filters_error=0", out)


class UntilBoundTest(_TranscriptCase):
    def _timed_transcript(self):
        return self.write([
            _user("early question", ts=T_EARLY),
            _assistant("answer on the bound", ts=T_BOUND),
            _user("no timestamp at all"),
            _assistant("late answer", ts=T_LATE),
        ])

    def test_records_after_the_bound_are_excluded(self):
        r = self.cli("--until", "2026-09-16T04:00:00Z", str(self._timed_transcript()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("early question", r.stdout)
        self.assertNotIn("late answer", r.stdout)

    def test_the_bound_itself_is_kept(self):
        r = self.cli("--until", "2026-09-16T04:00:00Z", str(self._timed_transcript()))
        self.assertIn("answer on the bound", r.stdout)

    def test_records_without_a_timestamp_are_kept(self):
        r = self.cli("--until", "2026-09-16T04:00:00Z", str(self._timed_transcript()))
        self.assertIn("no timestamp at all", r.stdout)

    def test_unparseable_record_timestamp_is_kept(self):
        path = self.write([_user("kept anyway", ts="not-a-timestamp")])
        body, _state = filter_transcript.render_transcript(
            path, [], filter_transcript.parse_instant("2026-09-16T04:00:00Z"))
        self.assertIn("kept anyway", body)

    def test_offset_and_z_forms_agree(self):
        path = self._timed_transcript()
        z = self.cli("--until", "2026-09-16T04:00:00Z", str(path))
        offset = self.cli("--until", "2026-09-16T12:00:00+08:00", str(path))
        self.assertEqual(z.stdout, offset.stdout)
        self.assertNotIn("late answer", offset.stdout)

    def test_naive_value_is_read_as_utc(self):
        self.assertEqual(filter_transcript.parse_instant("2026-09-16T04:00:00"),
                         filter_transcript.parse_instant("2026-09-16T04:00:00Z"))

    def test_naive_until_warns_loudly_while_keeping_the_utc_reading(self):
        """UTC is right for transcript timestamps and wrong for the number an
        operator copies: Raw frontmatter stores LOCAL time, so a hand-copied
        `time: 16:37:45` silently means 16:37:45Z — eight hours late in +08:00.
        The default stays; the silence does not.
        """
        r = self.cli("--until", "2026-09-16T04:00:00",
                     str(self._timed_transcript()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning", r.stderr)
        self.assertIn("no timezone", r.stderr)
        self.assertIn("LOCAL", r.stderr)
        # the bound itself is unchanged: still read as UTC
        self.assertIn("early question", r.stdout)
        self.assertNotIn("late answer", r.stdout)

    def test_the_equals_form_warns_too(self):
        r = self.cli("--until=2026-09-16T04:00:00",
                     str(self._timed_transcript()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning", r.stderr)

    def test_an_explicit_zone_is_silent(self):
        for value in ("2026-09-16T04:00:00Z", "2026-09-16T12:00:00+08:00"):
            with self.subTest(value=value):
                r = self.cli("--until", value, str(self._timed_transcript()))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")

    def test_naive_record_timestamps_do_not_warn(self):
        """The warning is about the operator's value. Per-record timestamps
        go through the same parser and would bury it."""
        path = self.write([_user("naive record", ts="2026-09-16T03:00:00"),
                           _assistant("another", ts="2026-09-16T03:30:00")])
        r = self.cli("--until", "2026-09-16T04:00:00Z", str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertIn("naive record", r.stdout)

    def test_equals_form_is_accepted(self):
        r = self.cli("--until=2026-09-16T04:00:00Z", str(self._timed_transcript()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("late answer", r.stdout)

    def test_invalid_value_fails_loudly_instead_of_ignoring_the_bound(self):
        r = self.cli("--until", "yesterday", str(self._timed_transcript()))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ISO-8601", r.stderr)
        # the whole point: it must NOT quietly render everything
        self.assertEqual(r.stdout, "")
        self.assertNotIn("late answer", r.stdout)

    def test_option_may_follow_the_transcript_path(self):
        """The form scripts/backfill-failed-raws.py builds: path, then
        --until with a datetime.isoformat() offset."""
        r = self.cli(str(self._timed_transcript()), "--until",
                     "2026-09-16T04:00:00+00:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("early question", r.stdout)
        self.assertNotIn("late answer", r.stdout)

    def test_missing_value_fails(self):
        r = self.cli(str(self._timed_transcript()), "--until")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")

    def test_unknown_option_fails(self):
        r = self.cli("--nope", str(self._timed_transcript()))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")


class BackCompatTest(_TranscriptCase):
    def test_single_argument_invocation_renders_everything(self):
        path = self.write([
            _user("early question", ts=T_EARLY),
            _assistant("late answer", ts=T_LATE),
        ])
        r = self.cli(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("<!-- audit:"))
        self.assertIn("early question", r.stdout)
        self.assertIn("late answer", r.stdout)

    def test_no_arguments_prints_usage_and_exits_2(self):
        r = self.cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stderr)

    def test_missing_transcript_exits_1_silently(self):
        r = self.cli(str(Path(self._tmp.name) / "nope.jsonl"))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
