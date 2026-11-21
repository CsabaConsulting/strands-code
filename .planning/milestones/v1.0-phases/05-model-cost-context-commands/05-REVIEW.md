---
status: issues
phase: 05-model-cost-context-commands
reviewer: phase-5 code reviewer (generic-agent workaround)
date: 2026-09-27
scope_commits: [5d08351, 137b587, b353050]
verdict: issues — no Critical findings; 1 Warning bug (malformed router return on one narrow path) + 1 Warning dead duplicate + 6 Info nits. No locked-decision violations. No source files modified by this review.
---

# Phase 05 Review: Model + Cost + Context Commands

inline-verdict: ISSUES (non-blocking) — full suite green (525 passed, 5 deselected), all threat mitigations present, but `router.py:180-183` returns a malformed nested action tuple on the bare-`/model` offline-empty non-tty path, and `model_switch.py:18` carries a dead duplicate of the compact marker.

## Verification performed

- Read `AGENTS.md`, `05-PLAN.md`, `05-SUMMARY.md`, `05-CONTEXT.md`; reviewed exactly the 10 scope files against `git log --oneline -6` (spine commits `5d08351`, `137b587`, `b353050` present).
- Ran `uv run pytest tests/test_model_switch.py tests/test_cost_context.py -q` → 65 passed; `uv run pytest tests/ -q` → 525 passed, 5 deselected.
- Bleed greps over the phase diff: `budget|enforce|halt|quota` appear only in display-only negations and the credential-scrub regex (purpose context, pinned by `test_no_budgets_or_enforcement_vocabulary` / `test_no_credential_persistence_sinks`); `auto.*rout|smart.*model|yolo|/btw|enable_trust|cedar|/init|/memory` clean; no `getenv`/`environ`, no relative imports, no `api_key` persistence sinks.

## Findings — Warning

### W-1: Malformed action tuple on bare-/model offline-empty non-tty path
- Where: [router.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/router.py:180)
- Code:
  ```
  if not seen:
      return (
          ("reply", f"No models discovered offline. {_MODEL_USAGE}"),
      )
  ```
  returns the 1-tuple `(("reply", msg),)`, not the `(action, message)` pair every other branch returns. Any caller doing `action, message = dispatch(...)` (as `loop.py:391` does) raises `ValueError` on unpack instead of showing the reply.
- Violated rule: plan item 12 / router tri-state contract (`dispatch` returns `(action, message)`; every non-selection path is a reply).
- Reachability: narrow — `run_loop` always passes a truthy `current_model`, so `configured` is never empty there and `seen` is never empty; the crash needs a direct `dispatch("/model", current_model=None)` call with failed discovery on non-tty stdin. Still a fail-soft violation on its face (offline `/model` must never traceback, UAT item 7) and the empty-`seen` path has no test pin. Fix: drop the trailing comma.

### W-2: Dead duplicate summary marker invites drift
- Where: [model_switch.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/model_switch.py:18)
- `_SUMMARY_MARKER` is defined but never referenced in the module; the live marker is [cost_context.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/cost_context.py:13) `SUMMARY_MARKER`, used at `:323` and `:330`. Two sources of truth for the T-05-06 mitigation string: if one is edited, marker checks silently stop matching.
- Violated rule: code-quality (dead code; single source of truth for a security-relevant constant). Fix: delete the duplicate and import from `cost_context` if ever needed.

## Findings — Info

### I-1: Non-snake_case local
- Where: [cost_context.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/cost_context.py:227) — `Pts = " | ".join(...)`.
- Violated rule: CONVENTIONS.md naming (`snake_case` for locals). Rename to `parts`.

### I-2: Stale comment contradicts implementation
- Where: [cost_context.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/cost_context.py:43) — `MODEL_LIMITS` comment says "longest match wins", but `_best_hit` (`:60-70`) is first insertion-order hit (the SUMMARY documents the deliberate longest-match→first-hit fix). Update the comment.

