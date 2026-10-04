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
- Env note: the ``bedrock`` SDK deps plus the ``litellm`` extra are
  installed here, so ``resolve_model`` for anthropic/openai/ollama ids raises
  ImportError (missing optional package), not ValueError. Unknown *provider
  names* still raise ValueError listing supported providers. ARN prefixes
  (``us.``/``eu.`` / ``global.``) are preserved verbatim by ``resolve_model``.
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
from strands_code_cli import model_capabilities, model_switch
from strands_code_cli.model_switch import (
    TRACE_LABEL,
    apply_switch,
    convert_history,
    discover_models,
    estimate_fit,
)


@pytest.fixture(autouse=True)
def _no_user_overrides(monkeypatch):
    """Verdict tests assume shipped tables; a real user file must not leak in."""
    monkeypatch.setattr(model_capabilities, "active_overrides", lambda: [])


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


class TestNormalizeModelRef:
    _ARN = (
        "arn:aws:bedrock:us-west-2:1:inference-profile/"
        "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    def test_profile_arn_maps_to_tail(self):
        from strands_code_cli.model_switch import normalize_model_ref

        assert (
            normalize_model_ref(self._ARN)
            == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )

    @pytest.mark.parametrize(
        "selection",
        [
            "us.anthropic.claude-sonnet-4-6",
            "anthropic.claude-sonnet-4-6",
            "bedrock/global.anthropic.claude-opus-5",
            "litellm/openrouter/x",
            "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-v2",
            "",
        ],
    )
    def test_everything_else_passes_through(self, selection):
        from strands_code_cli.model_switch import normalize_model_ref

        assert normalize_model_ref(selection) == selection

    def test_apply_switch_accepts_full_profile_arn(self):
        from types import SimpleNamespace

        from strands_code_cli.model_switch import apply_switch

        agent = SimpleNamespace(model="old", messages=[])
        _model, resolved = apply_switch(agent, self._ARN)
        assert type(agent.model).__name__ == "BedrockModel"
        assert resolved == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


class TestCanonicalPrefixHash:
    def test_stable_across_thinking_and_media_conversion(self):
        import warnings

        from strands_code_cli.model_switch import canonical_prefix_hash

        fixture = _fixture_history()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Nemotron strips BOTH thinking and media: the canonical form
            # must survive the full round-trip.
            converted = convert_history(
                fixture, "bedrock/global.anthropic.claude-sonnet-4-6", "openai/nemotron-70b"
            )
        assert _reasoning_blocks(converted) == []
        assert canonical_prefix_hash(converted) == canonical_prefix_hash(fixture)

    def test_breaks_on_real_edit(self):
        import copy

        from strands_code_cli.model_switch import canonical_prefix_hash

        fixture = _fixture_history()
        edited = copy.deepcopy(fixture)
        edited[0]["content"][0]["text"] = "run something else"
        assert canonical_prefix_hash(edited) != canonical_prefix_hash(fixture)

    def test_legacy_label_still_stripped(self):
        import copy
        import warnings

        from strands_code_cli.model_switch import (
            _LEGACY_TRACE_LABELS,
            TRACE_LABEL,
            canonical_prefix_hash,
        )

        fixture = _fixture_history()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            converted = convert_history(
                fixture, "bedrock/global.anthropic.claude-sonnet-4-6", "openai/nemotron-70b"
            )
        # Rewrite new labels to the retired bracketed shape: pre-upgrade
        # sessions must keep matching the stash.
        legacy = copy.deepcopy(converted)
        for message in legacy:
            for block in message.get("content", []):
                text = block.get("text", "")
                if text.startswith(TRACE_LABEL):
                    block["text"] = _LEGACY_TRACE_LABELS[0] + text[len(TRACE_LABEL):]
        assert any(
            block.get("text", "").startswith(_LEGACY_TRACE_LABELS[0])
            for message in legacy
            for block in message.get("content", [])
        )
        assert canonical_prefix_hash(legacy) == canonical_prefix_hash(fixture)


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
        # Trace preserved as LABELED text (signature dropped): weak models
        # mimic unlabeled traces as assistant speech.
        assert out[1]["content"][0] == {"text": f"{TRACE_LABEL}\nlet me think"}

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
# Capability almanac: fail-closed thinking, fail-open media (G-05-1g)
# ----------------------------------------------------------------------


def _reasoning_blocks(messages):
    return [
        block
        for message in messages
        for block in message.get("content", [])
        if "reasoningContent" in block
    ]


class TestCapabilityAlmanac:
    def test_gemma_target_strips_thinking(self):
        # UAT crash repro: Haiku thinking reached Gemma verbatim and
        # Bedrock rejected the turn. Now it converts to text.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = convert_history(
                _fixture_history(),
                "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                "google.gemma-3-27b-it",
            )
        assert _reasoning_blocks(out) == []
        assert out[1]["content"][0] == {"text": f"{TRACE_LABEL}\nlet me think"}
        assert any("reasoning" in str(w.message).lower() for w in caught)

    def test_unknown_target_strips_fail_closed(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = convert_history(
                _fixture_history(), "bedrock/anthropic.claude-x", "bedrock/acme-future-1"
            )
        assert _reasoning_blocks(out) == []

    def test_cross_vendor_strips_even_when_harness_listed(self):
        # qwen carries harness thinking levels, yet anthropic thinking must
        # not cross vendors (foreign signatures); qwen-to-qwen round-trips.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cross = convert_history(
                _fixture_history(), "bedrock/anthropic.claude-x", "qwen.qwen3-32b-v1:0"
            )
            same = convert_history(
                _fixture_history(), "qwen.qwen3-a", "qwen.qwen3-32b-v1:0"
            )
        assert _reasoning_blocks(cross) == []  # foreign signatures never cross vendors
        assert len(_reasoning_blocks(same)) == 1

    def test_fallback_allowlist_without_harness(self, monkeypatch):
        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.model_switch import supports_reasoning

        monkeypatch.setattr(model_switch_mod, "_harness_supports_thinking", None)
        assert supports_reasoning("bedrock/anthropic.claude-opus-5") is True
        assert supports_reasoning("qwen.qwen3-32b-v1:0") is False  # fail-closed

    def test_harness_verdicts_for_bedrock_families(self):
        from strands_code_cli.model_switch import supports_reasoning

        assert supports_reasoning("bedrock/anthropic.claude-opus-5") is True
        assert supports_reasoning("qwen.qwen3-32b-v1:0") is True
        assert supports_reasoning("bedrock/openai.gpt-oss-120b-1:0") is True
        assert supports_reasoning("google.gemma-3-27b-it") is False
        assert supports_reasoning("bedrock/deepseek.r1-v1:0") is False
        assert supports_reasoning("openai/gpt-4o") is False  # adapter path unverified
        assert supports_reasoning("litellm/openrouter/qwen/qwen3-32b") is False

    def test_unsigned_thinking_becomes_text_even_when_capable(self):
        src = [
            {"role": "user", "content": [{"text": "hi"}]},
            {
                "role": "assistant",
                "content": [{"reasoningContent": {"reasoningText": {"text": "hmm"}}}],
            },
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = convert_history(
                src,
                "bedrock/anthropic.claude-opus-5",
                "bedrock/anthropic.claude-sonnet-4-6",
            )
        assert _reasoning_blocks(out) == []
        assert out[1]["content"][0] == {"text": f"{TRACE_LABEL}\nhmm"}

    def test_redacted_thinking_round_trips_and_drops_cleanly(self):
        src = [
            {
                "role": "assistant",
                "content": [{"reasoningContent": {"redactedContent": "enc"}}],
            },
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            kept = convert_history(
                src,
                "bedrock/anthropic.claude-opus-5",
                "bedrock/anthropic.claude-sonnet-4-6",
            )
            dropped = convert_history(
                src, "bedrock/anthropic.claude-opus-5", "google.gemma-3-27b-it"
            )
        assert kept[0]["content"][0] == src[0]["content"][0]
        assert dropped[0]["content"] == []  # no blank text block emitted

    def test_same_vendor_across_id_forms(self):
        from strands_code_cli.model_switch import same_vendor

        assert same_vendor(
            "bedrock/global.anthropic.claude-opus-5", "us.anthropic.claude-haiku-1"
        )
        assert same_vendor("anthropic/claude-x", "bedrock/anthropic.claude-y")
        assert not same_vendor("bedrock/anthropic.claude-x", "qwen.qwen3-32b-v1:0")

    def test_media_rules_nova_micro_less_nova_pro_ok(self):
        from strands_code_cli.model_switch import supports_media

        assert supports_media("amazon.nova-micro-v1:0") is False
        assert supports_media("amazon.nova-lite-v1:0") is False
        assert supports_media("amazon.nova-pro-v1:0") is True
        # Nova 2 Lite takes TEXT+IMAGE+VIDEO (Bedrock modalities probe):
        # the nova-1 rows must not swallow the nova-2 generation.
        assert supports_media("amazon.nova-2-lite-v1:0") is True
        assert supports_media("global.amazon.nova-2-lite-v1:0") is True
        assert supports_media("meta.llama3-70b-instruct-v1:0") is False
        assert supports_media("bedrock/mystery-vision-1") is True  # fail-open

    def test_media_bedrock_openai_less_direct_openai_ok(self):
        from strands_code_cli.model_switch import supports_media

        # Harness-verified: OpenAI-family Converse models reject image
        # fields; direct OpenAI vision models are unaffected.
        assert supports_media("bedrock/openai.gpt-oss-120b-1:0") is False
        assert supports_media("openai.gpt-oss-120b-1:0") is False  # bare = bedrock
        assert supports_media("openai/gpt-4o") is True


class TestAggregatorIds:
    def test_true_vendor_and_family_parsing(self):
        from strands_code_cli.model_switch import _base_key, _vendor_family, _vendor_of

        entry = "litellm/openrouter/qwen/qwen3-32b"
        assert _base_key(entry) == "qwen/qwen3-32b"
        assert _vendor_of(entry) == "qwen"
        assert _vendor_family("qwen/qwen3-32b") == ("qwen", "qwen3")

    def test_reasoning_fail_closed_for_aggregators(self):
        from strands_code_cli.model_switch import supports_reasoning

        # Even true-vendor anthropic via an aggregator strips: adapter
        # translation of thinking blocks is unverified there.
        assert supports_reasoning("litellm/openrouter/anthropic/claude-x") is False

    def test_media_rules_see_true_vendor(self):
        from strands_code_cli.model_switch import supports_media

        assert supports_media("litellm/openrouter/meta/llama-x") is False
        assert supports_media("litellm/openrouter/qwen/qwen3-32b") is True

    def test_cascade_groups_aggregator_under_true_vendor(self):
        from strands_code_cli.model_switch import build_model_tree

        tree = build_model_tree(
            ["qwen.qwen3-32b-v1:0", "litellm/openrouter/qwen/qwen3-32b"]
        )
        assert [vendor for vendor, _ in tree] == ["qwen"]
        families = dict(tree[0][1])
        assert sorted(families) == ["qwen3"]
        assert len(families["qwen3"]) == 2  # bedrock id + aggregator route


class TestStreamingTools:
    def test_llama_families_warn_rest_fail_open(self):
        from strands_code_cli.model_switch import supports_streaming_tools

        assert supports_streaming_tools("us.meta.llama4-scout-17b-instruct-v1:0") is False
        assert supports_streaming_tools("meta.llama4-maverick-17b-instruct-v1:0") is False
        assert supports_streaming_tools("us.meta.llama3-3-70b-instruct-v1:0") is False
        assert (
            supports_streaming_tools("us.anthropic.claude-haiku-4-5-20251001-v1:0")
            is True
        )
        assert supports_streaming_tools("bedrock/mystery-model-1") is True

    def test_override_beats_shipped_rows(self, monkeypatch):
        import strands_code_cli.model_capabilities as caps
        from strands_code_cli.model_capabilities import CapabilityOverride
        from strands_code_cli.model_switch import supports_streaming_tools

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="meta", streaming_tools=True)],
        )
        assert supports_streaming_tools("us.meta.llama4-scout-17b-instruct-v1:0") is True
        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="qwen", streaming_tools=False)],
        )
        assert supports_streaming_tools("qwen.qwen3-32b-v1:0") is False


