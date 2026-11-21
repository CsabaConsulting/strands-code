# Phase 8: Model Routing with Decision Models - Research

**Researched:** 2026-10-11
**Domain:** Decision-model APIs (OpenRouter Decisions, Ollama System One) + per-ask model routing in a Python CLI
**Confidence:** HIGH (every API claim verified live this session: real catalog fetch + real calls to both engines)
**Rework note:** This overwrites the superseded chat-completions-JSON research. The phase was already implemented on chat JSON mode (`strands_code_cli/routing.py`); the revisit (D-14..D-16) replaces both engines with true Decision APIs. This document researches the NEW design and marks exactly what survives vs what gets rebuilt.

## Summary

Per ask, the CLI routes to the right model and thinking budget via a cheap decision model through true Decision APIs: OpenRouter `POST /api/alpha/decisions` (default) and Ollama `POST /v1/systemone` (local alternative), with manual override kept. I verified every API claim live this session: the decision-model catalog (19 entries, no key needed), a real Jev model-choice call (200 in 0.33s, correct deep-refactor route at 0.85, cost $0.000016), a real local `tev1:0.8b` call through `/v1/systemone`, the Ollama 2–26 option cap (40 options rejected live), and Jev accepting 30 options.

Two findings shape the plan most. First, the `confidence` field is vendor-specific and opaque: Ollama/tev1 matches the entropy formula `1-H/ln(N)` while Jev provably does not (it matches a normalized top-probability margin), so the D-16 threshold gate MUST compare the pick's top-1 probability, never `confidence`. Second, the binding `choice` cap is 26 (Ollama enforces 2–26 uniformly, verified live; OpenRouter caps are model-dependent), so the strategy enforces max 26 candidates code-side and the setup flow caps selection there.

**Primary recommendation:** Rebuild the two engine transports on the Decision APIs with shared typed `state`+`questions` builders, gate in code on top-1 probability (threshold + tie-margin), keep all surviving scaffolding (strategy load/validate shape, chain/hold, toggle, transcript/cost plumbing, rig), and derive the `confidence_threshold`/`tie_margin` defaults from a real probe run at implementation time — never ship round-number defaults.

## User Constraints (from CONTEXT.md)

### Locked Decisions

### Routing scope and strategy config
- **D-01:** Routing is auto-on only when a strategy is configured (candidate model set + directives). Without config there is not enough information to route, so routing stays off. — **Reversibility:** costly — the default posture shapes the turn loop and config surface; flipping it later changes every-turn behavior and the setup contract.
- **D-02:** Strategy shape is candidate models plus freeform scenario directives (e.g. "trivial asks go cheap, deep refactors go big"). Candidate entries carry user-editable criteria prose — cost words ("cheapest", "premium") plus role notes (Sol=mega / Terra=mid / Luna=small; Opus/Sonnet/Haiku tiers) — pre-computed at config time; this prose becomes the `choice` criteria. Prices, windows, and benchmarks never enter the decision call (decision models do no quantities); they stay code-side. — **Revisit 2026-10-11:** descriptors repositioned from decision-call stats to config-time criteria.
- **D-03:** Strategy lives both globally and per workspace; repo wins on conflict (Phase 3 D-08 policy precedence).
- **D-04:** Main turns and `/btw` side questions both route through the same strategy; side asks are flagged as side so directives can discriminate (closes the Phase 7 D-07 revisit).
- **D-05:** Thinking-level routing within thinking-capable models is in scope: the router picks a thinking level automatically via a second sequential `choice` over the picked model's advertised levels — not just the model. Single-candidate strategies skip the model call but still ask the effort question.

### Decision engine and fallback
- **D-06:** True Decision APIs are the engines: OpenRouter `/api/alpha/decisions` is the default until Bedrock offers decision models; Ollama `/v1/systemone` is the local alternative (requires Ollama ≥0.35 and a decision-capable pull such as tev1/nimble/clef). Generic chat LLMs in JSON mode are NOT decision engines. Setup enumerates chat models for routing candidates and `output_modalities=decisions` models for the decision pick, separately.
- **D-07:** Directives feed every decision call twice — once in `state` as data, once shaping the question instructions. Candidate stats (prices, windows, benchmarks) do NOT feed the call; directives shape all decisions, and they never sit idle while the model decides without them.
- **D-08:** Fallback chain is models-only: decision API → local model → pause and hold the current model, retrying next ask. Below-confidence-threshold picks also hold and retry (D-16). No heuristic ever picks a model. Roadmap SC2's "deterministic heuristic fallback" is satisfied by deterministic hold-current (a fixed rule, not a heuristic pick) — planner/researcher note this reinterpretation.
- **D-09:** Fully offline behavior is local decision model if configured, otherwise routing pauses and the current model is used (AWS-optional posture holds: no network, no API, no guessing).

### Override and visibility
- **D-10:** Routing has a session-sticky toggle (Phase 4/6 precedent). `/model` re-points immediately but warns the switch turns routing off and offers cancel to keep routing; a slash command turns routing back on. More routing slash commands are expected (planner scopes them).
- **D-11:** Routed switches are silent plus a transcript note; model choice never raises an approval prompt. Deny-first stays for tool side effects, not for routing.
- **D-12:** Every routed ask gets one transcript line — choice plus BOTH confidences (model + effort) inline plus the code-computed `~$/ask` delta — suppressible via config to cut noise; `/cost` carries a compact entry (choice, confidences, decision spend) with the full probability table in verbose/debug only. Code tie-break substitutions are noted on the line. There is no free-text `why` (decision APIs return probabilities, not prose).

### Strategy setup
- **D-13:** Guided setup flow creates the strategy (enumerate OpenRouter models, capture directives). Example strategies ship in the docs, manual file edits are allowed, and a slash command validates the configuration's validity.

### Decision-API rework (revisit 2026-10-11)
- **D-14:** Cost-awareness is a mash-up: cost words ride in the criteria prose (D-02), AND code substitutes the cheaper candidate when the top two probabilities fall within a `tie_margin` strategy knob (ships with a reasonable default; almanac prices decide "cheaper").
- **D-15:** Each routed ask makes up to two sequential decision calls — model `choice` first, then effort `choice` over only the picked model's levels. Single-candidate strategies skip call one but still ask call two.
- **D-16:** A `confidence_threshold` strategy knob (ships with a default) gates routing: a model pick below it holds current and retries next ask with its own distinct note (`Routing held (confidence 41% < 70%)`). Only the model confidence gates; a weak effort read still routes.

