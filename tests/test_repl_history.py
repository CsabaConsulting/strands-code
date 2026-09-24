"""REPL history file permissions (T-01-03): typed asks rest at 0o600/0o700."""

import os
import stat

from prompt_toolkit.history import FileHistory

from strands_code_cli import loop


def test_history_file_restricted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "platformdirs.user_cache_dir", lambda *_a, **_k: str(tmp_path)
    )
    history = loop._history()
    assert isinstance(history, FileHistory)
    st_dir = os.stat(tmp_path)
    assert stat.S_IMODE(st_dir.st_mode) == 0o700
    st_file = os.stat(tmp_path / "repl_history")
    assert stat.S_IMODE(st_file.st_mode) == 0o600


def test_history_rechmods_existing(tmp_path, monkeypatch):
    target = tmp_path / "repl_history"
    target.write_text("old\n")
    os.chmod(target, 0o644)
    monkeypatch.setattr(
        "platformdirs.user_cache_dir", lambda *_a, **_k: str(tmp_path)
    )
    loop._history()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
