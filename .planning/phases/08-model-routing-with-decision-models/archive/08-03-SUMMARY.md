---
phase: 08-model-routing-with-decision-models
plan: 03
subsystem: routing
tags: [model-routing, guided-setup, strategy-validation, fast-path, integration-tests]

requires:
  - phase: 08-model-routing-with-decision-models
    provides: 08-01 tracer (routing.py strategy/decide/hook, /route toggle) plus 08-02 local engine, /cost Routing section, side routing
  - phase: 05-model-cost-context-commands
    provides: /cost refresh populating the OpenRouter disk cache validate reads
provides:
  - Guided /route setup over the live OpenRouter catalog with atomic scoped save
  - /route validate judging the winning strategy per failure class with fixes
  - docs/ROUTING.md operator guide with two example strategies
  - Single-candidate fast path skipping all decision engines
  - Stub-server plus env-gated live engine integration tests
affects: [verify-work, cost-visibility, onboarding-docs]

actuals:
  tokens: 19356
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns: [guided-setup-radio-with-typed-fallback, shared-loader-skip-reasons, single-candidate-fast-path, stub-server-wire-proof]

key-files:
  created:
    - docs/ROUTING.md
  modified:
    - strands_code_cli/routing.py
    - strands_code_cli/router.py
    - tests/test_routing_strategy.py
    - tests/test_routing.py
    - tests/test_loop_routing.py

key-decisions:
  - "Stub-server Ollama test runs unmarked in the default suite; only the credential/daemon-gated tests carry the integration marker"
  - "Skipped candidate entries fail validation (strict judge vs fail-soft loader); unknown top-level keys, empty directives, and primary-off stay valid notes"
  - "Unknown decision model in a present cache fails validation; an absent cache reports unchecked and never fails"
  - "Live tests skip on absence (no key/daemon/models/catalog) but fail loudly when a present endpoint rejects the call"
  - "Missing-price catalog entries sort last with price n/a; true zero-price free-tier rows still sort first"
  - "Decision pick constrained to structured-output advertisers; an empty eligible set falls back to a typed id"

patterns-established:
  - "Setup choice helper: radio_choice on tty, numbered typed prompt off-tty, every unclear answer aborts unchanged"
  - "ValidationReport: valid flag plus winning source plus ordered lines, rendered by format() as the slash reply"

requirements-completed: [MODEL-03]

coverage:
  - id: D1
    description: "Guided /route setup enumerating the live catalog and writing a valid global or repo strategy, plus docs/ROUTING.md examples"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteSetup"
        status: pass
    human_judgment: false
  - id: D2
    description: "/route validate reporting strategy validity per failure class with the winning source file"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteValidate"
        status: pass
    human_judgment: false
  - id: D3
    description: "Single-candidate fast path skipping all engines with the standard Routed line and zero-token event"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestSingleCandidateFastPath"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestLiveEngines stub-server Ollama test"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live engine proof against real endpoints (OpenRouter decision call, Ollama daemon decision)"
    requirement: "MODEL-03"
    verification:
      - kind: integration
        ref: "tests/test_routing.py#TestLiveEngines::test_openrouter_live_decision_returns_text"
        status: pass
      - kind: integration
        ref: "tests/test_routing.py#TestLiveEngines::test_ollama_live_daemon_decision_returns_text"
        status: unknown
    human_judgment: true
    rationale: "OpenRouter passed live this run (env key present); Ollama needs a daemon plus a pulled model, absent here — verifier must run with OLLAMA_LIVE set"
  - id: D5
    description: "Guided setup against the live catalog plus a routed turn on the picked model"
    requirement: "MODEL-03"
    verification: []
    human_judgment: true
    rationale: "Needs interactive setup with a real key plus live spend, per the plan's manual live check"

duration: 16min
completed: 2026-10-11
status: complete
---

# Phase 08 Plan 03: Setup plus Validate Summary