### the agent's Discretion
- Routing slash command names and subcommand shapes (toggle on/off, setup, validate, status).
- Strategy file format, filenames, and exact global/workspace paths.
- Transcript line format and the /cost routing section shape.
- Hold-current retry/notify behavior (silent hold vs transcript note on failure).
- Descriptor/benchmark schema for candidate entries (researcher confirms sources first).
- Side-ask decision-call mechanics (per-ask call vs derived) within D-04.
- Decision-model selection and pinning (which OpenRouter decision id ships as default; which local tag; researcher re-verifies the live catalog — never hardcode from memory).
- Handling the `choice` 2–26 option cap against candidate scale (cap candidates, tiered pre-filter, or paged choices).
- `tie_margin` and `confidence_threshold` default values (researcher probes real models first).

### Deferred Ideas (OUT OF SCOPE)
- CodeAct action interface (Phase 9).
- Cost budgets/enforcement (locked: display only).
- Heuristic model-picking — rejected, not deferred: directives + models only.
- Fully automatic routing with no override — locked out; manual switching + toggle always win.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-03 | CLI auto-selects model and thinking budget per ask via a decision model (Jev/Kev/Laya class), with manual override | Decision-API engine section (request/response/error shapes, pinning, caps); question-shaping; calibration method; gate logic; surviving toggle/override/switch machinery |

## Project Constraints (from AGENTS.md)

