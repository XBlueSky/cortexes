"""SessionEnd recording guards, and what a filter failure leaves behind.

session-end-record.sh does `mkdir -p "$target_dir"` synchronously (before it
detaches the async writer via nohup), so "was Raw/ created?" is a race-free
signal for whether the script proceeded past the opt-out guard.

The second half of this module covers the filter's failure path. It used to be
`python3 "$FILTER" ... 2>/dev/null || echo "(filter failed)"`: the traceback
naming the offending filter went to /dev/null, and the ~100-byte stub left
behind did not even say which transcript produced it. 21 Raw files were lost
that way between 2026-09-02 and 2026-09-16 and had to be re-mapped to their
transcripts by hand. Now stderr is appended to ~/.cortex/filter-failures.log,
following the ~/.cortex/push-failures.log convention (see
tests/test_push_failure_visibility.py), and the transcript path is recorded in
the Raw's own frontmatter.

Three properties of that failure path are pinned here, each of which the first
attempt at it got wrong:

  * the log is a REDACTED sink (it goes through the same redact_secrets() the
    Raw body does) and is created 0600 -- "we never commit it" is not a
    control, a credential in cleartext on disk has already leaked;
  * the timeout that bounds a hung filter is a backstop, not a budget, and an
    unparsable CORTEX_FILTER_TIMEOUT falls back to the default instead of
    making timeout(1) exit 125 for every session in every repo;
  * the Raw is written atomically, so a filter killed mid-flush cannot leave a
    half-written body at the target path. Such a file matches neither half of
    the discriminator scripts/backfill-failed-raws.py uses (body strips to
    exactly "(filter failed)", size < 300 bytes), so it would be a corrupt
    record that no repair tool can ever find.
"""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "hooks" / "scripts" / "session-end-record.sh"

# The interpreter the stubs below delegate to. A stub that shadows python3 on
# PATH shadows it for the WHOLE hook -- the filter, the stderr redaction
# helper, meta_session.py, the cortex_vec probe. Delegating everything except
# the one call under test keeps each stub a model of "this filter crashed"
# rather than "this machine has no python".
REAL_PYTHON = shutil.which("python3") or "python3"

# A stderr line carrying two credential shapes redact_secrets() knows: a
# GitLab PAT behind an Authorization header, and a password in a DSN.
SECRET_STDERR = (
    "Traceback (most recent call last): boom-from-the-stub "
    "req_headers={Authorization: Bearer glpat-AbCdEfGhIjKlMnOpQrSt} "
    "dsn=postgres://svcuser:Sup3rS3cretPassw0rd@db.internal:5432/x"
)
LEAKED_TOKEN = "glpat-AbCdEfGhIjKlMnOpQrSt"
LEAKED_PASSWORD = "Sup3rS3cretPassw0rd"


def _setup(tmp_path):
    home = tmp_path / "home"
    (home / ".cortex").mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    (home / ".cortex" / "config.json").write_text(
        json.dumps({"vault_path": str(vault)})
    )
    # A transcript comfortably over the 4096-byte size gate so the script
    # reaches the recording logic.
    tx = tmp_path / "transcript.jsonl"
    line = json.dumps(
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "x" * 200}]}}
    )
    tx.write_text((line + "\n") * 40)
    assert tx.stat().st_size >= 4096
    cwd = tmp_path / "work"
    cwd.mkdir()
    return home, vault, tx, cwd


def _run(home, tx, cwd, extra_env=None):
    env = {**os.environ, "HOME": str(home)}
    env.pop("CORTEX_SESSION_RECORDING", None)
    env.pop("CORTEX_SKIP_RECORD", None)
    env.pop("CORTEX_FILTER_TIMEOUT", None)
    if extra_env:
        env.update(extra_env)
    stdin = json.dumps({"transcript_path": str(tx), "cwd": str(cwd)})
    return subprocess.run(
        ["bash", str(RECORD)], input=stdin, text=True,
        capture_output=True, env=env,
    )


def test_skip_record_env_suppresses_raw(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd, {"CORTEX_SKIP_RECORD": "1"})
    assert r.returncode == 0
    # Guard exits before the synchronous mkdir, so no Raw tree is created.
    assert not (vault / "Raw").exists()


def test_without_skip_env_proceeds_to_record(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd)
    assert r.returncode == 0
    # No opt-out: the script proceeds and synchronously creates the Raw dir.
    assert (vault / "Raw").exists()


# --- filter failure visibility -------------------------------------------

def _wait_for(pred, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.2)
    return pred()


def _raw_files(vault):
    return sorted((vault / "Raw").rglob("*.md"))


def _raw_body(path):
    """The Raw body, the way scripts/backfill-failed-raws.py splits it."""
    parts = path.read_text().split("---\n", 2)
    assert len(parts) == 3, f"not a frontmatter document: {path}"
    return parts[2]


