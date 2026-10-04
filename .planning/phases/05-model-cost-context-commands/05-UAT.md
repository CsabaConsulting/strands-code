---
status: testing
phase: 05-model-cost-context-commands
source: [05-SUMMARY.md]
started: 2026-09-27T12:00:00Z
updated: 2026-09-27T12:00:00Z
---

## Current Test

number: 6
name: Mid-turn /model refused
expected: |
  Typing /model while a turn is running prints the refusal text and
  the turn continues undisturbed.
awaiting: user response

## Tests

### 1. Switch models mid-session
expected: Launch the CLI, chat two turns, run /model, pick a different provider, and continue — the next answer is coherent and history is intact. Repeat with a custom id/ARN, including a us.-prefixed ARN.
result: pass
retest_after: G-05-1g
note: Re-tested 2026-09-27 on 8ca53ddd (Gemma relabel verified live; gaps G-05-1a..1n resolved). Llama streaming-tools remains an upstream limitation with an in-app warning, accepted.

### 2. Usage line and /cost
expected: After any turn a 451.27K (45%)-style usage line appears; /cost shows per-turn rows plus totals, with money figures only for priced ids.
result: pass
note: Verified 2026-10-04 on Gemma-3-27b (8ca53ddd): post-turn lines `12.66K (10%) $0.00` / `25.58K (20%) $0.01`; /cost rows + totals + `Prices: Bedrock live …` + footer. Kill-switch run showed tokens-only with `Prices: unknown.` Observation (not a gap): Gemma first answered a stale question (Belgium for Netherlands) in the 50+ message session, then self-corrected — model confusion, plus known plan-shape mimicry.

### 3. /context report
expected: /context shows tokens, percentage, message/tool counts, and provider/model name, all present.
result: pass
note: Verified 2026-10-04 (8ca53ddd, Gemma): header + `7.97K (6% of 128.00K)`, 63 messages, 0 tool calls, per-task 38.83K — all fields present.

### 4. /compact continuity
expected: /compact runs, the conversation continues, recent tool results are still referenced, and the last ask is re-grounded.
result: pass
note: Verified 2026-10-04 (8ca53ddd, Haiku): 3 tool calls made (fib, web_fetch, pi), `/compact` kept 11, Fibonacci 15th=377 and pi follow-ups correct post-compact, 16 messages + 3 tool calls after. Found G-05-4a (fixed same session).

### 5. /clear keeps session
expected: /clear prints `Context cleared — session <id> kept.`, the same session id stays resumable, and the model choice is kept.
result: pass
note: Verified 2026-10-04 (5f01fe51): exact reply, /context zeroed, fresh turn + model kept. Explicit exit+resume after /clear not pasted; accepted by note — every UAT run resumed successfully and /clear only wipes messages in place. Observation (out of scope): search_memory returns cross-session notes.

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
- gap_id: G-05-1l
  truth: "switching to amazon.nova-2-lite-v1:0 keeps image/video blocks (it takes TEXT+IMAGE+VIDEO)"
  status: resolved
  reason: "Live Bedrock modalities probe: nova-2-lite accepts IMAGE+VIDEO, but the nova-1 media-less rows matched it by substring ('lite' in 'nova-2-lite') and would placeholder-ize its media on switch"
  severity: major
  test: 1
  root_cause: "Generation-unscoped name substrings in _MEDIA_LESS"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "nova-1 rows over-matched nova-2 ids"
  missing:
    - "generation-scoped substrings (nova-micro/nova-lite); nova-2 regression assertions"
  resolved_by: c9de848
  resolved_at: 2026-09-27

- gap_id: G-05-1m
  truth: "Gemma answers on converted history with tools attached"
  status: resolved
  reason: "Gemma went deterministically mute (single empty text delta, ~130 billed tokens, 8/8 turns) on converted history with toolConfig. Live bisect isolated the trigger: our bracketed TRACE_LABEL pseudo-tag — not the trace content, orphans, length, or structure"
  severity: major
  test: 1
  root_cause: "Label shape ([...] pseudo-tag) mutes Gemma when tools attach; verified by substitution probes (bracketed mutes 8/8, paren/colon answers 3/3)"
  artifacts:
    - path: "strands_code_cli/model_switch.py"
      issue: "TRACE_LABEL shape muted Gemma"
  missing:
    - "relabel to paren/colon shape (live-verified); legacy label still stripped by canonical hash for pre-upgrade restore; retired labels migrate on convert"
  resolved_by: 71d261c+ed01b11
  resolved_at: 2026-09-27

