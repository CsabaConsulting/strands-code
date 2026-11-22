# Phase 14: First-Class Google Gemini & Provider-Aware Startup - Context

**Gathered:** 2026-11-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `google/` Gemini models first-class across startup, `/model`, reasoning/effort routing, and `/cost` without requiring AWS credentials or violating `Strands Box` phantom/egress assumptions (`MODEL-06`):
- Optional `gemini` extra (`strands-agents[gemini]`) and `_SDK_EXTRA_HINTS["google"] = "gemini"`.
- Box-compatible, provider-aware startup preflight (`first_run.py` + `entry/main.py`) replacing the unconditional `Bedrock-or-stop` STS gate, plus `--model` CLI flag and ambient env model auto-pick.
- Mutually exclusive Google auth fail-fast (`GOOGLE_GENAI_USE_VERTEXAI` vs. `GOOGLE_API_KEY` / `GEMINI_API_KEY`) and Vertex project check.
- `GeminiModel` cross-provider safety: `supports_reasoning("google/...")` delegation to `_harness_supports_thinking`, stripping `toolUse["reasoningSignature"]` on cross-vendor `convert_history()` (keeping it in `RichHistory` stashes and ignoring it in `canonical_prefix_hash()`), and fixing `_vendor_family()` decimal dot splitting on `gemini-2.5-pro`.
- Credential-gated `/model` Gemini discovery (`genai.Client().models.list()` filtered to `generateContent` `gemini-*`) with static fallback when Google-keyed, merged with Bedrock when AWS-keyed.
- Gemini `/cost` pricing & windows via `live_pricing.litellm_entry()` (`gemini/<tail>`, `<tail>`) + curated static fallback in `cost_context.py`.
- Fail-soft Gemini 2.5 vs. Gemini 3 `thinking_config` compatibility guard (with upstream issue draft if reproduced), repeatable `driver.py g1` UAT scenario, and `docs/QUICKSTART.md` Google AI Studio + Google AI Ultra (\$40–\$100/mo Developer Program credit) setup docs.

Out of scope: consumer OAuth piggybacking on Gemini CLI / Code Assist (`cloudcode-pa.googleapis.com` — ToS violation), migrating routing engines onto `DecisionModel` (**Phase 15**), remote skills marketplaces (**Phase 16**), Strands Box `box.toml`/`policy.dw` generator (**Phase 17**), `/help`/`@file`/`/review` (**Phase 18**), and `strands-agents-evals` (**Phase 19**).

</domain>

<decisions>
## Implementation Decisions

### Packaging & Install Hints
- **D-01 (`gemini` optional extra & `_SDK_EXTRA_HINTS`):** Add `gemini = ["strands-agents[gemini]"]` to `[project.optional-dependencies]` in `pyproject.toml` (zero upper pins during experimental phase) and add `_SDK_EXTRA_HINTS["google"] = "gemini"` in `strands_code_cli/dispatch/core.py` so missing `google-genai` surfaces `pip install strands-code-agent[gemini]`. — *Reversibility: easy — additive extra and one-entry dict hint.*