### I-3: Function-level import where no cycle exists
- Where: [model_switch.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/model_switch.py:180) (`estimate_fit` imports `cost_context` inside the function).
- Violated rule (minor): CONVENTIONS.md "keep imports at the top". Unlike the justified lazy imports (`boto3` in `discover_models`, `resolve_model` in `apply_switch`), `cost_context` does not import `model_switch`, so a top-level import is safe.

### I-4: D-05 text-serialized fallback has no explicit path
- Where: `convert_history` ([model_switch.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/model_switch.py:61)) keeps toolUse/toolResult byte-identical unconditionally; no branch detects targets without native function calling.
- Assessment: acceptable gap, not a violation — D-05 applies "only if such a target is ever selected" and the adapter layer owns wire format per D-03. Live cross-provider turns remain UAT (SUMMARY residuals). Noting so the gap stays explicit.

### I-5: `base_url` persistence has no CLI producer
- Where: [provider_config.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/provider_config.py:19) + [main.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/main.py:80)
- Load/save round-trip for the non-secret `base_url` host exists and is tested, and startup threads it into `OpenAIModel(client_args=...)` without ever persisting keys — but no CLI flow writes it (the `/model` custom path replies with usage; the loop persists only the model string). A custom endpoint therefore requires hand-editing `config.yaml` to take effect on restart. Within contract (plan requires persisting *at most* model + host, never keys); UX gap only.

### I-6: Mid-turn refusal flag is unreachable from the loop (defense-in-depth only)
- Where: [loop.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/loop.py:411) always calls `apply_model_action(..., turn_running=False)`; the D-01 refusal branch ([loop.py](/home/csaba/repos/AWS/strands-code/strands_code_cli/loop.py:320)) is tested directly but never `True` in production.
- Assessment: compliant — D-01/T-05-01 holds architecturally because `dispatch` only runs at the idle prompt. The flag is harmless tested armor, not a violated requirement.

## Locked-decision compliance (all hold)

- D-01 idle-only + immediate refusal, no queue: refusal text exact (`MODEL_REFUSAL`, pinned by `test_mid_turn_refusal_exact_text_model_unchanged`); swap code loop-owned, router returns `("model", id)` only.
- D-02 per-id checks, never family inference: substring tables with tokens-only fallback; unknown window → convert, never force-compact (`estimate_fit`).
- D-03 no hand-rolled vendor JSON: conversion rewrites SDK ContentBlocks only; pairs byte-identical and pair-atomic (`_pair_safe_start`, pinned).
- D-04 convert-or-compact: 70% convert line, summarize-old + keep-recent + last-user-message replay.
- D-06 verbatim ARNs, fail-soft discovery: lazy boto3, ON_DEMAND + profiles, never escalates/prompts, verbatim pinned.
- D-07 display-only cost: footer + vocabulary tests; usage line `451.27K (45%)` shape, money only on price hit.
- D-08 auto-compact at 80%, pair-atomic, same session id + index entry kept; `/clear` keeps id + model choice.
- Security: no keys to disk (model string + host only, 0o700 + atomic-replace + symlink refusal preserved); summaries re-enter marker-prefixed as text, never tool results; summarizer input credential-scrubbed; no new logging on agent-visible paths; constructor-kwarg config, absolute imports.

## Threat-register spot-check

T-05-01/02/03/06/07/10/11 blocking mitigations are each pinned by at least one green test (refusal text, pair intactness, reasoning strip + warn, untrusted marker, verbatim ARN, no-secret round-trip, offline fallback). T-05-04 holds by construction (mutate `agent.messages` + `explicit_save`, index never touches blobs). T-05-05/08/09/12/13/14/15 mitigations reviewed clean in code.

## Result

REVIEW COMPLETE — verdict: **issues** (2 Warnings, 6 Infos, 0 Critical). Recommended fixes before merge: W-1 (one-character trailing-comma fix + a regression test for bare `/model` with `current_model=None` offline non-tty) and W-2 (delete the dead marker). No source files were modified by this review.
