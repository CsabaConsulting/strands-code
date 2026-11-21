# Phase 10: Provider-Reported Turn Spend - Research

**Researched:** 2026-10-12
**Domain:** OpenRouter per-request cost capture (`usage.cost`) + Strands SDK usage surfacing + `/cost` display
**Confidence:** HIGH (every load-bearing claim verified live this session: real OpenRouter chat calls, real generation lookups, real LiteLLM passthrough, installed-SDK source reads)
**Dispatch note:** Produced via generic-agent workaround (typed `gsd-phase-researcher` dispatch unavailable); follows the role contract and provenance rules.

## Summary

OpenRouter reports authoritative per-request USD cost inline on every chat completion as `usage.cost` (plus `usage.cost_details` and `usage.is_byok`) — non-streaming and streaming alike — immediately, with no extra lookup. I verified this live: a `gpt-4o-mini` call returned `"cost": 2.4e-06` inline, the streaming final chunk carried the identical shape, and a `:free` model returned `"cost": 0` (int zero). The alternative `GET /api/v1/generation?id=` path works but is delayed (404 immediately and at +5s, 200 with `total_cost` only at +15s) — it races aggregation and cannot serve the post-turn usage line, so the plan must use inline `usage.cost` only.

The capture problem is that the Strands SDK drops the field: `LiteLLMModel` yields the raw LiteLLM `Usage` object (which preserves `.cost` — verified live through real `litellm.completion` calls), but `OpenAIModel.format_chunk` maps only `prompt/completion/total_tokens` (+ cache tokens) into the `metadata` chunk, and `EventLoopMetrics._accumulate_usage` sums only token keys. So `result.metrics` — the CLI's only usage source today — can never carry cost. The fix is a thin CLI-owned `LiteLLMModel` subclass overriding `format_chunk` to record the raw cost per cycle into an instance side-channel (chunks stay byte-identical, zero agent-loop risk), wrapped at model-resolution time for openrouter-routed ids only, drained per turn by `record_turn_metrics`, and rendered by `cost_report` with actual-wins precedence. Bedrock reports no per-request cost (Converse `usage` is tokens-only; dollars live in CUR/Cost Explorer at daily grain) and stays estimate per D-07.

**Primary recommendation:** Capture inline `usage.cost` via a `format_chunk`-overriding `LiteLLMModel` subclass applied only to `litellm/openrouter/*` ids at the three resolve sites; store `reported_cost` per session-turn row; render actuals with an inline marker and a blended total + split, with literal `0.0` displayed as a marked actual zero.

## User Constraints

### Actual-vs-estimate marking
- **D-01:** Per-turn `/cost` rows distinguish reported actuals from estimates with an inline marker (no separate column, no footer-only note).
- **D-02:** The post-turn usage line carries the same marking as `/cost` rows.
- **D-03:** Bare `$` keeps today's meaning (an estimate); only actuals get marked. Follows the Phase 9 computed-rate marker precedent.
- **D-04:** Routing/decision spend lines adopt the same actual marker for consistency across `/cost`.