def _log_path(home):
    return home / ".cortex" / "filter-failures.log"


def _log_text(home):
    log = _log_path(home)
    assert _wait_for(lambda: log.exists() and "exit=" in log.read_text()), \
        "filter failure was not logged"
    return log.read_text()


def _stub_python(tmp_path, filter_case):
    """A python3 earlier on PATH whose FILTER invocation runs `filter_case`.

    Every other python3 call the hook makes -- `python3 -c ...` (the stderr
    redaction helper and the cortex_vec probe), meta_session.py -- is handed
    to the real interpreter, so the hook behaves exactly as it would in the
    field with one crashing filter.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        f'case "$1" in -c) exec {REAL_PYTHON} "$@" ;; esac\n'
        'case "$*" in\n'
        "  *filter-transcript.py*)\n"
        f"{filter_case}"
        "    ;;\n"
        "esac\n"
        f'exec {REAL_PYTHON} "$@"\n'
    )
    stub.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}"}


def _crashing_filter(tmp_path, message="Traceback (most recent call last): boom-from-the-stub"):
    """The filter fails, loudly, on stderr.

    Forces the hook down its failure path without needing a payload that
    actually breaks a filter — the whole point of the fail-open work is that
    such payloads should no longer exist.
    """
    return _stub_python(
        tmp_path,
        f'    printf "%s\\n" {shlex.quote(message)} >&2\n'
        "    exit 1\n",
    )


def _broken_python(tmp_path, message):
    """A python3 that fails for EVERY call — filter and helpers alike.

    This is the no-interpreter case: even the stderr redaction helper cannot
    run, which is exactly when the temptation to log stderr raw appears.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" {shlex.quote(message)} >&2\n'
        "exit 1\n"
    )
    stub.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}"}


def test_filter_failure_is_logged_with_stderr(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd, {**_crashing_filter(tmp_path),
                             "CORTEX_NO_CLASSIFIER": "1"})
    assert r.returncode == 0

    text = _log_text(home)
    # the traceback that used to go to /dev/null
    assert "boom-from-the-stub" in text
    # and the three fields that make a backfill mechanical instead of forensic
    assert f"transcript={tx}" in text
    assert "raw=" in text and str(vault / "Raw") in text
    assert "exit=1" in text

    # the body fallback still exists, so the Raw is self-describing
    raws = _raw_files(vault)
    assert len(raws) == 1
    assert "(filter failed)" in raws[0].read_text()


