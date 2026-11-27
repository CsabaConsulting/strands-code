"""Hermetic tests for Strands Box config, egress profiles, Dogwood policy, and diagnostics."""

from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.routing.core import (
    RoutingCandidate,
    RoutingEngine,
    RoutingStrategy,
)
from strands_code_cli.sandbox.box import (
    CORE_PROVIDERS,
    OPTIONAL_PROFILES,
    default_box_config_dir,
    default_box_data_dir,
    detect_active_providers,
    discover_box_binaries,
    format_doctor_report,
    init_box_config,
    is_in_strands_box,
    launch_box_run,
    repo_config_id,
    resolve_runtime_paths,
    run_box_doctor,
)


def _fake_box_dir(root: Path, *, include_all: bool = True) -> Path:
    bdir = root / "box-bin"
    bdir.mkdir(parents=True, exist_ok=True)
    names = ["box"]
    if include_all:
        names.extend(["strands-box-contain-trampoline", "strands-box-sock-alias"])
    for name in names:
        p = bdir / name
        p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(p, 0o755)
    return bdir


def _assert_no_nested_dirs(entries: list[str]) -> None:
    paths = [Path(p) for p in entries]
    for idx, cand in enumerate(paths):
        for jdx, other in enumerate(paths):
            if idx != jdx:
                assert other != cand and cand not in other.parents, (cand, other)


class TestConftestAndBoxEnv:
    def test_conftest_scrubs_box_env_vars(self):
        from tests.conftest import _PROVIDER_ENV_VARS

        for name in ("STRANDS_BOX", "STRANDS_BOX_BIN", "EXPERIMENTAL_X86_SUPPORT"):
            assert name in _PROVIDER_ENV_VARS
            assert name not in os.environ

    def test_is_in_strands_box(self, monkeypatch):
        assert is_in_strands_box() is False
        assert is_in_strands_box({"STRANDS_BOX": "0"}) is False
        assert is_in_strands_box({"STRANDS_BOX": "1"}) is True
        assert is_in_strands_box({"STRANDS_BOX": "true"}) is True
        monkeypatch.setenv("STRANDS_BOX", "yes")
        assert is_in_strands_box() is True


