---
phase: 13
slug: upstream-sdk-harness-resync
verified: 2026-11-21T21:35:00Z
status: passed
score: 10/10
---

# Phase 13 Verification Report (`UPSTREAM-01`)

**Status:** Passed (`10/10` truths & criteria verified against `31ecc3e` and `8c8b70f`)

---

## Success Criteria & `must_haves` Checklist

| # | Criterion / Must-Have | Plan / Decision | Evidence & Observed Output | Status |
|---|---|---|---|---|
| 1 | `pyproject.toml` declares `strands-agents>=1.65.0` and `strands-harness>=0.4.0` with zero upper pins; `uv.lock` resolves both | `13-01` / `D-01` | [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml#L27-L31) sets `>=1.65.0` & `>=0.4.0` with no `<` upper pins; `.venv` has `strands-agents==1.65.0`, `strands-harness==0.4.0`; `uv lock --check` resolved 139 packages (exit `0`) | ✅ Verified |
| 2 | Existing agent, steering, and memory tests pass without reviving default `todos` or altering `steering.py` boundary semantics | `13-01` / `D-06`, `D-07` | `BeforeToolCallEvent.cancel_tool` retained in `steering.py`; `tests/memory/test_memory_file.py` updated to match `ContextInjector` (`agent.add_middleware`); `strands_code_agent/` byte-pristine (`git diff strands_code_agent/` empty); full suite `1559 passed, 11 deselected` | ✅ Verified |
| 3 | `estimate_messages_tokens` counts `ContextInjector` `InjectedBlock` (`{"injected": {"text": ...}}`) | `13-01` / `D-05` | [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) sums `len(text)` for dict `injected` blocks; tested in `tests/cost/test_cost_context.py` | ✅ Verified |
| 4 | `canonical_prefix_hash` ignores `"injected"` blocks so `RichHistory` stashes remain valid across memory reloads | `13-01` / `D-05` | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) skips `"injected" in block`; tested in `tests/model/test_model_switch.py` (`TestCanonicalPrefixHash`) | ✅ Verified |
| 5 | `fork_btw_history` strips `"injected"` blocks and `CodeAgentCallbackHandler` never echoes them | `13-01` / `D-05` | [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py) filters `"injected" not in block`; callback non-echo tested in `tests/model/test_model_switch.py` and `tests/loop/test_btw.py` | ✅ Verified |
| 6 | Route-aware `window_for()` checks OpenRouter live first on `litellm/openrouter/*` and SDK `Model.model_info.limits.context_window` first on direct providers, then LiteLLM / `MODEL_LIMITS` | `13-02` / `D-02` | [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) implements `_sdk_window` (offline `get_context_window_limit` + `model.model_info`) and route-aware `window_for(model_id, *, model=None)`; `tests/cost/test_cost_context.py` & `test_live_pricing.py` `111 passed` | ✅ Verified |
| 7 | Bedrock `_NO_STREAMING_TOOLS` models receive `streaming=False` across `build_agent`, `apply_switch`, `_route_side_spawn`, and `build_btw_agent` with concise launch/`/model` notes (`quiet` on `/route`) | `13-02` / `D-03` | `configure_streaming_for_model` & `UNARY_TOOL_MODE_NOTE` wired across `model_switch.py`, `main.py`, `core.py`, `btw.py`; tested across `TestConfigureStreamingForModel`, `test_startup_on_llama_warns_once`, `test_switch_to_llama_warns_in_reply`, `TestBuildBtwAgent` | ✅ Verified |
| 8 | Hybrid session restore (`prepare_resumed_history`) leaves media-capable Bedrock histories untouched for `#5166` / `drop_block` wire stripping and runs `convert_history()` on non-Bedrock / media-less models | `13-02` / `D-04` | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) `prepare_resumed_history` wired in `loop/core.py:run_loop`; verified in `TestPrepareResumedHistory` & `TestUpstreamReasoningWireStrip` (`BedrockModel._format_bedrock_messages` drops foreign signed `reasoningContent` on Nova 2 Lite, Nova 1 Lite, Qwen 3) | ✅ Verified |
| 9 | Inline `HumanInTheLoop` behavior under `strands-agents==1.65.0` preserves classifier `[deny]` / Plan-mode deny reasons | `13-02` / `D-07` | [policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py) `PolicyHumanInTheLoop` + `PolicyClassifier.last_deny_reason`; `tests/policy/` & `tests/ui/test_choice.py` `333 passed` | ✅ Verified |
| 10 | All 6 `.github/workflows/gates.yml` CI gates pass with zero failures or complexity/layering violations | `13-02` / Gates | `pytest tests/ -q`: `1559 passed, 11 deselected`; `ruff check`: `All checks passed!`; `ruff format --check`: `110 files already formatted`; `xenon --max-absolute C`: exit `0`; `lint-imports`: `1 kept, 0 broken`; `CLEANUP-01` grep & absence: exit `0` | ✅ Verified |

---

## Manual Smoke Note

Live Bedrock runtime calls (`us.meta.llama4-scout-17b-instruct-v1:0` unary tool execution and Opus -> Nova session `--session-id` round-trip against live AWS) remain optional manual smokes when AWS credentials are available; offline `BedrockModel._format_bedrock_messages` wire formatting and `BedrockModel.update_config(streaming=False)` configuration are pinned in automated unit tests (`TestUpstreamReasoningWireStrip`, `test_switch_to_llama_warns_in_reply`).
