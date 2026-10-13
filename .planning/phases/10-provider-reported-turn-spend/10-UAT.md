---
status: complete
phase: 10-provider-reported-turn-spend
source: [10-01-SUMMARY.md, 10-02-SUMMARY.md, 10-03-SUMMARY.md, 10-04-SUMMARY.md]
started: 2026-10-13T00:15:00Z
updated: 2026-10-13T00:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Live OpenRouter proof (keyed integration run)
expected: With OPENROUTER_API_KEY set and the litellm extra installed, `uv run pytest tests/test_reported_cost.py::TestLiveReportedCost -q -rs -m integration` passes with a drained float >= 0 and an actual-marked row (a legitimate 0.0 must pass per D-09/WR-04).
result: issue
reported: "AttributeError: 'LiteLLMModel' object has no attribute 'take_reported_costs' at tests/test_reported_cost.py:523 — wrap_for_openrouter returned the model unpromoted (fail-soft swallowed the promotion failure)"
severity: blocker

### 2. Prohibition review (P1, P2, P3)
expected: The three must-NOT prohibitions in 10-VERIFICATION.md are reviewed against the cited code and each `status: unresolved` is explicitly accepted (or a blocking finding is raised).
result: pass

### 3. End-to-end main-turn confirmation
expected: One real OpenRouter main turn shows the marked actual (`$X actual`) on both the post-turn usage line and the /cost row, matching the provider's reported cost for the turn.
result: issue
reported: "Usage line shows bare '3.01K (2%) $0.00' with no actual marker after a real OpenRouter main turn"
severity: major

### 4. Inline usage.cost capture per model cycle with verbatim chunk delegation
expected: Inline usage.cost capture per model cycle with verbatim chunk delegation
result: pass
source: automated
coverage_id: 10-01-D1

### 5. Per-turn drain with any-rule sum (present 0.0 stays actual, all-absent drains to None)
expected: Per-turn drain with any-rule sum (present 0.0 stays actual, all-absent drains to None)
result: pass
source: automated
coverage_id: 10-01-D2

### 6. Wrap gate: openrouter ids promote in place, other ids pass through identical
expected: Wrap gate: openrouter ids promote in place, other ids pass through identical
result: pass
source: automated
coverage_id: 10-01-D3

### 7. Marked actual on the post-turn usage line with actual-wins precedence
expected: Marked actual on the post-turn usage line with actual-wins precedence
result: pass
source: automated
coverage_id: 10-01-D4

### 8. /cost rows render marked actuals, bare-$ estimates, or tokens-only with one money lane per row
expected: /cost rows render marked actuals, bare-$ estimates, or tokens-only with one money lane per row
result: pass
source: automated
coverage_id: 10-01-D5

### 9. Mixed sessions show a blended headline total plus an actual/estimated split beneath it
expected: Mixed sessions show a blended headline total plus an actual/estimated split beneath it
result: pass
source: automated
coverage_id: 10-02-D1

### 10. Pure actuals or pure estimate sessions show the plain total with no split line
expected: Pure actuals or pure estimate sessions show the plain total with no split line
result: pass
source: automated
coverage_id: 10-02-D2

### 11. Routing lines mark reported spend and fold it into the actuals lane; absent costs stay bare and never open the lane
expected: Routing lines mark reported spend and fold it into the actuals lane; absent costs stay bare and never open the lane
result: pass
source: automated
coverage_id: 10-02-D3

### 12. Bedrock and offline turns render byte-identical to the pre-phase output
expected: Bedrock and offline turns render byte-identical to the pre-phase output
result: pass
source: automated
coverage_id: 10-02-D4

### 13. Side builds get fresh wrappers; draining one never touches parent or sibling costs
expected: Side builds get fresh wrappers; draining one never touches parent or sibling costs
result: pass
source: automated
coverage_id: 10-03-D1

### 14. Finished side turns carry drained cost on pending 4-tuples through to rows
expected: Finished side turns carry drained cost on pending 4-tuples through to rows
result: pass
source: automated
coverage_id: 10-03-D2

### 15. Explicit reported_cost (incl None) wins without consulting the model
expected: Explicit reported_cost (incl None) wins without consulting the model
result: pass
source: automated
coverage_id: 10-03-D3

