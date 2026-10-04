---
status: testing
phase: 05-model-cost-context-commands
source: [05-SUMMARY.md]
started: 2026-09-27T12:00:00Z
updated: 2026-09-27T12:00:00Z
---

## Current Test

number: 1
name: Switch models mid-session
expected: |
  Launch the CLI, chat two turns, run /model, pick a different provider, and
  continue — the next answer is coherent and history is intact. Repeat with a
  custom id/ARN, including a us.-prefixed ARN.
awaiting: user response

## Tests

### 1. Switch models mid-session
expected: Launch the CLI, chat two turns, run /model, pick a different provider, and continue — the next answer is coherent and history is intact. Repeat with a custom id/ARN, including a us.-prefixed ARN.
result: [pending]
retest_after: G-05-1g

### 2. Usage line and /cost
expected: After any turn a 451.27K (45%)-style usage line appears; /cost shows per-turn rows plus totals, with money figures only for priced ids.
result: [pending]

### 3. /context report
expected: /context shows tokens, percentage, message/tool counts, and provider/model name, all present.
result: [pending]

### 4. /compact continuity
expected: /compact runs, the conversation continues, recent tool results are still referenced, and the last ask is re-grounded.
result: [pending]

### 5. /clear keeps session
expected: /clear prints `Context cleared — session <id> kept.`, the same session id stays resumable, and the model choice is kept.
result: [pending]

### 6. Mid-turn /model refused
expected: Typing /model while a turn is running prints the refusal text and the turn continues undisturbed.
result: [pending]

### 7. Offline /model
expected: With no AWS credentials, /model offers the configured/custom entries with no key prompt and no traceback.
result: [pending]

### 8. Mid-session /model switch continues the same conversation, converted or compacted
expected: Mid-session /model switch continues the same conversation, converted or compacted
result: pass
source: automated
coverage_id: D1

### 9. Per-session/per-task cost display plus post-turn usage line, display only
expected: Per-session/per-task cost display plus post-turn usage line, display only
result: pass
source: automated
coverage_id: D2

### 10. /compact, /clear, /context without losing place; 80% auto-compact preserves tool pairs
expected: /compact, /clear, /context without losing place; 80% auto-compact preserves tool pairs
result: pass
source: automated
coverage_id: D3

## Summary

total: 10
passed: 3
issues: 0
pending: 7
skipped: 0

## Gaps

- gap_id: G-05-1a
  truth: "Long /model picker list scrolls so the (*) marker stays visible"
  status: resolved
  reason: "User reported: marker disappears below the displayed list section when moving past visible rows"
  severity: major
  test: 1
  root_cause: "_build_app rendered all options with no scrolling container; Window overflowed the terminal"
  artifacts:
    - path: "strands_code_cli/choice.py"
      issue: "no visible-window slicing; highlight could leave the rendered area"
  missing:
    - "Render only visible_rows options; window follows highlight on arrows"
  resolved_by: 068a0d1
  resolved_at: 2026-09-27
- gap_id: G-05-1b
  truth: "/model discovery lists only chat-capable models"
  status: resolved
  reason: "User reported: list includes embedding, reranking, and image models (titan-embed-*, amazon.rerank-v1:0, stability.*image*, cohere.embed-*, cohere.rerank-v3-5:0)"
  severity: major
  test: 1
  root_cause: "discover_models filtered only on ON_DEMAND, ignoring modalities"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "no chat-capability filter on foundation models or profiles"
  missing:
    - "TEXT in/out modality filter + rerank/embed name backstop; profiles dropped only when positively non-chat"
  resolved_by: c85dcf5
  resolved_at: 2026-09-27
- gap_id: G-05-1c
  truth: "/model list is ABC-ordered with profile ARNs grouped per model"
  status: resolved
  reason: "User reported: filtered list unordered; same model repeats as configured id plus regional/global profile ARNs (multi-region blowup)"
  severity: minor
  test: 1
  root_cause: "Discovery order preserved; no normalization across direct ids and profile ARNs"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "no grouping/normalization of routes"
    - path: "strands_code_cli/router.py"
      issue: "single flat picker over raw discovered strings"
  missing:
    - "group_models by base key (strip ARN/provider/routing prefixes), ABC order, profiles-first routes; two-step picker with compact route labels"
  resolved_by: 3ad8c6a
  resolved_at: 2026-09-27
- gap_id: G-05-1d
  truth: "/model picker cascades vendor > family > model > route; /models aliases /model"
  status: resolved
  reason: "User reported: grouped list still too long for a tall screen; wants vendor/family stages (anthropic > claude/fable, openai > gpt/gpt-oss) plus /models alias"
  severity: minor
  test: 1
  root_cause: "Single-level group list still renders 100+ entries at once"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "no vendor/family nesting"
    - path: "strands_code_cli/router.py"
      issue: "flat group picker; no /models alias"
  missing:
    - "build_model_tree nesting with compound-family rule; cascade picker with single-child auto-advance; /models dispatch alias"
  resolved_by: 6e72f5d
  resolved_at: 2026-09-27
