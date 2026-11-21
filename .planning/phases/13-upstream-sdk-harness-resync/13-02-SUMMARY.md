---
phase: 13-upstream-sdk-harness-resync
plan: "02"
subsystem: cost-model-policy-loop
tags: [model_info, bedrock, streaming, resume, hitl, strands-agents, upstream-resync]
dependency_graph:
  requires:
    - 13-01 (strands-agents==1.65.0, strands-harness==0.4.0 in .venv and uv.lock)
  provides:
    - Route-aware SDK Model.model_info context window precedence in cost_context.window_for() (D-02)
    - Preemptive streaming=False for _NO_STREAMING_TOOLS Bedrock models across all 4 call sites + UNARY_TOOL_MODE_NOTE (D-03)
    - Hybrid session restore via model_switch.prepare_resumed_history() + #5166 wire-strip pin closing Phase 4 blocker (D-04)
    - PolicyHumanInTheLoop preserving DENY:/Plan-mode reasons under strands-agents 1.65.0 Proceed/Deny inline HITL actions
  affects:
    - Phase 14 (MODEL-06 Gemini / provider-aware startup inherits window_for and hybrid convert_history/restore seams)
    - Phase 15 (UPSTREAM-02 DecisionModel routing benefits from clean unary-mode routing and green HITL gates)
tech_stack:
  added: []
  updated:
    - strands_code_cli/cost/cost_context.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/policy/policy_gate.py
key_files:
  modified:
    - strands_code_cli/cost/cost_context.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/policy/policy_gate.py
    - tests/cost/test_cost_context.py
    - tests/cost/test_live_pricing.py
    - tests/loop/test_btw.py
    - tests/model/test_model_switch.py
    - tests/policy/test_broker.py
    - tests/policy/test_diff_gate.py
    - tests/policy/test_mode.py
    - tests/policy/test_policy_gate.py
    - tests/ui/test_choice.py
