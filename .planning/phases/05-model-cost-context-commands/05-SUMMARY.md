---
phase: 05-model-cost-context-commands
plan: 05
subsystem: cli
tags: [model-switching, cost-display, context-management, strands, bedrock]

# Dependency graph
requires:
  - phase: 04-plan-act-modes-steering
    provides: [reply-only router actions, gate/turn layer, transcript-first UX]
  - phase: 03-permissions-gate
    provides: [single-HITL gate spine, deny-first approvals]
  - phase: 01-session-management
    provides: [SessionIndex sidecar, snapshot persistence, explicit_save]
provides:
  - [mid-session /model switching with convert-or-compact history portability]
  - [display-only spend visibility (usage line, /cost) on static tables]
  - [/compact, /clear, /context plus 80% auto-compact preserving tool pairs]
affects: [07-btw-side-channel, future model-routing work]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 520
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [turn-boundary swap seam, convert-when-fits else compact, static-table spend display]

key-files:
  created: [strands_code_cli/model_switch.py, strands_code_cli/cost_context.py, tests/test_model_switch.py, tests/test_cost_context.py]
  modified: [strands_code_cli/router.py, strands_code_cli/loop.py, strands_code_cli/main.py, strands_code_cli/provider_config.py, strands_code_agent/utils.py, tests/test_cli_entry.py]

key-decisions:
  - "Swap seam: in-place agent.model assignment (tracer-proven; rebuild fallback deleted)"
  - "/clear keeps session id + index entry + model choice; /context exact field list per item 3"
  - "Static MODEL_PRICING/MODEL_LIMITS with tokens-only fallback; cost display-only forever"
  - "Mid-turn /model: immediate refusal reply, never queued"
  - "Pre-existing test_cli_entry /model-out-of-scope assertion updated to the MODEL-01 contract"

patterns-established:
  - "Router validates, loop applies: new slash actions return (\"model\", id), swap code lives in loop.py only"
  - "Pair-atomic history ops: toolUse/toolResult never split by convert, trim, compact, or auto-compact"
  - "Untrusted-marker summaries: compaction output re-enters as marker-prefixed text, never a tool result"

requirements-completed: [MODEL-01, MODEL-02, SES-02]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Mid-session /model switch continues the same conversation, converted or compacted"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "tests/test_model_switch.py#TestIdleOnlySwap"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-session/per-task cost display plus post-turn usage line, display only"
    requirement: "MODEL-02"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestCostReport"
        status: pass
    human_judgment: false
  - id: D3
    description: "/compact, /clear, /context without losing place; 80% auto-compact preserves tool pairs"
    requirement: "SES-02"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestContextOps"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live CLI switching, discovery UX, and spend accuracy against real providers"
    verification: []
    human_judgment: true
    rationale: "Needs a human driving the REPL across providers and network states (UAT below)"

# Metrics
duration: 55min
completed: 2026-09-27
status: complete
---

# Phase 05 Plan 05: Model + Cost + Context Commands Summary

**Mid-session `/model` switching with convert-or-compact portability, display-only spend visibility, and pair-safe context controls — all on replay-model tests, full suite green.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-09-27T (session start)
- **Completed:** 2026-09-27
- **Tasks:** 3 completed
- **Files modified:** 10 (4 created, 6 modified)

## Accomplishments

- Tracer proved the spine offline: `resolve_model` per provider shape, in-place swap seam winner, conversion table, usage format, compact-replay — observations recorded in `tests/test_model_switch.py` docstring.
- `/model` switches providers at the idle prompt with Bedrock discovery (fail-soft), convert-when-fits else compact, verbatim ARNs, and persisted model choice (never credentials).
- `/cost`, `/compact`, `/clear`, `/context` reply branches plus post-turn `451.27K (45%)`-style usage line and 80% auto-compact preserving tool pairs.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer** - `5d08351` (feat)
2. **Task 2: /model switching** - `137b587` (feat)
3. **Task 3: /cost + usage + context ops** - `b353050` (feat)

## Files Created/Modified

