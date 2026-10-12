---
phase: "09"
slug: "native-typesafe-decision-engine"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-12"
---

# Phase 09 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Repo strategy file ↔ loader/chain | Operator-editable YAML crosses into engine order and model strings | `order` list, `native_model`, candidates; untrusted input |
| CLI ↔ TypeSafe native API | Decision calls cross to a new third-party endpoint | Truncated ask + directives + criteria; API key header-only |
| Setup stdin ↔ strategy file | Typed engine names and model ids cross into the saved file | Engine names, Jev model ids; never key material |
| Validate ping ↔ native API | Live ping crosses to the endpoint with the env key | Minimal decision call; key header-only, results mapped to notes |
| Probe runner ↔ native API | Live decision calls cross with the env key | Fixed labeled asks; key header-only; fault probes use bogus key |
| Probe records ↔ run files | Verdict JSONL crosses into /tmp and the baseline file | Asks, tables, snapshots; never secrets |
| Rig ↔ shell | Scenario runs cross into tmux panes with the ambient environment | Rendered transcript; fail-fast echoes one failed line locally |
| Hook ↔ transcript/cost | Skip notes + computed spend cross into user-visible output | Notes, token counts, computed cost; never keys |

---

## Threat Register

Plan-authored register (09-01..09-03 `<threat_model>` blocks): 5 unique threats, all verified against current source 2026-10-12.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-9-01 | Information disclosure | decide_via_typesafe, _failure_reason, validate ping, run records | medium | mitigate | Key read at call time inside engine fn only (routing.py:1320), header-only (routing.py:1274,1330,1378); presence check reads env without storing (routing.py:1417,1693); failure classes never carry bodies or headers; validate ping maps HTTP classes to notes, no key echo (router.py:1242); fault probes use bogus key and restore byte-identically (route-probe.py:33,254,264); records carry tables and snapshots, never secrets | closed |
| T-9-02 | Information disclosure | save_strategy, setup payload, live tests, rig | medium | mitigate | Setup never prompts for keys — 'TypeSafe key' phrasing only (router.py:1022-1041,1124); saved file drops secret-shaped keys (routing.py:456,509-522); live tests and rig read the key from the ambient env at call time and assert snapshots/token counts, never key material | closed |
| T-9-03 | Tampering | build_decision_state, _fit_decision_payload, order builder, pinned pick, baseline.json | medium | mitigate | Ask plus directives truncated with body cap fit (Phase 8 machinery, reused unchanged); order entries validated against the available set with fail-closed abort (routing.py:276,681,847); native ids constrained to the two verified strings (routing.py:55,58 NATIVE_JEV_PIN/NATIVE_JEV_ALIAS); native baseline section mirrors the openrouter record shape with compare failing loudly on drift | closed |
| T-9-04 | Tampering | validate_choice_answer, gate_model, engineless fallback | low | mitigate | Shared membership validation plus top-1-probability gate consume native tables unchanged; stale choices hold; empty or keyless orders degrade to hold-current with notes, never to a guessed engine (single-user CLI, no privilege boundary crossed) | closed |
| T-9-SC | Tampering | supply chain | low | accept | Zero package installs this phase — stdlib urllib plus locked deps; pyproject.toml and uv.lock untouched by every Phase 9 commit (f2f55da..HEAD range clean). See R-09-01. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-09-01 | T-9-SC | Zero new dependencies added; nothing to gate — accepted as documented non-risk | secure-phase L1 audit | 2026-10-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-12 | 5 | 5 | 0 | secure-phase L1 grep audit (State B, short-circuit — plan-authored register, ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-12
