---
phase: "10"
slug: "provider-reported-turn-spend"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-13"
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| provider-stream→CLI | OpenRouter/LiteLLM Usage objects cross into format_chunk capture | Numeric `cost` float only; untrusted input |
| turn-row→display | Stored reported_cost floats render into usage lines and /cost | Floats already held in memory; never payloads or keys |
| agent→model drain | Main-turn call sites resolve the serving model before draining | Model reference; drain reads take_reported_costs only |
| wrap→drain discipline | Instances enter per-turn drain discipline at promotion time | Per-instance cost list; discarded once at wrap |
| main-agent→side-agent | Model instances cross into side builds via kwargs replay | Fresh wrapper per side build; never the parent instance |
| test→provider | Keyed live proof sends one minimal turn to OpenRouter | Minimal prompt; key header-only from ambient env |

---

## Threat Register

Plan-authored register (10-01..10-05 `<threat_model>` blocks), consolidated to unique threats: 8 total, all verified against current source 2026-10-13.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-10-01 | Tampering/Denial | _extract_cost / format_chunk capture | medium | mitigate | Bool-safe numeric extractor plus math.isfinite gate (reported_cost.py:25-27); NaN/Inf/-Inf capture as absent; fail-soft capture never raises into the stream (reported_cost.py:54-55); worst case is the D-05 estimate display | closed |
| T-10-02 | Tampering | drain attribution: serving model, fresh wrappers, drain-once, actual-wins | medium | mitigate | Serving-model lookup at both drain sites (loop.py:827,839) plus nested-model fallback; fresh wrapper per agent construction and per side build (reported_cost.py:113, btw.py:428); take resets the list so each cost drains once (reported_cost.py:59-62); pre-discipline accumulation discarded once at wrap (reported_cost.py:109, D-09); actual-wins per row with is-not-None checks so each turn counts exactly once and estimates never pose as actuals | closed |
| T-10-03 | Information disclosure | cost capture / row storage / display | low | accept | Capture records only the numeric float — never payloads, headers, generation ids, or keys; no new logging; display renders floats already held in memory. See R-10-01. | closed |
| T-10-04 | Information disclosure | live proof test credentials | low | accept | Key read from env at call time only (test_reported_cost.py:539-541), header-only transport, never logged or persisted; follows the Phase 8/9 live-test precedent. See R-10-02. | closed |
| T-10-05 | Tampering | _composed_class inheritance shape | medium | mitigate | Single-inheritance composed class (reported_cost.py:37) with __slots__ = () (reported_cost.py:40) so __class__ promotion succeeds on the real slotted SDK chain; pinned by TestRealSdkPromotion with dummy client_args and zero network I/O | closed |
| T-10-06 | Information disclosure | Fail-soft promotion masking (WR-01 swallowing TypeError) | low | mitigate | The silent-failure vector on the production class is removed by T-10-05 (promotion now succeeds); the D-05 choke-point except (reported_cost.py:104) stays for genuinely unknown shapes, preserving the display-only posture | closed |
| T-10-07 | Information disclosure | Dummy credential in the regression test | low | mitigate | Test uses only the bogus literal probe-dummy-key (test_reported_cost.py:504,512) and performs zero network I/O; the real key is read from the environment at call time by the live test only | closed |
| T-10-SC | Tampering | supply chain | low | accept | Zero package installs this phase — stdlib (math) plus locked deps; pyproject.toml and uv.lock untouched across the Phase 10 commit range (092a263..HEAD clean). See R-10-03. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-10-01 | T-10-03 | Numeric-float-only capture with no new logging or persistence; residual disclosure risk negligible | secure-phase L1 audit | 2026-10-13 |
| R-10-02 | T-10-04 | Env-at-call-time key handling follows the established Phase 8/9 live-test precedent | secure-phase L1 audit | 2026-10-13 |
| R-10-03 | T-10-SC | Zero new dependencies added; nothing to gate — accepted as documented non-risk | secure-phase L1 audit | 2026-10-13 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-13 | 8 | 8 | 0 | secure-phase L1 grep audit (State B, short-circuit — plan-authored register, ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-13
