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

from strands_code_cli.entry.first_run import (
    BEDROCK_SETUP_POINTER,
    has_anthropic_credentials,
    has_openai_credentials,
    preflight_credentials,
)
from strands_code_cli.entry.provider_config import ProviderConfig


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

    def test_canary_secrets_never_leak_to_output_logs_or_disk(
        self, monkeypatch, capsys, caplog
    ):
        canary = "AIzaSyCanarySecretDoNotLeak98765"
        monkeypatch.setenv("GOOGLE_API_KEY", canary)
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        with caplog.at_level("WARNING"), pytest.raises(typer.Exit):
            preflight_credentials()
        captured = capsys.readouterr()
        assert "mutually exclusive" in captured.err.lower()
        assert canary not in captured.out
        assert canary not in captured.err
        assert canary not in caplog.text

        meta_canary = "LLM|9999999|MetaCanarySecretDoNotLeak1234"
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
        monkeypatch.setenv("MODEL_API_KEY", meta_canary)
        monkeypatch.setenv("META_BASE_URL", "ftp://bad.example/v1")
        with caplog.at_level("WARNING"), pytest.raises(typer.Exit):
            preflight_credentials()
        meta_captured = capsys.readouterr()
        assert "META_BASE_URL" in meta_captured.err
        assert meta_canary not in meta_captured.out
        assert meta_canary not in meta_captured.err
        assert meta_canary not in caplog.text

    def test_google_api_key_auto_picks_gemini_flash_without_sts(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "any-nonempty-token")
        assert (
            preflight_credentials(
                probe=lambda: pytest.fail("STS must not run when Google key is set")
            )
            == "google/gemini-3.8-flash"
        )

    def test_gemini_api_key_auto_picks_gemini_flash_without_sts(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "any-gemini-token")
        assert (
            preflight_credentials(
                probe=lambda: pytest.fail("STS must not run when GEMINI_API_KEY is set")
            )
            == "google/gemini-3.8-flash"
        )

    def test_vertex_adc_auto_picks_gemini_flash(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
        assert (
            preflight_credentials(
                probe=lambda: pytest.fail("STS must not run for Vertex ADC")
            )
            == "google/gemini-3.8-flash"
        )

    def test_vertex_false_with_api_key_uses_api_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "0")
        monkeypatch.setenv("GOOGLE_API_KEY", "nonempty-api-key")
        assert preflight_credentials(probe=_no_creds) == "google/gemini-3.8-flash"

    def test_vertex_and_api_key_mutually_exclusive_fails_fast(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "GOOGLE_GENAI_USE_VERTEXAI" in err
        assert "mutually exclusive" in err.lower()
        assert "secret-key" not in err

    def test_vertex_missing_project_fails_fast_noting_global(self, monkeypatch, capsys):
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "GOOGLE_CLOUD_PROJECT" in err
        assert "global" in err

    def test_explicit_google_model_without_google_creds_fails(self, capsys):
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(model="google/gemini-2.5-pro", probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "GOOGLE_API_KEY" in err

    def test_strands_box_bypasses_sts_and_accepts_phantom_keys(self, monkeypatch):
        monkeypatch.setenv("STRANDS_BOX", "1")
        assert (
            preflight_credentials(
                probe=lambda: pytest.fail("STRANDS_BOX=1 must skip STS probe")
            )
            is None
        )
        monkeypatch.setenv("GOOGLE_API_KEY", "strands_box_phantom_token")
        assert preflight_credentials() == "google/gemini-3.8-flash"

    def test_anthropic_and_openai_ambient_auto_pick(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        assert preflight_credentials(probe=_no_creds) == "anthropic/claude-sonnet-5-5"
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        assert preflight_credentials(probe=_no_creds) == "openai/gpt-6.2-sol"

    def test_meta_ambient_auto_pick_priority_and_helpers(self, monkeypatch, capsys):
        from strands_code_cli.entry.first_run import (
            META_DEFAULT_BASE_URL,
            has_meta_credentials,
            meta_api_key,
            meta_base_url,
        )

        assert has_meta_credentials({}) is False
        assert has_meta_credentials({"MODEL_API_KEY": "   "}) is False
        assert has_meta_credentials({"MODEL_API_KEY": "strands_box_meta"}) is True
        assert has_meta_credentials({"META_API_KEY": "fallback_tok"}) is True
        assert meta_api_key({"MODEL_API_KEY": "primary", "META_API_KEY": "sec"}) == (
            "primary"
        )
        assert meta_api_key({"META_API_KEY": " sec "}) == "sec"
        assert meta_api_key({}) is None
        assert meta_base_url({}) == META_DEFAULT_BASE_URL
        assert (
            meta_base_url({"META_BASE_URL": "https://meta-proxy.local/v1/"})
            == "https://meta-proxy.local/v1"
        )
        for bad_url in (
            "ftp://api.meta.ai/v1",
            "https://user:pass@api.meta.ai/v1",
            "https://api.meta.ai/v1 bad",
        ):
            with pytest.raises(ValueError):
                meta_base_url({"META_BASE_URL": bad_url})

        monkeypatch.setenv("MODEL_API_KEY", "any-meta-token")
        assert (
            preflight_credentials(probe=_no_creds) == "meta/muse-spark-1.3-contributor"
        )
        # Priority: OpenAI beats Meta; Meta beats OpenRouter error
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        assert (
            preflight_credentials(probe=_no_creds) == "meta/muse-spark-1.3-contributor"
        )
        monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
        assert preflight_credentials(probe=_no_creds) == "openai/gpt-6.2-sol"
        monkeypatch.delenv("OPENAI_API_KEY")
        monkeypatch.delenv("OPENROUTER_API_KEY")
        monkeypatch.delenv("MODEL_API_KEY")

        monkeypatch.setenv("META_API_KEY", "fallback-token")
        assert (
            preflight_credentials(probe=_no_creds) == "meta/muse-spark-1.3-contributor"
        )
        monkeypatch.setenv("META_BASE_URL", "ftp://bad.example/v1")
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_no_creds)
        assert exc_info.value.exit_code == 2
        assert "META_BASE_URL" in capsys.readouterr().err
        monkeypatch.delenv("META_BASE_URL")
        monkeypatch.delenv("META_API_KEY")

        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(model="meta/muse-wonder-1.0", probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        assert "MODEL_API_KEY" in capsys.readouterr().err
        assert (
            preflight_credentials(
                model="meta/muse-wonder-1.0",
                base_url="https://meta-proxy.local/v1",
                probe=_no_creds,
            )
            is None
        )

    def test_explicit_meta_validates_meta_base_url_unless_explicit_base_url(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("MODEL_API_KEY", "k-meta")
        monkeypatch.setenv("META_BASE_URL", "ftp://bad.example/v1")
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(model="meta/muse-wonder-1.0", probe=lambda: None)
        assert exc_info.value.exit_code == 2
        assert "META_BASE_URL" in capsys.readouterr().err

        assert (
            preflight_credentials(
                model="meta/muse-wonder-1.0",
                base_url="https://proxy.example/v1",
                probe=lambda: None,
            )
            is None
        )

    def test_has_openai_and_anthropic_credentials_presence_only(self, monkeypatch):
        assert has_openai_credentials({}) is False
        assert has_openai_credentials({"OPENAI_API_KEY": "   "}) is False
        assert has_openai_credentials({"OPENAI_API_KEY": "strands_box_oai"}) is True
        assert has_anthropic_credentials({}) is False
        assert has_anthropic_credentials({"ANTHROPIC_API_KEY": "\t"}) is False
        assert (
            has_anthropic_credentials({"ANTHROPIC_API_KEY": "strands_box_ant"}) is True
        )

        monkeypatch.setenv("OPENAI_API_KEY", "any-non-prefix-val")
        assert has_openai_credentials() is True
        monkeypatch.setenv("ANTHROPIC_API_KEY", "any-non-prefix-val")
        assert has_anthropic_credentials() is True

    def test_openrouter_ambient_requires_explicit_model_then_passes(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        # Bedrock/Box users who export OPENROUTER_API_KEY for /route still launch cleanly.
        assert preflight_credentials(probe=_creds_ok) is None
        monkeypatch.setenv("STRANDS_BOX", "1")
        assert preflight_credentials(probe=_no_creds) is None
        monkeypatch.delenv("STRANDS_BOX")
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "br-tok")
        assert preflight_credentials(probe=_no_creds) is None
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK")

        # Only when AWS/Box credentials are absent does it stop with the explicit --model pointer.
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_no_creds)
        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "--model" in err
        assert "litellm/openrouter/" in err
        assert (
            preflight_credentials(
                model="litellm/openrouter/google/gemini-2.5-flash", probe=_no_creds
            )
            is None
        )

    def test_litellm_ambient_pointer_google_scope_base_url_openrouter_and_unknown_provider(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("LITELLM_API_KEY", "litellm-only-key")
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(probe=_no_creds)
        assert exc_info.value.exit_code == 2
        assert "--model" in capsys.readouterr().err
        monkeypatch.delenv("LITELLM_API_KEY")

        # Stale conflicting Vertex + Gemini env does NOT block non-Google --model launches.
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "stale-gemini-key")
        monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
        assert (
            preflight_credentials(model="openai/gpt-6.2-sol", probe=_no_creds) is None
        )
        assert (
            preflight_credentials(model="anthropic/claude-sonnet-5-5", probe=_no_creds)
            is None
        )
        # Still fails fast when targeting google/ directly.
        with pytest.raises(typer.Exit) as exc_google:
            preflight_credentials(model="google/gemini-2.5-flash", probe=_creds_ok)
        assert exc_google.value.exit_code == 2
        assert "mutually exclusive" in capsys.readouterr().err.lower()
        monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI")
        monkeypatch.delenv("GEMINI_API_KEY")

        # Explicit litellm/openrouter with custom base_url passes without OPENROUTER_API_KEY.
        assert (
            preflight_credentials(
                model="litellm/openrouter/anthropic/claude-sonnet-4.6",
                base_url="https://proxy.local/v1",
                probe=_no_creds,
            )
            is None
        )

        # Typo / unknown provider prefix fails explicitly rather than probing STS.
        with pytest.raises(typer.Exit) as exc_unk:
            preflight_credentials(
                model="anthropi/claude-sonnet-5-5",
                probe=lambda: pytest.fail("Unknown provider must not probe STS"),
            )
        assert exc_unk.value.exit_code == 2
        assert "Unknown model provider 'anthropi'" in capsys.readouterr().err

    def test_ollama_passes_without_keys_or_sts(self):
        sts_fail = lambda: pytest.fail("Ollama must not probe STS")  # noqa: E731
        assert preflight_credentials(model="ollama/llama3.2", probe=sts_fail) is None
        assert (
            preflight_credentials(model="litellm/ollama_chat/llama3.2", probe=sts_fail)
            is None
        )

    def test_bedrock_bearer_token_skips_sts(self, monkeypatch):
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bearer-tok")
        assert (
            preflight_credentials(
                model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                probe=lambda: pytest.fail("Bearer token must skip STS"),
            )
            is None
        )

    def test_explicit_anthropic_openai_and_base_url_preflight(
        self, monkeypatch, capsys
    ):
        sts_fail = lambda: pytest.fail("Non-AWS provider must not probe STS")  # noqa: E731
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(model="anthropic/claude-sonnet-4-6", probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        assert "ANTHROPIC_API_KEY" in capsys.readouterr().err

        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(model="openai/gpt-5.4", probe=_creds_ok)
        assert exc_info.value.exit_code == 2
        assert "OPENAI_API_KEY" in capsys.readouterr().err

        assert (
            preflight_credentials(
                model="openai/gpt-5.4",
                base_url="http://127.0.0.1:8000/v1",
                probe=sts_fail,
            )
            is None
        )

    def test_explicit_litellm_and_openrouter_preflight_branches(
        self, monkeypatch, capsys
    ):
        sts_fail = lambda: pytest.fail("litellm provider must not probe STS")  # noqa: E731
        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(
                model="litellm/openrouter/anthropic/claude-sonnet-4.6",
                probe=_creds_ok,
            )
        assert exc_info.value.exit_code == 2
        capsys.readouterr()

        monkeypatch.setenv("LITELLM_API_KEY", "tok")
        assert (
            preflight_credentials(
                model="litellm/openrouter/anthropic/claude-sonnet-4.6",
                probe=sts_fail,
            )
            is None
        )
        monkeypatch.delenv("LITELLM_API_KEY")

        with pytest.raises(typer.Exit) as exc_info:
            preflight_credentials(
                model="litellm/deepseek/deepseek-chat", probe=_creds_ok
            )
        assert exc_info.value.exit_code == 2
        assert "OPENROUTER_API_KEY" in capsys.readouterr().err

        assert (
            preflight_credentials(
                model="litellm/deepseek/deepseek-chat",
                base_url="https://proxy.local",
                probe=sts_fail,
            )
            is None
        )
        monkeypatch.setenv("STRANDS_BOX", "1")
        assert (
            preflight_credentials(
                model="litellm/deepseek/deepseek-chat", probe=sts_fail
            )
            is None
        )


# ----------------------------------------------------------------------
# CLI-level: no-creds run leaves the filesystem untouched
# ----------------------------------------------------------------------


class TestFirstRunCli:
    def test_no_creds_cli_exits_non_zero_with_pointer(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.entry.main")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            main_module, "_preflight_credentials", side_effect=typer.Exit(code=2)
        ):
            result = CliRunner().invoke(main_module.app, [])
        assert result.exit_code != 0

    def test_no_creds_cli_creates_no_session_dir(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.entry.main")

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
        main_module = importlib.import_module("strands_code_cli.entry.main")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            main_module, "_preflight_credentials", side_effect=typer.Exit(code=2)
        ):
            CliRunner().invoke(main_module.app, [])
        assert not Path(".agent").exists()

    def test_cli_model_flag_is_session_scoped_and_never_writes_config(
        self, tmp_path, monkeypatch
    ):
        main_module = importlib.import_module("strands_code_cli.entry.main")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("GOOGLE_API_KEY", "strands_box_test_key")
        with (
            patch.object(main_module, "build_agent", return_value=object()) as built,
            patch.object(main_module, "run_loop") as loop,
        ):
            result = CliRunner().invoke(
                main_module.app, ["--model", "google/gemini-2.5-flash"]
            )
        assert result.exit_code == 0, result.output
        assert built.call_args[1]["model"] == "google/gemini-2.5-flash"
        assert loop.call_args[1]["model_id"] == "google/gemini-2.5-flash"
        assert not (tmp_path / "xdg").exists()

    def test_cli_ambient_auto_pick_passes_model_id_to_run_loop(
        self, tmp_path, monkeypatch
    ):
        main_module = importlib.import_module("strands_code_cli.entry.main")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("GOOGLE_API_KEY", "strands_box_test_key")
        with (
            patch.object(main_module, "build_agent", return_value=object()) as built,
            patch.object(main_module, "run_loop") as loop,
        ):
            result = CliRunner().invoke(main_module.app, [])
        assert result.exit_code == 0, result.output
        assert built.call_args[1]["model"] == "google/gemini-3.8-flash"
        assert loop.call_args[1]["model_id"] == "google/gemini-3.8-flash"
        assert not (tmp_path / "xdg").exists()

    def test_blank_model_flag_rejected_before_side_effects(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.entry.main")

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(main_module.app, ["--model", "   "])
        assert result.exit_code != 0
        assert "invalid --model" in result.output
        assert not (tmp_path / ".agent").exists()


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

    def test_api_mode_round_trip_and_validation(self, tmp_path):
        path = tmp_path / "config.yaml"
        ProviderConfig(
            model="openai/gpt-6.1-sol",
            base_url="https://proxy.local/v1",
            api_mode="chat",
        ).save(path)
        loaded = ProviderConfig.load(path)
        assert loaded.api_mode == "chat"

        ProviderConfig(model="openai/gpt-6.1-sol", api_mode="responses").save(path)
        assert ProviderConfig.load(path).api_mode == "responses"

        path.write_text("model: openai/gpt-4o\napi_mode: legacy\n", encoding="utf-8")
        with pytest.raises(ValueError, match="api_mode"):
            ProviderConfig.load(path)
        with pytest.raises(ValueError, match="api_mode"):
            ProviderConfig(model="openai/gpt-4o", api_mode="legacy").save(path)

    def test_base_url_validation_and_cross_provider_switch_clearing(self, tmp_path):
        path = tmp_path / "config.yaml"
        for bad in (
            "https://user:secret@proxy.example/v1",
            "file:///etc/passwd",
            "ftp://proxy.example/v1",
            "https://",
            "https://proxy.example/v1\r\nX: 1",
        ):
            with pytest.raises(ValueError, match="base_url"):
                ProviderConfig(model="openai/gpt-6.1-sol", base_url=bad).save(path)

        cfg = ProviderConfig(
            model="openai/gpt-6.1-sol",
            base_url="http://127.0.0.1:8000/v1",
            api_mode="chat",
        )
        cfg.save_model_choice("openai/gpt-6.1-terra", path)
        same_provider = ProviderConfig.load(path)
        assert same_provider.base_url == "http://127.0.0.1:8000/v1"
        assert same_provider.api_mode == "chat"

        same_provider.save_model_choice("anthropic/claude-sonnet-5-5", path)
        cross_provider = ProviderConfig.load(path)
        assert cross_provider.model == "anthropic/claude-sonnet-5-5"
        assert cross_provider.base_url is None
        assert cross_provider.api_mode is None

        or_cfg = ProviderConfig(
            model="litellm/openrouter/anthropic/claude-sonnet-4.6",
            base_url="http://127.0.0.1:4000/v1",
            api_mode="chat",
        )
        or_cfg.save_model_choice("litellm/anthropic/claude-sonnet-4-6", path)
        switched_lt = ProviderConfig.load(path)
        assert switched_lt.base_url is None
        assert switched_lt.api_mode is None

    def test_provider_config_field_types_and_tmp_symlink_rejection(self, tmp_path):
        from strands_code_cli.entry.provider_config import _provider_of_model

        assert (
            _provider_of_model("arn:aws:bedrock:us-west-2:123:inference-profile/x")
            == "bedrock"
        )
        assert _provider_of_model("bare-id") == "bedrock"

        path = tmp_path / "config.yaml"
        for bad_cfg in (
            ProviderConfig(model=123),
            ProviderConfig(base_url=123),
            ProviderConfig(codeact="invalid"),
            ProviderConfig(diff_mode="approve-each"),
            ProviderConfig(memory_mode="auto"),
        ):
            with pytest.raises(ValueError):
                bad_cfg.save(path)

        victim = tmp_path / "victim.txt"
        victim.write_text("keep", encoding="utf-8")
        (tmp_path / "config.yaml.tmp").symlink_to(victim)
        saved = ProviderConfig(model="openai/gpt-6.1-sol").save(path)
        assert saved == path
        assert (path.stat().st_mode & 0o777) == 0o600
        assert victim.read_text(encoding="utf-8") == "keep"

        real_dir = tmp_path / "real-cfg"
        real_dir.mkdir()
        linked_dir = tmp_path / "linked-cfg"
        linked_dir.symlink_to(real_dir)
        with pytest.raises(ValueError, match="symlink"):
            ProviderConfig(model="openai/gpt-6.1-sol").save(linked_dir / "config.yaml")


# ----------------------------------------------------------------------
# Untrusted CWD .env auto-load guard (T-14-02)
# ----------------------------------------------------------------------


class TestCwdDotenvGuard:
    def test_untrusted_repo_dotenv_cannot_hijack_provider_or_base_url(self, tmp_path):
        import os
        import subprocess
        import sys

        hostile_keys = (
            "GEMINI_API_KEY",
            "GOOGLE_GEMINI_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "STRANDS_BOX",
        )
        (tmp_path / ".env").write_text(
            "GEMINI_API_KEY=evil-attacker-key\n"
            "GOOGLE_GEMINI_BASE_URL=https://evil.example\n"
            "ANTHROPIC_BASE_URL=https://evil.example\n"
            "STRANDS_BOX=1\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        for key in hostile_keys:
            env.pop(key, None)
        probe = (
            "import os\n"
            "import strands_code_cli\n"
            "from strands_code_cli.cost import live_pricing\n"
            "from strands_code_cli.entry.first_run import has_google_credentials\n"
            "live_pricing.litellm_entry('google/gemini-3.8-flash')\n"
            "leaked = [k for k in ('GEMINI_API_KEY', 'GOOGLE_GEMINI_BASE_URL', 'ANTHROPIC_BASE_URL', 'STRANDS_BOX') if k in os.environ]\n"
            "assert not leaked, f'leaked .env keys: {leaked}'\n"
            "assert has_google_credentials() is False\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    def test_explicit_dotenv_path_still_delegates(self, tmp_path, monkeypatch):
        import os

        import dotenv

        from strands_code_cli.entry.first_run import disable_cwd_dotenv

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("STRANDS_TEST_DOTENV_GUARD", raising=False)
        monkeypatch.delenv("STRANDS_TEST_DOTENV_EXPLICIT", raising=False)
        (tmp_path / ".env").write_text(
            "STRANDS_TEST_DOTENV_GUARD=from_cwd\n", encoding="utf-8"
        )
        explicit = tmp_path / "explicit.env"
        explicit.write_text(
            "STRANDS_TEST_DOTENV_EXPLICIT=from_explicit\n", encoding="utf-8"
        )

        disable_cwd_dotenv()
        assert dotenv.load_dotenv() is False
        assert "STRANDS_TEST_DOTENV_GUARD" not in os.environ

        assert dotenv.load_dotenv(dotenv_path=explicit) is True
        assert os.environ.get("STRANDS_TEST_DOTENV_EXPLICIT") == "from_explicit"

    def test_wave5_vertex_enterprise_precedence_dotenv_values_and_openai_base_url(
        self, tmp_path, monkeypatch
    ):
        import dotenv

        from strands_code_cli.entry import first_run

        # Exact google-genai truthiness: "yes" or padded whitespace is NOT enabled; ENTERPRISE overrides VERTEXAI.
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "yes")
        assert first_run.has_google_credentials() is False
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", " true ")
        assert first_run.has_google_credentials() is False
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
        monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "0")
        assert first_run.has_google_credentials() is False
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "0")
        monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
        assert first_run.has_google_credentials() is True

        # disable_cwd_dotenv also blocks implicit dotenv.dotenv_values() from CWD .env.
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("SECRET_FROM_CWD=leaked\n", encoding="utf-8")
        explicit = tmp_path / "exp.env"
        explicit.write_text("EXPLICIT_OK=yes\n", encoding="utf-8")
        first_run.disable_cwd_dotenv()
        assert dotenv.dotenv_values() == {}
        assert dotenv.dotenv_values(dotenv_path=explicit) == {"EXPLICIT_OK": "yes"}

        # openai_base_url validates & normalizes trailing slash.
        monkeypatch.setenv("OPENAI_BASE_URL", "https://oai.example/v1/")
        assert first_run.openai_base_url() == "https://oai.example/v1"
