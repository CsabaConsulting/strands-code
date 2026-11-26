# Cross-Cutting Invariants & Discussion Hygiene

> Mandatory guardrails for `/gsd-discuss-phase`, `/gsd-plan-phase`, and implementation PRs.
> Created 2026-11-25 after auditing Phases 13–19 to prevent accidental cross-phase drift, Row-1 anchoring, and unverified constraints.

---

## 1. Discussion-Phase Hygiene Rules (`/gsd-discuss-phase` & `/gsd-plan-phase`)

1. **Peer Parity Matrix first:** Before asking design questions on any recurring cross-cutting axis (model providers, routing engines, protected/sensitive paths, config persistence, `/cost` lanes, env vars, CLI surface), present a single compact table showing how every existing peer behaves today.
2. **One atomic decision per question:** Never bundle two independent axes into a single option row (for example, coupling two separate opt-in flags, or bundling policy-protection scope with live integration test scope). Split independent decisions into separate questions.
3. **"Match Existing Pattern" default burden of proof:** Consistency across peers is the default baseline. Any option proposing an exception (e.g., opt-in flag vs auto-detection, config-only vs `/route setup`, `actual` vs `estimated` spend, fail-soft vs fail-loud) MUST name the specific technical or security threat that justifies diverging and carry a `⚠️ Breaks parity with Phase X` note.
4. **Verify constraint claims before locking:** Every complexity, upstream, or policy-engine justification (e.g., `xenon CC <= 20`, Strands Harness behavior, Dogwood default-deny interaction) must be verified with concrete `file:line` references and live metrics (`uv run radon cc`) before presenting options.
5. **No unilateral shifts in "Pre-decided anchors":** Do not bury cross-phase overrides, parity breaks, or new architectural choices inside an italicized "not re-asked" preamble. Surface them explicitly as questions or parity table rows.

---

## 2. Horizontal Backport Rule

Whenever a phase hardens or fixes a shared pattern — such as:
- network timeouts / retry caps in catalog discovery,
- symlink-refused atomic `0o600` file writes (`tempfile.mkstemp(..., dir=path.parent)` + `parent.is_symlink()`),
- credential scrubbing regexes,
- control-char / unsafe-model-id validation, or
- protected-path policy downgrades —

sweep **all existing peer functions** across `strands_code_cli/` in the same phase/commit rather than hardening only the newest addition.

---

## 3. Cross-Cutting Checklists

### A. Adding or Updating a Model Provider

| Layer / File | What to Check / Update |
|---|---|
| `pyproject.toml` | `[project.optional-dependencies]` extra matching `strands-agents[<extra>]` |
| `strands_code_cli/dispatch/core.py` | `_SDK_EXTRA_HINTS` mapping provider prefix to extra name |
| `strands_code_cli/entry/first_run.py` | `_KNOWN_EXPLICIT_PROVIDERS`, `_PROVIDER_ENV_KEYS`, `_AMBIENT_DEFAULT_MODELS`, `_LITELLM_ANY_KEYS`, `_check_explicit_provider`, scoped `*_BASE_URL` / provider env validation (never leaking to other providers!) |
| `strands_code_cli/entry/provider_config.py` | `_provider_of_model`, `save_model_choice()` clearing `base_url`/`api_mode` across providers, `_validate_base_url` |
| `strands_code_cli/entry/main.py` | `model_for_config()`, `_build_web_fetch_model()`, `build_agent()` `base_url`/`api_mode` wiring |
| `strands_code_cli/model/model_switch.py` | `supports_reasoning()`, `_MEDIA_LESS`, `_NO_STREAMING_TOOLS`, `convert_history()` / `prepare_resumed_history()`, `_discover_*_models()` (with `timeout`/`max_retries` caps & `_has_unsafe_model_chars`), `_vendor_of()`, `_vendor_family()`, `configure_*_for_model()`, `resolve_harness_model()` |
| `strands_code_cli/cost/live_pricing.py` | `_litellm_keys()`, `platformdirs.user_cache_dir("strands-code")` cache helpers |
| `strands_code_cli/cost/cost_context.py` | `MODEL_PRICING`, `MODEL_LIMITS`, `window_for()`, `_default_cache_rates()`, `_CRED_PATTERNS` (`scrub_credentials`) |
| `strands_code_cli/sandbox/box.py` | `CORE_PROVIDERS`, `_provider_from_model_id()`, `_providers_from_env()`, `_egress_specs_for_providers()`, `_collect_box_warnings()` |
| `tests/conftest.py` | Add ALL provider API key / endpoint / region env vars to `_PROVIDER_ENV_VARS` |

