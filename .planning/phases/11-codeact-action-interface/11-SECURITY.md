---
phase: "11"
slug: "codeact-action-interface"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-16"
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| model→sandbox | Generated code crosses into the stint interpreter | Code text; runs under the {math} allowlist + narrow functions |
| code-block→user | Generated code crosses to the human approver | Full block preview; one prompt per code action |
| turn→transcript | Interface records cross into history and display | Label strings; parallel list keeps them off cost rows |
| argv→session | CLI flags cross into session-start state | Interface choice; validated pre-gate with zero side effects |
| stint→turn | Stint interpreter crosses into the live turn | Swapped python_repl; restored in finally at the turn boundary |
| config→session | Persisted keys cross into session-start defaults | codeact choice + remember flag; fail-loud validation |

---

## Threat Register

Plan-authored register (11-01..11-04 `<threat_model>` blocks), consolidated to unique threats: 13 total, all verified against current source 2026-10-16. Note: 11-04 reused IDs T-11-01..T-11-03 for different components; they are recorded below as T-11-11..T-11-13 with the planner's IDs in parentheses.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-11-01 | Spoofing | turn label | low | mitigate | Exact `interface: tool/codeact` line pinned by label tests; `turn_interfaces` parallel list (loop.py:1891,1932) keeps records off cost rows | closed |
| T-11-02 | Tampering | config keys | low | mitigate | Fail-loud ValueError on unknown codeact values and non-bool remember flag in load/save (provider_config.py:83,86,104) | closed |
| T-11-03 | Spoofing | /codeact dispatch | low | mitigate | `codeact` in BUILTIN_SLASH_HEADS (skills.py:42) plus branch before the skills-dynamic branch (router.py:244); shadow warning automatic | closed |
| T-11-04 | Elevation | authorized imports | high | mitigate | CODEACT allowlist is exactly {math} (codeact.py:143) pinned by fail-closed import tests; capabilities ride narrow functions, never imports | closed |
| T-11-05 | Tampering | interior shell | high | mitigate | Argv-list subprocess only, no shell=True anywhere in codeact.py (verified by grep); command text visible in the approved block | closed |
| T-11-06 | Information disclosure | stint state | medium | mitigate | reset() on every interface switch (loop.py:2255) pinned by stint tests; stint interpreter separate from the tool-turn REPL; live-proven in UAT (NameError after switch) | closed |
| T-11-07 | Tampering | per-turn swap | medium | mitigate | Public replace() only (codeact.py:355-358), restore in finally (loop.py:2481-2485) pinned by exception test; no registry-dict mutation, no messages surgery | closed |
| T-11-08 | Tampering | preview render | medium | mitigate | Full-code Syntax preview (policy_gate.py:568) pinned by the 2000-char test; truncated preview cannot hide trailing malicious code; REVISE_HINT on denial (policy_gate.py:84,556) | closed |
| T-11-09 | Elevation | Always rules | medium | mitigate | Narrow derived rule for always/never, never tool="*" (policy_gate.py:371); denials never cover (existing fail-closed semantics kept) | closed |
| T-11-10 | Denial of service | approval fatigue | low | accept | Batch coverage already silences same-signature repeats (BatchState, policy_gate.py:114); one prompt per code action is the locked unit (D-05). See R-11-01. | closed |
| T-11-11 (11-04 T-11-01) | Tampering | _expand_bare_codeact argv rewrite | low | mitigate | Pure token-list rewrite: no shell, no eval, match restricted to the exact --codeact token, -- sentinel respected (main.py:246-280); helper cases pin every shape | closed |
| T-11-12 (11-04 T-11-02) | Spoofing | --codeact value validation | low | mitigate | Strict tool/code/both membership check kept byte-identical before the credential gate; invalid values rejected with zero side effects (existing test) | closed |
| T-11-SC | Tampering | supply chain | low | accept | Zero package installs this phase; pyproject.toml and uv.lock untouched across the Phase 11 commit range. See R-11-02. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-11-01 | T-11-10 | Batch dedup plus the user-locked one-prompt-per-action unit (D-05); residual fatigue risk negligible | secure-phase L1 audit | 2026-10-16 |
| R-11-02 | T-11-SC | Zero new dependencies added; nothing to gate — accepted as documented non-risk | secure-phase L1 audit | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-16 | 13 | 13 | 0 | secure-phase L1 grep audit (State B, short-circuit — plan-authored register, ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-16
