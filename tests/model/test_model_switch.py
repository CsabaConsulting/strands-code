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

import strands_code_cli.model.model_capabilities as model_capabilities
import strands_code_cli.model.model_switch as model_switch
from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.model.model_switch import (
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
        self,
        output_model: Any,
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError("offline test double")
        yield  # pragma: no cover - keeps this an async generator

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ):  # type: ignore[override]
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
                {
                    "reasoningContent": {
                        "reasoningText": {"text": "let me think", "signature": "sig-1"}
                    }
                },
                {
                    "toolUse": {
                        "toolUseId": "t-1",
                        "name": "python_repl",
                        "input": {"code": "1+1"},
                    }
                },
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
        {
            "role": "user",
            "content": [
                {"image": {"format": "png", "source": {"bytes": b"0123456789"}}}
            ],
        },
    ]


# ----------------------------------------------------------------------
# resolve_model spike: one id per provider family + invalid provider
# ----------------------------------------------------------------------


class TestResolveSpike:
    def test_bedrock_global_id_resolves(self):
        model = resolve_model(
            "bedrock/global.anthropic.claude-sonnet-4-6",
            default="bedrock/global.anthropic.claude-opus-5-5",
        )
        # harness 0.5.0 (#4683) builds Claude-on-Bedrock via AnthropicModel(AsyncAnthropicBedrock)
        assert type(model).__name__ == "AnthropicModel"
        assert type(model.client).__name__ == "AsyncAnthropicBedrock"
        assert (
            model.get_config().get("model_id") == "global.anthropic.claude-sonnet-4-6"
        )

    def test_bare_bedrock_id_defaults_to_bedrock(self):
        claude = resolve_model("anthropic.claude-sonnet-4-6", default="bedrock/x")
        assert type(claude).__name__ == "AnthropicModel"
        assert type(claude.client).__name__ == "AsyncAnthropicBedrock"
        nova = resolve_model("us.amazon.nova-2-lite-v1:0", default="bedrock/x")
        assert type(nova).__name__ == "BedrockModel"

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
        from strands_code_cli.model.model_switch import normalize_model_ref

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
        from strands_code_cli.model.model_switch import normalize_model_ref

        assert normalize_model_ref(selection) == selection

    def test_apply_switch_accepts_full_profile_arn(self):
        from types import SimpleNamespace

        from strands_code_cli.model.model_switch import apply_switch

        agent = SimpleNamespace(model="old", messages=[])
        _model, resolved = apply_switch(agent, self._ARN)
        assert type(agent.model).__name__ == "AnthropicModel"
        assert type(agent.model.client).__name__ == "AsyncAnthropicBedrock"
        assert resolved == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


class TestCanonicalPrefixHash:
    def test_stable_across_thinking_and_media_conversion(self):
        import warnings

        from strands_code_cli.model.model_switch import canonical_prefix_hash

        fixture = _fixture_history()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Nemotron strips BOTH thinking and media: the canonical form
            # must survive the full round-trip.
            converted = convert_history(
                fixture,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                "openai/nemotron-70b",
            )
        assert _reasoning_blocks(converted) == []
        assert canonical_prefix_hash(converted) == canonical_prefix_hash(fixture)

    def test_breaks_on_real_edit(self):
        import copy

        from strands_code_cli.model.model_switch import canonical_prefix_hash

        fixture = _fixture_history()
        edited = copy.deepcopy(fixture)
        edited[0]["content"][0]["text"] = "run something else"
        assert canonical_prefix_hash(edited) != canonical_prefix_hash(fixture)

    def test_legacy_labels_migrate_on_convert(self):
        import copy

        from strands_code_cli.model.model_switch import _LEGACY_TRACE_LABELS

        legacy_block = _LEGACY_TRACE_LABELS[0] + "\nThe user is asking about capitals."
        src = [
            {"role": "user", "content": [{"text": "hi"}]},
            {"role": "assistant", "content": [{"text": legacy_block}]},
        ]
        before = copy.deepcopy(src)
        out = convert_history(
            src,
            "bedrock/global.anthropic.claude-sonnet-4-6",
            "google.gemma-3-27b-it",
        )
        assert out[1]["content"][0] == {
            "text": f"{TRACE_LABEL}\nThe user is asking about capitals."
        }
        assert src == before  # convert never mutates its input

    def test_legacy_label_still_stripped(self):
        import copy
        import warnings

        from strands_code_cli.model.model_switch import (
            _LEGACY_TRACE_LABELS,
            TRACE_LABEL,
            canonical_prefix_hash,
        )

        fixture = _fixture_history()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            converted = convert_history(
                fixture,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                "openai/nemotron-70b",
            )
        # Rewrite new labels to the retired bracketed shape: pre-upgrade
        # sessions must keep matching the stash.
        legacy = copy.deepcopy(converted)
        for message in legacy:
            for block in message.get("content", []):
                text = block.get("text", "")
                if text.startswith(TRACE_LABEL):
                    block["text"] = _LEGACY_TRACE_LABELS[0] + text[len(TRACE_LABEL) :]
        assert any(
            block.get("text", "").startswith(_LEGACY_TRACE_LABELS[0])
            for message in legacy
            for block in message.get("content", [])
        )
        assert canonical_prefix_hash(legacy) == canonical_prefix_hash(fixture)

    def test_injected_blocks_ignored_in_prefix_hash(self):
        import copy

        from strands_code_cli.model.model_switch import canonical_prefix_hash

        fixture = _fixture_history()
        with_injected = copy.deepcopy(fixture)
        with_injected[0]["content"].append(
            {"injected": {"text": "<ctx>memory</ctx>", "source": "strands-code:memory"}}
        )
        edited_injected = copy.deepcopy(fixture)
        edited_injected[0]["content"].append(
            {"injected": {"text": "<ctx>edited</ctx>", "source": "strands-code:memory"}}
        )
        assert canonical_prefix_hash(with_injected) == canonical_prefix_hash(fixture)
        assert canonical_prefix_hash(edited_injected) == canonical_prefix_hash(fixture)

    def test_callback_handler_does_not_echo_injected_blocks(self):
        import io

        from rich.console import Console

        from strands_code_agent.callback_handler import CodeAgentCallbackHandler

        buf = io.StringIO()
        handler = CodeAgentCallbackHandler()
        handler.console = Console(file=buf, force_terminal=False, no_color=True)
        handler(
            message={
                "role": "user",
                "content": [
                    {
                        "injected": {
                            "text": "secret ctx",
                            "source": "strands-code:memory",
                        }
                    }
                ],
            }
        )
        assert buf.getvalue() == ""


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
        assert type(agent.model).__name__ == "AnthropicModel"
        assert type(agent.model.client).__name__ == "AsyncAnthropicBedrock"
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
        assert out[1]["content"][0] == {
            "reasoningContent": {
                "reasoningText": {"text": "let me think", "signature": "sig-1"}
            }
        }

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
                _fixture_history(),
                "bedrock/anthropic.claude-x",
                "bedrock/acme-future-1",
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
        import strands_code_cli.model.model_switch as model_switch_mod
        from strands_code_cli.model.model_switch import supports_reasoning

        monkeypatch.setattr(model_switch_mod, "_harness_supports_thinking", None)
        assert supports_reasoning("bedrock/anthropic.claude-opus-5") is True
        assert supports_reasoning("qwen.qwen3-32b-v1:0") is False  # fail-closed

    def test_harness_verdicts_for_bedrock_families(self):
        from strands_code_cli.model.model_switch import supports_reasoning

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
        from strands_code_cli.model.model_switch import same_vendor

        assert same_vendor(
            "bedrock/global.anthropic.claude-opus-5", "us.anthropic.claude-haiku-1"
        )
        assert same_vendor("anthropic/claude-x", "bedrock/anthropic.claude-y")
        assert not same_vendor("bedrock/anthropic.claude-x", "qwen.qwen3-32b-v1:0")

    def test_media_rules_nova_micro_less_nova_pro_ok(self):
        from strands_code_cli.model.model_switch import supports_media

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
        from strands_code_cli.model.model_switch import supports_media

        # Harness-verified: OpenAI-family Converse models reject image
        # fields; direct OpenAI vision models are unaffected.
        assert supports_media("bedrock/openai.gpt-oss-120b-1:0") is False
        assert supports_media("openai.gpt-oss-120b-1:0") is False  # bare = bedrock
        assert supports_media("openai/gpt-4o") is True


class TestAggregatorIds:
    def test_true_vendor_and_family_parsing(self):
        from strands_code_cli.model.model_switch import (
            _base_key,
            _vendor_family,
            _vendor_of,
        )

        entry = "litellm/openrouter/qwen/qwen3-32b"
        assert _base_key(entry) == "qwen/qwen3-32b"
        assert _vendor_of(entry) == "qwen"
        assert _vendor_family("qwen/qwen3-32b") == ("qwen", "qwen3")

    def test_reasoning_fail_closed_for_aggregators(self):
        from strands_code_cli.model.model_switch import supports_reasoning

        # Even true-vendor anthropic via an aggregator strips: adapter
        # translation of thinking blocks is unverified there.
        assert supports_reasoning("litellm/openrouter/anthropic/claude-x") is False

    def test_media_rules_see_true_vendor(self):
        from strands_code_cli.model.model_switch import supports_media

        assert supports_media("litellm/openrouter/meta/llama-x") is False
        assert supports_media("litellm/openrouter/qwen/qwen3-32b") is True

    def test_cascade_groups_aggregator_under_true_vendor(self):
        from strands_code_cli.model.model_switch import build_model_tree

        tree = build_model_tree(
            ["qwen.qwen3-32b-v1:0", "litellm/openrouter/qwen/qwen3-32b"]
        )
        assert [vendor for vendor, _ in tree] == ["qwen"]
        families = dict(tree[0][1])
        assert sorted(families) == ["qwen3"]
        assert len(families["qwen3"]) == 2  # bedrock id + aggregator route


class TestStreamingTools:
    def test_llama_families_warn_rest_fail_open(self):
        from strands_code_cli.model.model_switch import supports_streaming_tools

        assert (
            supports_streaming_tools("us.meta.llama4-scout-17b-instruct-v1:0") is False
        )
        assert (
            supports_streaming_tools("meta.llama4-maverick-17b-instruct-v1:0") is False
        )
        assert supports_streaming_tools("us.meta.llama3-3-70b-instruct-v1:0") is False
        assert (
            supports_streaming_tools("us.anthropic.claude-haiku-4-5-20251001-v1:0")
            is True
        )
        assert supports_streaming_tools("bedrock/mystery-model-1") is True

    def test_override_beats_shipped_rows(self, monkeypatch):
        import strands_code_cli.model.model_capabilities as caps
        from strands_code_cli.model.model_capabilities import CapabilityOverride
        from strands_code_cli.model.model_switch import supports_streaming_tools

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="meta", streaming_tools=True)],
        )
        assert (
            supports_streaming_tools("us.meta.llama4-scout-17b-instruct-v1:0") is True
        )
        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="qwen", streaming_tools=False)],
        )
        assert supports_streaming_tools("qwen.qwen3-32b-v1:0") is False

    def test_mistral_and_writer_bedrock_unary_rows_stay_scoped(self):
        from strands_code_cli.model.model_switch import supports_streaming_tools

        for unary_id in (
            "mistral.mistral-large-2402-v1:0",
            "bedrock/mistral.mistral-large-2402-v1:0",
            "mistral.mistral-large-2407-v1:0",
            "us.mistral.pixtral-large-2502-v1:0",
            "bedrock/us.mistral.pixtral-large-2502-v1:0",
            "us.writer.palmyra-x4-v1:0",
            "us.writer.palmyra-x5-v1:0",
        ):
            assert supports_streaming_tools(unary_id) is False

        for streaming_id in (
            "mistral.mistral-large-3-675b-instruct",
            "mistral.devstral-2-123b",
            "mistral.ministral-3-8b-instruct",
            "mistral.magistral-small-2509",
            "writer.palmyra-vision-7b",
            "litellm/openrouter/mistralai/mistral-large-2407",
            "litellm/openrouter/meta/llama4-scout",
            "litellm/openrouter/meta-llama/llama-4-scout",
            "ollama/llama4",
            "ollama/llama3.3",
        ):
            assert supports_streaming_tools(streaming_id) is True


class TestRichHistory:
    def _agent_with_thinking(self, tmp_path):
        import uuid

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "canned")
        agent.messages.extend(_fixture_history())
        return agent

    def test_switch_back_restores_thinking_plus_suffix(self, tmp_path):
        import warnings

        from strands_code_cli.loop.core import RichHistory, apply_model_action

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

        from strands_code_cli.loop.core import RichHistory, apply_model_action

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

        from strands_code_cli.loop.core import RichHistory, apply_model_action

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

        from strands_code_cli.loop.core import RichHistory, apply_model_action

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
        assert not [
            w for w in caught if "dropping reasoningcontent" in str(w.message).lower()
        ]
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

        from strands_code_cli.loop.core import RichHistory, apply_model_action

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
        from strands_code_cli.loop.core import RichHistory

        assert RichHistory.load(None).messages is None
        assert RichHistory.load(tmp_path / "nope.json").messages is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert RichHistory.load(bad).messages is None
        bad.write_text('{"version": 1}', encoding="utf-8")
        assert RichHistory.load(bad).messages is None

    def test_empty_save_removes_stale_file(self, tmp_path):
        from strands_code_cli.loop.core import RichHistory

        path = tmp_path / "s.json"
        path.write_text("{}", encoding="utf-8")
        RichHistory().save(path)  # /clear + /compact path: no raise, file gone
        assert not path.exists()
        RichHistory().save(None)

    def test_stash_path_rejects_traversal(self, tmp_path):
        from strands_code_cli.session.session_index import rich_stash_path

        assert rich_stash_path(tmp_path, "../../evil") is None
        assert rich_stash_path(tmp_path, "no/slash") is None
        ok = rich_stash_path(tmp_path, "91190877-b0cb-4521-b561-cb797c40ce58")
        assert (
            ok
            == tmp_path / "rich_history" / "91190877-b0cb-4521-b561-cb797c40ce58.json"
        )


