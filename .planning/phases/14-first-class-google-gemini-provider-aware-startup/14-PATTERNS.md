# Phase 14 Codebase Patterns & Extension Seams

**Created:** 2026-11-21
**Purpose:** Concrete patterns, line-level conventions, and invariants to preserve across Plans `14-01`, `14-02`, and `14-03`.

---

## 1. Entry Preflight & Config Order (`strands_code_cli/entry/`)

- **Fail-fast CLI exit (`first_run.py:42-50`):** Catch `Exception`, log only `type(exc).__name__` (never secret values or env dumps), print actionable pointer via `typer.secho(..., err=True, fg=typer.colors.RED)`, and `raise typer.Exit(code=2)`.
- **Secret-free boundary (`test_no_credential_persistence_sinks`):**
  - Keep ALL `os.environ.get(...)` calls confined to `strands_code_cli/entry/first_run.py`.
  - Inspect presence via `bool((source.get(key) or "").strip())` only — never log, return, format, or inspect key prefixes (`AIza`, `sk-`, `strands_box_`).
  - Support injectable `env: Mapping[str, str] | None = None` on helpers in `first_run.py` so unit tests stay 100% deterministic without mutating global env unless using `monkeypatch.setenv`.
- **Box compatibility (`STRANDS_BOX == "1"`):**
  - When `STRANDS_BOX == "1"`, verify AWS credential presence locally (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`, `AWS_BEARER_TOKEN_BEDROCK`, or `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` / `AWS_WEB_IDENTITY_TOKEN_FILE` / non-empty `boto3.Session().get_credentials()`) without network calls to `sts.get_caller_identity()`.
- **CLI option expansion (`entry/main.py:219-256`):**
  - Add `--model` as a Typer `str | None` option on `_root()`.
  - Load `config = ProviderConfig.load()` BEFORE `_preflight_credentials(model=requested_model, base_url=config.base_url)`, passing `requested_model or config.model`.
  - Keep `--model` session-scoped: pass `effective_model = requested_model or config.model or detected_model` into `model_for_config(effective_model, config.base_url)` WITHOUT writing `--model` back to `config.yaml` (preserving explicit `/model` persistence semantics).

---

## 2. `ModelSwitch` History, Discovery & Normalizers (`strands_code_cli/model/model_switch.py`)

- **Complexity discipline:** Keep `discover_models`, `convert_history`, and `canonical_prefix_hash` modular via focused private helpers (`_discover_bedrock_models`, `_discover_google_models`, `_convert_tool_use_block`, `_canonical_block`, `_strip_decimal_dots` / `_split_vendor_family`).
- **`reasoningSignature` round-trip symmetry:**
  - `supports_reasoning()` allows `("bedrock", "anthropic", "google")` to delegate to `_harness_supports_thinking`.
  - Cross-vendor switch (`not (supports_reasoning(new_id) and same_vendor(old_id, new_id))`) copies `toolUse` without `"reasoningSignature"` (via helper dict copy omitting `"reasoningSignature"`). Same-vendor switch (e.g. `google/gemini-2.5-pro` -> `google/gemini-2.5-flash`) keeps `"reasoningSignature"` intact.
  - `canonical_prefix_hash()` normalizes `"toolUse"` blocks without `"reasoningSignature"` so `RichHistory` stashes match regardless of stripped tool signatures and can restore `"reasoningSignature"` when switching back to `google/`.
- **`_vendor_family(base)` rule:**
  - Avoid splitting on dots inside version numbers (`gemini-2.5-pro` -> `re.split` only when dot is NOT between digits `\d\.\d` -> vendor `"google"`, family `"gemini"` when vendor is known or implied by `"gemini-"`). Preserve existing contracts: `"anthropic.claude-sonnet-4-6"` -> `("anthropic", "claude")`, `"openai.gpt-oss-120b-1:0"` -> `("openai", "gpt-oss")`, `"qwen/qwen3-32b"` -> `("qwen", "qwen3")`, and `"x"` (from `"bedrock/x"`) -> `("x", "x")`.
- **Gemini 2.5 thinking normalization (`configure_gemini_for_model`):**
  - Mirror `configure_streaming_for_model(model_id, resolved) -> resolved` signature and fail-soft `getattr`/`try...except` style.
  - Call right alongside `configure_streaming_for_model` in `apply_switch` (`model_switch.py:779`), `build_agent` (`entry/main.py:185`), `_route_side_spawn` (`loop/core.py:511`), and `build_btw_agent` (`loop/btw.py:463`).
  - Only act when normalized provider is `"google"` and model name starts with `"gemini-2.5"` (case-insensitive); normalize `config["params"]["thinking_config"]` by dropping `"thinking_level"` and setting `"thinking_budget": -1` (when `"thinking_level"` was `"low"`/`"medium"`/`"high"`) or `"thinking_budget": 0` (if ever `"off"`/`"none"`), then calling `resolved.update_config(params=updated_params)` fail-soft.

---

## 3. Cost & Pricing Lookup (`strands_code_cli/cost/`)

- **`live_pricing.litellm_entry(model_id)`:**
  - When `_openrouter_id(model_id)` is `None` and `model_id.lower().startswith("google/")`, check `[f"gemini/{tail}", tail, model_id]` before Bedrock prefixes so a `google/` model always resolves Gemini entries cleanly.
  - For any non-OpenRouter ID, include `f"gemini/{tail}"` and `tail` candidates as well (without breaking Bedrock / `bedrock_mantle/` precedence).
- **`cost_context._live_price(model_id, region)`:**
  - Only call `live_pricing.bedrock_live_price(...)` when `model_id` is Bedrock (`"/" not in model_id` or `model_id.startswith(("arn:", "bedrock/"))`), skipping AWS Pricing API overhead/errors cleanly for `google/`, `anthropic/`, `openai/`, and `ollama/`.
- **Curated fallbacks (`MODEL_PRICING`, `MODEL_LIMITS`):**
  - Specific keys before general prefixes (`"gemini-2.5-flash-lite"` BEFORE `"gemini-2.5-flash"` so substring matching `_best_hit` hits `-lite` first!). Same rule for `"gemini-3.1-flash-lite"` before `"gemini-3.1-flash"`.

---

## 4. UAT Rig & Hermetic Testing (`scripts/uattest/`, `tests/`)

- **Sibling-module pattern:** Follow `scripts/uattest/scenarios_upstream.py` (`sys.path.insert(0, ...)` + `uattest_lib` `# noqa: E402` reason-citing comment, `ensure_workdir`, isolated `XDG_CONFIG_HOME=/tmp/uatr8/g1/.xdg`, `USAGE_END_RE`).
- **Rig contract tests:** Mirror `tests/rig/test_uattest_upstream.py` in `tests/rig/test_uattest_gemini.py` via `importlib.util` (never running tmux in pytest).
- **CI gates after every wave:** `pytest tests/...`, `ruff check strands_code_cli tests scripts`, `ruff format --check strands_code_cli tests scripts`, `xenon --max-absolute C strands_code_cli tests scripts`, `lint-imports`, `git diff strands_code_agent/` empty.
