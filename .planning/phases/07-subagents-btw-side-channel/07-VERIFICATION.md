---
phase: 07-subagents-btw-side-channel
verified: 2026-10-06T09:00:00Z
status: human_needed
score: 11/11 must-haves verified
covered_files:
  - .planning/phases/07-subagents-btw-side-channel/07-01-PLAN.md
  - .planning/phases/07-subagents-btw-side-channel/07-02-PLAN.md
  - .planning/phases/07-subagents-btw-side-channel/07-03-PLAN.md
  - .planning/phases/07-subagents-btw-side-channel/07-01-SUMMARY.md
  - .planning/phases/07-subagents-btw-side-channel/07-02-SUMMARY.md
  - .planning/phases/07-subagents-btw-side-channel/07-03-SUMMARY.md
  - .planning/phases/07-subagents-btw-side-channel/07-REVIEW.md
  - .planning/phases/07-subagents-btw-side-channel/07-REVIEW-FIX.md
  - .planning/REQUIREMENTS.md
  - strands_code_cli/btw.py
  - strands_code_cli/loop.py
  - strands_code_cli/steering.py
  - strands_code_cli/main.py
  - strands_code_cli/router.py
  - strands_code_cli/skills.py
  - strands_code_cli/policy_gate.py
  - strands_code_cli/diff_gate.py
  - tests/test_btw.py
  - tests/test_router_btw.py
  - tests/test_policy_gate.py
  - tests/test_broker.py
  - tests/test_plan_cancel.py
  - tests/test_cost_context.py
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Start a long main task, fire /btw needing approval, let main finish first"
    expected: "Tagged [btw] prompt is announced at idle ('btw approval needed — will prompt when the next turn starts.') and served by the next turn's pump; fenced block lands without scrambling the prompt line"
    why_human: "Bounded-wait idle choreography + cursor behavior are inherently live-terminal (07-VALIDATION Manual-Only, D-11)"
  - test: "Run main + btw concurrently, press Ctrl-C once"
    expected: "Chooser offers main/btw/both and cancels only the named target (ESC cancels nothing)"
    why_human: "Signal + dialog choreography needs a live terminal (07-VALIDATION Manual-Only, D-08)"
  - test: "Fire /btw mid-task while main streams"
    expected: "Fenced btw blocks arrive live with main output outside and no torn lines"
    why_human: "Readability of interleaved output needs a human eye (07-VALIDATION Manual-Only, D-09)"
  - test: "Review LOOP-03 safety prohibition: btw mutations face the same deny-first gate"
    expected: "No weaker btw approval lane exists; trust_delegated auto-trust is announced in the transcript"
    why_human: "Judgment-tier prohibition (unverified-prohibition — human review recommended); LLM-judge verdict below is non-authoritative"
  - test: "Review LOOP-03 transparency prohibition: side content never presented as main content"
    expected: "Fences, prompts, history appends, /policy last entries all carry btw identity"
    why_human: "Judgment-tier prohibition (unverified-prohibition — human review recommended); LLM-judge verdict below is non-authoritative"
  - test: "Review LOOP-03 memory-safety prohibition: side reasoning never memorialized as durable user memory"
    expected: "Side agent recalls shared facts but never writes the fact store or curate queue"
    why_human: "Judgment-tier prohibition (unverified-prohibition — human review recommended); LLM-judge verdict below is non-authoritative"
---

# Phase 07: Subagents + /btw Side Channel Verification Report

**Phase Goal:** Users can ask side questions mid-task without disturbing the main task
**Verified:** 2026-10-06T09:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