class TestTurnGuard:
    @pytest.fixture(autouse=True)
    def _hermetic_fact_dir(self, tmp_path, monkeypatch):
        # Hermetic curate boundary: ambient harness fact files must not
        # queue promotion proposals (and prompt on stdin) during runs.
        import strands_code_cli.loop.core as loop_mod

        monkeypatch.setattr(loop_mod, "MEMORY_FACT_DIR", tmp_path / "memory")

    def test_provider_error_fails_turn_not_session(self, tmp_path, monkeypatch, capsys):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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

        def _boom(agent, text, event, **kwargs):
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
        loop_mod.run_loop(
            agent, session_id=index.mint(), index=index, model_id="bedrock/x"
        )
        assert calls == ["hello", "again"]  # re-prompted after each failure
        assert "Turn failed (RuntimeError): boom" in capsys.readouterr().out

    def test_model_action_error_fails_switch_not_session(
        self, tmp_path, monkeypatch, capsys
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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
        loop_mod.run_loop(
            agent, session_id=index.mint(), index=index, model_id="bedrock/x"
        )
        assert (
            "Model switch failed (boom); session unchanged." in capsys.readouterr().out
        )

    def test_streaming_tool_error_hints_model_switch(
        self, tmp_path, monkeypatch, capsys
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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

        def _boom(agent, text, event, **kwargs):
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

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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

        def _flake_then_answer(agent, text, event, **kwargs):
            calls.append(text)
            agent.messages.append({"role": "user", "content": [{"text": text}]})
            if len(calls) == 1:
                agent.messages.append({"role": "assistant", "content": []})
            else:
                agent.messages.append(
                    {"role": "assistant", "content": [{"text": "hi"}]}
                )
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
        loop_mod.run_loop(
            agent, session_id=index.mint(), index=index, model_id="bedrock/x"
        )
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

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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

        def _always_empty(agent, text, event, **kwargs):
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
        loop_mod.run_loop(
            agent, session_id=index.mint(), index=index, model_id="bedrock/x"
        )
        assert calls == ["hello", "hello"]  # one retry, then stop
        assert agent.messages == [
            {"role": "user", "content": [{"text": "hello"}]},
            {"role": "assistant", "content": []},
        ]
        assert "returned empty twice" in capsys.readouterr().out

    def test_empty_detector_rejects_weird_shapes(self):
        from strands_code_cli.loop.core import _turn_appended_empty

        assert _turn_appended_empty(0, []) is False  # nothing appended
        assert (
            _turn_appended_empty(0, [{"role": "assistant", "content": []}])
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

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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
        normalized = " ".join(out.split())
        assert normalized.count("streaming disabled for") == 1
        assert "(Bedrock unary tool mode)" in normalized
        assert "rejects tool use in streaming" not in normalized


# ----------------------------------------------------------------------
# estimate_fit spike: local estimator vs MODEL_LIMITS
# ----------------------------------------------------------------------


class TestEstimateFit:
    def test_small_history_fits(self):
        fits, pct, tokens = estimate_fit(
            [{"role": "user", "content": [{"text": "hi"}]}],
            "bedrock/global.anthropic.claude-sonnet-4-6",
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
        fits, pct, tokens = estimate_fit(
            big, "bedrock/anthropic.claude-3-haiku-20240307"
        )
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
                        {
                            "inferenceProfileArn": "arn:aws:bedrock:us-east-1:123:inference-profile/global.anthropic.claude-opus-5"
                        }
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

        _embed = (
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
        )
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

    def test_profile_only_image_model_drops_its_profile(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("boto3")

        def _profile(name, model_arns):
            return {
                "inferenceProfileArn": (
                    f"arn:aws:bedrock:us-east-1:123:inference-profile/{name}"
                ),
                "models": [{"modelArn": arn} for arn in model_arns],
            }

        _img = "arn:aws:bedrock:us-east-1::foundation-model/stability.stable-up:0"

        class _Client:
            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        {
                            # Profile-only image tool: no TEXT output, no
                            # ON_DEMAND route. Must still land on the
                            # non-chat denylist so its profile drops.
                            "modelId": "stability.stable-up:0",
                            "inferenceTypesSupported": ["INFERENCE_PROFILE"],
                            "inputModalities": ["TEXT", "IMAGE"],
                            "outputModalities": ["IMAGE"],
                        },
                    ]
                }

            def list_inference_profiles(self, **kwargs):
                return {
                    "inferenceProfileSummaries": [
                        _profile("stability.stable-up:0", [_img]),
                    ]
                }

        fake.client = lambda *a, **k: _Client()  # noqa: E731
        monkeypatch.setitem(sys.modules, "boto3", fake)
        options, offline = discover_models(region="us-east-1")
        assert offline is False
        assert options == []

    def test_aws_only_omits_gemini_clutter(self, monkeypatch):
        import sys

        from strands_code_cli.model.model_switch import discover_models

        monkeypatch.setitem(sys.modules, "boto3", None)
        options, offline = discover_models(configured=["bedrock/x"])
        assert offline is True
        assert options == ["bedrock/x"]

    def test_google_keyed_discovers_live_generate_content_gemini_models(
        self, monkeypatch
    ):
        import sys
        import types

        from strands_code_cli.model.model_switch import discover_models

        monkeypatch.setenv("GOOGLE_API_KEY", "strands_box_test")
        monkeypatch.setitem(sys.modules, "boto3", None)

        entries = [
            types.SimpleNamespace(
                name="models/gemini-2.5-pro",
                supported_actions=["generateContent", "countTokens"],
            ),
            types.SimpleNamespace(
                name="models/gemini-2.5-flash",
                supported_actions=["generateContent"],
            ),
            types.SimpleNamespace(
                name="models/gemini-embedding-001",
                supported_actions=["embedContent"],
            ),
            types.SimpleNamespace(
                name="models/imagen-3.0-generate-002",
                supported_actions=["predict"],
            ),
        ]
        fake_client_inst = types.SimpleNamespace(
            models=types.SimpleNamespace(list=lambda: iter(entries))
        )
        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = lambda **kwargs: fake_client_inst
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

        options, offline = discover_models()
        assert offline is False
        assert options == ["google/gemini-2.5-pro", "google/gemini-2.5-flash"]

    def test_google_keyed_offline_falls_back_to_curated_gemini_models(
        self, monkeypatch
    ):
        import sys

        from strands_code_cli.model.model_switch import (
            CURATED_GEMINI_MODELS,
            discover_models,
        )

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setitem(sys.modules, "boto3", None)
        monkeypatch.setitem(sys.modules, "google.genai", None)

        options, offline = discover_models()
        assert offline is True
        assert options == list(CURATED_GEMINI_MODELS)

    def test_bedrock_and_google_online_merge_without_duplicates(self, monkeypatch):
        import sys
        import types

        from strands_code_cli.model.model_switch import discover_models

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        fake_boto = types.ModuleType("boto3")

        class _BedrockClient:
            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        {
                            "modelId": "anthropic.claude-sonnet-4-6",
                            "inferenceTypesSupported": ["ON_DEMAND"],
                            "inputModalities": ["TEXT"],
                            "outputModalities": ["TEXT"],
                        }
                    ]
                }

            def list_inference_profiles(self, **kwargs):
                return {"inferenceProfileSummaries": []}

        fake_boto.client = lambda *a, **k: _BedrockClient()
        monkeypatch.setitem(sys.modules, "boto3", fake_boto)

        entries = [
            types.SimpleNamespace(
                name="models/gemini-2.5-flash",
                supported_actions=["generateContent"],
            ),
            types.SimpleNamespace(
                name="models/gemini-2.5-flash",
                supported_actions=["generateContent"],
            ),
        ]
        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = lambda **kwargs: types.SimpleNamespace(
            models=types.SimpleNamespace(list=lambda: iter(entries))
        )
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

        options, offline = discover_models()
        assert offline is False
        assert options == ["anthropic.claude-sonnet-4-6", "google/gemini-2.5-flash"]


# ----------------------------------------------------------------------
# Grouped picker: one model, several routes
# ----------------------------------------------------------------------


class TestGroupModels:
    def test_direct_and_profiles_group_once_profiles_first(self):
        from strands_code_cli.model.model_switch import group_models

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
        from strands_code_cli.model.model_switch import group_models

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
        from strands_code_cli.model.model_switch import group_models

        groups = group_models(
            [
                "bedrock/global.anthropic.claude-opus-5",
                "arn:aws:bedrock:r:1:inference-profile/global.anthropic.claude-opus-5",
            ]
        )
        assert [base for base, _ in groups] == ["anthropic.claude-opus-5"]
        assert len(groups[0][1]) == 2

    def test_route_label_compacts_arns(self):
        from strands_code_cli.model.model_switch import route_label

        assert (
            route_label("arn:aws:bedrock:us-west-2:1:inference-profile/global.foo")
            == "profile global.foo (us-west-2)"
        )
        assert route_label("qwen.qwen3-32b-v1:0") == "qwen.qwen3-32b-v1:0"


class TestBuildModelTree:
    def test_vendor_family_nesting_sorted(self):
        from strands_code_cli.model.model_switch import build_model_tree

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
        from strands_code_cli.model.model_switch import build_model_tree

        tree = build_model_tree(["openai.gpt-oss-120b-1:0", "openai.gpt-5-mini"])
        families = dict(next(fams for vendor, fams in tree if vendor == "openai"))
        assert sorted(families) == ["gpt", "gpt-oss"]

    def test_dotless_id_groups_under_itself(self):
        from strands_code_cli.model.model_switch import build_model_tree

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

        import strands_code_cli.model.model_switch as model_switch_mod
        import strands_code_cli.ui.choice as choice_mod
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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
        from strands_code_cli.dispatch.core import _MODEL_BACK

        action, message, calls = self._dispatch(
            monkeypatch,
            tmp_path,
            ["anthropic", _MODEL_BACK, "qwen"],
            ["anthropic.fable-5", self._DIRECT, "qwen.qwen3-32b-v1:0"],
        )
        assert calls == ["Select vendor", "Select anthropic family", "Select vendor"]
        assert (action, message) == ("model", "qwen.qwen3-32b-v1:0")

    def test_back_from_route_returns_to_model(self, tmp_path, monkeypatch):
        from strands_code_cli.dispatch.core import _MODEL_BACK

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
        from strands_code_cli.dispatch.core import _MODEL_BACK

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

        import strands_code_cli.model.model_switch as model_switch_mod
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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

        import strands_code_cli.model.model_switch as model_switch_mod
        import strands_code_cli.ui.choice as choice_mod
        from strands_code_cli.dispatch.core import _MODEL_CANCEL, dispatch
        from strands_code_cli.session.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        seen_options = []
        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda title, options, **kwargs: (
                seen_options.append(options) or _MODEL_CANCEL
            ),
        )
        monkeypatch.setattr(
            model_switch_mod,
            "discover_models",
            lambda **_: (["qwen.qwen3-32b-v1:0"], False),
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

        import strands_code_cli.model.model_switch as model_switch_mod
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(
            model_switch_mod,
            "discover_models",
            lambda **_: (["qwen.qwen3-32b-v1:0"], False),
        )
        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        assert dispatch(
            "/models", session_id=session_id, index=index, current_model=None
        ) == dispatch("/model", session_id=session_id, index=index, current_model=None)

    def test_models_alias_validates_selection(self, tmp_path, monkeypatch):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/models nope/not-a-provider", session_id=index.mint(), index=index
        )
        assert action == "reply"
        assert "Unknown model" in message

    def test_missing_sdk_names_the_extra(self, tmp_path, monkeypatch):
        import strands_harness.models as harness_models

        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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
        from strands_code_cli.cost.cost_context import SUMMARY_MARKER, compact_messages

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
        assert (
            isinstance(model_switch.MODEL_REFUSAL, str)
            and "idle prompt" in model_switch.MODEL_REFUSAL
        )


# ----------------------------------------------------------------------
# P1: /model switching — discovery, convert-or-compact, idle-only swap
# ----------------------------------------------------------------------


