"""Single-intervention PolicyGateHandler tests & adversarial specs (TOOL-03, D-01..D-07)."""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from strands import Agent, tool
from strands.hooks import HookRegistry
from strands.interventions.actions import Deny as HitlDeny
from strands.interventions.actions import Proceed
from strands.interventions.registry import InterventionRegistry
from strands.models.model import Model
from strands.types.exceptions import EventLoopException
from strands_harness.interventions import resolve_interventions

import strands_code_cli.policy.policy_gate as gate_module
from strands_code_cli.loop.steering import SteeringState, register_steering_hook
from strands_code_cli.policy.core import PolicyConfig, PolicyOptions, Rule
from strands_code_cli.policy.policy_gate import (
    ApprovalBroker,
    BatchState,
    PolicyGateHandler,
    TurnCancelled,
    _dialog_title,
    build_interventions,
    gate_for,
    tag_for,
    worker_cancelled,
)

main_module = importlib.import_module("strands_code_cli.entry.main")


class _FakeAgent:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def _event(name: str, tool_input: dict[str, Any], agent: Any = None, uid: str = "t1"):
    return SimpleNamespace(
        agent=agent if agent is not None else _FakeAgent(),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )


def _gate(loader=None, answers: list[str] | None = None, monkeypatch=None, **kwargs):
    handler = PolicyGateHandler(policy_loader=loader or PolicyConfig.load, **kwargs)
    if answers is not None and monkeypatch is not None:
        it = iter(answers)
        monkeypatch.setattr("builtins.input", lambda *args: next(it))
    return handler, handler


