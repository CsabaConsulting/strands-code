# Debug Session: rig-bedrock-model-id (G-08-1)

status: root-cause-found
goal: find_root_cause_only (generic-agent workaround — typed dispatch unavailable)
date: 2026-10-12
gap: G-08-1 (08-UAT.md test 1, severity blocker)

## Symptoms (pre-filled)

- **Truth (expected):** R2/R3/R4 PASS — live local-engine route, /model override
  respect, side-ask parity against real engines (UAT test 1).
- **Actual (verbatim user report):** r3 `AssertionError: TIMEOUT waiting for
  main-end` after [valid]/[explicit-on]; r4 `AssertionError: TIMEOUT waiting for
  side-spawn: 'Side question noted'` after [explicit-on]. r2 log looks green
  (confirmation of exit code pending).
- **Errors:** Bedrock `ValidationException: Invocation of model ID
  amazon.nova-micro-v1:0 with on-demand throughput isn't supported. Retry with
  the ID or ARN of an inference profile.` Transcripts /tmp/uatr8/r3.log,
  /tmp/uatr8/r4.log, /tmp/uatr8/r2.log.
- **Reproduction:** Test 1 in 08-UAT.md — `cd /tmp && python3
  scripts/uattest/driver.py r3` / `r4`.
- **Timeline:** Discovered during UAT.

## Hypotheses

- H1 (working hypothesis, from dispatch): rig strategies hardcode candidate
  `bedrock/amazon.nova-micro-v1:0`, not invokable in this account/region;
  routing product behaved correctly. r3: failed turn prints no cost line so
  wait_main_end times out. r4: main turn failed in <6s so /btw landed on idle
  prompt where it is by design a normal main turn (router.py D-01), hence no
  side-spawn marker.
- H2 (alternative): product routing bug — wrong pick, dropped cost line, or
  broken side-spawn path.
- H3 (alternative): transient Bedrock outage/throttle, not id-specific.

## Experiments & Evidence

### E1 — Bedrock ground truth for the model id (read-only describe calls, no model invocations)

- `aws bedrock get-foundation-model --region us-west-2 --model-id
  amazon.nova-micro-v1:0` → `inferenceTypesSupported: ['INFERENCE_PROFILE']`
  only. No `ON_DEMAND`. This is the Bedrock-side cause of the exact
  ValidationException in r3.log:29-30 and r4.log:26-29.
- `aws bedrock list-inference-profiles --region us-west-2` →
  `us.amazon.nova-micro-v1:0 | US Nova Micro | ACTIVE | SYSTEM_DEFINED`.
  **Concrete replacement id confirmed invokable-form.**
- In-repo precedent: r2.log:33-37 shows bare `us.anthropic.claude-haiku-4-5-20251001-v1:0`
  (same `us.` cross-region profile-id form) invoking fine and serving the turn.
- `strands_code_cli/model_switch.py:607-623` (`normalize_model_ref` docstring):
  "the profile-id tail (`us.anthropic....`) is the valid Bedrock Converse
  identifier and the form configs use."
- Verdict: H1's "not invokable bare id" CONFIRMED at the Bedrock API layer.
  H3 REFUTED (deterministic id/throughput rejection, present in every log that
  routes to the bare id, with a precise Bedrock error naming the remedy).

### E2 — Rig hardcodes the bare id; engine legitimately picked it (r3)

- `scripts/uattest/driver.py:370` (r2), `:430` (r3), `:507` (r4):
  `write_strategy` blocks hardcode `- id: bedrock/amazon.nova-micro-v1:0`.
  Verified live in /tmp/uatr8/w3/.agent/routing.yaml and w4 (w4 has it twice —
  see E4).