class TestModelRouterBranch:
    def test_valid_selection_returns_model_action(self, tmp_path):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model bogus/xyz", session_id=index.mint(), index=index
        )
        assert action == "reply"
        assert "Supported providers" in message

    def test_uninstallable_provider_reply_fail_soft(self, tmp_path, monkeypatch):
        import strands_harness.models as harness_models

        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        def _missing_sdk(*_args, **_kwargs):
            raise ImportError("anthropic sdk missing in probe")

        monkeypatch.setattr(harness_models, "resolve_model", _missing_sdk)
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model anthropic/claude-3-7-sonnet-latest",
            session_id=index.mint(),
            index=index,
        )
        assert action == "reply"
        assert "anthropic/claude-3-7-sonnet-latest" in message
        assert "strands-code-agent[anthropic]" in message

    def test_arn_prefix_preserved_verbatim(self, tmp_path):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/model us.anthropic.claude-sonnet-4-6",
            session_id=index.mint(),
            index=index,
        )
        assert (action, message) == ("model", "us.anthropic.claude-sonnet-4-6")

    def test_full_profile_arn_direct_maps_to_tail(self, tmp_path):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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

        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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

        import strands_code_cli.model.model_switch as model_switch_mod
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

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
        from strands_code_cli.loop.core import apply_model_action

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
        assert type(agent.model).__name__ == "AnthropicModel"
        assert type(agent.model.client).__name__ == "AsyncAnthropicBedrock"
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
        from strands_code_cli.loop.core import apply_model_action

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
        from strands_code_cli.loop.core import apply_model_action

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        before = agent.model
        resolved, reply = apply_model_action(
            agent,
            "bedrock/global.anthropic.claude-sonnet-4-6",
            turn_running=True,
            current_model="bedrock/global.anthropic.claude-opus-5",
        )
        assert resolved is None
        assert (
            reply
            == "Model switches apply at the idle prompt — wait for the turn to finish."
        )
        assert agent.model is before

    def test_switch_to_llama_warns_in_reply(self, tmp_path):
        import warnings

        from strands_code_cli.loop.core import apply_model_action

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
        assert (
            "Note: streaming disabled for us.meta.llama4-scout-17b-instruct-v1:0 "
            "(Bedrock unary tool mode)."
        ) in reply
        assert agent.model.config.get("streaming") is False

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
        assert "streaming disabled for" not in reply2
        assert agent2.model.config.get("streaming") is not False

    def test_bad_selection_leaves_session_untouched(self, tmp_path):
        import copy

        from strands_code_cli.loop.core import apply_model_action

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
        from strands_code_cli.entry.provider_config import ProviderConfig

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
        import sys
        import types

        from strands_code_cli.entry.main import model_for_config

        assert model_for_config(None) is None
        assert (
            model_for_config("bedrock/global.anthropic.claude-sonnet-4-6")
            == "bedrock/global.anthropic.claude-sonnet-4-6"
        )
        # Default responses/messages mode preserves strings so create_harness keeps
        # effort, CacheConfig, and native web_search intact even with base_url.
        assert (
            model_for_config("openai/gpt-6.1-sol", "https://proxy.local/v1")
            == "openai/gpt-6.1-sol"
        )
        assert (
            model_for_config(
                "anthropic/claude-sonnet-5-5",
                "https://anth-proxy.local",
                api_mode="responses",
            )
            == "anthropic/claude-sonnet-5-5"
        )

        # Opt-in api_mode="chat" strips the openai/ prefix for Chat Completions
        # OpenAIModel and falls back to the string when SDK is absent.
        built_args: list = []

        class _FakeOpenAIChat:
            def __init__(self, **kwargs):
                built_args.append(kwargs)

        fake_mod = types.ModuleType("strands.models.openai")
        fake_mod.OpenAIModel = _FakeOpenAIChat
        monkeypatch.setitem(sys.modules, "strands.models.openai", fake_mod)
        chat_model = model_for_config(
            "openai/nemotron-70b", "https://proxy.local/v1", api_mode="chat"
        )
        assert isinstance(chat_model, _FakeOpenAIChat)
        assert built_args == [
            {
                "model_id": "nemotron-70b",
                "client_args": {"base_url": "https://proxy.local/v1"},
            }
        ]

        # Simulated missing provider SDK -> verbatim string fallback, never a
        # raise (hermetic: must not depend on which extras are installed).
        monkeypatch.delitem(sys.modules, "strands.models.openai", raising=False)
        real_import = builtins.__import__

        def _no_openai(name, *args, **kwargs):
            if name == "strands.models.openai" or name.startswith(
                "strands.models.openai."
            ):
                raise ImportError(f"No module named {name!r} (test probe)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openai)
        assert (
            model_for_config(
                "openai/nemotron-70b", "https://proxy.local/v1", api_mode="chat"
            )
            == "openai/nemotron-70b"
        )


class TestReportedWrapScope:
    """Wrap gate scope: openrouter promotes, others pass through identical."""

    def _stub_litellm_base(self, monkeypatch):
        import sys
        import types

        class FakeLiteLLMModel:
            """Minimal format_chunk base standing in for LiteLLMModel."""

            def format_chunk(self, event, **kwargs):
                return {"chunk": dict(event), "kwargs": dict(kwargs)}

        module = types.ModuleType("strands.models.litellm")
        module.LiteLLMModel = FakeLiteLLMModel
        monkeypatch.setitem(sys.modules, "strands.models.litellm", module)
        return FakeLiteLLMModel

    def test_openrouter_ids_wrap(self, monkeypatch):
        from strands_code_cli.cost.reported_cost import wrap_for_openrouter

        fake_base = self._stub_litellm_base(monkeypatch)
        resolved = fake_base()
        wrapped = wrap_for_openrouter("litellm/openrouter/qwen/qwen3-32b", resolved)
        assert wrapped is resolved
        assert callable(getattr(wrapped, "take_reported_costs", None))

    def test_non_openrouter_ids_pass_through_identical(self, monkeypatch):
        from strands_code_cli.cost.reported_cost import wrap_for_openrouter

        fake_base = self._stub_litellm_base(monkeypatch)
        bedrock = fake_base()
        assert wrap_for_openrouter("bedrock/anthropic.claude-x", bedrock) is bedrock
        assert not hasattr(bedrock, "take_reported_costs")
        direct = fake_base()
        assert wrap_for_openrouter("openai/gpt-4o", direct) is direct
        assert not hasattr(direct, "take_reported_costs")

    def test_apply_switch_preserves_effort_forwarding(self, monkeypatch):
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import apply_switch

        fake_base = self._stub_litellm_base(monkeypatch)
        calls: list = []

        def _fake_resolve(*args, **kwargs):
            calls.append((args, kwargs))
            return fake_base()

        monkeypatch.setattr(harness_models, "resolve_model", _fake_resolve)
        agent = SimpleNamespace(model=None, messages=[])
        model, resolved_id = apply_switch(
            agent, "litellm/openrouter/qwen/qwen3-32b", effort="high"
        )
        assert calls[-1] == (
            ("litellm/openrouter/qwen/qwen3-32b", "litellm/openrouter/qwen/qwen3-32b"),
            {"caching": True, "caching_explicit": False, "effort": "high"},
        )
        assert agent.model is model
        assert callable(getattr(model, "take_reported_costs", None))
        assert resolved_id == "litellm/openrouter/qwen/qwen3-32b"
        plain_calls = len(calls)
        other = fake_base()

        def _fake_resolve_other(*args, **kwargs):
            calls.append((args, kwargs))
            return other

        monkeypatch.setattr(harness_models, "resolve_model", _fake_resolve_other)
        model, resolved_id = apply_switch(agent, "bedrock/anthropic.claude-x")
        assert calls[plain_calls:] == [
            (
                ("bedrock/anthropic.claude-x", "bedrock/anthropic.claude-x"),
                {"caching": True, "caching_explicit": False},
            )
        ]
        assert model is other
        assert agent.model is other
        assert not hasattr(model, "take_reported_costs")


class TestConfigureStreamingForModel:
    def test_disables_streaming_only_for_bedrock_no_streaming_tools(self):
        from strands_code_cli.model.model_switch import configure_streaming_for_model

        class _FakeModel:
            def __init__(self):
                self.calls = []

            def update_config(self, **kwargs):
                self.calls.append(kwargs)

        llama4 = _FakeModel()
        assert (
            configure_streaming_for_model(
                "us.meta.llama4-scout-17b-instruct-v1:0", llama4
            )
            is llama4
        )
        assert llama4.calls == [{"streaming": False}]

        llama3 = _FakeModel()
        configure_streaming_for_model("us.meta.llama3-3-70b-instruct-v1:0", llama3)
        assert llama3.calls == [{"streaming": False}]

        claude = _FakeModel()
        configure_streaming_for_model(
            "us.anthropic.claude-haiku-4-5-20251001-v1:0", claude
        )
        assert claude.calls == []

        openai_model = _FakeModel()
        configure_streaming_for_model("openai/gpt-4o", openai_model)
        assert openai_model.calls == []

        mistral_unary = _FakeModel()
        configure_streaming_for_model("mistral.mistral-large-2402-v1:0", mistral_unary)
        assert mistral_unary.calls == [{"streaming": False}]

        mistral_stream = _FakeModel()
        configure_streaming_for_model(
            "mistral.mistral-large-3-675b-instruct", mistral_stream
        )
        assert mistral_stream.calls == []

    def test_honors_capability_overrides_and_fails_soft(self, monkeypatch):
        from types import SimpleNamespace

        import strands_code_cli.model.model_capabilities as caps
        from strands_code_cli.model.model_capabilities import CapabilityOverride
        from strands_code_cli.model.model_switch import configure_streaming_for_model

        class _FakeModel:
            def __init__(self):
                self.calls = []

            def update_config(self, **kwargs):
                self.calls.append(kwargs)

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="meta", streaming_tools=True)],
        )
        meta_override = _FakeModel()
        configure_streaming_for_model(
            "us.meta.llama4-scout-17b-instruct-v1:0", meta_override
        )
        assert meta_override.calls == []

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [CapabilityOverride(vendor="qwen", streaming_tools=False)],
        )
        qwen_override = _FakeModel()
        configure_streaming_for_model("qwen.qwen3-32b-v1:0", qwen_override)
        assert qwen_override.calls == [{"streaming": False}]

        # Fail-soft when resolved is None, lacks update_config, or raises.
        assert configure_streaming_for_model("us.meta.llama4-scout-17b", None) is None
        no_method = SimpleNamespace()
        assert (
            configure_streaming_for_model("us.meta.llama4-scout-17b", no_method)
            is no_method
        )

        def _boom(**_kwargs):
            raise RuntimeError("bad config")

        broken = SimpleNamespace(update_config=_boom)
        assert (
            configure_streaming_for_model("us.meta.llama4-scout-17b", broken) is broken
        )

    def test_build_agent_configures_streaming_false_on_llama(
        self, monkeypatch, tmp_path
    ):
        from types import SimpleNamespace

        import strands_code_cli.entry.main as entry_main

        update_calls = []

        class _ResolvedModel:
            def get_config(self):
                return {"model_id": "us.meta.llama4-scout-17b-instruct-v1:0"}

            def update_config(self, **kwargs):
                update_calls.append(kwargs)

        fake_agent = SimpleNamespace(model=_ResolvedModel(), hooks=[])
        monkeypatch.setattr(entry_main, "create_harness", lambda **kwargs: fake_agent)
        monkeypatch.setattr(entry_main, "bind_main_agent", lambda a: None)
        monkeypatch.setattr(
            entry_main, "register_steering_hook", lambda a: SimpleNamespace()
        )
        monkeypatch.setattr(entry_main, "bind_steering", lambda *_a: None)
        monkeypatch.setattr(entry_main, "register_memory_plugin", lambda *_a: None)
        monkeypatch.setattr(entry_main, "set_mode", lambda *_a: None)
        monkeypatch.setattr(entry_main, "bind_session", lambda *_a: None)

        built = entry_main.build_agent(
            model="us.meta.llama4-scout-17b-instruct-v1:0",
            session_id="test-session",
            session_dir=tmp_path,
        )
        assert built is fake_agent
        assert update_calls == [{"streaming": False}]

    def test_route_side_spawn_and_routed_pick_unary_behavior(
        self, monkeypatch, tmp_path, capsys
    ):
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        import strands_code_cli.loop.core as loop_mod
        import strands_code_cli.routing.core as routing_mod
        from strands_code_cli.session.session_index import SessionIndex

        update_calls = []

        class _RoutedModel:
            def get_config(self):
                return {"model_id": "us.meta.llama4-scout-17b-instruct-v1:0"}

            def update_config(self, **kwargs):
                update_calls.append(kwargs)

        monkeypatch.setattr(
            routing_mod,
            "load_strategy",
            lambda: SimpleNamespace(
                candidates=["us.meta.llama4-scout-17b-instruct-v1:0"], quiet=True
            ),
        )
        monkeypatch.setattr(
            routing_mod,
            "decide",
            lambda *args, **kwargs: (
                SimpleNamespace(
                    model="us.meta.llama4-scout-17b-instruct-v1:0",
                    effort="",
                    model_confidence=0.9,
                    effort_confidence=None,
                    tie_break=False,
                ),
                "heuristic",
                (0, 0, None),
                "",
            ),
        )
        monkeypatch.setattr(
            routing_mod, "validate_routed_effort", lambda *args, **kwargs: True
        )
        monkeypatch.setattr(
            harness_models,
            "resolve_model",
            lambda *args, **kwargs: _RoutedModel(),
        )

        kwargs = {"model": object()}
        events: list = []
        loop_mod._route_side_spawn(
            "why?",
            kwargs,
            live_model=object(),
            current_model="bedrock/global.anthropic.claude-sonnet-4-6",
            routing=None,
            routing_events=events,
        )
        assert update_calls == [{"streaming": False}]

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions", "before")
        agent("first ask")
        index = SessionIndex(tmp_path / "index")
        pick = SimpleNamespace(
            model="us.meta.llama4-scout-17b-instruct-v1:0",
            effort="",
            model_confidence=0.9,
            effort_confidence=None,
            tie_break=False,
        )
        loop_mod._apply_routed_pick(
            agent,
            pick=pick,
            strategy=SimpleNamespace(candidates=[pick.model], quiet=True),
            current_model="bedrock/global.anthropic.claude-sonnet-4-6",
            rich=None,
            index=index,
            session_id="s-route",
            stash_path=None,
            engine="heuristic",
            usage=(0, 0, None),
            routing_events=[],
        )
        out = capsys.readouterr().out
        assert "streaming disabled for" not in out
        assert "rejects tool use in streaming" not in out