**Guided /route setup over the live OpenRouter catalog with atomic scoped saves, /route validate judging every failure class with fixes, routing docs with working examples, a zero-engine single-candidate fast path, and live engine proof (OpenRouter passed live, Ollama gated).**

Executed as gsd-executor-08-03 (generic-agent workaround: typed gsd-executor dispatch is unavailable in this runtime).

## Performance

- **Duration:** 16 min
- **Started:** 2026-10-11T04:52:00Z
- **Completed:** 2026-10-11T05:08:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Guided `/route setup`: scope then engine then candidate picks then decision-model pick then local-model text then directives, over `fetch_openrouter_models` filtered to chat-capable ids and sorted by price ascending, with radio on tty plus typed fallbacks off-tty and a typed-id path when the catalog fetch fails; every ESC, empty, or unclear answer aborts with the filesystem untouched.
- `save_strategy`: scope-selected atomic write (tmp plus `os.replace`, parent dir 0700), symlink refusal, api_key-shaped key drop with a warning at top level and inside `engine`, and zero-usable-candidate refusal.
- `/route validate` plus `validate_strategy`: winning source file, one line per candidate with the exact loader skip reason, engine checks (decision model against the cached catalog only — known, unknown, or unchecked), directives note, and a manual-edit fix per failure class; never writes, never fetches, never calls an engine.
- `docs/ROUTING.md`: concepts, quick start, cheap-default plus tiered example strategies (both parse as valid YAML with required keys), manual-edit rules, repo-wins and never-keys notes, stay-on-current tie-break, troubleshooting.
- Single-candidate fast path: one candidate advertising levels returns the pick verdict (`only candidate`, engine `none`, zero usage) with zero engine calls through the unchanged hook; lone candidates without levels, empty sets, and multi-candidate sets behave exactly as before.
- Live proof: stub-server Ollama test asserts the `/api/chat` request shape plus response parsing in the default suite; the OpenRouter live test ran against the real endpoint with the env key and passed; the Ollama live test skips cleanly without `OLLAMA_LIVE`.
- Full suite green at 1066 passed, 8 deselected (6 pre-existing plus the 2 gated live tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: Guided /route setup enumerating the live catalog plus routing docs with examples** - `dd1ba88` (feat)
2. **Task 2: /route validate reporting strategy validity per failure class** - `e6f5193` (feat)
3. **Task 3: Single-candidate fast path plus env-gated live engine integration tests** - `765a1f7` (feat)

## Files Created/Modified

- `strands_code_cli/routing.py` (MOD) - `save_strategy` plus `validate_strategy`/`ValidationReport` plus `_candidate_skip_reason` shared by the loader plus the `decide` fast path plus `ROUTE_USAGE` with the new verbs.
- `strands_code_cli/router.py` (MOD) - `/route setup` guided flow (catalog filter, tty/off-tty pickers, typed fallback) plus `/route validate` branch plus `USAGE_HINT` update.
- `docs/ROUTING.md` (NEW) - Routing guide with the two example strategies.
- `tests/test_routing_strategy.py` (MOD) - `TestRouteSetup` (12 tests), `TestRouteValidate` (16 tests).
- `tests/test_routing.py` (MOD) - `TestSingleCandidateFastPath` (4 tests), `TestLiveEngines` (stub plus 2 gated live tests).
- `tests/test_loop_routing.py` (MOD) - One-line usage-hint assertion update for the new verbs (consequential).

## Decisions Made

- Stub-server Ollama test runs unmarked in the default suite; only the credential/daemon-gated tests carry the `integration` marker — the plan verification requires stub-server tests passing in the full suite while gated live tests skip.
- Skipped candidate entries fail validation (validate is the strict judge, load stays fail-soft); unknown top-level keys, empty directives, and `primary: off` stay valid notes since the loader degrades gracefully and the config means what it says.
- Unknown decision model in a present cache fails validation (the decision call would 404 at runtime); an absent cache reports unchecked and never fails — setup never populates the cache, so failing there would punish fresh setups.
- Live tests skip on absence (no key, daemon, pulled models, or catalog) but fail loudly when a present endpoint rejects the call, so contract drift surfaces instead of hiding behind a skip.
- Missing-price catalog entries sort last with `price n/a`; true zero-price `:free` rows still sort first as the cheapest options.
- Decision pick constrained to entries advertising `response_format`/`structured_outputs`; an empty eligible set falls back to a typed id with a note rather than blocking setup.
- Off-tty decision pick re-prompts once on an unknown id then aborts (no valid-subset concept for a single choice); off-tty candidates write the valid subset on the second attempt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Usage-hint test asserted the pre-setup verb list**
- **Found during:** Task 1 (USAGE_HINT advertises the new `/route setup` verb)
- **Issue:** `test_usage_hint_advertises_route` asserted the literal `/route [on|off|status]`, which the feature legitimately extends; leaving the hint stale would mislead users.
- **Fix:** Updated the one-line assertion to the prefix form `/route [on|off|status|setup`, which also survives task 2's `|validate]` extension with no further churn.
- **Files modified:** tests/test_loop_routing.py
- **Verification:** Routing trio green (110 passed) after the commit.
- **Committed in:** dd1ba88 (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/consequential)
**Impact on plan:** One-line test literal keeping the tree green; no scope creep. All flagged edge-probe assumptions carried visibly, never auto-resolved.

## Issues Encountered

- Missing-price catalog entries first defaulted to $0 (sorting first as if free); fixed to sort last with `price n/a` while true `:free` zero-price rows still sort first. Found by the price-order assertion, fixed inside the task-1 commit.
- Empty-levels subtlety: `levels: []` falls through to the engine chain (not a fast path) and the strict parse then rejects every effort — locked by test rather than special-cased.

## Threat Flags

Threat-register mitigations verified in this plan:

- T-08-10 (key persistence via setup): setup never prompts for keys and `save_strategy` drops api_key-shaped keys (every case/separator spelling) at top level and inside `engine` with a warning; locked by the drop test plus the no-key-material file assertion.
- T-08-11 (malformed live catalog payload): field-by-field type checks, chat-capable filter mirroring `_is_chat_model`, unknown shapes skipped, catalog failure falls back to the typed-id path; locked by the fixture-catalog test (embed/rerank/malformed rows excluded, unpriced chat rows offered last).
- T-08-12 (stale doc examples): examples labeled starting points with a written date plus setup/validate pointers and no live claims (benchmark values marked illustrative).
- T-08-SC (package installs): no new dependencies; setup and validate reuse pyyaml, prompt_toolkit, and stdlib urllib.
- Transparency prohibition: setup copy states manual `/model` always wins; routed switches never fire mid-turn (no loop.py changes — the hook path is untouched).
- Privacy prohibition: setup sends nothing anywhere; the decision path still carries ask-only truncated text per 08-01.
- Disclosure prohibition: validate surfaces every failure class with fixes, and the fast path records a zero-token event so `/cost` stays truthful.

## Known Stubs

Stub scan over the touched source and test files found no new stubs: the three `pass` hits in `router.py` are pre-existing lines outside this plan's hunks, and the `pass` in `test_routing.py` is the stub HTTP server's deliberate `log_message` silence override. No `.planning/WINDOWS.md` exists and there is nothing to append.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 8 is complete: MODEL-03 closes here (strategy, both engines, hook, toggle, /cost visibility, side routing, setup, validate, docs, fast path, live proof).
- Manual live checks (gate verify-work, not this plan): run `/route setup` against the live catalog with a real key, confirm `/route validate` reports clean plus a routed turn serves on the picked model; run the Ollama live test with `OLLAMA_LIVE` set against a daemon with a pulled model.
- Phase 9 (CodeAct) inherits the finished routing surface; no routing follow-ups remain.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-11*

## Self-Check: PASSED
