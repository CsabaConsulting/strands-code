"""CLI integration & /policy status tests for ``strands-code box`` (SANDBOX-01)."""

from __future__ import annotations

from typer.testing import CliRunner

from strands_code_cli.dispatch.core import _policy_message
from strands_code_cli.entry import main as entry_main
from strands_code_cli.sandbox import box as sandbox_box
from strands_code_cli.sandbox.box import BoxDoctorCheck, BoxDoctorReport


class TestPolicyStatusBoxIndicator:
    def test_policy_and_policy_show_display_box_indicator(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("STRANDS_BOX", "1")
        out_default = _policy_message("")
        out_show = _policy_message("show")
        assert "Sandbox: Strands Box active (STRANDS_BOX=1)" in out_default
        assert "Sandbox: Strands Box active (STRANDS_BOX=1)" in out_show

    def test_policy_omits_box_indicator_when_unboxed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("STRANDS_BOX", raising=False)
        out = _policy_message("")
        assert "Strands Box active" not in out


class TestBoxCliSubcommands:
    def _forbid_preflight(self, monkeypatch) -> None:
        def _boom(*_args, **_kwargs):
            raise AssertionError("subcommand should not trigger REPL preflight")

        monkeypatch.setattr(entry_main, "_preflight_credentials", _boom)

    def test_box_init_generates_files_warns_under_repo_and_skips_preflight(
        self, tmp_path, monkeypatch
    ):
        self._forbid_preflight(monkeypatch)
        monkeypatch.chdir(tmp_path)
        out_dir = tmp_path / ".box-local"
        result = CliRunner().invoke(
            entry_main.app,
            [
                "box",
                "init",
                "--out",
                str(out_dir),
                "--provider",
                "bedrock",
                "--provider",
                "openai",
                "--region",
                "us-west-2",
                "--aws-profile",
                "dev",
                "--allow-decisions-api",
                "--allow-github-skills",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (out_dir / "box.toml").is_file()
        assert (out_dir / "policy.dw").is_file()
        assert "bedrock, openai" in result.output
        assert "Warning:" in result.output
        toml_text = (out_dir / "box.toml").read_text(encoding="utf-8")
        assert "bedrock-runtime.us-west-2.amazonaws.com" in toml_text
        assert "api.openai.com" in toml_text
        assert "api.github.com" in toml_text

    def test_box_init_rejects_unknown_provider_with_exit_1(self, tmp_path, monkeypatch):
        self._forbid_preflight(monkeypatch)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            entry_main.app,
            ["box", "init", "--out", str(tmp_path / "cfg"), "--provider", "bogus"],
        )
        assert result.exit_code == 1
        assert "Unknown provider 'bogus'" in result.output

    def test_box_doctor_returns_zero_when_ready(self, monkeypatch):
        self._forbid_preflight(monkeypatch)
        monkeypatch.setattr(
            sandbox_box,
            "run_box_doctor",
            lambda **_kw: BoxDoctorReport(
                checks=(BoxDoctorCheck("binary_layout", True, "Found all binaries"),),
                ok=True,
            ),
        )
        result = CliRunner().invoke(entry_main.app, ["box", "doctor"])
        assert result.exit_code == 0
        assert "Status: READY" in result.output

    def test_box_doctor_exits_one_with_remediation_on_failure(self, monkeypatch):
        self._forbid_preflight(monkeypatch)
        monkeypatch.setattr(
            sandbox_box,
            "run_box_doctor",
            lambda **_kw: BoxDoctorReport(
                checks=(
                    BoxDoctorCheck(
                        "apparmor_userns",
                        False,
                        "AppArmor blocks unprivileged userns",
                        "Install /etc/apparmor.d/strands-box",
                    ),
                ),
                ok=False,
            ),
        )
        result = CliRunner().invoke(entry_main.app, ["box", "doctor"])
        assert result.exit_code == 1
        assert "Status: ACTION REQUIRED" in result.output
        assert "/etc/apparmor.d/strands-box" in result.output

    def test_box_run_forwards_extra_args_after_double_dash(self, tmp_path, monkeypatch):
        self._forbid_preflight(monkeypatch)
        recorded: dict[str, object] = {}

        def _fake_launch(extra_args, **kwargs):
            recorded["extra_args"] = list(extra_args)
            recorded["kwargs"] = kwargs
            return 0, ["Enabled EXPERIMENTAL_X86_SUPPORT=TRUE for Linux x86_64."]

        monkeypatch.setattr(sandbox_box, "launch_box_run", _fake_launch)
        cfg = tmp_path / "box.toml"
        result = CliRunner().invoke(
            entry_main.app,
            [
                "box",
                "run",
                "--config",
                str(cfg),
                "--",
                "--codeact",
                "--model",
                "google/gemini-3.8-flash",
            ],
        )
        assert result.exit_code == 0, result.output
        assert recorded["extra_args"] == [
            "--codeact",
            "--model",
            "google/gemini-3.8-flash",
        ]
        assert recorded["kwargs"] == {"config_path": cfg, "box_bin": None}
        assert "EXPERIMENTAL_X86_SUPPORT=TRUE" in result.output

    def test_box_run_propagates_nonzero_exit_and_value_error(self, monkeypatch):
        self._forbid_preflight(monkeypatch)
        monkeypatch.setattr(
            sandbox_box,
            "launch_box_run",
            lambda *_a, **_kw: (2, []),
        )
        rc_res = CliRunner().invoke(entry_main.app, ["box", "run"])
        assert rc_res.exit_code == 2

        def _missing(*_a, **_kw):
            raise ValueError("Box config not found")

        monkeypatch.setattr(sandbox_box, "launch_box_run", _missing)
        err_res = CliRunner().invoke(entry_main.app, ["box", "run"])
        assert err_res.exit_code == 1
        assert "Box config not found" in err_res.output

    def test_root_repl_still_launches_without_subcommand(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        seen_build: list[tuple[object, ...]] = []
        seen_loop: list[dict[str, object]] = []
        monkeypatch.setattr(
            entry_main, "_preflight_credentials", lambda *_a, **_kw: None
        )
        monkeypatch.setattr(
            entry_main,
            "model_for_config",
            lambda *_a, **_kw: object(),
        )
        monkeypatch.setattr(
            entry_main,
            "build_agent",
            lambda *args, **kw: seen_build.append(args) or object(),
        )
        monkeypatch.setattr(
            entry_main,
            "run_loop",
            lambda *args, **kw: seen_loop.append(kw),
        )

        res = CliRunner().invoke(
            entry_main.app, ["--codeact", "code", "--model", "openai/gpt-4o"]
        )
        assert res.exit_code == 0, res.output
        assert len(seen_build) == 1
        assert len(seen_loop) == 1
        assert seen_loop[0]["codeact"] == "code"
        assert seen_loop[0]["model_id"] == "openai/gpt-4o"