class TestPrepareResumedHistory:
    def test_media_capable_bedrock_leaves_messages_untouched(self):
        import copy
        from types import SimpleNamespace

        from strands_code_cli.loop.core import RichHistory
        from strands_code_cli.model.model_switch import prepare_resumed_history

        for target in (
            "bedrock/amazon.nova-2-lite-v1:0",
            "us.anthropic.claude-sonnet-4-6",
        ):
            original = _fixture_history()
            agent = SimpleNamespace(messages=copy.deepcopy(original))
            rich = RichHistory()
            changed = prepare_resumed_history(agent, target, rich)
            assert changed is False
            assert agent.messages == original
            assert rich.messages is None

    def test_non_bedrock_converts_reasoning_and_stashes_rich_history(self, tmp_path):
        import copy
        from types import SimpleNamespace

        from strands_code_cli.loop.core import RichHistory
        from strands_code_cli.model.model_switch import (
            canonical_prefix_hash,
            prepare_resumed_history,
        )

        for target in (
            "openai/gpt-4o",
            "litellm/openrouter/qwen/qwen3-32b",
        ):
            original = _fixture_history()
            agent = SimpleNamespace(messages=copy.deepcopy(original))
            rich = RichHistory()
            stash_path = tmp_path / f"{target.replace('/', '_')}.json"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                changed = prepare_resumed_history(agent, target, rich, stash_path)
            assert changed is True
            assistant_blocks = agent.messages[1]["content"]
            assert "reasoningContent" not in assistant_blocks[0]
            assert assistant_blocks[0]["text"].startswith(TRACE_LABEL)
            # toolUse and image remain preserved on media-capable non-Bedrock targets
            assert assistant_blocks[1] == original[1]["content"][1]
            assert agent.messages[3]["content"][0] == original[3]["content"][0]
            assert rich.messages == original
            assert rich.model_id == "__resumed__"
            assert rich.length == len(original)
            assert rich.prefix_hash == canonical_prefix_hash(original)
            reloaded = RichHistory.load(stash_path)
            assert reloaded.messages == original

    def test_media_less_bedrock_converts_reasoning_and_media_placeholders(self):
        import copy
        from types import SimpleNamespace

        from strands_code_cli.loop.core import RichHistory
        from strands_code_cli.model.model_switch import prepare_resumed_history

        original = _fixture_history()
        agent = SimpleNamespace(messages=copy.deepcopy(original))
        rich = RichHistory()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            changed = prepare_resumed_history(
                agent, "us.meta.llama4-scout-17b-instruct-v1:0", rich
            )
        assert changed is True
        assert agent.messages[1]["content"][0]["text"].startswith(TRACE_LABEL)
        assert agent.messages[3]["content"][0] == {"text": "[image: png, 10 bytes]"}
        assert rich.messages == original

    def test_empty_or_unchanged_history_returns_false(self):
        from types import SimpleNamespace

        from strands_code_cli.loop.core import RichHistory
        from strands_code_cli.model.model_switch import prepare_resumed_history

        empty_agent = SimpleNamespace(messages=[])
        assert (
            prepare_resumed_history(empty_agent, "openai/gpt-4o", RichHistory())
            is False
        )

        plain = [{"role": "user", "content": [{"text": "hello"}]}]
        plain_agent = SimpleNamespace(messages=list(plain))
        rich = RichHistory()
        assert prepare_resumed_history(plain_agent, "openai/gpt-4o", rich) is False
        assert plain_agent.messages == plain
        assert rich.messages is None

    def test_run_loop_resumes_non_bedrock_with_converted_history(
        self, tmp_path, monkeypatch
    ):
        import copy
        from contextlib import nullcontext
        from types import SimpleNamespace

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

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
        original = _fixture_history()
        agent = SimpleNamespace(
            messages=copy.deepcopy(original),
            _session_manager=None,
            model=None,
        )
        index = SessionIndex(tmp_path / "index")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            loop_mod.run_loop(
                agent,
                session_id=index.mint(),
                index=index,
                model_id="openai/gpt-4o",
            )
        assert "reasoningContent" not in agent.messages[1]["content"][0]
        assert agent.messages[1]["content"][0]["text"].startswith(TRACE_LABEL)


class TestUpstreamReasoningWireStrip:
    def test_bedrock_format_messages_strips_foreign_signed_reasoning_on_nova_and_qwen(
        self,
    ):
        import copy
        from types import SimpleNamespace

        from strands.models.bedrock import BedrockModel

        from strands_code_cli.model.model_switch import prepare_resumed_history

        resumed_messages = [
            {"role": "user", "content": [{"text": "explain"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "reasoningContent": {
                            "reasoningText": {
                                "text": "claude internal thought",
                                "signature": "anthropic-sig-123",
                            }
                        }
                    },
                    {"text": "final answer"},
                ],
            },
        ]
        for model_id in ("amazon.nova-2-lite-v1:0", "qwen.qwen3-32b-v1:0"):
            agent = SimpleNamespace(messages=copy.deepcopy(resumed_messages))
            assert prepare_resumed_history(agent, model_id) is False
            bedrock = BedrockModel(model_id=model_id, region_name="us-west-2")
            wire = bedrock._format_bedrock_messages(agent.messages)
            assistant_wire = wire[1]["content"]
            assert all("reasoningContent" not in block for block in assistant_wire)
            assert assistant_wire == [{"text": "final answer"}]
            # Snapshot history keeps the original reasoningContent untouched for later switch-back.
            assert "reasoningContent" in agent.messages[1]["content"][0]

        # Pin #5166 direct wire strip on Nova 1 Lite as well (even though
        # Nova 1 Lite is media-less in _MEDIA_LESS and converts on resume).
        nova1 = BedrockModel(model_id="amazon.nova-lite-v1:0", region_name="us-west-2")
        nova1_wire = nova1._format_bedrock_messages(copy.deepcopy(resumed_messages))
        assert nova1_wire[1]["content"] == [{"text": "final answer"}]


# ----------------------------------------------------------------------
# Phase 14: Google Gemini cross-provider switching, grouping & 2.5 thinking guard
# ----------------------------------------------------------------------


class TestGeminiCrossProviderSafety:
    def test_supports_reasoning_google_gemini_vs_gemma(self):
        from strands_code_cli.model.model_switch import supports_reasoning

        assert supports_reasoning("google/gemini-2.5-pro") is True
        assert supports_reasoning("google/gemini-2.5-flash") is True
        assert supports_reasoning("google.gemma-3-27b-it") is False

    def test_convert_history_strips_tool_use_reasoning_signature_cross_vendor(self):
        from strands.models.litellm import LiteLLMModel

        from strands_code_cli.model.model_switch import (
            canonical_prefix_hash,
            convert_history,
        )

        gemini_history = [
            {"role": "user", "content": [{"text": "read foo.py"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "c1",
                            "name": "read",
                            "input": {"path": "foo.py"},
                            "reasoningSignature": "SIG_B64==",
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "c1",
                            "status": "success",
                            "content": [{"text": "ok"}],
                        }
                    }
                ],
            },
        ]

        # Same-vendor Gemini -> Gemini preserves reasoningSignature.
        same_vendor_out = convert_history(
            gemini_history, "google/gemini-2.5-pro", "google/gemini-2.5-flash"
        )
        assert (
            same_vendor_out[1]["content"][0]["toolUse"]["reasoningSignature"]
            == "SIG_B64=="
        )

        # Cross-vendor strips reasoningSignature so LiteLLM does not mangle tool_calls[].id.
        for target in (
            "litellm/openrouter/anthropic/claude-sonnet-4",
            "anthropic/claude-sonnet-4-6",
        ):
            converted = convert_history(gemini_history, "google/gemini-2.5-pro", target)
            tool_use = converted[1]["content"][0]["toolUse"]
            assert "reasoningSignature" not in tool_use
            formatted = LiteLLMModel.format_request_message_tool_call(tool_use)
            assert formatted["id"] == "c1"
            assert "__thought__" not in formatted["id"]

        # Canonical prefix hash ignores toolUse["reasoningSignature"].
        stripped = convert_history(
            gemini_history, "google/gemini-2.5-pro", "openai/gpt-5.4"
        )
        assert canonical_prefix_hash(gemini_history) == canonical_prefix_hash(stripped)

    def test_rich_history_restores_tool_use_reasoning_signature_on_switch_back(self):
        import copy
        from types import SimpleNamespace
        from unittest.mock import patch

        from strands_code_cli.loop.core import RichHistory, apply_model_action
        from strands_code_cli.model.model_switch import prepare_resumed_history

        gemini_history = [
            {"role": "user", "content": [{"text": "read foo.py"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "c1",
                            "name": "read",
                            "input": {"path": "foo.py"},
                            "reasoningSignature": "SIG_B64==",
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "c1",
                            "status": "success",
                            "content": [{"text": "ok"}],
                        }
                    }
                ],
            },
        ]

        # 1. apply_model_action round-trip: google/ -> openai/ -> google/
        agent = SimpleNamespace(messages=copy.deepcopy(gemini_history), model=object())
        rich = RichHistory()
        with patch(
            "strands_code_cli.loop.core.apply_switch",
            side_effect=lambda ag, target, **kw: (object(), target),
        ):
            _new_id, reply = apply_model_action(
                agent,
                "openai/gpt-5.4",
                turn_running=False,
                current_model="google/gemini-2.5-pro",
                rich=rich,
            )
            assert (
                "reasoningSignature" not in agent.messages[1]["content"][0]["toolUse"]
            )
            assert rich.messages is not None

            _back_id, back_reply = apply_model_action(
                agent,
                "google/gemini-2.5-pro",
                turn_running=False,
                current_model="openai/gpt-5.4",
                rich=rich,
            )
        assert "thinking restored" in back_reply
        assert (
            agent.messages[1]["content"][0]["toolUse"]["reasoningSignature"]
            == "SIG_B64=="
        )

        # 2. prepare_resumed_history stashes toolUse["reasoningSignature"] too.
        resumed = SimpleNamespace(messages=copy.deepcopy(gemini_history))
        resumed_rich = RichHistory()
        assert prepare_resumed_history(resumed, "openai/gpt-5.4", resumed_rich) is True
        assert resumed_rich.messages is not None
        assert (
            resumed_rich.messages[1]["content"][0]["toolUse"]["reasoningSignature"]
            == "SIG_B64=="
        )

    def test_vendor_family_gemini_and_tree_grouping(self):
        from strands_code_cli.model.model_switch import (
            _rule_matches,
            _vendor_family,
            build_model_tree,
        )

        assert _vendor_family("gemini-2.5-pro") == ("google", "gemini")
        assert _vendor_family("custom-1.5") == ("custom-1.5", "custom-1.5")
        assert _vendor_family("gpt-5.4") == ("openai", "gpt")
        tree = build_model_tree(
            ["google/gemini-2.5-pro", "google/gemini-3-flash-preview"]
        )
        assert [vendor for vendor, _ in tree] == ["google"]
        families = dict(tree[0][1])
        assert list(families) == ["gemini"]
        assert len(families["gemini"]) == 2

        assert _rule_matches((None, "google", "gemini", None), "google/gemini-2.5-pro")
        assert not _rule_matches(
            (None, "google", "gemini", None), "bedrock/google.gemma-3-27b-it"
        )

    def test_capability_override_matches_google_gemini_without_gemma(self, monkeypatch):
        import strands_code_cli.model.model_capabilities as caps
        from strands_code_cli.model.model_capabilities import CapabilityOverride
        from strands_code_cli.model.model_switch import supports_reasoning

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [
                CapabilityOverride(vendor="google", family="gemini", reasoning=False)
            ],
        )
        assert supports_reasoning("google/gemini-2.5-pro") is False

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [
                CapabilityOverride(vendor="google", family="gemini", reasoning=True)
            ],
        )
        assert supports_reasoning("google.gemma-3-27b-it") is False

    def test_configure_gemini_for_model_translates_25_thinking_and_wires_all_sites(
        self, monkeypatch, tmp_path
    ):
        from types import SimpleNamespace
        from unittest.mock import patch

        from strands_code_cli.model.model_switch import (
            apply_switch,
            configure_gemini_for_model,
        )

        class _FakeGemini:
            def __init__(self, params):
                self.config = {"params": params}

            def get_config(self):
                return self.config

            def update_config(self, **kwargs):
                self.config.update(kwargs)

        # Rewrites thinking_level -> thinking_budget on gemini-2.5-*
        g25 = _FakeGemini(
            {"thinking_config": {"thinking_level": "high"}, "temperature": 0.2}
        )
        configure_gemini_for_model("google/gemini-2.5-pro", g25)
        assert g25.config["params"]["thinking_config"] == {"thinking_budget": -1}
        assert g25.config["params"]["temperature"] == 0.2

        g25_off = _FakeGemini({"thinking_config": {"thinking_level": "off"}})
        configure_gemini_for_model("google/gemini-2.5-flash", g25_off)
        assert g25_off.config["params"]["thinking_config"] == {"thinking_budget": 0}

        # Leaves gemini-3* and non-google models untouched
        g3 = _FakeGemini({"thinking_config": {"thinking_level": "high"}})
        configure_gemini_for_model("google/gemini-3-flash-preview", g3)
        assert g3.config["params"]["thinking_config"] == {"thinking_level": "high"}

        # Fails soft on broken/missing config objects
        assert configure_gemini_for_model("google/gemini-2.5-pro", object()) is not None

        # 1. Wired in apply_switch
        switched = _FakeGemini({"thinking_config": {"thinking_level": "high"}})
        switched.config["model_id"] = "gemini-2.5-pro"
        fake_agent = SimpleNamespace(model=None)
        with patch("strands_harness.models.resolve_model", return_value=switched):
            apply_switch(fake_agent, "google/gemini-2.5-pro", effort="high")
        assert switched.config["params"]["thinking_config"] == {"thinking_budget": -1}

        # 2. Wired in entry/main.py build_agent
        import strands_code_cli.entry.main as main_mod

        monkeypatch.chdir(tmp_path)
        built_gem = _FakeGemini({"thinking_config": {"thinking_level": "medium"}})
        built_gem.config["model_id"] = "gemini-2.5-flash"
        with (
            patch.object(
                main_mod,
                "create_harness",
                return_value=SimpleNamespace(
                    model=built_gem, add_hook=lambda *a, **k: None
                ),
            ),
            patch.object(main_mod, "register_memory_plugin"),
        ):
            main_mod.build_agent(
                "s1", tmp_path / "sess", model="google/gemini-2.5-flash"
            )
        assert built_gem.config["params"]["thinking_config"] == {"thinking_budget": -1}

        # 3. Wired in loop/core.py _route_side_spawn
        import strands_code_cli.loop.core as loop_mod
        import strands_code_cli.routing.core as routing_mod

        routed_gem = _FakeGemini({"thinking_config": {"thinking_level": "low"}})
        routed_gem.config["model_id"] = "gemini-2.5-pro"
        monkeypatch.setattr(
            routing_mod,
            "load_strategy",
            lambda: SimpleNamespace(candidates=["google/gemini-2.5-pro"], quiet=True),
        )
        monkeypatch.setattr(
            routing_mod,
            "decide",
            lambda *args, **kwargs: (
                SimpleNamespace(
                    model="google/gemini-2.5-pro",
                    effort="low",
                    model_confidence=0.9,
                    effort_confidence=0.9,
                    tie_break=False,
                ),
                "heuristic",
                (0, 0, None),
                "",
            ),
        )
        monkeypatch.setattr(
            routing_mod, "validate_routed_effort", lambda *args, **kwargs: True
        )
        with patch("strands_harness.models.resolve_model", return_value=routed_gem):
            side_kwargs = {"model": object()}
            loop_mod._route_side_spawn(
                "why?",
                side_kwargs,
                live_model=object(),
                current_model="openai/gpt-5.4",
                routing=None,
                routing_events=[],
            )
        assert routed_gem.config["params"]["thinking_config"] == {"thinking_budget": -1}

    def test_gemini_25_clears_gemini_tools_and_38_4_support(self):
        from strands_code_cli.model.model_switch import (
            CURATED_GEMINI_MODELS,
            _vendor_family,
            configure_gemini_for_model,
            supports_reasoning,
        )

        class _FakeGeminiFull:
            def __init__(self, params, gemini_tools):
                self.config = {"params": params, "gemini_tools": gemini_tools}

            def get_config(self):
                return self.config

            def update_config(self, **kwargs):
                self.config.update(kwargs)

        sentinel_tool = object()
        g25 = _FakeGeminiFull(
            {"thinking_config": {"thinking_level": "high"}}, [sentinel_tool]
        )
        configure_gemini_for_model("google/gemini-2.5-flash", g25)
        assert g25.config["params"]["thinking_config"] == {"thinking_budget": -1}
        assert g25.config["gemini_tools"] == []

        # Even without params/thinking_level, gemini-2.5* clears gemini_tools
        g25_tools_only = _FakeGeminiFull({}, [sentinel_tool])
        configure_gemini_for_model("google/gemini-2.5-pro", g25_tools_only)
        assert g25_tools_only.config["gemini_tools"] == []

        # Gemini 3.8 and Gemini 4 keep both thinking_level and gemini_tools untouched
        for modern in ("google/gemini-3.8-flash", "google/gemini-4-neon"):
            mod = _FakeGeminiFull(
                {"thinking_config": {"thinking_level": "high"}}, [sentinel_tool]
            )
            configure_gemini_for_model(modern, mod)
            assert mod.config["params"]["thinking_config"] == {"thinking_level": "high"}
            assert mod.config["gemini_tools"] == [sentinel_tool]

        assert _vendor_family("gemini-3.8-flash") == ("google", "gemini")
        assert _vendor_family("gemini-4-neon") == ("google", "gemini")
        for mid in (
            "google/gemini-3.8-flash",
            "google/gemini-4-hydrogen",
            "google/gemini-4-neon",
            "google/gemini-4-argon",
            "google/gemini-4-carbon",
        ):
            assert supports_reasoning(mid) is True
            assert mid in CURATED_GEMINI_MODELS

    def test_prepare_resumed_history_strips_gemini_tool_use_signature_and_stashes(
        self, tmp_path
    ):
        import copy
        from types import SimpleNamespace

        from strands_code_cli.loop.core import RichHistory
        from strands_code_cli.model.model_switch import (
            canonical_prefix_hash,
            prepare_resumed_history,
        )

        original = [
            {"role": "user", "content": [{"text": "check file"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "t1",
                            "name": "read",
                            "input": {"path": "a.py"},
                            "reasoningSignature": "SIG_B64==",
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "t1",
                            "status": "success",
                            "content": [{"text": "ok"}],
                        }
                    }
                ],
            },
            {"role": "assistant", "content": [{"text": "done"}]},
        ]
        agent = SimpleNamespace(messages=copy.deepcopy(original))
        rich = RichHistory()
        stash_path = tmp_path / "stash.json"

        changed = prepare_resumed_history(
            agent, "openai/gpt-5.4", rich=rich, stash_path=stash_path
        )
        assert changed is True
        tool_use = agent.messages[1]["content"][0]["toolUse"]
        assert "reasoningSignature" not in tool_use
        assert rich.messages == original
        assert rich.prefix_hash == canonical_prefix_hash(original)
        assert stash_path.exists() is True
        assert RichHistory.load(stash_path).messages == original

    def test_configure_gemini_preserves_existing_budget_and_fails_soft(self):
        from strands_code_cli.model.model_switch import configure_gemini_for_model

        class _BudgetModel:
            def __init__(self):
                self.config = {
                    "params": {
                        "thinking_config": {
                            "thinking_level": "high",
                            "thinking_budget": 4096,
                        }
                    }
                }

            def get_config(self):
                return self.config

            def update_config(self, **kwargs):
                self.config.update(kwargs)

        preserved = _BudgetModel()
        configure_gemini_for_model("google/gemini-2.5-pro", preserved)
        assert preserved.config["params"]["thinking_config"] == {
            "thinking_budget": 4096
        }

        class _BrokenGet:
            def get_config(self):
                raise RuntimeError("boom get")

        class _BrokenUpdate:
            def get_config(self):
                return {"params": {"thinking_config": {"thinking_level": "high"}}}

            def update_config(self, **kwargs):
                raise RuntimeError("boom update")

        broken_get = _BrokenGet()
        broken_upd = _BrokenUpdate()
        assert (
            configure_gemini_for_model("google/gemini-2.5-pro", broken_get)
            is broken_get
        )
        assert (
            configure_gemini_for_model("google/gemini-2.5-pro", broken_upd)
            is broken_upd
        )

    def test_is_google_chat_model_legacy_methods_and_invalid_name(self):
        from types import SimpleNamespace

        from strands_code_cli.model.model_switch import _is_google_chat_model

        assert (
            _is_google_chat_model(
                SimpleNamespace(
                    name="models/gemini-2.5-flash",
                    supported_generation_methods=["generateContent"],
                )
            )
            == "gemini-2.5-flash"
        )
        assert (
            _is_google_chat_model(
                SimpleNamespace(
                    name="models/gemini-2.5-flash",
                    supported_generation_methods=["embedContent"],
                )
            )
            is None
        )
        assert _is_google_chat_model(SimpleNamespace(name=None)) is None


