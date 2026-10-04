---
phase: 05-model-cost-context-commands
verified: 2026-10-04T21:06:54Z
status: passed
score: 3/3 must-haves verified
covered_files:
  - .planning/phases/05-model-cost-context-commands/05-CONTEXT.md
  - .planning/phases/05-model-cost-context-commands/05-PLAN.md
  - .planning/phases/05-model-cost-context-commands/05-RESEARCH.md
  - .planning/phases/05-model-cost-context-commands/05-SUMMARY.md
  - .planning/phases/05-model-cost-context-commands/05-UAT.md
  - .planning/phases/05-model-cost-context-commands/05-SECURITY.md
  - strands_code_cli/model_switch.py
  - strands_code_cli/model_capabilities.py
  - strands_code_cli/cost_context.py
  - strands_code_cli/live_pricing.py
  - strands_code_cli/router.py
  - strands_code_cli/loop.py
  - strands_code_cli/steering.py
  - strands_code_cli/main.py
  - strands_code_cli/provider_config.py
  - strands_code_agent/utils.py
covered_digest: "v1:sha256:41fd83c48c091c644bfb6fb33d28ff26e339dba811fe9d24eab85d3275293008"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: none
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 5 Verification: Model + Cost + Context Commands (MODEL-01, MODEL-02, SES-02)

**Verified:** 2026-10-04 (gsd-verifier, independent read of code, not SUMMARY claims)
**Scope:** 05-PLAN.md must_haves (3 truths, 6 artifacts, 4 key_links, 9 prohibitions)
+ MODEL-01/MODEL-02/SES-02 + D-01..D-08 + UAT log + SECURITY register
**Test runs (this session):** phase
`tests/test_model_switch.py tests/test_cost_context.py tests/test_live_pricing.py`
→ **178 passed**; full `tests/` → **668 passed, 5 deselected** (pre-existing
integration deselects)

(Digest method: sha256 over the concatenated covered files in listed order.)

## Truths

### T1 — PASS — Idle-prompt /model switches providers, same conversation converted or compacted (MODEL-01, D-01..D-06)
- `strands_code_cli/router.py:194-393` — `_model_message` never swaps inline:
  bare `/model` offers the discovered cascade (vendor > family > model > route
  with Back/Cancel, `router.py:240-370`) or a non-tty listing; direct arg
  validates via `resolve_model` on the normalized ref (`router.py:387-393`),
  ValueError → reply listing providers, ImportError → fail-soft reply with
  install hint. Success returns `("model", new_id)` only.
