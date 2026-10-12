# Phase 9: Native TypeSafe Decision Engine - Research

**Researched:** 2026-10-12
**Domain:** TypeSafe native System One API (`POST /v1/systemone`) + third routing engine in a Python CLI
**Confidence:** HIGH (every native API claim verified live this session: real catalog fetch, real decision calls, model-string matrix, error-shape matrix)
**Dispatch note:** Produced by gsd-phase-researcher 09 via the generic-agent workaround (typed dispatch unavailable); provenance tags follow the gsd-phase-researcher contract.

## Summary

TypeSafe's native API is the same System One protocol the CLI already speaks to OpenRouter and Ollama: `POST https://api.typesafe.ai/v1/systemone` with `{model, state, questions}`, `Authorization: Bearer $TYPESAFE_API_KEY`, returning `{model, answers, usage}`. I verified every claim live: the catalog (`GET /v1/models`, aliases only), real decision calls (200 in 0.11–0.20s, served snapshot `jev-1.13.0`), the model-string matrix, and the full error-shape matrix. The native transport is a near-clone of `decide_via_openrouter` minus provider metadata.

Three findings shape the plan most. First, **D-05's pinned string `jev-1.13` is invalid on native** — the API 400s `Unknown model: jev-1.13`; only full semver `jev-1.13.0` and the aliases `jev-latest`/`jev-preview` work. The planner must ship `jev-1.13.0` as the pin, not `jev-1.13`. Second, **native `usage` carries no `cost`** (`{input_tokens, output_tokens}` only, confirmed live and in the official docs example), so the planner must pick between code-side spend computation (exact arithmetic at the published flat rate) and unknown-spend display. Third, **native error codes differ from OpenRouter's**: missing key is 403 (not 401), unknown model and bad bodies are 400/422, and the body shape is `{"Detail": ...}` — retry classification must treat 4xx as hold-immediately, 429/529/5xx as the one-retry class.

**Primary recommendation:** Mirror `decide_via_openrouter` as `decide_via_typesafe` on the native endpoint with the verified model strings, plug it into the chain as a third link behind the new user-ordered engines list, compute native spend code-side from reported input tokens at the published $0.042/1M input-only rate (mark provenance), and calibrate with `--run native` against the shared 0.62/0.04 baseline — splitting knobs only on probe evidence of divergence.

## User Constraints (from CONTEXT.md)

### Locked Decisions

### Chain position
- **D-01:** Engine priority is user-ordered: the user picks a primary engine plus ordered fallbacks (multiple keys may exist). Stored as an ordered engines list in the strategy. — **Reversibility:** costly — the ordered list is consumed by setup, validate, the chain runner, and probes; reordering semantics touch all four.
- **D-02:** Setup proposes an intelligent default order from availability (keys present, Ollama reachable): native first when `TYPESAFE_API_KEY` exists, else the current OpenRouter → Ollama order.
- **D-03:** A listed engine with no key (or unreachable local) is skipped with a one-line note; the user can suppress these notes via config if noisy (planner scopes the knob).
- **D-04:** `TYPESAFE_API_KEY` is env-only, read at call time, never persisted — the locked no-keys-persisted posture carried forward (Phase 5 / OpenRouter precedent).
- **D-05:** Setup offers a pinned Jev list (`jev-1.13`, `jev-latest`, exact strings verified live); no native catalog fetch.
- **D-06:** The native engine is hidden in setup until `TYPESAFE_API_KEY` is present.
- **D-07:** `/route validate` live-pings the native engine (cheap call; catches bad keys and wrong model strings).
- **D-08:** Native failures (bad key, offline, unready) follow the same chain rules as other engines: skip/hold/pause with a distinct note (D-08/D-09 carried forward).

### Calibration
- **D-09:** Native reuses the shared knobs (0.62/0.04) and shared baseline unless probes prove divergence — same Jev model, different transport, expected identical behavior; split only on evidence.
- **D-10:** Probe runner gains `--run native` over the full 20-probe set, compared against the shared baseline.
- **D-11:** A native-vs-OpenRouter verdict disagreement is investigated as a bug, not resolved by preferring either side.

### the agent's Discretion
- Spend reporting when native `usage` lacks `cost`: researcher checks what native returns; planner picks unknown-vs-estimate presentation (OpenRouter injects `usage.cost`; native may not).
- Exact strategy schema for the ordered engines list and the note-suppression knob shape.
- Bare (`jev-1.13`) vs prefixed (`typesafe/jev-1.13`) model strings on native: researcher verifies live; planner implements the verified form. Same for the exact native endpoint path and auth scheme — the Gemini briefs below are leads, not sources.

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-04 | CLI can route decisions through Jev via TypeSafe's native API (`TYPESAFE_API_KEY`), alongside OpenRouter and Ollama engines | Native engine reference (endpoint/auth/shapes/pinning/caps/errors); transport code pattern; chain/preflight/validate/probe integration; spend-reporting options |

## Project Constraints (from AGENTS.md)