class TestConfigureBaseUrlAndResolveHarness:
    def test_apply_switch_forwards_caching_web_search_and_base_url(self, monkeypatch):
        from types import SimpleNamespace

        import anthropic
        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import apply_switch

        calls: list = []
        oai_double = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)

        def _spy_resolve(*args, **kwargs):
            calls.append((args, kwargs))
            return oai_double

        monkeypatch.setattr(harness_models, "resolve_model", _spy_resolve)
        agent = SimpleNamespace(
            model=None, messages=[], _base_url="https://proxy.local/v1"
        )
        apply_switch(agent, "openai/gpt-6.1-sol")
        assert calls == [
            (
                ("openai/gpt-6.1-sol", "openai/gpt-6.1-sol"),
                {"caching": True, "caching_explicit": False, "web_search": True},
            )
        ]
        assert oai_double.client_args["base_url"] == "https://proxy.local/v1"

        anth_client = anthropic.AsyncAnthropic(api_key="test")
        anth_double = SimpleNamespace(client=anth_client)
        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *a, **kw: anth_double
        )
        apply_switch(agent, "anthropic/claude-sonnet-5-5")
        assert str(anth_client.base_url).rstrip("/") == "https://proxy.local/v1"

    def test_build_agent_pins_web_fetch_and_post_applies_base_url(
        self, tmp_path, monkeypatch
    ):
        from types import SimpleNamespace

        import strands_code_cli.entry.main as entry_main

        captured: dict = {}
        fake_model = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)

        def _fake_create_harness(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(model=fake_model)

        monkeypatch.setattr(entry_main, "create_harness", _fake_create_harness)
        monkeypatch.setattr(entry_main, "register_steering_hook", lambda _a: object())
        monkeypatch.setattr(entry_main, "bind_steering", lambda _s: None)
        monkeypatch.setattr(entry_main, "bind_main_agent", lambda _a: None)
        monkeypatch.setattr(entry_main, "register_memory_plugin", lambda _a, _l: None)

        agent = entry_main.build_agent(
            "sess-base-url",
            tmp_path / "sess",
            model="openai/gpt-6.1-sol",
            base_url="https://oai-proxy.example/v1",
        )
        assert captured["model"] == "openai/gpt-6.1-sol"
        assert captured["builtin_tools"]["web_fetch"] == {"model": "openai/gpt-6.1-sol"}
        assert fake_model.client_args["base_url"] == "https://oai-proxy.example/v1"
        assert agent._base_url == "https://oai-proxy.example/v1"
        assert agent._base_url_provider == "openai"
        assert agent._harness_kwargs["_base_url"] == "https://oai-proxy.example/v1"
        assert agent._harness_kwargs["_base_url_provider"] == "openai"

    def test_apply_switch_isolates_base_url_across_providers(self, monkeypatch):
        from types import SimpleNamespace

        import anthropic
        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import apply_switch

        anth_client = anthropic.AsyncAnthropic(api_key="test")
        default_anth_url = str(anth_client.base_url)
        anth_double = SimpleNamespace(client=anth_client)
        oai_double = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)

        agent = SimpleNamespace(
            model=None,
            messages=[],
            _base_url="https://oai-proxy.example/v1",
            _base_url_provider="openai",
        )
        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *a, **kw: oai_double
        )
        apply_switch(agent, "openai/gpt-6.1-terra")
        assert oai_double.client_args["base_url"] == "https://oai-proxy.example/v1"

        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *a, **kw: anth_double
        )
        apply_switch(agent, "anthropic/claude-sonnet-5-5")
        assert str(anth_client.base_url) == default_anth_url

    def test_route_side_spawn_scopes_base_url_by_provider(self, monkeypatch):
        from types import SimpleNamespace

        import anthropic
        import strands_harness.models as harness_models

        import strands_code_cli.loop.core as loop_mod
        import strands_code_cli.routing.core as routing_mod

        monkeypatch.setattr(
            routing_mod,
            "load_strategy",
            lambda: SimpleNamespace(
                candidates=["openai/gpt-6.1-terra", "anthropic/claude-haiku-5-5"],
                quiet=True,
            ),
        )
        monkeypatch.setattr(routing_mod, "validate_routed_effort", lambda *a, **k: True)

        oai_double = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)
        monkeypatch.setattr(
            routing_mod,
            "decide",
            lambda *a, **k: (
                SimpleNamespace(
                    model="openai/gpt-6.1-terra",
                    effort="low",
                    model_confidence=0.9,
                    effort_confidence=0.9,
                    tie_break=False,
                ),
                "heuristic",
                (0, 0, None),
                "",
            ),
        )
        monkeypatch.setattr(harness_models, "resolve_model", lambda *a, **k: oai_double)
        loop_mod._route_side_spawn(
            "hi",
            {
                "model": object(),
                "_base_url": "https://oai-proxy.example/v1",
                "_base_url_provider": "openai",
            },
            live_model=object(),
            current_model="openai/gpt-6.1-sol",
            routing=None,
            routing_events=[],
        )
        assert oai_double.client_args["base_url"] == "https://oai-proxy.example/v1"

        anth_client = anthropic.AsyncAnthropic(api_key="test")
        default_anth_url = str(anth_client.base_url)
        anth_double = SimpleNamespace(client=anth_client)
        monkeypatch.setattr(
            routing_mod,
            "decide",
            lambda *a, **k: (
                SimpleNamespace(
                    model="anthropic/claude-haiku-5-5",
                    effort="low",
                    model_confidence=0.9,
                    effort_confidence=0.9,
                    tie_break=False,
                ),
                "heuristic",
                (0, 0, None),
                "",
            ),
        )
        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *a, **k: anth_double
        )
        loop_mod._route_side_spawn(
            "hi",
            {
                "model": object(),
                "_base_url": "https://oai-proxy.example/v1",
                "_base_url_provider": "openai",
            },
            live_model=object(),
            current_model="openai/gpt-6.1-sol",
            routing=None,
            routing_events=[],
        )
        assert str(anth_client.base_url) == default_anth_url


