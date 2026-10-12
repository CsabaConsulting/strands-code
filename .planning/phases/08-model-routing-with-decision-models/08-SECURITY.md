---
phase: "08"
slug: "model-routing-with-decision-models"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-11"
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Repo strategy file ↔ loader | Operator-editable YAML crosses into routing; entries are untrusted input | Candidates, directives, knobs, pins; repo wins whole-file |
| CLI ↔ OpenRouter | Decision-model API + catalog fetch | Truncated ask + directives + criteria; API key header-only |
| CLI ↔ local Ollama | Localhost decision engine + preflight | Same payload; no key material on loopback |
| Vendor answer ↔ choice gate | Untrusted JSON crosses into membership tests | Typed tables; malformed holds, never routes |
| Hook ↔ switch machinery | Routed model id + level applied pre-turn at idle | Validated pick only |
| CLI ↔ transcript/cost | Routing notes + decision spend | Choice, confidences, tokens, reported cost; never keys |
| Probe runner ↔ live engines | Fixed labeled asks leave the machine (cloud path only) | Asks, tables, snapshots; never secret values |

---

## Threat Register

Plan-authored register (08-01..08-06 `<threat_model>` blocks): 21 unique threats, all verified against current source 2026-10-12.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-21 | Tampering | validate_choice_answer | high | mitigate | `_validate_choice_shape` type/probs-range/sum/str-choice checks (routing.py:1289-1316) + live-candidate membership (routing.py:1319-1337); effort inherits (routing.py:1340-1350); stale/malformed holds | closed |
| T-08-22 | Information disclosure | decide_via_openrouter | high | mitigate | Key read at call time inside engine fn only (routing.py:1104), header-only (routing.py:1114), constant URL (routing.py:46,1111); no key in logs/details (grep clean); save drops secret keys (routing.py:404-476) | closed |
| T-08-23 | Tampering | build_decision_state | medium | mitigate | Ask + directives each truncated to ASK_TRUNCATE_CHARS (routing.py:821-833); stats stay code-side; shaping truncated in both question builders (routing.py:860,897) | closed |
| T-08-24 | Denial of service | decide_via_openrouter | low | mitigate | `DECISION_TIMEOUT_SECONDS=10` (routing.py:43); `_post_decision` one retry on retryable codes/timeouts only (routing.py:1058-1084,957-971); every failure holds | closed |
| T-08-25 | Spoofing | decide_via_ollama | low | mitigate | `_valid_base_url` http(s)+host (routing.py:239-248); load-time check (routing.py:281-291) + call-time re-check (routing.py:1252); loopback never carries key (routing.py:1150-1162) | closed |
| T-08-26 | Tampering | build_effort_question | medium | mitigate | Criteria from picked candidate's live levels only with fixed code-side map + bare-name fallback (routing.py:870-909); never operator prose | closed |
| T-08-27 | Elevation of privilege | decide fast path | medium | mitigate | Lone-candidate branch validates effort answer + level membership (routing.py:1648-1660,1535-1601); unparseable call-2 holds (routing.py:1690-1697) | closed |
| T-08-28 | Information disclosure | _route_side_spawn | low | mitigate | Side decide with same truncated state, side=True (loop.py:657-660); side holds silent but every side decision appends an audited event | closed |
| T-08-29 | Denial of service | decide transports | medium | mitigate | Timeout + single retry retryable-only (T-08-24 machinery); preflight failures yield the inert unready link — zero POSTs (routing.py:1516-1519) | closed |
| T-08-30 | Tampering | local_engine_ready | low | mitigate | Any transport/parse failure returns False (routing.py:1190-1228); chain treats unready as skip, never ready | closed |
| T-08-31 | Information disclosure | format_hold_line | low | mitigate | `_link_detail` names engine + numeric code/class only (routing.py:1464-1481); `_failure_reason` fixed classes (routing.py:991-1018); debug logs snapshot only; keys never rendered | closed |
| T-08-32 | Tampering | body-size guard | medium | mitigate | `_fit_decision_payload` measures serialized length + tightens ask (routing.py:1021-1048), called by both transports (routing.py:1107,1254). Residual: criteria/directives cannot shrink — ask-exhausted oversize still ships, server 413s, holds fail-safe | closed |
| T-08-33 | Tampering | _setup_decision_entries | medium | mitigate | Field-by-field isinstance guards; alias + zero-context entries dropped; modalities must include decisions; hostile payload yields shorter list, never raises (router.py:650-710) | closed |
| T-08-34 | Information disclosure | _route_setup_message | high | mitigate | Prompts cover scope/engine/candidates/decider/local/directives only, never key prompts (router.py:944+); saved file drops secret-shaped keys (routing.py:453-476) | closed |
| T-08-35 | Tampering | docs/ROUTING.md | low | accept | "Starting points only" + written dates (ROUTING.md:52,59,85); setup enumerates live catalogs, validate judges the real file. See R-08-03. | closed |
| T-08-36 | Information disclosure | route-probe.py | medium | mitigate | Key from env at call time via production transports (header-only, never logged); fault probes use bogus key (route-probe.py:240-248); JSONL/baseline carry asks+tables+snapshots, never secrets (route-probe.py:30-33,333-345) | closed |
| T-08-37 | Tampering | baseline.json | low | mitigate | Baseline is a reviewed repo file; compare exits nonzero on drift, exit 2 on missing baseline (route-probe.py:588-610) | closed |
| T-08-38 | Tampering | TestLiveEngines | low | mitigate | Live tests integration-marked + env-gated (test_routing.py:2462,2504); assert typed shape + snapshot + positive cost; present-but-broken fails loudly, never skips (test_routing.py:2486-2502) | closed |
| T-08-39 | Tampering | _candidate_skip_reason + _parse_candidate | low | mitigate | Bool fold covers levels entries only, `is True/False` identity excludes ints (routing.py:171-227); validate_strategy reports through the shared gate so reports stay truthful | closed |
| T-08-40 | Denial of service | _validate_choice_shape + validate_choice_answer | low | mitigate | Non-string choice returns None and holds (routing.py:1314,1335); no TypeError escapes; effort inherits via shared check (routing.py:1347); pinned by TestUnhashableChoiceHolds | closed |
| T-08-SC | Tampering | supply chain | high | accept | Zero new dependencies (stdlib urllib only; pyproject untouched by Phase 8); promptfoo optional with compare-mode fallback (route-probe.py:17-28). See R-08-04. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Superseded Register (chat-JSON era)