## Unplanned additions (user-directed, 2026-09-27)

- Session deletion: `/forget <id-or-prefix>` + picker delete row (nested
  picker + explicit confirm, list refreshes). Shared `forget_session` core:
  snapshot dir (traversal-guarded), stash sidecar, index entry. Refuses the
  active session and ambiguous prefixes; pure-orphan dirs forgettable.
- Streaming-tool forewarning: almanac `supports_streaming_tools` (fail-open,
  overrideable `streaming_tools` field; llama3/llama4 rows from live
  probes). Warns in the `/model` reply, at startup on a known-bad
  persisted model, and hints `/model` on the matching turn failure.
  Advisory only — never gates conversion. Functional fix (non-streaming
  fallback) is upstream.
- Empty-turn retry: a turn that succeeds with zero content blocks (user
  message recorded, assistant empty — observed once on Gemma, 376 billed
  output tokens lost below the SDK) is dropped and re-run exactly once;
  usage prints per attempt, and a double-empty prints a notice instead
  of silence. Errors never retry; weird history shapes never retry.

## Live verification notes (2026-09-27, /tmp probes, not committed)

- OpenRouter (key quota restored): /models lists 466 models incl. 17 :free;
  live two-turn session via litellm/openrouter/qwen/qwen3.8-27b:free through
  harness resolve + bare strands Agent succeeded. Turn 1 emitted
  reasoningContent; turn 2 with thinking in history ACCEPTED. Our
  fail-closed aggregator verdict (strip on switch-to) stays: one qwen model
  does not prove all 466; per-model overrides exist for the exception.
- Nova 2 Lite (us-west-2): ListFoundationModels modalities TEXT+IMAGE+VIDEO
  in / TEXT out; served only via inference profile
  (global.amazon.nova-2-lite-v1:0 answers; FM id rejects on-demand).
  reasoningConfig enable emits native thinking; thinking-off replay of
  those blocks ACCEPTED (no ValidationException). Almanac keeps
  fail-closed reasoning (our turns run thinking-off) with the evidence
  recorded in code; media rows fixed per G-05-1l.

## Test 1 re-test (2026-09-27, session 8ca53ddd) — PASS (Llama excepted)

- Gemma relabel verified live: one switch deepseek→gemma healed the
  history via convert-time migration; Gemma answers directly (single
  usage line, no empty-turn notice). Mute fixed.
- Recall note (model capability, not our bug): Gemma listed 5/6
  countries, missing Switzerland; Haiku on the same history named all
  six plus the last-asked. No action.
- Plan-shape outputs from DeepSeek/Gemma are history mimicry: this
  50-message session still carries old plan-mode turns, and weaker
  models copy the shape (footer included). Same session, Haiku /
  Mistral / Qwen did not — not a mode-flag bug. Cosmetic; /compact
  would flush the old plan turns.
- G-05-1n (found in re-test, fixed 85c9fb4): 13 stability image-tool
  rows in the picker. Root: `discover_models` classified only
  ON_DEMAND models, so INFERENCE_PROFILE-only non-chat models never
  reached `non_chat_ids` and their profiles slipped through fail-open.
  Fix: classify every summary for the denylist, list bare ids only on
  ON_DEMAND chat. Live check us-west-2: 121 options, zero stability /
  embed / rerank. twelvelabs Pegasus (TEXT-out video model) remains —
  fail-open by design, one row.
- Nit (by design, D-02): `(n/a)` % and missing `$` on non-Anthropic
  models — MODEL_LIMITS/MODEL_PRICING know only Anthropic (+gpt-4o
  window); unknown ids fall back to tokens-only, never guessed.
  Consequence: no % and no 80% auto-compact for those models. The
  `context_window_limit not set` console line is the harness's own
  separate estimate, not ours. Almanac extension (documented windows /
  prices per Bedrock family) offered, scope pending.

