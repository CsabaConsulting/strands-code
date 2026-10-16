"""Phase 11 tracer + /codeact interface-toggle tests (TOOL-07; offline only).

Tracer observations (11-01-PLAN.md task 1, all offline, no live model):

- The toggle-to-turn pipeline is three pure seams: ``dispatch``
  flips the loop-owned holder, ``resolve_turn_interface`` fixes the
  turn's interface at send (D-14/D-19), and ``shape_turn_text`` plus
  ``codeact_label`` shape the turn and its transcript line (D-15).
- ``both`` runs tool-shaped until per-ask routing lands (11-02):
  the holder accepts it, turn setup resolves it to ``tool``.
- Interface records ride a loop-owned parallel list, never the
  ``session_turns`` rows (D-16) — cost rows stay byte-identical.

Invariants pinned here: tool-calling default with CodeAct never
mandatory; one interface per turn fixed at send; every turn labeled;
zero history mutation on switch; zero cost-row change.
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from strands_code_cli.codeact import (
    CODEACT_BOTH_REPLY,
    CODEACT_CODE_REPLY,
    CODEACT_PREFIX,
    CODEACT_TOOL_REPLY,
    CODEACT_USAGE,
    CodeactState,
    codeact_label,
    resolve_initial_interface,
    resolve_turn_interface,
    shape_turn_text,
)
from strands_code_cli.provider_config import ProviderConfig
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import BUILTIN_SLASH_HEADS, SkillIndex


CODEACT_BANNED_VOCAB = (
    "Mode:",
    "plan mode",
    "act mode",
    "policy rule",
    "rule [",
    "approve-each",
    "on-demand",
    "/diff",
    "yolo",
)


class _Summary:
    """Minimal response double exposing metrics.get_summary()."""

    def __init__(self, in_tok: int, out_tok: int):
        self._summary = {
            "accumulated_usage": {"inputTokens": in_tok, "outputTokens": out_tok},
            "total_cycles": 1,
            "total_duration": 0.5,
        }

    @property
    def metrics(self):
        outer = self

        class _Metrics:
            def get_summary(self):
                return dict(outer._summary)

        return _Metrics()


def _write_skill(skills_dir: Path, name: str) -> Path:
    """Build one ``<name>/SKILL.md`` fixture tree under skills_dir."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Does something useful.\n---\n# Instructions\n",
        encoding="utf-8",
    )
    return skill_dir


def _loop_source() -> str:
    return (
        Path(__file__).resolve().parent.parent / "strands_code_cli" / "loop.py"
    ).read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Holder
# ----------------------------------------------------------------------


class TestCodeactState:
    def test_fresh_holder_defaults_to_tool(self):
        assert CodeactState().interface == "tool"

    def test_valid_values(self):
        assert CodeactState.VALID == ("tool", "code", "both")

    def test_init_each_value(self):
        for value in CodeactState.VALID:
            assert CodeactState(initial=value).interface == value

    def test_init_unknown_raises(self):
        try:
            CodeactState(initial="turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_set_each_value_announces_and_flips(self):
        holder = CodeactState()
        assert holder.set("code") == CODEACT_CODE_REPLY
        assert holder.interface == "code"
        assert holder.set("both") == CODEACT_BOTH_REPLY
        assert holder.interface == "both"
        assert holder.set("tool") == CODEACT_TOOL_REPLY
        assert holder.interface == "tool"

    def test_set_unknown_raises_and_keeps_value(self):
        holder = CodeactState(initial="code")
        try:
            holder.set("turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")
        assert holder.interface == "code"

    def test_announce_reports_current(self):
        assert CodeactState(initial="tool").announce() == CODEACT_TOOL_REPLY
        assert CodeactState(initial="code").announce() == CODEACT_CODE_REPLY
        assert CodeactState(initial="both").announce() == CODEACT_BOTH_REPLY

    def test_replies_use_interface_vocabulary_only(self):
        for copy in (CODEACT_TOOL_REPLY, CODEACT_CODE_REPLY, CODEACT_BOTH_REPLY):
            for banned in CODEACT_BANNED_VOCAB:
                assert banned not in copy


# ----------------------------------------------------------------------
# Router: /codeact branch
# ----------------------------------------------------------------------


class TestRouterCodeact:
    def _dispatch(self, text: str, tmp_path, interface=None):  # type: ignore[no-untyped-def]
        index = SessionIndex(tmp_path / "index")
        return dispatch(text, session_id="s", index=index, interface=interface)

    def test_codeact_bare_reports_current(self, tmp_path):
        holder = CodeactState()
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_TOOL_REPLY)
        holder.set("code")
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_CODE_REPLY)
        holder.set("both")
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_BOTH_REPLY)

    def test_codeact_switch_names_code_and_sticks(self, tmp_path):
        holder = CodeactState()
        action, message = self._dispatch("/codeact code", tmp_path, holder)
        assert action == "reply"
        assert "code" in message
        assert holder.interface == "code"

    def test_codeact_switch_each_value(self, tmp_path):
        holder = CodeactState()
        for verb, reply in (
            ("tool", CODEACT_TOOL_REPLY),
            ("code", CODEACT_CODE_REPLY),
            ("both", CODEACT_BOTH_REPLY),
        ):
            assert self._dispatch(f"/codeact {verb}", tmp_path, holder) == ("reply", reply)
            assert holder.interface == verb

    def test_codeact_bogus_usage_never_agent_turn(self, tmp_path):
        holder = CodeactState(initial="code")
        action, message = self._dispatch("/codeact turbo", tmp_path, holder)
        assert action == "reply"
        assert message == CODEACT_USAGE
        assert holder.interface == "code"

    def test_codeact_without_holder_replies_tool_default(self, tmp_path):
        assert self._dispatch("/codeact", tmp_path, None) == ("reply", CODEACT_TOOL_REPLY)
        action, message = self._dispatch("/codeact bogus", tmp_path, None)
        assert action == "reply"
        assert message == CODEACT_USAGE

    def test_codeact_never_starts_agent_turn(self, tmp_path):
        holder = CodeactState()
        for text in ("/codeact", "/codeact tool", "/codeact code", "/codeact both", "/codeact nope"):
            action, _ = self._dispatch(text, tmp_path, holder)
            assert action == "reply"

    def test_usage_hint_lists_codeact(self):
        assert "/codeact [tool|code|both]" in USAGE_HINT

    def test_codeact_is_builtin_head(self):
        assert "codeact" in BUILTIN_SLASH_HEADS

    def test_codeact_beats_shadowed_skill(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "codeact")
        skills = SkillIndex(skills_dir)
        assert skills.warnings  # shadow warning automatic (T-11-03)
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/codeact code", session_id="s", index=index, skills=skills, interface=holder
        )
        assert action == "reply"
        assert message == CODEACT_CODE_REPLY
        assert holder.interface == "code"


