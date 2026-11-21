# Phase 13: Upstream SDK & Harness Resync - Pattern Map

**Mapped:** 2026-11-21
**Phase:** `13-upstream-sdk-harness-resync` (`UPSTREAM-01`)
**Files analyzed:** 11 (0 new, 11 modified: 2 packaging/lock, 5 CLI modules, 5 test mirrors)

---

## File Classification

| Modified File | Role | Data Flow | Analog / Seam | Match Quality |
| :--- | :--- | :--- | :--- | :--- |
| `pyproject.toml` | packaging config | declarative | itself (`dependencies` list `L27-37`) | exact |
| `uv.lock` | lockfile | generated | itself (`uv lock --upgrade-package ...`) | exact |
| `strands_code_cli/cost/cost_context.py` | utility | transform | itself (`_live_window`, `window_for`, `estimate_messages_tokens`) | exact |
| `strands_code_cli/model/model_switch.py` | service | transform + config | `cost/reported_cost.py:wrap_for_openrouter` + `apply_switch` | role-match |
| `strands_code_cli/entry/main.py` | composition root | init | `build_agent` openrouter wrap block (`L179-196`) | exact |
| `strands_code_cli/loop/btw.py` | service | transform + init | itself (`fork_btw_history`, `build_btw_agent`) | exact |
| `strands_code_cli/loop/core.py` | controller | session lifecycle | itself (`apply_model_action`, `_route_side_spawn`, `run_loop`) | exact |
| `tests/cost/test_cost_context.py` | test | unit | itself (`TestUsageAndWindow`, `TestEstimateTokens`) | exact |
| `tests/cost/test_live_pricing.py` | test | unit | itself (`TestLivePricingLayers`) | exact |
| `tests/model/test_model_switch.py` | test | unit | itself (`TestCanonicalPrefixHash`, `TestStreamingTools`, `TestApplyModelAction`) | exact |
| `tests/loop/test_btw.py` & `tests/memory/test_memory_file.py` | test | unit | themselves (`TestForkBtwHistory`, `TestMemoryPlugin`) | exact |

---

## Pattern Assignments

### 1. `strands_code_cli/model/model_switch.py` (`configure_streaming_for_model`, `prepare_resumed_history`, `canonical_prefix_hash`)
- **Analog for wrapper/configurator:** `wrap_for_openrouter` (`strands_code_cli/cost/reported_cost.py`) + `model_switch.apply_switch` (`L664-696`).
- **Pattern:** Fail-soft configuration helper accepting `(model_id: str, resolved: Any) -> Any`:
  - Normalize `model_id` via `normalize_model_ref`, verify `_provider_of(...) == "bedrock"` and `not supports_streaming_tools(model_id)`, then invoke `update_config(streaming=False)` if callable (try/except logging debug/warning on mock mismatch — never crash session launch or `/model` switch on test doubles).
- **Constants pattern:** Define `UNARY_TOOL_MODE_NOTE = "Note: streaming disabled for {model_id} (Bedrock unary tool mode)."` alongside `MODEL_REFUSAL` (`L28`).
- **`canonical_prefix_hash` (`L249-275`):** Add `or "injected" in block` to the existing skip filter (`"reasoningContent" in block or "image" in block or "video" in block`).
- **`prepare_resumed_history(agent, current_model, rich)`:** Exported helper keeping `run_loop` complexity unchanged (`C 18`): reads `agent.messages` fail-soft, short-circuits on empty history or `_provider_of(target) == "bedrock" and supports_media(target)`, otherwise converts via `convert_history(...)` and mutates `agent.messages[:] = converted`.

### 2. `strands_code_cli/cost/cost_context.py` (`_sdk_window`, `window_for`, `estimate_messages_tokens`)
- **Analog:** `_live_window` (`L100-110`) & `_best_hit` (`L67-77`).
- **Pattern:**
  - Read SDK bundled model info via lazy import inside `_sdk_window(model_id: str) -> int | None` (with `try/except (ImportError, Exception)` fail-soft so offline stubs remain safe) + optional live `model` `model_info.limits.context_window` check when applicable.
  - Route-aware order in `window_for(model_id)`:
    ```python
    if live_pricing.is_openrouter_id(model_id):
        # OpenRouter live endpoint cap first -> SDK model_info -> LiteLLM -> MODEL_LIMITS
    else:
        # SDK model_info first -> LiteLLM bundled -> MODEL_LIMITS
    ```
    (Respecting `live_pricing.live_disabled()` on the live/LiteLLM network/bundle branches just as today.)
  - In `estimate_messages_tokens` (`L449-464`), mirror the existing `isinstance(..., dict)` pattern:
    ```python
    injected = block.get("injected")
    if isinstance(injected, dict):
        chars += len(str(injected.get("text", "")))
    ```

### 3. Call Sites in `entry/main.py`, `loop/btw.py`, & `loop/core.py`
- **`entry/main.py:build_agent` (`L179-196`):** Follow the existing `resolved = getattr(agent, "model", None)` pattern right after `create_harness(**kwargs)` to call `configure_streaming_for_model(model or DEFAULT_MODEL, resolved)` (using `model if isinstance(model, str) else model_id_of(...)` fail-soft).
- **`loop/core.py:_route_side_spawn` (`L504-508`):** Call `configure_streaming_for_model(pick.model, routed)` immediately alongside `wrap_for_openrouter(pick.model, routed)` AND check `configure_streaming_for_model(current_model, live_model)` if needed; remove lines `L1362-1368` (`_route_pre_turn` streaming warning — reduces `C` complexity and honors `D-03` quiet on `/route`).
- **`loop/core.py:apply_model_action` & `_warn_if_no_streaming_tools` (`L1126-1135`, `L2253-2261`):** Swap warning text to `UNARY_TOOL_MODE_NOTE.format(model_id=...)` (keep `_route_pre_turn` silent via `quiet_streaming_note` or by ignoring/omitting unary note in `_print_routed_note`).
- **`loop/core.py:run_loop` (`L2513`):** Single one-line call `prepare_resumed_history(agent, current_model, rich)` directly after `rich = RichHistory.load(stash_path)` (adds 0 cyclomatic branches to `run_loop`).
- **`loop/btw.py:fork_btw_history` (`L200-208`):** Add `and "injected" not in block` to the block comprehension. `build_btw_agent` (`L451`): call `configure_streaming_for_model` if `parent_kwargs["model"]` resolved to a `BedrockModel` from string.

---

## Coding Conventions Enforced
- Absolute imports (`from strands_code_cli...`), no relative imports.
- `logger = logging.getLogger(__name__)` with `%s` formatting (no `print()` in library/CLI logic outside `console` / `print_plain`).
- Zero Rich markup tags in `print_plain` calls.
- Preserve `xenon --max-absolute C` (`CC <= 20`) everywhere — keep `run_loop` <= 18 and `apply_model_action` <= 19.
- Never reference `strands_code_agent.knowledge` or `pdf_to_okf` (`CLEANUP-01` CI grep guard).