- r3.log:28: `Routed → bedrock/amazon.nova-micro-v1:0 (off): model 68%, effort
  100%` — decision engine picked it above the 0.62 gate; directives ("stay on
  current") are advisory input to the decider, not a hard constraint. Routing
  behaved correctly.
- r3.log:29-30: `Turn failed (ValidationException)...` then NOTHING — no cost
  line, prompt returns. Mechanism: `strands_code_cli/loop.py:2259-2274`
  (provider/model errors fail the turn, never the session) sets `failed = True;
  break`, skipping `record_turn_metrics` at loop.py:2286. So no
  `(\d+%) $` line is ever printed on a failed turn.
- `scripts/uattest/driver.py:101-121` (`wait_main_end`) watches ONLY `COST_RE`
  (plus Approve? assist) — no fail-fast on `Turn failed`. Hence
  `TIMEOUT waiting for main-end` after a fast failure. Rig gap confirmed.

### E3 — r4 cascade: fast main failure → idle /btw → no side-spawn marker

- r4.log:24-29: main turn routes to nova-micro and `Turn failed` BEFORE the
  driver's 6s stagger (`driver.py:522`) elapses; r4.log:30-31 shows the /btw
  answered with main-style `Routed → bedrock/...` (NOT `Routed (btw)`).
- `strands_code_cli/router.py:221-226`: idle /btw (D-01) is a normal inline
  turn — returns `("agent", rest)`. By design, no side path at idle.
- `strands_code_cli/btw.py:54,390`: `BTW_NOTED = "Side question noted…"` prints
  only on the mid-turn submit path (`BtwContext.submit`). At idle it can never
  print. Hence `TIMEOUT waiting for side-spawn`. Product behaved per design;
  H2 REFUTED for the side path.

### E4 — Cross-run poisoning: routed pick persisted nova-micro as global default

- `strands_code_cli/loop.py:1546-1554`: a routed pick persists verbatim via
  `ProviderConfig.load().save_model_choice(current_model)` ("like /model").
- r3 routed TO `bedrock/amazon.nova-micro-v1:0` → global default overwritten.
  Observed: `~/.config/strands-code/config.yaml` now reads
  `model: bedrock/amazon.nova-micro-v1:0`; r2/r3 booted haiku, r4 booted
  nova-micro (r4.log:12); r4's `current_model_from_boot` therefore resolved to
  nova-micro, so /tmp/uatr8/w4/.agent/routing.yaml lists nova-micro TWICE —
  no invokable route existed regardless of the decision.
- Side effect, not root cause — but the fix must also restore the default
  model, and plan-phase should consider whether routed picks persisting the
  global default is intended.

### E5 — Product exoneration (H2 refuted)

- Decision + `Routed` line + BOTH confidences present in r2, r3, r4 logs
  (D-12 contract holds).
- r2 green end-to-end through the local engine (picked the invokable haiku id).
- `/route validate` reporting `candidate #0 bedrock/amazon.nova-micro-v1:0: ok`
  is NOT a false negative bug: `strands_code_cli/routing.py:678-682` checks
  structural parse only (`_candidate_skip_reason`), never invokability
  (offline by design, D-13). It cannot catch this class of failure.

## Reasoning checkpoint

```yaml
reasoning_checkpoint:
  hypothesis: "Rig strategies hardcode bedrock/amazon.nova-micro-v1:0, whose base id supports only INFERENCE_PROFILE throughput in us-west-2, so every routed turn to it fails at ConverseStream; the rig then hangs because wait_main_end only watches the cost line that failed turns never print (r3), and r4's main turn fails before the /btw stagger so the side ask lands on the idle prompt where it is by design a main turn (r4)."
  confirming_evidence:
    - "get-foundation-model: amazon.nova-micro-v1:0 inferenceTypes=['INFERENCE_PROFILE'] only"
    - "r3.log:28 Routed line picks nova-micro at 68%, then Turn failed ValidationException, no cost line"
    - "loop.py:2273-2274 break skips record_turn_metrics; driver.py:101-121 watches only COST_RE"
    - "r4.log:30-31 idle /btw answered as main turn (Routed →); router.py:221-226 D-01; btw.py:390 mid-turn-only marker"
    - "loop.py:1547-1554 routed-pick persistence + config.yaml now nova-micro + w4 strategy has it twice"
  falsification_test: "Replace the rig candidate with us.amazon.nova-micro-v1:0 and re-run r3/r4 — if the ValidationException persists, the id hypothesis is wrong."
  fix_rationale: "Using the ACTIVE SYSTEM_DEFINED profile id removes the Bedrock rejection at its source; fail-fast on 'Turn failed' converts future silent hangs into immediate diagnoses."
  blind_spots: "Did not live-invoke us.amazon.nova-micro-v1:0 via Converse (deliberately avoided spend); invokability inferred from ACTIVE profile status + bare us.anthropic precedent green in r2 + normalize_model_ref docstring. Did not re-run the driver (diagnose-only mode)."
  candidate_causes:
    - "config: rig strategy hardcodes a throughput-incompatible Bedrock id (primary)"
    - "environment: global default model poisoned to the same non-invokable id by routed-pick persistence (amplifier)"
  and_gate: "No — the bare id alone fully explains both timeouts; persistence explains only why r4's strategy had it twice."
```

## Root cause

Rig/env-side, no product bug. See return payload.

## Suggested fix direction (non-binding, for plan-phase --gaps)

1. Rig strategies (driver.py scenario_r2/r3/r4 + any docs): replace
   `bedrock/amazon.nova-micro-v1:0` with `bedrock/us.amazon.nova-micro-v1:0`
   (ACTIVE SYSTEM_DEFINED profile in us-west-2; `us.`-tail is the documented
   valid Converse identifier form). Bare `us.amazon.nova-micro-v1:0` is
   equivalent per the haiku precedent.
2. Restore the poisoned global default in ~/.config/strands-code/config.yaml
   to an invokable id (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`).
3. Rig fail-fast: `wait_main_end`/`wait_routed` should abort on `Turn failed`
   instead of hanging to timeout.
4. Consider (product question): whether routed picks should persist the global
   default model (loop.py:1547-1554) — this amplified a rig failure into
   environment poisoning.