Roadmap Success Criteria map onto the plan truths: SC1 ("ask a side question mid-task via /btw and get an answer from a subagent") is covered by truths 1–3; SC2 ("main task continues untouched") by truths 1, 4, 8, 10, 11. All plan truths verified, so both SCs hold.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Mid-turn /btw spawns a parallel side agent; main runs unpaused; plain text still steers (D-02/03/04) | ✓ VERIFIED | `is_btw_line` + `on_btw` seam in steering.py:65/278; dual-future `_invoke_parallel` loop.py:313 with `_spawn_next` main-thread spawn; TestParallelTurn + TestMidTurnCarveOut pass (full suite 883 green) |
| 2 | Side answer streams live as fenced btw block; side failure renders fenced error, never silent (D-09/12) | ✓ VERIFIED | FencedBtwHandler btw.py:98 + render_btw_error btw.py:128; RLock reentrancy fix + regression test post-review; TestFencedRender two-thread contiguity test passes |
| 3 | Same model/tools/gate, forked history, recall-only memory, Q&A appended at boundary (D-05/07/13/14/16) | ✓ VERIFIED | build_btw_agent btw.py:346 (same objects replayed, session False, writable=False btw.py:388/391); fork_btw_history btw.py:140; append_btw_turn btw.py:176; TestBuildBtwAgent + TestForkBtwHistory pass |
| 4 | Idle /btw runs a normal inline turn; other mid-turn slashes keep verbatim refusal (D-01/02) | ✓ VERIFIED | router.py:206 /btw branch before skills-dynamic + USAGE_HINT router.py:55; btw in BUILTIN_SLASH_HEADS; TestBtwIdleDispatch passes; refusal path untouched |
| 5 | Side spend melts into session /cost total, no btw rows (D-15) | ✓ VERIFIED | Boundary/idle flush reuse record_turn_metrics loop.py:1618/676 with identical key sets; cost_report unchanged; melt-in test passes |
| 6 | Every prompt tagged [main]/[btw] from event.agent; interleaved pipelines never swap contexts (D-06) | ✓ VERIFIED | tag_for policy_gate.py:82, _last_by_tag + _ASK_TAG policy_gate.py:94/360; TestAgentTaggedGate interleaved-classify reverse-order-ask test passes |
| 7 | Batch coverage namespaced per agent; denials never cover either side (D-06) | ✓ VERIFIED | tag keyword on is_covered/mark with (tag, signature) keys, 3-tuple _signature unchanged; pre-existing tests pass unmodified; namespaced-batch tests pass |
| 8 | Main and btw cancel independently; Ctrl-C with both asks main/btw/both, cancels only named target (D-08) | ✓ VERIFIED | Per-request cancel registry policy_gate.py:238-253; TestPerRequestCancel real-thread TurnCancelled routing passes; resolve_cancel_targets/ask_cancel_target loop.py:203/218 + both_running handler tests pass |
| 9 | btw counts as delegated under trust_delegated with visible transcript note | ✓ VERIFIED | Auto-trust note policy_gate.py:454 via print_plain under RENDER_LOCK; test asserts capsys note + builtins.print-raises guard passes |
| 10 | One side answer at a time; further /btw queue FIFO with visible depth, never dropped (D-10/04) | ✓ VERIFIED | BtwQueue + submit echoes btw.py:207/323 (BTW_NOTED/BTW_QUEUED_TEMPLATE); pump spawns only when no side runs loop.py:403-466; TestBtwQueue + TestBtwFifoDrain pass |
| 11 | Side run outlives main, lands fenced at idle; idle approvals served (D-11 bounded-wait) | ✓ VERIFIED | Tracer join removed; session-scoped BtwContext with attach/take_done_live btw.py:286-321; _drain_idle_btw loop.py:647 (append + metrics + announce-once latch); TestOutlivingMain incl. announce-then-served test passes |

**Score:** 11/11 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `strands_code_cli/btw.py` | RENDER_LOCK, LockedHandler, FencedBtwHandler, fork/build/append, BtwContext, BtwQueue | ✓ VERIFIED | All symbols present; RLock post-review; substantive (~400 lines) and wired |
| `strands_code_cli/steering.py` | is_btw_line + on_btw seam | ✓ VERIFIED | Present; bare-/btw usage edge handled; gate_open discipline untouched |
| `strands_code_cli/loop.py` | Dual pump, boundary flush, idle drain, chooser, both_running | ✓ VERIFIED | _invoke_parallel, _drain_idle_btw, ask/resolve chooser, WR-01 fix all present and wired |
| `strands_code_cli/main.py` | LockedHandler wrap sharing RENDER_LOCK | ✓ VERIFIED | main.py:156 wraps DEFAULT handler; imported from btw |
| `strands_code_cli/router.py` | /btw idle branch + USAGE_HINT | ✓ VERIFIED | Branch before skills-dynamic; usage on empty |
| `strands_code_cli/skills.py` | btw builtin head | ✓ VERIFIED | In BUILTIN_SLASH_HEADS; shadowing test passes |
| `strands_code_cli/policy_gate.py` | Tags, keyed stash, namespaced batch, cancel registry, has_pending, discard | ✓ VERIFIED | All present; WR-03 discard hooked into request() abort paths |
| `strands_code_cli/diff_gate.py` | PendingStore thread-safety outcome | ✓ VERIFIED | threading.Lock guard; ten-thread hammer test passes |
| `tests/test_btw.py` | Fork/fence/carve/parallel/build/queue/outlive tests | ✓ VERIFIED | 14 test classes incl. reentrancy regression + integration-marked live scenario |
| `tests/test_router_btw.py` | TestBtwIdleDispatch | ✓ VERIFIED | Present, passing |
| `tests/test_cost_context.py` | btw melt-in test | ✓ VERIFIED | Present, passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| steering reader | BtwContext.submit | on_btw callback enqueues only | ✓ WIRED | Reader never spawns; pump builds on main thread |
| _invoke_agent pump | main + btw futures | single broker pump, max_workers=2 | ✓ WIRED | No nesting/recursion; _spawn_next only when no side live |
| main handler | btw handler | shared RENDER_LOCK (RLock) | ✓ WIRED | Production nesting regression-tested post-CR-01 |
| btw worker | main history | boundary/idle flush on main thread | ✓ WIRED | Worker records pending slot only; append via append_btw_turn |
| idle /btw | agent turn | router ("agent", rest) + builtin head | ✓ WIRED | Skill named btw stays shadowed |
| ask context | worker threads | tag-keyed stash + thread-local | ✓ WIRED | Interleaved reverse-order test proves no swap |
| cancel chooser | per-request events | resolve targets → named events only | ✓ WIRED | Handler sets nothing while both run; WR-01 idempotent set on legacy path |

