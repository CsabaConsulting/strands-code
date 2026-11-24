---
phase: "14"
slug: "first-class-google-gemini-provider-aware-startup"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-23"
---

# Phase 14 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `PyPI / uv.lock → gemini extra` | Optional Google GenAI SDK dependency group pinned via lockfile | `strands-agents[gemini]` (`google-genai`), `pyproject.toml`, `uv.lock` |
| `Untrusted CWD repository (.env) → CLI startup / third-party imports` | Launching `strands-code` inside an untrusted repo triggers `smolagents.remote_executors` and `litellm._process_defaults` imports | Repo `.env` vars guarded at entry (`disable_cwd_dotenv`) before `os.environ` population |
| `Host / Strands Box env & ProviderConfig → preflight → model factory` | Presence-only credential checks, `--model` CLI flag, Vertex vs. API key conflict check, and `STRANDS_BOX=1` STS bypass | Env var presence booleans (never values/prefixes), `model` / `base_url`, error pointers |
| `GeminiModel / RichHistory → convert_history / prepare_resumed_history → foreign provider wire` | Cross-vendor model switches strip `toolUse["reasoningSignature"]` while keeping stashes aligned via `canonical_prefix_hash()` | Message history, `toolUse["reasoningSignature"]`, `RichHistory` stashes |
| `google.genai.Client().models.list() & live_pricing → /model & /cost` | Credential-gated model discovery, `_vendor_family()` cascade grouping, bundled LiteLLM / static pricing lookups | `generateContent` model IDs, model display groupings, display-only token/cost metadata |
| `Dev UAT rig (scripts/uattest/scenarios_gemini.py) → tmux / CLI` | Live-tmux UAT runner spawns `strands-code` with stripped `AWS_*` env and isolated `XDG_CONFIG_HOME` | `--model`, sentinel token, `/context`, `/cost`, `/model` switch output (`/tmp/uatr8/g1.log`) |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` (`smolagents`) |

---

## Threat Register

Audited against Phase 14 commits (`947c5a7..1666e13`), downstream documentation/UAT additions through `HEAD` (`dae7c23`), and the `T-14-02` remediation at OWASP ASVS Level 1 (`security_block_on: high`).

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-14-01` | Tampering (Supply Chain) | [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml#L43), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) | medium | mitigate | Added optional `gemini = ["strands-agents[gemini]"]` pinned via `uv.lock` (`uv lock --check` resolves `154` packages exit `0`). Missing `google-genai` surfaces static install hint `_SDK_EXTRA_HINTS["google"] = "gemini"` (`TestSdkHints`). | closed |
| `T-14-02` | Spoofing / Config & Endpoint Injection (Untrusted CWD `.env`) | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [\_\_init\_\_.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/__init__.py) | **high** | mitigate | **Discovered & remediated during this audit:** Importing `strands_code_cli` imported `SandboxedPythonInterpreter` → `smolagents.remote_executors` (`line 48`) and `/cost`/pricing paths lazily imported `litellm._process_defaults` (`line 24`), both of which called `dotenv.load_dotenv()` on CWD `.env` — allowing an untrusted repo `.env` to inject `GEMINI_API_KEY`, `ANTHROPIC_BASE_URL`, `GOOGLE_GEMINI_BASE_URL`, or `STRANDS_BOX=1` and hijack ambient model auto-pick, bypass STS, or redirect API calls. Added `disable_cwd_dotenv()` in `first_run.py` and invoked it at the top of `strands_code_cli/__init__.py` ahead of `entry/main.py`, blocking implicit CWD `load_dotenv()` (`dotenv_path=None, stream=None`) while delegating explicit path/stream calls. Pinned by `TestCwdDotenvGuard` in [test_first_run.py](file:///home/csaba/repos/AWS/strands-code/tests/entry/test_first_run.py). See `R-14-02`. | closed |
| `T-14-03` | Information Disclosure (Credential Leaks & Sink Discipline) | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [.gitignore](file:///home/csaba/repos/AWS/strands-code/.gitignore) | high | mitigate | Preflight inspects `bool(os.environ.get(name, "").strip())` only (never inspects prefixes like `AIza`/`sk-`, preserving `strands_box_` phantom compatibility), never logs/prints secret values (`test_canary_secrets_never_leak_to_output_logs_or_disk`), keeps `os.environ`/`os.getenv` absent from `entry/main.py`, `model_switch.py`, `cost_context.py`, `dispatch/core.py`, `loop/core.py`, and `loop/pump.py` (`test_no_credential_persistence_sinks`), and `.gitignore` excludes `.env` / `.env.*`. | closed |
| `T-14-04` | Broken Configuration / Persistent Side Effects | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py) | medium | mitigate | `_validate_google_env()` fails fast (`exit 2`) before `SessionIndex`/`build_agent` when `GOOGLE_GENAI_USE_VERTEXAI` conflicts with `GOOGLE_API_KEY`/`GEMINI_API_KEY` or lacks `GOOGLE_CLOUD_PROJECT`; `--model` rejects blank strings, loads read-only `ProviderConfig.load()` before preflight, and never writes `config.yaml`. | closed |
| `T-14-05` | Elevation of Privilege (Strands Box STS Bypass) | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py) | medium | mitigate | `_run_bedrock_probe()` skips `sts.get_caller_identity()` only when `STRANDS_BOX` is truthy or `AWS_BEARER_TOKEN_BEDROCK` is non-empty; explicit/ambient non-AWS providers still require non-empty credential presence and never weaken `PolicyHumanInTheLoop` or `SandboxedPythonInterpreter` runtime controls. | closed |
| `T-14-06` | Tampering / Validation Crash (Cross-Vendor `reasoningSignature`) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) | high | mitigate | `supports_reasoning()` limits pass-through to `("bedrock", "anthropic", "google")` (honoring `model-capabilities.yaml` first; `google.gemma-*` stays `False`). `convert_history()` strips `toolUse["reasoningSignature"]` via `_convert_tool_use_block()` on cross-vendor switches (preventing `LiteLLMModel` `__thought__` `tool_calls[].id` corruption) while keeping `RichHistory` stashes aligned via `_has_reasoning()` and `_canonical_block()`. Verified in `TestGeminiCrossProviderSafety` + live `g4a`. | closed |
| `T-14-07` | Denial of Service / Misconfiguration (Gemini 2.5 Thinking & Built-in Tools) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py) | medium | mitigate | `configure_gemini_for_model()` normalizes `thinking_level` → `thinking_budget` (`0` for off/none, `-1` otherwise) and clears `gemini_tools=[]` on `gemini-2.5*` across all 4 call sites (`build_agent`, `apply_switch`, `_route_side_spawn`, `build_btw_agent`), leaving Gemini 3+/4+ untouched (live verified `g4c`; upstream tracked at `strands-agents/harness-sdk#6510`). | closed |
| `T-14-08` | SSRF / Info Disclosure / ReDoS (`/model` Discovery & Grouping) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | medium | mitigate | `_discover_google_models()` checks `first_run.has_google_credentials()` before importing/calling `google.genai`, keeping AWS-only pickers uncluttered; filters strictly to `generateContent` `gemini-*` models via `_is_google_chat_model()` and fails soft to `CURATED_GEMINI_MODELS`; `_vendor_family()` uses linear string partitioning + anchored `_PURE_VENDOR_RE` (zero ReDoS, fixing `gemini-2.5-pro` decimal splits). | closed |
| `T-14-09` | SSRF / Info Disclosure (`live_pricing` & `_live_price`) | [live_pricing.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/live_pricing.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | low | mitigate | `_live_price()` gates `bedrock_live_price` behind `_is_bedrock_model()` so direct `google/`/`anthropic/`/`openai/` routes never hit AWS Pricing APIs, resolves local `litellm.model_cost` / static `MODEL_PRICING` / `MODEL_LIMITS`, honors `STRANDS_CODE_NO_LIVE_PRICING`, and enforces display-only vocabulary (`test_no_budgets_or_enforcement_vocabulary`). | closed |
| `T-14-10` | Command Injection / ToS Bypass / Upstream Divergence | [driver.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/driver.py), [scenarios_gemini.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/scenarios_gemini.py), [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md), [local_sandboxed.py](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/python_environments/local_sandboxed.py) | medium | accept | `driver.py` dispatches statically via `SCENARIOS.get("g1")`; `scenario_g1` strips `AWS_*` vars and isolates `XDG_CONFIG_HOME` under `/tmp/uatr8/g1`; `docs/QUICKSTART.md` explicitly excludes consumer Gemini CLI OAuth (ToS violation); `strands_code_agent/` stays untouched under `D-24` (`R-14-01`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-14-01` | `T-14-10` | Phase 14 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty). Any `CodeAgent` / `smolagents` hardening stays decoupled for upstream PRs (`D-07`) and Phase 17 Strands Box OS containment (`SANDBOX-01`). | secure-phase L1 audit | 2026-11-23 |
| `R-14-02` | `T-14-02` | `smolagents.remote_executors:48` and `litellm._process_defaults:24` call `dotenv.load_dotenv()` upstream. Because `strands_code_agent/` is frozen under `D-24`, `disable_cwd_dotenv()` enforces the boundary at the `strands_code_cli/__init__.py` entrypoint; standalone Python library consumers importing `strands_code_agent` directly (outside `strands_code_cli`) without calling `disable_cwd_dotenv()` still inherit upstream `smolagents` import behavior. | secure-phase L1 audit | 2026-11-23 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-23 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-14-02` via `disable_cwd_dotenv()` in `first_run.py` + `strands_code_cli/__init__.py` and `TestCwdDotenvGuard`; post-fix targeted security/model/rig suite `278 passed`; full suite `1646 passed, 12 deselected` + loopback `1 passed` = `1647 passed, 0 failed`; `uv lock --check` `154 packages`, `ruff`, `xenon`, `lint-imports` clean; `git diff ee42ea2 -- strands_code_agent/` empty) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-23