Actionable directives the planner must honor (AGENTS.md is stale — it maps `strands_code_agent/` only and says "no CLI exists" — but these survive as project posture; CONTEXT.md §Canonical References supersedes for CLI orientation):
- Python ≥3.10, `uv` toolchain; stdlib-only HTTP via `urllib` (per phase brief; no `requests` dependency).
- AWS-optional, never AWS-required; offline default holds (D-09).
- No upper pins during the experimental phase.
- `snake_case` modules/functions, `UPPER_SNAKE_CASE` constants, `PascalCase` classes; one import per line, absolute imports.
- Fail-soft read paths (return degraded values, never raise to callers); log-and-continue for best-effort cleanup only.
- Module `logger = logging.getLogger(__name__)` with `%s`-style args; no `print()` in library code (transcript prints live in the turn layer via `print_plain`, markup off — WR-06).
- Why-comments only (1–2 lines); docstrings on public functions/classes.
- Constructor-kwarg configuration, never env sniffing (exception: runtime credentials `OPENROUTER_API_KEY`/`OLLAMA_API_KEY`/`OLLAMA_HOST` read at call time inside engine functions only — established harness precedent).
- No keys in repo; API keys header-only, never logged.
- Reply-only router actions; prompts live in the gate/turn layer.
- Test files mirror modules: `tests/test_<module>.py`; pytest with `integration` marker deselected by default [VERIFIED: pyproject.toml:63-67] (`markers = [...]`, `addopts = "-m 'not integration'"`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Decision-API transport (OpenRouter/Ollama POST) | CLI process (execution layer) | — | Synchronous `urllib` calls pre-turn at idle; no server component exists |
| Strategy load/validate/setup | CLI process (composition layer) | — | File config + guided prompts; mirrors `ProviderConfig` precedent |
| Threshold/tie-margin gating + hold-current | CLI process (execution layer) | — | Pure code on typed responses; microseconds, runs pre-turn |
| Routing toggle + `/model` override | CLI session state (in-memory) | — | Session-sticky `RoutingState`; manual control always wins |
| Transcript note + `/cost` entry | CLI presentation layer | — | `print_plain` + `cost_context.py`; already built, format changes only |
| Decision judgment itself | External decision model | — | Only the probability table comes from outside; code owns everything else |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdlib `urllib` + `json` + `dataclasses` | builtin (Python ≥3.10) | Decision-API POSTs, typed answers | Zero-dependency transport is the locked AI-SPEC framework decision; both engines are one JSON POST each |
| PyYAML | 6.0.3 (locked) | Strategy file load/save | Already used by `routing.py`; fail-soft `ProviderConfig` precedent |
| platformdirs | (locked) | Global strategy path | Already used by `routing.py` `default_global_strategy_path` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 (locked) | Hermetic gate/engine/strategy/loop tests | All phase tests; live tests behind `integration` marker |
| tmux + `scripts/uattest/driver.py` | repo rig | Live UAT scenarios r1–r4 | Real latency/rendering/engine round-trips hermetic tests cannot cover |
| promptfoo | latest (CLI global) | Probe-set question regression in CI | Per AI-SPEC §5: wraps the labeled probe set, diffs verdicts per decision-model pin |

No new runtime dependency is added. No provider SDK (OpenAI/Anthropic/TypeSafe) — all lack Decision-API coverage or add lock-in for one POST call [CITED: https://openrouter.ai/skills/openrouter-decisions].

**Package Legitimacy Audit:** skipped — this phase installs zero packages (stdlib + locked deps only).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `urllib` | `requests` / OpenRouter SDK | New dependency for one POST; SDK Decisions path needs `serverURL` override and still lacks Ollama — use `urllib` |
| Typed dicts + explicit checks | Pydantic models | Pydantic is NOT in the dependency closure; do not add it for one response shape — dataclasses + explicit checks |

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌──────────────── strategy.yaml ────────────────┐
                    │ candidates + criteria prose + directives      │
                    │ + tie_margin + confidence_threshold + pins   │
                    └──────────────┬────────────────┬───────────────┘
                    global (platformdirs)    repo (./.agent, wins whole-file)
                                   ▼
User ask ──► pre-turn @ idle ──► load_strategy ──► toggle on? ──► manual /model pin?
 (loop.py)        (D-01)              │                │ no            │ yes
                                     │                ▼               ▼
                                     │           serve current   serve pinned
                                     │           (no line)       (no routing line)
                                     ▼ yes / configured
                          ┌───── Call 1: model choice ─────┐
                          │ state={ask,directives,side}    │
                          │ questions={pick_model: choice} │
                          │ criteria=candidate prose (D-02)│
                          │ (SKIP if 1 candidate — D-15)   │
                          └──────────────┬─────────────────┘
                          OpenRouter /api/alpha/decisions ──► 4xx/schema-fail ──► HOLD
                                     │ retryable fail (1 retry)
                                     ▼
                          Ollama /v1/systemone ──► fail ──► HOLD current (D-08)
                                     │ table
                                     ▼
                    ┌── gate_model (code, D-14/D-16) ──┐
                    │ top1 < threshold → HOLD + note   │
                    │ top1−top2 ≤ margin → cheaper     │
                    │ (almanac decides cheaper)        │
                    └──────────────┬──────────────────┘
                                   ▼ pick
                          ┌───── Call 2: effort choice ─────┐
                          │ same state; criteria = picked    │
                          │ model's advertised levels only  │
                          │ (same engine chain; weak read    │
                          │ still routes — D-16)             │
                          └──────────────┬──────────────────┘
                                         ▼
                    validate_routed_effort ──► fail HOLD (survives)
                                         ▼
                    apply switch + transcript line (choice +
                    BOTH confidences + ~$/ask delta) + /cost entry
```

Data flows one way: strategy + ask → up to two sequential decision calls (never parallel — call 2's options depend on call 1's answer [CITED: https://openrouter.ai/skills/openrouter-decisions]) → code gate → switch machinery → transcript/cost surfaces.

### Recommended Project Structure

Keep the single-module shape — do NOT split into a `routing/` package. `routing.py` (1231 lines) already owns strategy/load/validate/engines/hook; the rework swaps function bodies inside it. New code adds two small pure sections, not new files:

```text
strands_code_cli/
├── routing.py            # EXTEND: Decision-API engines + gate + question builders
│   ├── (survives) load/save/validate strategy, RoutingState, cost delta, toggle
│   ├── (rebuild) decide_via_openrouter/decide_via_ollama transports
│   ├── (rebuild) build_routing_prompt → build_decision_state + model/effort questions
│   ├── (rebuild) parse_pick → validate_choice_answer + gate_model (threshold/tie)
│   └── (new) probe runner for calibration (or scripts/ — planner decides)
├── router.py             # EXTEND: setup enumerates chat + decisions catalogs separately
├── loop.py               # TOUCH: hook reads new decide() verdict incl. confidences
├── cost_context.py       # TOUCH: routing entry adds decision spend (usage.cost) + confidences
└── btw.py                # TOUCH: side-spawn verdict shape (same as main)
tests/
├── test_routing.py             # EXTEND: gate math, answer validation, transports (stubbed)
├── test_routing_strategy.py    # EXTEND: new knobs/criteria keys, 26-cap validation
└── test_loop_routing.py        # EXTEND: two-call flow, hold-note variants, transcript lines
```

### Pattern 1: Thin typed Decision-API client (shared shape, two base URLs)
**What:** One `decide()` helper POSTs `{model, state, questions}` and returns the parsed dict; engine functions differ only in base URL, auth, and usage mapping.
**When to use:** Both engines — the request/response shapes are identical by design [VERIFIED: live probes both engines this session].
**Example:**
```python
# Source: live probe 2026-10-11 (OpenRouter 200 in 0.33s; Ollama 200 local)
def decide(model, state, questions, *, base_url, api_key=None, timeout_s, keep_alive=None):
    payload = {"model": model, "state": state, "questions": questions}
    if keep_alive:  # Ollama only
        payload["keep_alive"] = keep_alive
    req = urllib.request.Request(base_url, data=json.dumps(payload).encode(),
                                 method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())  # {model, answers, usage, id?, provider?}
```

### Pattern 2: Code-side gate on the FULL probability table
**What:** Read `choice`, `probabilities`, `confidence` from the typed answer; threshold compares the pick's top-1 probability; tie-margin compares top1−top2; `confidence` is logged, never gated on (vendor-specific — see Pitfall 1).
**When to use:** Every model pick (D-14/D-16); effort pick is top-choice only.
**Example:**
```python
# Source: AI-SPEC §4 gate_model + live-probe calibration note (this research)
def gate_model(table, strategy):
    top, second = top_two(table.probabilities)
    if table[top] < strategy.confidence_threshold:  # top-1 PROBABILITY, not .confidence
        return HOLD(f"confidence {table[top]:.0%} < {strategy.confidence_threshold:.0%}")
    if table[top] - table[second] <= strategy.tie_margin:
        cheaper = min([top, second], key=almanac_price)  # almanac decides (D-14)
        return pick(cheaper, tie_break_note=(top != cheaper))
    return pick(top)
```

### Pattern 3: Fail-soft engine chain with HOLD as the only failure value
**What:** Keep the existing `_chain_for` + `decide()` shape [VERIFIED: routing.py:998-1079]: primary selects links, unconfigured links skip, every failure class (transport, 4xx, schema-invalid, below-threshold) yields HOLD with a distinct note. Add max-1 retry on retryable codes only (current code never retries — behavior change).
**When to use:** Both decision calls; call 2 uses the same chain.

### Anti-Patterns to Avoid
- **Gating on `confidence`:** vendor-specific concentration statistic, not correctness (Pitfall 1). Gate on top-1 probability.
- **Paged/tiered choices to dodge the 26-cap:** probabilities from separate calls are incomparable ("ask each decision one way" [CITED: skill limits ref]); cap candidates at 26 instead.
- **Two questions in one request for model+effort:** parallel questions cannot see each other's answers [CITED: https://openrouter.ai/skills/openrouter-decisions]; effort MUST be sequential (D-15).
- **Caching a routing verdict across asks:** strategy/availability can change; each call is stateless — re-send ask + directives every time.
- **Retrying 4xx:** 400/401/402/403/404/413 mean the request/key/credits/model are wrong — hold, never retry [CITED: OpenAPI error list].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Decision judgment | Chat-JSON prompt+parse, keyword/regex/length heuristics | Decision APIs (`choice` + code gate) | Prompt-and-parse is the superseded design; length-as-difficulty under-routes ("fix the auth race" → cheapest); heuristics are locked out (D-08) |
| Confidence math | Own entropy/margin formula | Log the returned `confidence`; gate on top-1 probability | Vendors compute it differently (verified live); recomputing invites silent drift |
| Price comparison | Model prose ("cheapest") | Almanac `price_for` code-side (D-14) | Decision models do no quantities [CITED: skill limits ref] |
| Catalog fetch/cache | New fetcher | `live_pricing.fetch_openrouter_models` + `cached_tables` [VERIFIED: live_pricing.py:366,519] | Fail-soft layering already built; add `?output_modalities=decisions` as one more read |
| Guided-pick UX | New dialog | `_setup_ask`/tty/typed pickers [VERIFIED: router.py:650-860] | Owned-keys radio + off-tty typed paths already handle abort/re-prompt |

**Key insight:** the model judges, code computes. Every deterministic step (prices, thresholds, margins, caps, truncation, validation) stays in code; the model returns only probability tables [CITED: https://openrouter.ai/skills/openrouter-decisions].

## Engine Reference (verified live 2026-10-11)

### OpenRouter `POST /api/alpha/decisions`
- Auth: `Authorization: Bearer $OPENROUTER_API_KEY`, key server-side only [CITED: OpenAPI page]. Request: `{model, state, questions}` + optional `session_id` (observability grouping, ≤256 chars, never sent to provider), `trace`, `user`, `provider` [CITED: OpenAPI page]. Recommend sending `session_id` only (session UUID groups the two sequential calls); skip the rest.
- Response: `{id, model, provider, answers, usage}`. `model` is the dated snapshot that served the request (observed `typesafe/jev-1.13-20260917`) — log it with every answer for drift tracing [VERIFIED: live probe]. `usage = {input_tokens, output_tokens, cost}` with `cost` in USD [VERIFIED: live probe: 384 in / 41 out / $0.000016128].
- Billing is input-tokens-only; output tokens are free [CITED: Jev tutorial FAQ]. Verified arithmetically: 384 × $0.042/1M = $0.000016128 exactly [VERIFIED: live probe + live catalog pricing].
- Latency: 0.33s per call observed (both probes) [VERIFIED: live probe]; third-party median 0.33s/p95 0.44s over 791 calls [CITED: ayautomate Jev guide]. Keep `DECISION_TIMEOUT_SECONDS = 10` [VERIFIED: routing.py:42] — ~30× headroom.
- Errors: `{error: {code, message}}` for 400 (invalid params), 401 (missing auth), 402 (no credits), 403 (management keys only), 404 (not found), 413 (payload too large), 429 (rate limit), 500, 502/529 (provider error), 503, 524 (timeout) [CITED: OpenAPI page]. Retryable: 429/500/502/503/524/529 + transport timeouts (max 1 retry). Never retry: 400/401/402/403/404/413.
- Schema marks `probabilities`, `confidence`, `legend` optional — read through presence checks; check `type` before reading fields; missing key or wrong `type` is an error, never a default [CITED: skill decisions-api ref].
- Rate limits adjust dynamically without notice (~250K tok/s, 1200 req/min per third-party) — treat 429 as an observed availability signal, not a bug [CITED: ayautomate Jev guide — MEDIUM].

### Ollama `POST /v1/systemone`
- No key for loopback; `OLLAMA_API_KEY` header only for proxied hosts (existing `_ollama_headers` survives [VERIFIED: routing.py:841-853]). Same `{model, state, questions}` shape + optional `keep_alive` (duration string or seconds; server default 5m) [CITED: Ollama System One API page]. Keep `OLLAMA_KEEP_ALIVE = "5m"` [VERIFIED: routing.py:55].
- Response: `{model, answers, usage}` with `usage = {input_tokens, output_tokens}` — NO `cost` field (local = $0) [VERIFIED: live probe: 198 in / 1 out]. Cost code must handle cost-absent (record $0, never estimate).
- Hard limits [CITED: Ollama System One API page + capability guide]: body ≤64 KiB (never truncated — oversize 413s); each rendered prompt must fit the loaded context window with 2 tokens spare; no streaming/images/tools/generation controls; 1–64 questions per request; `choice`/`score` criteria 2–26 [VERIFIED: live probe — 40 options rejected with `criteria must contain 2–26 candidates`].
- Decision models are NOT in the Ollama CLI or Python/JS libraries — raw HTTP is the interface [CITED: ollama.com/library/clef]. Calling a decision model via `/api/chat` yields filler-token runaway — never do it (observed 2250 empty tokens to exhaustion, CONTEXT).
- Floor: Ollama ≥0.35 (endpoint does not exist below; `nimble`/`tev1` registry blobs carry `"requires":"0.35.0"`) [CITED: modelfit guide + capability guide]; Clef needs ≥0.35.1 [CITED: ollama.com/library/clef]. Preflight via `GET /api/version` before using the local engine (local daemon here: 0.40.3 [VERIFIED: live probe]).

### Decision-model pinning (live catalog 2026-10-11)
`GET /api/v1/models?output_modalities=decisions` needs no key and returned 19 entries [VERIFIED: live curl]. Only entries whose `architecture.output_modalities` contains `decisions` accept the endpoint [CITED: skill models ref].

| id | canonical_slug | ctx | prompt $/1M | Verdict |
|----|---------------|-----|-------------|---------|
| typesafe/jev-1.13 | typesafe/jev-1.13-20260917 | 64000 | 0.042 | **PIN AS DEFAULT** — reference model in all docs; correct live route (luna 0.85); input-only billing |
| ~typesafe/jev-latest | (alias — moves) | 64000 | 0.042 | NEVER PIN — alias shifts probabilities silently [CITED: skill models ref] |
| microsoft/microsoft-decision-1 | …-20261009 | 32768 | 0.042 | Runner-up (same price, smaller ctx) |
| inception/mercury-decide[:free] | …-20260930 | 65536 | 0.02 / 0 | Budget alt — probe quality first |
| jaredpalmer/kev-4b | …-20260924 | 8192 | 0.042 | Tight ctx for ask+directives — avoid as default |
| respan/span-01* (3 entries) | … | **0** | 0–0.02 | AVOID — ctx 0 entries; yes/no-only per third-party |
| others (drex, clef×3, solar×2, pplx, luna, d1, tev1-4b-exp) | dated | 32K–1M | 0–0.24 | Probe via `--compare` equivalents only if Jev fails calibration |

Pin the versioned `id` (`typesafe/jev-1.13`) in one strategy-config value; re-verify the catalog at implementation time (it changes without notice) and re-probe on any model change — thresholds do not carry between models [CITED: skill models ref]. All completion prices are $0 [VERIFIED: live catalog].

### Local tag choice
| Tag | Size | Notes | Verdict |
|-----|------|-------|---------|
| `nimble` | 9B / 9.5GB, 256K ctx, text-only | Bespoke: choice 81.6% vs Jev 82.9% on 13 public sets [CITED: ollama.com/library/nimble] | **DEFAULT local tag** — closest to Jev on `choice` |
| `tev1:0.8b` | 0.8B / ~812MB | Already pulled locally; live probe UNDER-ROUTED deep refactor → sol 0.66 [VERIFIED] | Low-resource fallback only; needs its own (higher) threshold calibration |
| `tev1` / `tev1:4b` | 4B / ~4.5GB, experimental | Mid option | Acceptable alt where 9B does not fit |
| `clef` / `clef-flash` | 27B/18GB / 9B, multimodal, 256K | Needs ≥0.35.1; images unused here; RouterBench ≈ Jev [CITED: ollama.com/library/clef] | Reject — 18GB + multimodal buys nothing for text routing |

## Common Pitfalls

### Pitfall 1: `confidence` is vendor-specific — never gate on it
**What goes wrong:** The D-16 threshold compares the wrong number; a threshold calibrated on Ollama misfires on Jev and vice versa.
**Why it happens:** Each vendor computes `confidence` its own way. Verified live: Ollama/tev1 `p=(0.6631,0.2874,0.0495)` reported 0.2904, matching entropy `1−H/ln(3)=0.2903`; Jev `p=(0.06,0.09,0.85)` reported 0.77, while entropy gives 0.523 — Jev matches a normalized margin `(0.85−1/3)/(2/3)=0.775` instead [VERIFIED: live probes + arithmetic]. TypeSafe documents it only as "collapses that shape into a single number", threshold-from-cost-of-mistakes [CITED: docs.typesafe.ai/confidence].
**How to avoid:** Threshold and tie-margin operate on the pick's top-1 probability from `probabilities` (model-invariant). Log `confidence` on the transcript line (D-12) but never branch on it.
**Warning signs:** Threshold "works on one engine, holds everything on the other".

### Pitfall 2: Jev rounds probabilities coarsely
**What goes wrong:** A `tie_margin` below the rounding granularity fires randomly or never.
**Why it happens:** Jev returned 2-decimal probabilities (0.06/0.09/0.85) [VERIFIED: live probe]. Margins <0.01 are noise on this engine.
**How to avoid:** Floor the tie-margin search grid at 0.01 during calibration; hermetic tests use exact ties and ±ε boundaries with ε ≥ 0.005.
**Warning signs:** Tie-breaks firing on identical tables across engines but not within Jev.

### Pitfall 3: Exceeding the `choice` cap fails the whole call
**What goes wrong:** A 27-candidate strategy 400s/fails every routed ask on Ollama (uniform 2–26 [VERIFIED: live probe]); OpenRouter caps are model-dependent and NOT in the catalog (Solar ≤26, hosted Tev1 ≤20 per third-party measurement [CITED: jev-agent.com/decisions-api — MEDIUM]).
**Why it happens:** The cap lives server-side per model/engine; the catalog does not advertise it.
**How to avoid:** Hard code-side cap: max 26 candidates (setup refuses more; validate fails >26 with a fix line). 1-candidate strategies skip call 1, so the 2-minimum never binds. Effort levels likewise ≤26 (never binding in practice; enforce anyway).
**Warning signs:** Routing holds only when the local engine serves.

### Pitfall 4: Quantities/dates/negation smuggled into questions
**What goes wrong:** The model literal-reads ("is this about billing" matches broadly; "does it mention" ignores negation), cannot compare magnitudes, and degrades on contradictory instructions-vs-criteria [CITED: skill limits ref, verified on Jev 1.13].
**Why it happens:** No scratchpad for arithmetic, no loop for counting, no text output channel.
**How to avoid:** D-02/D-07 already encode this — prices/windows/benchmarks stay code-side; criteria carry cost WORDS + role prose; ask about the fact ("Which candidate model should serve this ask?"), never the text; one judgment per question; criteria read as an extension of instructions.
**Warning signs:** Calibration accuracy flat across thresholds; short asks systematically under-routed.

### Pitfall 5: Oversized state 413s on Ollama (never truncated)
**What goes wrong:** A long ask + verbose directives exceeds 64 KiB and the local call fails while OpenRouter succeeds.
**Why it happens:** Ollama never truncates; `ASK_TRUNCATE_CHARS = 2000` [VERIFIED: routing.py:39] already bounds the ask, but directives ride twice (state + instructions, D-07).
**How to avoid:** Keep the 2000-char ask truncation; bound total serialized body code-side (measure `len(json.dumps(payload))`, truncate ask further if needed) and note truncation on the transcript line. Validate warns when directives exceed ~4K chars.
**Warning signs:** Local-only holds on long pastes.

### Pitfall 6: Single-candidate fast path must CHANGE (stale behavior)
**What goes wrong:** Reusing the current fast path (lone candidate + levels → zero-call pick of first level [VERIFIED: routing.py:1045-1054]) violates D-05/D-15: call 2 (effort) must still be asked.
**Why it happens:** Copy-paste from the chat-JSON implementation.
**How to avoid:** Rewrite the fast path: skip call 1, still run call 2 over the candidate's levels; record call-2-only usage. Zero-call verdicts are gone.
**Warning signs:** `/cost` shows routed asks with zero decision spend on single-candidate strategies.

### Pitfall 7: `none`/no-match criterion vs code-side HOLD
**What goes wrong:** Adding a `none` option "per the skill" creates a second no-match mechanism that fights the D-16 threshold gate.
**Why it happens:** The skill says to add a no-match option "whenever nothing may fit" [CITED: skill step 4], but here a guessed `none` pick must STILL hold (a pick of nothing is not routable).
**How to avoid:** Follow AI-SPEC: NO `none` criterion — below-threshold tables hold code-side (one mechanism, D-16). The threshold gate subsumes the no-match case.
**Warning signs:** `none` wins with 0.4 probability and the code holds anyway — wasted probability mass that skewed the real options.

## Code Examples

### Model-choice call (call 1)
```python
# Source: live OpenRouter probe 2026-10-11 (200, 0.33s, luna @ 0.85) + D-07
state = {"ask": ask, "directives": strategy.directives, "side": side}
questions = {"pick_model": {
    "type": "choice",
    "instructions": (
        "Which candidate model should serve the ask in `ask`? "
        "Judge the ask, not its length. " + directives_shaping),
    "criteria": {c.id: c.criteria for c in strategy.candidates}}}  # D-02 prose
resp = decide(pinned_id, state, questions, base_url=OPENROUTER_DECISIONS_URL,
              api_key=os.environ["OPENROUTER_API_KEY"], timeout_s=10)
# resp["model"] -> dated snapshot, log it; resp["answers"]["pick_model"] -> typed table
```

### Effort-choice call (call 2)
```python
# Source: D-15 + Ollama score/choice shapes; same state, picked model's levels only
questions = {"pick_effort": {
    "type": "choice",
    "instructions": f"How much thinking budget does the ask in `ask` need on {pick}?",
    "criteria": {level: describe(level) for level in candidate.levels}}}
effort = top_choice(decide(...))  # weak read still routes (D-16); then validate_routed_effort
```

### Typed answer validation (replaces `parse_pick`)
```python
# Source: skill decisions-api ref (type-check, optional-field presence) + AI-SPEC §4b
def validate_choice_answer(answer, question_key, candidates):
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None  # HOLD: wrong type or missing key is an error, never a default
    probs = answer.get("probabilities")
    if not isinstance(probs, dict) or not probs:
        return None  # HOLD: schema marks probabilities optional — presence-check
    if any(not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0 for p in probs.values()):
        return None
    if abs(sum(probs.values()) - 1.0) > 1e-6:
        return None
    if answer.get("choice") not in probs or answer["choice"] not in candidates:
        return None  # HOLD: stale pick after a strategy edit must never route
    return answer  # confidence: answer.get("confidence") may be absent — log if present
```

### Setup enumeration (split catalogs per D-06)
```python
# Source: live catalog fetch (no key) + existing _setup_catalog_entries [router.py:586]
chat_entries = _setup_catalog_entries(fetch_openrouter_models())  # candidates (survives)
dec = fetch("https://openrouter.ai/api/v1/models?output_modalities=decisions")["data"]
decision_entries = [m for m in dec
                    if "decisions" in ((m.get("architecture") or {}).get("output_modalities") or [])
                    and not m["id"].startswith("~")          # never offer aliases
                    and (m.get("context_length") or 0) > 0]  # drop ctx-0 entries (respan)
# sort by prompt price asc, then id; radio/typed pick over decision_entries (rebuild _setup_pick_decision)
```

### Ollama preflight (version + pull check)
```python
# Source: Ollama /api/version + library requires>=0.35 (clef >=0.35.1)
def local_engine_ready(base, tag):
    ver = get(base + "/api/version", timeout=5).get("version", "")  # "0.40.3" observed
    if parse(ver) < (0, 35): return False
    if tag.startswith("clef") and parse(ver) < (0, 35, 1): return False
    return tag in {m["name"] for m in get(base + "/api/tags").get("models", [])}
```

## State of the Art

| Old Approach (chat-JSON, superseded) | Current Approach (Decision APIs) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One chat completion + `response_format: json_object`, parsed `RoutingPick(model, effort, why)` | Up to two sequential typed `choice` calls returning probability tables; code gates | Revisit 2026-10-11 (D-14..D-16) | Transports, question building, parsing all rebuilt; `why` prose is gone (D-12) |
| Prices/windows/benchmarks in the prompt table | Cost words in criteria prose + almanac tie-break code-side | Revisit (D-02/D-14) | `_candidate_row` price/window table is deleted, not moved |
| Single threshold-less pick; lone candidate = zero-call first level | Threshold gate + tie-margin; lone candidate still asks effort | Revisit (D-05/D-15/D-16) | Fast path rewritten (Pitfall 6); gate is new code |
| Setup picks a "cheap JSON-capable chat model" as decider | Setup enumerates chat catalog (candidates) + decisions catalog (decider) separately | Revisit (D-06) | `_setup_pick_decision` rebuilt on the decisions catalog |

**What survives (keep, extend only):** strategy load/save shape + repo-wins + symlink/`off`/YAML-bool handling [VERIFIED: routing.py:104-398]; `validate_strategy` structure (extend keys: `criteria` per candidate, `tie_margin`, `confidence_threshold`, 26-cap, decisions-catalog decider check) [VERIFIED: routing.py:505-680]; `_chain_for` registry + primary select/skip semantics [VERIFIED: routing.py:998-1019]; `decide()` signature shape (internals become two-call + gate) [VERIFIED: routing.py:1022-1079]; `validate_routed_effort` + `_EFFORT_NO_THINKING` [VERIFIED: routing.py:1082-1104]; `route_cost_delta`, `decision_model_for`, `RoutingState`, `warn_applies` [VERIFIED: routing.py:1107-1231]; pre-turn hook + side-spawn hook attachment points [VERIFIED: loop.py:605,1350]; `/cost` routing section + transcript plumbing (format changes per D-12); setup picker UX + directives capture [VERIFIED: router.py:650-876]; uattest rig r1–r4 (scenarios updated for the new flow) [VERIFIED: driver.py:276,331,382,457]; `ASK_TRUNCATE_CHARS`, timeouts, `keep_alive`, `_ollama_headers` loopback rule.

**What gets rebuilt:** `OPENROUTER_CHAT_URL` → `/api/alpha/decisions` + `/v1/systemone` transports; `_SYSTEM_PROMPT`/`build_routing_prompt` → state/question builders; `decide_via_openrouter`/`decide_via_ollama` bodies (payloads, usage mapping incl. `cost` passthrough + response-`model` logging); `parse_pick` + `RoutingPick.why` → typed validation + `gate_model`; `format_routed_line`/`format_hold_line` (both confidences inline, tie-break + threshold-hold notes, no `why`); `_setup_pick_decision` + `_setup_local_model` (decisions catalog + tag default); decision-model validate check (decisions catalog, not chat cache); retry policy (max 1 on retryable codes; current code never retries).

**Calibration method (for `tie_margin` + `confidence_threshold` defaults):** skill step 7 — run the real questions over representative inputs (clear cases, ambiguous, no-match, empty/off-topic, negated, adversarial) through BOTH pinned engines; set thresholds from observed numbers, never round numbers; repeat on any model change [CITED: https://openrouter.ai/skills/openrouter-decisions]. Concretely: run the AI-SPEC 20-probe set, bin accuracy by top-1 probability, put the threshold where wrong picks concentrate below and correct routes above with margin; set the tie-margin from the observed top1−top2 distribution on near-tie probes (grid ≥0.01 — Pitfall 2). Calibration anecdote from this session (n=2, NOT shippable): Jev correct at top-1 0.85, tev1:0.8b wrong at top-1 0.66 on the identical deep-refactor ask — consistent with a threshold in the 0.70–0.75 band, but the planner MUST re-derive from the full probe set. Per-engine thresholds are allowed (local small model may need a higher bar); one shared default only if probes support it.

**Deprecated/outdated:**
- Chat-completions JSON mode as a decision engine: rejected by D-06 — delete, do not keep as fallback.
- `RoutingPick.why` free text: decision APIs return no prose (D-12) — remove from the verdict shape.
- `typesafe/jev-1.13` hardcoded without re-verification: catalog changes silently — re-fetch at implementation.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Jev `choice` accepts up to 255 options [CITED tertiary: ayautomate; live-verified only to 30] | Pitfalls | LOW — code caps at 26 anyway; only matters if the cap is ever raised |
| A2 | Hosted Tev1 ≤20 / Solar ≤26 option caps [CITED: jev-agent.com — MEDIUM] | Pitfalls | LOW — neither is the pinned default; 26-cap covers Solar, and Ollama-side Tev1 follows the uniform 2–26 rule |
| A3 | Rate limits ~250K tok/s + 1200 req/min, dynamic [CITED tertiary] | Engine Reference | LOW — per-ask volume is far below; 429 path is hold+note regardless |
| A4 | No Pydantic in the dependency closure (per AGENTS.md stack; not re-grepped this session) | Standard Stack | LOW — planner verifies with one grep; dataclasses work either way |
| A5 | `nimble` quality ≈ Jev on `choice` (vendor numbers: 81.6% vs 82.9%) [CITED: ollama.com/library/nimble] | Pinning | MEDIUM — vendor benchmark; implementation probes confirm or the default local tag changes to `tev1:4b` |

## Open Questions (RESOLVED)

1. **Per-engine vs shared threshold** — RESOLVED (plan 08-05 task 2 probes both engines, prefers one shared value)
   - What we know: Thresholds do not transfer across models [CITED: skill]; tev1:0.8b under-routed where Jev routed correctly (live anecdote).
   - What's unclear: Whether one `confidence_threshold` serves both pinned engines after full probing.
   - Recommendation: Probe both; ship per-engine knobs only if the shared default misfires on either — prefer one knob.

2. **Effort-level criteria prose source** — RESOLVED (plan 08-02 task 1: fixed code-side map + bare-name fallback)
   - What we know: Call 2 needs per-level descriptions; `supports_reasoning` gates thinking levels [VERIFIED: routing.py:1102].
   - What's unclear: Whether level prose is user-authored per candidate, generated from a fixed map (low/medium/high → prose), or bare level names (Clef allows `criteria: null` — option name describes itself [CITED: ollama.com/library/clef]).
   - Recommendation: Fixed code-side map for known levels + bare-name fallback; user-editable only if probes show the prose matters.

3. **`session_id` value** — RESOLVED (COVERAGE.md OPT-OUT; field not sent)
   - What we know: Optional OpenRouter grouping field, ≤256 chars, never sent to provider [CITED: OpenAPI page].
   - What's unclear: Whether the CLI has a stable session UUID at the routing decision point.
   - Recommendation: Pass the session UUID if reachable from the hook; else omit — pure observability.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + pytest | All tests | ✓ | pytest 9.1.1 (locked) | — |
| Ollama daemon | Local engine + r2 + calibration | ✓ | 0.40.3 (≥0.35 floor) | Hold-current; skip live tests |
| `tev1:0.8b` pull | Local probes | ✓ | 811 MB, pulled | `ollama pull nimble` for the default tag |
| `nimble` pull | Default local tag | ✗ | — | Pull at implementation (`ollama pull nimble`, 9.5GB) |
| `OPENROUTER_API_KEY` | Cloud engine + r1/r3/r4 + calibration | ✓ | present in env | Hold-current; skip live tests |
| tmux | uattest rig r1–r4 | presume ✓ (rig ran in Phase 8) | — | Hermetic tests only, note gap |
| promptfoo | Probe regression in CI | unknown | — | Planner checks; `npm install -g promptfoo` or pip |

**Missing dependencies with no fallback:** none (every live layer degrades to hold/skip).
**Missing dependencies with fallback:** `nimble` pull (fallback: `tev1:0.8b` already local, weaker); promptfoo (fallback: raw probe JSONL diffs).

## Validation Architecture

Test framework: pytest 9.1.1, `addopts = "-m 'not integration'"` (live tests deselected by default) [VERIFIED: pyproject.toml:63-67].
Existing routing tests (all survive as extension targets): `tests/test_routing.py` (993 lines), `tests/test_routing_strategy.py` (752), `tests/test_loop_routing.py` (1064) [VERIFIED: wc].

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (no conftest changes needed) |
| Quick run command | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODEL-03 | Two-call route: model table → gate → effort table → switch + transcript line with BOTH confidences + delta | unit (stubbed engines) | `uv run pytest tests/test_loop_routing.py -q` | ✅ extend |
| MODEL-03 | Threshold hold: top-1 < threshold holds with distinct note, retries next ask | unit (synthetic tables) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-03 | Tie-margin: top1−top2 ≤ margin substitutes cheaper (almanac) + note; determinism on repeat | unit (stubbed almanac) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-03 | Answer validation: wrong type / bad sum / stale choice / missing keys → hold, zero retries | unit (fixtures) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-03 | Transport faults: 4xx→hold zero-retry; 5xx/timeout→1 retry→fallback→hold; offline→pause, current serves | unit (fault injection) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-03 | Strategy: new knobs/criteria keys load; >26 candidates fail validate; `off`/symlink preserved | unit | `uv run pytest tests/test_routing_strategy.py -q` | ✅ extend |
| MODEL-03 | Override respect: `/model` pin never re-pointed; toggle round-trip; no mid-turn flip | unit + live | quick cmd + `driver.py r3` | ✅ extend + rig |
| MODEL-03 | Live engines: real Jev + real nimble round-trips, spend accounting, latency shape | integration (gated) | `uv run pytest -m integration -q` + `driver.py r1 r2 r3 r4` | ✅ rig exists, scenarios updated |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green + probe-set calibration recorded before verify

### Wave 0 Gaps
- [ ] `tests/test_routing*.py` — extend with gate/validation/transport cases (no new files needed)
- [ ] Probe set + runner (`routing/probe.py` or `scripts/route-probe.py`) — 20 labeled asks per AI-SPEC §5; planner decides location
- [ ] `evals/routing-probe/promptfooconfig.yaml` — only if promptfoo is available (else JSONL-diff fallback)
- [ ] uattest r1–r4 scenario updates for the Decision-API flow (setup split-catalog, confidences lines, hold notes)

## Security Domain

ASVS Level 1, `security_enforcement: true`, block on high [VERIFIED: config.json workflow section].

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API keys) | `OPENROUTER_API_KEY` env-at-call-time, header-only, never logged/persisted; `save_strategy` drops `api_key`-shaped keys [VERIFIED: routing.py:308-319]; local loopback sends no key [VERIFIED: routing.py:841-853] |
| V3 Session Management | no | N/A (CLI session, no cookies/tokens) |
| V4 Access Control | partial | Strategy files 0700 parent dir, symlink refusal [VERIFIED: routing.py:357,391-395]; repo file is user-trusted input — truncate + fail-soft |
| V5 Input Validation | yes | Strict answer validation (type/sum/range/stale-choice); candidate cap 26; body-size bound; ask truncation 2000 chars; base-URL http(s)-only [VERIFIED: routing.py:170-178] |
| V6 Cryptography | no | TLS via platform; no crypto code — never hand-roll |
| V7 Errors/Logging | yes | Failures → hold + note; raw payloads logged at debug only (may contain ask text); never log keys |
| V10 Malicious Code | yes | Zero new dependencies — no supply-chain delta |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious repo `routing.yaml` injects unbounded text into paid calls | Tampering | Truncate ask (2000) + directives; bound serialized body; fail-soft entries |
| Ask text exfiltrated to the wrong engine | Information disclosure | Endpoint allowlist per engine (exact URLs); ask goes only to the configured engine (D-09) |
| Key material persisted next to strategy | Information disclosure | `_is_secret_shaped_key` drop-on-save (top level + `engine`) [VERIFIED: routing.py:322-380] |
| Prompt-injection-via-ask skewing the pick | Tampering | State is data; criteria explicit about what counts; adversarial probes in calibration set [CITED: skill limits ref] |
| Stale pick after strategy edit routes to a removed model | Tampering/Elevation | `choice ∈ live candidates` check in validation — stale holds, never routes |

## Sources

### Primary (HIGH confidence — live-verified this session, 2026-10-11)
- Live `GET /api/v1/models?output_modalities=decisions` (19 entries, ids/canonical slugs/ctx/pricing) — no key needed
- Live `POST /api/alpha/decisions` ×2 (model-choice 200/0.33s luna@0.85 + $0.000016128; 30-option 200) — `OPENROUTER_API_KEY` from env
- Live `POST localhost:11434/v1/systemone` ×2 (tev1:0.8b choice + 40-option 2–26 rejection) + `/api/version` (0.40.3)
- In-repo reads: `routing.py` (full, 1231 lines), `router.py` setup section (586–960), `pyproject.toml` pytest config, uattest `driver.py` scenarios, AGENTS.md, 08-CONTEXT.md, 08-AI-SPEC.md, REQUIREMENTS.md, STATE.md

### Secondary (MEDIUM — official docs, extracted this session)
- https://openrouter.ai/skills/openrouter-decisions (7-step workflow, gating, probing)
- Skill refs: decisions-api.md (shapes, optional fields, SDK paths), models.md (pinning criteria, catalog fields), decision-model-limits.md (12 limits, verified on Jev 1.13)
- https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request (error codes 400–529, session_id/trace/user/provider)
- https://openrouter.ai/docs/guides/community/jev-tutorial (billing FAQ, response reading, alias guidance)
- https://docs.ollama.com/capabilities/decision + https://docs.ollama.com/api/systemone (shapes, 64 KiB cap, ≥0.35 floor, keep_alive)
- https://docs.typesafe.ai/confidence (confidence semantics, risk-scaled thresholds)
- https://ollama.com/library/nimble + https://ollama.com/library/clef (tags, sizes, requires, benchmarks — vendor numbers)

### Tertiary (LOW — third-party, flagged)
- https://jev-agent.com/decisions-api (model-dependent caps: Solar ≤26, hosted Tev1 ≤20; confidence-accuracy gaps)
- https://www.ayautomate.com/blog/how-to-use-jev-guide (255 options, latency distribution, rate limits)
- https://llmconfigurator.com/en/guides/decision-models/ollama-setup + https://modelfit.io/blog/ollama-decision-models-nimble-tev1-mac (setup, requires-0.35.0 blobs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; all claims live-verified or locked-file reads
- Architecture: HIGH — pattern is the locked AI-SPEC design + surviving in-repo machinery, both read this session
- Pitfalls: HIGH — the two load-bearing findings (vendor-specific confidence, 2–26 binding cap) are live-probe verified
- Pinning: HIGH for catalog snapshot; MEDIUM for durability — catalog changes silently, must re-verify at implementation
- Calibration defaults: LOW by design — no defaults ship from n=2 anecdotes; implementation probes produce them

**Research date:** 2026-10-11
**Valid until:** 2026-10-18 (fast-moving: decision-model catalog + pins; API shapes stable)

## RESEARCH COMPLETE



