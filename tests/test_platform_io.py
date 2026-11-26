"""Wave 0 tests for shared atomic persistence and symlink refusal (`platform_io.py`)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from strands_code_cli.platform_io import (
    atomic_write_text,
    ensure_private_dir,
    refuse_symlink,
)


class TestPlatformIo:
    def test_refuse_symlink_target_and_ancestors(self, tmp_path):
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        real_file = real_dir / "file.txt"
        real_file.write_text("ok", encoding="utf-8")

        sym_file = tmp_path / "link.txt"
        sym_file.symlink_to(real_file)
        with pytest.raises(ValueError, match=r"Refusing symlink target:"):
            refuse_symlink(sym_file, "target")

        sym_parent = tmp_path / "sym_parent"
        sym_parent.symlink_to(real_dir)
        with pytest.raises(ValueError, match=r"Refusing symlink parent for cfg:"):
            refuse_symlink(sym_parent / "cfg.yaml", "cfg", max_ancestors=1)

        with pytest.raises(ValueError, match=r"Refusing symlink parent for nested:"):
            refuse_symlink(sym_parent / "sub" / "cfg.yaml", "nested", max_ancestors=2)

        # Stopping at refused roots (/tmp, /) never errors on clean tmp_path children.
        refuse_symlink(tmp_path / "clean" / "file.txt", "clean", max_ancestors=10)

    def test_ensure_private_dir_refuses_symlinks_and_sets_0700(self, tmp_path):
        target = tmp_path / "real"
        target.mkdir()
        sym_dir = tmp_path / "sym_dir"
        sym_dir.symlink_to(target)
        with pytest.raises(ValueError, match="Refusing symlink"):
            ensure_private_dir(sym_dir, "priv")
        with pytest.raises(ValueError, match="Refusing symlink parent"):
            ensure_private_dir(sym_dir / "nested", "nested", max_ancestors=1)

        priv = tmp_path / "a" / "b"
        out = ensure_private_dir(priv, "priv")
        assert out == Path(os.path.realpath(priv))
        assert stat.S_IMODE(os.stat(priv).st_mode) == 0o700

    def test_atomic_write_private_0600_immune_to_stale_tmp_symlink_and_cleans_up(
        self, tmp_path, monkeypatch
    ):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        victim = tmp_path / "victim.txt"
        victim.write_text("keep", encoding="utf-8")
        (cfg_dir / "settings.yaml.tmp").symlink_to(victim)

        target = cfg_dir / "settings.yaml"
        out = atomic_write_text(target, "model: test\n", mode=0o600, dir_mode=0o700)
        assert out == target
        assert target.read_text(encoding="utf-8") == "model: test\n"
        assert victim.read_text(encoding="utf-8") == "keep"
        assert stat.S_IMODE(os.stat(cfg_dir).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(target).st_mode) == 0o600

        # Error during os.replace removes mkstemp temp file cleanly.
        err_dir = tmp_path / "err_dir"
        err_dir.mkdir()

        def _boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", _boom)
        with pytest.raises(OSError, match="disk full"):
            atomic_write_text(err_dir / "out.txt", "abc", mode=0o600)
        assert list(err_dir.iterdir()) == []

    def test_atomic_write_mode_none_uses_umask_without_calling_os_umask(
        self, tmp_path, monkeypatch
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        os.chmod(repo, 0o755)

        def _forbid_umask(*_args, **_kwargs):
            raise AssertionError("atomic_write_text must never call os.umask()")

        monkeypatch.setattr(os, "umask", _forbid_umask)
        target = repo / "STRANDS.md"
        atomic_write_text(target, "# Repo\n", mode=None, dir_mode=None)

        file_mode = stat.S_IMODE(os.stat(target).st_mode)
        dir_mode = stat.S_IMODE(os.stat(repo).st_mode)
        assert file_mode != 0o600
        assert file_mode & stat.S_IRUSR
        assert file_mode & stat.S_IRGRP or file_mode & stat.S_IROTH
        assert dir_mode == 0o755