class TestBoxConfigGenerationAndEgress:
    def test_host_only_storage_perms_and_distinct_repo_hashes(
        self, tmp_path, monkeypatch
    ):
        cfg_root = tmp_path / "cfg_root"
        data_root = tmp_path / "data_root"
        cache_root = tmp_path / "cache_root"
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(cfg_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(data_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(cache_root / app)
        )

        repo_a = tmp_path / "a" / "service"
        repo_b = tmp_path / "b" / "service"
        repo_a.mkdir(parents=True)
        repo_b.mkdir(parents=True)

        id_a = repo_config_id(repo_a)
        id_b = repo_config_id(repo_b)
        assert id_a.startswith("service-") and id_b.startswith("service-")
        assert id_a != id_b
        assert (
            default_box_config_dir(repo_a) == cfg_root / "strands-box" / "repos" / id_a
        )
        assert (
            default_box_data_dir(repo_a) == data_root / "strands-box" / "repos" / id_a
        )

        res = init_box_config(
            repo_a, env={"HOME": str(tmp_path), "TERM": "xterm-256color"}
        )
        assert res.self_tamper_risk is False
        assert res.box_toml.parent == default_box_config_dir(repo_a)
        assert stat.S_IMODE(res.box_toml.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(res.box_toml.stat().st_mode) == 0o600
        assert stat.S_IMODE(res.policy_dw.stat().st_mode) == 0o600

        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        assert parsed["policy"] == "policy.dw"
        assert parsed["box_dir"] == str(default_box_data_dir(repo_a))
        write_paths = [
            Path(p).resolve() for p in parsed["agent"]["filesystem"]["write"]
        ]
        assert (cfg_root / "strands-box").resolve() not in write_paths
        assert res.box_toml.parent.resolve() not in write_paths

    def test_uv_symlink_realpath_resolution_and_agent_env(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        uv_py = (
            home
            / ".local"
            / "share"
            / "uv"
            / "python"
            / "cpython-3.12"
            / "bin"
            / "python3.12"
        )
        uv_py.parent.mkdir(parents=True)
        uv_py.write_text("#!/bin/sh\n", encoding="utf-8")

        repo = tmp_path / "repo"
        venv_bin = repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        venv_py = venv_bin / "python"
        venv_py.symlink_to(uv_py)

        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(home / ".config" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(home / ".cache" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir",
            lambda app: str(home / ".local" / "share" / app),
        )

        paths = resolve_runtime_paths(
            repo,
            python_executable=venv_py,
            home=home,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        for needed in (
            repo.resolve(),
            (repo / ".venv").resolve(),
            uv_py.parent.parent.resolve(),
            (home / ".local" / "share" / "uv" / "python").resolve(),
        ):
            assert any(needed == r or r in needed.parents for r in paths["read"]), (
                needed
            )

        res = init_box_config(
            repo,
            python_executable=venv_py,
            home=home,
            env={
                "HOME": str(home),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "AWS_REGION": "us-east-1",
            },
        )
        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        env_tbl = parsed["agent"]["env"]
        assert env_tbl["STRANDS_BOX"] == "1"
        assert env_tbl["TERM"] == "xterm-256color"
        assert env_tbl["COLORTERM"] == "truecolor"
        assert env_tbl["AWS_REGION"] == "us-east-1"
        assert "HOME" not in env_tbl
        assert env_tbl["TMPDIR"] == str(
            (home / ".cache" / "strands-code" / "tmp").resolve()
        )
        assert str((repo / ".venv" / "bin").resolve()) in env_tbl["PATH"]
        fs_tbl = parsed["agent"]["filesystem"]
        assert "read_file" not in fs_tbl
        assert "list" not in fs_tbl
        assert str(uv_py.resolve()) in fs_tbl["exec"]
        assert str(venv_py) not in fs_tbl["exec"]
        assert "/usr" not in fs_tbl["read"]
        assert "/tmp" not in fs_tbl["read"]
        assert "/tmp" not in fs_tbl["write"]
        _assert_no_nested_dirs(fs_tbl["read"])
        _assert_no_nested_dirs(fs_tbl["write"])

    def test_extension_exec_and_arch_lib_read_grants(self, tmp_path, monkeypatch):
        import platform
        import sysconfig

        home = tmp_path / "home"
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(home / ".config" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(home / ".cache" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir",
            lambda app: str(home / ".local" / "share" / app),
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        res = init_box_config(repo, home=home, env={"HOME": str(home)})
        fs_tbl = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))["agent"][
            "filesystem"
        ]
        dyn = Path(sysconfig.get_paths()["stdlib"]).resolve() / "lib-dynload"
        if dyn.is_dir():
            assert str(dyn) in fs_tbl["exec"]
        arch_lib = Path(f"/usr/lib/{platform.machine()}-linux-gnu")
        if arch_lib.is_dir():
            arch_real = str(arch_lib.resolve())
            assert arch_real in fs_tbl["read"]
            assert arch_real not in fs_tbl["exec"]

    def test_least_privilege_provider_detection(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        assert detect_active_providers(
            repo,
            config=ProviderConfig(model=None),
            routing_strategy=None,
            env={},
        ) == ["bedrock"]

        detected = detect_active_providers(
            repo,
            config=ProviderConfig(model="anthropic/claude-sonnet-5-5"),
            routing_strategy=RoutingStrategy(
                candidates=[RoutingCandidate(id="google/gemini-3.8-flash")],
                engine=RoutingEngine(
                    primary="native",
                    order=["native", "llm", "decisions_api"],
                    llm_model="openai/gpt-6.2-sol",
                ),
            ),
            env={"MODEL_API_KEY": "x", "GITHUB_TOKEN": "ghp_unrelated"},
        )
        assert set(detected) == {
            "google",
            "anthropic",
            "openai",
            "meta",
            "typesafe",
            "decisions_api",
        }
        assert detected.index("decisions_api") == detected.index("typesafe") + 1
        assert "github_skills" not in detected

        env_detected = detect_active_providers(
            repo,
            config=ProviderConfig(model=None),
            routing_strategy=None,
            env={"TYPESAFE_API_KEY": "ts", "JEV_API_KEY": "jev"},
        )
        assert env_detected == ["typesafe", "decisions_api"]

        with_opt = detect_active_providers(
            repo,
            config=ProviderConfig(
                model="litellm/openrouter/anthropic/claude-sonnet-4.6"
            ),
            routing_strategy=None,
            env={},
            allow_decisions_api=True,
            allow_github_skills=True,
        )
        assert with_opt == ["openrouter", "decisions_api", "github_skills"]

    def test_all_seven_plus_two_egress_profiles(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()

        res = init_box_config(
            repo,
            providers=[*CORE_PROVIDERS, *OPTIONAL_PROFILES],
            aws_region="eu-central-1",
            allow_decisions_api=True,
            allow_github_skills=True,
            env={"HOME": str(tmp_path), "GITHUB_TOKEN": "token-present"},
        )
        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        egress = parsed["egress"]

        assert egress["bedrock"]["destinations"] == [
            "bedrock-runtime.eu-central-1.amazonaws.com"
        ]
        assert egress["bedrock"]["secret"]["ref"] == "aws://"
        assert "sts.amazonaws.com" not in res.box_toml.read_text(encoding="utf-8")

        assert egress["google"]["destinations"] == ["generativelanguage.googleapis.com"]
        assert egress["google"]["secret"] == {
            "ref": "env://GOOGLE_API_KEY",
            "placement": "header",
            "header": "x-goog-api-key",
            "prefix": "",
        }
        assert egress["anthropic"]["secret"]["header"] == "Authorization"
        assert egress["anthropic"]["secret"]["prefix"] == "Bearer"
        assert egress["openai"]["destinations"] == ["api.openai.com"]
        assert egress["meta"]["destinations"] == ["api.meta.ai"]
        assert egress["openrouter"]["destinations"] == [
            "openrouter.ai/api/v1/chat/*",
            "openrouter.ai/api/alpha/decisions",
        ]
        assert "openrouter_models" not in egress
        assert egress["typesafe"]["destinations"] == ["api.typesafe.ai"]
        assert egress["decisions_api"]["destinations"] == ["decisionapi.net"]
        assert egress["github_api"]["destinations"] == ["api.github.com"]
        assert egress["github_api"]["secret"]["ref"] == "env://GITHUB_TOKEN"
        assert "github_downloads" not in egress
        dw_text = res.policy_dw.read_text(encoding="utf-8")
        assert 'context.input.path like "/api/v1/models*"' in dw_text
        assert 'context.input.host == "codeload.github.com"' in dw_text
        assert 'context.input.host == "objects.githubusercontent.com"' in dw_text

    def test_secretless_egress_targets_stay_out_of_box_toml(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        # Secret-less github_skills stays out of box.toml while permitted in policy.dw.
        res_no_gh = init_box_config(
            repo,
            out_dir=tmp_path / "cfg_no_gh",
            providers=["github_skills"],
            allow_github_skills=True,
            env={"HOME": str(tmp_path)},
        )
        parsed_no_gh = tomllib.loads(res_no_gh.box_toml.read_text(encoding="utf-8"))
        assert "egress" not in parsed_no_gh
        dw_no_gh = res_no_gh.policy_dw.read_text(encoding="utf-8")
        assert 'context.input.host == "api.github.com"' in dw_no_gh
        assert 'context.input.host == "codeload.github.com"' in dw_no_gh

    def test_empty_order_cache_read_aws_profile_cli_cmd_and_mode_warnings(
        self, tmp_path, monkeypatch
    ):
        cfg_root = tmp_path / "cfg"
        data_root = tmp_path / "data"
        cache_root = tmp_path / "cache"
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(cfg_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(data_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(cache_root / app)
        )

        repo = tmp_path / "repo"
        venv_bin = repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        cli_bin = venv_bin / "strands-code"
        cli_bin.write_text("#!/bin/sh\n", encoding="utf-8")
        py_bin = venv_bin / "python"
        py_bin.write_text("#!/bin/sh\n", encoding="utf-8")

        # Empty routing order disables routing instead of falling back to openrouter.
        disabled = RoutingStrategy(
            candidates=[RoutingCandidate(id="anthropic/claude-sonnet-5-5")],
            engine=RoutingEngine(primary="openrouter", order=[]),
        )
        res_empty = init_box_config(
            repo,
            config=ProviderConfig(model=None),
            routing_strategy=disabled,
            python_executable=py_bin,
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "AWS_PROFILE": "corp"},
        )
        assert res_empty.providers == ("bedrock",)
        parsed_empty = tomllib.loads(res_empty.box_toml.read_text(encoding="utf-8"))
        assert parsed_empty["egress"]["bedrock"]["secret"]["ref"] == "aws://corp"
        assert parsed_empty["agent"]["command"] == [str(cli_bin.resolve())]
        assert str(cli_bin.resolve()) in parsed_empty["agent"]["filesystem"]["exec"]
        read_strs = parsed_empty["agent"]["filesystem"]["read"]
        write_strs = parsed_empty["agent"]["filesystem"]["write"]
        cache_resolved = str((cache_root / "strands-code").resolve())
        assert cache_resolved in read_strs
        assert cache_resolved in write_strs
        assert "/tmp" not in read_strs
        assert "/tmp" not in write_strs
        assert parsed_empty["agent"]["env"]["TMPDIR"] == str(
            (cache_root / "strands-code" / "tmp").resolve()
        )
        assert (data_root / "strands-box" / "repos").is_dir()
        assert (cfg_root / "strands-code").is_dir()
        assert (cache_root / "strands-code" / "tmp").is_dir()

        # Absent CLI binary uses executable -c fallback instead of non-existent __main__.py.
        cli_bin.unlink()
        paths_no_cli = resolve_runtime_paths(
            repo, python_executable=py_bin, env={"PATH": ""}
        )
        assert paths_no_cli["agent_command"][:2] == [str(py_bin.resolve()), "-c"]

        # Mode warnings for Vertex AI, custom base_url, Ollama, and bedrock-mantle.
        res_warn = init_box_config(
            repo,
            config=ProviderConfig(
                model="bedrock-mantle/openai.gpt-6.2-sol",
                base_url="https://proxy.example/v1",
            ),
            routing_strategy=RoutingStrategy(
                candidates=[RoutingCandidate(id="ollama/llama3.2")],
                engine=RoutingEngine(primary="local"),
            ),
            env={
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin",
                "GOOGLE_GENAI_USE_VERTEXAI": "1",
            },
        )
        joined = "\n".join(res_warn.warnings)
        assert "GOOGLE_GENAI_USE_VERTEXAI" in joined
        assert "custom base_url" in joined
        assert "Ollama" in joined
        assert "bedrock-mantle" in res_warn.providers

    def test_bedrock_mantle_egress_profile(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        res_mantle_warn = init_box_config(
            repo,
            providers=["bedrock"],
            config=ProviderConfig(model="bedrock-mantle/openai.gpt-6.2-sol"),
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        )
        assert any("bedrock-mantle" in w for w in res_mantle_warn.warnings)
        mantle_only = init_box_config(
            repo,
            providers=["bedrock-mantle"],
            aws_region="eu-central-1",
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        )
        parsed_mantle = tomllib.loads(mantle_only.box_toml.read_text(encoding="utf-8"))
        assert parsed_mantle["egress"]["bedrock_mantle"]["destinations"] == [
            "bedrock-mantle.eu-central-1.api.aws"
        ]

    def test_tool_sections_use_valid_canonical_paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()

        res = init_box_config(
            repo, providers=["openrouter"], env={"HOME": str(tmp_path)}
        )
        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        tools = parsed["tool"]
        assert tools and "python" not in tools
        for tool_name, tool_tbl in tools.items():
            cmd_path = Path(tool_tbl["command"][0])
            assert cmd_path.is_file(), tool_name
            t_fs = tool_tbl["filesystem"]
            for w_dir in t_fs.get("write", []):
                w_path = Path(w_dir)
                assert any(
                    w_path == r_dir or r_dir in w_path.parents
                    for r_dir in map(Path, t_fs["read"])
                )
        if (
            "pytest" in tools
            and b"python"
            in Path(tools["pytest"]["command"][0]).read_bytes().splitlines()[0].lower()
        ):
            import sys

            py_real = str(Path(os.path.realpath(sys.executable)))
            pytest_fs = tools["pytest"]["filesystem"]
            covered = any(
                py_real == r or Path(r) in Path(py_real).parents
                for r in pytest_fs["read"]
            )
            assert covered or py_real in pytest_fs.get("read_file", [])

    def test_box_name_cap_and_in_workspace_tools_skipped(self, tmp_path, monkeypatch):
        import re

        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = (
            tmp_path / "a-very-long-repository-name-exceeding-thirty-two-bytes-easily"
        )
        venv_bin = repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        for name in ("pytest", "ruff"):
            p = venv_bin / name
            p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(p, 0o755)

        res = init_box_config(
            repo,
            providers=["bedrock"],
            env={"HOME": str(tmp_path), "PATH": str(venv_bin)},
        )
        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        box_name = parsed["name"]
        assert len(box_name.encode("utf-8")) <= 32
        assert re.fullmatch(r"[A-Za-z0-9._-]+", box_name)
        write_paths = [Path(w) for w in parsed["agent"]["filesystem"]["write"]]
        for tool_tbl in parsed.get("tool", {}).values():
            cmd = Path(tool_tbl["command"][0])
            assert not any(cmd == w or w in cmd.parents for w in write_paths)
        assert "pytest" not in parsed.get("tool", {})
        assert "ruff" not in parsed.get("tool", {})

        # Non-writable git on PATH still resolves while repo .venv pytest/ruff do not fall back to global binaries.
        res_sys = init_box_config(
            repo,
            out_dir=tmp_path / "cfg_sys",
            providers=["bedrock"],
            env={"HOME": str(tmp_path), "PATH": f"{venv_bin}:/usr/bin:/bin"},
        )
        tools_sys = tomllib.loads(res_sys.box_toml.read_text(encoding="utf-8")).get(
            "tool", {}
        )
        assert "pytest" not in tools_sys
        assert "ruff" not in tools_sys
        assert "git" in tools_sys
        for tool_tbl in tools_sys.values():
            cmd = Path(tool_tbl["command"][0])
            assert not any(cmd == w or w in cmd.parents for w in write_paths)

    def test_dogwood_policy_rules_and_tools(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()

        res = init_box_config(
            repo, providers=["openrouter"], env={"HOME": str(tmp_path)}
        )
        dw = res.policy_dw.read_text(encoding="utf-8")
        for expected in (
            'action == Box::Action::"net:connect"',
            'action == Box::Action::"http:request"',
            'context.input.path like "/api/v1/chat/*"',
            'context.input.path like "*/.env"',
            'context.input.path like "*/.env.*"',
            'context.input.path like "*/.envrc"',
            'context.input.path like "*/.ssh/*"',
            'context.input.path like "*/.aws/*"',
            'context.input.path like "*/.git/config"',
            'context.input.path like "*/.netrc"',
            'context.input.path like "*/.npmrc"',
            'context.input.path like "*/.pypirc"',
            '@id("allow_fs_read")',
            '@id("allow_fs_write")',
            '@id("allow_fs_delete")',
            '@id("allow_fs_move")',
            '@id("allow_shell_exec")',
            '["pytest", "rg", "ruff", "uv", "git"].contains(context.input.program)',
            '@id("forbid_uv_git_push")',
            'forbid (principal, action == Box::Action::"shell:spawn", resource)',
            'context.input.program == "git"',
            "context.input has arg1",
            'context.input.arg1 == "push"',
            "unless temporal {",
            "formerly within 900s",
            'Box::Action::"shell:spawn"::response',
            'input.program: "pytest"',
            'input.arg1: "--version"',
            'input.arg1: "run"',
            'input.arg2: "pytest"',
            "output.status: 0",
            "scoped revisit of v1.0 D-05",
        ):
            assert expected in dw


class TestSandboxSecurityAndDiagnostics:
    def test_out_self_tamper_warning_and_symlink_refusal(self, tmp_path, monkeypatch):
        cfg_root = tmp_path / "cfg_root"
        data_root = tmp_path / "data_root"
        cache_root = tmp_path / "cache_root"
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(cfg_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(data_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(cache_root / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        in_repo_out = repo / ".agent" / "box"
        res_warn = init_box_config(
            repo, out_dir=in_repo_out, env={"HOME": str(tmp_path)}
        )
        assert res_warn.self_tamper_risk is True
        assert any("writable sandbox paths" in w for w in res_warn.warnings)

        in_code_cfg_out = cfg_root / "strands-code" / "box"
        res_code_cfg = init_box_config(
            repo, out_dir=in_code_cfg_out, env={"HOME": str(tmp_path)}
        )
        assert res_code_cfg.self_tamper_risk is True

        sym_dir = tmp_path / "sym_box_dir"
        sym_dir.symlink_to(tmp_path)
        with pytest.raises(ValueError, match="symlink"):
            init_box_config(repo, out_dir=sym_dir, env={"HOME": str(tmp_path)})

        sym_toml_dir = tmp_path / "sym_toml_dir"
        sym_toml_dir.mkdir()
        (sym_toml_dir / "box.toml").symlink_to(res_warn.box_toml)
        with pytest.raises(ValueError, match=r"Refusing symlink box\.toml: "):
            init_box_config(repo, out_dir=sym_toml_dir, env={"HOME": str(tmp_path)})

        bdir = _fake_box_dir(tmp_path)
        with pytest.raises(ValueError, match="symlink"):
            launch_box_run(
                [],
                repo_root=repo,
                config_path=sym_toml_dir / "box.toml",
                box_bin=bdir / "box",
                env={"HOME": str(tmp_path)},
            )

    def test_canary_secrets_never_leak_and_injection_rejected(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        canaries = {
            "AWS_BEARER_TOKEN_BEDROCK": "br_CanarySecret_0001",
            "GOOGLE_API_KEY": "AIzaSyCanarySecret_0002",
            "ANTHROPIC_API_KEY": "sk-ant-CanarySecret_0003",
            "OPENAI_API_KEY": "sk-CanarySecret_0004",
            "MODEL_API_KEY": "LLM|CanarySecret_0005",
            "OPENROUTER_API_KEY": "sk-or-CanarySecret_0006",
            "TYPESAFE_API_KEY": "ts_CanarySecret_0007",
            "JEV_API_KEY": "jev_CanarySecret_0008",
            "GITHUB_TOKEN": "ghp_CanarySecret_0009",
        }
        fake_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", **canaries}
        res = init_box_config(
            repo,
            providers=[*CORE_PROVIDERS, *OPTIONAL_PROFILES],
            allow_decisions_api=True,
            allow_github_skills=True,
            env=fake_env,
        )
        toml_body = res.box_toml.read_text(encoding="utf-8")
        dw_body = res.policy_dw.read_text(encoding="utf-8")
        report_txt = format_doctor_report(
            run_box_doctor(repo, config_path=res.box_toml, env=fake_env)
        )
        for secret in canaries.values():
            assert secret not in toml_body
            assert secret not in dw_body
            assert secret not in report_txt

        for bad_region in ("us-west-2\nevil", 'us-west-2"', "bad/region"):
            with pytest.raises(ValueError, match="AWS region|control"):
                init_box_config(
                    repo, aws_region=bad_region, env={"HOME": str(tmp_path)}
                )
        for bad_prof in ("bad profile", "a\nb", "../esc"):
            with pytest.raises(ValueError, match="AWS profile|control"):
                init_box_config(repo, aws_profile=bad_prof, env={"HOME": str(tmp_path)})
        with pytest.raises(ValueError, match="Unknown provider"):
            init_box_config(repo, providers=["bogus"], env={"HOME": str(tmp_path)})

    def test_linux_three_binary_colocation_x86_apparmor_and_launch(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        res = init_box_config(repo, env={"HOME": str(tmp_path)})

        partial = _fake_box_dir(tmp_path / "partial", include_all=False)
        resolved, missing = discover_box_binaries(partial / "box")
        assert resolved is None
        assert set(missing) == {
            "strands-box-contain-trampoline",
            "strands-box-sock-alias",
        }

        full = _fake_box_dir(tmp_path / "full", include_all=True)
        resolved_ok, missing_ok = discover_box_binaries(
            env={"STRANDS_BOX_BIN": str(full / "box")}
        )
        assert resolved_ok == full / "box" and missing_ok == []

        sysctl = tmp_path / "apparmor_restrict_unprivileged_userns"
        profile = tmp_path / "strands-box.profile"
        sysctl.write_text("1\n", encoding="utf-8")

        bad_rep = run_box_doctor(
            repo,
            config_path=res.box_toml,
            box_bin=full / "box",
            env={"HOME": str(tmp_path), "PATH": str(full)},
            system_name="Linux",
            machine="x86_64",
            apparmor_sysctl_path=sysctl,
            apparmor_profile_path=profile,
        )
        assert bad_rep.ok is False
        by_name = {c.name: c for c in bad_rep.checks}
        assert by_name["linux_arch"].ok is False
        assert by_name["apparmor_userns"].ok is False
        rendered_bad = format_doctor_report(bad_rep)
        assert "EXPERIMENTAL_X86_SUPPORT=TRUE" in rendered_bad
        assert "userns," in rendered_bad

        profile.write_text("profile strands-box {}\n", encoding="utf-8")
        missing_userns_rep = run_box_doctor(
            repo,
            config_path=res.box_toml,
            box_bin=full / "box",
            env={
                "HOME": str(tmp_path),
                "PATH": str(full),
                "EXPERIMENTAL_X86_SUPPORT": "TRUE",
            },
            system_name="Linux",
            machine="x86_64",
            apparmor_sysctl_path=sysctl,
            apparmor_profile_path=profile,
        )
        assert {c.name: c for c in missing_userns_rep.checks}[
            "apparmor_userns"
        ].ok is False

        profile.write_text("profile strands-box {\n  userns,\n}\n", encoding="utf-8")
        good_rep = run_box_doctor(
            repo,
            config_path=res.box_toml,
            box_bin=full / "box",
            env={
                "HOME": str(tmp_path),
                "PATH": str(full),
                "EXPERIMENTAL_X86_SUPPORT": "TRUE",
            },
            system_name="Linux",
            machine="x86_64",
            apparmor_sysctl_path=sysctl,
            apparmor_profile_path=profile,
        )
        assert good_rep.ok is True
        assert "Status: READY" in format_doctor_report(good_rep)

        captured: dict = {}

        def _fake_runner(cmd, *, env, check):
            captured["cmd"] = cmd
            captured["env"] = env
            captured["check"] = check
            return SimpleNamespace(returncode=0)

        rc, notices = launch_box_run(
            ["--codeact", "--model", "anthropic/claude-sonnet-5-5"],
            repo_root=repo,
            config_path=res.box_toml,
            box_bin=full / "box",
            env={"HOME": str(tmp_path)},
            machine="x86_64",
            runner=_fake_runner,
        )
        assert rc == 0
        assert captured["cmd"] == [
            str(full / "box"),
            "run",
            "--config",
            str(res.box_toml),
            "--",
            "--codeact",
            "--model",
            "anthropic/claude-sonnet-5-5",
        ]
        assert captured["env"]["EXPERIMENTAL_X86_SUPPORT"] == "TRUE"
        assert any("EXPERIMENTAL_X86_SUPPORT=TRUE" in n for n in notices)

    def test_grandparent_and_pre_realpath_code_dir_symlinks_refused(
        self, tmp_path, monkeypatch
    ):
        cfg_root = tmp_path / "cfg_root"
        data_root = tmp_path / "data_root"
        cache_root = tmp_path / "cache_root"
        for d in (cfg_root, data_root, cache_root):
            d.mkdir()
        target = tmp_path / "real_target"
        target.mkdir()
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(cfg_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(data_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(cache_root / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        box_cfg_root = cfg_root / "strands-box"
        box_cfg_root.symlink_to(target)
        with pytest.raises(ValueError, match="Refusing symlink parent"):
            init_box_config(repo, env={"HOME": str(tmp_path)})
        box_cfg_root.unlink()

        code_cfg = cfg_root / "strands-code"
        code_cfg.symlink_to(target)
        with pytest.raises(ValueError, match="Refusing symlink"):
            init_box_config(repo, env={"HOME": str(tmp_path)})
        code_cfg.unlink()

        code_cache = cache_root / "strands-code"
        code_cache.symlink_to(target)
        with pytest.raises(ValueError, match="Refusing symlink"):
            init_box_config(repo, env={"HOME": str(tmp_path)})

    def test_launch_box_run_fails_closed_on_corrupt_or_unsafe_box_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        bdir = _fake_box_dir(tmp_path)

        bad_toml = tmp_path / "bad" / "box.toml"
        bad_toml.parent.mkdir()
        bad_toml.write_text("name = [broken", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid box.toml"):
            launch_box_run(
                [], repo_root=repo, config_path=bad_toml, box_bin=bdir / "box"
            )

        real_pol = tmp_path / "real.dw"
        real_pol.write_text("", encoding="utf-8")
        sym_pol = bad_toml.parent / "custom.dw"
        sym_pol.symlink_to(real_pol)
        bad_toml.write_text('policy = "custom.dw"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="Refusing symlink policy"):
            launch_box_run(
                [], repo_root=repo, config_path=bad_toml, box_bin=bdir / "box"
            )

        for unsafe_dir in ("relative/box", str(Path.home() / "box_data"), "/tmp/x"):
            bad_toml.write_text(f'box_dir = "{unsafe_dir}"\n', encoding="utf-8")
            with pytest.raises(ValueError, match="box_dir"):
                launch_box_run(
                    [], repo_root=repo, config_path=bad_toml, box_bin=bdir / "box"
                )

    def test_discover_box_binaries_requires_executable_and_safe_path(self, tmp_path):
        bdir = _fake_box_dir(tmp_path)
        os.chmod(bdir / "strands-box-contain-trampoline", 0o644)
        found, missing = discover_box_binaries(bdir / "box")
        assert found is None
        assert "strands-box-contain-trampoline" in missing

        os.chmod(bdir / "strands-box-contain-trampoline", 0o755)
        os.chmod(bdir / "box", 0o644)
        found2, missing2 = discover_box_binaries(bdir / "box")
        assert found2 is None and missing2

        found3, _ = discover_box_binaries(env={"STRANDS_BOX_BIN": "/bin/box\nevil"})
        assert found3 is None

    def test_policy_dw_hardens_git_flag_push_and_box_dir_mutations(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        res = init_box_config(repo, providers=["bedrock"], env={"HOME": str(tmp_path)})
        dw = res.policy_dw.read_text(encoding="utf-8")
        assert 'context.input.arg2 == "push"' in dw
        assert 'context.input.command like "* push"' in dw
        for rid in (
            "forbid_box_config_write",
            "forbid_box_config_delete",
            "forbid_box_config_move",
        ):
            assert f'@id("{rid}")' in dw
        assert 'context.input.path like "*/.config/strands-box/*"' in dw
        assert 'context.input.path like "*/.local/share/strands-box/*"' in dw

    def test_render_agent_env_filters_unsafe_xdg_paths(self, tmp_path):
        from strands_code_cli.sandbox.box import _render_agent_env

        repo = tmp_path / "repo"
        repo.mkdir()
        rt = resolve_runtime_paths(repo, home=tmp_path)
        valid_xdg = str(tmp_path / "xdg_cfg")
        env_rel = _render_agent_env(
            runtime=rt,
            providers=["bedrock"],
            aws_region="us-west-2",
            env={
                "PATH": "/usr/bin:/bin",
                "XDG_CONFIG_HOME": "relative/cfg",
                "XDG_CACHE_HOME": "/tmp",
            },
        )
        assert "XDG_CONFIG_HOME" not in env_rel
        assert "XDG_CACHE_HOME" not in env_rel
        env_ok = _render_agent_env(
            runtime=rt,
            providers=["bedrock"],
            aws_region="us-west-2",
            env={"PATH": "/usr/bin:/bin", "XDG_CONFIG_HOME": valid_xdg},
        )
        assert env_ok["XDG_CONFIG_HOME"] == valid_xdg


class TestBoxNyquistEdgeBranches:
    def test_shebang_atomic_write_and_dir_helper_edge_branches(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.sandbox import box as sandbox_box

        assert sandbox_box._shebang_interpreter(tmp_path / "missing") is None
        assert sandbox_box._shebang_interpreter(tmp_path) is None

        empty_shebang = tmp_path / "empty_shebang.sh"
        empty_shebang.write_text("#!   \nexit 0\n", encoding="utf-8")
        assert sandbox_box._shebang_interpreter(empty_shebang) is None

        assert sandbox_box._valid_nonroot_dir(None) is None
        repo_no_venv = tmp_path / "repo_no_venv"
        repo_no_venv.mkdir()
        assert (
            sandbox_box._resolve_venv_dir(repo_no_venv, Path("/opt/custom/python3"))
            is None
        )

        monkeypatch.setattr(sandbox_box, "_valid_nonroot_dir", lambda _cand: None)
        assert sandbox_box._system_arch_lib_dir() is None

        out_dir = tmp_path / "atomic_fail"
        out_dir.mkdir()

        def _fail_replace(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", _fail_replace)
        with pytest.raises(OSError, match="disk full"):
            sandbox_box._atomic_write_text(out_dir / "box.toml", "x = 1\n")
        assert list(out_dir.iterdir()) == []

    def test_provider_detection_fallbacks_and_alias_egress_keys(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.sandbox import box as sandbox_box

        assert (
            sandbox_box._provider_from_model_id("us.anthropic.claude-sonnet-4-6")
            == "bedrock"
        )
        assert (
            sandbox_box._provider_from_model_id(
                "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude"
            )
            == "bedrock"
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        or_strat = RoutingStrategy(
            engine=RoutingEngine(order=("openrouter",)), candidates=()
        )
        assert "openrouter" in detect_active_providers(
            repo, config=ProviderConfig(), routing_strategy=or_strat, env={}
        )

        assert sandbox_box._normalize_requested_providers(
            ["google,,anthropic,"],
            allow_decisions_api=False,
            allow_github_skills=False,
        ) == ["google", "anthropic"]

        google_spec = sandbox_box._egress_specs_for_providers(
            ["google"],
            aws_region="us-west-2",
            aws_profile=None,
            env={"GEMINI_API_KEY": "g"},
        )[0]
        assert google_spec.secret_ref == "env://GEMINI_API_KEY"

        meta_spec = sandbox_box._egress_specs_for_providers(
            ["meta"],
            aws_region="us-west-2",
            aws_profile=None,
            env={"META_API_KEY": "m"},
        )[0]
        assert meta_spec.secret_ref == "env://META_API_KEY"

        refs = sandbox_box._configured_model_refs(
            ProviderConfig(),
            RoutingStrategy(
                engine=RoutingEngine(order=("llm",), llm_model="ollama/qwen3:8b"),
                candidates=(),
            ),
        )
        assert refs == ["ollama/qwen3:8b"]

        def _raise_val(*_args, **_kwargs):
            raise ValueError("corrupt")

        monkeypatch.setattr(ProviderConfig, "load", _raise_val)
        assert detect_active_providers(
            repo,
            routing_strategy=RoutingStrategy(
                engine=RoutingEngine(order=()), candidates=()
            ),
            env={},
        ) == ["bedrock"]

        monkeypatch.setattr(sandbox_box, "load_strategy", _raise_val)
        assert detect_active_providers(repo, config=ProviderConfig(), env={}) == [
            "bedrock"
        ]

    def test_doctor_and_binary_discovery_edge_branches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        full = _fake_box_dir(tmp_path / "full", include_all=True)
        dogwood = full / "dogwood"
        dogwood.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(dogwood, 0o755)

        found_dir, missing_dir = discover_box_binaries(full)
        assert found_dir == full / "box" and missing_dir == []

        rep_darwin = run_box_doctor(
            repo,
            box_bin=full,
            env={"HOME": str(tmp_path), "PATH": str(full)},
            system_name="Darwin",
            machine="arm64",
        )
        checks_d = {c.name: c for c in rep_darwin.checks}
        assert checks_d["linux_arch"].ok is False
        assert "Unsupported host OS 'Darwin'" in checks_d["linux_arch"].detail
        assert "Optional dogwood CLI installed at" in checks_d["dogwood_cli"].detail
        assert checks_d["box_config"].ok is False
        assert "Config not found" in checks_d["box_config"].detail

        sysctl = tmp_path / "sysctl"
        sysctl.write_text("0\n", encoding="utf-8")
        bad_dir = tmp_path / "bad_cfg"
        bad_dir.mkdir()
        bad_toml = bad_dir / "box.toml"
        bad_toml.write_text("name = [broken\n", encoding="utf-8")
        (bad_dir / "policy.dw").write_text("", encoding="utf-8")
        rep_arm = run_box_doctor(
            repo,
            config_path=bad_toml,
            box_bin=full / "box",
            env={"HOME": str(tmp_path)},
            system_name="Linux",
            machine="aarch64",
            apparmor_sysctl_path=sysctl,
        )
        checks_a = {c.name: c for c in rep_arm.checks}
        assert checks_a["linux_arch"].ok is True
        assert "GA supported" in checks_a["linux_arch"].detail
        assert checks_a["apparmor_userns"].ok is True
        assert "restriction disabled" in checks_a["apparmor_userns"].detail
        assert checks_a["box_config"].ok is False
        assert "Invalid box.toml" in checks_a["box_config"].detail

        sym_dir = tmp_path / "sym_cfg"
        sym_dir.mkdir()
        sym_toml = sym_dir / "box.toml"
        sym_toml.symlink_to(bad_toml)
        (sym_dir / "policy.dw").write_text("", encoding="utf-8")
        rep_sym = run_box_doctor(
            repo,
            config_path=sym_toml,
            box_bin=full / "box",
            env={"HOME": str(tmp_path)},
        )
        checks_s = {c.name: c for c in rep_sym.checks}
        assert checks_s["box_config"].ok is False
        assert "Symlink refused" in checks_s["box_config"].detail

    def test_launch_box_run_validation_and_default_config_edge_branches(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.sandbox import box as sandbox_box

        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(tmp_path / "cfg" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(tmp_path / "data" / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda app: str(tmp_path / "cache" / app)
        )

        repo = tmp_path / "repo"
        repo.mkdir()
        full = _fake_box_dir(tmp_path / "full", include_all=True)

        with pytest.raises(ValueError, match="Box config not found"):
            launch_box_run(
                [],
                repo_root=repo,
                box_bin=full / "box",
                env={"HOME": str(tmp_path)},
            )

        res = init_box_config(repo, env={"HOME": str(tmp_path)})
        with pytest.raises(ValueError, match="Strands Box binary layout incomplete"):
            launch_box_run(
                [],
                repo_root=repo,
                config_path=res.box_toml,
                box_bin=tmp_path / "missing-box",
                env={"HOME": str(tmp_path)},
            )

        abs_sym_pol = tmp_path / "abs_sym.dw"
        abs_sym_pol.symlink_to(res.policy_dw)
        abs_cfg_dir = tmp_path / "abs_cfg"
        abs_cfg_dir.mkdir()
        abs_cfg = abs_cfg_dir / "box.toml"
        abs_cfg.write_text(f'policy = "{abs_sym_pol}"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="Refusing symlink policy"):
            launch_box_run(
                [],
                repo_root=repo,
                config_path=abs_cfg,
                box_bin=full / "box",
                env={"HOME": str(tmp_path)},
            )

        bad_cfg = abs_cfg_dir / "bad_box.toml"
        bad_cfg.write_text("[broken\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid"):
            sandbox_box._validate_launch_config(bad_cfg)

    def test_wave3_box_toml_utf8_xdg_defaults_litellm_apparmor_and_symlinks(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.sandbox import box as sandbox_box

        # Non-BMP TOML serialization succeeds while surrogates fail closed.
        rendered = sandbox_box._toml_str("/tmp/🚀-repo")
        assert tomllib.loads(f"v = {rendered}")["v"] == "/tmp/🚀-repo"
        with pytest.raises(ValueError, match="surrogate"):
            sandbox_box._toml_str("/tmp/\ud800bad")

        # LITELLM_API_KEY activates openrouter egress profile.
        assert "openrouter" in sandbox_box._providers_from_env(
            {"LITELLM_API_KEY": "sk-lt"}
        )

        # Unset XDG_CONFIG_HOME / XDG_CACHE_HOME default to host config/cache parents.
        repo = tmp_path / "repo"
        repo.mkdir()
        rt = resolve_runtime_paths(repo, home=tmp_path)
        env_default = sandbox_box._render_agent_env(
            runtime=rt,
            providers=["anthropic"],
            aws_region="us-west-2",
            env={"PATH": "/usr/bin:/bin"},
        )
        assert env_default["XDG_CONFIG_HOME"] == str(rt["code_cfg"].parent)
        assert env_default["XDG_CACHE_HOME"] == str(rt["code_cache"].parent)

        # AppArmor sysctl OSError fails closed.
        bad_sysctl = tmp_path / "sysctl_dir"
        bad_sysctl.mkdir()
        chk = sandbox_box._check_apparmor(bad_sysctl, tmp_path / "missing_prof")
        assert chk.ok is False

        # 3-ancestor symlink in strands-box root & custom policy symlink caught by box doctor & run.
        real_root = tmp_path / "real_sbx"
        real_root.mkdir()
        sym_root = tmp_path / "strands-box"
        sym_root.symlink_to(real_root)
        nested = sym_root / "repos" / "demo-1234"
        nested.mkdir(parents=True)
        cfg_toml = nested / "box.toml"
        cfg_dw = nested / "policy.dw"
        cfg_dw.write_text("", encoding="utf-8")
        cfg_toml.write_text('name = "demo"\n', encoding="utf-8")
        doc_chk = sandbox_box._check_box_config(cfg_toml, cfg_dw)
        assert doc_chk.ok is False and "Symlink" in doc_chk.detail
        with pytest.raises(ValueError, match="Refusing symlink parent"):
            sandbox_box._validate_launch_config(cfg_toml)


def _assert_box_run_clean(
    box_bin: Path, box_toml: Path, cwd: Path, env: dict[str, str]
) -> None:
    import subprocess

    run_proc = subprocess.run(
        [str(box_bin), "run", "--config", str(box_toml), "--", "--help"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = run_proc.stderr or ""
    for bad in (
        "invalid credential entry",
        "will not load",
        "is refused:",
        "does not exist",
        "No such file or directory",
        "Monty answers it",
        "is invalid:",
    ):
        assert bad not in stderr, stderr
    if "this identity may not create a user namespace" in stderr:
        pytest.skip(stderr.strip().splitlines()[-1])
    assert run_proc.returncode == 0, stderr or run_proc.stdout
    assert "Usage:" in run_proc.stdout


@pytest.mark.integration
def test_host_strands_box_or_dogwood_validates_generated_policy(tmp_path):
    """Validate generated box.toml / policy.dw against host binaries when present."""
    import shutil
    import subprocess
    import tempfile

    from strands_code_cli.sandbox.box import CORE_PROVIDERS

    # Keep fake_home short so the box broker UNIX socket stays within Linux's 108-byte limit.
    with tempfile.TemporaryDirectory(prefix="sbx-") as short_tmp:
        base = Path(short_tmp)
        repo = base / "strands-code"
        cfg_dir = base / "c"
        fake_home = base / "h"
        repo.mkdir()
        fake_home.mkdir()
        dummy_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(fake_home),
            "EXPERIMENTAL_X86_SUPPORT": "TRUE",
            "AWS_ACCESS_KEY_ID": "AKIADUMMYTEST0000001",
            "AWS_SECRET_ACCESS_KEY": "dummy-secret",
            "GOOGLE_API_KEY": "dummy-google",
            "ANTHROPIC_API_KEY": "dummy-anthropic",
            "OPENAI_API_KEY": "dummy-openai",
            "MODEL_API_KEY": "dummy-meta",
            "OPENROUTER_API_KEY": "dummy-openrouter",
            "TYPESAFE_API_KEY": "dummy-typesafe",
            "JEV_API_KEY": "dummy-jev",
            "GITHUB_TOKEN": "ghp_dummy_token",
        }

        res = init_box_config(
            repo_root=repo,
            out_dir=cfg_dir,
            providers=CORE_PROVIDERS,
            allow_github_skills=True,
            home=fake_home,
            env=dummy_env,
        )
        dogwood_bin = shutil.which("dogwood")
        box_bin, _ = discover_box_binaries()
        if not dogwood_bin and box_bin is None:
            pytest.skip("Host Strands Box / Dogwood binaries not installed")

        if dogwood_bin:
            proc = subprocess.run(
                [dogwood_bin, "validate", str(res.policy_dw)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 0, proc.stderr or proc.stdout

        if box_bin is not None:
            report = run_box_doctor(
                repo_root=repo, config_path=res.box_toml, box_bin=box_bin, env=dummy_env
            )
            by_name = {c.name: c for c in report.checks}
            if "apparmor_userns" in by_name and not by_name["apparmor_userns"].ok:
                pytest.skip(by_name["apparmor_userns"].detail)

            schema_dir = tmp_path / "schema"
            schema_dir.mkdir()
            schema_proc = subprocess.run(
                [
                    str(box_bin),
                    "policy",
                    "generate-schema",
                    "--config",
                    str(res.box_toml),
                    "--output-dir",
                    str(schema_dir),
                ],
                env=dummy_env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert schema_proc.returncode == 0, schema_proc.stderr or schema_proc.stdout
            _assert_box_run_clean(box_bin, res.box_toml, repo, dummy_env)

            # Also verify self-hosting on the actual strands-code repository itself.
            self_repo = Path(__file__).resolve().parents[2]
            self_home = base / "hs"
            self_home.mkdir()
            self_env = {**dummy_env, "HOME": str(self_home)}
            self_res = init_box_config(
                repo_root=self_repo,
                out_dir=base / "cs",
                providers=("bedrock",),
                home=self_home,
                env=self_env,
            )
            _assert_box_run_clean(box_bin, self_res.box_toml, self_repo, self_env)
