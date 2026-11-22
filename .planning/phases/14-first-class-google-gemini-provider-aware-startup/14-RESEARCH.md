# Phase 14: First-Class Google Gemini & Provider-Aware Startup — Research

**Researched:** 2026-11-21
**Phase:** `14-first-class-google-gemini-provider-aware-startup`
**Requirement:** `MODEL-06`
**Sources Verified Live in `.venv`:** `strands-agents==1.65.0`, `strands-harness==0.4.0`, `litellm`, and the Phase 13 codebase (`fa27d06` / `bafa867`).

---

## 1. Upstream SDK & Harness Inspection (`strands-agents==1.65.0`, `strands-harness==0.4.0`)

### 1.1 Packaging & Extra Bounds
- Installed `strands-agents==1.65.0` declares extra `gemini`:
  `google-genai<3.0.0,>=1.68.0; extra == 'gemini'`.
- Adding `gemini = ["strands-agents[gemini]"]` to `[project.optional-dependencies]` in `pyproject.toml` pulls `google-genai` lazily only for users syncing `--extra gemini` (default installs and CI remain offline/lightweight with zero new base runtime deps).
- Currently `_SDK_EXTRA_HINTS` in `strands_code_cli/dispatch/core.py:77` is `{"litellm": "litellm", "bedrock": "agentcore"}` — adding `"google": "gemini"` lets `/model google/...` emit `pip install strands-code-agent[gemini]` on `ImportError`.

### 1.2 `GeminiModel` & `google-genai` Auth (`strands/models/gemini.py`)
- `GeminiModel` (`strands/models/gemini.py:174-191`) constructs `genai.Client(**self.client_args)`.
- `google-genai` supports:
  1. **Google AI Studio (API Key / Google AI Pro & Ultra Developer Program credits):** `GOOGLE_API_KEY` or `GEMINI_API_KEY` (`GOOGLE_API_KEY` wins if both are set).
  2. **Vertex AI (ADC / Service Account):** `GOOGLE_GENAI_USE_VERTEXAI=true` (truthy `1`/`true`) + `GOOGLE_CLOUD_PROJECT` (+ optional `GOOGLE_CLOUD_LOCATION`, where Gemini 2.5/3 models often use `global`).
- **Mutual exclusion trap:** `google.genai.Client()` raises `ValueError` at initialization if both Vertex flags (`GOOGLE_GENAI_USE_VERTEXAI` / project / location) AND `GOOGLE_API_KEY` / `GEMINI_API_KEY` are configured simultaneously. Catching this upfront in `first_run.py` turns a cryptic client traceback into an immediate, actionable CLI exit message (`D-03`).

### 1.3 Cross-Provider `toolUse["reasoningSignature"]` Serialization (`gemini.py` & `litellm.py`)
- `GeminiModel._format_request_content_part` (`strands/models/gemini.py:252-265`) reads and emits `content["toolUse"]["reasoningSignature"]` (base64 thought signature attached directly to `toolUse` blocks).
- `LiteLLMModel.format_request_message_tool_call` (`strands/models/litellm.py:145-150`) appends `__thought__<reasoningSignature>` to `tool_calls[].id`:
  ```python
  reasoning_signature = tool_use.get("reasoningSignature")
  if reasoning_signature and _THOUGHT_SIGNATURE_SEPARATOR not in tool_call["id"]:
      tool_call["id"] = f"{tool_call['id']}{_THOUGHT_SIGNATURE_SEPARATOR}{reasoning_signature}"
  ```
- When switching away from `google/gemini-*` to Anthropic-via-LiteLLM, OpenRouter, or OpenAI, keeping `"reasoningSignature"` on copied `toolUse` blocks bloats/breaks downstream tool IDs (`^[a-zA-Z0-9_-]{1,64}$`) and mismatches `toolResult.toolUseId`.
- `convert_history()` (`model_switch.py:347-396`) currently deep-copies `"toolUse"` blocks verbatim. Stripping `"reasoningSignature"` on copied `"toolUse"` blocks when `not (supports_reasoning(new_id) and same_vendor(old_id, new_id))` (while keeping `RichHistory` stashes unmodified and ignoring `"reasoningSignature"` inside `canonical_prefix_hash()`) prevents cross-provider tool corruption while preserving lossless switch-back to Gemini (`D-04`).