# ----------------------------------------------------------------------
# Turn setup: fix-at-send + prefix shaping
# ----------------------------------------------------------------------


class TestTurnSetup:
    def test_resolve_each_holder_value(self):
        assert resolve_turn_interface("tool") == "tool"
        assert resolve_turn_interface("code") == "code"
        # Both runs tool-shaped until per-ask routing lands (11-02).
        assert resolve_turn_interface("both") == "tool"

    def test_resolve_unknown_raises(self):
        try:
            resolve_turn_interface("turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_code_turn_prepends_prefix(self):
        shaped = shape_turn_text("code", "list the files")
        assert shaped == f"{CODEACT_PREFIX}\n\nlist the files"

    def test_tool_turn_byte_identical(self):
        text = "list the files"
        shaped = shape_turn_text("tool", text)
        assert shaped == text
        assert shaped is text
        assert CODEACT_PREFIX not in shaped

    def test_fix_at_send_snapshot(self):
        holder = CodeactState(initial="code")
        resolved = resolve_turn_interface(holder.interface)
        holder.set("tool")  # a later flip must not move the fixed turn
        assert resolved == "code"
        assert shape_turn_text(resolved, "go").startswith(CODEACT_PREFIX)


# ----------------------------------------------------------------------
# Prefix content + vocabulary
# ----------------------------------------------------------------------


class TestCodeactPrefix:
    def test_prefix_names_execution_surface(self):
        for name in ("python_repl", "read", "write", "edit", "shell"):
            assert name in CODEACT_PREFIX

    def test_prefix_states_paths_and_scope(self):
        assert "absolute paths" in CODEACT_PREFIX
        assert "working directory" in CODEACT_PREFIX
        assert "/tmp" in CODEACT_PREFIX

    def test_prefix_states_one_interface_per_turn(self):
        assert "one interface per turn" in CODEACT_PREFIX.lower()

    def test_prefix_vocabulary_lock(self):
        lowered = CODEACT_PREFIX.lower()
        for banned in ("policy", "approve-each", "on-demand", "auto", "yolo", "plan mode"):
            assert banned not in lowered


# ----------------------------------------------------------------------
# Labels
# ----------------------------------------------------------------------


class TestCodeactLabel:
    def test_exact_label_lines(self):
        assert codeact_label("code") == "interface: codeact"
        assert codeact_label("tool") == "interface: tool"


# ----------------------------------------------------------------------
# History + cost rows untouched
# ----------------------------------------------------------------------


class TestCodeactHistory:
    def test_switch_leaves_history_byte_identical(self, tmp_path):
        holder = CodeactState()
        agent = SimpleNamespace(
            messages=[
                {"role": "user", "content": [{"text": "q"}]},
                {"role": "assistant", "content": [{"text": "a"}]},
            ]
        )
        before = copy.deepcopy(agent.messages)
        index = SessionIndex(tmp_path / "index")
        for verb in ("code", "both", "tool"):
            dispatch("/codeact " + verb, session_id="s", index=index, agent=agent, interface=holder)
        assert agent.messages == before


class TestCodeactCostRows:
    def test_session_turn_row_keys_unchanged(self):
        from strands_code_cli.loop import record_turn_metrics

        turns: list = []
        record_turn_metrics(_Summary(1000, 200), "bedrock/x-model", turns)
        assert len(turns) == 1
        assert set(turns[0]) == {"turn", "input_tokens", "output_tokens", "model"}
        assert "interface" not in turns[0]


# ----------------------------------------------------------------------
# Tracer: toggle -> shaped turn -> label, end to end
# ----------------------------------------------------------------------


class TestTracer:
    def test_codeact_code_to_shaped_turn_to_label(self, tmp_path):
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/codeact code", session_id="s", index=index, interface=holder
        )
        assert action == "reply"
        assert holder.interface == "code"
        turn = resolve_turn_interface(holder.interface)
        shaped = shape_turn_text(turn, "list the files")
        label = codeact_label(turn)
        assert shaped.startswith(CODEACT_PREFIX)
        transcript = f"{message}\n{label}"
        assert transcript.count("interface: codeact") == 1
        assert "interface: tool" not in transcript

    def test_default_tool_turn_unshaped_with_tool_label(self, tmp_path):
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch("/codeact", session_id="s", index=index, interface=holder)
        assert action == "reply"
        assert holder.interface == "tool"
        turn = resolve_turn_interface(holder.interface)
        ask = "list the files"
        assert shape_turn_text(turn, ask) == ask
        transcript = f"{message}\n{codeact_label(turn)}"
        assert transcript.count("interface: tool") == 1
        assert "interface: codeact" not in transcript


