"""Tracer: resolve + convert + swap seam + discovery fail-soft on replay models.

Tracer observations (recorded 2026-09-27, strands-harness 0.1.2, strands-agents
1.57.0 — no live Bedrock touched; discovery fail-soft path only):

- Swap winner: IN-PLACE ``agent.model = resolve_model(...)``. A replay agent
  assigned a resolved ``BedrockModel`` kept ``agent.messages`` intact; the
  rebuild fallback (``build_agent`` on the same session id) is unnecessary.
  The losing rebuild path is deleted, not kept as an option.
- Snapshot mechanics: live blob
  ``.agent/sessions/session/<uuid>/scopes/agent/default/snapshots/snapshot_latest.json``
  holds ``{"scope", "schema_version", "created_at", "data": {"messages": [...]},
  "app_data"}``. Wholesale ``agent.messages`` replacement persists through the
  snapshot layer on flush — compact/clear mutate ``agent.messages`` in place
  and let ``explicit_save`` flush; never touch blobs by hand.
- Pricing re-check date 2026-09-27, canonical
  ``https://aws.amazon.com/bedrock/pricing`` (via 2026 guides, convergent):
  Sonnet 4.6 $3/$15, Opus 4.6/4.8 $5/$25, Haiku 4.5 $1/$5, Sonnet 5 promo
  expired 2026-08-31 (now $3/$15), Nova Micro/Lite/Pro
  $0.035/$0.14, $0.06/$0.24, $0.80/$3.20 per 1M in/out.
- Window sources: harness Claude map (opus-/sonnet-/fable- 128K, haiku- 64K)
  plus 1M for Opus/Sonnet 4.6 (builder cost guide); unknown ids fall back to
  tokens-without-% and tokens-without-money (D-02/D-07).
- Env note: only the ``bedrock`` provider's SDK deps are installed here, so
  ``resolve_model`` for anthropic/openai/litellm/ollama ids raises ImportError
  (missing optional package), not ValueError. Unknown *provider names* still
  raise ValueError listing supported providers. ARN prefixes (``us.``/``eu.`` /
  ``global.``) are preserved verbatim by ``resolve_model``.
- Conversion table: reasoningContent{reasoningText+signature} -> {"text"} on
  non-reasoning targets (DeepSeek-drop mirror + warn); toolUse/toolResult
  blocks byte-identical; trim only at pair boundaries; image blocks become
  placeholder text on media-less targets.

All tests run offline with a replay model double (copied pattern, no imports
from other test modules, no live Bedrock calls).
"""

from __future__ import annotations

import uuid
import warnings
from pathlib import Path
from typing import Any

import pytest
from strands.models.model import Model
from strands_harness import create_harness
from strands_harness.models import resolve_model

from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli import model_switch
from strands_code_cli.model_switch import (
    apply_switch,
    convert_history,
    discover_models,
    estimate_fit,
)


# ----------------------------------------------------------------------
# Offline replay double (pattern copied from tests/test_kill_resume.py)
# ----------------------------------------------------------------------


class _ReplayModel(Model):
    """Offline model double streaming one canned text turn."""

    def __init__(self, text: str) -> None:
        self._text = text

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(  # type: ignore[override]
        self, output_model: Any, prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> Any:
        raise NotImplementedError("offline test double")
        yield  # pragma: no cover - keeps this an async generator

    async def stream(self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any):  # type: ignore[override]
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self._text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 0},
            }
        }


def _make_replay_agent(session_id: str, session_dir: Path, text: str = "canned"):
    """Build a harness agent with the offline replay double."""
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    return create_harness(
        tools=[interpreter.get_tool()],
        instructions=CODE_AGENT_INSTRUCTIONS,
        session={"id": session_id, "dir": str(session_dir)},
        model=_ReplayModel(text),
        memory=False,
        skills=False,
    )


