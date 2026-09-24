"""First-run gate contracts: no creds stops with pointer, creates nothing.

Fail-fast style per the document_code TypeError/ValueError analog: the
credential probe is injected, so CI stays offline-clean and no AWS mocks
leak into other tests.
"""

from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from strands_code_cli.first_run import BEDROCK_SETUP_POINTER, preflight_credentials
from strands_code_cli.provider_config import ProviderConfig


def _no_creds() -> None:
    raise RuntimeError("Unable to locate credentials")


def _creds_ok() -> None:
    return None


# ----------------------------------------------------------------------
# Gate unit contracts
# ----------------------------------------------------------------------


class TestPreflightGate:
    def test_no_creds_exits_non_zero(self):
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_no_creds)
        assert exc_info.value.exit_code != 0

    def test_no_creds_prints_setup_pointer(self, capsys):
        with pytest.raises(typer.Exit):
            preflight_credentials(probe=_no_creds)
        err = capsys.readouterr().err
        assert "Bedrock" in err
        assert BEDROCK_SETUP_POINTER.splitlines()[0] in err

    def test_creds_ok_passes_silently(self, capsys):
        assert preflight_credentials(probe=_creds_ok) is None

    def test_never_reads_credentials_directly(self):
        import inspect

        source = inspect.getsource(preflight_credentials) + inspect.getsource(
            importlib.import_module("strands_code_cli.first_run")
        )
        assert "os.environ" not in source
        assert "os.getenv" not in source
        assert "getenv" not in source


# ----------------------------------------------------------------------
# CLI-level: no-creds run leaves the filesystem untouched
# ----------------------------------------------------------------------


class TestFirstRunCli:
    def test_no_creds_cli_exits_non_zero_with_pointer(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            main_module, "_preflight_credentials", side_effect=typer.Exit(code=2)
        ):
            result = CliRunner().invoke(main_module.app, [])
        assert result.exit_code != 0

    def test_no_creds_cli_creates_no_session_dir(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            main_module, "_preflight_credentials", side_effect=typer.Exit(code=2)
        ):
            CliRunner().invoke(
                main_module.app,
                ["--session-id", str(uuid.uuid4())],
            )
        assert list(tmp_path.iterdir()) == []

    def test_gate_runs_before_session_resolution(self, tmp_path, monkeypatch):
        """A failing gate must not mint index entries or snapshot dirs."""
        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            main_module, "_preflight_credentials", side_effect=typer.Exit(code=2)
        ):
            CliRunner().invoke(main_module.app, [])
        assert not Path(".agent").exists()


# ----------------------------------------------------------------------
# Provider choice persists across runs (D-06)
# ----------------------------------------------------------------------


class TestProviderConfigPersistence:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "config.yaml"
        ProviderConfig(model="bedrock:anthropic.claude-x").save(path)
        assert ProviderConfig.load(path).model == "bedrock:anthropic.claude-x"

    def test_missing_file_loads_defaults(self, tmp_path):
        assert ProviderConfig.load(tmp_path / "missing.yaml").model is None

    def test_unknown_keys_rejected(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("model: x\nbogus_key: 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Unknown provider config keys"):
            ProviderConfig.load(path)

    def test_corrupt_yaml_fails_soft_to_defaults(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("{{{not: yaml", encoding="utf-8")
        assert ProviderConfig.load(path).model is None

    def test_config_file_holds_no_credentials(self, tmp_path):
        path = tmp_path / "config.yaml"
        ProviderConfig(model="bedrock:anthropic.claude-x").save(path)
        body = path.read_text(encoding="utf-8").lower()
        assert "secret" not in body
        assert "access" not in body
        assert "token" not in body
