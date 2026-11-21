# Phase 13: Upstream SDK & Harness Resync - Research

**Researched:** 2026-11-21
**Phase:** `13-upstream-sdk-harness-resync` (`UPSTREAM-01`)
**Decisions Locked:** `13-CONTEXT.md` (`D-01`..`D-07`)

---

## 1. Packaging & Toolchain Contracts (`D-01`, `D-07`)

- **Host `uv` binary:** `/home/csaba/.local/bin/uv` (`uv 0.12.23`).
- **`pyproject.toml` dependencies (`L27-37`):** Currently `"strands-agents>=0.1.0"` and `"strands-harness>=0.1"`. `D-01` raises lower bounds to `"strands-agents>=1.65.0"` and `"strands-harness>=0.4.0"` with **zero upper pins**.
- **CI gates (`.github/workflows/gates.yml`):**
  1. `uv sync --locked --extra litellm`
  2. `uv run pytest tests/ -q` (`addopts = "-m 'not integration'"`)
  3. `uv run ruff check strands_code_cli tests scripts`
  4. `uv run ruff format --check strands_code_cli tests scripts`
  5. `uv run --group dev xenon --max-absolute C strands_code_cli tests scripts` (`CC <= 20`)
  6. `uv run --group dev lint-imports` (`strands_code_cli` -> `strands_code_cli.entry.main` forbidden)
  7. `CLEANUP-01` absence + grep guard (never reference `strands_code_agent.knowledge` or `pdf_to_okf` in `.py` files)
- **`D-24` library boundary (`pyproject.toml:76-78`):** `strands_code_agent/` stays untouched except for deliberate upstream syncs; any compatibility adjustments surfaced by `strands-agents >=1.65` are recorded cleanly for optional upstreaming (`D-07`).

---

## 2. `ContextInjector` `InjectedBlock` & Plugin Audits (`D-05`, `D-06`)

### 2.1 `InjectedBlock` Wire/Message Shape
In `strands-agents >=1.65` / `strands-harness >=0.4.0`, `ContextInjector` writes rendered context into `agent.messages` as `{"injected": {"text": "..."}}` (on models supporting temporary system blocks such as Anthropic Claude it delivers per-call temporary system blocks while still recording `InjectedBlock` semantics safely across tool turns via `#5158`).
- **`strands_code_cli/memory/memory_file.py:348`:** Already constructs `ContextInjector(render, name="strands-code:memory", trigger="userTurn")`, matching the keyword signature.
- **`tests/memory/test_memory_file.py:167-184`:** `test_register_twice_registers_exactly_once` passes a `SimpleNamespace(_middleware_registry=SimpleNamespace(add_middleware=...))` stub to `register_memory_plugin`; Wave 1 Task 1 must verify immediately after `uv lock` + `uv sync` whether `ContextInjector.init_agent` expects additional attributes on the stub or works verbatim.
- **`cost_context.estimate_messages_tokens` (`strands_code_cli/cost/cost_context.py:445-465`):** Currently inspects `"text"`, `"toolUse"`, `"toolResult"`, and `"reasoningContent"` ONLY. Must also add `len(str(injected.get("text", "")))` when `isinstance(block.get("injected"), dict)` so `STRANDS.md`, `.agent/MEMORY.md`, and `environment` blocks count toward `AUTO_COMPACT_PCT = 80`.
- **`model_switch.canonical_prefix_hash` (`strands_code_cli/model/model_switch.py:249-275`):** Currently strips `"reasoningContent"`, `"image"`, `"video"`, `TRACE_LABEL`, and `_MEDIA_PLACEHOLDER_RE`. Must skip `"injected" in block` so memory-file edits or turn re-injections never invalidate `RichHistory` stashes across `/model` switches.
- **`btw.fork_btw_history` (`strands_code_cli/loop/btw.py:199-208`):** Side agents already register `load_memory` directly (`build_btw_agent` `L452`), so parent `"injected"` blocks should be stripped alongside `"reasoningContent"` when copying parent messages to avoid duplicating `<ctx>` memory blocks or leaving empty messages.
- **`CodeAgentCallbackHandler.__call__` (`strands_code_agent/callback_handler.py:88-137`):** Only inspects `'text'`, `'toolUse'`, and `'toolResult'`, so `"injected"` blocks are naturally non-echoed without touching `strands_code_agent/`.