T-08-01..T-08-12 (audited 2026-10-11 against the chat-completions-JSON implementation) are retired: the Decision-API rework removed the cited surface (`parse_pick`, `build_routing_prompt`, `OPENROUTER_CHAT_URL`, `why` prose — confirmed absent by the 08-REVIEW grep). Each is subsumed by a current-register threat:

| Retired ID | Subsumed By | Note |
|------------|-------------|------|
| T-08-01 (verbatim pick match) | T-08-21 | Typed validation + live-membership replaces parse_pick |
| T-08-02 (ask truncation) | T-08-23 | Truncation now covers ask + directives in state builders |
| T-08-03 (pre-turn apply) | T-08-27 | Fast-path validation; hook ordering unchanged |
| T-08-04 (resolve before assign) | T-08-21 | Stale-pick hold via live membership |
| T-08-05 (timeout, no retry) | T-08-24, T-08-29 | One-retry-on-retryable policy (behavior change, verified) |
| T-08-06 (scheme allowlist) | T-08-25 | Same allowlist + call-time re-check on the new endpoint |
| T-08-07 (directive bound) | T-08-23 | Fixed: directives truncated in state + both questions |
| T-08-08 (routing events/spend) | T-08-28, T-08-31 | Events carry tokens + reported cost, never keys |
| T-08-09 (call-time key) | T-08-22 | Same control on the new transport |
| T-08-10 (save drops secrets) | T-08-22, T-08-34 | Same control, re-verified |
| T-08-11 (catalog guards) | T-08-33 | Split-catalog guards incl. decisions listing |
| T-08-12 (doc staleness) | T-08-35 | Re-labeled examples, re-verified |

Retired threats do not resurface in future audit runs.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-08-01 | T-08-12 (retired) | Chat-era doc-acceptance; superseded by R-08-03. | secure-phase audit (generic-agent workaround) | 2026-10-11 |
| R-08-02 | T-08-SC (chat-era) | Chat-era supply-chain acceptance; superseded by R-08-04. | secure-phase audit (generic-agent workaround) | 2026-10-11 |
| R-08-03 | T-08-35 | Doc examples are labeled starting points with dates; setup enumerates the live catalogs and validate judges the real file, so stale docs cannot silently misconfigure. | secure-phase audit (generic-agent workaround) | 2026-10-12 |
| R-08-04 | T-08-SC | Phase 8 added no new dependencies (stdlib urllib + already-declared pyyaml/prompt-toolkit/platformdirs); promptfoo is optional with a built-in compare fallback, so no install-channel risk lands in-repo. | secure-phase audit (generic-agent workaround) | 2026-10-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-11 | 13 | 12 | 1 (T-08-07, non-blocking medium) | gsd-security-auditor via generic-agent workaround (typed dispatch unavailable) — plan-driven audit, ASVS L1, block_on high |
| 2026-10-11 | 13 | 13 | 0 | Gap fix: directives truncated to ASK_TRUNCATE_CHARS in `build_routing_prompt` + `test_prompt_truncates_long_directives` (suite 1067 passed) |
| 2026-10-12 | 21 | 21 | 0 | gsd-security-auditor via generic-agent workaround (typed dispatch unavailable) — Decision-API rework re-audit: retired T-08-01..T-08-12, verified T-08-21..T-08-40 + T-08-SC against current source, ASVS L1, block_on high; routing suite 306 passed / 2 deselected (integration) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-12