Actionable directives the planner must honor (same posture as Phase 8; AGENTS.md still maps `strands_code_agent/` only — CONTEXT.md §Canonical References supersedes for CLI orientation):
- Python ≥3.10, `uv` toolchain; stdlib-only HTTP via `urllib` (no `requests`, no TypeSafe SDK dependency).
- AWS-optional, never AWS-required; offline default holds (D-09 carried forward).
- No upper pins during the experimental phase.
- `snake_case` modules/functions, `UPPER_SNAKE_CASE` constants, `PascalCase` classes; one import per line, absolute imports.
- Fail-soft read paths (return degraded values, never raise to callers); log-and-continue for best-effort cleanup only.
- Module `logger = logging.getLogger(__name__)` with `%s`-style args; no `print()` in library code (transcript prints live in the turn layer via `print_plain`, markup off — WR-06).
- Why-comments only (1–2 lines); docstrings on public functions/classes.
- Constructor-kwarg configuration, never env sniffing (exception: runtime credentials `OPENROUTER_API_KEY`/`OLLAMA_API_KEY`/`OLLAMA_HOST` read at call time inside engine functions only — `TYPESAFE_API_KEY` joins this exact exception list per D-04).
- No keys in repo; API keys header-only, never logged. `save_strategy` drops api_key-shaped keys at top level and inside `engine` [VERIFIED: routing.py:404-476].
- Test files mirror modules: `tests/test_<module>.py`; pytest with `integration` marker deselected by default.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Native Decision-API transport (TypeSafe POST) | CLI process (execution layer) | — | Synchronous `urllib` call pre-turn at idle, same as the two existing engines |
| Ordered engines list + note-suppression knob | CLI process (composition layer) | — | Strategy schema extension; `_chain_for` consumes the order |
| Setup availability detection + default order | CLI presentation layer (`router.py`) | — | Env-presence checks + daemon preflight drive the D-02 proposal |
| Validate live-ping (D-07) | CLI presentation layer (`router.py`) | `routing.py` transport | Cheap decision call through the production transport |
| Threshold/tie-margin gating + hold-current | CLI process (execution layer) | — | Unchanged shared code (`gate_model`, D-09/D-14/D-16) |
| Spend display (`/cost` routing lines) | CLI presentation layer | — | `_routing_line` renders reported cost; native cost source is the planner's pick |
| Decision judgment itself | External Jev model (native) | — | Same probability-table contract; code owns everything else |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdlib `urllib` + `json` + `dataclasses` | builtin (Python ≥3.10) | Native Decision-API POSTs, typed answers | Locked posture; the native call is one JSON POST identical in shape to OpenRouter's |
| PyYAML | 6.0.3 (locked) | Strategy file load/save (ordered engines list) | Already used by `routing.py`; fail-soft precedent |
| platformdirs | (locked) | Global strategy path | Already used by `routing.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 (locked) | Hermetic chain/transport/strategy/setup tests | All phase tests; live tests behind `integration` marker |
| `scripts/route-probe.py` | repo script | `--run native` calibration over the 20-probe set | D-10 calibration + `--compare` regression |
| tmux + `scripts/uattest/driver.py` | repo rig | Live UAT for setup/validate/routing with native | Real key-present/key-absent flows hermetic tests cannot cover |

No new runtime dependency is added. No TypeSafe SDK (`typesafe-sdk` / `@typesafe-ai/sdk`) — the SDK only wraps the same single POST and would add a dependency for zero contract gain; the OpenRouter guide confirms the SDK is just a base-URL client over `/v1/systemone` [CITED: https://openrouter.ai/docs/guides/community/typesafe-sdk].

**Package Legitimacy Audit:** skipped — this phase installs zero packages (stdlib + locked deps only).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `urllib` | `typesafe-sdk` PyPI package | New dependency for one POST; SDK retry policy is uncontrolled and Ollama still needs raw HTTP — use `urllib` |
| Pinned native list (D-05) | `GET /v1/models` catalog fetch | The native catalog lists aliases only (verified live), so a fetch buys nothing over the verified pinned list — keep D-05 |
| Code-side spend computation | Unknown-spend display ($0.0000) | $0.0000 on paid calls misleads; the published flat input-only rate makes code-side computation exact — recommend compute (planner confirms) |

## Native Engine Reference (verified live 2026-10-12)

### Endpoint, auth, and request shape
- Base: `https://api.typesafe.ai` [VERIFIED: live probes this session — 200s on this host]; decision path `POST /v1/systemone` [VERIFIED: live probes + CITED: https://docs.typesafe.ai/models ("Every model on this page is served by the same endpoint, POST /v1/systemone")].
- Auth: `Authorization: Bearer $TYPESAFE_API_KEY`, header-only [VERIFIED: live probes + CITED: https://docs.typesafe.ai/models (curl example sends `-H "Authorization: Bearer $TYPESAFE_API_KEY"`)]. No-auth yields 403, bad key yields 401 (see Errors below).
- Request: `{model, state, questions}` — identical top-level shape to OpenRouter/Ollama [VERIFIED: live probes]. Optional `keep_alive` is Ollama-only; native docs show no extra fields — send exactly the OpenRouter payload minus provider metadata (per CONTEXT: mirror `decide_via_openrouter`).
- `state` accepts text, JSON objects, and arrays of text; text-only — no image/audio/video input [CITED: https://docs.typesafe.ai/models]. The existing `build_decision_state` (`ask`/`directives`/`side`) is valid native state [VERIFIED: live probes accepted it].
- Latency: 0.11–0.20s per call observed across 10 live calls [VERIFIED: live probes]. Keep `DECISION_TIMEOUT_SECONDS = 10` — ~50× headroom, same as OpenRouter.

### Verbatim response shape
`jev-latest` decision call, 200 [VERIFIED: live probe]:
```json
{"model":"jev-1.13.0","answers":{"pick":{"type":"choice","choice":"a","confidence":0.24,"probabilities":{"a":0.62,"b":0.38}}},"usage":{"input_tokens":317,"output_tokens":31}}
```
- `model` is the dated snapshot that served the request (`jev-1.13.0`) — log it per answer exactly like the OpenRouter `model` field for drift tracing.
- `answers` carries the same typed `choice` tables (with `confidence` + `probabilities`) — the shared `validate_choice_answer` + `gate_model` consume it unchanged.
- `usage = {input_tokens, output_tokens}` — **NO `cost` field** [VERIFIED: live probes on every 200 + CITED: https://docs.typesafe.ai/api (example response shows `"usage": {"input_tokens": 312, "output_tokens": 48}` with no cost key)]. This settles the agent's-discretion item: native never reports spend; the planner picks code-side computation vs unknown display (recommendation: compute — see Spend Reporting below).
- Probability rounding is 2-decimal (0.62/0.38, 0.74/0.26 observed) [VERIFIED: live probes] — same granularity as Jev-via-OpenRouter, so Pitfall 2's 0.01 grid floor and the shared 0.04 tie-margin survive unchanged.

### Model strings (live matrix — D-05 correction)
| String sent | Result | Served snapshot |
|-------------|--------|-----------------|
| `jev-latest` | 200 | `jev-1.13.0` |
| `jev-preview` | 200 | `jev-1.13.0` |
| `jev-1.13.0` | 200 | `jev-1.13.0` |
| `jev-1.13` | **400 `Unknown model: jev-1.13`** | — |
| `typesafe/jev-1.13` | **400 `Unknown model: typesafe/jev-1.13`** | — |
| `no-such-model` | 400 `Unknown model: no-such-model` | — |

[VERIFIED: live probes this session.] Consequences for the planner:
- **D-05's `jev-1.13` is wrong for native.** Ship the pinned list as `jev-1.13.0` (pin) + `jev-latest` (alias, explicit opt-in). CONTEXT anticipated this ("exact strings verified live") — this is the verification.
- Bare-vs-prefixed is settled: bare full-semver only; OpenRouter-style `typesafe/` prefixes are rejected. The two engines' model-string namespaces do not overlap — strategy schema needs a separate native model field (e.g. `engine.native_model`), never a shared id.
- `jev-preview` resolves to `jev-1.13.0` today but is a moving alias — never pin it, never offer it in setup (same rule as `~typesafe/jev-latest` on OpenRouter).

### Native catalog (`GET /v1/models`)
200, aliases only [VERIFIED: live probe]:
```json
{"models":[{"name":"jev-latest","description":"The latest iteration of TypeSafe's System One Model: Jev","release_date":"2026-09-10T18:38:01.391457+00:00"},{"name":"jev-preview","description":"A preview version of `jev-latest`: should be better in most ways","release_date":"2026-09-10T18:39:06.057655+00:00"}]}
```
Versioned IDs such as `jev-1.13.0` are accepted by the `model` field whether or not they appear in the list [CITED: https://docs.typesafe.ai/models ("Listing models")]. Requires auth (key-gated), unlike the OpenRouter decisions catalog. D-05 (pinned list, no catalog fetch) is confirmed as the right call — a fetch would return only the two aliases. The endpoint doubles as a free key-validity check if the planner wants one (no tokens spent), but D-07's validate ping must still be a decision call to catch wrong model strings.

### Pricing (Gemini $42/B-input lead: VERIFIED)
- $42 per Btok / $0.042 per Mtok input; output free [CITED: https://docs.typesafe.ai/models (Current models table: "Price (per Btok / per Mtok) | $42 / $0.042") + consistent tertiary: LiteLLM "$0.042 per 1M input tokens, no output charge"].
- Same rate as OpenRouter's `typesafe/jev-1.13` ($0.042/1M input, verified in Phase 8), so code-side native spend (`input_tokens × 0.042/1M`) reproduces exactly the number OpenRouter reports for the same call shape.
- Billing is input-tokens-only; output tokens free [CITED: https://docs.typesafe.ai/models + LiteLLM Jev launch post].

### Rate limits, context caps, retry classification
- Published limits: 100K tokens/second, 80 requests/second [CITED: https://docs.typesafe.ai/models]. (Older tertiary sources cite 250K tok/s + 1200 req/min as dynamic — the official models page value governs; either is far above per-ask volume.)
- Context: 64k tokens per request; 32k for `state` plus the longest question [CITED: https://docs.typesafe.ai/models]. The existing 64 KiB body cap + 2000-char ask truncation already undershoot this — no new truncation code.
- Errors use standard HTTP codes with a JSON body [CITED: https://docs.typesafe.ai/api]: 401 missing/invalid key, 422 body validation failure, 429 rate limit (back off and retry), 529 overloaded (retry after a short delay). SDKs retry 429/529 with backoff automatically; raw clients must implement it.
- Retryable (max 1 retry, reuse `_RETRYABLE_STATUS` + `_retryable_error`): 429/529/5xx/timeouts. The existing `_RETRYABLE_STATUS = {429, 500, 502, 503, 524, 529}` already covers the native retryable set — no change needed.
- Hold-immediately (never retry): 400/401/403/404/413/422 — wrong key, unknown model, malformed body.

### Verbatim error shapes (live matrix)
| Case | Code | Body |
|------|------|------|
| Bad key | 401 | `{"Detail":{"error_type":"authentication_error","message":"Cannot authenticate with the server. Please check your API key and try again."}}` |
| Missing `Authorization` header | **403** | `{"Detail":{"error_type":"authentication_error","message":"Must supply an API key! Check your request and try again."}}` |
| Unknown model | 400 | `{"Detail":{"error_type":"api_usage_error","message":"Unknown model: jev-1.13"}}` |
| Missing `questions` field | 422 | `{"Detail":[{"type":"missing","loc":["body","questions"],"msg":"Field required","input":{...}}]}` |

[VERIFIED: live probes this session.] Notes: the envelope key is capital-`Detail` (FastAPI style), unlike OpenRouter's lowercase `error` — but the transport only needs the HTTP code for retry classification, so no body parsing is required. Missing-key-as-403 (vs OpenRouter's 401) matters only for human-readable notes, not for code paths — both hold immediately.

### Choice floor difference (informational)
A 1-option `choice` returns 200 with `probabilities: {"a": 1.0}` on native [VERIFIED: live probe] — native does NOT enforce Ollama's 2–26 floor. No code change: the shared builders already skip degenerate questions (1-candidate skips call 1, single-level skips call 2), and the 26-cap stays for Ollama. Do not add a `none` criterion — the D-16 threshold gate remains the single no-match mechanism.

## Architecture Patterns

### System Architecture Diagram

```text
User ask ──► pre-turn @ idle ──► load_strategy ──► toggle on? ──► manual /model pin?
 (loop.py)        (D-01)              │                │ no            │ yes
                                     │                ▼               ▼
                                     │           serve current   serve pinned
                                     ▼ yes / configured
                    ┌──── ordered engines list (D-01) ────┐
                    │ e.g. [native, openrouter, local]    │
                    │  no-key/unready links SKIP + note   │
                    │  (D-03; suppressible via config)    │
                    └──────────────┬──────────────────────┘
                                   ▼ Call 1: model choice
                    ┌── native link ──► answers? ──► validate ──► gate_model
                    │   decide_via_typesafe      │ fail (4xx/schema)
                    │   TYPESAFE_API_KEY @call   ▼
                    ├── openrouter link ──► answers? ──► validate ──► gate_model
                    │                            │ fail
                    │                            ▼
                    └── local link ──► answers? ──► validate ──► gate_model
                                                 │ fail
                                                 ▼
                                          HOLD current (D-08)
                    below-threshold: HOLD immediately, no next engine (D-16)
                                   ▼ pick
                          Call 2: effort choice (same chain, same state)
                                   ▼
                    validate_routed_effort ──► fail HOLD
                                   ▼
                    apply switch + transcript line + /cost entry
                    (native spend: computed input×rate or unknown — planner picks)
```

Data flows one way, unchanged from Phase 8: strategy + ask → up to two sequential decision calls over the user-ordered chain → code gate → switch machinery → transcript/cost surfaces. The only structural delta is primary-select → ordered-list chain construction.

### Recommended Project Structure

Keep the single-module shape — do NOT split `routing.py`. The native engine is a third transport plus chain-registry generalization in the same file:

```text
strands_code_cli/
├── routing.py            # EXTEND: native transport + ordered chain + native schema keys
│   ├── (new) TYPESAFE_DECISIONS_URL + TYPESAFE_INPUT_USD_PER_MTOK constants
│   ├── (new) decide_via_typesafe (mirrors decide_via_openrouter, cost computed/absent)
│   ├── (rebuild) _ENGINE_REGISTRY/_chain_for: primary-select → ordered engines list
│   ├── (extend) _parse_engine/_TOP_LEVEL_KEYS/validate_strategy: engines list + native_model + note knob
│   └── (survive) state/question builders, validate_choice_answer, gate_model, decide() two-call flow
├── router.py             # EXTEND: setup (availability order, native branch, pinned Jev list) + validate live-ping
├── cost_context.py       # TOUCH: native spend rendering per the planner's spend pick
├── loop.py / btw.py      # TOUCH (maybe): skip-note rendering for D-03 if notes are transcript-level
scripts/route-probe.py    # EXTEND: --run native + native fault set (bad-key/no-key/unknown-model)
evals/routing-probe/      # EXTEND: native run records; baseline gains a native section on evidence
docs/ROUTING.md           # EXTEND: native engine setup/validate/cost docs
```

### Pattern 1: Native transport mirrors OpenRouter (shared `_post_decision`)
**What:** `decide_via_typesafe` reuses `_fit_decision_payload` + `_post_decision` (retry-once on the shared retryable set) with native URL/auth/usage mapping. Key read at call time via `os.environ.get("TYPESAFE_API_KEY")`, header-only, never logged (D-04).
**When to use:** The native chain link, the validate live-ping (D-07), and `--run native` probes — all three call the same function.
**Example:** see Code Examples below.

### Pattern 2: Chain links skip when unconfigured, hold-detail when attempted-and-failed
**What:** Keep the `EngineAttempt → EngineResult | None` contract (`None` = skipped, never attempted). The native link returns `None` when no native model is configured (and, per D-03, when the key is absent — planner confirms whether OpenRouter's link adopts the same skip-on-no-key or keeps its tried-and-failed shape).
**When to use:** Every `_chain_for` construction; both decision calls iterate the same chain.

### Pattern 3: Spend computed code-side from reported tokens at the published flat rate
**What:** `cost = input_tokens × 0.042 / 1_000_000`, output free. Exact arithmetic (same rate OpenRouter reports), not an estimate — but provenance-marked as code-computed since the API never returns `cost`.
**When to use:** Only if the planner picks compute-over-unknown (recommended). The alternative (cost=None → `$0.0000` line) misreports paid calls as free.

### Anti-Patterns to Avoid
- **Sharing one model-id field across OpenRouter and native:** the namespaces are disjoint (`typesafe/jev-1.13` 400s on native; `jev-1.13.0` is not an OpenRouter id) — separate schema fields, separate validate checks.
- **Retrying 400/401/403/422:** native 4xx (bad key, unknown model, malformed body) holds immediately, exactly like OpenRouter 4xx.
- **Gating on `confidence`:** unchanged from Phase 8 — gate on top-1 probability only (native `confidence` 0.24 on a 0.62/0.38 table matches neither engine's formula target; log it, never branch on it).
- **Fetching the native catalog in setup:** it lists aliases only and needs a key — the verified pinned list is strictly better (D-05 stands).
- **Persisting `TYPESAFE_API_KEY`:** env-only per D-04; `save_strategy` already drops api_key-shaped keys — the native setup branch must never write one.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Decision POST + retry | New HTTP layer | `_post_decision` + `_RETRYABLE_STATUS` (already includes 429/529) | Retry-once/backoff semantics are built and tested; native needs only a new URL + headers |
| Answer validation + gating | Native-specific parsing | `validate_choice_answer` + `gate_model` unchanged | Native tables are the same typed shape (verified live); a second validator invites silent drift |
| Spend math | Token estimation | Reported `input_tokens` × published rate | Tokens are reported; only the rate is a constant — estimation would add error for nothing |
| Setup pickers | New dialog widgets | `_setup_ask`/typed pickers [VERIFIED: router.py:710-895] | Owned-keys radio + off-tty typed paths already handle abort/re-prompt |
| Engine registry | Parallel chain code | Generalized `_ENGINE_REGISTRY` + `_chain_for` | One chain serves both decision calls; a second chain doubles the hold/pause logic |

**Key insight:** the native engine is a transport swap, not a new decision path. Everything above the transport (state, questions, validation, gate, verdict, cost plumbing, probes) is engine-agnostic by Phase 8 design — the phase adds one POST function, one schema list, and setup/validate/probe branches.

## State of the Art

| Phase 8 (current) | Phase 9 (this phase) | Impact |
|--------------|------------------|--------|
| `engine.primary: openrouter\|local\|off` selects the chain | Ordered `engines` list drives `_chain_for` order | `_chain_for`, `_parse_engine`, validate, setup all generalize; `primary` migrates or coexists (planner picks, fail-soft on old files) |
| Two transports (`decide_via_openrouter`, `decide_via_ollama`) | Third transport `decide_via_typesafe` | New function only; `_post_decision`, builders, gate survive |
| Setup: engine radio (openrouter/local) + decisions-catalog decider pick | Setup: availability-driven default order + native branch (pinned Jev list, hidden without key) | `_route_setup_message` extends; pinned list is `jev-1.13.0` + `jev-latest`, NOT `jev-1.13` |
| Validate: file-only, no network | Validate: file checks + native live-ping (D-07) | New branch in `_route_validate_message`; cheap decision call catches bad keys + wrong model strings |
| Probe `--run openrouter\|local` | Probe `--run native` + native faults | `run_probe`/`_FaultContext` extend; full 20-probe set vs shared baseline (D-10) |
| Spend: OpenRouter reported `cost`, local None→$0 | Native: computed input×rate (recommended) or None→$0 | Planner picks; `cost_context` renders per pick |

**Calibration method (D-09/D-10/D-11):** run the full 20-probe set via `--run native` with pin `jev-1.13.0`, diff against `baseline.json` with `--compare`. Shared 0.62/0.04 knobs stand unless the native run shows systematic divergence (routed-but-wrong above threshold, or mass hold where OpenRouter routes). Any native-vs-OpenRouter verdict disagreement is a bug investigation (D-11), not a knob change — same Jev weights, different transport, expected identical tables modulo 2-decimal rounding. Record the native run (distributions + snapshot `jev-1.13.0`) in the baseline file.

**Deprecated/outdated:**
- `engine.primary` as the sole chain selector: superseded by the ordered list (D-01) — planner decides migration vs dual-support.
- `jev-1.13` as a native model string: never valid — 400s live. (It remains the correct OpenRouter id `typesafe/jev-1.13`; the two namespaces must not be confused.)
- Gemini briefs as sources: all leads verified or corrected above; cite only the live probes and official docs URLs in this document.

## Common Pitfalls

### Pitfall 1: `jev-1.13` 400s on native — the D-05 string must be corrected
**What goes wrong:** Setup writes `jev-1.13` per a literal D-05 reading; every native call holds with `native HTTP 400`.
**Why it happens:** OpenRouter ids (`typesafe/jev-1.13`) and native ids (`jev-1.13.0`) look interchangeable but the native API requires full semver or alias [VERIFIED: live probes].
**How to avoid:** Pin `jev-1.13.0`; offer `jev-latest` as the explicit alias choice; validate live-ping (D-07) catches any regression.
**Warning signs:** Native-only `HTTP 400` holds while OpenRouter routes the same ask.

### Pitfall 2: Native `usage` has no `cost` — `/cost` silently shows $0.0000 for paid calls
**What goes wrong:** `EngineResult.cost=None` flows into `_routing_line`, which renders `$0.0000` and adds nothing to totals — paid native spend vanishes from the report.
**Why it happens:** `_routing_line` treats None as local/zero [VERIFIED: cost_context.py:190-222]; native is the first paid-but-costless engine.
**How to avoid:** Planner picks compute (recommended: input×$0.042/1M, exact) vs explicit unknown-spend display (e.g. `$?` + note). Never silently $0.
**Warning signs:** `/cost` routing lines `via native $0.0000` with nonzero input tokens.

### Pitfall 3: 403-means-no-key on native (vs 401 on OpenRouter)
**What goes wrong:** A note/logs classifier that maps 401→"bad key" mislabels a missing-key 403, or a retry policy that retries 403s.
**Why it happens:** Native returns 403 for a missing `Authorization` header and 401 for a wrong key [VERIFIED: live probes] — both hold-immediately, neither retries.
**How to avoid:** Treat all native 4xx uniformly (hold, no retry); if notes distinguish, map 401→bad key, 403→missing key.
**Warning signs:** Retry storms on misconfigured keys; confusing hold notes.

### Pitfall 4: Ordered-list migration breaks existing strategies
**What goes wrong:** Old files with `engine.primary` fail to load or silently change chain order after the schema migration.
**Why it happens:** D-01 replaces the selector the loader, validate, setup, and probes all consume (costly reversibility, noted in D-01).
**How to avoid:** Fail-soft loader: `primary: openrouter` → `[openrouter, local]` (current order), `primary: local` → `[local]`, `primary: off` → routing off; validate flags the legacy shape with a fix line instead of failing.
**Warning signs:** Routing silently off after upgrade; validate INVALID on untouched files.

### Pitfall 5: Skip-notes noise (D-03) spams every ask
**What goes wrong:** A listed-but-keyless engine prints a note on every routed ask, burying the transcript line.
**Why it happens:** The skip check runs per ask (key presence can change mid-session, so it cannot be cached at load).
**How to avoid:** Planner scopes the suppression knob (D-03); default should note once per session or per `/route` status, not per ask. Probe: keyless-native strategy routes via fallback with exactly one note.
**Warning signs:** Transcript doubled in length after adding a keyless engine to the list.

### Pitfall 6: `none`/alias drift — `jev-latest` moves silently
**What goes wrong:** Thresholds calibrated on `jev-1.13.0` drift when `jev-latest` resolves to a new build; probes go red without a code change.
**Why it happens:** Aliases are moving targets (same rule as OpenRouter's `~typesafe/jev-latest`).
**How to avoid:** Setup defaults to the pinned `jev-1.13.0`; `jev-latest` is an explicit opt-in with a drift warning; every verdict record logs the serving snapshot so `--compare` flags moves.
**Warning signs:** `--compare` snapshot-change warnings cluster after a TypeSafe release.

## Code Examples

### Native transport (mirrors `decide_via_openrouter`)
```python
# Source: live probes 2026-10-12 + routing.py decide_via_openrouter pattern
TYPESAFE_DECISIONS_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_INPUT_USD_PER_MTOK = 0.042  # CITED: https://docs.typesafe.ai/models

def decide_via_typesafe(*, native_model, state, questions,
                        timeout=DECISION_TIMEOUT_SECONDS):
    api_key = os.environ.get("TYPESAFE_API_KEY")  # call time only (D-04)
    if not api_key or not native_model:
        return EngineResult(answers=None)
    payload, truncated = _fit_decision_payload(
        {"model": native_model, "state": state, "questions": questions}
    )
    data, error = _post_decision(TYPESAFE_DECISIONS_URL, payload, {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "strands-code",
    }, timeout)
    if data is None:
        return EngineResult(answers=None, error=error, truncated=truncated)
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return EngineResult(answers=None, error="invalid body", truncated=truncated)
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    model = data.get("model")
    in_tok = _count(usage.get("input_tokens"))
    return EngineResult(
        answers=answers,
        input_tokens=in_tok,
        output_tokens=_count(usage.get("output_tokens")),
        # No usage.cost on native: exact code-side computation at the
        # published flat input-only rate (planner confirms vs unknown).
        cost=in_tok * TYPESAFE_INPUT_USD_PER_MTOK / 1_000_000,
        model=model if isinstance(model, str) else None,
        truncated=truncated,
    )
```

### Native preflight / readiness (chain skip + setup detection)
```python
# Source: D-03/D-06 + local_engine_ready precedent (routing.py)
def native_engine_ready() -> bool:
    """True when a native call is worth attempting: key present.

    No network: like the OpenRouter link (which has no preflight),
    attempted-call failure carries the detail (401 bad key, 403 no
    key, 400 unknown model). Daemon-style version/tag checks do not
    apply to a hosted API.
    """
    return bool(os.environ.get("TYPESAFE_API_KEY"))
# _chain_for: native link skipped (None) when no native model is
# configured OR the key is absent; the skip emits the D-03 one-line
# note (suppressible via the planner's knob).
```

### Validate live-ping (D-07)
```python
# Source: D-07 + decide_via_typesafe above; ~300 input tokens ≈ $0.000013
result = decide_via_typesafe(
    native_model=strategy.engine.native_model,
    state={"ask": "validate", "directives": "", "side": False},
    questions={"ping": {"type": "choice",
                        "instructions": "Which option?",
                        "criteria": {"a": "first", "b": "second"}}},
)
# answers None + error "HTTP 401/403" -> bad/missing key line (INVALID)
# answers None + error "HTTP 400"     -> wrong model string line (INVALID)
# answers present                     -> native engine ok line (VALID)
# NOTE: 08 validate_strategy is file-only/no-network; the live-ping is
# a NEW network branch in _route_validate_message (planner scopes
# whether it runs always or only when native is listed).
```

### Setup pinned Jev list (D-05 corrected)
```python
# Source: live model-string matrix 2026-10-12 (jev-1.13 400s; full semver only)
NATIVE_JEV_PIN = "jev-1.13.0"      # default pin — full semver, verified 200
NATIVE_JEV_ALIAS = "jev-latest"    # explicit opt-in alias, drift warning (Pitfall 6)
# Offer via the existing _setup_ask radio (tty) / validated typed id
# (off-tty); never jev-preview (moving), never jev-1.13 (400s),
# never typesafe/-prefixed ids (400s).
```

### Probe extension (`--run native`)
```python
# Source: scripts/route-probe.py run_probe/_FaultContext pattern
NATIVE_MODEL_PIN = "jev-1.13.0"
# run_probe(engine="native") calls decide_via_typesafe with the shared
# state/question builders + gate_model; record pin/snapshot/table.
# _FaultContext gains native faults: bad-key/no-key swap TYPESAFE_API_KEY
# (bogus value only, never the real one), unknown-model overrides the id,
# timeout/dead-port reuse the shared paths. Compare via --compare
# against baseline.json (D-10); disagreement with the OpenRouter run is
# a bug investigation (D-11), not a tie-break.
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Older tertiary rate limits (250K tok/s, 1200 req/min, dynamic) are superseded by the official models page (100K tok/s, 80 req/s) | Engine Reference | LOW — per-ask volume is orders below either; 429 path holds+notes regardless |
| A2 | Native probability rounding stays 2-decimal (observed on 10 calls) | Engine Reference | LOW — grid floor 0.01 already assumed; `--compare` top-1-drift warnings would flag a change |
| A3 | `jev-preview` keeps resolving to the stable build (observed `jev-1.13.0` today) | Model strings | NONE — never pinned or offered; alias behavior is irrelevant to the plan |
| A4 | Native keeps accepting the shared `{ask, directives, side}` state object (accepted live today) | Request shape | LOW — validate live-ping + integration tests fail loudly on contract drift |
| A5 | The published $0.042/1M input-only rate holds through implementation (no pricing API to poll) | Pricing | LOW — rate is a named constant; a price change needs one constant bump, and OpenRouter's reported `cost` cross-checks it |

## Open Questions (RESOLVED)

1. **Compute-vs-unknown native spend (agent's-discretion item — research input complete)** — RESOLVED (plan 09-01 objective + tasks 1-2: compute into cost at $0.042/1M input-only with computed-rate Prices marker, never silent $0)
   - What we know: native `usage` never carries `cost` (verified live + docs); the rate is published flat input-only ($0.042/1M), so code-side computation is exact arithmetic identical to OpenRouter's reported number.
   - What's unclear: planner/UX pick — computed spend in the `cost` field (renders inline, folds into totals) vs explicit unknown display.
   - Recommendation: compute into `cost` with a provenance note (e.g. `/cost` Prices line keeps native marked estimated-in-code); never silent $0. MODEL-05 (provider-reported actuals) can later refine the marking.

2. **Ordered-list schema shape (agent's-discretion item)** — RESOLVED (plan 09-01 tasks 1+3: order/native_model/skip_notes keys; legacy primary maps to the equivalent order with a validate nudge, no auto-rewrite)
   - What we know: D-01 locks an ordered engines list; the loader must stay fail-soft on legacy `primary` files (Pitfall 4).
   - What's unclear: exact key names (`engines: [native, openrouter, local]` vs `engine.order`), the note-suppression knob shape, and whether `primary` migrates or coexists.
   - Recommendation: planner picks names; loader maps legacy `primary` to the equivalent order with a validate fix-line nudge (no auto-rewrite).

3. **Skip-on-no-key for cloud links (D-03 vs OpenRouter precedent)** — RESOLVED (plan 09-01 task 2: native link skips on absent key with the D-03 note path; OpenRouter link shape explicitly unchanged)
   - What we know: D-03 says a listed engine with no key is skipped with a note; the current OpenRouter link tries-and-fails on missing key (answers=None, error None → "openrouter failed").
   - What's unclear: whether the native link (and retroactively the OpenRouter link) returns None-skip on absent key, and where the one-line note renders (transcript vs status).
   - Recommendation: native link skips (None) on absent key with the D-03 note path; leave the OpenRouter link's shape untouched unless the planner unifies both (flag as explicit decision).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + pytest | All tests | ✓ | pytest 9.1.1 (locked) | — |
| `TYPESAFE_API_KEY` in shell env | Native transport + validate ping + `--run native` | ✓ | present in ~/.bashrc (count-verified, never printed) | Skip live tests; hold-current |
| `OPENROUTER_API_KEY` | OpenRouter-vs-native parity checks | ✓ | present in ~/.bashrc | Parity checks skipped |
| Ollama daemon + `nimble` | Fallback-order tests, full-chain UAT | ✓ (Phase 8) | daemon 0.40.3, nimble pulled | Chain tests stub the local link |
| `api.typesafe.ai` reachable | All live native work | ✓ | 0.11–0.20s/call observed | Hold-current; skip live tests |
| tmux | uattest rig (setup/validate scenarios) | presume ✓ (rig ran Phase 8) | — | Hermetic tests only, note gap |

**Missing dependencies with no fallback:** none (every live layer degrades to hold/skip).
**Missing dependencies with fallback:** none outstanding.

## Validation Architecture

Test framework: pytest 9.1.1, `addopts = "-m 'not integration'"` (live tests deselected by default). Existing routing tests extend in place: `tests/test_routing.py`, `tests/test_routing_strategy.py`, `tests/test_loop_routing.py`; probe runner `scripts/route-probe.py`; baseline `evals/routing-probe/baseline.json`.

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
| MODEL-04 | Native transport: answers+usage parse, snapshot logged, cost computed/absent per pick, key header-only | unit (stubbed POST) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-04 | Native faults: 400/401/403/422 hold zero-retry; 429/529/5xx/timeout retry-once then next link; offline pauses | unit (fault injection) | `uv run pytest tests/test_routing.py -q` | ✅ extend |
| MODEL-04 | Ordered chain: user order honored; keyless/unready links skip with note; legacy `primary` maps fail-soft | unit | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py -q` | ✅ extend |
| MODEL-04 | Strategy: engines list + native_model + note knob load/validate; `jev-1.13` rejected, `jev-1.13.0` accepted | unit | `uv run pytest tests/test_routing_strategy.py -q` | ✅ extend |
| MODEL-04 | Setup: native hidden without key; default order from availability; pinned list offers corrected strings | unit + live | quick cmd + `driver.py` setup scenario | ✅ extend + rig |
| MODEL-04 | Validate: file checks + native live-ping (bad key / wrong model fail with fix lines) | unit + live | quick cmd + rig validate scenario | ✅ extend + rig |
| MODEL-04 | Same verdict shape: native-routed ask yields identical pick/confidences/cost-line shape as OpenRouter | unit (stubbed) + probe | quick cmd + `route-probe.py --run native` | ✅ extend + probe |
| MODEL-04 | Calibration: 20-probe native run vs shared baseline; divergence splits knobs, disagreement = bug (D-11) | probe | `route-probe.py --run native` + `--compare` | ✅ extend runner |
| MODEL-04 | Live native: real Jev round-trip, spend accounting, latency shape | integration (gated) | `uv run pytest -m integration -q` + rig | ✅ rig exists, scenarios updated |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green + `--run native` 20-probe record vs baseline before verify

### Wave 0 Gaps
- [ ] `tests/test_routing*.py` — extend with native transport/chain/strategy cases (no new files needed)
- [ ] `scripts/route-probe.py` — `--run native` engine + native fault set in `_FaultContext`
- [ ] `evals/routing-probe/baseline.json` — native run section after calibration (distributions + snapshot)
- [ ] uattest setup/validate scenario updates for the native branch (key-present/key-absent/availability-order)

## Security Domain

ASVS Level 1, `security_enforcement: true`, block on high (per `.planning/config.json` workflow section).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `TYPESAFE_API_KEY` env-only at call time, `Authorization: Bearer` header-only, never logged/persisted (D-04; OpenRouter precedent) |
| V3 Session Management | no | No sessions; stateless per-ask POSTs |
| V4 Access Control | no | Single-user CLI; strategy files 0700-parent precedent via `save_strategy` |
| V5 Input Validation | yes | Model-string allowlist (pinned list + validate ping); `_validate_choice_shape` on answers; body-cap fit before POST |
| V6 Cryptography | no | TLS via `urllib`/system store; no hand-rolled crypto |
| V9 Communications | yes | HTTPS-only endpoint constant; key never in URL/query/logs; probe records carry tables/snapshots, never secrets |

### Known Threat Patterns for urllib + API-key CLI transports

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Key exfiltration via logs/errors | Information disclosure | Header-only auth; `_failure_reason` returns classes, never bodies/headers; probes use bogus key values for fault cases |
| Key persistence in strategy files | Information disclosure | `save_strategy` drops api_key-shaped keys (top + `engine`); setup never prompts for keys |
| Malicious repo strategy injection | Tampering | State/question builders truncate ask+directives; body-cap fit; model strings constrained to verified ids |
| Stale-pick routing after strategy edit | Tampering | `validate_choice_answer` membership check — stale choices hold, never route |

## Sources

### Primary (HIGH confidence — live probes + official docs this session)
- Live native probes 2026-10-12: `GET /v1/models` (200, alias catalog), 10× `POST /v1/systemone` (model-string matrix, error-shape matrix, usage/cost absence, latency 0.11–0.20s) — key read from ~/.bashrc at call time, never printed/persisted; scratch in /tmp only
- [https://docs.typesafe.ai/models](https://docs.typesafe.ai/models) — endpoint path, auth header, price $42/Btok, rate limits 100K tok/s + 80 req/s, context 64k/32k, text-only, versioned-id acceptance
- [https://docs.typesafe.ai/api](https://docs.typesafe.ai/api) — response shape (no `cost` in `usage`), error codes 401/422/429/529 + backoff guidance
- [https://openrouter.ai/docs/guides/community/typesafe-sdk](https://openrouter.ai/docs/guides/community/typesafe-sdk) — SDK is a base-URL client over `/v1/systemone`; Bearer auth from `apiKey`/`TYPESAFE_API_KEY`

### Secondary (MEDIUM confidence — tertiary, consistent with primary)
- [https://docs.litellm.ai/blog/typesafe_jev](https://docs.litellm.ai/blog/typesafe_jev) — $0.042/1M input, no output charge; `https://api.typesafe.ai` base; `GET /typesafe/v1/models` passthrough
- [https://www.truefoundry.com/docs/ai-gateway/jev](https://www.truefoundry.com/docs/ai-gateway/jev) — base URL + `/v1/systemone` evaluate path + `/v1/models` listing; Bearer auth
- [https://befailproof.ai/jev/pricing](https://befailproof.ai/jev/pricing) — $42/B input, 64k/32k context (older dynamic-limit figures superseded by the official page)

### In-repo (verified by Read this session)
- `strands_code_cli/routing.py` — `_post_decision` + `_RETRYABLE_STATUS` (lines 1058–1084, 71–72), `decide_via_openrouter` (1087–1138), `EngineResult` (912–935), `_chain_for` (1494–1523), `gate_model` (1364–1403), strategy load/validate (316–401, 603–812)
- `strands_code_cli/router.py` — setup pickers + `_route_setup_message` (841–1031)
- `strands_code_cli/cost_context.py` — `_routing_line` reported-spend rendering (190–222)
- `scripts/route-probe.py` — probe runner structure (`--run`/`--compare`, `_FaultContext`, pins)
- `.planning/phases/08-model-routing-with-decision-models/08-RESEARCH.md` — Decision-API contracts, probe precedent, pitfalls (extended, not redone)
