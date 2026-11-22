---
phase: "13"
slug: "upstream-sdk-harness-resync"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-21"
---

# Phase 13 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `PyPI/registry → uv.lock` | Upgraded Strands SDK & harness dependencies resolved and locked | `strands-agents==1.65.0`, `strands-harness==0.4.0`, `opentelemetry-processor-baggage==0.66b2` |
| `SDK HITL → PolicyHumanInTheLoop → tool execution` | Upstream `HumanInTheLoop.before_tool_call()` drives `PolicyClassifier` and `PolicyClassifier.ask`, returning `Proceed` or `Deny` into `InterventionRegistry` | Tool name, tool input arguments, `toolUseId`, approval decision, model-facing `Deny.reason` |
| `ContextInjector → InjectedBlock → CLI surfaces` | `harness-py 0.4.0` injects turn-scoped `{"injected": {"text": ..., "source": ...}}` blocks into `agent.messages` | Token estimate (`cost_context`), `RichHistory` prefix digest (`model_switch`), `/btw` forked history (`btw`), terminal output (`callback_handler`) |
| `Persisted snapshot → prepare_resumed_history → provider wire` | Saved session history loaded at startup and normalized or wire-formatted (`#5166`) for the opening model | Historical user/assistant messages, signed `reasoningContent`, media blocks |
| `Model ref / SDK model_info → CLI config/UI` | Model identifiers resolved offline against `strands.models._model_info`, OpenRouter live cache, `_NO_STREAMING_TOOLS`, and printed UI notes | Context window integer, `streaming=False` Bedrock config flag, console note |
| `Dev UAT rig (scripts/uattest/) → tmux/CLI` | Operator-invoked `driver.py` spawns isolated `tmux` CLI sessions against `/tmp/uatr8/` (`XDG_CONFIG_HOME`) using ambient `~/.aws` credentials | Scenario selector (`u1`/`u2`/`u3`), `--session-id` UUID parsed from pane, interactive `Approve?` prompt automation |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` (`smolagents`) tracked separately for upstream PRs (`D-07`) |

---

## Threat Register

Audited against Phase 13 code commits (`31ecc3e`, `8c8b70f`, `51b15b6`), delta commits through `c024329` (`9fecb81`, `900a7d9`, `073c9e1`), plus the `T-13-11` rig hardening at OWASP ASVS Level 1 (`security_block_on: high`).

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-13-01` | Tampering (Supply Chain) | [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml#L27-L31), [uv.lock](file:///home/csaba/repos/AWS/strands-code/uv.lock) | high | mitigate | `pyproject.toml` sets `strands-agents>=1.65.0` and `strands-harness>=0.4.0` without unpinned surprise overrides in CI: `gates.yml` runs `uv sync --locked --extra litellm` and `uv lock --check` verifies resolution (139 packages). Package delta audited (`strands-agents` `1.58.1→1.65.0`, `strands-harness` `0.1.2→0.4.0`, `opentelemetry-processor-baggage 0.66b2`). | closed |
| `T-13-02` | Spoofing / Broken Access Control (HITL) | `PolicyClassifier._last_by_tag` & `PolicyHumanInTheLoop` ([policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py)) | high | mitigate | **Discovered & remediated during this audit:** Previously, if upstream `HumanInTheLoop` skipped calling `PolicyClassifier` on a duplicate `toolUseId` (`hitl.py:340`) or caught a classifier exception (`hitl.py:363`), stale `_last_by_tag[tag]` from an earlier call could survive — letting `ask()` display/decide on an old command's preview or `last_deny_reason()` return an old call's `Deny.reason`. Hardened by popping `_last_by_tag[tag]` at entry to `PolicyClassifier.__call__`, binding `"tool_use_id"` and verifying it in `last_deny_reason()`, and clearing `_last_by_tag[tag]` in `PolicyHumanInTheLoop.before_tool_call` `finally:`. Pinned by `TestHitlFailClosedStaleContext` in [test_policy_gate.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy_gate.py). | closed |
| `T-13-03` | Elevation of Privilege (HITL / Plan Mode) | `PolicyHumanInTheLoop.before_tool_call` ([policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py)) | high | mitigate | Under `strands-agents==1.65.0`, inline `ask` returns `Proceed`/`Deny` directly instead of `Confirm`. `PolicyHumanInTheLoop` ONLY rewrites an already-denied `InterventionDeny` (`isinstance(action, InterventionDeny)`), so it can never downgrade `Deny` to `Proceed` or weaken Plan-mode / `[deny]` blocks; inherits `on_error="throw"` so `TurnCancelled` propagates (`test_turn_cancelled_not_swallowed`), preserves single-HITL name collision (`test_two_hitl_instances_collide`), and retains Plan-mode / `[deny]` / `REVISE_HINT` reasons on the wire. | closed |
| `T-13-04` | Elevation of Privilege (Turn Steering) | [steering.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/steering.py) | medium | mitigate | Retained `BeforeToolCallEvent.cancel_tool` mid-turn redirection and `cancel_signal` wiring across `harness-py 0.4.0` (`todos` plugin stays absent); verified by `tests/loop/test_steering.py`. | closed |
| `T-13-05` | Denial of Service / State Desync | `InjectedBlock` handling ([cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py)) | medium | mitigate | `estimate_messages_tokens()` guards `isinstance(injected, dict)` and counts injected text toward auto-compaction (preventing silent window overrun); `canonical_prefix_hash()` skips `"injected"` so memory reloads never break `RichHistory`; `fork_btw_history()` strips `"injected"` blocks and drops empty messages so side agents avoid duplicate injections. | closed |
| `T-13-06` | Information Disclosure (UI Transcript) | `CodeAgentCallbackHandler` ([callback_handler.py](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/callback_handler.py)) | low | mitigate | Pinned by unit test in [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py) verifying `"injected"` blocks produce zero console output. | closed |
| `T-13-07` | SSRF / Info Disclosure / Type Confusion | `_sdk_window` & `window_for` ([cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py)) | medium | mitigate | `_sdk_window()` reads bundled offline SDK `model_info` lazily without constructing `boto3` or provider HTTP clients; rejects `bool` subclasses of `int` and non-positive values; OpenRouter live lookup honors `live_disabled()` kill switch; `test_no_credential_persistence_sinks` confirms zero `os.getenv`/`os.environ` reads. | closed |
| `T-13-08` | Configuration Integrity / Terminal Injection | `configure_streaming_for_model` ([model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py)) | low | mitigate | `update_config(streaming=False)` applies only when normalized provider is `"bedrock"` and `not supports_streaming_tools(normalized)`; all 7 `_NO_STREAMING_TOOLS` rows (Meta Llama 3/4, Mistral 24.02/24.07, Pixtral 25.02, Writer Palmyra X4/X5) are strictly `"bedrock"`- and model/family-scoped with plain lowercase substring matching (zero ReDoS), leaving OpenRouter, Ollama, and newer streaming Mistral models fail-open (`900a7d9`, `073c9e1`); `UNARY_TOOL_MODE_NOTE` renders via markup-safe `print_plain(...)` (`console.print(..., markup=False)`). | closed |
| `T-13-09` | Tampering / Validation Bypass (Resume) | `prepare_resumed_history` ([model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py)) | medium | mitigate | Resuming onto non-Bedrock or media-less targets fails closed (`old_id = "__resumed__"`, preventing foreign `reasoningContent` or unvalidated signatures from replaying); media-capable Bedrock targets rely on pinned `#5166` `BedrockModel._format_bedrock_messages` wire stripping (`TestUpstreamReasoningWireStrip`) without mutating snapshot history; stash writes reuse validated `session_id` paths under `0o700` session dir. | closed |
| `T-13-10` | Upstream Sandbox Hardening (`smolagents`) | `strands_code_agent/` ([code_agent.py](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/code_agent.py), [local_sandboxed.py](file:///home/csaba/repos/AWS/strands-code/strands_code_agent/python_environments/local_sandboxed.py)) | low | accept | `strands_code_agent/` stayed byte-pristine under `D-24` (`git diff strands_code_agent/` empty). Broader `smolagents` sandbox / OS containment hardening (e.g., `CVE-2026-18830` watchpoints) is explicitly out of Phase 13 scope and tracked via [sample_code_agent_cve_2026_18830_pr.md](file:///home/csaba/repos/AWS/strands-code/docs/upstream/sample_code_agent_cve_2026_18830_pr.md) plus Phase 17/18. See `R-13-01`. | closed |
| `T-13-11` | Elevation of Privilege / Command Injection (Dev UAT Rig) | [driver.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/driver.py), [scenarios_upstream.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/scenarios_upstream.py) | low | mitigate | **Discovered & remediated during delta audit (`51b15b6..c024329`):** `driver.py` uses static allowlisted `SCENARIOS.get(which)` lookup; `scenario_u2` extracts `--session-id` strictly via `SESSION_ID_RE = r"Session ([0-9a-f-]{36})"` (hex + hyphens only, no shell metacharacters); all scenarios isolate `XDG_CONFIG_HOME` under `/tmp/uatr8/` without modifying `~/.config/strands-code/config.yaml` or persisting credentials (`scripts/` is excluded from packaged wheel). Hardened `scenario_u3` `wait_for` from wildcard `Approve\? \[main\] shell` to exact command `Approve\? \[main\] shell — echo HITL_OK_13` so any unexpected model-proposed shell command fails closed (`test_uattest_upstream.py`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-13-01` | `T-13-10` | Phase 13 preserves `D-24` (`strands_code_agent/` byte-pristine, zero edits). Any `CodeAgent` / `smolagents` hardening belongs in an upstream `sample-strands-code-agent` PR (`D-07`) and Phase 17 Strands Box OS containment (`SANDBOX-01`), not ad-hoc Phase 13 fork edits. | secure-phase L1 audit | 2026-11-21 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-21 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 diff & upstream-contract audit (found & closed `T-13-02` in `policy_gate.py`; `336 passed` in `tests/policy/` + `tests/ui/test_choice.py`; full suite `1562 passed, 11 deselected`; `ruff`, `xenon`, `lint-imports` clean) |
| 2026-11-21 | 11 | 11 | 0 | `gsd-secure-phase` delta re-audit across `51b15b6..c024329` (hardened `scenario_u3` HITL wait for `T-13-11`; `560 passed` in security/rig suites; full suite `1568 passed, 11 deselected`; `uv lock --check`, `ruff`, `xenon`, `lint-imports` clean; `git diff strands_code_agent/` empty) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-21