### 2.2 Boundary Steering & `todos` Plugin Removal (`D-06`)
- Keep `BeforeToolCallEvent.cancel_tool` in `strands_code_cli/loop/steering.py` (`Agent.cancel()` terminates the entire `agent()` run, whereas boundary steering cancels one tool call with `STEERING_REDIRECT_TEMPLATE` so the same turn continues). Keep `cancel_signal=cancel_event` in `_invoke_agent`.
- `harness-py v0.4.0` drops `"todos"` (`todo_write`) from `BUILTIN_PLUGIN_NAMES`. Grep confirms zero references to `todos`/`todo_write`/`Todos` anywhere in `strands_code_cli/`, `strands_code_agent/`, `tests/`, or `scripts/`. Removing `"todos"` eliminates an unallowlisted tool that previously triggered surprise HITL approval prompts (`KNOWN_TOOLS` never listed `todo_write`).

---

## 3. Route-Aware SDK `Model.model_info` Context Windows (`D-02`)

- **Upstream mechanism (`strands-py >=1.63`, `#5627`):** `strands` bundles shared model metadata (`strands/models/model_info.json` and helpers such as `strands/models/_model_info.py`) backing `Model.model_info` (`ModelLimits.context_window`).
  - **Key implementation constraint:** Reading the bundled `strands` model-info registry by normalized model ID inside `_sdk_window(model_id)` avoids instantiating `BedrockModel`/`AnthropicModel` (which could construct `boto3` clients or require optional SDKs/credentials) while still inspecting the live `agent.model.model_info` when an instance is supplied or looking up the exact same bundled table! Wave 2 Task 1 will inspect the installed `.venv` `strands/models/_model_info.py` after Wave 1 upgrades `strands-agents >=1.65.0` to use its public lookup/attribute names directly (with normalized ID fallback variants for `provider/name` vs bare IDs).
- **Locked `D-02` Precedence in `window_for(model_id)` (`cost_context.py:122-129`):**
  1. **If `live_pricing.is_openrouter_id(model_id)`:** check `openrouter_entry(model_id)` (`"window"`) first (unless `live_disabled()`), honoring OpenRouter's per-endpoint context caps, then SDK `model_info`, then `litellm_entry`, then static `MODEL_LIMITS`.
  2. **For all direct providers:** check SDK `model_info` (`_sdk_window(model_id)`) **first** (100% offline/deterministic, independent of `STRANDS_CODE_NO_LIVE_PRICING` or keep fail-soft behavior consistent — note check `test_kill_switch_restores_static_only` in `tests/cost/test_live_pricing.py:483`), then OpenRouter live (if applicable), `litellm_entry` (`_live_window`), and static `MODEL_LIMITS`.
- **Test impact check:** In `tests/cost/test_live_pricing.py:463-482` (`test_gpt_on_bedrock_falls_to_mantle_litellm`), `window_for("openai.gpt-5.4")` asserts `1050000` (populated from `_fake_litellm`!). And `test_window_lookup_known_and_unknown` in `tests/cost/test_cost_context.py:226-229` checks `bedrock/global.anthropic.claude-sonnet-4-6 == 1_000_000`, `bedrock/anthropic.claude-3-haiku-20240307 == 200_000`, `mystery/acme-1 is None`. Ensure LiteLLM-fallback window tests mock/bypass `_sdk_window` (or test IDs not in bundled `model_info`) when specifically testing the LiteLLM tier, and verify Anthropic 4.6 Sonnet 1M vs 200K / Haiku 200K against the upgraded `model_info.json`!

---

## 4. Bedrock `_NO_STREAMING_TOOLS` Unary Mode (`D-03`)

- **Confirmed SDK config API (`BedrockModel.BedrockConfig`):** Accepts `'streaming': bool | None` via constructor or `model.update_config(streaming=False)`.
- **All 4 resolution/creation sites across the CLI:**
  1. `strands_code_cli/model/model_switch.py:apply_switch` (`L690-696`) — handles `/model` switches and `/route` main-turn switches.
  2. `strands_code_cli/entry/main.py:build_agent` (`L172-196`) — initial agent launch (`model` resolved by `create_harness(**kwargs)` onto `agent.model`).
  3. `strands_code_cli/loop/core.py:_route_side_spawn` (`L504-508`) — `/btw` side-agent model resolution before `build_btw_agent`.
  4. `strands_code_cli/loop/btw.py:build_btw_agent` (`L451-452`) — when `build_btw_agent` constructs via `create_harness(**kwargs)` cleanly, inspect `agent.model` (or `kwargs["model"]`) and apply `configure_streaming_for_model` if not already configured.
- **Shared helper (`model_switch.configure_streaming_for_model(model_id, resolved)`):**
  - If `not supports_streaming_tools(model_id)` and `getattr(resolved, "update_config", None)` is callable (or `config` indicates Bedrock): check provider (`_provider_of(normalize_model_ref(model_id)) == "bedrock"`) and call `resolved.update_config(streaming=False)` (fail-soft if mock/stub lacks `update_config` or raises).
