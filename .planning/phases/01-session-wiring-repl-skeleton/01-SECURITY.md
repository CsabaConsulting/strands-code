---
phase: "01"
slug: "session-wiring-repl-skeleton"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-24"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| argv→CLI (`--session-id`) | Untrusted CLI input flows into the SDK session identifier | Session id string (untrusted) |
| picker selection→session load | User-chosen index entry resolves to snapshot state on disk | Index entry → snapshot path |
| `/rename` input→sidecar index | Freeform rename text is written to the JSON index | Rename string (untrusted) |
| auto-title prompt→model | First-exchange content is sent to the model for titling | User-typed first exchange |
| REPL input→agent | Freeform user text becomes agent content, never executed by the CLI | Ask text (untrusted) |
| credential probe→boto3 chain | Ambient credentials are touched read-only, never handled in code | Exception type names only |
| config file→CLI | User-editable YAML flows into model construction | Provider string |
| exit path→snapshot store | Final flush writes whole-agent state to disk | Agent snapshot |
| snapshot files at rest | Conversation data (may contain secrets) sits on local disk | Transcripts, history |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering | main.py `--session-id` handling | high | mitigate | SDK `validate_identifier` + `typer.BadParameter` usage errors at both entry points; negative test `--session-id ../../x` | closed |
| T-01-02 | Tampering | session snapshot files | medium | mitigate | Symlink refusal in session_index + provider_config; 0o700 session/index/config dirs | closed |
| T-01-03 | Information disclosure | session dir + REPL history at rest | medium | mitigate | 0o700 session/index/cache dirs; history file 0o600 (`loop.py` + `tests/test_repl_history.py`); never log transcript content | closed |
| T-01-04 | Spoofing | resumed transcript | low | accept | Resumed content trusted-to-self in Phase 1; prompt-injection hardening is Phase 3 scope | closed |
| T-02-01 | Tampering | router.py `/rename` value | high | mitigate | Rename validation (no separators/blanks, 120-char cap); titles sidecar-only, never filenames | closed |
| T-02-02 | Tampering | picker index join | medium | mitigate | Sidecar index treated as untrusted: fail-soft corrupt JSON, ignore entries without snapshots | closed |
| T-02-03 | Information disclosure | auto-title prompt | low | accept | Title call sends only the already-typed first exchange; no added context | closed |
| T-03-01 | Information disclosure | provider_config.py / first_run.py | high | mitigate | Never log credential material; config holds provider string only; static setup pointer | closed |
| T-03-02 | Tampering | provider config file | medium | mitigate | Unknown-key rejection, fail-soft malformed YAML, symlink refusal | closed |
| T-03-03 | Denial of service | exit-flush path | low | accept | Best-effort flush over per-message saves; failed flush still leaves per-message state | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-01 | T-01-04 | Phase 1 trusts resumed content to self; injection hardening deferred to Phase 3 permissions | Csaba (discuss-phase D-record) | 2026-09-23 |
| R-02 | T-02-03 | Auto-title unavoidably sends the first exchange to the model; nothing beyond it is attached | Csaba (discuss-phase D-record) | 2026-09-23 |
| R-03 | T-03-03 | Exit flush best-effort; per-message saves bound the loss window to one turn | Csaba (discuss-phase D-record) | 2026-09-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-24 | 10 | 9 | 1 | gsd-security-auditor (T-01-03 history perms open) |
| 2026-09-24 | 10 | 10 | 0 | orchestrator fix-first: history chmod + tests/test_repl_history.py |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-24