decisions:
  - D-02: window_for(model_id, *, model=None) checks openrouter_entry before _sdk_window on litellm/openrouter/* routes, and _sdk_window before LiteLLM/static MODEL_LIMITS on direct providers.
  - D-03: configure_streaming_for_model() sets streaming=False on Bedrock _NO_STREAMING_TOOLS models across apply_switch, build_agent, _route_side_spawn, and build_btw_agent; UNARY_TOOL_MODE_NOTE renders on launch and /model while /route stays quiet.
  - D-04: prepare_resumed_history() leaves media-capable Bedrock histories untouched so upstream #5166 / drop_block strip incompatible reasoningContent on the wire, and runs convert_history() (+ RichHistory stash) when resuming onto non-Bedrock or media-less targets.
  - D-07 / Option B HITL reconciliation: PolicyHumanInTheLoop subclasses HumanInTheLoop so inline-ask Deny actions under strands-agents >=1.65.0 retain classifier rule and Plan-mode deny reasons instead of generic human-rejected text.
metrics:
  completed_date: "2026-11-21"
  commit: "8c8b70f"
  tests_passed: 1559
  tests_deselected: 11
---

# Phase 13 Plan 02: SDK `model_info`, Bedrock Unary Mode, Hybrid Restore & CI Gates Summary

**One-liner:** Integrated route-aware SDK `Model.model_info` context windows (`D-02`), preemptive Bedrock `streaming=False` for Llama 3/4 (`D-03`), hybrid session restore paired with upstream `#5166` wire stripping (`D-04`, closing the Phase 4 restore blocker), and `PolicyHumanInTheLoop` for `strands-agents 1.65.0` inline HITL actions — with all 6 `.github/workflows/gates.yml` checks green (`1559 passed, 11 deselected`).

---

## Key Changes & Seams

1. **SDK `Model.model_info` Context Window Precedence (`D-02` — [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py)):**
   - Added `_sdk_window_candidates`, `_instance_context_window`, `_sdk_window`, `_openrouter_window`, and `_litellm_window`, resolving offline against `strands.models._model_info.get_context_window_limit` (and live `model.model_info.limits.context_window` when supplied) without instantiating `boto3` or provider HTTP clients.
   - Updated `window_for(model_id, *, model=None)` so `litellm/openrouter/*` routes check OpenRouter live (`openrouter_entry`) first before `_sdk_window` -> LiteLLM -> `MODEL_LIMITS`, while direct providers check `_sdk_window` first before LiteLLM / `MODEL_LIMITS`. Updated `context_report()` to forward `model=getattr(agent, "model", None)`.
   - Added `TestSdkModelInfoWindow` in [test_cost_context.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_cost_context.py) and pinned the LiteLLM fallback assertion in [test_live_pricing.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_live_pricing.py) (`111 passed, 2 warnings`).

2. **Bedrock Unary Tool Mode for `_NO_STREAMING_TOOLS` (`D-03`):**
   - Added `UNARY_TOOL_MODE_NOTE` (`"Note: streaming disabled for {model_id} (Bedrock unary tool mode)."`) and `configure_streaming_for_model()` in [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), disabling streaming (`update_config(streaming=False)`) fail-soft whenever `_provider_of(normalize_model_ref(model_id)) == "bedrock"` and `not supports_streaming_tools(normalized)`.
   - Wired `configure_streaming_for_model` across all 4 construction/switch call sites: `apply_switch` ([model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py)), `build_agent` ([main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py)), `_route_side_spawn` ([core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py)), and `build_btw_agent` ([btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py)).
   - Updated launch (`_warn_if_no_streaming_tools` dim note) and `/model` (`apply_model_action` reply note) while deleting the yellow warning from `/route` (`_apply_routed_pick`) so routed switches stay silent. Added coverage in [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py) and [test_btw.py](file:///home/csaba/repos/AWS/strands-code/tests/loop/test_btw.py).

3. **Hybrid Session Restore & Upstream `#5166` Pin (`D-04`, closes Phase 4 Blocker):**
   - Added `_has_reasoning()` and `prepare_resumed_history(agent, current_model, rich=None, stash_path=None)` in [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), wired as one branchless call in [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) (`run_loop` right after `RichHistory.load(stash_path)`), preserving `run_loop`'s `xenon` complexity headroom.
   - Media-capable Bedrock opening models leave `agent.messages` untouched so upstream `#5166` (`BedrockModel._rejects_reasoning_block`) + `drop_block` handle cross-family wire stripping without erasing snapshot traces; non-Bedrock and media-less targets run `convert_history()` in place and stash raw thinking into `RichHistory`.
   - Added `TestPrepareResumedHistory` and `TestUpstreamReasoningWireStrip` in [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py), pinning real installed `BedrockModel._format_bedrock_messages` stripping signed Anthropic `reasoningContent` on `amazon.nova-2-lite-v1:0`, `qwen.qwen3-32b-v1:0`, and `amazon.nova-lite-v1:0` offline (`119 passed` in `test_model_switch.py`).

4. **`strands-agents==1.65.0` Inline HITL Reconciliation (`Option B` under `D-07`):**
   - Upstream `HumanInTheLoop.before_tool_call` (`strands/vended_interventions/hitl/hitl.py`) changed from returning `Confirm` (with classifier reason in `Confirm.prompt`) to evaluating inline `ask` calls immediately and returning `Proceed()` or `Deny(reason='Tool "..." denied: the human rejected the call.')`.
   - Added `PolicyClassifier.last_deny_reason()` and `PolicyHumanInTheLoop(HumanInTheLoop)` in [policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py) and wired `build_interventions()` to use it, preserving `"Plan mode is read-only ..."` and `"DENY:<rule>"` (+ `REVISE_HINT` on `python_repl`) model-facing `Deny` reasons.
   - Reconciled the 24 affected assertions across [test_broker.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_broker.py), [test_diff_gate.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_diff_gate.py), [test_mode.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_mode.py), [test_policy_gate.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy_gate.py), and [test_choice.py](file:///home/csaba/repos/AWS/strands-code/tests/ui/test_choice.py) (`333 passed`).

---

## Verification Results

All checks ran after the final edit (`8c8b70f`):

- **Lockfile check:** `/home/csaba/.local/bin/uv lock --check` -> `Resolved 139 packages in 2ms` (exit `0`)
- **Full test suite (`.venv/bin/pytest tests/ -q`):**
  - Inside restricted sandbox network (`BypassSandbox: false`): `1558 passed, 1 failed` (`tests/routing/test_routing.py::TestLiveEngines::test_stub_server_systemone_decision_routes` only, due to loopback HTTP block to `127.0.0.1`).
  - Unsandboxed (`BypassSandbox: true`, matching CI runner): **`1559 passed, 11 deselected, 1148 warnings`** (exit `0`).
- **Lint:** `.venv/bin/ruff check strands_code_cli tests scripts` -> `All checks passed!` (exit `0`).
- **Format:** `.venv/bin/ruff format --check strands_code_cli tests scripts` -> `110 files already formatted` (exit `0`).
- **Complexity:** `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> exit `0` (`CC <= 20`).
- **Import contracts:** `.venv/bin/lint-imports` -> `Analyzed 39 files, 81 dependencies. Contracts: 1 kept, 0 broken.` (exit `0`).
- **`CLEANUP-01` & `D-24` guards:** `examples/pdf_to_okf_bundle` & `strands_code_agent/knowledge` absent, zero grep matches, and `git diff strands_code_agent/` empty.