### B. Adding or Updating a Routing Engine

| Layer / File | What to Check / Update |
|---|---|
| `strands_code_cli/routing/transports.py` | `DecisionModel` subclass, `read_env_api_key()`, `valid_base_url()`, `valid_model_id()`, 64 KiB body fit, explicit `Uncertain` handling |
| `strands_code_cli/routing/core.py` | `_VALID_ORDER_ENGINES`, `_VALID_PRIMARY_ENGINES`, `_ENGINE_KEYS`, `*_engine_ready()`, `chain_skip_notes()`, `/route validate` checks |
| `strands_code_cli/dispatch/core.py` | `_ENGINE_LABELS`, `_setup_engine_order()`, `_setup_gather_engine_models()`, `_route_validate_message()` |
| `strands_code_cli/cost/cost_context.py` | `/cost` routing row lane (`actual` vs `estimated` vs unknown) & provenance |
| `strands_code_cli/sandbox/box.py` | `_providers_from_routing()`, `_providers_from_env()`, egress spec & `policy.dw` rules |
| `tests/conftest.py` | Add engine API key & host env vars to `_PROVIDER_ENV_VARS` |

### C. Adding or Updating Protected / Sensitive Paths

| Layer / File | What to Check / Update |
|---|---|
| `strands_code_cli/policy/core.py` | `_is_protected_skills_or_config_path()` (`protected_dirs` & `protected_files` covering repo `.agent/*` configs/skills/memory, `STRANDS.md`, `~/.config/strands-code`, `~/.cache/strands-code`, `~/.config/strands-box`, `~/.local/share/strands-box`) |
| `strands_code_cli/policy/policy_gate.py` | Disable `"Always — approve + remember rule"` on protected paths so dead `[[allow]]` rules are never written |
| `strands_code_cli/sandbox/box.py` | Keep Strands Box host config outside `[agent.filesystem].write` and verify consistency with `policy.dw` |

### D. Persisted Config & Cache Files

- Resolve directories via `platformdirs.user_config_dir` / `user_data_dir` / `user_cache_dir` (never hardcode `Path.home() / ".cache"`).
- Refuse symlinks on **both** target file and parent directory.
- Write via `tempfile.mkstemp(..., dir=path.parent)` (`0o600` file permissions from creation, `0o700` directory permissions, `os.replace`, unlink temp on error).

---

## 4. Static Repo Invariants (CI-Enforced)

- `strands_code_agent/` remains unmodified on `main` (`git diff ee42ea2 -- strands_code_agent/` empty) so upstream resyncs stay conflict-free; put CLI code and temporary upstream-PR workarounds in `strands_code_cli/` as isolated, auto-retiring bridges, editing `strands_code_agent/` only on a dedicated upstream-PR branch or with explicit user approval when wrapping from `strands_code_cli/` is impossible.
- **Upstream-first contribution & bridge retirement:** For generic bugs or gaps in upstream repos (`aws-samples/sample-strands-code-agent`, `strands-agents/harness-sdk`, `strands-agents/sdk-python`, `strands-agents/box`, or other AWS dependencies), detour to file an upstream issue (and PR when applicable), tag any interim `strands_code_cli/` bridge with `# Upstream: <org>/<repo>#<id> — retire once released`, and track it in `docs/upstream/` + `.planning/STATE.md` for clean removal on future upstream resyncs.
- Zero `os.environ` / `os.getenv` tokens in `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, or `entry/main.py`.
- Zero unnegated `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings in those modules.
- `xenon --max-absolute C strands_code_cli tests scripts` (`CC <= 20`) and `lint-imports` pass.
