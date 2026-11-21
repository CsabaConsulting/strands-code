# Domain Pitfalls & Mitigations — Strands Code v2.0

**Researched:** 2026-11-21
**Milestone:** `v2.0` (Phases 13–19)

---

## Pitfall 1: `GeminiModel` `toolUse["reasoningSignature"]` Corrupts Cross-Provider Tool IDs (Phase 14)
- **What happens:** `strands/models/gemini.py:215-224, 419-422` attaches `reasoningSignature` (base64, often 500+ chars) directly onto `toolUse` blocks, not only `reasoningContent`. `convert_history()` (`model_switch.py:338`) copies `toolUse` verbatim. When switching from `google/...` to `litellm/openrouter/anthropic/...` (or OpenAI), `LiteLLMModel.format_request_message_tool_call` (`litellm.py:147-150`) appends `__thought__<reasoningSignature>` to `tool_calls[].id`, violating Anthropic's `^[a-zA-Z0-9_-]{1,64}$` constraint and breaking `toolResult.toolUseId` matching.
- **Prevention:** Strip `reasoningSignature` from copied `toolUse` blocks in `convert_history()` when `not (supports_reasoning(new_id) and same_vendor(old_id, new_id))`. Keep `RichHistory` stashes unmodified for switch-back, and ignore `toolUse["reasoningSignature"]` inside `canonical_prefix_hash()`.

## Pitfall 2: `_vendor_family()` Mangling Versioned Model Names like `gemini-2.5-pro` (Phase 14)
- **What happens:** In `strands_code_cli/model/model_switch.py:575`, `_base_key("google/gemini-2.5-pro")` produces `"gemini-2.5-pro"`, and `base.partition(".")` returns `("gemini-2", "5")` instead of `("google", "gemini")`.
- **Impact:** Splits Gemini models into nonsense cascades in `/model` tree navigation and breaks `family: gemini` overrides in `model-capabilities.yaml`.
- **Prevention:** Preserve the provider/vendor when known or stop treating decimal version dots (`\d\.\d`) as vendor delimiters in `_vendor_family()`.

## Pitfall 3: Gemini `litellm_entry()` Lookup Miss, Mutual-Exclusion Init & Thinking Config (Phase 14)
- **What happens:**
  1. `live_pricing.litellm_entry()` (`L496-497`) only checks `[model_id, bedrock/..., bedrock_mantle/...]`, whereas `litellm.model_cost` indexes Google AI Studio models as `gemini/<tail>` or bare `<tail>`.
  2. In `google-genai`, setting **both** `GOOGLE_GENAI_USE_VERTEXAI=true` (`GOOGLE_CLOUD_PROJECT`) and `GOOGLE_API_KEY` / `GEMINI_API_KEY` raises `ValueError` (project/location and API key are mutually exclusive).
  3. `strands_harness/models.py` sends `thinking_config={"thinking_level": effort}` (Gemini 3+) and defaults `_WEB_FETCH_MODELS["google"] = "gemini-3.5-flash"`. Older `gemini-2.5-*` models use integer `thinking_budget`, and unverified preview IDs in `_WEB_FETCH_MODELS` could 404 on `web_fetch` / memory extraction.
- **Prevention:** Add `f"gemini/{tail}"` and `tail` lookup candidates + curated Gemini table fallback in `cost_context.py`; document/warn on mutually exclusive env vars; smoke-test `google/gemini-2.5-*` and `gemini-3-*` against `_harness._gemini` + `web_fetch` and open a minimal upstream PR to `harness-sdk` if needed.

## Pitfall 4: `strands.decisions` Edge Cases vs. v1 Calibrated Routing (`0.62` / `0.04`) (Phase 15)
- **What happens:**
  1. `Uncertain` (`strands.decisions.types`) is **truthy** (`bool(Uncertain()) is True`), so `if result.answers["pick"]:` silently accepts an `Uncertain` object as a decision.
  2. `DecisionsAPIDecisionModel` defaults `default_min_confidence=0.5` on the vendor `confidence` field, whereas `strands-code` gates on **raw top-1 probability `>= 0.62`** and `top - second <= 0.04`.
  3. `_system_one_http_adapter.py` caps request bodies at **32 KiB** (smaller than our `64 KiB` `_fit_decision_payload`), `DecisionResult.usage` drops inline USD `cost` (needed for `/cost` OpenRouter actuals), and changing per-choice `criteria` formatting alters prompt token distribution around the `0.62` / `0.04` boundary.
- **Prevention:** Always check `isinstance(val, Uncertain)`, pass `uncertainty=False`, read `result.metadata.probabilities` directly, keep `64 KiB` body fitting + USD `cost` capture inside `OpenRouterDecisionModel(DecisionModel)`, keep `TypeSafeDecisionModel` + `OllamaDecisionModel(DecisionModel)`, and re-run `scripts/evals` / probe calibration if prompt serialization changes.