- `strands_code_cli/loop.py:427-511` — `apply_model_action` owns the swap:
  `turn_running` → `MODEL_REFUSAL` verbatim (`loop.py:455-456`,
  text at `model_switch.py:27` matches the plan's exact refusal copy);
  otherwise switch-before-convert (resolve raises before any history mutation,
  `loop.py:457-460`), rich-stash restore when returning to a same-vendor
  thinking model, `convert_history`, convert-when-fits else compact
  (`loop.py:480-492`), reply `Model: <id> — conversation continued
  (<n> messages kept|compacted)` (`loop.py:508-511`, plan shape plus
  optional `, thinking restored` suffix and streaming-tools advisory).
- `strands_code_cli/loop.py:591-609` — run_loop applies the `("model", …)`
  action only at idle (dispatch happens outside any turn), persists the
  verbatim selection via `ProviderConfig.save_model_choice`, flushes via
  `explicit_save`; any exception → `Model switch failed (…); session
  unchanged`, session survives.
- `strands_code_cli/model_switch.py:265-340` — `convert_history` rewrites SDK
  ContentBlocks only: thinking round-trips only when harness-verified,
  same-vendor, and signed/redacted, else labeled trace text + warn
  (`model_switch.py:299-317`, DeepSeek-drop mirror); toolUse/toolResult
  deepcopy byte-identical (`model_switch.py:337-338`); media → placeholder
  text on media-less targets; legacy trace labels migrate; never trims.
- `strands_code_cli/model_switch.py:390-457` — `discover_models` lazy boto3,
  ON_DEMAND + inference profiles, verbatim ids/ARNs, chat-capability filter
  with fail-open profiles and full-summary denylist; any failure →
  `(fallback, True)`, never raises, never prompts.
- `strands_code_cli/model_switch.py:607-646` — `normalize_model_ref` strips
  only the `:inference-profile/` ARN envelope (routing prefixes intact);
  `apply_switch` is the tracer-winning in-place seam (`agent.model = …`,
  rebuild path deleted).
- Mid-turn steering path: `strands_code_cli/steering.py:65-82`
  `mid_turn_slash_reply` refuses `/model` mid-turn with MODEL_REFUSAL verbatim
  and never arms steering (G-05-6a fix); reader routes slash lines to
  `on_refusal` (`steering.py:299-306`).
- Capability verdicts defer to the harness with fail-closed static fallback
  (`model_switch.py:140-161`), aggregator see-through (`model_switch.py:86-87,
  479-482`), user overrides fail-soft (`model_capabilities.py:55-128`,
  symlink refusal + unknown-key skip).
- Custom endpoints: `main.py:80-97` `model_for_config` builds `OpenAIModel`
  with `client_args={"base_url": …}` (key never persisted);
  `provider_config.py:19,37` persists `model` + non-secret `base_url` only.

### T2 — PASS — Post-turn usage line + /cost, display only, never enforcement (MODEL-02, D-07)
- `strands_code_cli/cost_context.py:157-172` — `format_usage` renders the
  `451.27K (45%)` shape with `n/a` % on unknown windows; `usage_line`
  appends `$` money only on a price hit.
- `strands_code_cli/cost_context.py:110-145` — `price_for`/`window_for`/
  `cost_for`: live layers first, static `MODEL_PRICING`/`MODEL_LIMITS`
  (`cost_context.py:25-61`), else None → tokens-only fallback, never
  family inference.
- `strands_code_cli/cost_context.py:175-220` — `cost_report` per-turn rows
  (turn #, in/out tokens, cost-if-priced) priced at each row's own turn
  model (G-05-4a), session totals, `Prices: <provenance>.` line, and the
  `Display only — no budgets or enforcement.` footer.
- `strands_code_cli/loop.py:149-178` — `record_turn_metrics` appends one row
  per turn with the turn model and returns the usage line; `loop.py:656-658`
  prints it after every turn. `strands_code_agent/utils.py:10-41` extends
  `get_response_metrics` with backwards-compatible `model_id`/`price_table`
  kwargs (signature unchanged, CLI passes the table in).
- `strands_code_cli/router.py:138-153` — `/cost [refresh|table [filter]]`
  reply branch; refresh/table are read-only inspection over fail-soft caches.
- `strands_code_cli/live_pricing.py` — layered display-only resolution
  (Bedrock Price List 24h cache → OpenRouter /models → LiteLLM bundled →
  static; windows OpenRouter → LiteLLM → static); every layer fails soft to
  the next, nothing raises to callers, `STRANDS_CODE_NO_LIVE_PRICING=1`
  forces static-only. No value on any cost path can halt, deny, or redirect
  a turn (no enforcement logic anywhere; bleed grep below).

### T3 — PASS — /compact, /clear, /context keep the user's place; 80% auto-compact preserves tool pairs (SES-02, D-08)
- `strands_code_cli/router.py:156-185` — `/compact`, `/clear`, `/context`
  reply branches; `router.py:20-26` USAGE_HINT lists all five new commands.
- `strands_code_cli/cost_context.py:355-380` — `context_report` renders the
  exact item-3 field list: input tokens + % of window, message count,
  tool-call count, per-task accumulated tokens, current provider/name
  (plus capability-override count only when active).
- `strands_code_cli/cost_context.py:471-525` — `compact_messages`:
  summarize-old + keep-recent-verbatim, pair-atomic cut
  (`_pair_safe_start`, `cost_context.py:443-468`), untrusted-marker prefix
  (`SUMMARY_MARKER`, never a tool result), credential-scrubbed summarizer
  input (`scrub_credentials`, `cost_context.py:391-396`), last-user-message
  replay; mutates `agent.messages` in place, caller flushes.
- `strands_code_cli/cost_context.py:528-532` — `clear_messages` wipes in
  place; `router.py:169-176` replies `Context cleared — session <id> kept.`
  Session id, index entry, and model choice are untouched (no id/title/model
  mutation in the clear path).
- `strands_code_cli/loop.py:181-194` — `maybe_auto_compact` fires at
  `AUTO_COMPACT_PCT = 80` (`cost_context.py:19`), skips unknown windows,
  announces `Context at <p>% — auto-compacted, <n> recent messages kept.`;
  `loop.py:681-685` flushes after auto-compact. No separate warning UI —
  the live context-% line is the pressure signal (D-08).
- `loop.py:584-589` — `/compact`/`/clear` flush via `explicit_save` +
  `index.ensure` and reset the persisted rich stash (so post-compact
  switch-backs cannot restore stale thinking).

## Key links — all hold
- K1 loop applies the swap, router never swaps mid-turn: `router.py:194-393`
  returns `("model", …)` or replies; `loop.py:591-609` applies at idle;
  mid-turn gets the refusal via `loop.py:455` and `steering.py:78-81`.
  No queue-until-idle anywhere (no queue primitive on the /model path).
- K2 SDK-ContentBlock conversion + adapter-owned wire format:
  `convert_history` touches only SDK blocks (`model_switch.py:265-340`);
  provider instances come from `resolve_model` (`model_switch.py:644`) or
  the internal `OpenAIModel` constructor (`main.py:97`); no hand-rolled
  vendor JSON (no vendor payload builders in `strands_code_cli/`).
- K3 spend extends metrics with static-table prices; unknown ids degrade:
  `utils.py:36-41` threads `price_table`; `cost_context.py:110-137`
  degrade to tokens-without-%/money.
- K4 compact/clear mutate `agent.messages` in place, keep session id +
  index entry, flush via `explicit_save`: `cost_context.py:493-532`,
  `loop.py:584-589,606,684,702`. SessionIndex never touches blobs
  (regression: full suite green, prior Phase 1 truths intact).

## Prohibitions (9/9 hold)
- P1 no mid-turn switch or queue — PASS: refusal-only paths above; no queue.
- P2 no hand-rolled vendor translation — PASS: adapter paths only (K2).
- P3 no ARN-prefix normalization — PASS: `normalize_model_ref` strips only
  the ARN envelope; routing prefixes (`global./us./eu./apac./au./jp.`)
  preserved (`model_switch.py:460-461,607-623`); picker values verbatim.
- P4 no budgets/enforcement — PASS: `budget|enforce|halt|quota` over the
  three phase modules hits only display-only negations (docstring +
  footer, `cost_context.py:4-5,176,219`); no enforcement logic.
- P5 no auto-routing/yolo/effort//btw/skills surface — PASS:
  `auto.*rout|smart.*model|enable_trust|cedar` hits only pre-existing
  prohibitive comments in policy/main modules; `yolo|/btw|/init|/memory`
  absent from router/loop. (`/forget` + picker delete flow is
  UAT-documented user-directed scope, not a listed prohibition.)
- P6 no persisted keys — PASS: `api_key|bearer|secret` hits only the
  defensive scrub regex (`cost_context.py:385`) and a `non-secret` docstring;
  `provider_config.py` persists model + base_url host under existing 0o700 +
  atomic-replace + symlink-refusal; OpenRouter fetch keyless, caches hold
  prices/windows only.
- P7 no hand-read snapshot blobs — PASS: all history ops mutate
  `agent.messages`; flush via `explicit_save`.
- P8 no env-sniff for provider auth; no new logging on agent-visible paths;
  absolute imports — PASS with one judgment call: zero `logger`/`print`/
  `logging` in model_switch/cost_context/live_pricing; absolute imports
  only; no `os.getenv` in phase modules. `live_pricing.py:339` reads
  `AWS_REGION`/`AWS_DEFAULT_REGION` inside `resolve_region` — this is
  *region selection* for the display-only Price List query (auth rides the
  ambient boto3 chain), not provider-auth sniffing, so it stays inside the
  prohibition's auth scope. `STRANDS_CODE_*` reads are the app's own
  kill-switch/cache overrides.
- P9 (plan assumptions honored) — tracer observations recorded in
  `tests/test_model_switch.py:1-31` and `tests/test_cost_context.py:1-22`
  docstrings (swap winner, snapshot mechanics, pricing/window sources,
  ARN verbatimness); no new dependencies (stdlib + installed
  strands/harness/boto3; `litellm` is an optional extra with install hint
  per G-05-1i, no pins added); schema-gate clean (ProviderConfig gains only
  `base_url`, SessionIndex untouched).

## Requirements coverage (every ID accounted for)
- MODEL-01 — SATISFIED: T1 evidence above; UAT Test 1 pass (live picker +
  custom id/ARN incl. `us.`-prefixed, gaps G-05-1a..1n resolved).
- MODEL-02 — SATISFIED: T2 evidence above; UAT Test 2 pass (live usage
  lines + `/cost` rows/totals/provenance/footer on 8ca53ddd).
- SES-02 — SATISFIED: T3 evidence above; UAT Tests 3/4/5 pass (`/context`
  fields, `/compact` continuity with pair preservation + replay, `/clear`
  keeps id + model).

## UAT log check — body supports 10/10 pass
- Manual Tests 1–7: each `result: pass` with dated live-session notes
  (8ca53ddd/5f01fe51), including the mid-turn refusal re-test (G-05-6a)
  and the ruled offline test (STS preflight makes literal no-creds REPL
  unreachable by D-05 design; automated fallback tests pin the picker).
- Automated Tests 8–10 (D1/D2/D3): `result: pass`, matching the coverage
  refs — `TestIdleOnlySwap` (`test_model_switch.py:1898`),
  `TestCostReport` (`test_cost_context.py:239`), `TestContextOps`
  (`test_cost_context.py:284`), all green this session.
- Hygiene note (not a gap): the UAT frontmatter/summary block is stale
  (`status: testing`, `passed: 3, pending: 7`) and contradicts the body
  where all 10 tests read `pass`. The body is the record; counters need a
  closeout refresh (left untouched — planning files out of scope for edits).

## SECURITY register — verified, 0 open
- `05-SECURITY.md`: `status: verified`, `threats_open: 0`, 15/15 closed
  with line-anchored mitigations. Spot-checked T-05-01 (refusal +
  steering slash path), T-05-03 (fail-closed thinking strip +
  harness deferral), T-05-06 (marker + scrub), T-05-10 (no key sinks),
  T-05-13 (display-only), T-05-15 (80% gate + unknown-window skip) —
  all match the current code.

## Regression check (Phases 1–4)
- Full suite **668 passed, 5 deselected** (up from 525 at SUMMARY time —
  UAT-gap tests added, none removed); Phase 1–4 suites green unmodified.
- Phase 4 locks re-grepped: exactly one `HumanInTheLoop(` site
  (`policy_gate.py:516`); no re-entrant `agent(` in steering.py (docstring
  mention only); no `.cancel()` in loop/steering; `/approve` handoff and
  gate/reader protocol untouched by the Phase 5 diff (loop additions are
  the model action branch, usage line, auto-compact, turn-error guard,
  empty-turn retry — all additive).

## Scope notes (user-directed, UAT-documented — not gaps)
- Live price/window almanac (`live_pricing.py`, `/cost refresh|table`)
  supersedes the plan's static-only stance ("No live pricing API") per the
  UAT-recorded option-(a) direction; display-only posture preserved
  (cached, fail-soft, provenance-labeled). Static tables remain the
  hermetic fallback (suite default via conftest kill-switch).
- `/forget` + picker delete, streaming-tool forewarning, and empty-turn
  retry are logged as user-directed unplanned additions with fixes pinned
  by tests; none violate a prohibition.
- Residuals carried (documented, not closed): local estimator accuracy
  (A-6), static-table staleness (periodic re-check of the Bedrock pricing
  page), Llama streaming-tools as an upstream limitation with in-app
  warning, live cross-provider turns beyond the UAT probes.

## Follow-ups (closeout, not verification gaps)
- Flip MODEL-01/MODEL-02/SES-02 to checked in `.planning/REQUIREMENTS.md`
  and the traceability rows from Pending → Complete.
- Refresh the `05-UAT.md` summary counters/status to match the 10/10-pass body.
