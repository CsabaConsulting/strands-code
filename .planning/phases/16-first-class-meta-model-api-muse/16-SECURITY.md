---
phase: "16"
slug: "first-class-meta-model-api-muse"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-24"
---

# Phase 16 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `PyPI / uv.lock -> strands-agents 1.66.0, strands-harness 0.5.0 & meta extra` | Resynced core SDK dependencies + optional `meta` extra (`strands-agents[openai]`, `openai>=2.0.0`) pinned in `uv.lock` | Package resolutions (`Resolved 156 packages`), [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock) |
| `Untrusted CWD repository (.env) -> CLI entry & SDK imports` | Launching inside an untrusted repo triggers `strands`, `strands_harness`, `openai`, `smolagents`, and `litellm` imports | Repo `.env` auto-loading blocked at package init via `disable_cwd_dotenv()` before `os.environ` population |
| `Env & config.yaml -> first_run -> build_meta_model / resolve_harness_model / build_btw_agent` | `MODEL_API_KEY`, `META_API_KEY`, `META_BASE_URL`, `ProviderConfig.base_url`, and ambient `OPENAI_*` env vars cross adapter construction | API keys (in-memory only, never persisted), validated endpoints, empty OpenAI overrides (`admin_api_key`, `organization`, `project`, `webhook_secret`) |
| `https://api.meta.ai/v1 (or META_BASE_URL) <-> OpenAIResponsesModel / discovery` | Live `GET /v1/models` and `POST /v1/responses` over HTTPS/HTTP | Model catalog IDs (`muse-*`), server-side `web_search` tool calls, multimodal image blocks, inclusive usage counters |
| `RichHistory / Anthropic / Bedrock <-> convert_history -> Meta` | Cross-provider `/model` and `/route` switches into/out of `meta/muse-*` | Signed `reasoningContent`, media attachments (`supports_media == True` for Muse vs `False` for Bedrock Llama), stashed `RichHistory` |
| `Extractive compaction / logs -> scrub_credentials() -> session summaries` | User/tool text containing `LLM\|...` or `LLM_...` Meta tokens crosses summarization & error outputs | Credential-scrubbed text (`[redacted]`), canary-free stdout/stderr/logs |
| `Dev UAT rig & upstream issues -> tmux / GitHub #6521` | Zero-AWS tmux rig (`m1`, `o1`), `.env` isolation in `conftest.py`, and upstream issue update (`#6521`) | Stripped AWS env, isolated `XDG_CONFIG_HOME`, zero real keys in repo files |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` (`smolagents`) |

---

## Threat Register

Audited against Phase 16 commits (`cc99d5a..2247b47`), upstream `#6521` sync (`aab271f`), live UAT (`16-UAT.md` `6/6` passed), and ASVS Level 1 remediations verified freshly across the full suite at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-16-01` | Tampering (Supply Chain & Untrusted CWD `.env`) | [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock), [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) | medium | mitigate | Upgraded cleanly onto `strands-agents>=1.66.0` (`1.66.0`) and `strands-harness>=0.5.0` (`0.5.0`), added optional `meta` extra (`strands-agents[openai]`, `openai>=2.0.0`), pinned in `uv.lock` (`uv lock --check` resolves `156` packages), mapped `_SDK_EXTRA_HINTS["meta"] = "meta"`, and empirically verified `disable_cwd_dotenv()` blocks `MODEL_API_KEY` & `OPENAI_API_KEY` from untrusted CWD `.env` across `strands_harness`/`openai` imports (`None`). | closed |
| `T-16-02` | Information Disclosure / Cross-Provider Credential & Tenant Header Exfiltration (`OPENAI_*` into Meta) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | **high** | mitigate | **Discovered & remediated during this audit:** `build_meta_model()` and `_discover_meta_models()` previously left `api_key` unset when unkeyed and did not override `openai` SDK env fallbacks (`OPENAI_API_KEY`, `OPENAI_ADMIN_KEY`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `OPENAI_WEBHOOK_SECRET`), allowing ambient OpenAI credentials/headers to leak to `api.meta.ai/v1` or a custom Meta proxy. Added `_meta_openai_client_args()` setting explicit `api_key` (`""` unkeyed default, `"not-required"` unkeyed explicit proxy), `admin_api_key=""`, `organization=""`, `project=""`, `webhook_secret=""`, and `default_headers={"OpenAI-Organization": openai.omit, "OpenAI-Project": openai.omit}`. Pinned with real `AsyncOpenAI._build_request()` assertions across all 6 `OPENAI_*` canaries in `test_meta_security_isolates_openai_env_and_validates_inputs`. See `R-16-02`. | closed |
| `T-16-03` | Spoofing / Injection & DoS (`configure_base_url_for_model` URI, Catalog ID Control Chars & Discovery Timeouts) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | **medium** | mitigate | **Discovered & remediated during this audit:** `configure_base_url_for_model()` previously wrote caller `base_url` without scheme/credential validation, `_is_meta_chat_model()` / `build_meta_model()` allowed ASCII control chars (ANSI escapes, newlines) and whitespace inside model IDs, and `_discover_meta_models()` used `openai.OpenAI` default timeouts/retries (`600s × 3`). Added `_validate_base_url(base_url)` + `.rstrip("/")` normalization in `configure_base_url_for_model()`, `_has_unsafe_model_chars()` rejection in `_is_meta_chat_model()` and `build_meta_model()`, and `timeout=5.0, max_retries=0` in `_discover_meta_models()`. Pinned in `test_model_switch.py`. See `R-16-03`. | closed |
| `T-16-04` | Information Disclosure (Meta Token Scrubbing & Env/Error Canary Isolation) | [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [test_first_run.py](file:///home/csaba/repos/AWS/strands-code/tests/entry/test_first_run.py), [test_cost_context.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_cost_context.py) | **medium** | mitigate | **Discovered & hardened during this audit:** Widened Meta token pattern in `cost_context._CRED_PATTERNS` to `r"LLM[_\|]\d+[_\|][A-Za-z0-9\-._~+/=]{12,}"` (covering base64/punctuated `LLM\|...` and `LLM_...` tokens alongside `Bearer \|` support), extended `test_canary_secrets_never_leak_to_output_logs_or_disk` for `MODEL_API_KEY` + `META_BASE_URL` failures, and verified zero `os.environ` reads outside `first_run.py` / `live_pricing.py` / `routing/core.py` (`test_no_credential_persistence_sinks` green). | closed |
| `T-16-05` | Denial of Service / Protocol Misconfiguration (Meta `effort="none"`, `prompt_cache_options`, `0.5.0` Web Search & `caching=False` on `/btw`) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py) | medium | mitigate | `_normalize_meta_effort()` omits `reasoning` on `"none"`/`"off"` (avoiding HTTP 400); `_meta_model_info()` + `CacheConfig()` without `strategy="auto"` avoids HTTP 400 `prompt_cache_options` and `UserWarning`; `build_agent` & `build_btw_agent` pass `caching=False` for pre-built `_strands_model_ref` instances; `resolve_harness_model()` gates `web_search=True` on `_web_search_kind(normalized) == "native"` (`#5997`); live-verified (`0` warnings, `driver.py m1` & `/btw`). | closed |
| `T-16-06` | Tampering / Wire Validation Failure (Cross-Provider Thinking & Multimodal Muse vs Llama Media Scope) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | high | mitigate | `_MEDIA_LESS` narrowed from blanket `(None, "meta", None, None)` to `("bedrock", "meta", "llama3", None)` and `("bedrock", "meta", "llama4", None)` (plus existing `(None, None, None, "llama")`), retaining native vision on `meta/muse-*` while keeping Llama text-only. `supports_reasoning("meta/...")` stays `False`, converting signed thinking into safe `TRACE_LABEL` text via `convert_history()`. | closed |
| `T-16-07` | SSRF / Info Disclosure (`GET /v1/models` Discovery & Picker Grouping) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | medium | mitigate | `_discover_meta_models()` gates strictly behind `first_run.has_meta_credentials()` (returns `([], False)` unkeyed with zero `meta/` leakage), filters non-chat assets (`_META_NON_CHAT_TOKENS`: `image`, `voice`, `transcribe`, `audio`, `sam-`, `embed`, `tts`, `video`, `moderation`) plus control/whitespace chars, and groups deterministically via `_infer_bare_vendor()` into `("meta", "muse")`. | closed |
| `T-16-08` | Information Disclosure / Auth Bypass (`MODEL_API_KEY` / `META_API_KEY` Prefix Checks & `META_BASE_URL` Validation) | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [provider_config.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/provider_config.py) | high | mitigate | `has_meta_credentials()` & `meta_api_key()` check non-empty `.strip()` presence only (supporting arbitrary Strands Box tokens without leaking/inspecting prefixes); `meta_base_url()` and `_validate_meta_env()` fail fast (`typer.Exit(code=2)`) on malformed `META_BASE_URL`; `scoped_base_url()` keeps custom Meta endpoints isolated from other providers. | closed |
| `T-16-09` | Repudiation / Vocabulary & Inclusive Meta Usage Accounting | [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), [live_pricing.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/live_pricing.py) | low | mitigate | `_litellm_keys()` resolves bare & `meta/` Muse entries without Bedrock prefix collision, `MODEL_LIMITS["muse-"]` & `_default_cache_rates()` reflect display-only pricing (`50×` contributor cache rate), and `test_no_budgets_or_enforcement_vocabulary` passes 100%. | closed |
| `T-16-10` | Isolation / Upstream Divergence (`scripts/uattest/`, `conftest.py`, `#6521` & `strands_code_agent/`) | [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), [scenarios_meta.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/scenarios_meta.py), [strands_code_agent/](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/code_agent.py) | medium | accept | `tests/conftest.py` strips `MODEL_API_KEY`, `META_API_KEY`, and `META_BASE_URL`; `scenario_m1` & `scenario_o1` strip `AWS_*` env vars and isolate `XDG_CONFIG_HOME`; `tests/rig/` stays offline (`44 passed`); `strands_code_agent/` remains byte-identical (`git diff ee42ea2 -- strands_code_agent/` empty per `D-24`, `R-16-01`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-16-01` | `T-16-10` | Phase 16 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty). Native `meta/` support in Harness & encrypted reasoning replay stay tracked upstream (`strands-agents/harness-sdk#6521`, `#3389`) via auto-retiring `upstream_supports_meta()`. | secure-phase L1 audit | 2026-11-24 |
| `R-16-02` | `T-16-02` | `openai.AsyncOpenAI.__init__` still reads `OPENAI_CUSTOM_HEADERS` if a user explicitly exports that env var in their own shell; all credential, tenant, and endpoint env vars (`OPENAI_API_KEY`, `OPENAI_ADMIN_KEY`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `OPENAI_WEBHOOK_SECRET`, `OPENAI_BASE_URL`) are explicitly isolated via `_meta_openai_client_args()`. | secure-phase L1 audit | 2026-11-24 |
| `R-16-03` | `T-16-03`, `T-16-08` | Plaintext `http://` remains allowed in `META_BASE_URL` and `ProviderConfig.base_url` (when valid host URL without embedded credentials or whitespace/control chars) for local loopback proxies and development gateways. Remote endpoints must use `https://`. | secure-phase L1 audit | 2026-11-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-24 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-16-02` HIGH, `T-16-03` MEDIUM, `T-16-04` MEDIUM; verified after final code/test edits: `ruff format --check` `119 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C` `exit 0`, `lint-imports` `1 kept, 0 broken`, `uv lock --check` `156 packages`, `pytest tests/rig/` `44 passed`, full default suite `1705 passed, 12 deselected` sandboxed + standalone loopback stub `1 passed` = `1706/1706` green, and `git diff ee42ea2 -- strands_code_agent/` empty; `16-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-24