## Pitfall 5: `ContextInjector` `InjectedBlock` Accounting in `harness-py v0.4.0` (Phase 13)
- **What happens:** `harness-py v0.4.0` writes `ContextInjector` payloads (`STRANDS.md`, `.agent/MEMORY.md`, `environment`) into `agent.messages` as `{"injected": {"text": ...}}`.
- **Impact:** `estimate_messages_tokens()` (`cost_context.py:445-465`) ignores `"injected"` blocks (under-counting context before 80% auto-compact), and `canonical_prefix_hash()` (`model_switch.py:249-275`) can mismatch across memory-file reloads or stashes. Also verify stub `_middleware_registry` compatibility in `tests/memory/test_memory_file.py:167`.
- **Prevention:** Handle `"injected"` explicitly in `estimate_messages_tokens` and `canonical_prefix_hash` during Phase 13 resync.

## Pitfall 6: Supply-Chain, Symlink Exfiltration & Prompt Injection in `SKILL-03` (Phase 16)
- **What happens:**
  1. Remote skills bundle `references/*` and `scripts/*`. A symlink (`references/leak.md -> ~/.aws/credentials`) could be read silently by pre-allowed `read` (`BUILTIN_ALLOWED_TOOLS = {"read", "search"}` in `policy/core.py:93`).
  2. `agentskills.io` `allowed-tools` frontmatter declares pre-approved tools; honoring it would let an untrusted repo skill grant itself `shell` or `write`.
  3. An injected turn could overwrite `./.agent/skills*` or `marketplaces.yaml` via `write`/`edit` if broad repo `[[allow]]` globs (`path = "*"`) apply.
- **Prevention:** Reject all tar/git symlinks, hardlinks, submodules, and `..` paths (`strict=True` + file-count/byte caps); copy plain files only; never treat `allowed-tools` as permission; warn on `scripts/*` at install/update; pin immutable 40-char `commit_sha` + SHA-256 `computed_hash` in `skills-lock.json`; block agent `write`/`edit` auto-approval on `.agent/skills*` and `~/.config/strands-code/**`; print remote metadata exclusively via `print_plain` (`markup=False`); label third-party skill provenance in slash prompts.

## Pitfall 7: Strands Box Linux Traps (`SANDBOX-01` — Phase 17)
- **Actual pitfalls discovered:**
  1. **No `bwrap` / Ubuntu 24.04 AppArmor `EPERM`:** Box uses `strands-box-contain-trampoline` with `CLONE_NEWUSER`, not `bwrap`. Ubuntu 24.04 `apparmor_restrict_unprivileged_userns=1` blocks launch unless `/etc/apparmor.d/strands-box` covers `box` + `strands-box-contain-trampoline` (or sysctl is disabled in dev). Linux `x86_64` also refuses to run without `EXPERIMENTAL_X86_SUPPORT=TRUE`.
  2. **Egress header & phantom traps:** Gemini expects `header = "x-goog-api-key"` and Anthropic `header = "x-api-key"` (default `Bearer` causes 401/403). OpenRouter `inject = "phantom"` on blanket `openrouter.ai` breaks unauthenticated `openrouter.ai/api/v1/models` fetches in `live_pricing.py` — scope OpenRouter destinations to `/api/v1/chat/*` + `/api/alpha/decisions` or set `inject = "always"`.
  3. **`first_run.py` + STS block + phantom strings:** Never check API key vendor prefixes, and skip `sts.get_caller_identity()` when `STRANDS_BOX=1`.
  4. **Self-tamper & `uv` symlinks:** Keep `box.toml`/`policy.dw` outside `[agent.filesystem].write`; include host `uv` Python install dirs (`~/.local/share/uv/python`) in `[agent.filesystem].read`; route `codeact_shell` through `sh -c` under `STRANDS_BOX=1` so Dogwood logs temporal shell events.

## Pitfall 8: `@file` False Positives, `"document"` History Conversion & `/review` Mode Traps (Phase 18)
- **What happens:**
  1. Prompts naturally contain `@dataclass`, `@pytest.mark`, or emails — attaching unresolved `@tokens` would fail turns. Only resolve `@<token>` when it maps to an existing regular in-scope file.
  2. Attaching a PDF creates a `{"document": ...}` block, which `convert_history` (`model_switch.py:371`) currently misses when switching to a media-less target (`Supports only image/video`), risking downstream Bedrock/OpenAI `ValidationException`. Fix `convert_history`, `_media_placeholder_block`, `_MEDIA_PLACEHOLDER_RE`, and `canonical_prefix_hash` for `"document"`, and sanitize `document.name`.
  3. `/review` cannot ask the agent to run `git diff` because `PolicyClassifier` blocks `shell` in Plan mode (`PLAN_MUTATING_TOOLS`), and `--codeact code`/`both` would inject `CODEACT_PREFIX` telling the model to call blocked `python_repl`. Pre-collect `git diff` in Python (`dispatch/review.py`, rejecting `-`-prefixed refs), restore sticky `ModeState` cleanly, and force `turn_interface = "tool"` for `/review`.
- **Complexity budget warning:** `run_loop` is at `C (18)` and `_setup_decision_entries` is at `C (20)` (`xenon --max-absolute C` max is 20). Isolate new logic in dedicated modules to avoid failing CI complexity gates.