### Missing-cost fallback
- **D-05:** An OpenRouter main turn with no reported `usage.cost` falls back to the tokens × almanac-rate estimate (NOT the Phase 8 decision rule of rendering zero — main turns stay informative).
- **D-06:** When neither a reported cost nor an almanac price exists, the row stays tokens-only (today's money-only-on-hit rule, unchanged).
- **D-07:** Bedrock and offline turns keep estimates exactly as today; only OpenRouter-reported turns change. No billing-API reach for Bedrock this phase.

### Session totals
- **D-08:** Mixed sessions show a blended headline total plus an actual/estimated split beneath it.
- **D-09:** No-double-counting rule: a turn contributes either its reported actual or its estimate to the total, never both — actual wins when present.
- **D-10:** Routing/decision spend stays included in the session total as reported actuals.
- **D-11:** When a session has no actuals at all, the split is hidden entirely and today's plain total shows (no not-available clutter).

### the agent's Discretion
- Literal `0.0` reported cost: whether a `usage.cost` of exactly 0.0 displays as a marked actual zero or falls back to the estimate path — planner/researcher decides (user said "you decide").
- Exact marker text/symbol for actuals; exact split layout beneath the headline total.

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-05 | `/cost` shows provider-reported actuals for main turns where supplied (OpenRouter), estimates elsewhere, without double counting | Inline-`usage.cost` capture seam (subclass + wrap sites + drain); actual-wins data model; marker/split display contract; 0.0 ruling; Bedrock-stays-estimate confirmation |

## Project Constraints (from AGENTS.md)

Actionable directives the planner must honor (AGENTS.md maps the older `strands_code_agent/` tree, but these survive as project posture; 10-CONTEXT.md §Canonical References supersedes for CLI orientation):
- Python ≥3.10, `uv` toolchain; stdlib-only HTTP via `urllib` (no `requests`; this phase needs no new transport — cost arrives inside the existing LiteLLM stream).
- AWS-optional, never AWS-required; offline default holds (D-07/D-09: Bedrock/offline paths untouched).
- No upper pins during the experimental phase.
- `snake_case` modules/functions, `UPPER_SNAKE_CASE` constants, `PascalCase` classes; one import per line, absolute imports.
- Fail-soft read paths (return degraded values, never raise to callers); log-and-continue for best-effort cleanup only.
- Module `logger = logging.getLogger(__name__)` with `%s`-style args; no `print()` in library code (transcript prints live in the turn layer via `print_plain`, markup off — WR-06).
- Why-comments only (1–2 lines); docstrings on public functions/classes.
- Constructor-kwarg configuration, never env sniffing (exception: runtime credentials read at call time inside engine functions only — this phase reads NO credentials at all; cost capture rides the existing authenticated stream).
- No keys in repo; API keys header-only, never logged. Research probes read `OPENROUTER_API_KEY` from env at call time only; /tmp scratch only.
- Test files mirror modules: `tests/test_<module>.py`; pytest with `integration` marker deselected by default [VERIFIED: pyproject.toml] (`addopts = "-m 'not integration'"` — same config cited in 08-RESEARCH.md).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Raw `usage.cost` capture per model cycle | CLI-owned `LiteLLMModel` subclass (model layer) | — | Only code that sees the raw LiteLLM `Usage` before `format_chunk` drops cost; chunks stay byte-identical |
| Wrap-at-resolve for openrouter-routed ids | CLI model wiring (`apply_switch`, routed/side resolve, initial build) | — | `resolve_model` uses pre-built `Model` instances verbatim, so wrapping is a local call-site change |
| Per-turn drain + row storage (`reported_cost`) | Turn loop (`record_turn_metrics`) | — | Single choke point already appending every per-turn row (main, btw, revise, idle-drain) |
| Actual-wins totals, marker, split display | `cost_context.py` (`cost_report`, `usage_line`) | — | Owns all `/cost` rendering + the `_reported_spend` precedent |
| Cost truth itself | OpenRouter inline `usage` | — | Authoritative per-request USD; no local recomputation |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Installed `strands` SDK (`models.litellm`, `models.openai`) | 1.58.1 (locked) | Subclass seam (`format_chunk` override) + inherited `stream_options` default | The drop point and the capture point are both here; no SDK change needed |
| Installed `strands_harness.models.resolve_model` | 0.1.2 (locked) | Verbatim pass-through of pre-built `Model` instances | Lets the CLI inject the subclass without touching the harness |
| stdlib `urllib` + `json` | builtin (Python ≥3.10) | Zero new transports (cost rides the existing stream) | Locked posture; nothing to add |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 (locked) | Hermetic wrapper/drain/display tests | All phase tests; live tests behind `integration` marker |
| `litellm` extra | ≥1.104 (optional extra, NOT currently installed) | Live verification of the capture path | Integration test only; hermetic tests fake the `Usage` object |

**Package Legitimacy Audit:** skipped — this phase installs zero packages (stdlib + locked deps only; the `litellm` extra is only needed to *run* the live integration test, not to ship the phase).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `format_chunk`-override subclass | `litellm.success_callback` global hook | Global mutable state; correlating callbacks to turns across parallel main+btw agents is fragile — use the instance side-channel |
| Inline `usage.cost` | `GET /api/v1/generation?id=` lookup per turn | Delayed 6–15s (verified 404→200), extra round-trip per request, and Strands drops the generation id too — reject entirely, not even as fallback |
| Instance side-channel drain | Injecting `cost` into the `metadata.usage` dict | `_accumulate_usage` sums only known token keys, so injected cost would NOT accumulate; also mutates the SDK-visible chunk shape — use the side-channel |

## Cost Source Reference (verified live 2026-10-12)

### OpenRouter inline `usage.cost` (THE source — use this)
- Every chat completion returns `usage.cost` (USD, float) inline: non-streaming responses AND the streaming final chunk (Strands always sends `stream_options={"include_usage": True}` by default [VERIFIED: strands/models/openai.py:515] (`stream_options = params.pop("stream_options", {"include_usage": True})`), which LiteLLM translates for OpenRouter) [VERIFIED: live probes 1+3 this session].
- Verbatim non-streaming `usage` (gpt-4o-mini, 12 in / 1 out) [VERIFIED: live probe]:
```json
{"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13, "cost": 2.4e-06,
 "is_byok": false,
 "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0},
 "cost_details": {"upstream_inference_cost": 2.4e-06, "upstream_inference_prompt_cost": 1.8e-06,
                  "upstream_inference_completions_cost": 6e-07},
 "completion_tokens_details": {"reasoning_tokens": 0, "image_tokens": 0, "audio_tokens": 0}}
```
- Streaming: identical `usage` object on the final `chat.completion.chunk` (3 chunks total for a 1-token reply; `provider: "Azure"` named per-chunk) [VERIFIED: live probe]. Response top-level keys: `choices, created, id, model, object, provider, service_tier, system_fingerprint, usage`; `id` is the `gen-...` generation id.
- Timing: immediate — present in the response that ends the request. No polling, no delay [VERIFIED: live probe].
- Free-tier: `:free` models report `"cost": 0` (JSON int zero, all `cost_details` zero) [VERIFIED: live probe on `apodex/apodex-1.1-mini:free`]. This is a *present* zero, not an absent cost — see the 0.0 ruling below.
- Docs corroboration: `usage.cost` + `cost_details` documented on the chat-completion reference and the usage-accounting cookbook (`usage: { include: true }` for streaming) [CITED: https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion, https://openrouter.ai/docs/cookbook/administration/usage-accounting].

### Generation-id lookup (REJECTED — documented so the planner never retries it)
- `GET /api/v1/generation?id=<gen-id>` (Bearer auth) returns `data: {total_cost, usage, tokens_prompt, tokens_completion, cache_discount, ...}` [VERIFIED: live probe at +15s: `total_cost: 2.4e-06, usage: 2.4e-06, tokens_prompt: 1, tokens_completion: 2, cache_discount: null`].
- BUT it 404s immediately after the request AND at +5s (verified twice, two ids), succeeding only at +15s — OpenRouter-side aggregation delay, matching the reported race where early lookups return null [VERIFIED: live probe; CITED: TanStack/ai#468 discussion of the `/generation` race].
- Two further disqualifiers: one extra HTTP round-trip per turn, and the CLI would still need the generation `id`, which Strands drops exactly like cost. No fallback role: a delayed backfill would rewrite already-printed usage lines and complicate the no-double-count model for zero gain over inline cost.

### LiteLLM passthrough (the capture enabler)
- `litellm.completion(model="openrouter/...")` preserves everything: `response.id` is the `gen-...` id, and `response.usage` is a `Usage` object with `.cost = 2.4e-06`, `.is_byok = False`, `.cost_details = {...}` — both non-streaming and streaming-with-`stream_options` [VERIFIED: live probe 3, litellm ≥1.104]. `hidden_params` was empty (no cost there — read `.cost` on `usage`).
- Caveat: bare `stream=True` with NO `stream_options` yields NO usage chunk at all [VERIFIED: live probe 4] — but that path never occurs under Strands, which always sends `include_usage` (see above). Hermetic tests must construct the `Usage`-shaped fake directly, never rely on this.

### Strands surfacing (the gap this phase bridges)
- `LiteLLMModel.stream` yields `format_chunk({"chunk_type": "metadata", "data": response.usage})` per request, both modes [VERIFIED: strands/models/litellm.py:564,613-614] (`yield self.format_chunk({"chunk_type": "metadata", "data": response.usage})` / `if usage := getattr(event, "usage", None):`).
- `OpenAIModel.format_chunk` `case "metadata":` maps ONLY `prompt_tokens/completion_tokens/total_tokens` (+ `cached_tokens`, `cache_write_tokens`) into `usage_data` — `.cost`/`.cost_details`/`.is_byok` are silently dropped [VERIFIED: strands/models/openai.py:601-624] (`"inputTokens": event["data"].prompt_tokens,` …).
- `Usage` is `class Usage(TypedDict, total=False)` with only token keys declared [VERIFIED: strands/types/event_loop.py:8]; `EventLoopMetrics._accumulate_usage` sums exactly `inputTokens/outputTokens/totalTokens` + the two cache keys [VERIFIED: strands/telemetry/metrics.py:370-378] (`target["inputTokens"] += source["inputTokens"]` …). Extra keys would neither accumulate nor typecheck — hence the instance side-channel, not chunk injection.
- `LiteLLMModel(OpenAIModel)` with no `format_request` override [VERIFIED: strands/models/litellm.py:37] (`class LiteLLMModel(OpenAIModel):`), so both the `stream_options` default and the `format_chunk` drop are inherited — one subclass override point covers both modes.
- Callback-handler path carries no cost either: `process_stream` re-yields already-formatted chunks, so by the time any hook/callback sees `metadata`, cost is gone. There is no existing hook that sees the raw provider payload.

### Model-id routing (which turns are OpenRouter turns)
- The harness has NO `openrouter` provider (`_PROVIDERS` = bedrock, bedrock-mantle, anthropic, openai, google, ollama, litellm) [VERIFIED: strands_harness/models.py:296-303]; OpenRouter main turns travel as `litellm/openrouter/<model>` through `LiteLLMModel` [VERIFIED: strands_code_cli/live_pricing.py:357-368] (`for prefix in ("litellm/openrouter/", "openrouter/"):`).
- `resolve_model` uses a pre-built `Model` instance verbatim [VERIFIED: strands_harness/models.py:423] (`A passed-in ``Model`` or ``ModelRouter`` instance is used verbatim: its provider is unknown, so`), with `effort`/`caching` ignored + warned — so the wrapper must be constructed with reasoning already configured (or only wrap when effort is auto/off; planner scopes this).

### Bedrock cost reporting (confirmed: none — stays estimate per D-07)
- Bedrock passthrough: `BedrockModel` copies `response["usage"]` verbatim into the metadata chunk (no cost mapping exists because Converse returns none) [VERIFIED: strands/models/bedrock.py:1666-1670] (`metadata["metadata"]["usage"] = response["usage"]`).
- Converse returns a normalized envelope (`output`, `stopReason`, `usage`, `metrics`); `usage` carries only input/output/total (+ cache) token counts [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference]. Per-request dollars exist only in model invocation logs (token counts you convert yourself) and CUR/Cost Explorer at per-usage-type-per-day grain — never inline, never per-request [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/cost-management]. No billing-API reach this phase (D-07).

## Architecture Patterns

### System Architecture Diagram

```text
OpenRouter chat API ──► litellm SDK ──► CostAwareLiteLLMModel.format_chunk ──► Strands chunks (unchanged)
  usage.cost inline        (preserves         │ "metadata" → record raw            │ tokens only,
  per request              .cost — verified)  │ cost to instance list              ▼
                                             │ then delegate to super()     event loop → result.metrics
                                             │ (bytes-identical chunks)           │ (tokens only, as today)
                                             ▼                                    ▼
                                    per-agent side-channel              record_turn_metrics(result, model, rows)
                                    (one list per model                       │ drains side-channel,
                                     instance — NEVER shared                  │ appends row {turn, in/out,
                                     between main + btw)                      │ model, reported_cost?}
                                                                              ▼
                                                              cost_report: actual-wins per row,
                                                              blended total + split, inline marker
```

Data flows one way: provider truth → instance side-channel → turn row → display. The agent loop, event stream, and `result.metrics` shapes are untouched.

### Recommended Project Structure

Keep the single-module shape — do NOT create a models package. One small new module for the wrapper plus touches to the two existing display/loop files:

```text
strands_code_cli/
├── reported_cost.py        # NEW: CostAwareLiteLLMModel + wrap_for_openrouter() + drain helper (~60 lines)
├── model_switch.py         # TOUCH: apply_switch wraps openrouter-routed ids (loop.py:719 routed path same)
├── main.py                 # TOUCH: initial model_for_config/create_harness path wraps too
├── loop.py                 # TOUCH: record_turn_metrics drains + stores reported_cost (all 4 call sites flow through it)
└── cost_context.py         # TOUCH: usage_line marker, cost_report actual-wins + split, routing-line marker
tests/
├── test_reported_cost.py   # NEW: wrapper capture/drain semantics (fake Usage objects, no network)
└── test_cost_context.py    # EXTEND: actual-wins, marker, split shown/hidden, 0.0-as-actual
```

### Pattern 1: Capture-before-delegate `format_chunk` override
**What:** Subclass `LiteLLMModel`; on `chunk_type == "metadata"`, read `event["data"]` (the raw LiteLLM `Usage`) with `getattr(data, "cost", None)`, validate via the `_cost`-shaped verbatim extractor (None when absent/non-numeric/bool), append to `self._reported_costs`, then return `super().format_chunk(event)` unmodified.
**When to use:** The ONLY capture seam — every OpenRouter model cycle funnels through it in both streaming and non-streaming modes.
**Example:**
```python
# Source: strands/models/litellm.py:564,614 (metadata yield) + openai.py:601 (drop point)
class CostAwareLiteLLMModel(LiteLLMModel):
    def format_chunk(self, event, **kwargs):
        if event.get("chunk_type") == "metadata":
            cost = _reported_cost(getattr(event.get("data"), "cost", None))
            self._reported_costs.append(cost)  # None marks absent (D-05 per-cycle)
        return super().format_chunk(event, **kwargs)

    def take_reported_costs(self):
        costs, self._reported_costs = self._reported_costs, []
        return costs  # sum of non-None per turn; all-None → estimate path
```

### Pattern 2: Wrap at resolve, only for openrouter-routed ids
**What:** After each `resolve_model(string, ...)` call, if `is_openrouter_id(string)` [VERIFIED: live_pricing.py:366-368], rebuild as the subclass (same `client_args`/`model_id`); else pass through untouched. Bedrock/Ollama/offline models never see the subclass (D-07).
**When to use:** All three construction sites: `apply_switch` [VERIFIED: model_switch.py:649-656], the routed/side resolve in `loop.py:719`, and the initial `create_harness(model=...)` in `main.py` — plus the btw rebuild path, which must get its OWN instance (Pitfall 1).

### Pattern 3: Per-turn actual-XOR-estimate row
**What:** The session-turn row gains optional `reported_cost` (float|None). `cost_report` computes per row: reported wins when present (even 0.0 — see ruling); else `cost_for` estimate; else tokens-only. Totals accumulate exactly one money value per row (D-09); the split sums the two lanes separately.
**When to use:** Every `/cost` render and every post-turn usage line (D-01/D-02/D-08).

### the agent's Discretion Ruling 1: literal `0.0` → marked ACTUAL zero (not estimate-fallback)
**Recommendation:** A present `usage.cost` of exactly `0.0` (or int `0`, as `:free` models return) displays as a marked actual zero (`$0.0000` + actual marker) and contributes 0.0 to the actuals lane.
**Reasoning:** (1) D-05's estimate fallback is for *absent* cost; 0.0 is present — the provider affirmatively said "this request cost nothing". (2) Falling back would fabricate spend: a `:free` turn would show almanac-priced dollars for a call that was genuinely free (the almanac lists $0 for `:free` ids, so the fallback would usually agree — but for BYOK keys, where OpenRouter charges $0 while the user pays upstream, an estimate would invent OpenRouter spend that never happened). (3) Consistent with the Phase 8 precedent: cost-absent local decision calls render zero, never an estimate — reported/derivable zeros are shown, not re-estimated. (4) The marker semantics stay crisp: marked = "the provider said this number", bare = "we estimated it". Risk if wrong: BYOK users see `$0.0000 actual` for turns their upstream key was billed for — mitigated by documenting that "actual" means provider-reported OpenRouter spend.
**Implementation note:** `0.0` is falsy — the actual-wins check MUST be `is not None`, never truthiness (Pitfall 4). Reuse the `_cost` extractor shape [VERIFIED: routing.py:1108-1114] (`if isinstance(value, (int, float)): return float(value)`), which already maps int `0` → `0.0` and non-numeric → `None`.

### the agent's Discretion Ruling 2: marker and split layout (recommendation)
**Marker:** append the word `actual` to the money cell: `, $0.0042 actual` on `/cost` rows, usage line, and routing lines (D-01/D-02/D-04). Rationale: D-03 keeps bare `$` = estimate, so the marker must be unambiguous in a plain-text terminal without inventing punctuation the user must learn; the word matches the D-08 "actual/estimated split" vocabulary. Planner may substitute a symbol if tests pin it — but keep ONE marker everywhere (D-04 consistency).
**Split:** beneath the blended headline total, one dim line `  (actual $X + estimated $Y)`; hidden entirely when the actuals lane is empty (D-11) AND when the estimated lane is empty (symmetric restraint — a pure-actuals session needs no split either). Routing/decision spend counts in the actuals lane (D-10).

### Anti-Patterns to Avoid
- **Sharing one wrapper instance between main and btw agents:** both agents' cycles would land in one list and drains would misattribute spend. One instance per agent, always.
- **Summing `reported_cost` + estimate anywhere:** D-09 forbids it; the row holds one lane or the other, and totals accumulate the winning lane only.
- **Treating `reported_cost is None` and `reported_cost == 0.0` the same:** None → estimate path (D-05); 0.0 → marked actual zero (Ruling 1).
- **Wrapping non-OpenRouter models "for uniformity":** Bedrock passthrough has no cost field and direct-OpenAI LiteLLM usage may lack `.cost` — wrapping buys nothing and risks behavior drift on the untouched paths (D-07).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-request cost truth | Tokens × price-table recomputation as "actual" | Inline `usage.cost` verbatim | OpenRouter routes one model id across upstreams with different prices + cache discounts; static tables silently drift (the TanStack/ai#468 lesson) |
| Cost transport from provider | New HTTP client / polling / generation-id backfill | The existing LiteLLM stream + `format_chunk` override | Cost already arrives free in-band; a second transport adds latency, races, and failure modes for the same number |
| Reported-spend validation | New extractor semantics | `_cost` / `_reported_spend` shapes [VERIFIED: routing.py:1108-1114, cost_context.py:182-187] | Bool-safe, int-tolerant, None-on-absent — already tested precedent |
| Turn-row plumbing | A parallel spend ledger | The existing `session_turns` row + `record_turn_metrics` choke point | All four record sites (main, btw, revise, idle-drain) already funnel through it [VERIFIED: loop.py:1019,1875,2288-2294] |

**Key insight:** the provider reports, the SDK drops, the CLI recovers at the seam. Every deterministic step (None handling, actual-wins, totals, split) stays in CLI code; the model stream supplies only the raw number.

## Common Pitfalls

### Pitfall 1: Shared wrapper instance across main + btw agents corrupts drains
**What goes wrong:** Both agents' cycle costs land in one `_reported_costs` list; whichever turn drains first steals the other's spend, and totals misattribute across main/side rows.
**Why it happens:** The btw side agent is rebuilt from stashed parent kwargs — if `kwargs["model"]` holds an already-wrapped instance, `create_harness` reuses it verbatim.
**How to avoid:** Wrap per agent construction, never per model string: the btw build path must construct its OWN wrapper instance from the resolved string (or the wrap helper must always return a fresh instance, never a cached one).
**Warning signs:** `/cost` rows whose actuals sum exceeds the session's OpenRouter activity; btw rows showing spend on turns the side agent never ran.

### Pitfall 2: Multi-cycle turns need summed, not last, cost
**What goes wrong:** A tool-loop turn makes N model requests; recording only the last cycle's cost understates the turn.
**Why it happens:** `format_chunk` fires once per request, but `record_turn_metrics` runs once per turn.
**How to avoid:** Drain-and-sum ALL costs accumulated since the last drain; per-cycle Nones (absent cost on one cycle of a multi-cycle turn) must not poison the sum — sum the present ones, and treat the turn as actual iff at least one cycle reported [ASSUMED: OpenRouter reports cost on every cycle or none; mixed turns unobserved — planner picks all-or-any rule, tests pin it].
**Warning signs:** Tool-heavy OpenRouter turns reporting suspiciously tiny actuals next to large token counts.

### Pitfall 3: Mid-turn model switches strand drained costs
**What goes wrong:** A `/model` switch (or routed switch) replaces `agent.model`; undrained costs on the old instance are orphaned, and the new instance starts empty mid-accounting.
**Why it happens:** Switches happen at idle, but drains happen per turn — a switch between drain and next turn is safe, yet a routed switch *during* turn setup (pre-turn hook) could interleave.
**How to avoid:** Drain from the model instance that SERVED the turn (pass it to `record_turn_metrics` or read `agent.model` at record time — both are the serving instance post-turn since switches only happen at idle).
**Warning signs:** First turn after a switch shows estimate where actual was expected.

### Pitfall 4: Falsy-zero collapsing (`if reported:` instead of `is not None`)
**What goes wrong:** Literal `0.0` (free models, full cache discount, BYOK) falls into the estimate path, violating Ruling 1 and D-09 lane accounting.
**Why it happens:** `0.0` and `0` are falsy; a truthiness check looks natural.
**How to avoid:** Every actual-wins branch checks `reported_cost is not None`. Tests pin int-`0` and float-`0.0` explicitly as actuals.
**Warning signs:** `:free` turns showing bare-`$` estimates instead of marked `$0.0000 actual`.

### Pitfall 5: `effort`/`caching` silently dropped on pre-built instances
**What goes wrong:** Routed picks with a thinking level lose their effort when the CLI passes a pre-built wrapper to `resolve_model` — it warns and ignores `effort`/`caching` [VERIFIED: strands_harness/models.py:431-437].
**Why it happens:** The verbatim-instance path cannot configure reasoning after construction.
**How to avoid:** Either construct the wrapper with reasoning pre-configured (mirror what `resolve_model` would have set), or bypass-and-wrap: resolve the plain instance first WITH effort, then re-wrap preserving its config. Planner scopes; tests assert a routed effort survives wrapping.
**Warning signs:** Routed OpenRouter turns ignoring thinking levels after the phase lands.

### Pitfall 6: Assuming `.cost` exists on every LiteLLM `Usage`
**What goes wrong:** `AttributeError` (or a crash in the hot stream path) when a non-OpenRouter provider or a LiteLLM version skew yields a `Usage` without `.cost`.
**Why it happens:** `.cost` is provider-supplied metadata, not part of the OpenAI usage schema.
**How to avoid:** `getattr(data, "cost", None)` + the bool-safe numeric extractor; capture code must never raise (fail-soft: unrecorded cost degrades to the D-05 estimate path, and the agent loop never sees the failure).
**Warning signs:** Any exception mentioning `format_chunk` or `cost` in turn logs; OpenRouter turns failing outright.

## Code Examples

### Drain-aware `record_turn_metrics` extension (sketch)
```python
# Source: loop.py:278-307 (existing choke point) + Pattern 1 drain
def record_turn_metrics(result, current_model, session_turns, model=None):
    ...  # existing metrics extraction + row append, unchanged
    reported = None
    take = getattr(model, "take_reported_costs", None)
    if callable(take):
        try:
            costs = [c for c in take() if c is not None]
            reported = sum(costs) if costs else None
        except Exception:
            reported = None  # fail soft → D-05 estimate path
    session_turns[-1]["reported_cost"] = reported
    return usage_line(in_tok, out_tok, current_model, reported_cost=reported)
```

### Actual-wins row rendering (sketch)
```python
# Source: cost_context.py:253-269 (existing row loop) + D-09
reported = row.get("reported_cost")
if reported is not None:                       # is-not-None: 0.0 is an actual (Ruling 1)
    cell += f", ${reported:.4f} actual"
    total_actual += reported
else:
    turn_cost = cost_for(in_tok, out_tok, row_model)   # D-05 estimate fallback, unchanged
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tokens × almanac estimate for every main turn | Provider-reported `usage.cost` actuals where supplied, estimate elsewhere | This phase (MODEL-05) | `/cost` money becomes exact on OpenRouter; estimates remain for Bedrock/offline |
| Generation-id lookup for cost auditing | Inline `usage.cost` on the response | OpenRouter-side (cost now inline everywhere) | No new transport, no delay, no backfill needed |
| Decision spend verbatim, main turns estimated | Same verbatim-reported treatment for main turns | This phase extends the Phase 8 precedent | One actual/estimate vocabulary across `/cost` (D-04) |

**Deprecated/outdated:**
- Tokens-only cost derivation as the sole main-turn source: superseded by actuals on OpenRouter paths (kept as the D-05/D-07 fallback, not deleted).
- `/generation` lookup as a live cost source: rejected — audit/history use only, never the turn path.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Mixed cost presence within one multi-cycle turn (some cycles report, some don't) is unobserved; planner picks any-vs-all rule | Pitfall 2 | LOW — either rule keeps D-09 (one lane per turn); difference is estimate-vs-actual classification on a rare edge |
| A2 | Non-OpenRouter LiteLLM providers (direct OpenAI etc.) omit `.cost`, degrading cleanly to estimates via `getattr` default | Pitfall 6 | LOW — fail-soft capture makes the worst case today's estimate display |
| A3 | `cost_details` / `is_byok` capture is out of scope; `cost` alone satisfies MODEL-05 | Architecture | LOW — BYOK nuance documented; a later phase can surface upstream cost if asked |

**No planner-blocking assumptions:** all load-bearing claims (inline cost shape, timing, LiteLLM passthrough, Strands drop points, generation delay, Bedrock absence) are live-verified or code-verified this session.

## Open Questions (RESOLVED)

None blocking. The agent's-discretion items are ruled above (0.0 → marked actual zero; marker = `actual`; split = `(actual $X + estimated $Y)` hidden when either lane is empty). The planner may adjust marker/split cosmetics within D-01..D-04/D-08/D-11; anything else is locked.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + pytest | All tests | ✓ | pytest 9.1.1 (locked) | — |
| `OPENROUTER_API_KEY` | Live probes (done) + integration test | ✓ | present in env | Skip live tests; hermetic fakes cover logic |
| OpenRouter chat API | Live probes (done) | ✓ | `usage.cost` live-verified | — |
| `litellm` extra | Live integration test only | ✗ (not installed; optional extra) | ≥1.104 per pyproject | `uv sync --extra litellm` at test time; hermetic tests use fake `Usage` |
| tmux + uattest rig | Live `/cost` render check | presume ✓ (rig ran Phase 8–9) | — | Hermetic render tests only, note gap |

**Missing dependencies with no fallback:** none (every live layer degrades to skip + hermetic coverage).
**Missing dependencies with fallback:** `litellm` extra (fallback: fake-`Usage` hermetic tests; install only for the integration run).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (no conftest changes needed) |
| Quick run command | `uv run pytest tests/test_reported_cost.py tests/test_cost_context.py -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| MODEL-05 | Wrapper captures `.cost` per metadata chunk; chunks byte-identical to super() | unit (fake Usage) | `uv run pytest tests/test_reported_cost.py -q` | ❌ Wave 0 |
| MODEL-05 | Drain sums multi-cycle costs; all-None → None; absent `.cost` → None, never raises | unit (fake Usage) | `uv run pytest tests/test_reported_cost.py -q` | ❌ Wave 0 |
| MODEL-05 | `record_turn_metrics` stores `reported_cost` on the row (incl. btw/revise paths) | unit (doubles) | `uv run pytest tests/test_cost_context.py -q` | ✅ extend |
| MODEL-05 | Row renders marked actual when present (incl. int-0 and 0.0), estimate on None, tokens-only on no-price (D-01/D-05/D-06) | unit | `uv run pytest tests/test_cost_context.py -q` | ✅ extend |
| MODEL-05 | Blended total + split; split hidden when either lane empty (D-08/D-09/D-11); routing spend in actuals lane + routed lines marked (D-04/D-10) | unit | `uv run pytest tests/test_cost_context.py -q` | ✅ extend |
| MODEL-05 | Usage line carries the same marker (D-02); bare `$` stays estimate-only (D-03) | unit | `uv run pytest tests/test_cost_context.py -q` | ✅ extend |
| MODEL-05 | Non-OpenRouter ids never wrapped; Bedrock rows byte-identical to today (D-07) | unit | `uv run pytest tests/test_reported_cost.py tests/test_model_switch.py -q` | ❌ Wave 0 + ✅ extend |
| MODEL-05 | Routed effort survives wrapping (Pitfall 5) | unit | `uv run pytest tests/test_reported_cost.py -q` | ❌ Wave 0 |
| MODEL-05 | Live OpenRouter turn via LiteLLMModel subclass captures real `usage.cost` end-to-end | integration (env-gated, needs litellm extra + key) | `uv run pytest -m integration -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_reported_cost.py tests/test_cost_context.py -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_reported_cost.py` — NEW: wrapper capture/drain/wrap-scope/effort-survival cases (fake `Usage` objects, no network, no litellm import — import-guard the module so the suite stays green without the extra)
- [ ] `tests/test_cost_context.py` — EXTEND: actual-wins, marker, split shown/hidden, 0.0-as-actual, routing-lane cases
- [ ] `tests/test_model_switch.py` — EXTEND: wrap-scope cases (openrouter ids wrapped, others pass through identical)
- [ ] Integration live test (env-gated: skips without key or without litellm extra): one real `litellm/openrouter/...` turn asserting `reported_cost > 0` captured and row marked
- [ ] `uv sync --extra litellm` before the integration run (do NOT commit lockfile churn — verify `git status` clean of `uv.lock` after, or use a throwaway env)

## Security Domain

ASVS Level 1, `security_enforcement: true`, block on high [VERIFIED: config.json workflow section].

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial (no new auth) | Phase reads NO credentials — cost rides the existing authenticated stream; probes used env-at-call-time key, header-only, never logged/persisted |
| V3 Session Management | no | N/A (CLI session, no cookies/tokens) |
| V4 Access Control | no | No new files/paths with secrets; session rows hold floats, never payloads |
| V5 Input Validation | yes | Bool-safe numeric extractor for `.cost` (bool/int/float/str→None-or-float); capture never raises into the stream (fail-soft → estimate path) |
| V6 Cryptography | no | TLS via platform; no crypto code — never hand-roll |
| V7 Errors/Logging | yes | Capture failures degrade silently to estimates (no log spam per cycle); never log raw usage payloads (may carry provider metadata) or keys |
| V10 Malicious Code | yes | Zero new dependencies — no supply-chain delta |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed provider `usage` (string/bool/object `.cost`) crashes the stream | Tampering/Denial | `_cost`-shaped extractor + try/except around capture; worst case is today's estimate display |
| Spend misattribution across main/btw agents via a shared wrapper | Tampering | Fresh wrapper instance per agent construction (Pitfall 1); test pins it |
| Key material captured alongside cost | Information disclosure | Record ONLY the numeric cost (float), never the payload, headers, or generation id |

## Sources

### Primary (HIGH confidence — live-verified this session, 2026-10-12)
- Live `POST /api/v1/chat/completions` non-streaming (gpt-4o-mini, 200, `usage.cost: 2.4e-06` verbatim) — `OPENROUTER_API_KEY` from env
- Live streaming call with `usage: {include: true}` (final chunk carries identical `usage.cost`) + live `:free` call (`usage.cost: 0` int)
- Live `GET /api/v1/generation?id=` ×2 ids (404 at 0s/+5s, 200 with `total_cost` at +15s)
- Live `litellm.completion` non-streaming + streaming (`.cost`/`.cost_details`/`.is_byok` preserved; bare-stream no-usage caveat) in a throwaway /tmp venv (project env untouched)
- In-repo reads: `cost_context.py` (full), `loop.py` record sites, `routing.py` `_cost`/`EngineResult`/usage mapping, `live_pricing.py` id prefixes, `model_switch.py` `apply_switch`, `main.py` `model_for_config`/`build_agent`, 10-CONTEXT.md, 08-CONTEXT.md D-12, 08-RESEARCH.md, 09-CONTEXT.md, REQUIREMENTS.md, STATE.md, AGENTS.md, config.json
- Installed-SDK reads: `strands/models/openai.py` (`format_chunk` metadata case, `stream_options` default), `strands/models/litellm.py` (metadata yields, inheritance), `strands/models/bedrock.py` (usage passthrough), `strands/types/event_loop.py` (`Usage`), `strands/telemetry/metrics.py` (`_accumulate_usage`), `strands/event_loop/streaming.py` (`extract_usage_metrics`), `strands_harness/models.py` (`_PROVIDERS`, `resolve_model` verbatim rule)

### Secondary (MEDIUM — official docs, extracted this session)
- https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion (`usage.cost` + `cost_details` reference shape)
- https://openrouter.ai/docs/cookbook/administration/usage-accounting (`usage: {include: true}`, generation-id alternative)
- https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation (`total_cost` record)
- https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference + .../cost-management (Converse envelope; no per-request dollars)

### Tertiary (LOW — third-party, corroborating only)
- TanStack/ai#468 (inline `usage.cost` authority; `/generation` aggregation race) — race independently verified live, so the finding itself is HIGH

## Metadata

**Confidence breakdown:**
- Cost location/shape/timing: HIGH — verbatim live responses, both modes, plus free-tier zero
- LiteLLM passthrough: HIGH — live `Usage.cost` reads in a real litellm install
- Strands drop points + accumulation: HIGH — installed-source reads with line citations
- Generation-lookup rejection: HIGH — twice-verified delay, plus architectural disqualifiers
- Bedrock-stays-estimate: HIGH — code passthrough + AWS docs agree
- Wrapper/drain design: HIGH — seam verified at every hop; only multi-cycle mixed-presence rule is planner's pick (A1)
- Marker/split cosmetics: agent's-discretion recommendation, tests pin whatever ships

**Research date:** 2026-10-12
**Valid until:** 2026-10-19 (fast-moving: OpenRouter response shapes are stable but provider-attributed; re-probe if the phase slips)

## RESEARCH COMPLETE
