"""The CLI's agent-facing failure contract.

An agent decides its next step from the exit code alone: 2 means "fix the
command and retry", 3 means "the environment is not set up — stop and tell
the user". Every error is one stderr line that names the fix.
"""
import json
import sys

import pytest

from cortex_vec import cli, config, store

# conftest replaces config.load_config with a stub for every test; keep the
# real one so these tests can exercise the missing/invalid-config paths.
_REAL_LOAD_CONFIG = config.load_config


def _run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    err = capsys.readouterr().err
    return exc.value.code, err


def _run_ok(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["cortex-vec", *argv])
    cli.main()
    return capsys.readouterr()


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setattr(config, "load_config", lambda: {"vault_path": str(root)})
    return root


def test_missing_config_is_a_setup_error_naming_genesis(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "load_config", _REAL_LOAD_CONFIG)
    monkeypatch.setattr(config, "CORTEX_CONFIG", tmp_path / "absent.json")

    code, err = _run(monkeypatch, capsys, "distill-queue")

    assert code == 3
    assert err.startswith("cortex-vec: error: ")
    assert "/cortexes:genesis" in err
    assert err.count("\n") == 1


def test_invalid_vault_path_is_a_setup_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "load_config",
                        lambda: {"vault_path": str(tmp_path / "gone")})

    code, err = _run(monkeypatch, capsys, "distill-queue")

    assert code == 3
    assert "vault_path" in err


def test_missing_api_key_is_a_setup_error_offering_bm25_only(vault, monkeypatch, capsys):
    (vault / "Notes").mkdir()
    (vault / "Notes" / "a.md").write_text("# a\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    code, err = _run(monkeypatch, capsys, "upsert", "Notes/a.md")

    assert code == 3
    assert "OPENAI_API_KEY" in err
    assert "--bm25-only" in err


def test_upsert_of_a_missing_file_is_a_caller_error(vault, monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, "upsert", "Notes/nope.md")

    assert code == 2
    assert "Notes/nope.md" in err
    assert str(vault) in err  # names the root the path is resolved against


def test_delete_of_an_unindexed_path_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(store, "get_client", lambda: None)
    monkeypatch.setattr(store, "get_collection", lambda client: None)
    monkeypatch.setattr(store, "_delete_stale_entries", lambda col, rel: [])

    out = _run_ok(monkeypatch, capsys, "delete", "Notes/never.md")

    assert out.out == ""
    assert "not indexed" in out.err


def test_search_without_a_bm25_index_is_a_setup_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "BM25_DIR", tmp_path / "no-bm25")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    code, err = _run(monkeypatch, capsys, "search", "anything")

    assert code == 3
    assert "cortex-vec rebuild" in err


def test_raw_page_errors_keep_their_json_envelope(tmp_path, monkeypatch, capsys):
    # raw-map/raw-span already speak JSON-on-stdout + exit 2; the new stderr
    # contract must not wrap or duplicate them.
    monkeypatch.setattr(sys, "argv", ["cortex-vec", "raw-span", str(tmp_path / "x.md"),
                                      "--plan-id", "nope"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    cap = capsys.readouterr()
    assert exc.value.code == 2
    assert "error" in json.loads(cap.out)
    assert "cortex-vec: error:" not in cap.err
