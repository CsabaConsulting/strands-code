---
phase: "05"
slug: "model-cost-context-commands"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-04"
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Idle prompt→model swap | /model resolves + validates at dispatch but swaps only in the loop at idle; mid-turn input gets the refusal reply, never a queue | Model selection (low) |
| History→new vendor | convert_history rewrites SDK ContentBlocks only; reasoning→text with warn, pairs byte-identical, trim at pair boundaries | Conversation incl. tool payloads (medium) |
| Discovery→selection | Bedrock control-plane reads fail soft to configured/custom; verbatim ids/ARNs; never escalate, never prompt for keys | Model catalog (low) |
| Keys→disk | API keys pass as client_args constructor kwargs at runtime only; ProviderConfig persists model string (+ non-secret base_url host) under 0o700 + atomic-replace + symlink-refusal; never credentials | Credentials (high, never persisted) |
| Summary→history | Auto/man compact summaries re-enter as marker-prefixed text (untrusted), never tool results; summarizer input credential-scrubbed best-effort | Conversation summaries (medium) |
| Spend→action | Cost paths are display-only; no value they compute can halt, deny, or redirect a turn | Token/cost figures (low) |
| Price APIs→cache | Bedrock Price List via ambient boto3 chain + keyless OpenRouter /models; 24h disk cache holds prices/windows only | Public price data (low) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Tampering | Mid-turn /model corrupts broker/approval state | high | mitigate | Idle-only swap: loop.py:455 MODEL_REFUSAL on turn_running; steering.py mid_turn_slash_reply refuses slash mid-turn, never arms | closed |
| T-05-02 | Tampering | Converted history loses tool calls | high | mitigate | Tool blocks deepcopy byte-identical (model_switch.py:337); trim only via pair-atomic _pair_safe_start (cost_context.py:443) | closed |
| T-05-03 | Tampering | reasoningContent resumes on non-reasoning target | high | mitigate | Strip to labeled trace + warn unless signed/redacted AND same-vendor AND harness-verified (model_switch.py:299); supports_reasoning defers to harness, fail-closed fallback (model_switch.py:140) | closed |
| T-05-04 | Tampering | Compact/clear corrupts resume blobs | medium | mitigate | compact_messages/clear_messages mutate agent.messages in place only; callers flush via explicit_save (loop.py:586,606) | closed |
| T-05-05 | Tampering | Thinking re-injected into forced-tool-choice turn | medium | mitigate | No toolChoice/tool_choice code anywhere in strands_code_cli — forced choice is never set, re-injection impossible; unsigned thinking stripped regardless (model_switch.py:310) | closed |
| T-05-06 | Tampering | Compact summary injects instructions via tool output | medium | mitigate | SUMMARY_MARKER untrusted prefix (cost_context.py:17); summary re-enters as plain text, never a tool result (cost_context.py:502); scrub_credentials pre-send (cost_context.py:391,399,412) | closed |
| T-05-07 | Spoofing | ARN prefix normalized → wrong model billed/invoked | medium | mitigate | normalize_model_ref strips only the ARN envelope, routing prefixes intact (model_switch.py:607); picker verbatim (model_switch.py:509); loop persists verbatim selection (loop.py:601) | closed |
| T-05-08 | Spoofing | Family-inferred window/pricing misleads switch | medium | mitigate | Id-substring tables + tokens-only fallback (cost_context.py:25,46,64); live layers are exact dict lookups (live_pricing.py:322,437,462); unknown window → convert, never force-compact (model_switch.py:584) | closed |
| T-05-09 | Spoofing | Pre-built Model instance skips validation | low | mitigate | No user-supplied Model instance path: router returns ("model", string) (router.py:393); apply_switch takes strings (model_switch.py:626); OpenAIModel built internally with base_url-only client_args (main.py:97) | closed |
| T-05-10 | Information disclosure | API key persisted to config.yaml or repo | high | mitigate | provider_config.py:95 persists model + non-secret base_url only (0o700, atomic, symlink refusal); api_key/bearer/secret hits are the defensive scrub regex + docstring only; OpenRouter fetch keyless, caches hold prices/windows only | closed |
| T-05-11 | Information disclosure | Discovery path prompts for or escalates credentials | medium | mitigate | discover_models catches all failures → (fallback, True); never escalates, never prompts, never raises (model_switch.py:390) | closed |
| T-05-12 | Information disclosure | New logging leaks spend/history onto agent-visible paths | low | mitigate | Zero logger/print/logging in model_switch.py, cost_context.py, live_pricing.py; model_capabilities.py logging is override-parse diagnostics only; console output is transcript echoes | closed |
| T-05-13 | Elevation | Cost display grows into budgets/enforcement | medium | mitigate | budget/enforce/halt/quota hits are display-only negations only (docstrings + footer cost_context.py:219); no enforcement logic | closed |
| T-05-14 | Elevation | /model smuggles auto-routing | medium | mitigate | auto.*rout/smart.*model grep over strands_code_cli/ empty; live-pricing source ordering is per-model-source fallback (cost_context.py:77), not model selection | closed |
| T-05-15 | Denial of service | Auto-compact thrashes or drops recent work | medium | mitigate | AUTO_COMPACT_PCT=80 (cost_context.py:19); maybe_auto_compact gates on threshold, skips unknown window (loop.py:181), pair-atomic keep-recent-verbatim + replay-last | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|

No accepted risks.

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-04 | 15 | 15 | 0 | gsd-security-auditor (generic-agent workaround) + orchestrator L1 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-04
