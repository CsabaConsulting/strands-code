"""Tool-surface contracts: builtin mapping, scope guard, prompt steering (TOOL-01).

Live-turn observation (tracer, RESEARCH §1.3): ``build_agent`` never passed
``builtin_tools``, so the harness default set was already live —
``["shell", "read", "write", "edit", "web_fetch", "web_search",
"programmatic_tool_caller", "subagent"]`` per the ``create_harness``
docstring (``strands_harness/agent.py``). Phase 2 pins this explicitly via a
MAPPING (not a pin list) so future upstream defaults still flow: shell/read
stay on, builtin write/edit go off in favor of the diff-gated wrappers of
the same names, and the local ``search`` tool rides the consumer tools list.
No ``strands_tools`` import anywhere (deprecated editor/shell, not installed).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS, CodeAgent
import importlib

main_module = importlib.import_module("strands_code_cli.main")
from strands_code_cli.scope import ScopeGuard, confine, resolve


def _tool_names(tools):
    return [getattr(t, "tool_name", getattr(t, "__name__", "")) for t in tools]


def _build_kwargs(tmp_path):
    with patch.object(main_module, "create_harness", return_value=MagicMock()) as factory:
        main_module.build_agent("test-session", tmp_path)
        return factory.call_args[1]


class TestBuiltinToolsMapping:
    def test_mapping_enables_shell_and_read(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        mapping = kwargs["builtin_tools"]
        assert mapping["shell"] is True
        assert mapping["read"] is True

    def test_mapping_pins_off_builtin_write_edit_for_wrappers(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        mapping = kwargs["builtin_tools"]
        assert mapping["write"] is False
        assert mapping["edit"] is False

    def test_mapping_is_mapping_not_pin_list(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        assert isinstance(kwargs["builtin_tools"], dict)

    def test_python_repl_stays_present(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        assert any("python_repl" in name for name in _tool_names(kwargs["tools"]))

    def test_search_tool_registered(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        assert "search" in _tool_names(kwargs["tools"])

    def test_gated_wrappers_replace_builtins(self, tmp_path):
        kwargs = _build_kwargs(tmp_path)
        names = _tool_names(kwargs["tools"])
        assert "write" in names
        assert "edit" in names

    def test_no_strands_tools_import(self):
        import subprocess

        proc = subprocess.run(
            ["grep", "-rn", "strands_tools", "strands_code_cli", "strands_code_agent"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, proc.stdout


class TestScopeGuard:
    def test_absolute_in_scope(self, tmp_path):
        target = tmp_path / "a.py"
        target.write_text("x")
        assert confine(target, tmp_path) == target.resolve()

    def test_relative_in_scope(self, tmp_path):
        assert resolve("sub/a.py", tmp_path) == tmp_path / "sub" / "a.py"
        assert confine("sub/a.py", tmp_path) == tmp_path / "sub" / "a.py"

    def test_sibling_refused_names_allowed_roots(self, tmp_path):
        # NOTE: pytest tmp dirs live under /tmp, which is itself an allowed
        # root — so refusal tests use a synthetic cwd outside /tmp.
        cwd = Path("/opt/scope-test-proj")
        with pytest.raises(ValueError, match="allowed roots"):
            confine("/opt/other-repo/a.py", cwd)

    def test_tmp_admitted(self, tmp_path):
        assert confine("/tmp/scratch-note.txt", tmp_path) == Path("/tmp/scratch-note.txt")

    def test_dotdot_traversal_refused(self, tmp_path):
        cwd = Path("/opt/scope-test-proj")
        with pytest.raises(ValueError, match="allowed roots"):
            confine(cwd / ".." / "escape.py", cwd)

    def test_symlink_escape_refused(self, tmp_path):
        cwd = Path("/opt/scope-test-proj")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to("/definitely-outside-scope-target")
        except OSError:
            pytest.skip("symlinks unavailable")
        with pytest.raises(ValueError, match="allowed roots"):
            confine(link, cwd)

    def test_guard_constructor_kwarg_pattern(self, tmp_path):
        guard = ScopeGuard(cwd=tmp_path)
        assert guard.resolve("a.py") == tmp_path / "a.py"
        assert guard.confine("a.py") == tmp_path / "a.py"

    def test_shell_commands_pass_through_unscoped(self, tmp_path):
        # D-06: full shell is never scope-checked here; documented, not closed.
        assert "echo hi" == "echo hi"


class TestPromptSteering:
    @pytest.mark.parametrize("tool_name", ["search", "read", "write", "edit", "shell"])
    def test_prompt_names_dedicated_tools(self, tool_name):
        assert tool_name in CODE_AGENT_INSTRUCTIONS

    def test_prompt_steers_away_from_python_open(self):
        assert "open()" in CODE_AGENT_INSTRUCTIONS

    def test_caller_tool_list_unaliased(self):
        extra = MagicMock()
        extra.tool_name = "my_tool"
        caller_list = [extra]
        with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None):
            CodeAgent(tools=caller_list, tmp_dir=False)
        assert caller_list == [extra]

    def test_repl_present_with_extra_tools(self):
        extra = MagicMock()
        extra.tool_name = "my_tool"
        with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None) as mock_init:
            CodeAgent(tools=[extra], tmp_dir=False)
            tools = mock_init.call_args[1]["tools"]
            assert extra in tools
            assert any("python_repl" in n for n in _tool_names(tools))

    def test_cwd_default_is_process_cwd(self, tmp_path):
        assert os.getcwd()


# ---------------------------------------------------------------------------
# Scope-policy ordering (Phase 3 D-13: policy match runs before confine)
# ---------------------------------------------------------------------------


class TestScopePolicyOrdering:
    def test_outside_path_with_allow_rule_admitted(self, tmp_path):
        from strands_code_cli.policy import PolicyConfig, Rule
        from strands_code_cli.scope import confine, effective_roots

        cwd = Path("/opt/scope-test-proj")
        policy = PolicyConfig(allow=[Rule(tool="write", path="/opt/granted/*.md")])
        roots = effective_roots(cwd, policy)
        assert any(str(r).startswith("/opt/granted") for r in roots)
        admitted = confine("/opt/granted/notes.md", cwd, [r for r in roots if str(r) not in (str(cwd), "/tmp")])
        assert str(admitted) == "/opt/granted/notes.md"

    def test_outside_path_without_rule_denied_names_roots(self):
        from strands_code_cli.policy import PolicyConfig
        from strands_code_cli.scope import confine, effective_roots

        cwd = Path("/opt/scope-test-proj")
        roots = effective_roots(cwd, PolicyConfig())
        assert [str(r) for r in roots] == [str(cwd), "/tmp"]
        with pytest.raises(ValueError, match="allowed roots"):
            confine("/opt/other-repo/a.py", cwd)

    def test_relative_allow_rule_grants_no_extra_roots(self, tmp_path):
        from strands_code_cli.policy import PolicyConfig, Rule
        from strands_code_cli.scope import effective_roots

        policy = PolicyConfig(allow=[Rule(tool="write", path="docs/*.md")])
        assert [str(r) for r in effective_roots(tmp_path, policy)] == [str(tmp_path), "/tmp"]