### Provider-Aware Startup Preflight, Ambient Auto-Pick & `--model` Flag
- **D-02 (Unified v2 startup order, `--model` flag & env-presence preflight):**
  - Load `ProviderConfig.load()` before running `preflight_credentials(...)` in `strands_code_cli/entry/main.py` (still ahead of `SessionIndex` directory creation and `build_agent`).
  - Add `--model` CLI flag to `strands-code` as a session-scoped override (does not overwrite `config.yaml` unless `/model` is run).
  - Check **non-empty env presence only** (NEVER inspect vendor key prefixes like `AIza...` / `sk-...` so Phase 17 Strands Box `strands_box_<random>` phantom strings always pass). When `STRANDS_BOX == "1"` (or Box proxy env + synthetic AWS creds / `AWS_BEARER_TOKEN_BEDROCK`), verify local AWS credential presence without calling `sts.get_caller_identity()`.
  - When both `--model` and `config.model` are `None` and AWS credentials are absent, auto-pick a sensible opening model from ambient env: `GOOGLE_API_KEY` / `GEMINI_API_KEY` / Vertex (`GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT`) → `"google/gemini-2.5-flash"`; `ANTHROPIC_API_KEY` → `"anthropic/claude-sonnet-4-6"`; `OPENAI_API_KEY` → `"openai/gpt-5.4"`; `OPENROUTER_API_KEY` / `LITELLM_API_KEY` → actionable setup pointer telling the user to pass `--model litellm/openrouter/<vendor>/<model>` (or set `model:` in `config.yaml`).
  - **Test invariant guard:** Keep all `os.environ` presence checks strictly inside `strands_code_cli/entry/first_run.py` (`bool(os.environ.get(...).strip())` only — never log/store key values) so `tests/cost/test_cost_context.py::test_no_credential_persistence_sinks` stays green across `entry/main.py`, `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, and `loop/pump.py`.
  — *Reversibility: moderate — centralizes provider routing at entry; easy to adjust default model IDs.*

- **D-03 (Mutually exclusive Google auth fail-fast & Vertex validation):** Fail fast inside `first_run.py` with an actionable error message naming the conflicting env vars whenever both `GOOGLE_GENAI_USE_VERTEXAI` (truthy) and `GOOGLE_API_KEY` / `GEMINI_API_KEY` are set non-empty for a `google/` launch (`google-genai` raises `ValueError` at client creation when both are set). In Vertex mode (`GOOGLE_GENAI_USE_VERTEXAI` truthy), require non-empty `GOOGLE_CLOUD_PROJECT` and mention `GOOGLE_CLOUD_LOCATION=global` for Gemini 2.5/3 in the setup pointer. — *Reversibility: easy — isolated check inside `first_run.py`.*

### `GeminiModel` Cross-Provider Switching, Naming & Reasoning
- **D-04 (`reasoningSignature` stripping, `_vendor_family` fix & `supports_reasoning`):**
  - Add `"google"` alongside `"bedrock"` and `"anthropic"` in `supports_reasoning()` (`model_switch.py:165`) so `google/...` delegates to `_harness_supports_thinking`.
  - Strip `"reasoningSignature"` from copied `toolUse` dicts inside `convert_history()` whenever `not (supports_reasoning(new_id) and same_vendor(old_id, new_id))` (preventing `LiteLLMModel` `__thought__<sig>` corruption of `tool_calls[].id`), keep `toolUse["reasoningSignature"]` intact inside `RichHistory` stashes for same-vendor switch-back, and strip `"reasoningSignature"` on `toolUse` copies inside `canonical_prefix_hash()`.
  - Fix `_vendor_family()` (`model_switch.py:573`) so versioned hyphen-dot names like `gemini-2.5-pro` (`google/gemini-2.5-pro` → `_base_key` `"gemini-2.5-pro"`) are not split at decimal dots (`("gemini-2", "5")`), grouping under `("google", "gemini")` in `/model` trees and honoring `vendor: google` / `family: gemini` overrides in `model-capabilities.yaml`.
  — *Reversibility: easy — localized to `strands_code_cli/model/model_switch.py`.*

### `/model` Gemini Discovery & Merge Behavior
- **D-05 (Live `google-genai` discovery + credential-gated static fallback):**
  - Extend `discover_models()` in `model_switch.py` to support multi-provider discovery without breaking its return contract:
    - Keep Bedrock discovery when AWS credentials resolve (fail-soft offline).
    - When Google credentials exist (non-empty `GOOGLE_API_KEY` / `GEMINI_API_KEY` or configured Vertex), lazily import `google.genai`, call `Client().models.list()`, filter to `gemini-*` models supporting `generateContent`, and emit `google/<name>` IDs.
    - Merge live Bedrock and live Gemini lists when both providers are keyed.
    - When Google credentials exist and live discovery fails or `google-genai` is absent, include curated static Gemini fallback entries (`google/gemini-2.5-pro`, `google/gemini-2.5-flash`, `google/gemini-2.5-flash-lite`, `google/gemini-3-flash-preview`); omit static Gemini models when Google creds are absent so AWS-only pickers remain uncluttered.
  — *Reversibility: easy — discovery stays fail-soft and offline-testable via dependency injection / monkeypatching.*

### `/cost` Pricing & Context Windows
- **D-06 (`litellm_entry` Gemini keys, static fallbacks & direct-provider pricing skip):**
  - Extend `live_pricing.litellm_entry()` (`strands_code_cli/cost/live_pricing.py:497`) to check `f"gemini/{tail}"` and bare `tail` alongside `bedrock/` and `bedrock_mantle/` (matching LiteLLM's 65 bundled Gemini keys).
  - Add curated static Gemini rows (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.5-flash`) to `MODEL_PRICING` and `MODEL_LIMITS` in `cost_context.py` as offline/non-`litellm` fallbacks (keeping SDK `Model.model_info` first per Phase 13 `D-02`).
  - Skip Bedrock Price List (`bedrock_live_price`) lookups in `_live_price()` for non-Bedrock direct providers (`google/`, `anthropic/`, `openai/`) so Gemini sessions never touch AWS Pricing APIs.
  — *Reversibility: easy — purely display-only tables and key lookup order.*