# ----------------------------------------------------------------------
# Startup surfaces: --codeact flag, config keys, remember-last (task 2)
# ----------------------------------------------------------------------


class TestCodeactStartupFlag:
    def _invoke(self, main_module, args):  # type: ignore[no-untyped-def]
        from typer.testing import CliRunner

        return CliRunner().invoke(main_module.app, args)

    def test_flag_each_value_reaches_run_loop(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.main")
        monkeypatch.chdir(tmp_path)  # real SessionIndex must not touch the repo
        for value in ("tool", "code", "both"):
            with (
                patch.object(main_module, "_preflight_credentials", return_value=None),
                patch.object(main_module, "build_agent", return_value=object()),
                patch.object(main_module, "run_loop") as loop,
            ):
                result = self._invoke(main_module, ["--codeact", value])
            assert result.exit_code == 0, result.output
            assert loop.call_args[1]["codeact"] == value

    def test_no_flag_passes_none(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.main")
        monkeypatch.chdir(tmp_path)
        with (
            patch.object(main_module, "_preflight_credentials", return_value=None),
            patch.object(main_module, "build_agent", return_value=object()),
            patch.object(main_module, "run_loop") as loop,
        ):
            result = self._invoke(main_module, [])
        assert result.exit_code == 0, result.output
        assert loop.call_args[1]["codeact"] is None

    @pytest.mark.parametrize("bad", ["turbo", "CODE", ""])
    def test_invalid_flag_rejected_before_side_effects(self, tmp_path, monkeypatch, bad):
        main_module = importlib.import_module("strands_code_cli.main")
        monkeypatch.chdir(tmp_path)
        with (
            patch.object(
                main_module, "_preflight_credentials", side_effect=AssertionError("gate runs")
            ),
            patch.object(main_module, "build_agent", side_effect=AssertionError("build runs")),
            patch.object(main_module, "run_loop", side_effect=AssertionError("loop runs")),
            patch.object(ProviderConfig, "load", side_effect=AssertionError("config loads")),
        ):
            result = self._invoke(main_module, ["--codeact", bad])
        assert result.exit_code != 0
        assert "codeact" in result.output.lower()
        assert not Path(".agent").exists()

    def test_bare_flag_at_end_implies_code(self):
        main_module = importlib.import_module("strands_code_cli.main")
        assert main_module._expand_bare_codeact(["p", "--codeact"]) == [
            "p",
            "--codeact",
            "code",
        ]

    def test_bare_flag_before_other_flag_implies_code(self):
        main_module = importlib.import_module("strands_code_cli.main")
        assert main_module._expand_bare_codeact(
            ["p", "--codeact", "--session-id", "x"]
        ) == ["p", "--codeact", "code", "--session-id", "x"]

    @pytest.mark.parametrize(
        "argv", [["p", "--codeact", "both"], ["p", "--codeact=tool"]]
    )
    def test_valued_and_equals_forms_untouched(self, argv):
        main_module = importlib.import_module("strands_code_cli.main")
        assert main_module._expand_bare_codeact(argv) == argv

    def test_sentinel_stops_expansion(self):
        main_module = importlib.import_module("strands_code_cli.main")
        assert main_module._expand_bare_codeact(["p", "--", "--codeact"]) == [
            "p",
            "--",
            "--codeact",
        ]

    def test_helper_never_mutates_input(self):
        main_module = importlib.import_module("strands_code_cli.main")
        argv = ["p", "--codeact"]
        main_module._expand_bare_codeact(argv)
        assert argv == ["p", "--codeact"]

    def test_main_expands_bare_flag_to_code(self, tmp_path, monkeypatch):
        main_module = importlib.import_module("strands_code_cli.main")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["strands-code", "--codeact"])
        with (
            patch.object(main_module, "_preflight_credentials", return_value=None),
            patch.object(main_module, "build_agent", return_value=object()),
            patch.object(main_module, "run_loop") as loop,
        ):
            with pytest.raises(SystemExit) as exc:
                main_module.main()
        assert exc.value.code == 0
        assert loop.call_args[1]["codeact"] == "code"


class TestCodeactStartupConfig:
    def test_keys_round_trip(self, tmp_path):
        path = tmp_path / "config.yaml"
        cfg = ProviderConfig(
            model="m", base_url="http://x", codeact="code", codeact_remember=True
        )
        cfg.save(path)
        assert ProviderConfig.load(path) == cfg

    def test_missing_config_yields_defaults(self, tmp_path):
        loaded = ProviderConfig.load(tmp_path / "missing.yaml")
        assert loaded.codeact is None
        assert loaded.codeact_remember is False

    def test_defaults_not_persisted(self, tmp_path):
        path = tmp_path / "config.yaml"
        ProviderConfig(model="m").save(path)
        assert "codeact" not in path.read_text(encoding="utf-8")
        assert ProviderConfig.load(path).codeact_remember is False

    def test_unknown_codeact_value_raises(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("codeact: turbo\n", encoding="utf-8")
        with pytest.raises(ValueError, match="tool\\|code\\|both"):
            ProviderConfig.load(path)
        with pytest.raises(ValueError, match="tool\\|code\\|both"):
            ProviderConfig(codeact="turbo").save(tmp_path / "out.yaml")

    @pytest.mark.parametrize("word", ["'yes'", "1"])
    def test_non_bool_remember_raises(self, tmp_path, word):
        path = tmp_path / "config.yaml"
        path.write_text(f"codeact_remember: {word}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a bool"):
            ProviderConfig.load(path)
        with pytest.raises(ValueError, match="must be a bool"):
            ProviderConfig(codeact_remember="yes").save(tmp_path / "out.yaml")  # type: ignore[arg-type]

    @pytest.mark.parametrize("word,expected", [("true", True), ("false", False)])
    def test_bool_spellings_accepted(self, tmp_path, word, expected):
        path = tmp_path / "config.yaml"
        path.write_text(f"codeact_remember: {word}\n", encoding="utf-8")
        assert ProviderConfig.load(path).codeact_remember is expected


class TestCodeactStartupPrecedence:
    def test_flag_wins_over_remembered(self):
        assert resolve_initial_interface("code", "tool", True) == "code"

    def test_remembered_wins_over_default(self):
        assert resolve_initial_interface(None, "code", True) == "code"

    def test_saved_ignored_unless_remembered(self):
        assert resolve_initial_interface(None, "code", False) == "tool"

    def test_remember_without_saved_starts_tool(self):
        assert resolve_initial_interface(None, None, True) == "tool"

    def test_default_tool_session_start(self):
        assert resolve_initial_interface(None, None, False) == "tool"

    def test_missing_config_starts_tool(self, tmp_path):
        loaded = ProviderConfig.load(tmp_path / "missing.yaml")
        initial = resolve_initial_interface(None, loaded.codeact, loaded.codeact_remember)
        assert initial == "tool"

    def test_invalid_values_raise(self):
        with pytest.raises(ValueError, match="tool\\|code\\|both"):
            resolve_initial_interface("turbo", None, False)
        with pytest.raises(ValueError, match="tool\\|code\\|both"):
            resolve_initial_interface(None, "turbo", True)


class TestCodeactStartupPersist:
    def test_save_choice_persists_and_keeps_other_keys(self, tmp_path):
        path = tmp_path / "config.yaml"
        cfg = ProviderConfig(model="m", base_url="http://x", codeact_remember=True)
        cfg.save(path)
        cfg.save_codeact_choice("both", path)
        loaded = ProviderConfig.load(path)
        assert loaded.codeact == "both"
        assert loaded.model == "m"
        assert loaded.base_url == "http://x"
        assert loaded.codeact_remember is True

    def test_save_choice_invalid_raises(self, tmp_path):
        with pytest.raises(ValueError, match="tool\\|code\\|both"):
            ProviderConfig().save_codeact_choice("turbo", tmp_path / "out.yaml")

    def test_switch_persists_last_choice(self, tmp_path, monkeypatch):
        import strands_code_cli.provider_config as provider_config_module

        path = tmp_path / "config.yaml"
        monkeypatch.setattr(provider_config_module, "default_config_path", lambda: path)
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        dispatch("/codeact code", session_id="s", index=index, interface=holder)
        # The loop's persist line: save the flipped holder value.
        provider_config_module.ProviderConfig.load().save_codeact_choice(holder.interface)
        assert provider_config_module.ProviderConfig.load().codeact == "code"

    def test_loop_wires_codeact_startup(self):
        source = _loop_source()
        assert "codeact: str | None = None," in source
        assert "resolve_initial_interface(" in source

    def test_loop_wires_codeact_persist(self):
        source = _loop_source()
        assert "codeact_before = interface.interface" in source
        assert "save_codeact_choice(interface.interface)" in source


def _codeact_source() -> str:
    return (
        Path(__file__).resolve().parent.parent / "strands_code_cli" / "codeact.py"
    ).read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Stint lifecycle + sync interior file/shell functions (11-02 task 1)
# ----------------------------------------------------------------------


class TestCodeactStintLifecycle:
    def test_lazy_until_first_use(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        assert stint._interpreter is None
        stint.reset()  # a never-built stint stays unbuilt, no error
        assert stint._interpreter is None

    def test_bare_name_write_then_read_back(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stdout, stderr = stint.execute_code("write('n.txt','hi')")
        assert stderr == ""
        assert (tmp_path / "n.txt").read_text(encoding="utf-8") == "hi"
        stdout, stderr = stint.execute_code("print(read('n.txt'))")
        assert stderr == ""
        assert "hi" in stdout

    def test_write_confirms_naming_path(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stdout, _ = stint.execute_code("print(write('sub/n.txt','hi'))")
        assert "n.txt" in stdout
        assert (tmp_path / "sub" / "n.txt").read_text(encoding="utf-8") == "hi"

    def test_state_persists_across_calls(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stint.execute_code("stint_var = 41")
        stdout, stderr = stint.execute_code("print(stint_var + 1)")
        assert stderr == ""
        assert "42" in stdout

    def test_reset_clears_stint_state(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stint.execute_code("stint_var = 41")
        stint.reset()
        _, stderr = stint.execute_code("print(stint_var)")
        assert "not defined" in stderr

    def test_reset_keeps_bare_names_usable(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stint.execute_code("write('n.txt','hi')")
        stint.reset()
        stdout, stderr = stint.execute_code("print(read('n.txt'))")
        assert stderr == ""
        assert "hi" in stdout

    def test_os_import_fails_closed(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        _, stderr = stint.execute_code("import os")
        assert "not allowed" in stderr

    def test_subprocess_import_fails_closed(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        _, stderr = stint.execute_code("import subprocess")
        assert "not allowed" in stderr

    def test_math_import_works(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stdout, stderr = stint.execute_code("import math\nprint(math.floor(3.7))")
        assert stderr == ""
        assert "3" in stdout

    def test_allowlist_pinned_to_math(self, tmp_path):
        from strands_code_cli.codeact import CODEACT_AUTHORIZED_IMPORTS, CodeactStint

        assert CODEACT_AUTHORIZED_IMPORTS == frozenset({"math"})
        stint = CodeactStint(cwd=tmp_path)
        stint.execute_code("pass")
        assert stint._interpreter is not None
        assert stint._interpreter.authorized_imports == frozenset({"math"})
        assert stint._interpreter.timeout_seconds == 60

    def test_tool_property_built_once(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        first = stint.tool
        assert first.tool_name == "python_repl"
        assert stint.tool is first

    def test_out_of_scope_write_returns_refusal(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stdout, stderr = stint.execute_code(
            "print(write('/definitely-outside-scope-x/n.txt','hi'))"
        )
        assert stderr == ""
        assert "outside the allowed roots" in stdout

    def test_shell_runs_argv(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        stint = CodeactStint(cwd=tmp_path)
        stdout, stderr = stint.execute_code("print(shell(['echo','hi']))")
        assert stderr == ""
        assert "hi" in stdout

    def test_no_shell_true_in_module(self):
        assert "shell=True" not in _codeact_source()

    def test_no_prompt_dialog_stdin_on_execution_path(self):
        source = _codeact_source().lower()
        for symbol in ("prompt", "dialog", "stdin"):
            assert symbol not in source

    def test_loop_owns_stint_and_resets_on_switch(self):
        source = _loop_source()
        assert "CodeactStint(cwd=" in source
        assert "stint.reset()" in source


class TestCodeactInteriorFunctions:
    def test_read_missing_returns_not_found(self, tmp_path):
        from strands_code_cli.codeact import codeact_read

        assert "not found" in codeact_read(tmp_path, "missing.txt").lower()

    def test_read_out_of_scope_returns_refusal(self, tmp_path):
        from strands_code_cli.codeact import codeact_read

        result = codeact_read(tmp_path, "/definitely-outside-scope-x/n.txt")
        assert "outside the allowed roots" in result

    def test_write_creates_parents_and_confirms(self, tmp_path):
        from strands_code_cli.codeact import codeact_write

        result = codeact_write(tmp_path, "a/b/n.txt", "hi")
        assert "n.txt" in result
        assert (tmp_path / "a" / "b" / "n.txt").read_text(encoding="utf-8") == "hi"

    def test_edit_replaces_first_occurrence_only(self, tmp_path):
        from strands_code_cli.codeact import codeact_edit, codeact_write

        codeact_write(tmp_path, "n.txt", "aa bb aa")
        result = codeact_edit(tmp_path, "n.txt", "aa", "zz")
        assert "n.txt" in result
        assert (tmp_path / "n.txt").read_text(encoding="utf-8") == "zz bb aa"

    def test_edit_absent_match_reports(self, tmp_path):
        from strands_code_cli.codeact import codeact_edit, codeact_write

        codeact_write(tmp_path, "n.txt", "hi")
        result = codeact_edit(tmp_path, "n.txt", "zzz", "yy")
        assert "No match" in result
        assert (tmp_path / "n.txt").read_text(encoding="utf-8") == "hi"

    def test_edit_missing_file_reports(self, tmp_path):
        from strands_code_cli.codeact import codeact_edit

        assert "not found" in codeact_edit(tmp_path, "missing.txt", "a", "b").lower()

    def test_interior_functions_never_raise(self, tmp_path):
        from strands_code_cli.codeact import (
            codeact_edit,
            codeact_read,
            codeact_shell,
            codeact_write,
        )

        # Every out-of-scope / malformed call returns a string, never raises.
        assert isinstance(codeact_read(tmp_path, "/nope-x/n.txt"), str)
        assert isinstance(codeact_write(tmp_path, "/nope-x/n.txt", "x"), str)
        assert isinstance(codeact_edit(tmp_path, "/nope-x/n.txt", "a", "b"), str)
        assert isinstance(codeact_shell(tmp_path, "echo hi"), str)  # type: ignore[arg-type]
        assert isinstance(codeact_shell(tmp_path, []), str)

    def test_shell_string_refused(self, tmp_path):
        from strands_code_cli.codeact import codeact_shell

        assert "argv list" in codeact_shell(tmp_path, "echo hi")  # type: ignore[arg-type]

    def test_shell_labels_stdout_and_stderr(self, tmp_path):
        from strands_code_cli.codeact import codeact_shell

        result = codeact_shell(tmp_path, ["echo", "hi"])
        assert "STDOUT:" in result
        assert "hi" in result

    def test_shell_missing_command_reports(self, tmp_path):
        from strands_code_cli.codeact import codeact_shell

        result = codeact_shell(tmp_path, ["codeact-no-such-cmd-xyz"])
        assert "not found" in result.lower()

    def test_shell_runs_under_stint_cwd(self, tmp_path):
        from strands_code_cli.codeact import codeact_shell

        (tmp_path / "marker.txt").write_text("m", encoding="utf-8")
        result = codeact_shell(tmp_path, ["ls", "marker.txt"])
        assert "marker.txt" in result


class _FakeRegistry:
    """ToolRegistry double exposing replace plus a registry mapping."""

    def __init__(self, default_tool):
        self.registry = {"python_repl": default_tool}
        self.calls: list = []

    def replace(self, new_tool):
        self.calls.append(new_tool)
        self.registry["python_repl"] = new_tool


def _fake_agent(default_tool):
    return SimpleNamespace(tool_registry=_FakeRegistry(default_tool))


# ----------------------------------------------------------------------
# Per-turn python_repl swap onto the stint (11-02 task 2)
# ----------------------------------------------------------------------


class TestCodeactSwap:
    def test_turn_setup_code_turn_swaps_then_restores(self):
        from strands_code_cli.codeact import restore_after_turn, swap_for_code_turn

        default_tool, stint_tool = object(), object()
        agent = _fake_agent(default_tool)
        swapped = swap_for_code_turn(agent, "code", stint_tool, default_tool)
        assert swapped is True
        assert agent.tool_registry.registry["python_repl"] is stint_tool
        restore_after_turn(agent, swapped, default_tool)
        assert agent.tool_registry.calls == [stint_tool, default_tool]
        assert agent.tool_registry.registry["python_repl"] is default_tool

    def test_turn_setup_tool_turn_never_swaps(self):
        from strands_code_cli.codeact import restore_after_turn, swap_for_code_turn

        default_tool, stint_tool = object(), object()
        agent = _fake_agent(default_tool)
        swapped = swap_for_code_turn(agent, "tool", stint_tool, default_tool)
        assert swapped is False
        restore_after_turn(agent, swapped, default_tool)
        assert agent.tool_registry.calls == []
        assert agent.tool_registry.registry["python_repl"] is default_tool

    def test_turn_setup_missing_default_skips_swap(self):
        from strands_code_cli.codeact import restore_after_turn, swap_for_code_turn

        agent = _fake_agent(None)
        agent.tool_registry.registry = {}
        swapped = swap_for_code_turn(agent, "code", object(), None)
        assert swapped is False
        restore_after_turn(agent, swapped, None)  # no error, no call
        assert agent.tool_registry.calls == []

    def test_turn_setup_missing_stint_tool_skips_swap(self):
        from strands_code_cli.codeact import swap_for_code_turn

        default_tool = object()
        agent = _fake_agent(default_tool)
        assert swap_for_code_turn(agent, "code", None, default_tool) is False
        assert agent.tool_registry.calls == []

    def test_turn_setup_missing_registry_skips_swap(self):
        from strands_code_cli.codeact import swap_for_code_turn

        agent = SimpleNamespace()  # no tool_registry at all
        assert swap_for_code_turn(agent, "code", object(), object()) is False

    def test_turn_setup_exception_mid_turn_still_restores(self):
        from strands_code_cli.codeact import restore_after_turn, swap_for_code_turn

        default_tool, stint_tool = object(), object()
        agent = _fake_agent(default_tool)
        swapped = swap_for_code_turn(agent, "code", stint_tool, default_tool)
        try:
            try:
                raise RuntimeError("mid-turn boom")
            finally:
                restore_after_turn(agent, swapped, default_tool)
        except RuntimeError:
            pass  # the turn failed; the boundary still restored
        assert agent.tool_registry.calls == [stint_tool, default_tool]
        assert agent.tool_registry.registry["python_repl"] is default_tool

    def test_turn_setup_default_handle_reads_registry(self):
        from strands_code_cli.codeact import default_repl_handle

        default_tool = object()
        assert default_repl_handle(_fake_agent(default_tool)) is default_tool
        assert default_repl_handle(SimpleNamespace()) is None
        bare = SimpleNamespace(tool_registry=SimpleNamespace(registry={}))
        assert default_repl_handle(bare) is None

    def test_turn_setup_restore_without_swap_is_noop(self):
        from strands_code_cli.codeact import restore_after_turn

        default_tool = object()
        agent = _fake_agent(default_tool)
        restore_after_turn(agent, False, default_tool)
        restore_after_turn(agent, True, None)
        assert agent.tool_registry.calls == []

    def test_turn_setup_loop_wires_swap_and_restore(self):
        import inspect

        import strands_code_cli.loop as loop_module

        run_source = inspect.getsource(loop_module.run_loop)
        assert "default_repl = default_repl_handle(agent)" in run_source
        assert "swapped = swap_for_code_turn(" in run_source
        assert "stint.tool if turn_interface == \"code\" else None" in run_source
        assert "restore_after_turn(agent, swapped, default_repl)" in run_source

    def test_turn_setup_side_pool_path_performs_no_swap(self):
        import inspect

        import strands_code_cli.loop as loop_module

        for name in ("_invoke_parallel", "_pump_parallel", "_route_side_spawn"):
            source = inspect.getsource(getattr(loop_module, name))
            assert "swap_for_code_turn" not in source
            assert "restore_after_turn" not in source
            assert "stint" not in source

    def test_turn_setup_no_private_registry_mutation(self):
        # Public replace() only: neither module assigns into .registry.
        for source in (_codeact_source(), _loop_source()):
            assert ".registry[" not in source
            assert "registry[" not in source
            assert ".registry =" not in source
            assert "agent.messages" not in _codeact_source()


# ----------------------------------------------------------------------
# Both-mode per-ask routing via /code and /tool (11-02 task 3)
# ----------------------------------------------------------------------


class TestCodeactBothRouting:
    def _dispatch(self, text: str, tmp_path, interface=None):  # type: ignore[no-untyped-def]
        index = SessionIndex(tmp_path / "index")
        return dispatch(text, session_id="s", index=index, interface=interface)

    def test_both_code_prefix_arms_code_for_exactly_one_turn(self, tmp_path):
        from strands_code_cli.codeact import CodeactState

        holder = CodeactState(initial="both")
        action, message = self._dispatch("/code list the files", tmp_path, holder)
        assert action == "agent"
        assert message == "list the files"
        assert holder.resolve_turn() == "code"  # the armed turn
        assert holder.resolve_turn() == "both"  # arm consumed, sticky back
        assert holder.interface == "both"  # sticky value never moves

    def test_both_tool_prefix_arms_tool(self, tmp_path):
        from strands_code_cli.codeact import CodeactState

        holder = CodeactState(initial="both")
        action, message = self._dispatch("/tool list the files", tmp_path, holder)
        assert (action, message) == ("agent", "list the files")
        assert holder.resolve_turn() == "tool"
        assert holder.resolve_turn() == "both"

    def test_both_prefixes_override_sticky_tool_and_code(self, tmp_path):
        from strands_code_cli.codeact import CodeactState

        tool_holder = CodeactState(initial="tool")
        assert self._dispatch("/code go", tmp_path, tool_holder)[0] == "agent"
        assert tool_holder.resolve_turn() == "code"
        assert tool_holder.resolve_turn() == "tool"
        code_holder = CodeactState(initial="code")
        assert self._dispatch("/tool go", tmp_path, code_holder)[0] == "agent"
        assert code_holder.resolve_turn() == "tool"
        assert code_holder.resolve_turn() == "code"

    def test_both_empty_prefix_returns_usage_without_arming(self, tmp_path):
        from strands_code_cli.codeact import CODEACT_ROUTE_USAGE, CodeactState

        assert CODEACT_ROUTE_USAGE == "Usage: /code <ask> or /tool <ask>"
        for text in ("/code", "/code   ", "/tool", "/tool  "):
            holder = CodeactState(initial="both")
            action, message = self._dispatch(text, tmp_path, holder)
            assert action == "reply"
            assert message == CODEACT_ROUTE_USAGE
            assert holder.resolve_turn() == "both"  # nothing armed

    def test_both_bare_ask_returns_routing_usage(self, tmp_path):
        from strands_code_cli.codeact import CODEACT_ROUTE_USAGE, CodeactState

        holder = CodeactState(initial="both")
        action, message = self._dispatch("list the files", tmp_path, holder)
        assert action == "reply"
        assert message == CODEACT_ROUTE_USAGE

    def test_both_bare_asks_in_tool_and_code_start_agent_turns(self, tmp_path):
        from strands_code_cli.codeact import CodeactState

        for sticky in ("tool", "code"):
            holder = CodeactState(initial=sticky)
            assert self._dispatch("list the files", tmp_path, holder) == (
                "agent",
                None,
            )

    def test_both_bare_ask_without_holder_starts_agent_turn(self, tmp_path):
        assert self._dispatch("list the files", tmp_path, None) == ("agent", None)

    def test_both_prefix_without_holder_starts_agent_turn(self, tmp_path):
        action, message = self._dispatch("/code go", tmp_path, None)
        assert (action, message) == ("agent", "go")

    def test_both_arm_rejects_anything_but_code_or_tool(self):
        from strands_code_cli.codeact import CodeactState

        holder = CodeactState()
        for bad in ("both", "turbo", "", "TOOL"):
            try:
                holder.arm_one_shot(bad)
            except ValueError as exc:
                assert "code|tool" in str(exc)
            else:
                raise AssertionError(f"expected ValueError for {bad!r}")
        assert holder.resolve_turn() == "tool"  # failed arms arm nothing

    def test_both_resolve_turn_passes_sticky_through(self):
        from strands_code_cli.codeact import CodeactState

        for sticky in CodeactState.VALID:
            assert CodeactState(initial=sticky).resolve_turn() == sticky

    def test_both_full_flow_prefix_then_bare_ask(self, tmp_path):
        from strands_code_cli.codeact import (
            CODEACT_ROUTE_USAGE,
            CodeactState,
            resolve_turn_interface,
            shape_turn_text,
        )

        holder = CodeactState(initial="both")
        # Turn 1: explicit /code routing runs a code turn.
        action, message = self._dispatch("/code list the files", tmp_path, holder)
        assert action == "agent"
        turn = resolve_turn_interface(holder.resolve_turn())
        assert turn == "code"
        assert shape_turn_text(turn, message).startswith("You are in CodeAct mode")
        # Turn 2: a bare ask never silently defaults — usage again.
        assert self._dispatch("and the docs", tmp_path, holder) == (
            "reply",
            CODEACT_ROUTE_USAGE,
        )

    def test_both_heads_are_builtin(self):
        assert "code" in BUILTIN_SLASH_HEADS
        assert "tool" in BUILTIN_SLASH_HEADS

    def test_both_heads_beat_shadowed_skills(self, tmp_path):
        from strands_code_cli.codeact import CodeactState

        for name, armed in (("code", "code"), ("tool", "tool")):
            skills_dir = tmp_path / f"skills-{name}"
            _write_skill(skills_dir, name)
            skills = SkillIndex(skills_dir)
            assert skills.warnings
            holder = CodeactState(initial="both")
            index = SessionIndex(tmp_path / "index")
            action, message = dispatch(
                f"/{name} go", session_id="s", index=index, skills=skills,
                interface=holder,
            )
            assert (action, message) == ("agent", "go")
            assert holder.resolve_turn() == armed

    def test_both_usage_hint_documents_prefixes(self):
        assert "/code <ask>" in USAGE_HINT
        assert "/tool <ask>" in USAGE_HINT

    def test_both_loop_fix_at_send_consumes_one_shot(self):
        import inspect

        import strands_code_cli.loop as loop_module

        run_source = inspect.getsource(loop_module.run_loop)
        assert "interface.resolve_turn()" in run_source


# ----------------------------------------------------------------------
# 11-03 task 2: switching coherence pins (D-16/D-18/D-20)
# ----------------------------------------------------------------------


class TestCodeactSwitchingCoherence:
    def test_turn_rows_exclude_interface_across_turns(self):
        from strands_code_cli.loop import record_turn_metrics

        turns: list = []
        interfaces: list[str] = []
        record_turn_metrics(_Summary(1000, 200), "bedrock/x-model", turns)
        interfaces.append("tool")
        record_turn_metrics(_Summary(3000, 400), "bedrock/x-model", turns)
        interfaces.append("code")
        assert interfaces == ["tool", "code"]
        assert [row["turn"] for row in turns] == [1, 2]
        for row in turns:
            assert set(row) == {"turn", "input_tokens", "output_tokens", "model"}
            assert "interface" not in row

    def test_cost_report_byte_identical_across_interfaces(self):
        from strands_code_cli.cost_context import cost_report
        from strands_code_cli.loop import record_turn_metrics

        def _session(interfaces: list[str]) -> str:
            turns: list = []
            for in_tok, out_tok in ((1000, 200), (3000, 400)):
                record_turn_metrics(
                    _Summary(in_tok, out_tok), "bedrock/x-model", turns
                )
            # The parallel list shadows the rows one-to-one, never a row key.
            assert len(turns) == len(interfaces)
            return cost_report(turns, "bedrock/x-model")

        tool_report = _session(["tool", "tool"])
        code_report = _session(["code", "code"])
        assert tool_report == code_report
        assert "interface" not in tool_report

    def test_policy_file_byte_identical_across_switches(self, tmp_path):
        from strands_code_cli.policy import Allow, PolicyConfig, Rule, decide

        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"
        PolicyConfig().append_rule(
            "allow", Rule(tool="shell", command="git status"), repo_path=repo
        )
        before = repo.read_bytes()
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        for verb in ("code", "both", "tool", "code"):
            action, _ = dispatch(
                "/codeact " + verb, session_id="s", index=index, interface=holder
            )
            assert action == "reply"
        assert repo.read_bytes() == before
        # The remembered rule still decides identically after the switches.
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert isinstance(
            decide("shell", {"command": "git status --short"}, reloaded), Allow
        )

    def test_messages_byte_identical_across_switch_with_stint_reset(self, tmp_path):
        from strands_code_cli.codeact import CodeactStint

        holder = CodeactState()
        stint = CodeactStint(tmp_path)
        stint.execute_code("x = 41")
        agent = SimpleNamespace(
            messages=[
                {"role": "user", "content": [{"text": "q"}]},
                {"role": "assistant", "content": [{"text": "a"}]},
            ]
        )
        before = copy.deepcopy(agent.messages)
        for verb in ("code", "tool"):
            holder.set(verb)
            stint.reset()  # the loop's post-switch reset (D-17)
        assert len(agent.messages) == len(before)
        assert agent.messages == before
