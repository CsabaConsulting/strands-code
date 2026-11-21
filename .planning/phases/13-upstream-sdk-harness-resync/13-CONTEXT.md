# Phase 13: Upstream SDK & Harness Resync - Context

**Gathered:** 2026-11-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Re-base `strands-code` cleanly onto `strands-agents >=1.65.0` and `strands-harness >=0.4.0` (`UPSTREAM-01`), closing the Phase 4 cross-family `reasoningContent` restore blocker (`#5166` + `drop_block`), adapting `estimate_messages_tokens` and `canonical_prefix_hash` for `ContextInjector` `InjectedBlock` (`{"injected": {"text": ...}}`), integrating SDK `Model.model_info.limits.context_window` into `window_for()`, preemptively setting `streaming=False` on `BedrockModel` for `_NO_STREAMING_TOOLS` (Llama 3/4), and auditing `harness-py v0.4.0` `todos` removal while preserving `BeforeToolCallEvent.cancel_tool` boundary steering.

Out of scope: Google Gemini `google/` provider features and provider-aware `first_run.py` preflight (`Phase 14`), `strands.decisions.DecisionModel` routing refactor (`Phase 15`), remote skills marketplaces (`Phase 16`), Strands Box Linux containment (`Phase 17`), `/help`/`@file`/`/review` UX additions (`Phase 18`), and `strands-agents-evals` (`Phase 19`).

</domain>

<decisions>
## Implementation Decisions

### Dependency Bounds & Lockfile
- **D-01 (Dependency floors):** Raise lower bounds in `pyproject.toml` to `strands-agents>=1.65.0` and `strands-harness>=0.4.0` while keeping **zero upper pins** during the experimental phase, and upgrade `uv.lock` accordingly (`uv lock --upgrade-package strands-agents --upgrade-package strands-harness` / full compatible sync). — *Reversibility: easy — lower bounds align packaging with relied-upon upstream primitives (`#5166`, `#5158`, `Model.model_info`, `InjectedBlock`) and eliminate dead pre-`1.65` branches.*