- `strands_code_cli/model_switch.py` - `convert_history`/`discover_models`/`estimate_fit`/`apply_switch`, refusal text
- `strands_code_cli/cost_context.py` - `MODEL_PRICING`/`MODEL_LIMITS`, usage/cost/context/compact/clear builders
- `strands_code_cli/router.py` - `/model` (`("model", id)` action) + `/cost`/`/compact`/`/clear`/`/context` reply branches
- `strands_code_cli/loop.py` - idle-only swap, per-turn metrics + usage line, 80% auto-compact, post-mutation flush
- `strands_code_cli/main.py` - `model_for_config` (custom-endpoint `base_url` via constructor kwarg)
- `strands_code_cli/provider_config.py` - optional non-secret `base_url` key + `save_model_choice`
- `strands_code_agent/utils.py` - `get_response_metrics` threads static-table prices (backwards-compatible kwargs)
- `tests/test_model_switch.py`, `tests/test_cost_context.py` - 65 replay-model tests
- `tests/test_cli_entry.py` - one stale `/model`-out-of-scope assertion updated to the MODEL-01 contract

## Decisions Made

- **Swap seam: in-place** (checkpoint:decision, tracer evidence): `agent.model = resolve_model(...)` kept messages intact and the next turn succeeded; rebuild fallback deleted, not kept as an option.
- **`get_response_metrics` extension landed in the tracer commit**, not task 3: the tracer's usage-format spike explicitly requires fixture-summary + static-price lookup. Backwards-compatible optional kwargs; layering preserved (CLI passes the table in, agent lib never imports CLI).
- **`/compact` needs no confirmation prompt**: the plan allowed none ("confirmation (if any)"), so it executes immediately as a reply branch.
- **`/model` picker lives in the router** (plan-literal): discovery + `choice.radio_choice` at dispatch, still reply-only on every non-selection path; the swap itself stays loop-owned.
- **Stale contract updated**: `test_model_command_out_of_scope` pinned pre-Phase-5 behavior; MODEL-01 supersedes it (single-test update, documented here).

## Deviations from Plan

None - plan executed exactly as written, with two judgment calls documented above as Decisions (utils-threading commit placement; stale-test contract update). Both are within the task contracts, no scope creep.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope creep; all prohibitions hold (bleed greps clean, see below).

## Issues Encountered

- Only `bedrock` provider SDK deps are installed in this env: `resolve_model` for anthropic/openai/litellm/ollama ids raises `ImportError`, not `ValueError`. Handled per contract: unknown *names* → ValueError reply listing providers; valid names with missing SDK → fail-soft reply (pinned by test). Cross-vendor switch coverage therefore runs Bedrock↔Bedrock ids plus id-string conversion for anthropic/litellm shapes; live cross-provider turns remain UAT.
- `_best_hit` longest-match lost to family prefixes (`claude-sonnet-` beat `sonnet-4-6`); fixed to insertion-order first-hit with versioned keys first. `claude-3-haiku` needed its own 200K entry.
- Bleed grep vs required prose: the display-only footer and the credential-scrub regex legitimately contain flagged substrings; tests assert the negation/purpose context instead of blanket absence.

## Verification

- `uv run pytest tests/test_model_switch.py tests/test_cost_context.py -q` → 65 passed.
- `uv run pytest tests/ -q` → **525 passed, 5 deselected** (integration marker), Phase 1–4 suites unmodified-green.
- Bleed audit over the phase diff: `budget|enforce|halt|quota` only in display-only negations; `auto.*rout|smart.*model|yolo|/btw|enable_trust|cedar|/init|/memory` clean; no `os.getenv`/`os.environ` in new code; absolute imports only; one `logger.warning` (persistence failure, module logger — not the `python_repl` observation path).

## UAT Notes (user runs, agent did not simulate)

1. Launch CLI, chat two turns, run `/model`, pick a different provider, continue — next answer coherent, history intact; repeat with a custom id/ARN incl. a `us.`-prefixed ARN.
2. After any turn check the `451.27K (45%)`-style line; run `/cost` — per-turn rows + totals, money only for priced ids.
3. Run `/context` — tokens, %, message/tool counts, provider/name all present.
4. Run `/compact` — conversation continues, recent tool results still referenced, last ask re-grounded.
5. Run `/clear` — `Context cleared — session <id> kept.`, same id resumable, model choice kept.
6. Type `/model` mid-turn — refusal text, turn undisturbed.
7. Offline (no AWS creds) `/model` — configured/custom entries offered, no key prompt, no traceback.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Phase 6: swap seam (in-place), 80% threshold, static-table spend model, and untrusted-marker convention are locked downstream inputs.
- Residuals (documented, not closed): local estimator accuracy (A-6), static-table staleness (re-check `https://aws.amazon.com/bedrock/pricing` periodically), tty picker path untested (needs human), live cross-provider turns untested (UAT item 1).

## Self-Check: PASSED

---
*Phase: 05-model-cost-context-commands*
*Completed: 2026-09-27*