## Live price/window almanac (2026-10-04, option (a) + OpenRouter)

- New `strands_code_cli/live_pricing.py`: layered display-only
  resolution. Prices: Bedrock Price List (24h disk cache, standard
  on-demand tier only) -> OpenRouter /models (24h cache, routed ids
  only) -> LiteLLM bundled model_cost (when installed) -> static
  table. Windows: OpenRouter context_length -> LiteLLM
  max_input_tokens -> static (no AWS API exposes windows).
- Price List findings (live): Bedrock model APIs carry no
  window/price fields; `AmazonBedrock` Price List records do, keyed by
  parsing `usagetype` (region prefix + `-(input|output)-tokens` +
  tier). `inferenceType`/`feature` are unreliable tier signals
  (priority records claim On-demand; batch shares Input tokens), so
  the usagetype suffix (exactly `-tokens` or `-tokens-standard`) is
  the arbiter. Routed ids (`us.*`) deliberately miss live (they pay
  cross-region prices) and fall to LiteLLM/static.
- OpenRouter `/models` verified public (no key): per-token USD +
  context_length for 466 models; only consulted for openrouter-routed
  ids (the billing party prices the call).
- `/cost` gains a `Prices: <provenance>.` line; every layer fails
  soft; stale cache serves during outages with 10-min cooldown;
  `STRANDS_CODE_NO_LIVE_PRICING=1` forces static-only (suite-wide
  hermetic default via tests/conftest.py).
- Live cross-check us-west-2: Mistral Large 3 $0.50/$1.50, Gemma 27B
  $0.23/$0.38, Qwen3 32B $0.15/$0.60 (all match LiteLLM to the cent);
  us.Haiku 4-5 falls to LiteLLM $1.10/$5.50 (routed form). No
  user-facing source toggle: automatic layering already yields the
  most precise available number, provenance shows what won.

## /cost refresh + table (2026-10-04)

- `/cost refresh` force-refetches both live sources (bypasses TTL +
  cooldown, failures reported inline, stale kept); `/cost table
  [filter]` lists cached Bedrock rows (readable record names now
  stored) + OpenRouter rows + the static fallback without touching
  the network (40 rows/section cap, filter narrows). Usage:
  `/cost [refresh|table [filter]]`. Live: 99 Bedrock + 466 OpenRouter
  rows in us-west-2.

## GPT-on-Bedrock pricing gap (2026-10-04)

- Why `/cost table openai` shows only gpt-oss: AWS publishes no Price
  List records for Bedrock-hosted GPT models — 800 OpenAI records
  scanned across all regions, zero non-oss, and the public pricing
  page's per-region tables list gpt-oss only. The GPT models are
  INFERENCE_PROFILE-only and new; not our tier filter (unfiltered
  scan; profile-only nova2.0lite IS present in the cache).
- Mitigation: LiteLLM prices them under `bedrock_mantle/` keys (31
  keys, 7 vendors), which our lookup now tries. `openai.gpt-5.4`
  resolves $2.75/$16.50 @ 1.05M via LiteLLM bundled; refreshes pick
  up live AWS records automatically if/when published.

- gap_id: G-05-4a
  truth: "/cost prices each turn at its own turn model after mid-session switches"
  status: resolved
  reason: "Spotted in Test 4 transcript: Gemma turns ($0.0030/$0.0060) repriced to $0.0152/$0.0301 after switching to Haiku — rows stored tokens only, report priced everything at the active model"
  severity: major
  test: 4
  root_cause: "record_turn_metrics stored no model; cost_report priced all rows at the report model_id"
  artifacts:
    - path: "strands_code_cli/loop.py"
      issue: "turn rows lacked the turn model"
    - path: "strands_code_cli/cost_context.py"
      issue: "single-model pricing + provenance for mixed-model rows"
  missing:
    - "per-row turn model with report-model fallback; per-row pricing; mixed provenance label"
  resolved_by: b24b188
  resolved_at: 2026-10-04