- **UX messages (`D-03`):**
  - Constant `UNARY_TOOL_MODE_NOTE = "Note: streaming disabled for {model_id} (Bedrock unary tool mode)."` (or helper `unary_mode_note(model_id)`).
  - Used in `model_switch.apply_model_action` (`loop/core.py:1126-1135`) on `/model` switch and `_warn_if_no_streaming_tools` (`loop/core.py:2253-2261`) on launch.
  - **Wait — `apply_model_action` is shared by `/model` (`L2589`) AND `_route_pre_turn` (`L1292`+)!** Let's check whether `/route` suppresses `apply_model_action`'s reply (`quiet` or completely)! Let's check `_route_pre_turn` in `loop/core.py` in Wave 1/2 — removing `L1362-1368` already removes the `/route` warning, and if `_route_pre_turn` discards `reply`, then `/route` is already silent; adding an optional `quiet: bool = False` or letting `_route_pre_turn` stay silent guarantees zero unary note on `/route` (`D-03`)!
  - Existing tests pinning the old `"rejects tool use in streaming"` phrasing in `tests/model/test_model_switch.py:1198, 2078, 2090` must be updated cleanly to assert both `streaming=False` configuration and the new `"streaming disabled for ... (Bedrock unary tool mode)"` note!

---

## 5. Hybrid Session Restore & `#5166` Cross-Family Reasoning Strip (`D-04`)

- **Where resume runs:** `dispatch/core.py:2057` (`/resume`) only displays the UUID hint; actual history restoration happens when launching with `--session-id` or selecting a session from the startup picker -> `build_agent` (`main.py:244`) loads persisted snapshot messages into `agent.messages` -> `run_loop` (`loop/core.py:2504-2514`).
- **Locked `D-04` rule:** After `rich = RichHistory.load(stash_path)` (`loop/core.py:2513`), call helper `prepare_resumed_history(agent, current_model, rich)` (defined in `model_switch.py` to keep `run_loop` under `xenon C <= 20`!):
  - If `not getattr(agent, "messages", None)`: return (fresh session, no-op).
  - Normalize `target_id = normalize_model_ref(current_model)`.
  - Compute `is_bedrock = _provider_of(target_id) == "bedrock"` and `media_ok = supports_media(target_id)`.
  - If `is_bedrock and media_ok`: **leave `agent.messages` untouched** — upstream `#5166` (`BedrockModel._rejects_reasoning_block`) and `v1.62.0` (`drop_block` retry) strip incompatible `reasoningContent` at wire formatting while keeping full history on disk if the user switches back later!
  - Otherwise (`not is_bedrock or not media_ok`):
    - If `_has_thinking(agent.messages)` and `rich is not None` and `rich.messages is None`: stash original `copy.deepcopy(agent.messages)` into `rich` (`model_id=target_id`, `length=len(...)`, `prefix_hash=canonical_prefix_hash(...)`, and persist if needed via existing save path or when next saved) using source attribution (note: if snapshot doesn't store original vendor, fallback `old_id = "resumed"` ensures `same_vendor("resumed", target_id)` is False so incompatible `reasoningContent` converts to readable `[Thinking trace]` text while same-vendor or non-Bedrock media-less strips media safely!).Wait: what if the user resumes an Anthropic Bedrock session onto a media-less *Bedrock* model (e.g., `meta.llama4` / `nova-lite`) vs a *non-Bedrock* Anthropic-direct (`anthropic/claude-opus-4-6`)?
      - Using `old_id = current_model`? Wait: if a user ran Opus on `bedrock/`, stopped, and resumed with `current_model = "meta.llama4"`, `_vendor_of("meta.llama4")` is `"meta"` -> `supports_reasoning("meta.llama4")` is `False`, so even with `old_id = current_model`, `reasoning_ok = False` strips `reasoningContent` AND `media_ok = False` strips images!
      - What if the user ran Opus on `bedrock/` (with Bedrock Opus reasoning trace) and resumed directly onto `anthropic/claude-opus-4-6` (direct Anthropic API, NOT Bedrock), or ran DeepSeek/Nova 2 reasoning on Bedrock and resumed onto `openai/gpt-4o`? With `old_id = "bedrock-resumed"` (or `"resumed"`), `same_vendor` is `False` so cross-provider foreign signatures NEVER pass raw to `anthropic/` or `openai/`! And `RichHistory` (when already saved from a `/model` switch, or if stashed cleanly) already records `rich.model_id`! Even better: check if `_provider_of(target_id) != "bedrock"`: passing `old_id = "__resumed__"` forces foreign `reasoningContent` into `[Thinking trace]` text safely across providers (while media-less `supports_media(target_id)` converts image/video blocks). Let's keep `prepare_resumed_history` simple, crisp, and thoroughly unit-tested!
