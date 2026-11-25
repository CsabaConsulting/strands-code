---
phase: "17"
slug: "decision-routing-convergence-decisionmodel"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-24"
---

# Phase 17 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `Untrusted CWD repository (.env) -> disable_cwd_dotenv() -> transports & strands.decisions` | Importing `strands_code_cli` and `strands.decisions` inside an untrusted workspace | Repo `.env` auto-loading blocked at package init; `TYPESAFE_API_KEY` / `JEV_API_KEY` / `OPENROUTER_API_KEY` confirmed `None` |
| `Untrusted repo .agent/routing.yaml -> load_strategy / validate_strategy / save_strategy` | Strategy YAML parsed fail-soft on load, judged offline on validate, written atomically (`0o700`, non-symlink) | Candidate IDs (`MAX_CANDIDATES = 26`), `directives` (`2000`-char cap), `local_base_url`, engine model IDs, secret-key stripping (`api_key`, `JEV_API_KEY`, `TYPESAFE_API_KEY`) |
| `Env API keys (OPENROUTER / TYPESAFE / JEV / OLLAMA) -> read_env_api_key -> DecisionModel headers` | Provider credentials read only in `routing/` layer | Non-empty trimmed secrets without control chars (`< 0x20`, `0x7f`) attached strictly to request headers |
| `System One HTTP transports (api.typesafe.ai, decisionapi.net, openrouter.ai, Ollama) <-> per-call httpx.AsyncClient / Client` | Hosted TLS APIs and local/proxied Ollama `/api/version`, `/api/tags`, `/v1/systemone` | Bounded `<= 64 KiB` JSON bodies (`ask` truncated), `follow_redirects=False`, strict `NaN`/`Infinity` rejection, loopback `Authorization` suppression |
| `LLMDecisionModel <-> resolve_harness_model(..., effort="off", web_search=False, caching=False) <-> structured_output` | Untrusted user asks + directives passed to structured-output LLM routing | Prompt-injection system guardrail in [llm_decision_model.py](file:///home/csaba/repos/AWS/strands-code/.venv/lib/python3.12/site-packages/strands/decisions/llm_decision_model.py), bounded `asyncio.wait_for` timeout, forced enum + `Uncertain` hold |
| `DecisionModel.ask() <-> OpenTelemetry "decision" spans` | SDK tracing around every routing decision (`INTERNAL` `"decision"` span) | Question IDs, serialized answers, latency, token counts (no API keys or raw headers) |
| `Routing events -> cost_context / scrub_credentials() -> /cost & summaries` | Token/USD telemetry & transcript display | `openrouter`/`native` actuals vs `llm` estimated lane vs `$0.0000` `decisions_api`; credential scrubbing in summaries |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` (`smolagents`) |

---

## Threat Register

Audited against Phase 17 commits (`f6d8651..1ea2872`), [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py), [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), upstream `strands.decisions` modules (`decision_model.py`, `_system_one_http_adapter.py`, `typesafe_decision_model.py`, `decisions_api_decision_model.py`, `llm_decision_model.py`), UAT (`17-UAT.md` `6/6` passed), and ASVS Level 1 remediations verified freshly across the full suite at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-17-01` | Information Disclosure / Header Injection (`TYPESAFE_API_KEY`, `JEV_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_API_KEY`) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py), [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), [first_run.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/first_run.py) | high | mitigate | `tests/conftest.py` scrubs `TYPESAFE_API_KEY` & `JEV_API_KEY` hermetically unless `@pytest.mark.integration`; `disable_cwd_dotenv()` blocks untrusted CWD `.env` injection across `strands_code_cli.routing.transports` & `strands.decisions` imports (`None None`); `save_strategy` drops secret-shaped keys (`JEV_API_KEY`, `TYPESAFE_API_KEY`); zero `os.environ` in `model_switch.py`/`cost_context.py`/`dispatch/`/`loop/`/`entry/main.py` (`test_no_credential_persistence_sinks`). **Hardened in this audit:** added `read_env_api_key()` stripping outer whitespace and rejecting ASCII control chars (`< 0x20`, `0x7f`) across all 4 env keys in `transports.py` and `core.py` readiness/attempt/skip-note paths. | closed |
| `T-17-02` | Information Disclosure / Terminal Control Injection (Error Messages, OTel Spans & `Uncertain.reason`) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | **medium** | mitigate | `failure_reason()` maps transport faults strictly to short classes (`HTTP <code>`, `timeout`, `refused`, `unreachable`, `invalid body`, `invalid table`) with zero response bodies or `Authorization` headers; `scrub_credentials()` redacts `TYPESAFE_API_KEY=...` & `JEV_API_KEY=...` in `cost_context.py`. **Discovered & remediated in this audit:** added `_sanitize_uncertain_reason()` in `transports.py` stripping ASCII control chars/ANSI escapes (`\x1b`, `\r\n`), normalizing whitespace, and capping `Uncertain.reason` at `200` chars; canary test confirms zero API key leakage across HTTP 401 failures and OTel `"decision"` spans (`R-17-04`). | closed |
| `T-17-03` | Spoofing / SSRF & Credential Exfiltration (`valid_base_url`, `preflight_get`, `local_engine_ready`, `ollama_headers`) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py) | **high** | mitigate | **Discovered & remediated in this audit:** tightened `valid_base_url()` to reject embedded `username`/`password`, ASCII control chars & whitespace, `query`, `fragment`, and invalid ports (`http`/`https` + hostname only); enforced `valid_base_url()` pre-checks in both `local_engine_ready()` and `preflight_get()` (zero requests on bad URLs); added `_is_loopback_host()` (`ipaddress.ip_address`: full `127.0.0.0/8`, `::1`, `[0:0:0:0:0:0:0:1]`, `::ffff:127.0.0.1`, `localhost`, `*.localhost`, fail-closed `True` on parse errors) so `ollama_headers()` suppresses `Authorization` on all loopback and invalid URLs (`R-17-02`). | closed |
| `T-17-04` | Denial of Service / Event-Loop Deadlock (`run_decision_sync` & Per-Call `AsyncClient`) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py) | medium | mitigate | `run_decision_sync()` branches on `asyncio.get_running_loop()` (direct `asyncio.run` vs isolated `ThreadPoolExecutor(max_workers=1)`) with per-call `async with make_async_client(timeout)`, `asyncio.wait_for(..., timeout=timeout)` around `LLMDecisionModel.ask()`, single retry limited strictly to `ModelThrottledException`, `429/5xx`, and timeouts (zero retries on `ConnectError`, 4xx, `StructuredOutputException`, `ContextWindowOverflowException`). | closed |
| `T-17-05` | Business Logic Bypass (`Uncertain` Sentinel Confusion & `candidates[0]` Fallback) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py) | high | mitigate | `decision_result_to_engine_result()` explicitly narrows `isinstance(answer, Uncertain)` before answer indexing; `LLMDecisionModel` runs with `uncertainty=True` and holds immediately (`llm uncertain`) with zero fallback to later engines or `candidates[0]`; System One transports validate probabilities (`math.isfinite`, 4-decimal grid tolerance), reject reserved `"uncertain"` choice labels pre-send, and preserve `0.62`/`0.04` gating and byte-identical history on hold. | closed |
| `T-17-06` | Information Disclosure / Tampering (`follow_redirects=False` & Non-Standard `NaN`/`Infinity` JSON Constants) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py) | **high** | mitigate | **Discovered & remediated in this audit:** set explicit `follow_redirects=False` in `make_async_client()` and `make_sync_client()` so HTTP 301/302/307/308 responses stop on hop 1 with `HTTP <code>` instead of forwarding `Authorization` headers to redirect targets; added `parse_constant=_reject_json_constant` in `_parse_system_one_payload()` and `preflight_get()` (matching upstream `_system_one_http_adapter.py:238`) so `NaN`/`Infinity` fail closed to `"invalid body"` / `None`. | closed |
| `T-17-07` | Injection / Tampering (`routing.yaml` Model IDs, Directives, Symlinks & Zero-Network Validate) | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py), [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py) | **medium** | mitigate | **Discovered & remediated in this audit:** added `valid_model_id()` rejecting whitespace and ASCII control chars across `_assign_engine_string()` (fail-soft drop + warning on load), `_validate_engine_model_ids()` (strict `INVALID` + `fix:` on `/route validate`), and all 5 `run_*_decision()` entrypoints before HTTP send or model resolution; `build_decision_state()` caps `ask`/`directives` at `ASK_TRUNCATE_CHARS = 2000`; `fit_decision_payload()` & `build_folded_state_and_questions()` bound bodies `<= 64 KiB`; symlinks fail loud and `validate_strategy()` makes zero network calls. | closed |
| `T-17-08` | Privilege Escalation / Unintended Tool Invocation (`LLMDecisionModel` Tools & History Integrity) | [transports.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/transports.py), [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py) | medium | mitigate | `run_llm_decision()` resolves `resolve_harness_model(..., effort="off", web_search=False, caching=False)` suppressing `web_search` and prompt caching; `LLMDecisionModel` enforces forced structured-output enum + prompt-injection rules; picked efforts still pass `validate_routed_effort()` (`supports_reasoning()`), and switches go through `apply_model_action` + `convert_history()` + `RichHistory` stashes (`R-17-03`). | closed |
| `T-17-09` | Repudiation / Vocabulary & `/cost` Actual vs Estimated Lane Integrity | [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py) | low | mitigate | `_routing_line()` & `_fold_routing_events()` route `engine == "llm"` spend (`cost_for()`) into the `estimated` lane without `"actual"` suffix, keep `decisions_api` at `$0.0000` (`cost=None`), keep `openrouter`/`native` in `actuals`, preserve `price_table` (`CC 20`) untouched, and pass `test_no_budgets_or_enforcement_vocabulary`. | closed |
| `T-17-10` | Isolation / Complexity Ceiling & Upstream Immutability (`strands_code_agent/`, `CC 20`, `lint-imports`) | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/routing/core.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), [strands_code_agent/](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/code_agent.py) | medium | accept | Extracted `_assign_engine_string()` and `_validate_engine_model_ids()` keeping `_parse_engine` at `C (12)` and every function `<= C (20)`; left `save_strategy` (`20`), `_setup_decision_entries` (`20`), `price_table` (`20`), and `strands_code_agent/` untouched (`git diff ee42ea2 -- strands_code_agent/` empty, `D-24`, `R-17-01`); `lint-imports` enforces 0 `entry/` imports from `routing/`. | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-17-01` | `T-17-10` | Phase 17 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty) and leaves complexity-ceiling functions `save_strategy` (`20`), `dispatch/core.py:_setup_decision_entries` (`20`), and `cost_context.py:price_table` (`20`) unmodified. | secure-phase L1 audit | 2026-11-24 |
| `R-17-02` | `T-17-03` | Plaintext `http://` remains permitted on `local_base_url` / `OLLAMA_HOST` proxies for trusted LAN GPU hosts without TLS (`test_proxied_host_carries_bearer_key`), while loopback (`127.0.0.0/8`, `::1`, `localhost`, `*.localhost`), invalid/credential-bearing URLs, and redirects (`follow_redirects=False`) suppress `Authorization`. Remote internet endpoints should use `https://`. | secure-phase L1 audit | 2026-11-24 |
| `R-17-03` | `T-17-08` | Allowing `engine.order: [llm]` and `engine.llm_model` in `.agent/routing.yaml` means a repository config can direct one routing structured-output call per ask (using whichever provider key is already configured in env); impact is bounded by `effort="off"`, `web_search=False`, `caching=False`, `ASK_TRUNCATE_CHARS = 2000` + `64 KiB` cap, and `10s` `asyncio.wait_for` timeout, matching existing repo-level `decision_model` trust boundaries. | secure-phase L1 audit | 2026-11-24 |
| `R-17-04` | `T-17-02` | Upstream `strands.decisions._system_one_http_adapter._raise_http_error()` puts server error messages (`error`/`message`/`detail` from JSON body) in `httpx.HTTPStatusError` recorded on OTel span exceptions (`decision_model.py:90`), never API keys or request headers; CLI-facing `failure_reason()` strips error bodies entirely and surfaces only short classes (`HTTP <code>`, `timeout`, `refused`, `unreachable`, `invalid body`, `invalid table`). | secure-phase L1 audit | 2026-11-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-24 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-17-03` HIGH, `T-17-06` HIGH, `T-17-07` MEDIUM plus `T-17-01` env key whitespace/CRLF & `T-17-02` `Uncertain.reason`/canary checks; verified after final code/test edits: `ruff format --check` `121 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C` `exit 0` with `save_strategy`/`_setup_decision_entries`/`price_table` untouched at `20` and `_parse_engine` reduced `16 -> 12`, `lint-imports` `Contracts: 1 kept, 0 broken`, `uv lock --check` `Resolved 156 packages`, `pytest tests/rig/` `44 passed`, full default suite `1745 passed, 14 deselected` sandboxed + standalone loopback stub `1 passed` = `1746/1746` non-integration suite green, `git diff ee42ea2 -- strands_code_agent/` empty; `17-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-24