### Data-Flow Trace (Level 4)

N/A — no rendered-dynamic-data artifacts in this phase beyond the fenced transcript blocks, whose content flows from the side agent's own message stream through the shared handler (verified by fence tests). No static fallbacks or hollow props found.

### Behavioral Spot-Checks

Full suite run once in this session: `uv run pytest -q` → **883 passed, 6 deselected** (integration marker), 18.47s. Targeted class enumeration confirms every plan-named test class exists and ran green within that suite (TestForkBtwHistory, TestFencedRender, TestMidTurnCarveOut, TestParallelTurn, TestBuildBtwAgent, TestBtwIdleDispatch, TestAgentTaggedGate, TestPerRequestCancel, TestPendingStoreThreads, TestResolveCancelTargets, TestBothRunningHandler, TestHandleTurnCancelTarget, TestBtwQueue, TestBtwFifoDrain, TestSteeringDuringBacklog, TestGateOpenBtw, TestOutlivingMain).

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite green | `uv run pytest -q` | 883 passed, 6 deselected | ✓ PASS |
| Phase test classes present | grep `^class Test` over 6 test files | all plan-named classes found | ✓ PASS |
| Debt markers absent | grep TBD/FIXME/XXX/TODO/HACK over 8 impl files | no matches | ✓ PASS |

### Probe Execution

No probes declared by PLAN/SUMMARY (no `scripts/*/tests/probe-*.sh` referenced). Skipped.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| LOOP-03 | 07-01, 07-02, 07-03 | Side question mid-task via /btw answered by subagent without disturbing main | ✓ SATISFIED | All 11 truths verified; mechanisms hermetically tested; live-terminal rendering confirmation pending in human_verification |

No orphaned requirements: REQUIREMENTS.md maps only LOOP-03 to Phase 7, and all three plans declare it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none | — | No debt markers, stubs, or placeholder patterns in the 8 phase impl files |

Review state: CR-01 + WR-01/02/03 fixed and committed (48d48ab, 121205a, 647dc55, 6b10c56); fixes verified present in code (RLock, idempotent cancel set, deferred skills refresh, broker.discard). IN-01..IN-05 out of fix scope by design; IN-03 (teardown on crashing exception) and IN-05 (shared interpreter/model thread-safety audit) noted as follow-ups, not blockers.

### Prohibitions (judgment-tier, non-authoritative LLM-judge)

- Safety (same deny-first gate for btw): judge SATISFIED — build_btw_agent replays the SAME interventions list object (pinned by TestBuildBtwAgent identity assertion); trust_delegated note present. Flagged unverified-prohibition — human review recommended.
- Transparency (btw identity everywhere): judge SATISFIED — fenced headers/footers, tagged prompt first line, "[tag] "-prefixed /policy descriptions, "/btw <q>" history text. Flagged unverified-prohibition — human review recommended.
- Memory-safety (no durable writes from side): judge SATISFIED — resolve_memory(writable=False) + register_memory_plugin injector only (btw.py:388-395); no fact-store/curate writes in btw path. Flagged unverified-prohibition — human review recommended.

### Human Verification Required

See frontmatter `human_verification` (6 items): the 3 manual-only live-terminal checks from 07-VALIDATION.md (D-11 idle landing, D-08 chooser, D-09 fence visuals) plus the 3 judgment-tier prohibition reviews.

### Gaps Summary

No gaps. All must-haves verified against the codebase with passing automated tests. The phase goal is achieved subject to live-terminal human confirmation of rendering and signal choreography, which are inherently non-automatable.

Note: `covered_digest` omitted — no gsd-tools.cjs in this runtime (generic-agent workaround), and digests must never be hand-written.

---

_Verified: 2026-10-06T09:00:00Z_
_Verifier: Muse Code (gsd-verifier; generic-agent workaround)_