class TestSameProviderSummaryAndOpenAIGuard:
    def test_same_provider_and_cross_provider_thinking_roundtrip(
        self, monkeypatch, tmp_path
    ):
        import copy
        import warnings

        import strands_code_cli.loop.core as loop_core
        from strands_code_cli.loop.core import RichHistory, apply_model_action
        from strands_code_cli.model.model_switch import (
            TRACE_LABEL,
            convert_history,
            same_provider,
            same_vendor,
        )

        assert same_vendor(
            "anthropic/claude-sonnet-5-5",
            "bedrock/global.anthropic.claude-sonnet-4-6",
        )
        assert not same_provider(
            "anthropic/claude-sonnet-5-5",
            "bedrock/global.anthropic.claude-sonnet-4-6",
        )
        assert same_provider("anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5")
        assert same_provider(
            "bedrock/global.anthropic.claude-sonnet-4-6", "anthropic.claude-haiku-4-5"
        )

        signed_history = [
            {"role": "user", "content": [{"text": "solve carefully"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "reasoningContent": {
                            "reasoningText": {
                                "text": "anthropic secret chain",
                                "signature": "ANTHROPIC_SIG_1",
                            }
                        }
                    },
                    {
                        "toolUse": {
                            "toolUseId": "t1",
                            "name": "read",
                            "input": {"path": "x.py"},
                            "reasoningSignature": b"SIG_BYTES",
                        }
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {"toolResult": {"toolUseId": "t1", "content": [{"text": "ok"}]}}
                ],
            },
            {"role": "assistant", "content": [{"text": "done"}]},
        ]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            converted = convert_history(
                signed_history,
                "anthropic/claude-sonnet-5-5",
                "bedrock/global.anthropic.claude-sonnet-4-6",
            )
        assert any(
            TRACE_LABEL in str(w.message)
            or "Dropping reasoningContent" in str(w.message)
            for w in caught
        )
        assert all("reasoningContent" not in b for m in converted for b in m["content"])
        assert converted[1]["content"][0]["text"].startswith(TRACE_LABEL)
        assert "reasoningSignature" not in converted[1]["content"][1]["toolUse"]

        # Full RichHistory stash -> Bedrock -> restore on switch back to Anthropic
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(copy.deepcopy(signed_history))
        rich = RichHistory()
        monkeypatch.setattr(
            loop_core, "apply_switch", lambda ag, new_id, **kw: (ag.model, new_id)
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _id1, reply1 = apply_model_action(
                agent,
                "bedrock/global.anthropic.claude-sonnet-4-6",
                turn_running=False,
                current_model="anthropic/claude-sonnet-5-5",
                rich=rich,
            )
        assert "thinking restored" not in reply1
        assert all(
            "reasoningContent" not in b for m in agent.messages for b in m["content"]
        )

        # Switching back to another anthropic/ model restores the stashed raw blocks
        _id2, reply2 = apply_model_action(
            agent,
            "anthropic/claude-opus-5-5",
            turn_running=False,
            current_model="bedrock/global.anthropic.claude-sonnet-4-6",
            rich=rich,
        )
        assert "thinking restored" in reply2
        assert (
            agent.messages[1]["content"][0]["reasoningContent"]["reasoningText"][
                "signature"
            ]
            == "ANTHROPIC_SIG_1"
        )
        assert (
            agent.messages[1]["content"][1]["toolUse"]["reasoningSignature"]
            == b"SIG_BYTES"
        )

    def test_summary_block_switch_and_rich_history_restore(self, monkeypatch, tmp_path):
        import copy

        import strands_code_cli.loop.core as loop_core
        from strands_code_cli.loop.core import RichHistory, apply_model_action
        from strands_code_cli.model.model_switch import (
            SUMMARY_LABEL,
            _has_reasoning,
            canonical_prefix_hash,
            convert_history,
        )

        summary_history = [
            {
                "role": "assistant",
                "content": [
                    {
                        "summary": {
                            "provider": "anthropic",
                            "signature": "SUM_SIG",
                            "text": "Prior 10 turns compacted.",
                        }
                    },
                    {"summary": {"provider": "anthropic", "text": "   "}},
                ],
            },
            {"role": "user", "content": [{"text": "continue"}]},
        ]
        assert _has_reasoning(summary_history) is True

        same_prov = convert_history(
            summary_history, "anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5"
        )
        assert same_prov[0]["content"][0] == summary_history[0]["content"][0]

        for target in (
            "openai/gpt-6.1-sol",
            "bedrock/global.anthropic.claude-sonnet-4-6",
            "google/gemini-3-flash-preview",
        ):
            converted = convert_history(
                summary_history, "anthropic/claude-sonnet-5-5", target
            )
            assert converted[0]["content"] == [
                {"text": f"{SUMMARY_LABEL}\nPrior 10 turns compacted."}
            ]
            assert canonical_prefix_hash(converted) == canonical_prefix_hash(
                summary_history
            )

        # Round-trip restore via RichHistory
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(copy.deepcopy(summary_history))
        rich = RichHistory()
        monkeypatch.setattr(
            loop_core, "apply_switch", lambda ag, new_id, **kw: (ag.model, new_id)
        )
        apply_model_action(
            agent,
            "openai/gpt-6.1-sol",
            turn_running=False,
            current_model="anthropic/claude-sonnet-5-5",
            rich=rich,
        )
        assert agent.messages[0]["content"] == [
            {"text": f"{SUMMARY_LABEL}\nPrior 10 turns compacted."}
        ]
        apply_model_action(
            agent,
            "anthropic/claude-haiku-5-5",
            turn_running=False,
            current_model="openai/gpt-6.1-sol",
            rich=rich,
        )
        assert agent.messages[0]["content"][0]["summary"]["signature"] == "SUM_SIG"

    def test_vendor_family_openai_anthropic_and_tree_grouping(self):
        from strands_code_cli.model.model_switch import _vendor_family, build_model_tree

        assert _vendor_family("claude-sonnet-5-5") == ("anthropic", "claude")
        assert _vendor_family("gpt-6.1-sol") == ("openai", "gpt")
        assert _vendor_family("gpt-oss-120b") == ("openai", "gpt-oss")
        assert _vendor_family("o3") == ("openai", "o3")
        assert _vendor_family("o4-mini") == ("openai", "o4")
        assert _vendor_family("o1-preview") == ("openai", "o1")
        assert _vendor_family("gemini-2.5-pro") == ("google", "gemini")
        assert _vendor_family("x") == ("x", "x")

        tree = dict(
            build_model_tree(
                [
                    "anthropic/claude-sonnet-5-5",
                    "openai/gpt-6.1-sol",
                    "openai/o3",
                    "openai/gpt-oss-120b",
                    "bedrock/x",
                ]
            )
        )
        assert list(dict(tree["anthropic"])) == ["claude"]
        assert list(dict(tree["openai"])) == ["gpt", "gpt-oss", "o3"]
        assert "x" in tree

    @staticmethod
    def _fake_openai(params):
        class _FakeOpenAI:
            def __init__(self, initial_params):
                self.config = {"params": initial_params}
                self._bedrock_mantle_config = None

            def get_config(self):
                return self.config

            def update_config(self, **kw):
                self.config.update(kw)

        return _FakeOpenAI(params)

    def test_configure_openai_for_model_strips_and_clamps(self):
        from strands_code_cli.model.model_switch import configure_openai_for_model

        for model_id in (
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "openai/gpt-4-turbo",
            "openai/chatgpt-4o-latest",
            "openai/gpt-3.5-turbo",
        ):
            orig_params = {"reasoning": {"effort": "high"}, "temperature": 0.2}
            fake = self._fake_openai(orig_params)
            configure_openai_for_model(model_id, fake)
            assert "reasoning" not in fake.config["params"], model_id
            assert fake.config["params"]["temperature"] == 0.2
            assert "reasoning" in orig_params  # original dict not mutated

        for model_id in ("openai/o1", "openai/o3", "openai/o4-mini"):
            f_min = self._fake_openai({"reasoning": {"effort": "minimal"}})
            configure_openai_for_model(model_id, f_min)
            assert f_min.config["params"]["reasoning"]["effort"] == "low"
            f_xh = self._fake_openai({"reasoning": {"effort": "xhigh"}})
            configure_openai_for_model(model_id, f_xh)
            assert f_xh.config["params"]["reasoning"]["effort"] == "high"
            f_off = self._fake_openai({"reasoning": {"effort": "off"}})
            configure_openai_for_model(model_id, f_off)
            assert "reasoning" not in f_off.config["params"]

        for model_id in ("openai/gpt-5", "openai/gpt-5.1", "openai/gpt-5.2"):
            f_max = self._fake_openai({"reasoning": {"effort": "max"}})
            configure_openai_for_model(model_id, f_max)
            assert f_max.config["params"]["reasoning"]["effort"] == "high"
            f_min = self._fake_openai({"reasoning": {"effort": "minimal"}})
            configure_openai_for_model(model_id, f_min)
            assert f_min.config["params"]["reasoning"]["effort"] == "minimal"
            f_none = self._fake_openai({"reasoning": {"effort": "none"}})
            configure_openai_for_model(model_id, f_none)
            assert "reasoning" not in f_none.config["params"]

        for model_id in (
            "openai/gpt-6-astra",
            "openai/gpt-6.1-sol",
            "openai/gpt-6.2-sol",
            "openai/gpt-6.2-astra",
        ):
            f_min = self._fake_openai({"reasoning": {"effort": "minimal"}})
            configure_openai_for_model(model_id, f_min)
            assert f_min.config["params"]["reasoning"]["effort"] == "low"
            f_xh = self._fake_openai({"reasoning": {"effort": "xhigh"}})
            configure_openai_for_model(model_id, f_xh)
            assert f_xh.config["params"]["reasoning"]["effort"] == "xhigh"
            f_off = self._fake_openai({"reasoning": {"effort": "off"}})
            configure_openai_for_model(model_id, f_off)
            assert "reasoning" not in f_off.config["params"]

    def test_configure_openai_for_model_gpt62_native_sdk_and_effort_clamp(self):
        import strands.models._model_info as sdk_model_info
        from strands.models.openai_responses import OpenAIResponsesModel

        import strands_code_cli.model.model_switch as switch_mod
        from strands_code_cli.model.model_switch import (
            CURATED_OPENAI_MODELS,
            configure_openai_for_model,
        )

        assert not hasattr(switch_mod, "_gpt_62_model_info_fallback")
        assert "openai/gpt-6.2-sol" in CURATED_OPENAI_MODELS
        assert "openai/gpt-6.2-astra" in CURATED_OPENAI_MODELS
        assert (
            sdk_model_info.lookup_model_info("gpt-6.2-sol").limits.context_window
            == 1_050_000
        )

        real_model = OpenAIResponsesModel(
            client_args={"api_key": "test"}, model_id="gpt-6.2-sol"
        )
        configure_openai_for_model("openai/gpt-6.2-sol", real_model)
        assert real_model.context_window_limit == 1_050_000
        assert real_model.model_info.limits.max_output_tokens == 128_000
        assert real_model.model_info.capabilities.prompt_caching == "cache_points"

        f_min = self._fake_openai({"reasoning": {"effort": "minimal"}})
        configure_openai_for_model("openai/gpt-6.2-sol", f_min)
        assert f_min.config["params"]["reasoning"]["effort"] == "low"
        f_off = self._fake_openai({"reasoning": {"effort": "off"}})
        configure_openai_for_model("openai/gpt-6.2-astra", f_off)
        assert "reasoning" not in f_off.config["params"]

    def test_configure_openai_for_model_fails_soft_and_wires_all_sites(
        self, monkeypatch, tmp_path
    ):
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        import strands_code_cli.entry.main as entry_main
        from strands_code_cli.model.model_switch import (
            apply_switch,
            configure_openai_for_model,
            resolve_harness_model,
        )

        mantle = self._fake_openai({"reasoning": {"effort": "high"}})
        mantle._bedrock_mantle_config = object()
        configure_openai_for_model("openai/gpt-4o", mantle)
        assert mantle.config["params"]["reasoning"]["effort"] == "high"

        anthropic_fake = self._fake_openai({"reasoning": {"effort": "high"}})
        configure_openai_for_model("anthropic/claude-sonnet-5-5", anthropic_fake)
        assert anthropic_fake.config["params"]["reasoning"]["effort"] == "high"

        boom = self._fake_openai({"reasoning": {"effort": "high"}})

        def _boom(**_kw):
            raise RuntimeError("boom")

        boom.update_config = _boom
        assert configure_openai_for_model("openai/gpt-4o", boom) is boom

        switched_fake = self._fake_openai({"reasoning": {"effort": "high"}})
        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *_a, **_k: switched_fake
        )
        apply_switch(SimpleNamespace(), "openai/gpt-4o")
        assert "reasoning" not in switched_fake.config["params"]

        routed_fake = self._fake_openai({"reasoning": {"effort": "xhigh"}})
        monkeypatch.setattr(
            harness_models, "resolve_model", lambda *_a, **_k: routed_fake
        )
        resolve_harness_model("openai/o3", effort="xhigh")
        assert routed_fake.config["params"]["reasoning"]["effort"] == "high"

        built_fake = self._fake_openai({"reasoning": {"effort": "high"}})
        monkeypatch.setattr(
            entry_main,
            "create_harness",
            lambda **_kw: SimpleNamespace(model=built_fake),
        )
        monkeypatch.setattr(entry_main, "register_steering_hook", lambda _a: object())
        monkeypatch.setattr(entry_main, "bind_steering", lambda _s: None)
        monkeypatch.setattr(entry_main, "bind_main_agent", lambda _a: None)
        monkeypatch.setattr(entry_main, "register_memory_plugin", lambda _a, _l: None)
        entry_main.build_agent("s-oai", tmp_path / "sess", model="openai/gpt-4.1-mini")
        assert "reasoning" not in built_fake.config["params"]


class TestLiveOpenAIAndAnthropicDiscovery:
    def test_discover_openai_models_gating_filtering_and_fallback(self, monkeypatch):
        import sys
        import types

        from strands_code_cli.model.model_switch import (
            CURATED_OPENAI_MODELS,
            _discover_openai_models,
        )

        # No OPENAI_API_KEY -> empty, offline (no unkeyed clutter)
        assert _discover_openai_models() == ([], False)

        # Keyed + live SDK -> filters strictly to Responses chat/reasoning models
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        entries = [
            types.SimpleNamespace(id="gpt-6.1-sol"),
            types.SimpleNamespace(id="gpt-5.4"),
            types.SimpleNamespace(id="o3"),
            types.SimpleNamespace(id="o4-mini"),
            types.SimpleNamespace(id="gpt-4o"),
            types.SimpleNamespace(id="gpt-4.1"),
            types.SimpleNamespace(id="chatgpt-4o-latest"),
            types.SimpleNamespace(id="text-embedding-3-large"),
            types.SimpleNamespace(id="whisper-1"),
            types.SimpleNamespace(id="tts-1"),
            types.SimpleNamespace(id="gpt-image-1"),
            types.SimpleNamespace(id="gpt-4o-realtime-preview"),
            types.SimpleNamespace(id="omni-moderation-latest"),
            types.SimpleNamespace(id="dall-e-3"),
            types.SimpleNamespace(id="babbage-002"),
            types.SimpleNamespace(id="davinci-002"),
            types.SimpleNamespace(id="gpt-3.5-turbo-instruct"),
            types.SimpleNamespace(id="gpt-4o-transcribe"),
            types.SimpleNamespace(id="gpt-4o-audio-preview"),
            types.SimpleNamespace(id="sora-2"),
            types.SimpleNamespace(id="gpt-4o-mini-tts"),
            types.SimpleNamespace(id="gpt-4o-transcribe-diarize"),
        ]
        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = lambda **kw: types.SimpleNamespace(
            models=types.SimpleNamespace(list=lambda: iter(entries))
        )
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        models, online = _discover_openai_models()
        assert online is True
        assert models == [
            "openai/gpt-6.1-sol",
            "openai/gpt-5.4",
            "openai/o3",
            "openai/o4-mini",
            "openai/gpt-4o",
            "openai/gpt-4.1",
            "openai/chatgpt-4o-latest",
        ]

        # Keyed offline / missing SDK -> curated fallback
        monkeypatch.setitem(sys.modules, "openai", None)
        fallback, online2 = _discover_openai_models()
        assert online2 is False
        assert fallback == list(CURATED_OPENAI_MODELS)

    def test_discover_anthropic_models_gating_caching_and_fallback(
        self, monkeypatch, tmp_path
    ):
        import datetime as dt
        import sys
        import types

        import strands_code_cli.cost.live_pricing as live_pricing
        from strands_code_cli.model.model_switch import (
            CURATED_ANTHROPIC_MODELS,
            _discover_anthropic_models,
        )

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))

        # Unkeyed -> empty, offline
        assert _discover_anthropic_models() == ([], False)

        # Keyed + live SDK -> discovers models and stores 24h JSON-safe metadata
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

        class _Caps:
            def model_dump(self, mode: str = "json"):
                return {"thinking": {"supported": True}}

        entries = [
            types.SimpleNamespace(
                id="claude-sonnet-5-5",
                max_input_tokens=1_000_000,
                max_tokens=128_000,
                capabilities=_Caps(),
                line="sonnet",
                retires_at=None,
            ),
            types.SimpleNamespace(
                id="claude-opus-4-1",
                max_input_tokens=200_000,
                max_tokens=32_000,
                capabilities={"thinking": {"supported": True}},
                line="opus",
                retires_at=dt.datetime(2027, 2, 1, 0, 0, tzinfo=dt.timezone.utc),
            ),
        ]
        fake_anthropic = types.ModuleType("anthropic")
        fake_anthropic.Anthropic = lambda **kw: types.SimpleNamespace(
            models=types.SimpleNamespace(list=lambda: iter(entries))
        )
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

        models, online = _discover_anthropic_models()
        assert online is True
        assert models == ["anthropic/claude-sonnet-5-5", "anthropic/claude-opus-4-1"]

        cached = live_pricing.anthropic_model_entry("anthropic/claude-opus-4-1")
        assert cached is not None
        assert cached["max_input_tokens"] == 200_000
        assert cached["retires_at"].startswith("2027-02-01")
        assert live_pricing.anthropic_model_entry("anthropic/claude-sonnet-5-5")[
            "capabilities"
        ] == {"thinking": {"supported": True}}

        # Keyed offline / SDK missing -> curated fallback
        monkeypatch.setitem(sys.modules, "anthropic", None)
        fallback, online2 = _discover_anthropic_models()
        assert online2 is False
        assert fallback == list(CURATED_ANTHROPIC_MODELS)

    def test_discover_models_merges_keyed_providers_without_unkeyed_leak(
        self, monkeypatch, tmp_path
    ):
        import sys
        import types

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))

        from strands_code_cli.model.model_switch import (
            CURATED_ANTHROPIC_MODELS,
            discover_models,
        )

        # Unkeyed Bedrock-only user never sees OpenAI/Anthropic entries
        monkeypatch.setitem(sys.modules, "boto3", None)
        opts_unkeyed, off_unkeyed = discover_models(configured=["bedrock/x"])
        assert off_unkeyed is True
        assert opts_unkeyed == ["bedrock/x"]

        # Multi-key user: OpenAI online + Anthropic offline fallback merge cleanly
        monkeypatch.setenv("OPENAI_API_KEY", "k-oai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k-ant")
        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = lambda **kw: types.SimpleNamespace(
            models=types.SimpleNamespace(
                list=lambda: iter([types.SimpleNamespace(id="gpt-6.1-sol")])
            )
        )
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        monkeypatch.setitem(sys.modules, "anthropic", None)

        merged, offline = discover_models()
        assert offline is False
        assert "openai/gpt-6.1-sol" in merged
        for entry in CURATED_ANTHROPIC_MODELS:
            assert entry in merged
        assert all(not m.startswith("google/") for m in merged)

    def test_route_label_surfaces_anthropic_retires_date(self, monkeypatch, tmp_path):
        import strands_code_cli.cost.live_pricing as live_pricing
        from strands_code_cli.model.model_switch import normalize_model_ref, route_label

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))

        live_pricing.store_anthropic_models(
            [
                {
                    "id": "claude-opus-4-1",
                    "max_input_tokens": 200_000,
                    "retires_at": "2027-02-01T00:00:00Z",
                }
            ]
        )
        assert (
            route_label("anthropic/claude-opus-4-1")
            == "anthropic/claude-opus-4-1 (retires 2027-02-01)"
        )
        assert normalize_model_ref("anthropic/claude-opus-4-1") == (
            "anthropic/claude-opus-4-1"
        )
        assert route_label("openai/gpt-6.1-sol") == "openai/gpt-6.1-sol"

        monkeypatch.setenv("STRANDS_CODE_NO_LIVE_PRICING", "1")
        assert route_label("anthropic/claude-opus-4-1") == "anthropic/claude-opus-4-1"

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        for bad_date in ("\x1b[31m2027-01-01", "not-a-date-here"):
            live_pricing.store_anthropic_models(
                [{"id": "claude-craft", "retires_at": bad_date}]
            )
            assert route_label("anthropic/claude-craft") == "anthropic/claude-craft"

    def test_nyquist_model_switch_edge_branches(self, monkeypatch, tmp_path):
        import sys
        import types

        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import (
            _convert_summary_block,
            _discover_anthropic_models,
            _extract_anthropic_model_meta,
            _is_openai_chat_model,
            _openai_reasoning_params,
            _serialize_capabilities,
            configure_base_url_for_model,
            resolve_harness_model,
        )

        assert _convert_summary_block({"summary": "bad"}, "openai/gpt-6.1-sol") is None
        assert (
            _convert_summary_block(
                {"summary": {"provider": "anthropic", "text": "   "}},
                "openai/gpt-6.1-sol",
            )
            is None
        )
        assert _is_openai_chat_model(None) is False  # type: ignore[arg-type]
        assert _is_openai_chat_model("   ") is False

        class _BoomCaps:
            def model_dump(self, mode: str = "json"):
                raise RuntimeError("dump failed")

        assert _serialize_capabilities(_BoomCaps()) is None
        assert _serialize_capabilities(123) is None
        assert _extract_anthropic_model_meta(types.SimpleNamespace(id="  ")) is None
        meta = _extract_anthropic_model_meta(
            types.SimpleNamespace(
                id="claude-sonnet-5-5", retires_at="2027-03-01T00:00Z"
            )
        )
        assert meta is not None and meta["retires_at"] == "2027-03-01T00:00Z"

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
        fake_ant = types.ModuleType("anthropic")
        fake_ant.Anthropic = lambda **kw: types.SimpleNamespace(
            models=types.SimpleNamespace(
                list=lambda: iter(
                    [
                        types.SimpleNamespace(id="  "),
                        types.SimpleNamespace(id="claude-sonnet-5-5"),
                    ]
                )
            )
        )
        monkeypatch.setitem(sys.modules, "anthropic", fake_ant)
        models, online = _discover_anthropic_models()
        assert online is True and models == ["anthropic/claude-sonnet-5-5"]

        assert _openai_reasoning_params("gpt-6.1-sol", {"temperature": 0.5}) is None
        assert (
            _openai_reasoning_params("gpt-6.1-sol", {"reasoning": {"effort": 123}})
            is None
        )

        mantle = types.SimpleNamespace(client_args={}, _bedrock_mantle_config=object())
        configure_base_url_for_model(
            "openai/gpt-6.1-sol", mantle, base_url="https://proxy.example/v1"
        )
        assert "base_url" not in mantle.client_args

        class _RoClient:
            @property
            def base_url(self):
                return "https://api.anthropic.com"

            @base_url.setter
            def base_url(self, _value):
                raise RuntimeError("read-only")

        bad_anth = types.SimpleNamespace(client=_RoClient())
        assert (
            configure_base_url_for_model(
                "anthropic/claude-sonnet-5-5",
                bad_anth,
                base_url="https://proxy.example/v1",
            )
            is bad_anth
        )

        monkeypatch.setattr(
            harness_models,
            "supports_web_search",
            lambda _id: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(
            harness_models,
            "resolve_model",
            lambda *_a, **kw: types.SimpleNamespace(kwargs=kw),
        )
        res = resolve_harness_model("openai/gpt-6.1-sol")
        assert "web_search" not in res.kwargs


class TestMetaModelAdapter:
    """Thin auto-retiring meta/ adapter on OpenAIResponsesModel (Phase 16)."""

    def test_build_meta_model_protocol_caching_effort_and_web_search(self, monkeypatch):
        import warnings

        import openai
        from strands.models.openai_responses import OpenAIResponsesModel

        from strands_code_cli.model.model_switch import (
            build_meta_model,
            model_id_of,
            upstream_supports_meta,
        )

        assert upstream_supports_meta() is False
        monkeypatch.setenv("MODEL_API_KEY", "test-meta-token")
        monkeypatch.setenv("META_BASE_URL", "https://custom-meta.local/v1/")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = build_meta_model("meta/muse-spark-1.3-contributor")
            req = model._format_request(
                messages=[{"role": "user", "content": [{"text": "hi"}]}]
            )
        assert [w for w in caught if issubclass(w.category, UserWarning)] == []
        assert isinstance(model, OpenAIResponsesModel)
        assert model._strands_model_ref == "meta/muse-spark-1.3-contributor"
        assert model_id_of(model, "fallback") == "meta/muse-spark-1.3-contributor"
        assert model.client_args == {
            "base_url": "https://custom-meta.local/v1",
            "api_key": "test-meta-token",
            "admin_api_key": "",
            "organization": "",
            "project": "",
            "webhook_secret": "",
            "default_headers": {
                "OpenAI-Organization": openai.omit,
                "OpenAI-Project": openai.omit,
            },
        }
        assert model.model_info.capabilities.prompt_caching == "auto"
        assert model.model_info.limits.context_window == 1_048_576
        assert model.model_info.limits.max_output_tokens == 131_072
        cfg = model.get_config()
        assert cfg["cache_config"].ttl is None
        assert "prompt_cache_options" not in req
        assert cfg["params"] == {
            "reasoning": {"effort": "high"},
            "tools": [{"type": "web_search"}],
        }

        off_model = build_meta_model("meta/muse-ember-1.0", effort="none")
        assert "reasoning" not in off_model.get_config()["params"]
        off_model2 = build_meta_model("meta/muse-ember-1.0", effort="off")
        assert "reasoning" not in off_model2.get_config()["params"]
        max_model = build_meta_model("meta/muse-wonder-1.0", effort="max")
        assert max_model.get_config()["params"]["reasoning"] == {"effort": "max"}

    def test_meta_adapter_auto_retires_and_wires_startup_switch_route(
        self, monkeypatch, tmp_path
    ):
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        import strands_code_cli.entry.main as entry_main
        from strands_code_cli.model.model_switch import (
            apply_switch,
            configure_base_url_for_model,
            model_id_of,
            resolve_harness_model,
            upstream_supports_meta,
        )

        monkeypatch.setenv("MODEL_API_KEY", "test-meta-token")
        # Startup flow: model_for_config -> build_agent sets caching=False + keeps ref
        built_model = entry_main.model_for_config("meta/muse-spark-1.3-contributor")
        assert model_id_of(built_model, "") == "meta/muse-spark-1.3-contributor"

        captured: dict = {}
        monkeypatch.setattr(
            entry_main,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(model=built_model),
        )
        monkeypatch.setattr(entry_main, "register_steering_hook", lambda _a: object())
        monkeypatch.setattr(entry_main, "bind_steering", lambda _s: None)
        monkeypatch.setattr(entry_main, "bind_main_agent", lambda _a: None)
        monkeypatch.setattr(entry_main, "register_memory_plugin", lambda _a, _l: None)
        entry_main.build_agent("sess-meta", tmp_path / "sess", model=built_model)
        assert captured["caching"] is False

        # /model + /route switch seam
        agent = SimpleNamespace(
            model=None,
            messages=[],
            _base_url="https://override.meta.local/v1",
            _base_url_provider="meta",
        )
        swapped, resolved_id = apply_switch(
            agent, "meta/muse-wonder-1.0", effort="xhigh"
        )
        assert resolved_id == "meta/muse-wonder-1.0"
        assert swapped.client_args["base_url"] == "https://override.meta.local/v1"
        assert swapped.get_config()["params"]["reasoning"] == {"effort": "xhigh"}

        meta_stub = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)
        configure_base_url_for_model(
            "meta/muse-spark-1.3", meta_stub, base_url="https://proxy.meta.local/v1"
        )
        assert meta_stub.client_args["base_url"] == "https://proxy.meta.local/v1"

        # Auto-retire check when upstream strands-harness adds "meta" to _PROVIDERS
        monkeypatch.setitem(harness_models._PROVIDERS, "meta", object())
        assert upstream_supports_meta() is True
        delegated: list = []
        monkeypatch.setattr(
            harness_models,
            "resolve_model",
            lambda *a, **kw: delegated.append((a, kw)) or SimpleNamespace(kwargs=kw),
        )
        resolve_harness_model("meta/muse-spark-1.3-contributor")
        assert delegated and delegated[0][0][0] == "meta/muse-spark-1.3-contributor"
        assert (
            entry_main.model_for_config("meta/muse-spark-1.3-contributor")
            == "meta/muse-spark-1.3-contributor"
        )

    def test_muse_multimodal_media_and_bedrock_llama_scoping(self):
        from strands_code_cli.model.model_switch import (
            convert_history,
            supports_media,
            supports_reasoning,
        )

        for mid in (
            "meta/muse-spark-1.3-contributor",
            "meta/muse-spark-1.3",
            "meta/muse-wonder-1.0",
            "meta/muse-ember-1.0",
        ):
            assert supports_media(mid) is True
            assert supports_reasoning(mid) is False
        assert supports_media("meta.llama3-70b-instruct-v1:0") is False
        assert supports_media("us.meta.llama4-scout-17b-instruct-v1:0") is False
        assert supports_media("litellm/openrouter/meta/llama-x") is False

        history = [
            {
                "role": "assistant",
                "content": [
                    {
                        "reasoningContent": {
                            "reasoningText": {
                                "text": "secret thought",
                                "signature": "sig",
                            }
                        }
                    },
                    {"text": "hi"},
                ],
            },
            {
                "role": "user",
                "content": [{"image": {"format": "png", "source": {"bytes": b"x"}}}],
            },
        ]
        converted = convert_history(
            history, "anthropic/claude-sonnet-5-5", "meta/muse-spark-1.3-contributor"
        )
        assert any(
            "secret thought" in b.get("text", "")
            for b in converted[0]["content"]
            if "text" in b
        )
        assert not any("reasoningContent" in b for b in converted[0]["content"])
        assert "image" in converted[1]["content"][0]

    def test_meta_discovery_filtering_tree_grouping_and_isolation(self, monkeypatch):
        import sys
        import types

        from strands_code_cli.model.model_switch import (
            CURATED_META_MODELS,
            _discover_meta_models,
            _vendor_family,
            build_model_tree,
            discover_models,
        )

        assert _vendor_family("meta/muse-spark-1.3-contributor") == ("meta", "muse")
        assert _vendor_family("muse-ember-1.0") == ("meta", "muse")
        assert _vendor_family("muse-wonder-1.0") == ("meta", "muse")

        monkeypatch.setitem(sys.modules, "boto3", None)
        assert _discover_meta_models() == ([], False)
        opts_unkeyed, offline_u = discover_models(configured=["bedrock/x"])
        assert offline_u is True
        assert opts_unkeyed == ["bedrock/x"]

        monkeypatch.setenv("MODEL_API_KEY", "k-meta")
        monkeypatch.setenv("META_BASE_URL", "https://meta-catalog.local/v1/")
        client_calls: list = []

        class _FakeClient:
            def __init__(self, **kw):
                client_calls.append(kw)
                self.models = types.SimpleNamespace(
                    list=lambda: iter(
                        [
                            types.SimpleNamespace(id="muse-spark-1.3-contributor"),
                            types.SimpleNamespace(id="muse-spark-1.3"),
                            types.SimpleNamespace(id="muse-wonder-1.0"),
                            types.SimpleNamespace(id="muse-ember-1.0"),
                            types.SimpleNamespace(id="muse-spark-1.3\x1b[31m"),
                            types.SimpleNamespace(id="muse-ember-1.0\nfoo"),
                            types.SimpleNamespace(id="muse-image-1.0"),
                            types.SimpleNamespace(id="muse-voice-transcribe-1.0"),
                            types.SimpleNamespace(id="sam-3.1"),
                        ]
                    )
                )

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = _FakeClient
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        found, online = _discover_meta_models()
        assert online is True
        assert client_calls == [
            {
                "api_key": "k-meta",
                "base_url": "https://meta-catalog.local/v1",
                "admin_api_key": "",
                "organization": "",
                "project": "",
                "webhook_secret": "",
                "timeout": 5.0,
                "max_retries": 0,
            }
        ]
        assert found == [
            "meta/muse-spark-1.3-contributor",
            "meta/muse-spark-1.3",
            "meta/muse-wonder-1.0",
            "meta/muse-ember-1.0",
        ]
        merged, offline_m = discover_models()
        assert offline_m is False
        assert "meta/muse-spark-1.3-contributor" in merged
        assert all("muse-image" not in m and "sam-3.1" not in m for m in merged)
        tree = dict(build_model_tree(merged))
        assert "muse" in dict(tree["meta"])

        monkeypatch.setitem(sys.modules, "openai", None)
        fallback, online2 = _discover_meta_models()
        assert online2 is False
        assert fallback == list(CURATED_META_MODELS)

    def test_meta_security_isolates_openai_env_and_validates_inputs(self, monkeypatch):
        from types import SimpleNamespace

        import openai
        import pytest

        from strands_code_cli.model.model_switch import (
            build_meta_model,
            configure_base_url_for_model,
        )

        canaries = {
            "OPENAI_API_KEY": "sk-proj-CANARY_OAI_KEY_1234567890",
            "OPENAI_ADMIN_KEY": "sk-admin-CANARY_ADMIN_KEY_1234",
            "OPENAI_ORG_ID": "org-CANARY_ORG_987",
            "OPENAI_PROJECT_ID": "proj_CANARY_PROJ_654",
            "OPENAI_WEBHOOK_SECRET": "whsec_CANARY_HOOK_321",
            "OPENAI_BASE_URL": "https://evil-openai.invalid/v1",
        }
        for name, val in canaries.items():
            monkeypatch.setenv(name, val)

        def _assert_no_leak(model_obj, expected_host: str) -> None:
            client = openai.AsyncOpenAI(**model_obj.client_args)
            req = client._build_request(
                openai._models.FinalRequestOptions(method="post", url="/responses")
            )
            headers = {k.lower(): v for k, v in req.headers.items()}
            assert str(req.url) == f"{expected_host}/responses"
            assert "openai-organization" not in headers
            assert "openai-project" not in headers
            wire_dump = repr(
                (
                    headers,
                    client.api_key,
                    client.admin_api_key,
                    client.organization,
                    client.project,
                    client.webhook_secret,
                    str(client.base_url),
                )
            )
            for val in canaries.values():
                assert val not in wire_dump

        # Case 1: unkeyed default Meta (e.g. /model dispatch without MODEL_API_KEY)
        monkeypatch.delenv("MODEL_API_KEY", raising=False)
        monkeypatch.delenv("META_API_KEY", raising=False)
        unkeyed = build_meta_model("meta/muse-spark-1.3-contributor")
        _assert_no_leak(unkeyed, "https://api.meta.ai/v1")

        # Case 2: unkeyed custom proxy base_url uses non-empty placeholder, never OPENAI_API_KEY
        proxy = build_meta_model(
            "meta/muse-spark-1.3-contributor",
            base_url="https://meta-proxy.local/v1/",
        )
        _assert_no_leak(proxy, "https://meta-proxy.local/v1")
        assert proxy.client_args["api_key"] == "not-required"

        # Case 3: keyed Meta uses MODEL_API_KEY without leaking OPENAI_ORG_ID/PROJECT_ID/etc.
        monkeypatch.setenv("MODEL_API_KEY", "LLM|123456|MetaSecretValue1234")
        keyed = build_meta_model("meta/muse-ember-1.0")
        _assert_no_leak(keyed, "https://api.meta.ai/v1")
        assert keyed.client_args["api_key"] == "LLM|123456|MetaSecretValue1234"

        # Control chars / whitespace rejected in build_meta_model tail
        for bad_ref in (
            "meta/muse-spark-1.3\x1b[31m",
            "meta/muse-spark-1.3 bad",
        ):
            with pytest.raises(ValueError):
                build_meta_model(bad_ref)

        # configure_base_url_for_model validates schemes and embedded credentials
        stub = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)
        for bad_url in (
            "ftp://evil.local/v1",
            "https://user:pass@proxy.local/v1",
        ):
            with pytest.raises(ValueError):
                configure_base_url_for_model(
                    "meta/muse-spark-1.3", stub, base_url=bad_url
                )

    def test_meta_discovery_effort_and_model_config_edge_branches(self, monkeypatch):
        import sys
        import types
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import (
            CURATED_META_MODELS,
            _discover_meta_models,
            _is_meta_chat_model,
            _normalize_meta_effort,
            build_meta_model,
            upstream_supports_meta,
        )

        # _is_meta_chat_model edge inputs
        for bad_id in (None, "", "   ", "llama-3.3", "muse-spark\x7f", "muse-spark\t1"):
            assert _is_meta_chat_model(bad_id) is False  # type: ignore[arg-type]
        assert _is_meta_chat_model("  muse-spark-1.3  ") is True

        # _normalize_meta_effort edge inputs
        assert _normalize_meta_effort("auto") == "high"
        assert _normalize_meta_effort("  MINIMAL  ") == "minimal"
        assert _normalize_meta_effort("ultra") == "high"

        # _discover_meta_models fallback paths (all filtered or RuntimeError)
        monkeypatch.setenv("MODEL_API_KEY", "k-meta")

        class _OnlyFilteredClient:
            def __init__(self, **_kw):
                self.models = SimpleNamespace(
                    list=lambda: iter(
                        [
                            SimpleNamespace(id="muse-image-1.0"),
                            SimpleNamespace(id="sam-3.1"),
                        ]
                    )
                )

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = _OnlyFilteredClient
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        assert _discover_meta_models() == (list(CURATED_META_MODELS), False)

        class _BoomClient:
            def __init__(self, **_kw):
                self.models = SimpleNamespace(
                    list=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
                )

        fake_openai.OpenAI = _BoomClient
        assert _discover_meta_models() == (list(CURATED_META_MODELS), False)

        # upstream_supports_meta ImportError fallback
        monkeypatch.delitem(sys.modules, "strands_harness.models", raising=False)
        monkeypatch.setitem(sys.modules, "strands_harness.models", None)
        assert upstream_supports_meta() is False
        monkeypatch.setitem(sys.modules, "strands_harness.models", harness_models)

        # build_meta_model edge inputs and optional kwargs disabled
        import openai as real_openai
        import pytest

        monkeypatch.setitem(sys.modules, "openai", real_openai)
        for bad_ref in ("openai/gpt-6.2-sol", "meta/", "meta/   "):
            with pytest.raises(ValueError):
                build_meta_model(bad_ref)

        bare_meta = build_meta_model(
            "meta/muse-ember-1.0", effort="none", web_search=False, caching=False
        )
        bare_cfg = bare_meta.get_config()
        assert not bare_cfg.get("params")
        assert bare_cfg.get("cache_config") is None

    def test_meta_base_url_harness_web_search_and_entry_edge_branches(
        self, monkeypatch, tmp_path
    ):
        from types import SimpleNamespace

        import strands_harness.models as harness_models

        import strands_code_cli.entry.main as entry_main
        from strands_code_cli.model.model_switch import (
            configure_base_url_for_model,
            resolve_harness_model,
        )

        # configure_base_url_for_model overwrites meta/ (stripped) vs preserves openai/
        meta_stub = SimpleNamespace(
            client_args={"base_url": "https://api.meta.ai/v1"},
            _bedrock_mantle_config=None,
        )
        configure_base_url_for_model(
            "meta/muse-spark-1.3", meta_stub, base_url="https://meta-proxy.local/v1/"
        )
        assert meta_stub.client_args["base_url"] == "https://meta-proxy.local/v1"

        oai_stub = SimpleNamespace(
            client_args={"base_url": "https://existing-oai.local/v1"},
            _bedrock_mantle_config=None,
        )
        configure_base_url_for_model(
            "openai/gpt-6.2-sol", oai_stub, base_url="https://new-oai.local/v1"
        )
        assert oai_stub.client_args["base_url"] == "https://existing-oai.local/v1"

        # resolve_harness_model _web_search_kind gating (#5997)
        calls: list[dict] = []
        monkeypatch.setattr(harness_models, "supports_web_search", lambda _m: True)
        monkeypatch.setattr(
            harness_models,
            "resolve_model",
            lambda _m, _d, **kw: calls.append(kw) or SimpleNamespace(kwargs=kw),
        )
        monkeypatch.setattr(
            harness_models, "_web_search_kind", lambda _m: "agentcore", raising=False
        )
        resolve_harness_model("us.amazon.nova-2-lite-v1:0")
        assert "web_search" not in calls[-1]

        monkeypatch.setattr(
            harness_models, "_web_search_kind", lambda _m: "native", raising=False
        )
        resolve_harness_model("openai/gpt-6.2-sol")
        assert calls[-1]["web_search"] is True

        monkeypatch.delattr(harness_models, "_web_search_kind", raising=False)
        resolve_harness_model("openai/gpt-6.2-sol")
        assert calls[-1]["web_search"] is True

        # entry_main ImportError fallback & string model + base_url web_fetch pin
        monkeypatch.setattr(
            entry_main,
            "build_meta_model",
            lambda *_a, **_kw: (_ for _ in ()).throw(ImportError("missing openai")),
        )
        assert (
            entry_main.model_for_config("meta/muse-spark-1.3-contributor")
            == "meta/muse-spark-1.3-contributor"
        )

        captured: dict = {}
        monkeypatch.setattr(
            entry_main,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(model=None),
        )
        monkeypatch.setattr(entry_main, "register_steering_hook", lambda _a: object())
        monkeypatch.setattr(entry_main, "bind_steering", lambda _s: None)
        monkeypatch.setattr(entry_main, "bind_main_agent", lambda _a: None)
        monkeypatch.setattr(entry_main, "register_memory_plugin", lambda _a, _l: None)
        entry_main.build_agent(
            "sess-meta-str",
            tmp_path / "sess-meta-str",
            model="meta/muse-spark-1.3-contributor",
            base_url="https://meta-proxy.local/v1",
        )
        assert captured["builtin_tools"]["web_fetch"] == {
            "model": "meta/muse-spark-1.3-contributor"
        }