### Context Window Precedence
- **D-02 (`window_for()` precedence):** In `cost_context.window_for(model_id)` (and downstream `estimate_fit()` / auto-compact), resolve context windows in this order:
  1. **OpenRouter live (`openrouter_entry`)** first for `litellm/openrouter/*` aggregator routes (respecting OpenRouter's per-endpoint context caps).
  2. **SDK `Model.model_info.limits.context_window`** first for all direct providers (authoritative, zero-network offline coverage; optional live model instance passed or inspected cleanly when available).
  3. **LiteLLM bundled (`litellm_entry`)** next, followed by **static `MODEL_LIMITS`** fallback.
  — *Reversibility: easy — centralized in `strands_code_cli/cost/cost_context.py`.*

### Bedrock Unary Tool Mode (`_NO_STREAMING_TOOLS`)
- **D-03 (Preemptive `streaming=False` + concise note):** Automatically configure `streaming=False` on `BedrockModel` whenever `not supports_streaming_tools(model_id)` (Bedrock Llama 3/4) across initial `build_agent`, `/model` switch (`apply_switch`), `/route` switch, and `/btw` side spawns. Because `CodeAgentCallbackHandler` renders whole `'message'` events, terminal rendering stays identical. Replace the obsolete `"Warning: ... turns will fail ..."` messages at `loop/core.py:1127`, `1362`, and `2255` with a concise info note: `"Note: streaming disabled for <model> (Bedrock unary tool mode)."` on session launch and explicit `/model` switches, suppressed (`quiet`) on per-ask `/route` switches. — *Reversibility: easy — upstream closed `#4857`/`#4937` recommending client-side `streaming=False` maps.*

### Session Restore History Handling
- **D-04 (Hybrid session restore):** Rely on upstream `#5166` (`BedrockModel._rejects_reasoning_block`) + `v1.62.0` (`drop_block` retry) to handle cross-family Bedrock wire stripping on session restore (`--session-id` / `/resume`) without mutating persisted `agent.messages` when the opening model is media-capable Bedrock, **AND** run `convert_history()` on session launch / `/resume` when the opening model is non-Bedrock (e.g., `openai/...`, `litellm/...`, `anthropic/...`) or media-less (`not supports_media(current_model)`) so foreign `reasoningContent` and `image`/`video` blocks cannot fail validation on non-Bedrock adapters or text-only models. Keep `convert_history()` on all explicit in-session `/model` switches so prior reasoning is preserved as readable `[Thinking trace]` text. — *Reversibility: moderate — touches launch/resume history preparation and `RichHistory` interaction.*

### Upstream `harness-py >=0.4.0` & `strands-py >=1.65.0` Reconciliation
- **D-05 (`ContextInjector` `InjectedBlock` accounting):** Update `cost_context.estimate_messages_tokens()` (`L445-465`) to count `block.get("injected", {}).get("text", "")` toward the 80% auto-compact budget, and ensure `model_switch.canonical_prefix_hash()` (`L249-275`) ignores `"injected"` blocks so memory-file edits (`STRANDS.md` / `.agent/MEMORY.md`) or re-injections never invalidate `RichHistory` stashes. Verify `CodeAgentCallbackHandler` does not echo `injected` blocks and `tests/memory/test_memory_file.py` passes against `harness-py >=0.4.0`.
- **D-06 (Boundary steering & `todos` audit):** Keep `BeforeToolCallEvent.cancel_tool` in `loop/steering.py` (`Agent.cancel()` aborts whole turns rather than redirecting mid-turn) and keep `cancel_signal=cancel_event` in `_invoke_agent`. Verify `harness-py v0.4.0` removing default `"todos"` introduces zero prompt or test regressions (leave `"todos"` off).
- **D-07 (Byproduct-only upstreaming):** If bumping `strands-agents` / `strands-harness` uncovers any compatibility issue in `strands_code_agent/` (kept byte-pristine under `D-24`), document it cleanly for a targeted upstream PR to `aws-samples/sample-strands-code-agent` without expanding Phase 13 scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `UPSTREAM-01` requirements
- `.planning/ROADMAP.md` — Phase 13 goal & 3 success criteria
- `.planning/research/STACK.md` — `strands-py >=1.65` & `harness-py >=0.4` primitives
- `.planning/research/ARCHITECTURE.md` — Routing/steering/context seams & `xenon` C ceiling
- `.planning/research/PITFALLS.md` — Pitfall 5 (`ContextInjector` `InjectedBlock`)
- `pyproject.toml` — Dependency floors (`L27-37`), `D-24` exclude (`L76-78`), CI gates
- `strands_code_cli/entry/main.py` — `build_agent`, `model_for_config`
- `strands_code_cli/model/model_switch.py` — `_NO_STREAMING_TOOLS` (`L66-77`), `supports_streaming_tools` (`L186`), `canonical_prefix_hash` (`L249-275`), `apply_switch` (`L664-696`)
- `strands_code_cli/cost/cost_context.py` — `window_for` (`L122-129`), `estimate_messages_tokens` (`L445-465`)
- `strands_code_cli/loop/core.py` — `_NO_STREAMING_TOOLS` messages (`L1126-1131`, `L1362-1368`, `L2253-2261`), `apply_model_action` (`C 19`), `run_loop` (`C 18`)
- `strands_code_cli/loop/steering.py` — `BeforeToolCallEvent.cancel_tool` boundary hook
- `strands_code_cli/memory/memory_file.py` — `ContextInjector` registration (`L335-355`)
- `strands_code_agent/callback_handler.py` — Whole-message rendering (`L74-137`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `supports_streaming_tools()` (`strands_code_cli/model/model_switch.py:186`) already identifies Bedrock Llama 3/4 models needing unary tool mode.
- `apply_switch()` (`model_switch.py:664-696`) and `model_for_config()` (`entry/main.py:86-106`) centralize `resolve_model(...)` construction so `streaming=False` can be wired uniformly across startup, `/model`, `/route`, and `/btw`.
- `window_for()` (`cost_context.py:122-129`) already funnels live and static window lookups through one seam.
- `CodeAgentCallbackHandler.__call__` (`strands_code_agent/callback_handler.py:88-137`) renders `'message'` items (`'text'`, `'toolUse'`, `'toolResult'`), tolerating non-streaming `BedrockModel` turns and `'injected'` blocks without changes.

### Constraints & Watchpoints
- **Cyclomatic complexity (`xenon --max-absolute C`, max 20):** `run_loop` sits at `C (18)` and `apply_model_action` at `C (19)`. Extract clean helpers for any new resume/conversion or unary-note logic rather than growing those functions.
- **No `ModelRouter` / `Agent.cancel()` replacement:** Explicitly deferred/rejected in `v2.0` Out of Scope and `D-06`.

</code_context>

<specifics>
## Specific Ideas

- Keep `"Note: streaming disabled for <model> (Bedrock unary tool mode)."` concise on launch and `/model`, and omit it on `/route` (`quiet`) so per-ask routing transcripts stay clean.
- On hybrid session restore (`D-04`), check media capability (`supports_media`) alongside non-Bedrock provider check (`_provider_of(current_model) != "bedrock"`) so resuming an image-carrying or cross-provider session never fails silently or with `ValidationException`.

</specifics>

<deferred>
## Deferred Ideas

- Google Gemini `google/` provider integration, `toolUse["reasoningSignature"]` stripping, and provider-aware `first_run.py` preflight — queued for **Phase 14 (`MODEL-06`)**.
- Migrating custom Decision-API transports onto `strands.decisions.DecisionModel` — queued for **Phase 15 (`UPSTREAM-02`)**.

</deferred>

---

*Phase: 13-upstream-sdk-harness-resync*
*Context gathered: 2026-11-21*
