---
phase: "07"
slug: "subagents-btw-side-channel"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-11"
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| User terminal ↔ CLI | prompt_toolkit dialogs (approvals, cancel chooser), stdin keystrokes | Approval decisions, cancel targets; untrusted key bytes |
| Main agent ↔ side (/btw) agent | Forked history, shared tagged policy gate, parallel turns | Forked messages, tool requests tagged main/btw |
| Agent ↔ tools | shell / write / python_repl via HumanInTheLoop gate | Tool inputs; command strings, file paths, code |
| Agent ↔ model provider | Bedrock model calls for main and side turns | Prompts, forked history, completions |
| Agent ↔ memory files | `.agent/MEMORY.md` + memory shards | Recall-only context for side channel (no write path) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-07-01 | Elevation of privilege | policy_gate.py / btw.py | high | mitigate | Sole HumanInTheLoop construction (policy_gate.py:687); shared interventions list (main.py:151); btw kwargs replay without interventions override (btw.py:421-442) | closed |
| T-07-02 | Denial of service | btw.py / loop.py | medium | mitigate | RENDER_LOCK (btw.py:36); LockedHandler + fenced atomic blocks (btw.py:104,129-134); main wrapped (main.py:156); workers never open output context | closed |
| T-07-03 | Tampering | btw.py / loop.py | medium | mitigate | Fork deep-copies, drops unanswered toolUse, strips reasoningContent, preserves role alternation (btw.py:192-221); reap never touches messages (loop.py:321-339); append-back at main-thread boundary only (loop.py:599,830) | closed |
| T-07-04 | Spoofing | policy_gate.py | high | mitigate | tag_for from event.agent identity (policy_gate.py:84-93); thread-local + tag-keyed stash, ask reads own context (policy_gate.py:96-102,402,506-512,527-528) | closed |
| T-07-05 | Elevation of privilege | policy_gate.py | high | mitigate | Coverage keyed on (tag, signature) (policy_gate.py:128-139); only approvals cover, denials record-only (policy_gate.py:504,612,639); trust_delegated btw auto-trust announced (policy_gate.py:493-497) | closed |
| T-07-06 | Denial of service | policy_gate.py / loop.py | medium | mitigate | Per-tag cancel registry (policy_gate.py:280-298); btw/main registration (btw.py:246, loop.py:665); chooser sets only named targets (loop.py:206-250); handler sets nothing while both run (loop.py:916-928) | closed |
| T-07-07 | Tampering | btw.py / loop.py | medium | mitigate | Unbounded FIFO with blank rejection (btw.py:255-295); single main-thread spawn site (loop.py:437-467); single-worker side pool (loop.py:395,1623); spawn only when no side live (loop.py:488,499) | closed |
| T-07-08 | Denial of service | loop.py | medium | mitigate | Sequential suspend-serve-re-issue, no nesting (loop.py:759-791); idle prints via print_plain under pump ownership (loop.py:833,836) | closed |
| T-07-09 | Denial of service | policy_gate.py | high | mitigate | Pump nesting depth counter; inner exit restores outer pump (policy_gate.py:259,269,276-278) | closed |
| T-07-10 | Elevation of privilege | btw.py | high | mitigate | ONLY framing + do-not-perform preamble (btw.py:63-83); BTW_INFLIGHT_MARKER on trailing user turn (btw.py:214-217); backstop T-07-01 (every btw mutation still gated) | closed |
| T-07-11 | Denial of service | policy_gate.py / loop.py | high | mitigate | Request carries cancel + abort() (policy_gate.py:184-209); dead-tag drain via _poll_live (loop.py:253-270) applied at all serve sites (loop.py:502,540,688,783) | closed |
| T-07-12 | Information disclosure | policy_gate.py / loop.py | medium | mitigate | worker_cancelled unwraps EventLoopException chains (policy_gate.py:164-178); fenced "Cancelled by user" (loop.py:333-335); cancel-path mapping (loop.py:590,684,1412,1770) | closed |
| T-07-13 | Denial of service | loop.py | low | mitigate | Ack-before-join in cancel branches (loop.py:519,557,574) | closed |
| T-07-14 | Spoofing | policy_gate.py / choice.py | medium | mitigate | Dialog title carries tag + tool + detail (policy_gate.py:658-672); threaded into radio_choice (policy_gate.py:558-560) | closed |
| T-07-15 | Denial of service | loop.py | high | mitigate | Serve-at-idle via FIRST_COMPLETED (loop.py:759-791); drain + announce-once remnant for race sliver (loop.py:794-839) | closed |
| T-07-16 | Denial of service | loop.py / choice.py | high | mitigate | Fresh loop per episode, strictly sequential serve, never nested (loop.py:759-791); dialog owns termios, Ctrl-C re-raises after restore (choice.py:189-196) | closed |
| T-07-17 | Information disclosure | btw.py / loop.py | medium | mitigate | Fenced dropped-side note (btw.py:150-162; loop.py:842-854); from_exit suppresses next-turn promise (loop.py:835,1885-1888) | closed |
| T-07-18 | Denial of service | steering.py / choice.py | medium | mitigate | Reentrant StdinGuard (steering.py:66-122); radio_choice choke-point hold (choice.py:174-196); chooser hold (loop.py:231); ask hold (policy_gate.py:54,573,580); reader polls held() (steering.py:429,441,479) | closed |
| T-07-19 | Elevation of privilege | choice.py | high | mitigate | clear_typeahead on dialog entry, kernel bytes untouched (choice.py:176-182); covers all mid-turn dialogs via radio_choice choke point | closed |
| T-07-20 | Elevation of privilege | policy_gate.py / choice.py / loop.py | high | mitigate | Deny-first on every prompt path: missing context → "n" (policy_gate.py:532-533); ask exception → "n" (584-586); ESC/None → "n" (602-604); broken dialog → None, Ctrl-C re-raises (choice.py:190-193); unanswered → TurnCancelled (policy_gate.py:225-226); idle Ctrl-C → abort + cancel (loop.py:788-790); chooser no-choice cancels nothing (loop.py:212-218,521-523) | closed |
| T-07-21 | Tampering | btw.py | medium | mitigate | resolve_memory writable=False recall-only share (btw.py:429-439); injector-only plugin registration, no fact-store/curate write path (btw.py:443) | closed |
| T-07-22 | Spoofing | btw.py / loop.py | medium | mitigate | Every side message fenced (btw.py:124-135); error/cancel/drop fenced (btw.py:138-175); history append carries "/btw" identity (btw.py:224-236; loop.py:599,830) | closed |
| T-07-23 | Repudiation | policy_gate.py | low | mitigate | [tag]-prefixed batch log for /policy last on both agents (policy_gate.py:543,546,612,622,635,637,639) | closed |
| T-07-SC | Tampering | supply chain | high | accept | No package installs in Phase 7: btw.py/loop.py/choice.py/steering.py import only stdlib + already-declared strands/rich/prompt_toolkit; legitimacy gate not triggered. See R-07-01. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-07-01 | T-07-SC | Phase 7 added no new dependencies (stdlib + already-declared strands/rich/prompt_toolkit only); supply-chain review deferred to phases that introduce packages. | secure-phase audit (generic-agent workaround) | 2026-10-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-11 | 24 | 24 | 0 | gsd-security-auditor via generic-agent workaround (typed dispatch unavailable) — retroactive-STRIDE mode, ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-11
