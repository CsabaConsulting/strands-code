"""REPL history file permissions (T-01-03): typed asks rest at 0o600/0o700."""

import os
import stat

from prompt_toolkit.history import FileHistory

import strands_code_cli.loop.core as loop


def test_history_file_restricted(tmp_path, monkeypatch):
    monkeypatch.setattr("platformdirs.user_cache_dir", lambda *_a, **_k: str(tmp_path))
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
    monkeypatch.setattr("platformdirs.user_cache_dir", lambda *_a, **_k: str(tmp_path))
    loop._history()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_history_symlink_cache_or_file_falls_back_in_memory(tmp_path, monkeypatch):
    from prompt_toolkit.history import InMemoryHistory

    real_file = tmp_path / "secret.txt"
    real_file.write_text("untouched\n")
    os.chmod(real_file, 0o644)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "repl_history").symlink_to(real_file)
    monkeypatch.setattr("platformdirs.user_cache_dir", lambda *_a, **_k: str(cache_dir))
    hist = loop._history()
    assert isinstance(hist, InMemoryHistory)
    assert stat.S_IMODE(os.stat(real_file).st_mode) == 0o644

    real_dir = tmp_path / "real-dir"
    real_dir.mkdir()
    linked_dir = tmp_path / "linked-cache"
    linked_dir.symlink_to(real_dir)
    monkeypatch.setattr(
        "platformdirs.user_cache_dir", lambda *_a, **_k: str(linked_dir)
    )
    assert isinstance(loop._history(), InMemoryHistory)


def test_rich_history_refuses_symlink_parents_and_writes_private(tmp_path):
    good_stash = tmp_path / "sess" / "rich_history" / "s1.json"
    rh = loop.RichHistory()
    rh.messages = [{"role": "user", "content": [{"text": "hi"}]}]
    rh.model_id = "bedrock/a"
    rh.length = 1
    rh.prefix_hash = "abc"
    rh.save(good_stash)
    assert good_stash.exists()
    assert stat.S_IMODE(os.stat(good_stash).st_mode) == 0o600

    real_rh_dir = tmp_path / "real_rh"
    real_rh_dir.mkdir()
    linked_rh_dir = tmp_path / "sess" / "linked_rh"
    linked_rh_dir.symlink_to(real_rh_dir)
    evil_stash = linked_rh_dir / "s2.json"
    rh.save(evil_stash)
    assert not evil_stash.exists()

    (real_rh_dir / "s3.json").write_text(good_stash.read_text())
    loaded = loop.RichHistory.load(linked_rh_dir / "s3.json")
    assert loaded.messages is None