### Gemini 2.5 vs. 3 Harness Compatibility & Verification Posture
- **D-07 (Thinking-config guard & repeatable `driver.py g1` UAT):**
  - During Phase 14 research/implementation, verify how `strands_harness.models._gemini()` handles `effort` / `thinking_config` on `gemini-2.5-*` (which expects integer `thinking_budget` vs. Gemini 3 `thinking_level`) and `_WEB_FETCH_MODELS["google"]` (`gemini-3.5-flash`). If `harness-py` breaks `gemini-2.5-*` turns under default effort or invalid sub-model IDs, add a fail-soft local workaround when resolving/switching to `google/gemini-2.5-*` and draft a targeted upstream issue in `docs/upstream/`.
  - Keep all CI unit/contract suites (`pytest tests/ -q`, `ruff`, `xenon`, `import-linter`) 100% hermetic (zero network / zero keys).
  - Add a repeatable `driver.py g1` scenario (`scripts/uattest/scenarios_gemini.py`, pinned in `tests/rig/test_uattest_gemini.py`) exercising `--model google/gemini-2.5-flash` zero-AWS launch, tool turn + `/context` + `/cost`, and cross-provider switch/resume under isolated `XDG_CONFIG_HOME`, runnable live whenever `GOOGLE_API_KEY` or `GEMINI_API_KEY` is present.
  — *Reversibility: easy — local guard and optional live rig script stay isolated.*

### Documentation
- **D-08 (`docs/QUICKSTART.md` AI Studio & Google AI Ultra guide):** Document `uv sync --extra gemini`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `--model`, non-AWS startup, Vertex AI ADC + mutual-exclusion warning, and how personal **Google AI Pro** (\$10/mo), **Google AI Ultra 5x** (\$40/mo), and **Google AI Ultra 20x** (\$100/mo) Developer Program credits work via `aistudio.google.com` API keys (with consumer OAuth explicitly noted as unsupported/ToS-disallowed).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `MODEL-06` and Out-of-Scope consumer OAuth boundary
- `.planning/ROADMAP.md` — Phase 14 goal & 3 success criteria
- `.planning/research/ARCHITECTURE.md` §3 — Coordinated `first_run.py` + `entry/main.py` flow & `GeminiModel` `reasoningSignature` seam
- `.planning/research/PITFALLS.md` §1–§3 — `reasoningSignature` cross-provider crash, `_vendor_family()` dot-split bug, `litellm_entry()` / mutual exclusion / Gemini 2.5 vs. 3 thinking pitfalls
- `.planning/research/STACK.md` §2 & `.planning/research/V2-ALIGNMENT.md` §3 — `google-genai`, `GeminiModel`, Developer Program credit billing details
- `pyproject.toml` — Optional extras (`agentcore`, `litellm`, add `gemini`) & CI gates
- `strands_code_cli/entry/first_run.py` — Current `BEDROCK_SETUP_POINTER` & `preflight_credentials`
- `strands_code_cli/entry/main.py` — `model_for_config`, `_preflight_credentials`, `_root` startup sequence (`L219-256`), `build_agent`
- `strands_code_cli/entry/provider_config.py` — Persisted `model` / `base_url` loader
- `strands_code_cli/model/model_switch.py` — `supports_reasoning` (`L162`), `canonical_prefix_hash` (`L274`), `convert_history` (`L357`), `discover_models` (`L456`), `_base_key` / `_vendor_family` (`L525-601`)
- `strands_code_cli/dispatch/core.py` — `_SDK_EXTRA_HINTS` (`L77`), `_handle_model` (`L660-685`), `BUILTIN_SLASH_HEADS`
- `strands_code_cli/cost/live_pricing.py` — `_openrouter_id`, `litellm_entry` (`L480-518`)
- `strands_code_cli/cost/cost_context.py` — `MODEL_PRICING`, `MODEL_LIMITS`, `_live_price`, `window_for`
- `tests/cost/test_cost_context.py` — `test_no_credential_persistence_sinks` (`L950-972`, asserts `os.getenv`/`os.environ` absent outside `first_run.py`)
- `docs/QUICKSTART.md` — Provider & first-run documentation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `model_for_config()` (`entry/main.py:90`) already switches behavior by provider prefix before handing off to `create_harness` / `strands_harness.models.resolve_model`.
- `ProviderConfig.load()` (`entry/provider_config.py:49`) is side-effect-free on missing files and rejects symlinks/unknown keys, making it safe to run before preflight (`D-02`).
- `supports_reasoning()` (`model_switch.py:162`) already calls `strands_harness.models.supports_thinking(query)` for `"bedrock"` and `"anthropic"`, needing only `"google"` in its allowlist.
- `window_for()` (`cost_context.py:194`) already consults `strands.models._model_info.get_context_window_limit`, which natively returns `1_048_576` for Gemini 2.5 and 3.x models.
- `scripts/uattest/scenarios_upstream.py` establishes the isolated `XDG_CONFIG_HOME` `/tmp/uatr8/` tmux rig pattern (`_fresh_upstream_workdir`, `_wait_turn_end`, `USAGE_END_RE`) ready to copy for `scenarios_gemini.py`.

