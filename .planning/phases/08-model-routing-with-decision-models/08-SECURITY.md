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
| User ↔ CLI | Strategy files (global + repo), `/route` slashes, `/model` override | Candidate lists, directives, engine choice; repo file is untrusted input |
| CLI ↔ OpenRouter | Decision-model API + catalog fetch | Ask text (truncated), directives, candidate table; API key in header |
| CLI ↔ local Ollama | Localhost decision engine | Same prompt content; no key material on loopback |
| Router ↔ model provider | Routed switch via switch machinery | Model id + thinking level applied pre-turn |
| CLI ↔ transcript/cost | Routing notes + Routing cost section | Model, why, cost impact per routed ask |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Tampering | routing.py | medium | mitigate | `parse_pick` verbatim candidate-id match (:926) + advertised-levels membership (:932); single parse choke for both engines (:1057) | closed |
| T-08-02 | Information disclosure | routing.py / loop.py | medium | mitigate | `ASK_TRUNCATE_CHARS=2000` (:39), `ask[:2000]` (:720), ask-only prompt args; `ask_text=text` raw line (loop.py:2144, WR-02 fix confirmed) | closed |
| T-08-03 | Elevation of privilege | loop.py / router.py | medium | mitigate | `apply_model_action(turn_running=False)` pre-turn (:1437-1444, hook :2138 before retry loop); warn choke (router.py:207-209, :534-577); MODEL_REFUSAL intact (:1225-1226) | closed |
| T-08-04 | Tampering | model_switch.py / routing.py | medium | mitigate | `resolve_model` raises before `agent.model` assign (:651-657); status names source (:1197-1200); warn-and-skip (:114-168), unknown keys never widen | closed |
| T-08-05 | Denial of service | routing.py | low | mitigate | `DECISION_TIMEOUT_SECONDS=10` (:42), one attempt per engine (:1049-1062), no retry; failures hold, turn proceeds | closed |
| T-08-06 | Spoofing | routing.py | low | mitigate | Scheme allowlist (:170-178), warn-and-default at load (:212-222), call-time re-check (:861); loopback never carries key, Bearer [REDACTED] for proxied (:824-836) | closed |
| T-08-07 | Tampering | routing.py | medium | mitigate | Declared "directives delimited + length-bounded": delimiting present (`User directives:` header :714), catalog exclusion present (:679-696), exact-id constraint present (:672-676 + parse_pick). Length bound MISSING — no slice/cap in `build_routing_prompt` (:699-721), `_parse_strategy` (:226-258), or setup capture (router.py:849-874). A malicious repo strategy can inject unbounded directive text into the paid call. Fix: truncate directives (e.g. to ASK_TRUNCATE_CHARS) in `build_routing_prompt`. | open — below high threshold (non-blocking) |
| T-08-08 | Information disclosure | loop.py / cost_context.py | medium | mitigate | Routing event on all 5 hook outcomes (:1370,:1387,:1419,:1447,:1483) + all side outcomes; Routing section + decision spend in totals (:257-281); wiring (router.py:122-123,271) | closed |
| T-08-09 | Information disclosure | routing.py | high | mitigate | Key read at call time inside engine fn only (:767); header-only, constant URL (:787); no key in logs; save drops secret keys; setup has no key prompt | closed |
| T-08-10 | Information disclosure | routing.py / router.py | high | mitigate | Drops api_key-shaped keys top-level + engine with warning (:360-377); setup prompts scope/engine/candidates/decision/local/directives only (:877-956) | closed |
| T-08-11 | Tampering | router.py | medium | mitigate | `fetch_openrouter_models` (:908); field-by-field isinstance + float guards (:599-647); chat-capable filter (:608-622), skips unknown; typed-id fallback, never raises (:907-928) | closed |
| T-08-12 | Information disclosure | docs/ROUTING.md | low | accept | "Starting points only" (:42), written dates (:49/:66), re-validate pointers (:44/:115); conditions hold. See R-08-01. | closed |
| T-08-SC | Tampering | supply chain | high | accept | pyyaml/prompt-toolkit/platformdirs declared (pyproject.toml:33-36), untouched by Phase 8; stdlib urllib only (:765,:856). See R-08-02. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-08-01 | T-08-12 | Doc examples are labeled starting points with dates; setup enumerates the live catalog and validate judges the real file, so stale docs cannot silently misconfigure. | secure-phase audit (generic-agent workaround) | 2026-10-11 |
| R-08-02 | T-08-SC | Phase 8 added no new dependencies (stdlib urllib + already-declared pyyaml/prompt-toolkit/platformdirs); legitimacy gate not triggered. | secure-phase audit (generic-agent workaround) | 2026-10-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-11 | 13 | 12 | 1 (T-08-07, non-blocking medium) | gsd-security-auditor via generic-agent workaround (typed dispatch unavailable) — plan-driven audit, ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-11
