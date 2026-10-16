---
phase: "12"
slug: "structural-review-hygiene"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-16"
---

# Phase 12 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| registry→tree | New dev-tool packages cross into uv.lock | radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15, pinned |
| hook-repo→workstation | Pre-commit hook code crosses into developer runs | Official ruff hook repo pinned by tag; everything else local hooks |
| move→suite | Repackaged modules cross into the test gate | Pure-move commits; suite green at every commit proves behavior kept |
| docs→agent | Rewritten instructions cross into agent behavior | README/AGENTS.md/CONVENTIONS.md; grep-absence gates prove freshness |

---

## Threat Register

Plan-authored register (12-01..12-06 `<threat_model>` blocks), consolidated to unique threats: 14 total, all verified against current source 2026-10-16. Note: 12-06 reused ID T-11-01's successor slot T-12-01 for a different component; it is recorded below as T-12-13 with the planner's ID in parentheses.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-12-01 | Tampering | uv add of radon/xenon/ruff/import-linter | high | mitigate | Exact registry-verified names installed, pins recorded in uv.lock (radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15 — verified); CI syncs with --locked so artifacts cannot float | closed |
| T-12-02 | Denial of service | xenon/ruff gate configs | low | accept | Gates run offline via uv with no network; a misconfigured threshold fails loudly, never silently. See R-12-01. | closed |
| T-12-03 | Information disclosure | D-15 deletion | low | accept | Deletion removes code; no secrets involved; no dangling references (grep-verified empty). See R-12-02. | closed |
| T-12-04 | Tampering | package moves | medium | mitigate | Pure-move commits (0/0 purity, git-log verified) plus suite green at every commit; suite 1538 passed at phase end | closed |
| T-12-05 | Repudiation | checkpoint decision | low | accept | D-05 door choice recorded verbatim in 12-02-SUMMARY with auto-approval rationale under the user lock. See R-12-03. | closed |
| T-12-06 | Tampering | import rewrites | medium | mitigate | Plain-text grep completeness sweep (re-run: zero stale flat imports, zero stale attribute refs) plus suite green; entry smoke passes | closed |
| T-12-07 | Denial of service | console entry move | medium | mitigate | Atomic [project.scripts] update (strands_code_cli.entry.main:main, pyproject.toml:44) plus help smoke in the same step; UAT cold boot + a1 rig green on the moved entry | closed |
| T-12-08 | Tampering | scenario moves | low | accept | Bodies move verbatim; live a1 PASS plus re-homed assertions prove behavior identical. See R-12-04. | closed |
| T-12-09 | Denial of service | thin driver dispatch | low | accept | Identical command surface plus usage string; contract tests pin both. See R-12-05. | closed |
| T-12-10 | Tampering | pre-commit hook repos | high | mitigate | Only the official ruff hook repo pinned by tag (v0.17.1, == locked ruff); xenon and lint-imports run as local hooks — verified, no third-party hook repos added | closed |
| T-12-11 | Elevation of privilege | gate bypass via local flags | medium | mitigate | The CI workflow (gates.yml: pytest + ruff + xenon + lint-imports) is the blocking authority, not local hooks; local bypass cannot merge green | closed |
| T-12-12 | Information disclosure | CI logs | low | accept | Gate output is complexity and lint findings over public code; no secrets in configs; minimal workflow permissions (contents: read). See R-12-06. | closed |
| T-12-13 (12-06 T-12-01) | Tampering | AGENTS.md / CONVENTIONS.md example lines | low | mitigate | Exact-string acceptance criteria plus grep-absence gates (re-run: 0 matches for OKFBundle/GitHub loop/flat paths) and full re-read of both files | closed |
| T-12-SC | Tampering | supply chain | low | accept | Only 12-01 installs (4 dev tools, T-12-01); all other plans install-free. See R-12-07. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-12-01 | T-12-02 | Offline gates fail loudly on misconfiguration; no silent-degrade path | secure-phase L1 audit | 2026-10-16 |
| R-12-02 | T-12-03 | Deletion-only change with grep-proven zero dangling references | secure-phase L1 audit | 2026-10-16 |
| R-12-03 | T-12-05 | Checkpoint rationale recorded verbatim in SUMMARY for audit | secure-phase L1 audit | 2026-10-16 |
| R-12-04 | T-12-08 | Verbatim moves proven by live rig run + re-homed assertions | secure-phase L1 audit | 2026-10-16 |
| R-12-05 | T-12-09 | Identical surface pinned by contract tests | secure-phase L1 audit | 2026-10-16 |
| R-12-06 | T-12-12 | Public-code findings, minimal permissions, no secrets | secure-phase L1 audit | 2026-10-16 |
| R-12-07 | T-12-SC | Single reviewed install plan; nothing else added | secure-phase L1 audit | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-16 | 14 | 14 | 0 | secure-phase L1 grep audit (State B, short-circuit — plan-authored register, ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-16