def test_raw_frontmatter_records_its_transcript(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    _run(home, tx, cwd, {**_crashing_filter(tmp_path),
                         "CORTEX_NO_CLASSIFIER": "1"})
    assert _wait_for(lambda: _raw_files(vault) and _raw_files(vault)[0].stat().st_size)
    assert f"transcript: {tx}" in _raw_files(vault)[0].read_text()


def test_filter_failure_log_redacts_credentials(tmp_path):
    """The log is a redacted sink, not a raw one.

    An exception message quotes the payload that broke the filter, which is
    precisely where a credential lives. The first version of this log wrote
    `tail -c 8192 "$filter_err"` straight through, so a token that the Raw
    body would have redacted landed byte-for-byte in ~/.cortex. "We never
    commit that file" is a weaker control than not recording the secret.
    """
    home, vault, tx, cwd = _setup(tmp_path)
    _run(home, tx, cwd, {**_crashing_filter(tmp_path, SECRET_STDERR),
                         "CORTEX_NO_CLASSIFIER": "1"})
    text = _log_text(home)

    assert LEAKED_TOKEN not in text
    assert LEAKED_PASSWORD not in text
    assert "REDACTED" in text
    # the diagnostic value survives the redaction
    assert "boom-from-the-stub" in text


def test_filter_failure_log_is_owner_only(tmp_path):
    """0644 makes every local account a reader of the failure log."""
    home, vault, tx, cwd = _setup(tmp_path)
    _run(home, tx, cwd, {**_crashing_filter(tmp_path),
                         "CORTEX_NO_CLASSIFIER": "1"})
    _log_text(home)
    assert stat.S_IMODE(_log_path(home).stat().st_mode) == 0o600


def test_stderr_is_dropped_when_redaction_is_unavailable(tmp_path):
    """Fail-open in the SAFE direction.

    If the redaction pass cannot run (here: no usable python3 at all) the hook
    must log a fixed placeholder. Losing a traceback is recoverable; writing a
    credential to disk is not.
    """
    home, vault, tx, cwd = _setup(tmp_path)
    _run(home, tx, cwd, {**_broken_python(tmp_path, SECRET_STDERR)})
    text = _log_text(home)

    assert LEAKED_TOKEN not in text
    assert LEAKED_PASSWORD not in text
    assert "boom-from-the-stub" not in text
    assert "redaction unavailable" in text
    # the record still points at the transcript, which is what a backfill needs
    assert f"transcript={tx}" in text
    assert "exit=1" in text


def test_hanging_filter_is_bounded_and_logged(tmp_path):
    """A hang used to be worse than a crash.

    Without a bound, a filter that never returns left a frontmatter-only Raw
    with no "(filter failed)" body at all — invisible to any health check
    keyed on that string. timeout(1) converts it into an ordinary logged
    failure, and an explicit numeric CORTEX_FILTER_TIMEOUT is honoured.
    """
    home, vault, tx, cwd = _setup(tmp_path)
    env = _stub_python(tmp_path, "    sleep 30\n")
    _run(home, tx, cwd, {**env, "CORTEX_FILTER_TIMEOUT": "1"})

    assert "exit=124" in _log_text(home)  # 124 == killed by timeout(1)
    assert "(filter failed)" in _raw_files(vault)[0].read_text()


def test_killed_filter_leaves_no_partial_raw(tmp_path):
    """A SIGTERM mid-flush must not leave a half-written record behind.

    filter-transcript.py emits the whole body in one terminal write, so a
    filter killed by the timeout can have flushed an arbitrary prefix of it.
    Writing the filter straight into the target path appended "(filter
    failed)" to that prefix: the result is neither under the 300-byte ceiling
    nor does its body strip to exactly "(filter failed)", so
    scripts/backfill-failed-raws.py can never find it. It is a corrupt record
    with no marker — the exact failure mode the stub exists to prevent.
    """
    home, vault, tx, cwd = _setup(tmp_path)
    env = _stub_python(
        tmp_path,
        "    i=0\n"
        "    while [ $i -lt 400 ]; do\n"
        '      printf "REAL SESSION CONTENT %s\\n" "$i"\n'
        "      i=$((i + 1))\n"
        "    done\n"
        "    sleep 30\n",
    )
    _run(home, tx, cwd, {**env, "CORTEX_FILTER_TIMEOUT": "1"})

    assert "exit=124" in _log_text(home)
    raws = _raw_files(vault)
    assert len(raws) == 1
    text = raws[0].read_text()
    assert "REAL SESSION CONTENT" not in text
    # both halves of the backfill discriminator
    assert _raw_body(raws[0]).strip() == "(filter failed)"
    assert raws[0].stat().st_size < 300
    # the record is assembled elsewhere and renamed in, and nothing is left over
    assert not [p for p in (vault / "Raw").rglob("*") if ".partial." in p.name]


def test_non_numeric_timeout_falls_back_to_default(tmp_path):
    """timeout(1) exits 125 BEFORE python runs on a value it cannot parse.

    So a human-friendly CORTEX_FILTER_TIMEOUT="10 minutes" does not merely
    misconfigure one session — it stubs every session in every repo until
    someone reads the failure log. An unusable value must fall back to the
    default bound.
    """
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd, {"CORTEX_NO_CLASSIFIER": "1",
                             "CORTEX_FILTER_TIMEOUT": "10 minutes"})
    assert r.returncode == 0
    assert _wait_for(lambda: _raw_files(vault)
                     and "### Claude" in _raw_files(vault)[0].read_text())
    assert "(filter failed)" not in _raw_files(vault)[0].read_text()
    assert not _log_path(home).exists()


def test_default_filter_timeout_is_a_hang_backstop():
    """The default bound is read from the source on purpose.

    Exercising it would mean waiting it out, so the property pinned here is
    the size of the constant: everything the bound kills is a destroyed
    session record, so it has to sit far above the slowest legitimate run
    (~1131s measured, for a 128 KB single-line blob through the redaction
    pass). 600s was below that — a backstop that fired for slow-but-
    progressing work rather than for a hang.
    """
    m = re.search(r"CORTEX_FILTER_TIMEOUT:-(\d+)", RECORD.read_text())
    if m is None:
        m = re.search(r'filter_timeout="\$\{filter_timeout:-(\d+)\}"',
                      RECORD.read_text())
    assert m, "the default filter timeout is no longer a literal in the hook"
    assert int(m.group(1)) >= 1800, (
        f"default filter timeout {m.group(1)}s is a budget, not a backstop"
    )


def test_successful_filter_writes_no_log(tmp_path):
    home, vault, tx, cwd = _setup(tmp_path)
    r = _run(home, tx, cwd, {"CORTEX_NO_CLASSIFIER": "1"})
    assert r.returncode == 0
    assert _wait_for(lambda: _raw_files(vault)
                     and "### Claude" in _raw_files(vault)[0].read_text())
    body = _raw_files(vault)[0].read_text()
    assert "(filter failed)" not in body
    assert not _log_path(home).exists()