def _fixture_history() -> list[dict[str, Any]]:
    """History with reasoningContent + toolUse/toolResult pair + image block."""
    return [
        {"role": "user", "content": [{"text": "run the thing"}]},
        {
            "role": "assistant",
            "content": [
                {"reasoningContent": {"reasoningText": {"text": "let me think", "signature": "sig-1"}}},
                {"toolUse": {"toolUseId": "t-1", "name": "python_repl", "input": {"code": "1+1"}}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t-1",
                        "status": "success",
                        "content": [{"text": "2"}],
                    }
                }
            ],
        },
        {"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": b"0123456789"}}}]} ,
    ]


# ----------------------------------------------------------------------
# resolve_model spike: one id per provider family + invalid provider
# ----------------------------------------------------------------------


class TestResolveSpike:
    def test_bedrock_global_id_resolves(self):
        model = resolve_model(
            "bedrock/global.anthropic.claude-sonnet-4-6",
            default="bedrock/global.anthropic.claude-opus-5",
        )
        assert type(model).__name__ == "BedrockModel"
        assert model.get_config().get("model_id") == "global.anthropic.claude-sonnet-4-6"

    def test_bare_bedrock_id_defaults_to_bedrock(self):
        model = resolve_model("anthropic.claude-sonnet-4-6", default="bedrock/x")
        assert type(model).__name__ == "BedrockModel"

    def test_arn_prefix_preserved_verbatim(self):
        model = resolve_model("us.anthropic.claude-sonnet-4-6", default="bedrock/x")
        assert model.get_config().get("model_id") == "us.anthropic.claude-sonnet-4-6"
        assert model.get_config().get("model_id", "").startswith("us.")

    def test_invalid_provider_lists_supported(self):
        with pytest.raises(ValueError, match="Supported providers"):
            resolve_model("bogus/some-model", default="bedrock/x")

    @pytest.mark.parametrize(
        "selection",
        [
            "anthropic/claude-3-7-sonnet-latest",
            "openai/gpt-4o",
            "litellm/openai/gpt-4o",
            "ollama/llama3",
        ],
    )
    def test_non_bedrock_selection_never_crashes_resolve_contract(self, selection):
        """Known provider names resolve or fail only on missing optional deps.

        Only bedrock's SDK deps are installed in this env, so these raise
        ImportError. The contract pinned here: never ValueError (the name is
        valid), never a traceback-prone path — callers surface it as a reply.
        """
        try:
            model = resolve_model(selection, default="bedrock/x")
        except ImportError:
            return  # fail-soft: valid name, uninstallable provider locally
        assert model is not None


# ----------------------------------------------------------------------
# Swap-seam spike: in-place assignment wins, rebuild path deleted
# ----------------------------------------------------------------------