class TestRichHistory:
    def _agent_with_thinking(self, tmp_path):
        import uuid

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "canned")
        agent.messages.extend(_fixture_history())
        return agent

    def test_switch_back_restores_thinking_plus_suffix(self, tmp_path):
        import warnings

        from strands_code_cli.loop import RichHistory, apply_model_action

        agent = self._agent_with_thinking(tmp_path)
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, first = apply_model_action(
                agent,
                "google.gemma-3-27b-it",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
                rich=rich,
            )
        assert "thinking restored" not in first
        assert _reasoning_blocks(agent.messages) == []
        assert rich.length == 4
        agent.messages.append({"role": "user", "content": [{"text": "noticed?"}]})
        agent.messages.append({"role": "assistant", "content": [{"text": "yes"}]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, second = apply_model_action(
                agent,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="google.gemma-3-27b-it",
                rich=rich,
            )
        assert "thinking restored" in second
        assert agent.messages[1]["content"][0] == {
            "reasoningContent": {
                "reasoningText": {"text": "let me think", "signature": "sig-1"}
            }
        }
        assert agent.messages[-2]["content"][0] == {"text": "noticed?"}
        assert len(agent.messages) == 6

    def test_trim_below_stash_disables_restore(self, tmp_path):
        import warnings

        from strands_code_cli.loop import RichHistory, apply_model_action

        agent = self._agent_with_thinking(tmp_path)
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_model_action(
                agent,
                "google.gemma-3-27b-it",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
                rich=rich,
            )
            del agent.messages[:3]  # compaction trimmed under the stash point
            _, reply = apply_model_action(
                agent,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="google.gemma-3-27b-it",
                rich=rich,
            )
        assert "thinking restored" not in reply

    def test_cross_vendor_back_does_not_restore(self, tmp_path):
        import warnings

        from strands_code_cli.loop import RichHistory, apply_model_action

        agent = self._agent_with_thinking(tmp_path)
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_model_action(
                agent,
                "google.gemma-3-27b-it",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
                rich=rich,
            )
            _, reply = apply_model_action(
                agent,
                "qwen.qwen3-32b-v1:0",
                turn_running=False,
                current_model="google.gemma-3-27b-it",
                rich=rich,
            )
        assert "thinking restored" not in reply
        assert _reasoning_blocks(agent.messages) == []

    def test_stash_survives_resume_restores_thinking(self, tmp_path):
        import warnings

        from strands_code_cli.loop import RichHistory, apply_model_action

        agent = self._agent_with_thinking(tmp_path)
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_model_action(
                agent,
                "google.gemma-3-27b-it",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
                rich=rich,
            )
        path = tmp_path / "rich_history" / "session-1.json"
        rich.save(path)
        assert path.exists()

        # Resume: fresh stash from disk, converted history + away turns.
        resumed = RichHistory.load(path)
        assert resumed.model_id == "bedrock/global.anthropic.claude-opus-5"
        agent.messages.append({"role": "user", "content": [{"text": "noticed?"}]})
        agent.messages.append({"role": "assistant", "content": [{"text": "yes"}]})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _, reply = apply_model_action(
                agent,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="google.gemma-3-27b-it",
                rich=resumed,
            )
        assert "thinking restored" in reply
        assert not [w for w in caught if "dropping reasoningcontent" in str(w.message).lower()]
        assert agent.messages[1]["content"][0] == {
            "reasoningContent": {
                "reasoningText": {"text": "let me think", "signature": "sig-1"}
            }
        }
        # Image bytes survived the sidecar round-trip losslessly.
        images = [
            block["image"]["source"]["bytes"]
            for message in agent.messages
            for block in message.get("content", [])
            if "image" in block
        ]
        assert images == [b"0123456789"]

    def test_compact_summary_breaks_restore(self, tmp_path):
        import warnings

        from strands_code_cli.loop import RichHistory, apply_model_action

        agent = self._agent_with_thinking(tmp_path)
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_model_action(
                agent,
                "google.gemma-3-27b-it",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
                rich=rich,
            )
            # Same message COUNT as the stash point (length check passes)
            # but a compaction summary replaced the prefix: no restore.
            agent.messages[:] = [
                {"role": "user", "content": [{"text": "[summary] old stuff"}]},
                {"role": "assistant", "content": [{"text": "ack"}]},
                {"role": "user", "content": [{"text": "q"}]},
                {"role": "assistant", "content": [{"text": "a"}]},
            ]
            _, reply = apply_model_action(
                agent,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="google.gemma-3-27b-it",
                rich=rich,
            )
        assert "thinking restored" not in reply

    def test_missing_and_corrupt_stash_load_empty(self, tmp_path):
        from strands_code_cli.loop import RichHistory

        assert RichHistory.load(None).messages is None
        assert RichHistory.load(tmp_path / "nope.json").messages is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert RichHistory.load(bad).messages is None
        bad.write_text('{"version": 1}', encoding="utf-8")
        assert RichHistory.load(bad).messages is None

    def test_empty_save_removes_stale_file(self, tmp_path):
        from strands_code_cli.loop import RichHistory

        path = tmp_path / "s.json"
        path.write_text("{}", encoding="utf-8")
        RichHistory().save(path)  # /clear + /compact path: no raise, file gone
        assert not path.exists()
        RichHistory().save(None)

    def test_stash_path_rejects_traversal(self, tmp_path):
        from strands_code_cli.session_index import rich_stash_path

        assert rich_stash_path(tmp_path, "../../evil") is None
        assert rich_stash_path(tmp_path, "no/slash") is None
        ok = rich_stash_path(tmp_path, "91190877-b0cb-4521-b561-cb797c40ce58")
        assert ok == tmp_path / "rich_history" / "91190877-b0cb-4521-b561-cb797c40ce58.json"


class TestTurnGuard:
    def test_provider_error_fails_turn_not_session(self, tmp_path, monkeypatch, capsys):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        # Isolate from the output proxy: StdoutProxy binds the global
        # AppSession output, which earlier tests may have attached to a dead
        # capture buffer. The guard, not the proxy, is under test here.
        monkeypatch.setattr(loop_mod, "output_context", nullcontext)

        prompts = iter(["hello", "again"])

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)
        calls = []

        def _boom(agent, text, event):
            calls.append(text)
            raise RuntimeError("boom")

        monkeypatch.setattr(loop_mod, "_invoke_agent", _boom)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        monkeypatch.setattr(
            loop_mod,
            "start_steering_reader",
            lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
        )
        agent = SimpleNamespace(messages=[], _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(agent, session_id=index.mint(), index=index, model_id="bedrock/x")
        assert calls == ["hello", "again"]  # re-prompted after each failure
        assert "Turn failed (RuntimeError): boom" in capsys.readouterr().out

    def test_model_action_error_fails_switch_not_session(
        self, tmp_path, monkeypatch, capsys
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(loop_mod, "output_context", nullcontext)
        prompts = iter(["/model bedrock/x"])

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)

        def _boom(agent, message, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(loop_mod, "apply_model_action", _boom)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        monkeypatch.setattr(
            loop_mod,
            "start_steering_reader",
            lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
        )
        agent = SimpleNamespace(messages=[], model="bedrock/x", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(agent, session_id=index.mint(), index=index, model_id="bedrock/x")
        assert "Model switch failed (boom); session unchanged." in capsys.readouterr().out

    def test_streaming_tool_error_hints_model_switch(
        self, tmp_path, monkeypatch, capsys
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(loop_mod, "output_context", nullcontext)
        prompts = iter(["hello"])

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)

        def _boom(agent, text, event):
            raise RuntimeError(
                "An error occurred (ValidationException) when calling the "
                "ConverseStream operation: This model doesn't support tool "
                "use in streaming mode."
            )

        monkeypatch.setattr(loop_mod, "_invoke_agent", _boom)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        monkeypatch.setattr(
            loop_mod,
            "start_steering_reader",
            lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
        )
        agent = SimpleNamespace(messages=[], _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(
            agent,
            session_id=index.mint(),
            index=index,
            model_id="us.meta.llama4-scout-17b-instruct-v1:0",
        )
        out = capsys.readouterr().out
        assert "Turn failed (RuntimeError)" in out
        assert "needs non-streaming tool use" in out

    def test_empty_turn_retries_once_then_succeeds(self, tmp_path, monkeypatch, capsys):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(loop_mod, "output_context", nullcontext)
        prompts = iter(["hello"])

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)
        calls = []

        def _flake_then_answer(agent, text, event):
            calls.append(text)
            agent.messages.append({"role": "user", "content": [{"text": text}]})
            if len(calls) == 1:
                agent.messages.append({"role": "assistant", "content": []})
            else:
                agent.messages.append({"role": "assistant", "content": [{"text": "hi"}]})
            return None

        monkeypatch.setattr(loop_mod, "_invoke_agent", _flake_then_answer)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        monkeypatch.setattr(
            loop_mod,
            "start_steering_reader",
            lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
        )
        agent = SimpleNamespace(messages=[], _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(agent, session_id=index.mint(), index=index, model_id="bedrock/x")
        assert calls == ["hello", "hello"]  # retried exactly once
        # No-op attempt dropped: history shows the question once.
        assert agent.messages == [
            {"role": "user", "content": [{"text": "hello"}]},
            {"role": "assistant", "content": [{"text": "hi"}]},
        ]
        assert "returned empty twice" not in capsys.readouterr().out

    def test_double_empty_notices_and_stops(self, tmp_path, monkeypatch, capsys):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(loop_mod, "output_context", nullcontext)
        prompts = iter(["hello"])

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)
        calls = []

        def _always_empty(agent, text, event):
            calls.append(text)
            agent.messages.append({"role": "user", "content": [{"text": text}]})
            agent.messages.append({"role": "assistant", "content": []})
            return None

        monkeypatch.setattr(loop_mod, "_invoke_agent", _always_empty)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        monkeypatch.setattr(
            loop_mod,
            "start_steering_reader",
            lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
        )
        agent = SimpleNamespace(messages=[], _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(agent, session_id=index.mint(), index=index, model_id="bedrock/x")
        assert calls == ["hello", "hello"]  # one retry, then stop
        assert agent.messages == [
            {"role": "user", "content": [{"text": "hello"}]},
            {"role": "assistant", "content": []},
        ]
        assert "returned empty twice" in capsys.readouterr().out

    def test_empty_detector_rejects_weird_shapes(self):
        from strands_code_cli.loop import _turn_appended_empty

        assert _turn_appended_empty(0, []) is False  # nothing appended
        assert (
            _turn_appended_empty(
                0, [{"role": "assistant", "content": []}]
            )
            is False  # no user message
        )
        assert (
            _turn_appended_empty(
                0,
                [
                    {"role": "user", "content": [{"text": "hi"}]},
                    {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t"}}]},
                ],
            )
            is False  # tool-only turn is not empty
        )
        assert (
            _turn_appended_empty(
                0,
                [
                    {"role": "user", "content": [{"text": "hi"}]},
                    {"role": "assistant", "content": []},
                ],
            )
            is True
        )

    def test_startup_on_llama_warns_once(self, tmp_path, monkeypatch, capsys):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(loop_mod, "output_context", nullcontext)

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, *args, **kwargs):
                raise EOFError

        monkeypatch.setattr(loop_mod, "PromptSession", _Session)
        monkeypatch.setattr(
            loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
        )
        agent = SimpleNamespace(messages=[], _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        loop_mod.run_loop(
            agent,
            session_id=index.mint(),
            index=index,
            model_id="us.meta.llama4-scout-17b-instruct-v1:0",
        )
        out = capsys.readouterr().out
        # Rich wraps the console line; the reply-string test pins the full text.
        assert out.count("rejects tool use in streaming") == 1


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

    def test_online_filters_non_chat_models(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("boto3")

        def _fm(mid, in_mod, out_mod, types=("ON_DEMAND",)):
            entry = {"modelId": mid, "inferenceTypesSupported": list(types)}
            if in_mod is not None:
                entry["inputModalities"] = list(in_mod)
            if out_mod is not None:
                entry["outputModalities"] = list(out_mod)
            return entry

        class _Client:
            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        _fm("chat.text", ("TEXT", "IMAGE"), ("TEXT",)),
                        _fm("amazon.titan-embed-text-v2:0", ("TEXT",), ("EMBEDDING",)),
                        _fm("stability.stable-image-core-v1:1", ("TEXT",), ("IMAGE",)),
                        # Rerank reports TEXT modalities: the name backstop drops it.
                        _fm("cohere.rerank-v3-5:0", ("TEXT",), ("TEXT",)),
                        # Missing modalities: fail open, never hide a usable model.
                        _fm("mystery.model-v1", None, None),
                        _fm("provisioned-chat", ("TEXT",), ("TEXT",), ("PROVISIONED",)),
                    ]
                }

            def list_inference_profiles(self, **kwargs):
                return {"inferenceProfileSummaries": []}

        fake.client = lambda *a, **k: _Client()  # noqa: E731
        monkeypatch.setitem(sys.modules, "boto3", fake)
        options, offline = discover_models(region="us-east-1")
        assert offline is False
        assert "chat.text" in options
        assert "mystery.model-v1" in options
        for dropped in (
            "amazon.titan-embed-text-v2:0",
            "stability.stable-image-core-v1:1",
            "cohere.rerank-v3-5:0",
            "provisioned-chat",
        ):
            assert dropped not in options

    def test_profiles_drop_only_known_non_chat(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("boto3")

        def _profile(name, model_arns):
            entry = {
                "inferenceProfileArn": (
                    f"arn:aws:bedrock:us-east-1:123:inference-profile/{name}"
                )
            }
            if model_arns is not None:
                entry["models"] = [{"modelArn": arn} for arn in model_arns]
            return entry

        _embed = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
        _chat = "arn:aws:bedrock:us-east-1::foundation-model/chat.text"

        class _Client:
            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        {
                            "modelId": "chat.text",
                            "inferenceTypesSupported": ["ON_DEMAND"],
                            "inputModalities": ["TEXT"],
                            "outputModalities": ["TEXT"],
                        },
                        {
                            "modelId": "amazon.titan-embed-text-v2:0",
                            "inferenceTypesSupported": ["ON_DEMAND"],
                            "inputModalities": ["TEXT"],
                            "outputModalities": ["EMBEDDING"],
                        },
                    ]
                }

            def list_inference_profiles(self, **kwargs):
                return {
                    "inferenceProfileSummaries": [
                        _profile("chat-profile", [_chat]),
                        _profile("embed-profile", [_embed]),
                        # No model breakdown: fail open, profiles are curated.
                        _profile("bare-profile", None),
                    ]
                }

        fake.client = lambda *a, **k: _Client()  # noqa: E731
        monkeypatch.setitem(sys.modules, "boto3", fake)
        options, _offline = discover_models(region="us-east-1")
        assert any("chat-profile" in o for o in options)
        assert any("bare-profile" in o for o in options)
        assert not any("embed-profile" in o for o in options)


# ----------------------------------------------------------------------
# Grouped picker: one model, several routes
# ----------------------------------------------------------------------


class TestGroupModels:
    def test_direct_and_profiles_group_once_profiles_first(self):
        from strands_code_cli.model_switch import group_models

        direct = "anthropic.claude-haiku-4-5-20251001-v1:0"
        us_arn = (
            "arn:aws:bedrock:us-west-2:1:inference-profile/"
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        global_arn = (
            "arn:aws:bedrock:us-west-2:1:inference-profile/"
            "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        groups = group_models([direct, us_arn, global_arn])
        assert [base for base, _ in groups] == [direct]
        assert groups[0][1] == [global_arn, us_arn, direct]

    def test_groups_sorted_abc_custom_names_alone(self):
        from strands_code_cli.model_switch import group_models

        groups = group_models(
            [
                "qwen.qwen3-32b-v1:0",
                "arn:aws:bedrock:r:1:inference-profile/my-app-profile",
                "amazon.nova-lite-v1:0",
            ]
        )
        assert [base for base, _ in groups] == [
            "amazon.nova-lite-v1:0",
            "my-app-profile",
            "qwen.qwen3-32b-v1:0",
        ]

    def test_provider_name_merges_with_discovered(self):
        from strands_code_cli.model_switch import group_models

        groups = group_models(
            [
                "bedrock/global.anthropic.claude-opus-5",
                "arn:aws:bedrock:r:1:inference-profile/global.anthropic.claude-opus-5",
            ]
        )
        assert [base for base, _ in groups] == ["anthropic.claude-opus-5"]
        assert len(groups[0][1]) == 2

    def test_route_label_compacts_arns(self):
        from strands_code_cli.model_switch import route_label

        assert (
            route_label("arn:aws:bedrock:us-west-2:1:inference-profile/global.foo")
            == "profile global.foo (us-west-2)"
        )
        assert route_label("qwen.qwen3-32b-v1:0") == "qwen.qwen3-32b-v1:0"


class TestBuildModelTree:
    def test_vendor_family_nesting_sorted(self):
        from strands_code_cli.model_switch import build_model_tree

        tree = build_model_tree(
            [
                "qwen.qwen3-32b-v1:0",
                "anthropic.claude-opus-5",
                "anthropic.claude-haiku-4-5-20251001-v1:0",
                "amazon.nova-lite-v1:0",
            ]
        )
        assert [vendor for vendor, _ in tree] == ["amazon", "anthropic", "qwen"]
        families = next(fams for vendor, fams in tree if vendor == "anthropic")
        assert [family for family, _ in families] == ["claude"]
        models = families[0][1]
        assert [base for base, _ in models] == [
            "anthropic.claude-haiku-4-5-20251001-v1:0",
            "anthropic.claude-opus-5",
        ]

    def test_gpt_oss_stays_compound_family(self):
        from strands_code_cli.model_switch import build_model_tree

        tree = build_model_tree(["openai.gpt-oss-120b-1:0", "openai.gpt-5-mini"])
        families = dict(next(fams for vendor, fams in tree if vendor == "openai"))
        assert sorted(families) == ["gpt", "gpt-oss"]

    def test_dotless_id_groups_under_itself(self):
        from strands_code_cli.model_switch import build_model_tree

        tree = build_model_tree(["bedrock/x"])
        assert tree[0][0] == "x"
        assert tree[0][1][0][0] == "x"
        assert tree[0][1][0][1][0][0] == "x"


class TestCascadePicker:
    _DIRECT = "anthropic.claude-haiku-4-5-20251001-v1:0"
    _US_ARN = (
        "arn:aws:bedrock:us-west-2:1:inference-profile/"
        "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    def _dispatch(self, monkeypatch, tmp_path, script, discovered):
        import sys

        import strands_code_cli.choice as choice_mod
        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        calls = []

        def _scripted(title, options, **kwargs):
            calls.append(title)
            return script[len(calls) - 1]

        monkeypatch.setattr(choice_mod, "radio_choice", _scripted)
        monkeypatch.setattr(
            model_switch_mod, "discover_models", lambda **_: (list(discovered), False)
        )
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model", session_id=index.mint(), index=index, current_model=None
        )
        return action, message, calls

    def test_full_cascade_normalizes_profile_arn_to_tail(self, tmp_path, monkeypatch):
        # Single vendor/family/model auto-advance; only vendor + route ask.
        # Full profile ARNs resolve nowhere (the harness provider splitter
        # rejects them), so the loop receives the Converse-valid tail.
        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["anthropic", self._US_ARN],
            [self._DIRECT, self._US_ARN],
        )
        assert calls == ["Select vendor", f"Select route for {self._DIRECT}"]
        assert (action, message) == (
            "model",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )

    def test_four_levels_when_tree_branches(self, tmp_path, monkeypatch):
        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["anthropic", "claude", self._DIRECT, self._US_ARN],
            [
                "qwen.qwen3-32b-v1:0",
                "anthropic.fable-5",
                "anthropic.claude-opus-5",
                self._DIRECT,
                self._US_ARN,
            ],
        )
        assert calls == [
            "Select vendor",
            "Select anthropic family",
            "Select anthropic claude model",
            f"Select route for {self._DIRECT}",
        ]
        assert (action, message) == (
            "model",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )

    def test_single_route_skips_deeper_steps(self, tmp_path, monkeypatch):
        action, message, calls = self._dispatch(
            monkeypatch, tmp_path, ["qwen"], ["qwen.qwen3-32b-v1:0"]
        )
        assert calls == ["Select vendor"]
        assert (action, message) == ("model", "qwen.qwen3-32b-v1:0")

    def test_escape_at_route_step_keeps_model(self, tmp_path, monkeypatch):
        action, message, _calls = self._dispatch(
            monkeypatch, tmp_path, ["anthropic", None], [self._DIRECT, self._US_ARN]
        )
        assert (action, message) == ("reply", "Model unchanged.")

    def test_back_from_family_returns_to_vendor(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _MODEL_BACK

        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["anthropic", _MODEL_BACK, "qwen"],
            ["anthropic.fable-5", self._DIRECT, "qwen.qwen3-32b-v1:0"],
        )
        assert calls == ["Select vendor", "Select anthropic family", "Select vendor"]
        assert (action, message) == ("model", "qwen.qwen3-32b-v1:0")

    def test_back_from_route_returns_to_model(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _MODEL_BACK

        opus = "anthropic.claude-opus-5"
        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["anthropic", "claude", self._DIRECT, _MODEL_BACK, opus],
            ["anthropic.fable-5", opus, self._DIRECT, self._US_ARN],
        )
        assert calls == [
            "Select vendor",
            "Select anthropic family",
            "Select anthropic claude model",
            f"Select route for {self._DIRECT}",
            "Select anthropic claude model",
        ]
        assert (action, message) == ("model", opus)

    def test_back_skips_auto_advance_levels(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _MODEL_BACK

        # One vendor, one family: Back from the model step lands on the
        # vendor step, not on the auto-advanced family level.
        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["amazon", _MODEL_BACK, "amazon", "amazon.nova-pro-v1:0"],
            ["amazon.nova-lite-v1:0", "amazon.nova-pro-v1:0"],
        )
        assert calls == [
            "Select vendor",
            "Select amazon nova model",
            "Select vendor",
            "Select amazon nova model",
        ]
        assert (action, message) == ("model", "amazon.nova-pro-v1:0")

    def test_non_tty_lists_tree_sorted(self, tmp_path, monkeypatch):
        import sys

        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(
            model_switch_mod,
            "discover_models",
            lambda **_: (["qwen.qwen3-32b-v1:0", self._DIRECT, self._US_ARN], False),
        )
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model", session_id=index.mint(), index=index, current_model=None
        )
        assert action == "reply"
        assert "  anthropic:\n    claude:" in message
        assert f"      {self._DIRECT}:" in message
        assert f"        {self._US_ARN}" in message
        assert "      qwen.qwen3-32b-v1:0" in message
        assert message.index("anthropic") < message.index("qwen")  # ABC order

    def test_cancel_entry_stays_with_current(self, tmp_path, monkeypatch):
        import sys

        import strands_code_cli.choice as choice_mod
        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.router import _MODEL_CANCEL, dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        seen_options = []
        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda title, options, **kwargs: seen_options.append(options)
            or _MODEL_CANCEL,
        )
        monkeypatch.setattr(
            model_switch_mod, "discover_models", lambda **_: (["qwen.qwen3-32b-v1:0"], False)
        )
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model",
            session_id=index.mint(),
            index=index,
            current_model="anthropic.claude-opus-5",
        )
        assert (action, message) == ("reply", "Model unchanged.")
        labels = [label for _, label in seen_options[0]]
        assert labels[-1] == "Cancel (stay with anthropic.claude-opus-5)"
        assert any("Custom model id" in label for label in labels)

    def test_models_alias_lists_like_model(self, tmp_path, monkeypatch):
        import sys

        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(
            model_switch_mod, "discover_models", lambda **_: (["qwen.qwen3-32b-v1:0"], False)
        )
        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        assert dispatch(
            "/models", session_id=session_id, index=index, current_model=None
        ) == dispatch("/model", session_id=session_id, index=index, current_model=None)

    def test_models_alias_validates_selection(self, tmp_path, monkeypatch):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/models nope/not-a-provider", session_id=index.mint(), index=index
        )
        assert action == "reply"
        assert "Unknown model" in message

    def test_missing_sdk_names_the_extra(self, tmp_path, monkeypatch):
        import strands_harness.models as harness_models
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        def _boom(selection, default):
            raise ImportError("No module named 'litellm'")

        monkeypatch.setattr(harness_models, "resolve_model", _boom)
        index = SessionIndex(tmp_path / "index")
        _, litellm_msg = dispatch(
            "/model litellm/openrouter/qwen/qwen3-32b",
            session_id=index.mint(),
            index=index,
        )
        assert "strands-code-agent[litellm]" in litellm_msg
        _, bedrock_msg = dispatch(
            "/model some-bare-id", session_id=index.mint(), index=index
        )
        assert "strands-code-agent[agentcore]" in bedrock_msg
        _, other_msg = dispatch(
            "/model ollama/llama3", session_id=index.mint(), index=index
        )
        assert "provider SDK not installed" in other_msg


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

    def test_full_profile_arn_direct_maps_to_tail(self, tmp_path):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model arn:aws:bedrock:us-west-2:1:inference-profile/"
            "us.anthropic.claude-sonnet-4-6",
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

    def test_bare_model_offline_empty_returns_pair(self, tmp_path, monkeypatch):
        import sys

        import strands_code_cli.model_switch as model_switch_mod
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(model_switch_mod, "discover_models", lambda **_: ([], True))
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model",
            session_id=index.mint(),
            index=index,
            current_model=None,
        )
        assert action == "reply"
        assert "No models discovered offline" in message


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

    def test_switch_to_llama_warns_in_reply(self, tmp_path):
        import warnings

        from strands_code_cli.loop import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "before")
        agent("first ask")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resolved, reply = apply_model_action(
                agent,
                "us.meta.llama4-scout-17b-instruct-v1:0",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
            )
        assert resolved is not None
        assert "rejects tool use in streaming mode" in reply

        agent2 = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "before")
        agent2("first ask")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, reply2 = apply_model_action(
                agent2,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
            )
        assert "rejects tool use in streaming mode" not in reply2

    def test_bad_selection_leaves_session_untouched(self, tmp_path):
        import copy

        from strands_code_cli.loop import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "before")
        agent("first ask")
        before_model = agent.model
        before_messages = copy.deepcopy(agent.messages)
        with pytest.raises(ValueError, match="Unknown model provider"):
            apply_model_action(
                agent,
                "bogus/xyz",
                turn_running=False,
                current_model="bedrock/global.anthropic.claude-opus-5",
            )
        # The switch resolves before any history mutation: model AND
        # messages are exactly as they were.
        assert agent.model is before_model
        assert agent.messages == before_messages


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

    def test_model_for_config_shapes(self, monkeypatch):
        import builtins

        from strands_code_cli.main import model_for_config

        assert model_for_config(None) is None
        assert (
            model_for_config("bedrock/global.anthropic.claude-sonnet-4-6")
            == "bedrock/global.anthropic.claude-sonnet-4-6"
        )
        # Simulated missing provider SDK → verbatim string fallback, never a
        # raise (hermetic: must not depend on which extras are installed).
        real_import = builtins.__import__

        def _no_openai(name, *args, **kwargs):
            if name == "strands.models.openai" or name.startswith("strands.models.openai."):
                raise ImportError(f"No module named {name!r} (test probe)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openai)
        assert (
            model_for_config("openai/nemotron-70b", "https://proxy.local/v1")
            == "openai/nemotron-70b"
        )
