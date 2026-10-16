"""Native setup branch: availability order, pinned Jev list, closed aborts (MODEL-04).

Hermetic: TYPESAFE_API_KEY is deleted by default (the dev shell
exports it — every test pins key presence explicitly), the daemon
probe is stubbed (no network), and both catalog fetches serve
minimal fixtures. Mirrors the TestRouteSetup stub conventions.
"""

from __future__ import annotations

import sys

import pytest
import yaml

import strands_code_cli.routing as routing_mod
from strands_code_cli.router import _SETUP_DONE, dispatch
from strands_code_cli.routing import (
    NATIVE_JEV_ALIAS,
    NATIVE_JEV_PIN,
    EngineResult,
    load_strategy,
)
from strands_code_cli.session_index import SessionIndex


@pytest.fixture(autouse=True)
def _hermetic_native_env(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(routing_mod, "local_engine_ready", lambda base, tag: True)


def _setup_paths(monkeypatch, tmp_path):
    """Point both strategy defaults at tmp files; return (repo, global)."""
    repo = tmp_path / "repo" / ".agent" / "routing.yaml"
    glob = tmp_path / "home" / "routing.yaml"
    monkeypatch.setattr(routing_mod, "default_repo_strategy_path", lambda: repo)
    monkeypatch.setattr(routing_mod, "default_global_strategy_path", lambda: glob)
    return (repo, glob)


def _scripted_radio(monkeypatch, picks):
    """Serve scripted radio picks; return the (title, options) call log."""
    import strands_code_cli.choice as choice_mod

    calls: list = []
    queue = list(picks)

    def _fake(title, options, default=0):
        calls.append((title, list(options)))
        return queue.pop(0)

    monkeypatch.setattr(choice_mod, "radio_choice", _fake)
    return calls


def _scripted_input(monkeypatch, lines):
    """Serve scripted input() lines in order."""
    queue = list(lines)
    monkeypatch.setattr("builtins.input", lambda *args: queue.pop(0))


_SETUP_CHAT = [
    {
        "id": "good/cheap",
        "context_length": 64000,
        "pricing": {"prompt": "0.00000004", "completion": "0"},
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
    },
]
"""Minimal chat catalog: one priced chat-shaped row."""

_SETUP_DECISIONS = [
    {
        "id": "decide/cheap",
        "context_length": 64000,
        "pricing": {"prompt": "0.00000004", "completion": "0"},
        "architecture": {"output_modalities": ["decisions"]},
    },
]
"""Minimal decisions catalog: one priced decisions-shaped row."""


def _setup_catalog(monkeypatch):
    """Serve the minimal catalogs for both setup fetches."""
    import strands_code_cli.live_pricing as live_pricing_mod

    monkeypatch.setattr(
        live_pricing_mod,
        "fetch_openrouter_models",
        lambda: [dict(entry) for entry in _SETUP_CHAT],
    )
    monkeypatch.setattr(
        live_pricing_mod,
        "fetch_openrouter_decision_models",
        lambda: [dict(entry) for entry in _SETUP_DECISIONS],
    )


def _run_setup(tmp_path):
    return dispatch(
        "/route setup", session_id="s", index=SessionIndex(tmp_path / "index")
    )


class TestSetupOrderProposal:
    def test_key_present_proposal_starts_with_native(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["repo", "good/cheap", "decide/cheap", NATIVE_JEV_PIN],
        )
        _scripted_input(monkeypatch, ["", "", "", "deep work goes big", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        assert repo_path.exists() and not global_path.exists()
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["order"] == ["native", "openrouter", "local"]
        assert data["engine"]["native_model"] == NATIVE_JEV_PIN
        assert data["engine"]["skip_notes"] is True
        assert "engine order native, openrouter, local" in message
        assert f"native {NATIVE_JEV_PIN}" in message
        out = capsys.readouterr().out
        assert "Proposed engine order: native, openrouter, local" in out
        assert "local link will skip" not in out

    def test_key_absent_hides_native_from_every_choice(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        calls = _scripted_radio(
            monkeypatch,
            [
                "repo",
                "local",  # builder primary
                "openrouter",  # builder fallback (last: no done round)
                "good/cheap",
                "decide/cheap",
            ],
        )
        _scripted_input(monkeypatch, ["no", "", "", "d", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        offered = [value for _, opts in calls for value, _ in opts]
        assert "native" not in offered
        assert NATIVE_JEV_PIN not in offered
        assert NATIVE_JEV_ALIAS not in offered
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["order"] == ["local", "openrouter"]
        assert "native_model" not in data["engine"]
        assert "engine order local, openrouter" in message
        out = capsys.readouterr().out
        assert "Proposed engine order: openrouter, local" in out

    def test_daemon_unready_prints_skip_note(self, tmp_path, monkeypatch, capsys):
        _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", "good/cheap", "decide/cheap"])
        _scripted_input(monkeypatch, ["", "", "", "d", ""])
        action, _ = _run_setup(tmp_path)
        assert action == "reply"
        assert "local link will skip" in capsys.readouterr().out

    def test_proposal_unrecognized_twice_aborts(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo"])
        _scripted_input(monkeypatch, ["maybe", "huh"])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()


class TestSetupOrderBuilder:
    def test_tty_builder_writes_custom_order_without_openrouter(
        self, tmp_path, monkeypatch
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            [
                "repo",
                "native",  # builder primary
                "local",  # builder fallback (openrouter skipped)
                _SETUP_DONE,
                "good/cheap",  # lone candidate: no done round
                NATIVE_JEV_PIN,  # native pick (no decider: openrouter unlisted)
            ],
        )
        _scripted_input(monkeypatch, ["no", "", "", "d", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["order"] == ["native", "local"]
        assert "decision_model" not in data["engine"]
        assert data["engine"]["local_model"] == "nimble"
        assert data["engine"]["native_model"] == NATIVE_JEV_PIN
        assert "engine order native, local" in message

    def test_off_tty_typed_order_reprompts_once_then_writes(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(
            monkeypatch,
            [
                "2",  # scope: repo
                "no",  # decline the proposal
                "bogus, local",  # attempt 1: one unknown engine
                "local, openrouter",  # attempt 2: valid order written
                "good/cheap",  # candidates
                "decide/cheap",  # decider
                "",  # local tag takes nimble
                "",  # skip notes stay on
                "cheap first",
                "",
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["order"] == ["local", "openrouter"]
        assert "bogus" in capsys.readouterr().out

    def test_off_tty_typed_order_second_unknown_aborts(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(
            monkeypatch,
            ["2", "no", "bogus", "also-bogus"],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_tty_builder_esc_aborts(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", None])  # ESC at primary
        _scripted_input(monkeypatch, ["no"])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()


class TestSetupNativePick:
    def _run_with_native_pick(self, tmp_path, monkeypatch, pick):
        _setup_catalog(monkeypatch)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        calls = _scripted_radio(
            monkeypatch, ["repo", "good/cheap", "decide/cheap", pick]
        )
        _scripted_input(monkeypatch, ["", "", "", "d", ""])
        return _run_setup(tmp_path), calls

    def test_native_offer_is_exactly_pin_and_alias(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        (action, _), calls = self._run_with_native_pick(
            tmp_path, monkeypatch, NATIVE_JEV_PIN
        )
        assert action == "reply"
        native_calls = [opts for title, opts in calls if "Jev" in title]
        assert len(native_calls) == 1
        assert [value for value, _ in native_calls[0]] == [
            NATIVE_JEV_PIN,
            NATIVE_JEV_ALIAS,
        ]
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["native_model"] == NATIVE_JEV_PIN

    def test_alias_choice_prints_drift_warning(self, tmp_path, monkeypatch, capsys):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        (action, _), _ = self._run_with_native_pick(
            tmp_path, monkeypatch, NATIVE_JEV_ALIAS
        )
        assert action == "reply"
        out = capsys.readouterr().out
        assert "moving alias" in out
        assert "snapshot" in out
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["native_model"] == NATIVE_JEV_ALIAS

    def test_pin_choice_prints_no_warning(self, tmp_path, monkeypatch, capsys):
        _setup_paths(monkeypatch, tmp_path)
        (action, _), _ = self._run_with_native_pick(
            tmp_path, monkeypatch, NATIVE_JEV_PIN
        )
        assert action == "reply"
        assert "moving alias" not in capsys.readouterr().out


class TestSetupAbortAndRoundTrip:
    def test_abort_at_native_pick_writes_nothing(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", "good/cheap", "decide/cheap", None])
        _scripted_input(monkeypatch, ["", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_abort_at_skip_notes_writes_nothing(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", "good/cheap", "decide/cheap"])
        _scripted_input(monkeypatch, ["", "", "maybe", "huh"])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_payload_round_trips_through_loader(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["repo", "good/cheap", "decide/cheap", NATIVE_JEV_PIN],
        )
        _scripted_input(monkeypatch, ["", "", "no", "d", ""])
        action, _ = _run_setup(tmp_path)
        assert action == "reply"
        strategy = load_strategy(
            global_path=tmp_path / "absent.yaml", repo_path=repo_path
        )
        assert strategy is not None
        assert strategy.engine.order == ["native", "openrouter", "local"]
        assert strategy.engine.native_model == NATIVE_JEV_PIN
        assert strategy.engine.skip_notes is False
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["skip_notes"] is False


def _run_validate(tmp_path):
    return dispatch(
        "/route validate", session_id="s", index=SessionIndex(tmp_path / "index")
    )


def _write_strategy_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


_NATIVE_FILE = (
    "candidates: [{id: a/1}]\n"
    "directives: d\n"
    f"engine: {{order: [native], native_model: {NATIVE_JEV_PIN}}}\n"
)
"""Valid native-listed strategy for the live-ping tests."""


def _stub_ping(monkeypatch, result):
    """Serve one canned ping result; return the call-kwarg log."""
    calls: list = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(routing_mod, "decide_via_typesafe", _fake)
    return calls


class TestValidatePing:
    def test_ping_ok_names_serving_snapshot(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(repo_path, _NATIVE_FILE)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        calls = _stub_ping(
            monkeypatch,
            EngineResult(answers={"ping": {"choice": "a"}}, model="jev-1.13.0"),
        )
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy VALID")
        assert "native: engine ok (snapshot jev-1.13.0)" in message
        assert len(calls) == 1
        assert calls[0]["native_model"] == NATIVE_JEV_PIN
        assert list(calls[0]["questions"]) == ["ping"]
        assert calls[0]["questions"]["ping"]["type"] == "choice"

    @pytest.mark.parametrize("code", ["HTTP 401", "HTTP 403"])
    def test_ping_rejected_key_fails_with_key_fix(self, tmp_path, monkeypatch, code):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(repo_path, _NATIVE_FILE)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        _stub_ping(monkeypatch, EngineResult(answers=None, error=code))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy INVALID")
        assert "native: INVALID — TypeSafe key rejected" in message
        assert "fix: set TYPESAFE_API_KEY" in message

    def test_ping_unknown_model_fails_with_model_fix(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(repo_path, _NATIVE_FILE)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        _stub_ping(monkeypatch, EngineResult(answers=None, error="HTTP 400"))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy INVALID")
        assert "native: INVALID — unknown native model" in message
        assert f"fix: set engine.native_model to {NATIVE_JEV_PIN}" in message

    @pytest.mark.parametrize("error", ["timeout", "refused", "unreachable"])
    def test_ping_transport_failure_warns_leaving_valid(
        self, tmp_path, monkeypatch, error
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(repo_path, _NATIVE_FILE)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        _stub_ping(monkeypatch, EngineResult(answers=None, error=error))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy VALID")
        assert f"native ping inconclusive ({error})" in message

    def test_key_absent_skips_ping_without_calling(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(repo_path, _NATIVE_FILE)
        calls = _stub_ping(monkeypatch, EngineResult(answers={"ping": {}}, model="x"))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy VALID")
        assert "native ping skipped" in message
        assert calls == []

    def test_no_ping_when_native_unlisted(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(
            repo_path,
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [local], local_model: nimble}\n",
        )
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        calls = _stub_ping(monkeypatch, EngineResult(answers={"ping": {}}, model="x"))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy VALID")
        assert "native:" not in message
        assert calls == []

    def test_no_ping_when_file_invalid(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _write_strategy_file(
            repo_path,
            "candidates: []\n"
            "directives: d\n"
            f"engine: {{order: [native], native_model: {NATIVE_JEV_PIN}}}\n",
        )
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-native-key")
        calls = _stub_ping(monkeypatch, EngineResult(answers={"ping": {}}, model="x"))
        action, message = _run_validate(tmp_path)
        assert action == "reply"
        assert message.startswith("Routing strategy INVALID")
        assert "native: engine ok" not in message
        assert "native ping" not in message
        assert calls == []