### 1.4 `strands_harness.models` Thinking Levels & Gemini 2.5 Compatibility
- `strands_harness.models.supports_thinking("google/gemini-2.5-pro")` returns `True` because `_PROVIDERS["google"]` configures `thinking_levels=('low', 'medium', 'high')` (`recommended_thinking='high'`, `web_search=True`, `caching=True`).
- However, `_gemini(model_id, effort, web_search, caching)` (`strands_harness/models.py:284-295`) builds:
  ```python
  if effort is not None:
      extra["params"] = {"thinking_config": {"thinking_level": effort}}
  ```
  - `thinking_level` (`"minimal"`/`"low"`/`"medium"`/`"high"`) is the **Gemini 3+** API field!
  - **Gemini 2.5** (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`) uses integer `thinking_budget` (e.g., `-1` dynamic, `0` off, `1024..24576`), and Gemini 2.5 endpoints reject unknown/unsupported `thinking_level` fields with `400 INVALID_ARGUMENT`.
- `_WEB_FETCH_MODELS["google"]` is `"gemini-3.5-flash"`, which is separate from the main session model unless verified live; if a user is only keyed for GA `gemini-2.5-*`, the main agent should still run cleanly when configured through `build_agent`, `apply_switch`, `_route_side_spawn`, and `build_btw_agent`.
- Adding a fail-soft `configure_gemini_for_model(model_id, resolved)` normalizer in `model_switch.py` (translating `params["thinking_config"]` on `gemini-2.5*` from `thinking_level` into safe `thinking_budget` or stripping `thinking_level`, plus drafting a concise upstream issue `docs/upstream/harness_issue_gemini25_thinking.md`) protects every `google/gemini-2.5-*` turn out of the box (`D-07`).

### 1.5 Offline Windows (`_model_info`) & LiteLLM Pricing (`litellm.model_cost`)
- `strands.models._model_info.get_context_window_limit()` returns `1048576` (1M tokens) offline for:
  `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3-pro-preview`, `gemini-3.5-flash`.
- Bundled `litellm.model_cost` indexes **65** Gemini 2.5 / 3.x models under bare `<tail>` or `gemini/<tail>` (e.g. `gemini-2.5-pro` `1.25e-6`/`1e-5` `$1.25/$10.00`, `gemini-2.5-flash` `3e-7`/`2.5e-6` `$0.30/$2.50`, `gemini-2.5-flash-lite` `1e-7`/`4e-7` `$0.10/$0.40`, `gemini-3-flash-preview` `5e-7`/`3e-6` `$0.50/$3.00`, all `1048576` window).
- Currently `live_pricing.litellm_entry()` (`L496-497`) only searches `[model_id, f"bedrock/{model_id}", f"bedrock_mantle/{tail}"]` (plus `_openrouter_id`), missing `"gemini/<tail>"` and bare `"<tail>"`.
- Also `_live_price()` in `cost_context.py:89-93` calls `bedrock_live_price()` even for `google/...` or `anthropic/...` models, needlessly probing AWS Pricing when non-Bedrock direct providers are active.

---

## 2. Existing Code Seams, Complexity Budget & Test Contracts

### 2.1 Existing Tests & Hard Contracts to Honor
1. **`tests/cost/test_cost_context.py:950-972` (`test_no_credential_persistence_sinks`):**
   - Strictly asserts `"os.getenv" not in text and "os.environ" not in text` across `model/model_switch`, `cost/cost_context`, `dispatch/core`, `loop/core`, `loop/pump`, and `entry/main`.
   - **Design consequence:** All env-presence inspection (`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `STRANDS_BOX`, `AWS_*`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `LITELLM_API_KEY`) MUST reside exclusively inside `strands_code_cli/entry/first_run.py`. Other modules (`entry/main.py`, `model/model_switch.py`) call boolean/model-id helpers on `first_run.py`.
2. **`tests/entry/test_first_run.py:55-64` (`test_never_reads_credentials_directly`):**
   - Currently asserts `"os.environ" not in source` on `first_run.py` itself from the Phase 1 Bedrock-STS-only design.
   - Update in `14-01` to test the true security invariant: `first_run.py` inspects only non-empty truthiness (`bool`), never validates vendor key prefixes (accepting `strands_box_...` phantoms), and never embeds, returns, prints, or logs canary secret strings passed in env.
3. **`tests/entry/test_session_resume.py:165, 190` & `tests/entry/test_first_run.py:77, 87, 101`:**
   - These tests mock `main_module._preflight_credentials` with `return_value=None` or `side_effect=typer.Exit(code=2)`.
   - Keeping `_preflight_credentials(model: str | None = None, base_url: str | None = None) -> str | None` in `entry/main.py` preserves 100% compatibility with every existing mock!
4. **`tests/model/test_model_switch.py:1628-1635` (`test_dotless_id_groups_under_itself`):**
   - Expects `build_model_tree(["bedrock/x"])` to produce vendor `"x"`, family `"x"`, base `"x"`.
   - When fixing `_vendor_family()` for `"google/gemini-2.5-pro"` → `("google", "gemini")`, ensure `_vendor_family(base)` only avoids splitting on decimal version dots (`\d\.\d` or checking `/` / known vendor cues), without breaking bare dotless `"bedrock/x"`. Let `build_model_tree()` pass vendor/base context or preserve `"google"` as vendor when the input carries `"google/"` (so `"google/custom-dotless"` stays under `"google"`, while `"bedrock/x"` stays `"x"`!).

### 2.2 Cyclomatic Complexity (`xenon --max-absolute C`, `CC <= 20`)
Measured `radon cc` baseline on target functions:
- `model_switch.discover_models`: **`C (17)`** — MUST extract `_discover_bedrock_models()` and `_discover_google_models()` so `discover_models()` drops below `C (10)`.
- `model_switch.convert_history`: **`C (13)`** — extract `_convert_tool_use_block(block, reasoning_ok)` (keeps CC low).
- `model_switch.canonical_prefix_hash`: **`C (11)`** — extract `_canonical_block(block)` so stripping `toolUse["reasoningSignature"]` stays trivial (`<= 10`).
- `cost_context.cost_report` & `price_table`: **`C (20)`** — at ceiling; do NOT edit either function in Phase 14.
- `entry/main._root`: **`B (7)`** — plenty of headroom, keep `--model` and preflight delegation flat and clean.
- `dispatch/core._setup_decision_entries`: **`C (20)`** — unrelated; do not touch.

### 2.3 Import-Linter Contract
- `pyproject.toml:96-101` forbids feature modules from importing `strands_code_cli.entry.main` (except top-level package re-export). Importing `strands_code_cli.entry.first_run` from `model_switch.py` or `tests` respects this contract cleanly.
