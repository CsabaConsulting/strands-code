"""Hermetic tests for Strands Box config, egress profiles, Dogwood policy, and diagnostics."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomllib

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
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda app: str(cfg_root / app)
        )
        monkeypatch.setattr(
            "platformdirs.user_data_dir", lambda app: str(data_root / app)
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
        read_strs = [str(p) for p in paths["read"]]
        assert str(repo.resolve()) in read_strs
        assert str((repo / ".venv").resolve()) in read_strs
        assert str(uv_py.parent.parent.resolve()) in read_strs
        assert str((home / ".local" / "share" / "uv" / "python").resolve()) in read_strs

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
        assert env_tbl["HOME"] == str(home)
        assert str((repo / ".venv" / "bin").resolve()) in env_tbl["PATH"]
        assert parsed["agent"]["filesystem"]["read_file"] == [
            "/etc/hosts",
            "/etc/nsswitch.conf",
        ]

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
            env={"MODEL_API_KEY": "x"},
        )
        assert set(detected) == {"google", "anthropic", "openai", "meta", "typesafe"}
        assert "decisions_api" not in detected
        assert "github_skills" not in detected

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
        assert egress["anthropic"]["secret"]["header"] == "x-api-key"
        assert egress["anthropic"]["secret"]["prefix"] == ""
        assert egress["openai"]["destinations"] == ["api.openai.com"]
        assert egress["meta"]["destinations"] == ["api.meta.ai"]
        assert egress["openrouter"]["destinations"] == [
            "openrouter.ai/api/v1/chat/*",
            "openrouter.ai/api/alpha/decisions",
        ]
        assert egress["typesafe"]["destinations"] == ["api.typesafe.ai"]
        assert egress["decisions_api"]["destinations"] == ["decisionapi.net"]
        assert egress["github_api"]["destinations"] == ["api.github.com"]
        assert egress["github_api"]["secret"]["ref"] == "env://GITHUB_TOKEN"
        assert egress["github_downloads"]["destinations"] == [
            "codeload.github.com",
            "objects.githubusercontent.com",
        ]
        assert "secret" not in egress["github_downloads"]

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
        parsed = tomllib.loads(res.box_toml.read_text(encoding="utf-8"))
        tools = parsed["tool"]
        for tool_name in ("git", "pytest", "rg", "ruff", "uv", "python"):
            assert tool_name in tools
            assert tools[tool_name]["command"]

        dw = res.policy_dw.read_text(encoding="utf-8")
        assert 'action == Box::Action::"net:connect"' in dw
        assert 'action == Box::Action::"http:request"' in dw
        assert 'context.input.path like "/api/v1/chat/*"' in dw
        assert 'context.input.path like "*/.env"' in dw
        assert 'context.input.path like "*/.env.*"' in dw
        assert 'context.input.path like "*/.ssh/*"' in dw
        assert 'context.input.path like "*/.aws/*"' in dw
        assert "when temporal {" in dw
        assert "formerly within 900s" in dw
        assert 'context.input.command == "pytest"' in dw
        assert 'context.input.args like "push*"' in dw
        assert "scoped revisit of v1.0 D-05" in dw


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


@pytest.mark.integration
def test_host_strands_box_or_dogwood_validates_generated_policy(tmp_path):
    """Validate generated box.toml / policy.dw against host binaries when present."""
    import shutil
    import subprocess

    from strands_code_cli.sandbox.box import CORE_PROVIDERS

    repo = tmp_path / "repo"
    cfg_dir = tmp_path / "box-cfg"
    fake_home = tmp_path / "home"
    repo.mkdir()
    fake_home.mkdir()

    res = init_box_config(
        repo_root=repo,
        out_dir=cfg_dir,
        providers=CORE_PROVIDERS,
        home=fake_home,
        env={},
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
            repo_root=repo, config_path=res.box_toml, box_bin=box_bin
        )
        by_name = {c.name: c for c in report.checks}
        if "apparmor_userns" in by_name and not by_name["apparmor_userns"].ok:
            pytest.skip(by_name["apparmor_userns"].detail)
        rc, _ = launch_box_run(
            ["--help"], repo_root=repo, config_path=res.box_toml, box_bin=box_bin
        )
        assert rc == 0