class TestSwapSeam:
    def test_in_place_swap_keeps_messages_and_next_turn_succeeds(self, tmp_path):
        session_id = str(uuid.uuid4())
        agent = _make_replay_agent(session_id, tmp_path / "sessions", "first")
        agent("hello one")
        before = len(agent.messages)

        new_id = "bedrock/global.anthropic.claude-sonnet-4-6"
        model, resolved_id = apply_switch(agent, new_id)
        assert resolved_id == "global.anthropic.claude-sonnet-4-6"
        assert type(agent.model).__name__ == "BedrockModel"
        assert len(agent.messages) == before  # history untouched by the swap

        # Swap back to the offline double: the next turn still succeeds and
        # the pre-swap transcript survives the round trip.
        agent.model = _ReplayModel("second")
        agent("hello two")
        texts = [
            block.get("text", "")
            for message in agent.messages
            for block in message.get("content", [])
            if "text" in block
        ]
        assert "hello one" in texts
        assert "hello two" in texts

    def test_apply_switch_unknown_provider_raises_value_error(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        with pytest.raises(ValueError, match="Supported providers"):
            apply_switch(agent, "bogus/model")


# ----------------------------------------------------------------------
# convert_history spike: the conversion table
# ----------------------------------------------------------------------


class TestConvertHistory:
    def test_reasoning_to_text_on_non_reasoning_target(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = convert_history(
                _fixture_history(),
                "bedrock/global.anthropic.claude-sonnet-4-6",
                "openai/nemotron-70b",
            )
        assert any("reasoning" in str(w.message).lower() for w in caught)
        assistant_blocks = out[1]["content"]
        assert all("reasoningContent" not in block for block in assistant_blocks)
        texts = [block.get("text", "") for block in assistant_blocks]
        assert "let me think" in texts  # trace preserved as text, signature dropped

    def test_reasoning_kept_verbatim_on_reasoning_target(self):
        out = convert_history(
            _fixture_history(),
            "bedrock/global.anthropic.claude-sonnet-4-6",
            "bedrock/global.anthropic.claude-opus-5",
        )
        assert out[1]["content"][0] == {"reasoningContent": {"reasoningText": {"text": "let me think", "signature": "sig-1"}}}

    def test_tool_pairs_byte_identical(self):
        src = _fixture_history()
        out = convert_history(src, "bedrock/a", "anthropic/b")
        assert out[1]["content"][1] == src[1]["content"][1]
        assert out[2] == src[2]

    def test_image_to_placeholder_on_media_less_target(self):
        out = convert_history(_fixture_history(), "bedrock/a", "openai/nemotron-70b")
        last = out[-1]["content"][0]
        assert "text" in last and "reasoningContent" not in last
        assert "image" in last["text"].lower() or "png" in last["text"].lower()

    def test_image_kept_on_media_capable_target(self):
        src = _fixture_history()
        out = convert_history(src, "bedrock/a", "bedrock/b")
        assert out[-1] == src[-1]

    def test_does_not_mutate_input(self):
        src = _fixture_history()
        snapshot = [dict(m) for m in src]
        convert_history(src, "bedrock/a", "openai/nemotron-70b")
        assert [m["role"] for m in src] == [m["role"] for m in snapshot]
        assert src[1]["content"][0] == snapshot[1]["content"][0]


# ----------------------------------------------------------------------
# estimate_fit spike: local estimator vs MODEL_LIMITS
# ----------------------------------------------------------------------


class TestEstimateFit:
    def test_small_history_fits(self):
        fits, pct, tokens = estimate_fit(
            [{"role": "user", "content": [{"text": "hi"}]}], "bedrock/global.anthropic.claude-sonnet-4-6"
        )
        assert fits is True
        assert tokens > 0
        assert pct is not None and pct < 70.0

    def test_unknown_id_reports_no_percent_but_still_fits_small(self):
        fits, pct, tokens = estimate_fit(
            [{"role": "user", "content": [{"text": "hi"}]}], "mystery/acme-1"
        )
        assert pct is None
        assert tokens > 0
        assert fits is True  # unknown window: convert, never force-compact

    def test_huge_history_does_not_fit(self):
        big = [{"role": "user", "content": [{"text": "x" * 4000}]} for _ in range(200)]
        fits, pct, tokens = estimate_fit(big, "bedrock/anthropic.claude-3-haiku-20240307")
        assert fits is False
        assert pct is not None and pct >= 70.0


# ----------------------------------------------------------------------
# Discovery spike: fail-soft offline, verbatim ids when online
# ----------------------------------------------------------------------


class TestDiscoverModels:
    def test_offline_fallback_never_raises(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _no_boto3(name, *args, **kwargs):
            if name == "boto3" or name.startswith("boto3."):
                raise ImportError("No module named 'boto3' (offline probe)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_boto3)
        options, offline = discover_models(
            region="us-east-1", configured=["bedrock/global.anthropic.claude-opus-5"]
        )
        assert offline is True
        assert "bedrock/global.anthropic.claude-opus-5" in options

    def test_credential_failure_falls_back_without_traceback(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("boto3")

        class _Denied(Exception):
            pass

        class _Client:
            def list_foundation_models(self, **kwargs):
                raise _Denied("Unable to locate credentials")

            def list_inference_profiles(self, **kwargs):
                raise _Denied("Unable to locate credentials")

        fake.client = lambda *a, **k: _Client()  # noqa: E731
        monkeypatch.setitem(sys.modules, "boto3", fake)
        options, offline = discover_models(region="us-east-1", configured=["bedrock/x"])
        assert offline is True
        assert options == ["bedrock/x"]

    def test_online_results_verbatim(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("boto3")

        class _Client:
            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        {
                            "modelId": "us.anthropic.claude-sonnet-4-6",
                            "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/us.anthropic.claude-sonnet-4-6",
                            "inferenceTypesSupported": ["ON_DEMAND"],
                        },
                        {
                            "modelId": "provisioned-only",
                            "modelArn": "arn:x",
                            "inferenceTypesSupported": ["PROVISIONED"],
                        },
                    ]
                }

            def list_inference_profiles(self, **kwargs):
                return {
                    "inferenceProfileSummaries": [
                        {"inferenceProfileArn": "arn:aws:bedrock:us-east-1:123:inference-profile/global.anthropic.claude-opus-5"}
                    ]
                }

        fake.client = lambda *a, **k: _Client()  # noqa: E731
        monkeypatch.setitem(sys.modules, "boto3", fake)
        options, offline = discover_models(region="us-east-1")
        assert offline is False
        assert "us.anthropic.claude-sonnet-4-6" in options  # prefix verbatim
        assert "provisioned-only" not in options  # ON_DEMAND filter
        assert any("inference-profile" in o for o in options)


# ----------------------------------------------------------------------
# Compact-replay spike on the replay model
# ----------------------------------------------------------------------


class TestCompactReplaySpike:
    def test_compact_then_replay_on_replay_model(self, tmp_path):
        from strands_code_cli.cost_context import SUMMARY_MARKER, compact_messages

        session_id = str(uuid.uuid4())
        agent = _make_replay_agent(session_id, tmp_path / "sessions", "after")
        agent("first ask")
        agent("second ask")
        n_before = len(agent.messages)

        kept = compact_messages(
            agent,
            summarize=lambda old: f"summary of {len(old)} messages",
            keep_recent=2,
        )
        assert kept >= 1
        assert len(agent.messages) < n_before
        texts = [
            block.get("text", "")
            for message in agent.messages
            for block in message.get("content", [])
            if "text" in block
        ]
        assert any(SUMMARY_MARKER in t for t in texts)  # untrusted-marker prefix
        assert any("second ask" in t for t in texts)  # last user message replayed

        agent("third ask")  # replay model still turns after compaction
        assert any(
            "third ask" in block.get("text", "")
            for message in agent.messages
            for block in message.get("content", [])
            if "text" in block
        )

    def test_module_exports_tracer_surface(self):
        assert callable(model_switch.convert_history)
        assert callable(model_switch.discover_models)
        assert callable(model_switch.estimate_fit)
        assert callable(model_switch.apply_switch)
        assert isinstance(model_switch.MODEL_REFUSAL, str) and "idle prompt" in model_switch.MODEL_REFUSAL


# ----------------------------------------------------------------------
# P1: /model switching — discovery, convert-or-compact, idle-only swap
# ----------------------------------------------------------------------


class TestModelRouterBranch:
    def test_valid_selection_returns_model_action(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        sid = index.mint()
        action, message = dispatch(
            "/model bedrock/global.anthropic.claude-sonnet-4-6",
            session_id=sid,
            index=index,
        )
        assert action == "model"
        assert message == "bedrock/global.anthropic.claude-sonnet-4-6"

    def test_router_never_swaps_inline(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        before = agent.model
        action, _ = dispatch(
            "/model bedrock/global.anthropic.claude-sonnet-4-6",
            session_id=index.mint(),
            index=index,
        )
        assert action == "model"
        assert agent.model is before  # dispatch validates only; loop owns the swap

    def test_unknown_provider_reply_lists_providers(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch("/model bogus/xyz", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "Supported providers" in message

    def test_uninstallable_provider_reply_fail_soft(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model anthropic/claude-3-7-sonnet-latest",
            session_id=index.mint(),
            index=index,
        )
        assert action == "reply"
        assert "anthropic/claude-3-7-sonnet-latest" in message

    def test_arn_prefix_preserved_verbatim(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model us.anthropic.claude-sonnet-4-6",
            session_id=index.mint(),
            index=index,
        )
        assert (action, message) == ("model", "us.anthropic.claude-sonnet-4-6")

    def test_bare_model_offline_lists_configured(self, tmp_path, monkeypatch):
        import sys

        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model",
            session_id=index.mint(),
            index=index,
            current_model="bedrock/global.anthropic.claude-opus-5",
        )
        assert action == "reply"
        assert "bedrock/global.anthropic.claude-opus-5" in message


class TestIdleOnlySwap:
    def test_idle_switch_continues_conversation(self, tmp_path):
        from strands_code_cli.loop import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "before")
        agent("first ask")
        agent.messages.extend(_fixture_history())

        resolved, reply = apply_model_action(
            agent,
            "bedrock/global.anthropic.claude-sonnet-4-6",
            turn_running=False,
            current_model="bedrock/global.anthropic.claude-opus-5",
        )
        assert resolved == "global.anthropic.claude-sonnet-4-6"
        assert reply.startswith("Model: bedrock/global.anthropic.claude-sonnet-4-6")
        assert "messages kept" in reply
        assert type(agent.model).__name__ == "BedrockModel"
        # Tool pairs survived conversion byte-identical.
        uses = {
            block["toolUse"]["toolUseId"]
            for message in agent.messages
            for block in message.get("content", [])
            if "toolUse" in block
        }
        results = {
            block["toolResult"]["toolUseId"]
            for message in agent.messages
            for block in message.get("content", [])
            if "toolResult" in block
        }
        assert uses == results != set()

        agent.model = _ReplayModel("after")  # back to offline for the next turn
        agent("second ask")
        texts = [
            block.get("text", "")
            for message in agent.messages
            for block in message.get("content", [])
            if "text" in block
        ]
        assert "first ask" in texts and "second ask" in texts

    def test_oversize_switch_compacts(self, tmp_path):
        from strands_code_cli.loop import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(
            {"role": "user", "content": [{"text": "y" * 400}]} for _ in range(1500)
        )
        resolved, reply = apply_model_action(
            agent,
            "bedrock/anthropic.claude-3-haiku-20240307",
            turn_running=False,
            current_model="bedrock/global.anthropic.claude-opus-5",
        )
        assert resolved is not None
        assert "compacted" in reply

    def test_mid_turn_refusal_exact_text_model_unchanged(self, tmp_path):
        from strands_code_cli.loop import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        before = agent.model
        resolved, reply = apply_model_action(
            agent,
            "bedrock/global.anthropic.claude-sonnet-4-6",
            turn_running=True,
            current_model="bedrock/global.anthropic.claude-opus-5",
        )
        assert resolved is None
        assert reply == "Model switches apply at the idle prompt — wait for the turn to finish."
        assert agent.model is before


class TestModelPersistence:
    def test_save_model_choice_round_trip_no_secrets(self, tmp_path):
        from strands_code_cli.provider_config import ProviderConfig

        path = tmp_path / "config.yaml"
        config = ProviderConfig(model="bedrock/old", base_url="https://proxy.local")
        config.save_model_choice("bedrock/global.anthropic.claude-sonnet-4-6", path)
        reloaded = ProviderConfig.load(path)
        assert reloaded.model == "bedrock/global.anthropic.claude-sonnet-4-6"
        assert reloaded.base_url == "https://proxy.local"  # non-secret host kept
        text = path.read_text(encoding="utf-8").lower()
        assert "api_key" not in text and "bearer" not in text and "secret" not in text

    def test_model_for_config_shapes(self):
        from strands_code_cli.main import model_for_config

        assert model_for_config(None) is None
        assert (
            model_for_config("bedrock/global.anthropic.claude-sonnet-4-6")
            == "bedrock/global.anthropic.claude-sonnet-4-6"
        )
        # openai SDK not installed here → verbatim string fallback, never a raise.
        assert (
            model_for_config("openai/nemotron-70b", "https://proxy.local/v1")
            == "openai/nemotron-70b"
        )