### Constraints & Watchpoints
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:950-972`):** Strictly forbids `os.getenv` / `os.environ` inside `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `entry/main.py`! All env-presence checks MUST stay inside `strands_code_cli/entry/first_run.py` (or a dedicated helper called by `first_run.py`), returning provider/hint booleans or enums rather than key strings.
- **Strands Box phantom compatibility (`Phase 17` contract):** `first_run.py` MUST check non-empty string presence only — never validate key formats or prefixes — and MUST skip `sts.get_caller_identity()` under `STRANDS_BOX=1`.
- **Complexity ceiling (`xenon --max-absolute C`, `CC <= 20`):** Keep `entry/main.py:_root`, `dispatch/core.py:_handle_model`, `model_switch.py:discover_models`, and `model_switch.py:convert_history` well below `CC 20` via small single-purpose helpers.
- **`import-linter` contract & `D-24`:** Feature modules (`first_run.py`, `model_switch.py`, `dispatch/core.py`) must never import `entry/main.py`; `strands_code_agent/` stays untouched.

</code_context>

<specifics>
## Specific Ideas

- For `discover_models()`, accept an optional `vendor_provider` / multi-source check or inspect credential presence via a small seam from `first_run.py` (keeping `model_switch.py` free of direct `os.environ`/`os.getenv` calls!).
- For `_vendor_family(base)`: when `_vendor_of(entry)` is already `"google"` (or when splitting only before versioned `-` segments / avoiding splits on `digit.digit`), `"google/gemini-2.5-pro"` should return `("google", "gemini")` while preserving `"openai.gpt-oss-120b"` → `("openai", "gpt-oss")`, `"anthropic.claude-sonnet-4-6"` → `("anthropic", "claude")`, and `"litellm/openrouter/qwen/qwen3-32b"` → `("qwen", "qwen3")` behavior.
- Default auto-picked model when `GOOGLE_API_KEY` or `GEMINI_API_KEY` is present with no `--model` and no `config.model`: `google/gemini-2.5-flash`.

</specifics>

<deferred>
## Deferred Ideas

- Consumer OAuth login / Gemini CLI (`cloudcode-pa.googleapis.com`) token reuse — **Explicitly Out of Scope** (`REQUIREMENTS.md`, ToS violation).
- `DecisionModel` routing migration — **Phase 15 (`UPSTREAM-02`)**.
- Strands Box `box.toml` and Dogwood `policy.dw` generator (`x-goog-api-key` egress template) — **Phase 17 (`SANDBOX-01`)**.

</deferred>

*Phase: 14-first-class-google-gemini-provider-aware-startup*
*Context gathered: 2026-11-21*