def _capture_console(monkeypatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr(
        gate_module,
        "console",
        Console(file=buf, width=400, highlight=False, no_color=True),
    )
    return buf


def _run(handler, event):
    return asyncio.run(handler.before_tool_call(event))


class _ToolCallingModel(Model):
    """Offline model double emitting one toolUse turn, then final text."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        self._tool_name = tool_name
        self._tool_input = tool_input
        self.calls = 0

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model_id": "offline-tool-model"}

    async def structured_output(  # type: ignore[override]
        self,
        output_model: Any,
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ):  # type: ignore[override]
        idx = self.calls
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        if idx == 0:
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {"toolUseId": "tu-steer-1", "name": self._tool_name}
                    }
                }
            }
            yield {
                "contentBlockDelta": {
                    "delta": {"toolUse": {"input": json.dumps(self._tool_input)}}
                }
            }
            yield {"contentBlockStop": {}}
            stop_reason = "tool_use"
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": "redirected-ok"}}}
            yield {"contentBlockStop": {}}
            stop_reason = "end_turn"
        yield {"messageStop": {"stopReason": stop_reason}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 0},
            }
        }


# ---------------------------------------------------------------------------
# Single-intervention gate spine
# ---------------------------------------------------------------------------


class TestSingleGateSpine:
    def test_single_gate_constructs(self):
        gate = PolicyGateHandler(policy_loader=PolicyConfig.load)
        assert gate.name == "strands-code:policy-gate"
        assert gate.on_error == "throw"

    def test_two_gate_instances_collide_resolve_and_registry(self):
        one = PolicyGateHandler(policy_loader=PolicyConfig.load)
        two = PolicyGateHandler(policy_loader=PolicyConfig.load)
        with pytest.raises(ValueError, match="strands-code:policy-gate"):
            resolve_interventions([one, two])
        with pytest.raises(ValueError, match="Duplicate intervention handler name"):
            InterventionRegistry([one, two], HookRegistry())

    def test_interventions_reach_create_harness_as_single_policy_gate(self, tmp_path):
        with patch.object(
            main_module, "create_harness", return_value=MagicMock()
        ) as factory:
            agent = main_module.build_agent("test-session", tmp_path)
            kwargs = factory.call_args[1]
        interventions = kwargs["interventions"]
        assert isinstance(interventions, list) and len(interventions) == 1
        assert isinstance(interventions[0], PolicyGateHandler)
        assert gate_for(agent) is interventions[0]

    def test_programmatic_tool_caller_pinned_off(self, tmp_path):
        with patch.object(
            main_module, "create_harness", return_value=MagicMock()
        ) as factory:
            main_module.build_agent("test-session", tmp_path)
            mapping = factory.call_args[1]["builtin_tools"]
        assert mapping["programmatic_tool_caller"] is False


# ---------------------------------------------------------------------------
# Gate layer: decide + batching + remember-me
# ---------------------------------------------------------------------------


class TestGateLayer:
    def test_allow_in_scope_read_silent_while_outside_prompts(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(
                AssertionError("in-scope read must not prompt")
            ),
        )
        in_scope = str(Path.cwd() / "README.md")
        assert isinstance(_run(handler, _event("read", {"path": in_scope})), Proceed)

        prompts: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda *args: (prompts.append("ask"), "n")[1]
        )
        outside = _run(handler, _event("read", {"path": "/x"}))
        assert isinstance(outside, HitlDeny)
        assert prompts == ["ask"]

    def test_prompt_once_per_rule_per_turn(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        first = _run(handler, _event("shell", {"command": "make test"}, uid="u1"))
        assert isinstance(first, Proceed)
        second = _run(handler, _event("shell", {"command": "make test"}, uid="u2"))
        assert isinstance(second, Proceed)

    def test_batch_resets_next_turn(self, monkeypatch):
        prompts: list[str] = []
        handler, _ = _gate()
        it = iter(["y", "y"])
        monkeypatch.setattr(
            "builtins.input", lambda *args: (prompts.append("ask"), next(it))[1]
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, uid="u1")), Proceed
        )
        handler.bind_turn("turn-2")
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, uid="u3")), Proceed
        )
        assert len(prompts) == 2

    def test_deny_short_circuits_naming_rule(self, monkeypatch):
        def loader():
            return PolicyConfig(deny=[Rule(tool="shell", command="curl")])

        buf = _capture_console(monkeypatch)
        _, handler = _gate(loader=loader, monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(AssertionError("deny must not prompt")),
        )
        result = _run(handler, _event("shell", {"command": "curl http://x"}, uid="u9"))
        assert isinstance(result, HitlDeny)
        assert "curl" in result.reason
        assert "Denied by policy rule" in result.reason
        assert "Denied by policy rule" in buf.getvalue()
        assert "curl" in buf.getvalue()

    def test_always_appends_narrow_rule(self, tmp_path, monkeypatch):
        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"

        def loader():
            return PolicyConfig.load(home_path=missing, repo_path=repo)

        handler = PolicyGateHandler(policy_loader=loader, append_path=repo)
        monkeypatch.setattr("builtins.input", lambda *args: "always")
        result = _run(handler, _event("shell", {"command": "git status"}, uid="u1"))
        assert isinstance(result, Proceed)
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.allow) == 1
        assert reloaded.allow[0].tool == "shell"
        assert reloaded.allow[0].command == "git status"
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")),
        )
        second = _run(
            handler, _event("shell", {"command": "git status --short"}, uid="u2")
        )
        assert isinstance(second, Proceed)

    def test_never_appends_deny_rule(self, tmp_path, monkeypatch):
        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig.load(home_path=missing, repo_path=repo),
            append_path=repo,
        )
        monkeypatch.setattr("builtins.input", lambda *args: "never")
        result = _run(handler, _event("shell", {"command": "make test"}, uid="u1"))
        assert isinstance(result, HitlDeny)
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.deny) == 1

    def test_trust_delegated_skips_only_non_main_agent(self, monkeypatch):
        main_agent, child_agent = _FakeAgent(), _FakeAgent()
        prompts: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda *args: (prompts.append("ask"), "n")[1]
        )
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        handler.bind_main_agent(main_agent)
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, child_agent, "u1")),
            Proceed,
        )
        assert len(prompts) == 0
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, main_agent, "u2")),
            HitlDeny,
        )
        assert len(prompts) == 1

    def test_delegate_prompts_by_default(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        result = _run(
            handler, _event("shell", {"command": "make test"}, _FakeAgent(), "u1")
        )
        assert isinstance(result, Proceed)

    def test_unbound_agent_prompts_fail_closed(self, monkeypatch):
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        monkeypatch.setattr("builtins.input", lambda *args: "n")
        result = _run(
            handler, _event("shell", {"command": "make test"}, _FakeAgent(), "u1")
        )
        assert isinstance(result, HitlDeny)

    def test_prompt_error_denies_fail_closed(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(RuntimeError("tty gone"))
        )
        result = _run(handler, _event("shell", {"command": "make test"}))
        assert isinstance(result, HitlDeny)
        assert "failed closed" in result.reason


# ---------------------------------------------------------------------------
# python_repl gating + delegated e2e + deny messaging
# ---------------------------------------------------------------------------


class TestReplAndDelegation:
    def test_repl_prompted_with_code(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["n"])
        result = _run(
            handler,
            _event("python_repl", {"code": "import socket\nprint(1)"}, uid="r1"),
        )
        assert isinstance(result, HitlDeny)

    def test_subagent_call_prompts(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["n"])
        result = _run(handler, _event("subagent", {"task": "do it"}, uid="s1"))
        assert isinstance(result, HitlDeny)

    def test_deny_reason_propagates(self, monkeypatch):
        def loader():
            return PolicyConfig(deny=[Rule(tool="shell", command="curl")])

        _, handler = _gate(loader=loader, monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input", lambda *args: (_ for _ in ()).throw(AssertionError())
        )
        result = _run(handler, _event("shell", {"command": "curl http://x"}, uid="d1"))
        assert isinstance(result, HitlDeny)
        assert "Denied by policy rule" in result.reason and "curl" in result.reason

    def test_plan_mode_deny_reason_propagates(self, monkeypatch):
        handler, _ = _gate(monkeypatch=monkeypatch, answers=[])
        handler.set_mode("plan")
        monkeypatch.setattr(
            "builtins.input", lambda *args: (_ for _ in ()).throw(AssertionError())
        )
        result = _run(handler, _event("write", {"path": "x.txt"}, uid="p1"))
        assert isinstance(result, HitlDeny)
        assert "Plan mode is read-only" in result.reason


# ---------------------------------------------------------------------------
# Turn & log helpers
# ---------------------------------------------------------------------------


class TestGateTurnHelpers:
    def test_bind_turn_and_last_covered(self, monkeypatch):
        interventions = build_interventions()
        handler = interventions[0]
        handler.bind_turn("t-1")
        monkeypatch.setattr("builtins.input", lambda *args: "y")
        result = _run(handler, _event("shell", {"command": "make test"}))
        assert isinstance(result, Proceed)
        assert handler.last_covered() != []
        handler.bind_turn("t-2")
        assert len(handler.batch._covered) == 0

    def test_bind_main_agent_none_noop(self):
        PolicyGateHandler().bind_main_agent(None)


# ---------------------------------------------------------------------------
# Agent-tagged prompts, 3-way isolation, SHA-256 BatchState
# ---------------------------------------------------------------------------


class TestAgentTaggedGate:
    def test_tag_for_identity(self):
        main = _FakeAgent()
        assert tag_for(None, main) == "main"
        assert tag_for(None, None) == "main"
        assert tag_for(main, main) == "main"
        assert tag_for(_FakeAgent(), main) == "btw"

    def test_is_covered_tag_keyword_defaults_main(self):
        batch = BatchState()
        batch.bind_turn("t-1")
        sig = ("prompt", "shell", "Shell command: make test", "abc")
        assert batch.is_covered(sig) is False
        batch.mark(sig, "[main] approved shell: Shell command: make test")
        assert batch.is_covered(sig) is True
        assert batch.is_covered(sig, tag="main") is True
        assert batch.is_covered(sig, tag="btw") is False

    def test_three_way_agent_isolation_and_read_only_agents(self, monkeypatch):
        main_agent, btw_agent, sub_agent = _FakeAgent(), _FakeAgent(), _FakeAgent()
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")
        assert handler.tag_for(main_agent) == "main"
        assert handler.tag_for(btw_agent) == "btw"
        assert handler.tag_for(sub_agent) == "subagent"

        answers = iter(["y", "y", "y"])
        monkeypatch.setattr("builtins.input", lambda *args: next(answers))
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, main_agent, "m1")),
            Proceed,
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, btw_agent, "b1")),
            Proceed,
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, sub_agent, "s1")),
            Proceed,
        )
        assert list(answers) == []

        with handler.read_only(sub_agent):
            assert handler.is_read_only(sub_agent) is True
            assert handler.is_read_only(main_agent) is False
            sub_res = _run(
                handler, _event("write", {"path": "x.txt"}, sub_agent, "ro-1")
            )
            assert isinstance(sub_res, HitlDeny)
            assert "Plan mode is read-only" in sub_res.reason
        assert handler.is_read_only(sub_agent) is False

    def test_concurrent_prompts_keep_own_detail(self, monkeypatch):
        main_agent, btw_agent = _FakeAgent(), _FakeAgent()
        broker = ApprovalBroker()
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load, broker=broker)
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")
        buf = _capture_console(monkeypatch)
        answers = iter(["y", "y"])
        monkeypatch.setattr("builtins.input", lambda *args: next(answers))
        pump_cancel = threading.Event()
        outcomes: dict[str, Any] = {}

        def worker(key: str, agent: Any, cmd: str, uid: str):
            outcomes[key] = _run(handler, _event("shell", {"command": cmd}, agent, uid))

        with broker.pump(pump_cancel):
            threads = [
                threading.Thread(
                    target=worker, args=("main", main_agent, "main-cmd --main", "m1")
                ),
                threading.Thread(
                    target=worker, args=("btw", btw_agent, "btw-cmd --btw", "b1")
                ),
            ]
            for thread in threads:
                thread.start()
            while any(thread.is_alive() for thread in threads):
                req = broker.poll(timeout=0.05)
                if req is not None:
                    req.run_prompt()
            for thread in threads:
                thread.join(timeout=5)
        assert isinstance(outcomes["main"], Proceed)
        assert isinstance(outcomes["btw"], Proceed)
        rendered = buf.getvalue()
        assert "Approval needed: [main] shell" in rendered
        assert "main-cmd --main" in rendered
        assert "Approval needed: [btw] shell" in rendered
        assert "btw-cmd --btw" in rendered

    def test_btw_deny_reprompts(self, monkeypatch):
        main_agent, btw_agent = _FakeAgent(), _FakeAgent()
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")
        it = iter(["n", "n"])
        monkeypatch.setattr("builtins.input", lambda *args: next(it))
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, btw_agent, "b1")),
            HitlDeny,
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, btw_agent, "b2")),
            HitlDeny,
        )
        assert list(it) == []

    def test_trust_delegated_btw_prints_transcript_note(self, monkeypatch, capsys):
        def _raise(*args, **kwargs):
            raise AssertionError("trust note must use print_plain, not print")

        monkeypatch.setattr("builtins.print", _raise)
        main_agent, btw_agent = _FakeAgent(), _FakeAgent()
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")
        result = _run(
            handler, _event("shell", {"command": "make test"}, btw_agent, "b1")
        )
        assert isinstance(result, Proceed)
        assert result.reason == "delegated-trusted"
        assert "Auto-trusted delegated call (shell)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Self-identifying approval dialogs & sanitized headers (G-7-4, D-07)
# ---------------------------------------------------------------------------


class TestDialogAttribution:
    def _dialog_ask(self, monkeypatch, command, pick, *, btw=False):
        import strands_code_cli.ui.choice as choice_mod

        titles: list[str] = []

        def fake_radio(title, options, **kwargs):
            titles.append(title)
            if isinstance(pick, type) and issubclass(pick, BaseException):
                raise pick()
            return pick

        monkeypatch.setattr(choice_mod, "radio_choice", fake_radio)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        main_agent = _FakeAgent()
        btw_agent = _FakeAgent()
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")
        event_agent = btw_agent if btw else main_agent
        res = _run(handler, _event("shell", {"command": command}, event_agent, "u1"))
        return res, titles

    def test_main_dialog_title_carries_tag_tool_detail(self, monkeypatch):
        res, titles = self._dialog_ask(monkeypatch, "make test", "y")
        assert isinstance(res, Proceed)
        assert titles == ["Approve? [main] shell — make test"]

    def test_btw_dialog_title_carries_tag_tool_detail(self, monkeypatch):
        res, titles = self._dialog_ask(monkeypatch, "sleep 30", "y", btw=True)
        assert isinstance(res, Proceed)
        assert titles == ["Approve? [btw] shell — sleep 30"]

    def test_long_detail_truncates_to_one_line_and_strips_ansi(self, monkeypatch):
        res, titles = self._dialog_ask(
            monkeypatch,
            "\x1b[31mrun\x1b[0m this\nmultiline command " + "x" * 100,
            "y",
        )
        assert isinstance(res, Proceed)
        assert len(titles) == 1
        assert "\x1b" not in titles[0]
        assert "\n" not in titles[0]
        assert titles[0].startswith("Approve? [main] shell — run this multiline")
        assert titles[0].endswith("...")

    def test_header_and_typed_fallback_byte_identical(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *args: "y")
        buf = _capture_console(monkeypatch)
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        main_agent = _FakeAgent()
        handler.bind_main_agent(main_agent)
        res = _run(handler, _event("shell", {"command": "make test"}, main_agent, "u1"))
        assert isinstance(res, Proceed)
        assert buf.getvalue() == (
            "Approval needed: [main] shell\n"
            "  Detail: make test\n"
            "  Risk: Shell command: make test\n"
            "Approve? [y/n/always/never]\n"
            "> "
        )

    def test_dialog_escape_denies_and_ctrl_c_fails_closed_via_kbi(self, monkeypatch):
        res, _ = self._dialog_ask(monkeypatch, "make test", None)
        assert isinstance(res, HitlDeny)
        with pytest.raises(KeyboardInterrupt):
            self._dialog_ask(monkeypatch, "make test", KeyboardInterrupt)


# ---------------------------------------------------------------------------
# CodeAct preview + deny revise hint + rule coherence (D-05/D-06/D-07)
# ---------------------------------------------------------------------------


def _code_block_2000() -> str:
    line = "value = transform(input_value, options)\n"
    return (line * ((2000 // len(line)) + 1))[:2000]


class TestCodeactApprovalPreview:
    def test_preview_carries_full_2000_char_block(self, monkeypatch):
        block = _code_block_2000()
        assert len(block) == 2000
        buf = io.StringIO()
        monkeypatch.setattr(gate_module, "console", Console(file=buf, width=200))
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        result = _run(handler, _event("python_repl", {"code": block}, uid="c1"))
        assert isinstance(result, Proceed)
        lines = [line.rstrip() for line in buf.getvalue().split("\n")]
        start = lines.index("Approval needed: [main] python_repl") + 1
        end = next(i for i, ln in enumerate(lines) if ln.startswith("  Risk:"))
        assert "\n".join(lines[start:end]).rstrip("\n") == block.rstrip("\n")

    def test_dialog_title_keeps_sixty_char_collapse(self):
        block = _code_block_2000()
        assert _dialog_title("main", "python_repl", {"code": block}) == (
            "Approve? [main] python_repl — "
            "value = transform(input_value, options) value = transform..."
        )

    def test_single_use_yields_exactly_one_prompt(self, monkeypatch):
        buf = _capture_console(monkeypatch)
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        result = _run(handler, _event("python_repl", {"code": "print('hi')"}, uid="c2"))
        assert isinstance(result, Proceed)
        rendered = buf.getvalue()
        assert rendered.count("Approval needed: [main] python_repl") == 1
        assert "  Detail:" not in rendered
        assert "  Risk: Python execution:" in rendered

    def test_deny_carries_revise_hint_with_continue_verdict(self, monkeypatch):
        def loader():
            return PolicyConfig(
                deny=[Rule(tool="python_repl", command="import socket")]
            )

        buf = _capture_console(monkeypatch)
        _, handler = _gate(loader=loader, monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(AssertionError("deny must not prompt")),
        )
        result = _run(
            handler,
            _event("python_repl", {"code": "import socket\nprint(1)"}, uid="d1"),
        )
        assert isinstance(result, HitlDeny)
        assert "Revise the code or try a different approach." in result.reason
        assert "Revise the code or try a different approach." in buf.getvalue()
        assert "skipped, continuing" in buf.getvalue()


class TestCodeactRuleCoherence:
    def test_always_derives_narrow_python_repl_rule(self, tmp_path, monkeypatch):
        from strands_code_cli.policy.core import normalise_command

        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"

        def loader():
            return PolicyConfig.load(home_path=missing, repo_path=repo)

        handler = PolicyGateHandler(policy_loader=loader, append_path=repo)
        code = "total = '" + "ab" * 300 + "'"
        assert len(code) > 500
        monkeypatch.setattr("builtins.input", lambda *args: "always")
        result = _run(handler, _event("python_repl", {"code": code}, uid="r1"))
        assert isinstance(result, Proceed)
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.allow) == 1
        assert reloaded.allow[0].tool == "python_repl"
        assert reloaded.allow[0].command == normalise_command(code)[:500]
        fresh_handler = PolicyGateHandler(policy_loader=loader)
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")),
        )
        second = _run(
            fresh_handler,
            _event("python_repl", {"code": code + " + 'cd'"}, uid="r2"),
        )
        assert isinstance(second, Proceed)

    def test_never_derives_python_repl_deny_rule(self, tmp_path, monkeypatch):
        from strands_code_cli.policy.core import normalise_command

        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig.load(home_path=missing, repo_path=repo),
            append_path=repo,
        )
        code = "import socket; print(socket.gethostname())"
        monkeypatch.setattr("builtins.input", lambda *args: "never")
        result = _run(handler, _event("python_repl", {"code": code}, uid="r3"))
        assert isinstance(result, HitlDeny)
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.deny) == 1
        assert reloaded.deny[0].tool == "python_repl"
        assert reloaded.deny[0].command == normalise_command(code)[:500]

    @pytest.mark.parametrize("holder_value", ["tool", "code"])
    def test_plan_deny_holds_on_both_interfaces(
        self, holder_value, monkeypatch, tmp_path
    ):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.policy.codeact import CodeactState
        from strands_code_cli.session.session_index import SessionIndex

        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, _ = dispatch(
            "/codeact " + holder_value, session_id="s", index=index, interface=holder
        )
        assert action == "reply"
        assert holder.interface == holder_value
        buf = _capture_console(monkeypatch)
        handler = PolicyGateHandler(policy_loader=lambda: PolicyConfig(), mode="plan")
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(
                AssertionError("Plan deny must not prompt")
            ),
        )
        result = _run(handler, _event("python_repl", {"code": "print('x')"}))
        assert isinstance(result, HitlDeny)
        assert "Plan mode is read-only" in result.reason
        text = buf.getvalue()
        assert "Plan mode is read-only" in text
        for banned in (
            "policy rule",
            "rule [",
            "approve-each",
            "on-demand",
            "auto",
            "/diff",
            "yolo",
        ):
            assert banned not in result.reason
            assert banned not in text
        assert "Revise the code" not in text


class TestGateFailClosedAndProtected:
    def test_duplicate_tool_use_id_renders_own_preview_independently(self, monkeypatch):
        buf = _capture_console(monkeypatch)
        it = iter(["y", "n"])
        monkeypatch.setattr("builtins.input", lambda *args: next(it))
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        first = _run(handler, _event("shell", {"command": "make test"}, uid="dup-1"))
        assert isinstance(first, Proceed)
        second = _run(handler, _event("shell", {"command": "rm -rf /"}, uid="dup-1"))
        assert isinstance(second, HitlDeny)
        out = buf.getvalue()
        assert "make test" in out
        assert "rm -rf /" in out

    def test_duplicate_tool_use_id_after_plan_deny_does_not_leak_reason(
        self, monkeypatch
    ):
        _, handler = _gate(monkeypatch=monkeypatch, answers=[])
        handler.set_mode("plan")
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(
                AssertionError("plan deny must not prompt")
            ),
        )
        first = _run(handler, _event("write", {"path": "a.txt"}, uid="dup-2"))
        assert isinstance(first, HitlDeny)
        assert "Plan mode is read-only" in first.reason

        handler.set_mode("act")
        monkeypatch.setattr("builtins.input", lambda *args: "n")
        second = _run(handler, _event("shell", {"command": "echo hi"}, uid="dup-2"))
        assert isinstance(second, HitlDeny)
        assert "Plan mode is read-only" not in second.reason

    def test_loader_error_clears_nothing_and_denies_fail_closed(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        first = _run(handler, _event("shell", {"command": "make test"}, uid="ok-1"))
        assert isinstance(first, Proceed)

        monkeypatch.setattr(
            handler,
            "_current_policy",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(
                AssertionError("must not prompt on internal gate error")
            ),
        )
        second = _run(handler, _event("shell", {"command": "rm -rf /"}, uid="err-2"))
        assert isinstance(second, HitlDeny)
        assert "failed closed" in second.reason

    def test_protected_skills_path_prompts_through_gate(self, tmp_path, monkeypatch):
        prompts: list[str] = []
        monkeypatch.chdir(tmp_path)
        policy = PolicyConfig(allow=[Rule(tool="write", path="*")])
        handler = PolicyGateHandler(policy_loader=lambda: policy)
        monkeypatch.setattr(
            "builtins.input", lambda prompt="": (prompts.append("ask"), "n")[1]
        )
        verdict = _run(
            handler,
            _event("write", {"path": ".agent/skills/evil/SKILL.md"}, uid="prot-1"),
        )
        assert prompts == ["ask"]
        assert isinstance(verdict, HitlDeny)

    def test_protected_path_omits_always_dialog_blocks_dead_allow_and_keeps_never(
        self, tmp_path, monkeypatch
    ):
        import sys

        repo_policy = tmp_path / "policy.toml"
        missing_home = tmp_path / "missing.toml"
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agent").mkdir(parents=True)
        handler = PolicyGateHandler(
            policy_loader=lambda: PolicyConfig(allow=[Rule(tool="write", path="*")]),
            append_path=repo_policy,
        )

        seen_choices: list[list[str]] = []

        def _fake_radio(_title, options, default=1):
            seen_choices.append([val for val, _ in options])
            return "n"

        monkeypatch.setattr("strands_code_cli.ui.choice.radio_choice", _fake_radio)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        res_tty = _run(
            handler, _event("write", {"path": ".agent/routing.yaml"}, uid="prot-tty")
        )
        assert isinstance(res_tty, HitlDeny)
        assert seen_choices == [["y", "n", "never"]]

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        buf = _capture_console(monkeypatch)
        monkeypatch.setattr("builtins.input", lambda *a: "always")
        res_always = _run(
            handler, _event("write", {"path": ".agent/policy.toml"}, uid="prot-always")
        )
        assert isinstance(res_always, Proceed)
        assert not repo_policy.exists()
        assert "protected path" in buf.getvalue()
        assert "standing allow rules are disabled" in buf.getvalue()

        monkeypatch.setattr("builtins.input", lambda *a: "never")
        res_never = _run(
            handler, _event("write", {"path": "STRANDS.md"}, uid="prot-never")
        )
        assert isinstance(res_never, HitlDeny)
        reloaded = PolicyConfig.load(home_path=missing_home, repo_path=repo_policy)
        assert len(reloaded.deny) == 1
        assert reloaded.deny[0].path == str((tmp_path / "STRANDS.md").resolve())
        assert len(reloaded.allow) == 0


# ---------------------------------------------------------------------------
# Phase 19.1 Wave 2 adversarial & SDK integration invariants
# ---------------------------------------------------------------------------


class TestWave2HardeningInvariants:
    def test_real_agent_sdk_first_steering_skips_gate_prompt(self, monkeypatch):
        executed: list[str] = []

        @tool
        def shell(command: str) -> str:
            """Execute command."""
            executed.append(command)
            return "ran"

        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(
                AssertionError("steered tool must not prompt")
            ),
        )
        gate = PolicyGateHandler(policy_loader=PolicyConfig.load)
        agent = Agent(
            model=_ToolCallingModel("shell", {"command": "echo pwn"}),
            tools=[shell],
            callback_handler=None,
        )
        InterventionRegistry([gate], agent.hooks)
        slot = register_steering_hook(agent)
        state = SteeringState()
        state.bind_turn("turn-1")
        slot.state = state
        state.note("pivot to safe approach")
        result = agent("go")
        assert executed == []
        assert "redirected-ok" in str(result)

    def test_turn_cancelled_propagates_past_on_error_throw(self):
        class _AbortBroker(ApprovalBroker):
            def request(self, prompt, cancel=None):
                raise TurnCancelled()

        handler = PolicyGateHandler(
            policy_loader=PolicyConfig.load, broker=_AbortBroker()
        )
        assert handler.on_error == "throw"
        with pytest.raises(TurnCancelled):
            _run(handler, _event("shell", {"command": "echo hi"}, uid="tc-1"))
        assert worker_cancelled(EventLoopException(TurnCancelled())) is True

    def test_sha256_batch_distinguishes_identical_first_200_chars(self, monkeypatch):
        prefix = "x = " + "a" * 240 + "\n"
        code_a = prefix + "result = 1"
        code_b = prefix + "result = 2"
        prompts: list[str] = []
        answers = iter(["y", "n"])
        monkeypatch.setattr(
            "builtins.input", lambda *args: (prompts.append("ask"), next(answers))[1]
        )
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        assert isinstance(
            _run(handler, _event("python_repl", {"code": code_a}, uid="sha-1")),
            Proceed,
        )
        assert isinstance(
            _run(handler, _event("python_repl", {"code": code_b}, uid="sha-2")),
            HitlDeny,
        )
        assert len(prompts) == 2

    def test_trust_delegated_still_enforces_deny_outside_write_plan_and_protected(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("SECRET=1\n")
        (tmp_path / ".agent").mkdir()
        main_agent, btw_agent, sub_agent = _FakeAgent(), _FakeAgent(), _FakeAgent()
        cfg = PolicyConfig(
            allow=[Rule(tool="write", path=".agent/*")],
            deny=[Rule(tool="shell", command="rm")],
            options=PolicyOptions(trust_delegated=True),
        )
        handler = PolicyGateHandler(policy_loader=lambda: cfg)
        handler.bind_main_agent(main_agent)
        handler.register_agent(btw_agent, "btw")

        prompts: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda *args: (prompts.append("ask"), "n")[1]
        )
        # Normal non-protected delegated shell auto-trusts:
        assert isinstance(
            _run(handler, _event("shell", {"command": "echo ok"}, sub_agent, "d1")),
            Proceed,
        )
        # Explicit [[deny]] still blocks btw & subagent:
        assert isinstance(
            _run(handler, _event("shell", {"command": "rm -rf ."}, btw_agent, "d2")),
            HitlDeny,
        )
        # Outside-scope write still Denied on delegated agent:
        assert isinstance(
            _run(handler, _event("write", {"path": "/opt/pwn/f.txt"}, sub_agent, "d3")),
            HitlDeny,
        )
        # Sensitive .env read & protected .agent write MUST NOT trust_delegated:
        assert isinstance(
            _run(handler, _event("read", {"path": ".env"}, btw_agent, "d4")),
            HitlDeny,
        )
        assert isinstance(
            _run(
                handler,
                _event("write", {"path": ".agent/policy.toml"}, sub_agent, "d5"),
            ),
            HitlDeny,
        )
        assert len(prompts) == 2

        # Plan / read-only overrides trust_delegated:
        with handler.read_only(btw_agent):
            ro_res = _run(
                handler, _event("shell", {"command": "echo ok"}, btw_agent, "d6")
            )
            assert isinstance(ro_res, HitlDeny)
            assert "Plan mode is read-only" in ro_res.reason

    def test_worker_thread_renders_inside_pump_thread_no_output_context(
        self, monkeypatch
    ):
        main_ident = threading.get_ident()
        broker = ApprovalBroker()
        handler = PolicyGateHandler(policy_loader=PolicyConfig.load, broker=broker)
        buf = _capture_console(monkeypatch)
        render_threads: list[int] = []

        def _fake_input(*args):
            render_threads.append(threading.get_ident())
            return "y"

        monkeypatch.setattr("builtins.input", _fake_input)
        assert not hasattr(gate_module, "output_context")

        result_box: list[Any] = []

        def worker():
            result_box.append(
                _run(handler, _event("shell", {"command": "make test"}, uid="w-1"))
            )

        with broker.pump(threading.Event()):
            thread = threading.Thread(target=worker)
            thread.start()
            while thread.is_alive():
                req = broker.poll(timeout=0.05)
                if req is not None:
                    req.run_prompt()
            thread.join(timeout=5)
        assert render_threads == [main_ident]
        assert isinstance(result_box[0], Proceed)
        rendered = buf.getvalue()
        assert "Approval needed: [main] shell" in rendered
        assert "  Detail: make test" in rendered
        assert "  Risk: Shell command: make test" in rendered
        assert "Approve? [y/n/always/never]" in rendered
