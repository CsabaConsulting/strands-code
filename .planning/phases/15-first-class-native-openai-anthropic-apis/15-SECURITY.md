---
phase: "15"
slug: "first-class-native-openai-anthropic-apis"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-24"
---

# Phase 15 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `PyPI / uv.lock -> openai & anthropic extras` | Optional OpenAI (`openai>=2.0.0`) & Anthropic SDK dependency groups pinned via `uv.lock` | `strands-agents[openai]` (`openai 2.54.0`), `strands-agents[anthropic]` (`anthropic 2.13.0`), [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock) |
| `Untrusted CWD repository (.env) -> CLI entry & SDK imports` | Launching inside an untrusted repo triggers third-party imports (`smolagents`, `litellm`, `openai`, `anthropic`) | Repo `.env` vars blocked at package init via `disable_cwd_dotenv()` before `os.environ` population |
| `config.yaml (ProviderConfig) -> preflight -> build_agent / model switches` | Persisted `model`, custom `base_url`, and `api_mode` cross launch, `/model`, `/route`, and `/btw` | Non-secret host URL, provider ownership (`_base_url_provider`), validated `api_mode` (never secrets) |
| `AnthropicModel / OpenAIResponsesModel / RichHistory -> convert_history -> foreign wire` | Cross-provider/cross-vendor switches serialize conversation history across incompatible APIs | Signed `reasoningContent`, `toolUse["reasoningSignature"]`, Anthropic `SummaryBlock` (`summary`), `RichHistory` stashes |
| `Model catalog & live_pricing -> /model & anthropic-models.json` | Live `openai.models.list()`, `anthropic.models.list()`, and 24h disk caches feed `/model` tree and `window_for()` | Model IDs, Anthropic `max_input_tokens` and `retires_at` dates, LiteLLM/OpenRouter tables |
| `Provider API usage & extractive compaction -> /cost & summaries` | Provider token telemetry (`inputTokens`, cached read/write tokens) and fallback text summaries cross session logs | Display-only USD estimates and credential-scrubbed compaction text |
| `Dev UAT rig & upstream docs -> tmux / GitHub issues` | Live-tmux UAT scenarios (`o1`, `an1`) and upstream issue drafts (`#6521`, `#6522`) | Strip `AWS_*` env vars, isolate `XDG_CONFIG_HOME` (`/tmp/uatr8/`), zero real credentials in artifacts |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` (`smolagents`) |

---

## Threat Register

Audited against Phase 15 commits (`27bedc5..3b8ab4f`), GPT-6.2 Sol/Astra addition (`fa51c2d`), UAT verification (`a5defbe`), and ASVS Level 1 remediations (`8368ddb`) at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-15-01` | Tampering (Supply Chain & Untrusted CWD `.env`) | [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock), [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) | medium | mitigate | Optional `openai` (`openai>=2.0.0`, `2.54.0`) and `anthropic` (`2.13.0`) extras pinned in `uv.lock` (`uv lock --check` resolves `156` packages exit `0`). `_SDK_EXTRA_HINTS` maps `"openai"` and `"anthropic"` without eval/install side effects. Verified `disable_cwd_dotenv()` prevents `import openai` / `import anthropic` from loading untrusted CWD `.env` (`CANARY: None`). | closed |
| `T-15-02` | Information Disclosure / Credential Exfiltration (Cross-Provider `base_url`) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py), [provider_config.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/provider_config.py) | **high** | mitigate | **Discovered & remediated during this audit (`8368ddb`):** `agent._base_url` previously propagated unguarded across `/model`, `/route`, `/btw`, and CLI `--model` overrides, letting an OpenAI proxy `base_url` send `ANTHROPIC_API_KEY` (or vice versa) to the wrong endpoint. Added `scoped_base_url()` and `_base_url_provider` tracking across `build_agent`, `_root`, `apply_switch`, `_route_side_spawn`, and `build_btw_agent`, plus automatic `base_url`/`api_mode` clearing in `ProviderConfig.save_model_choice()` on cross-provider switches. Pinned in [test_first_run.py](file:///home/csaba/repos/AWS/strands-code/tests/entry/test_first_run.py), [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py), and [test_btw.py](file:///home/csaba/repos/AWS/strands-code/tests/loop/test_btw.py). See `R-15-02`. | closed |
| `T-15-03` | Spoofing / Injection & Information Disclosure (`base_url` URI + OpenAI Compaction Scrubbing) | [provider_config.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/provider_config.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | **high** | mitigate | **Discovered & remediated during this audit (`8368ddb`):** `ProviderConfig` previously accepted non-HTTP schemes, control characters, and embedded `user:pass@` URLs in `base_url`, and `scrub_credentials()` lacked an OpenAI `sk-...` pattern for extractive compaction summaries. Added `_validate_base_url()` (strict `http`/`https` + host, rejects embedded credentials and whitespace/control chars), temp symlink check + `0o600` chmod in `ProviderConfig.save()`, and `sk-(?:proj-\|svcacct-)?` redaction in `_CRED_PATTERNS`. Pinned in [test_first_run.py](file:///home/csaba/repos/AWS/strands-code/tests/entry/test_first_run.py) and [test_cost_context.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_cost_context.py). See `R-15-03`. | closed |
| `T-15-04` | Injection / Tampering (`route_label` ANSI Escapes & `live_pricing` Symlink Writes) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [live_pricing.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/live_pricing.py) | medium | mitigate | **Discovered & remediated during this audit (`8368ddb`):** `route_label()` sliced `retires_at.strip()[:10]` verbatim, and `_write_cache`/`_read_cache` wrote/read cache files without symlink checks or atomic replacement. Restricted `route_label()` with `_ISO_DATE_RE` (`^\d{4}-\d{2}-\d{2}`) and hardened `_read_cache`/`_write_cache` with `is_symlink()` refusal, `0o700` dir / `0o600` temp file permissions, and `os.replace()`. Pinned in [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py) and [test_live_pricing.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_live_pricing.py). | closed |
| `T-15-05` | Tampering / Wire Validation Failure (Cross-Provider Thinking & `SummaryBlock`) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py) | high | mitigate | `convert_history()` and `_should_restore_rich()` enforce `supports_reasoning(new_id) and same_vendor(old_id, new_id) and same_provider(old_id, new_id)`, stashing raw signed `reasoningContent` across `anthropic/` <-> `bedrock/anthropic.*` in `RichHistory` and converting non-Anthropic `SummaryBlock` (`summary`) blocks via `_convert_summary_block()` and `fork_btw_history()` into `SUMMARY_LABEL` text. Live-verified in UAT Test 4 (`4a`, `4c`). | closed |
| `T-15-06` | Information Disclosure (Credential Prefix Checks & Secret Sinks) | [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | high | mitigate | `has_openai_credentials()` / `has_anthropic_credentials()` check non-empty `.strip()` presence only (preserving `STRANDS_BOX` phantom tokens without prefix inspection). `test_no_credential_persistence_sinks` and `test_canary_secrets_never_leak_to_output_logs_or_disk` verify zero `os.environ`/`os.getenv` reads and zero secret persistence across runtime modules and `config.yaml`. | closed |
| `T-15-07` | Denial of Service / Misconfiguration (OpenAI `reasoning.effort` & GPT-6.2 `model_info`) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py) | medium | mitigate | `configure_openai_for_model()` strips `params["reasoning"]` on non-reasoning models (`gpt-4o`, `gpt-4.1*`), clamps unsupported effort values on `o1`/`o3`/`o4-mini`, `gpt-5`..`5.2`, `gpt-6-astra`, `gpt-6.1-sol`, and `gpt-6.2-*` across all 4 call sites, and bridges retireable `ModelInfo` for `gpt-6.2-sol`/`gpt-6.2-astra` when the locked SDK lacks it. Live-verified in UAT Test 4 (`4b`, `4d`; upstream `#6522`). | closed |
| `T-15-08` | SSRF / Info Disclosure (`/model` Discovery & Grouping) | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py) | medium | mitigate | `_discover_openai_models()` and `_discover_anthropic_models()` gate behind `first_run.has_*_credentials()` (never querying unkeyed providers), filter non-chat OpenAI IDs strictly via `_OPENAI_NON_CHAT_TOKENS`, and group via linear string partitioning in `_vendor_family()` (zero ReDoS). Live-verified in UAT Test 3 (`52` OpenAI / `15` Anthropic / `0` unkeyed leakage). | closed |
| `T-15-09` | Repudiation / Vocabulary & Usage Normalization | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | low | mitigate | `_extract_prompt_usage()` normalizes inclusive (`OpenAI`) vs. exclusive (`Anthropic`/`Bedrock`) `accumulated_usage` without double-counting, `cache_prices_for()`/`cost_for()` remain display-only (`"Display only — no budgets or enforcement."`), and `test_no_budgets_or_enforcement_vocabulary` blocks enforcement terms across CLI modules. | closed |
| `T-15-10` | Isolation / Upstream Divergence (`scripts/uattest/` & `strands_code_agent/`) | [scenarios_openai_anthropic.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/scenarios_openai_anthropic.py), [driver.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/driver.py), [strands_code_agent/](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/code_agent.py) | medium | accept | `driver.py` dispatches statically via `SCENARIOS`; `scenario_o1`/`scenario_an1` strip `AWS_*` env vars and isolate `XDG_CONFIG_HOME` under `/tmp/uatr8/`; `tests/rig/` stays 100% offline (`42 passed`); `strands_code_agent/` remains byte-identical (`git diff ee42ea2 -- strands_code_agent/` empty per `D-24`, `R-15-01`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-15-01` | `T-15-10` | Phase 15 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty). Any `CodeAgent` or upstream SDK changes stay decoupled as upstream issues (`#6521`, `#6522`) or Phase 19 Strands Box OS containment (`SANDBOX-01`). | secure-phase L1 audit | 2026-11-24 |
| `R-15-02` | `T-15-02` | Programmatic callers passing a pre-populated `agent._base_url` without `agent._base_url_provider` (or CLI `--model <other_provider/...>` when `config.yaml` sets `base_url` without `config.model`) preserve caller-supplied `base_url` intentionally for backwards compatibility. All CLI-built sessions and `ProviderConfig.save_model_choice()` switches enforce provider ownership. | secure-phase L1 audit | 2026-11-24 |
| `R-15-03` | `T-15-03` | Plaintext `http://` `base_url` remains allowed (when valid URL without embedded credentials or control chars) for local loopback proxies and development gateways (e.g., `http://127.0.0.1:8000/v1`, Ollama/vLLM). Production remote gateways must use `https://`. | secure-phase L1 audit | 2026-11-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-24 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-15-02`, `T-15-03`, `T-15-04` in `8368ddb`; targeted security/regression suite `441 passed, 2 deselected`; rig suite `42 passed`; full default suite `1686 passed, 11 deselected` sandboxed + standalone loopback stub `1 passed` = `1687/1687` green; `ruff check`, `ruff format --check` `117 files`, `xenon --max-absolute C`, `lint-imports` `1 kept / 0 broken`, `uv lock --check` `156 packages`, and `git diff ee42ea2 -- strands_code_agent/` empty verified after final code edit; live UAT `15-UAT.md` `6/6 PASS`) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-24