### 16. Sessions starting on OpenRouter capture from turn one; bedrock untouched; effort survives promotion
expected: Sessions starting on OpenRouter capture from turn one; bedrock untouched; effort survives promotion
result: pass
source: automated
coverage_id: 10-03-D4

### 17. Main turns drain the serving model and store reported_cost with a marked usage line; pre-discipline accumulation is discarded once at wrap
expected: Main turns drain the serving model and store reported_cost with a marked usage line; pre-discipline accumulation is discarded once at wrap
result: pass
source: automated
coverage_id: 10-04-D1

### 18. Wrap, copy, and extract degrade to estimates instead of raising or poisoning totals
expected: Wrap, copy, and extract degrade to estimates instead of raising or poisoning totals
result: pass
source: automated
coverage_id: 10-04-D2

## Summary

total: 18
passed: 16
issues: 2
pending: 0
skipped: 0

## Gaps

- gap_id: G-10-1
  truth: "Live OpenRouter turn captures a real reported cost end to end"
  status: failed
  reason: "User reported: AttributeError: 'LiteLLMModel' object has no attribute 'take_reported_costs' — wrap promotion fail-soft hid the failure on the real SDK class"
  severity: blocker
  test: 1
  artifacts: ["strands_code_cli/reported_cost.py:64-74 (_composed_class builds a MULTIPLE-inheritance subclass ReportedCostModel(ReportedCostMixin, base))", "strands_code_cli/reported_cost.py:109-113 (WR-01 fail-soft try/except swallows the promotion TypeError and returns input unchanged)", "tests/test_reported_cost.py:20-32 (hermetic FakeLiteLLMModel is a plain __dict__ class, so multi-inherit promotion succeeds there and all 27 hermetic tests pass)", "tests/test_reported_cost.py:523 (drain site raising AttributeError on the unpromoted real instance)"]
  missing: []
  root_cause: "CONFIRMED against real installed strands.models.litellm.LiteLLMModel (chain LiteLLMModel->OpenAIModel->Model, all __slots__=(), __dict__ from ABC): resolved.__class__ = _composed_class(LiteLLMModel) raises TypeError: __class__ assignment: 'ReportedCostModel' object layout differs from 'LiteLLMModel' because CPython rejects in-place promotion from a single-base instance to a MULTIPLE-inheritance subclass (extra base changes instance layout). The WR-01 except swallows it, wrap returns the model unpromoted, and the drain finds no take_reported_costs. The hermetic stub never reproduces this because FakeLiteLLMModel is a plain single-dict class where multi-inherit __class__ reassignment is legal."
  fix_direction: "Build the composed class with SINGLE inheritance: class ReportedCostModel(base) with __slots__ = (), capture methods (format_chunk/take_reported_costs) defined directly on it instead of via a mixin base. Verified: __class__ promotion then succeeds on a real LiteLLMModel instance, _reported_costs stores in the inherited __dict__, client_args/effort preserved in place, isinstance stays true. Keeps D-05 fail-soft except, D-09 rewrap-discard, and display-only semantics untouched; add one real-SDK promotion test (no network: construct LiteLLMModel with dummy client_args and wrap)."
- gap_id: G-10-3
  truth: "One real OpenRouter main turn shows the marked actual on usage line and /cost row"
  status: failed
  reason: "User reported: bare '3.01K (2%) $0.00', no actual marker — same root cause as G-10-1 (promotion never takes effect on the real SDK class)"
  severity: major
  test: 3
  artifacts: ["strands_code_cli/reported_cost.py:64-74 (_composed_class builds a MULTIPLE-inheritance subclass ReportedCostModel(ReportedCostMixin, base))", "strands_code_cli/reported_cost.py:109-113 (WR-01 fail-soft try/except swallows the promotion TypeError and returns input unchanged)", "loop.py record_turn_metrics drain path (finds no take_reported_costs on the unpromoted model, falls back to D-05 estimate display)"]
  missing: []
  root_cause: "Same confirmed root cause as G-10-1 (one diagnosis covers both): __class__ promotion to the multi-inheritance ReportedCostModel raises TypeError on the real slotted LiteLLMModel chain and is swallowed by the WR-01 fail-soft except, so the serving model never captures usage.cost and the turn renders the bare D-05 estimate with no actual marker."
  fix_direction: "Same fix as G-10-1: single-inheritance composed subclass with __slots__ = () and capture methods defined directly on it; fixes both gaps with one change."