- gap_id: G-05-1e
  truth: "Cascade picker offers Back to the previous level at every non-top step"
  status: resolved
  reason: "User reported: at family/model/route levels there is no way back to the higher-level list"
  severity: minor
  test: 1
  root_cause: "Linear cascade with no backward path"
  artifacts:
    - path: "strands_code_cli/router.py"
      issue: "one-shot forward cascade"
  missing:
    - "Cascade loop with Back entries, pick memory, and auto-level skipping in both directions"
  resolved_by: 15867cb
  resolved_at: 2026-09-27
- gap_id: G-05-1f
  truth: "Top-level picker offers an explicit Cancel entry naming the current model"
  status: resolved
  reason: "User reported: alongside Back entries, the top level needs an explicit cancel/stay choice, not just ESC"
  severity: minor
  test: 1
  root_cause: "Top level had vendors + Custom only; cancel was ESC-only"
  artifacts:
    - path: "strands_code_cli/router.py"
      issue: "no explicit cancel option at cascade top"
  missing:
    - "Cancel (stay with <current>) entry returning Model unchanged"
  resolved_by: c3a02a5
  resolved_at: 2026-09-27
- gap_id: G-05-1g
  truth: "Mid-session switch to a non-reasoning model converts thinking blocks instead of crashing the turn"
  status: resolved
  reason: "User reported: Haiku to Gemma switch crashed the CLI with ValidationException (reasoning content rejected)"
  severity: blocker
  test: 1
  root_cause: "convert_history fail-open on unknown ids (gemma unlisted); no capability almanac; no turn-error guard"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "substring heuristics instead of a capability table"
    - path: "strands_code_cli/loop.py"
      issue: "no richest-variant preservation; provider errors killed the session"
  missing:
    - "Capability almanac (fail-closed thinking, fail-open media, same-vendor rule); RichHistory stash/restore; turn-error guard"
  resolved_by: f63d017
  resolved_at: 2026-09-27
- gap_id: G-05-1h
  truth: "Capability verdicts defer to the harness; aggregator ids resolve to true vendors"
  status: resolved
  reason: "User-directed follow-up: almanac was minimal-verified; align with harness thinking tables and handle OpenRouter-style aggregator ids"
  severity: minor
  test: 1
  root_cause: "Hand-maintained allowlist diverged from harness family knowledge; provider prefix masked true vendor"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "parallel capability universe; no aggregator see-through"
  missing:
    - "Defer to supports_thinking with static fallback; provider-aware media rules; au/jp prefixes; openrouter true-vendor parsing; signature-aware conversion"
  resolved_by: 7118336
  resolved_at: 2026-09-27
- gap_id: G-05-1i
  truth: "litellm installs as an optional extra; users can override capability verdicts in a config file"
  status: resolved
  reason: "User-directed: OpenRouter needs a real dependency story, and shipped verdicts need an aider-style user escape hatch"
  severity: minor
  test: 1
  root_cause: "No litellm distribution story; verdicts had no user correction path"
  artifacts:
    - path: "pyproject.toml"
      issue: "litellm extra missing"
    - path: "strands_code_cli/model_capabilities.py"
      issue: "override file did not exist"
  missing:
    - "litellm extra + install hint + env docs; model-capabilities.yaml loader with fail-soft merge and /context count"
  resolved_by: 1706106+7d61496
  resolved_at: 2026-09-27
- gap_id: G-05-1j
  truth: "picking a full inference-profile ARN from the picker switches to that profile"
  status: resolved
  reason: "Picker offered verbatim profile ARNs but the harness provider splitter rejects full ARNs — Gemma→Haiku switch-back crashed the session (ValueError: Unknown model provider 'arn:aws:bedrock:...:inference-profile')"
  severity: major
  test: 1
  root_cause: "Picker path skipped resolve validation; no ARN→tail normalization; switch ran after history mutation with no loop guard"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "no normalize; apply_switch resolved raw selection"
    - path: "strands_code_cli/router.py"
      issue: "picker returned verbatim ARNs; direct path validated raw selection"
    - path: "strands_code_cli/loop.py"
      issue: "apply ran switch-after-convert; model branch unguarded"
  missing:
    - "normalize_model_ref (profile ARN→tail) at router returns, direct-path validation, apply seam; switch-before-convert ordering; run_loop model-action guard"
  resolved_by: f429527
  resolved_at: 2026-09-27
- gap_id: G-05-1k
  truth: "switching back to a thinking model after resume restores its native thinking instead of stripping it"
  status: resolved
  reason: "Gemma→Haiku after resume warned 'Dropping reasoningContent' and text-ified Haiku's OWN thinking: the rich stash was in-memory only, so the same-vendor rule keyed provenance off the away model"
  severity: major
  test: 1
  root_cause: "RichHistory never persisted; restore guard trusted message count alone; text-ified traces were unlabeled (weak models mimicked them — Gemma plan-mode confabulation)"
  artifacts:
    - path: "strands_code_cli/loop.py"
      issue: "stash lost on resume; re-stash blamed the away model"
    - path: "strands_code_cli/model_switch.py"
      issue: "unlabeled trace text; no canonical prefix fingerprint"
  missing:
    - "persisted sidecar stash (bytes-safe JSON, fail-soft load, traversal guard); canonical-prefix-hash restore guard; provenance-follows-thinking re-stash; TRACE_LABEL on text-ified thinking; reset on /clear + /compact"
  resolved_by: fcab5ee
  resolved_at: 2026-09-27
