# Phase 8: Model Routing with Decision Models — Research

**Researched:** 2026-10-11
**Domain:** Per-ask model + thinking-budget routing via a cheap decision model (OpenRouter API default, local-model alternative), pre-turn decision point, models-only fallback, transcript + /cost visibility
**Confidence:** HIGH
**Researcher note:** Typed `gsd-phase-researcher` dispatch is unavailable in this runtime; this file was produced by a generic-agent workaround following the researcher contract.

<user_constraints>

## User Constraints (Locked Decisions + Agent's Discretion + Deferred Ideas copied VERBATIM from CONTEXT.md)

### Routing scope and strategy config
- **D-01:** Routing is auto-on only when a strategy is configured (candidate model set + directives). Without config there is not enough information to route, so routing stays off. — **Reversibility:** costly — the default posture shapes the turn loop and config surface; flipping it later changes every-turn behavior and the setup contract.
- **D-02:** Strategy shape is candidate models plus freeform scenario directives (e.g. "trivial asks go cheap, deep refactors go big"). Candidate entries may carry model descriptors — relative size/role notes (Sol=mega / Terra=mid / Luna=small; Opus/Sonnet/Haiku tiers) — potentially with pulled compound benchmarks to help ranking.
- **D-03:** Strategy lives both globally and per workspace; repo wins on conflict (Phase 3 D-08 policy precedence).
- **D-04:** Main turns and `/btw` side questions both route through the same strategy; side asks are flagged as side so directives can discriminate (closes the Phase 7 D-07 revisit).
- **D-05:** Thinking-level routing within thinking-capable models is in scope: the router picks a thinking level automatically, not just the model.

### Decision engine and fallback
- **D-06:** OpenRouter's decision-model API is the default decision engine until Bedrock offers decision models; local models are supported as the alternative. Setup enumerates OpenRouter's open-model selection for user choice (Laya/Kev are candidates within it, not the whole menu).
- **D-07:** Directives plus candidate stats feed every decision call, API or local. Directives shape all decisions; they never sit idle while the model decides without them.
- **D-08:** Fallback chain is models-only: decision API → local model → pause and hold the current model, retrying next ask. No heuristic ever picks a model. Roadmap SC2's "deterministic heuristic fallback" is satisfied by deterministic hold-current (a fixed rule, not a heuristic pick) — planner/researcher note this reinterpretation.
- **D-09:** Fully offline behavior is local decision model if configured, otherwise routing pauses and the current model is used (AWS-optional posture holds: no network, no API, no guessing).

### Override and visibility
- **D-10:** Routing has a session-sticky toggle (Phase 4/6 precedent). `/model` re-points immediately but warns the switch turns routing off and offers cancel to keep routing; a slash command turns routing back on. More routing slash commands are expected (planner scopes them).
- **D-11:** Routed switches are silent plus a transcript note; model choice never raises an approval prompt. Deny-first stays for tool side effects, not for routing.
- **D-12:** Every routed ask gets one transcript line (model, why, cost impact), suppressible via config to cut noise; `/cost` carries the fuller routing detail.

### Strategy setup
- **D-13:** Guided setup flow creates the strategy (enumerate OpenRouter models, capture directives). Example strategies ship in the docs, manual file edits are allowed, and a slash command validates the configuration's validity.

### the agent's Discretion
- Routing slash command names and subcommand shapes (toggle on/off, setup, validate, status).
- Strategy file format, filenames, and exact global/workspace paths.
- Transcript line format and the /cost routing section shape.
- Hold-current retry/notify behavior (silent hold vs transcript note on failure).
- Descriptor/benchmark schema for candidate entries (researcher confirms sources first).
- Side-ask decision-call mechanics (per-ask call vs derived) within D-04.

### Deferred Ideas
- CodeAct action interface (Phase 9).
- Cost budgets/enforcement (locked: display only).
- Heuristic model-picking — rejected, not deferred: directives + models only.
- Fully automatic routing with no override — locked out; manual switching + toggle always win.

</user_constraints>

<phase_requirements>

| Req | Text | How this research covers it |
|-----|------|-----------------------------|
| MODEL-03 | CLI auto-selects model and thinking budget per ask via a decision model (Jev/Kev/Laya class), with manual override | Decision-call architecture (OpenRouter chat completions on a cheap model with a routing prompt; NOT the `openrouter/auto` turn router), candidate sourcing from strategy + almanac, thinking budget via harness `effort`, manual override via session toggle + `/model` warn-and-cancel, visibility via transcript line + `/cost` |

Notes on MODEL-03 wording: "Jev/Kev/Laya class" names a *class* of cheap small models, not literal ids — live catalog verification found zero models matching `laya`, `kev`, or `jevi` substrings [VERIFIED: live `curl https://openrouter.ai/api/v1/models`, 458 models, 2026-10-11]. Setup MUST enumerate the live catalog; never hardcode these names. The roadmap's "deterministic heuristic fallback" is reinterpreted per D-08 as deterministic hold-current (fixed rule, not a heuristic pick).

</phase_requirements>

## Summary

Phase 8 routes each ask pre-turn through a cheap decision model that returns a structured pick (candidate model + thinking level + one-line why). The decision engine is a plain OpenRouter chat-completions call on a user-chosen cheap model — there is no separate "decision-model API" product; D-06's "OpenRouter decision-model API" maps to `POST https://openrouter.ai/api/v1/chat/completions` with a routing prompt and `response_format: json_object`, plus the public `GET /models` catalog for setup enumeration. This is deliberately NOT `openrouter/auto`: the Auto Router executes the turn itself on OpenRouter infrastructure and only reveals its pick in the response `model` field, which cannot drive Bedrock-first turns, thinking-budget selection, or user directives. The local alternative is a raw-HTTP call to an Ollama daemon (`POST /api/chat` with `stream: false` and a JSON `format`), which needs no new dependency; the `ollama`, `openai`, and `litellm` Python packages are all absent from the project venv, and the codebase precedent (`live_pricing.py`) already does HTTP via stdlib `urllib`.

All application seams already exist. The harness resolves thinking budgets today: `resolve_model(model, default, effort=...)` maps one `effort` value onto each provider's native fields (`additional_request_fields` on Bedrock, `params` on Anthropic-direct, `reasoning.effort` on OpenAI-family), with `EFFORT_LEVELS = ("auto", "off", "minimal", "low", "medium", "high", "xhigh", "max")`. The CLI never passes `effort` today, so the planner must thread a routed level from the decision call through the switch path (`apply_switch` → `resolve_model`) and into `/btw` side-agent rebuilds. The decision point sits in `run_loop` after `dispatch` returns `"agent"` and the plan-prefix is applied, before the retry loop calls `_invoke_agent`; the switch itself reuses `apply_model_action` (restore-then-convert, convert-when-fits, in-place swap), which keeps Phase 5's one-model-per-turn and idle-only-switches contracts intact. Fallback is models-only per D-08: decision API → local model → pause-and-hold-current with retry next ask; every layer fails soft exactly like the `live_pricing` layering precedent, and nothing in this phase may pick a model by heuristic.

**Primary recommendation:** Build a `routing.py` decision-call module (stdlib `urllib` to OpenRouter chat completions with a JSON routing prompt; Ollama `/api/chat` as the local engine), a fail-soft YAML strategy file (global + repo, repo wins) holding candidates + directives + descriptor/benchmark snapshot, a pre-turn hook in `run_loop` that reuses `apply_model_action`, and visibility via one `print_plain` transcript line plus a `/cost` routing section — with zero new dependencies.

## Project Constraints (from AGENTS.md)

Same authority as locked decisions [VERIFIED: `AGENTS.md:11-16`, read this session]:

- **Tech stack:** "Python >=3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform". Routing pads `resolve_model`/`create_harness` seams; it must not reimplement vendor request formats.
- **AWS posture:** "AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports". D-09 offline behavior (local-or-pause, no network, no guessing) is this constraint restated; the decision path must lazy-import `boto3` exactly like `fetch_bedrock_records` does.
- **Compatibility:** "no upper pins during the experimental phase; resync upstream deliberately, not continuously". New config/schema must tolerate harness drift (e.g. `supports_thinking` import guard precedent in `model_switch.py:20-23`).
- **No env sniffing:** "No `.env` files, no `os.environ`/`os.getenv` reads anywhere ... all tuning is constructor kwargs" [VERIFIED: `AGENTS.md:61`]. Strategy and engine choice arrive as constructor kwargs / explicit config paths. Caution: the decision engines inherently need credentials at runtime (OpenRouter key, `OLLAMA_HOST`); the harness itself reads `OLLAMA_API_KEY`/`OLLAMA_HOST` env in `_ollama`, so engine credentials follow the harness precedent (runtime-supplied, never persisted — same rule as `ProviderConfig`: "never keys" [VERIFIED: `provider_config.py:32-33`]).
- **Naming/style:** `snake_case` modules mirroring `test_<module>.py`, no formatter/linter configured — match surrounding style by hand [VERIFIED: `AGENTS.md:86-101`].
- **Error handling:** fail-soft read paths ("return formatted 'not found' strings ... instead of raising"), log-and-continue only for best-effort cleanup [VERIFIED: `AGENTS.md:108-116`]. The whole engine chain inherits this: decision failures yield hold-current + transcript note, never raise into the turn.
- **Output:** "Never use `print()` in library code" for human-facing output; transcript prints go through `print_plain` (markup off) [VERIFIED: `AGENTS.md:121`, `output.py:34-42`].

## Architectural Responsibility Map

| Piece | Owner (new or existing) | Responsibility |
|-------|------------------------|----------------|
| Strategy file (global + repo) | NEW `routing_strategy.py` (name at planner discretion) | Fail-soft YAML load, repo-wins merge, candidate + directive + descriptor schema, `validate` logic for the slash command |
| Decision call | NEW `routing.py` (name at planner discretion) | Build routing prompt (directives + candidate stats table), call engine, parse strict JSON pick, record spend |
| OpenRouter engine | `routing.py` (stdlib `urllib`) | `POST /api/v1/chat/completions` on the configured cheap decision model, `response_format` JSON, timeout + fail-soft |
| Local engine | `routing.py` (stdlib `urllib`) | `POST {OLLAMA_HOST}/api/chat`, `stream:false`, JSON `format`; fail-soft to hold-current |
| Setup enumeration | NEW setup flow in router/loop | `GET /models` (reuse `fetch_openrouter_models` + cache), `radio_choice` picker, directive capture |
| Pre-turn hook | `loop.py run_loop` edit | After `"agent"` action + plan-prefix, before retry loop: decide → `apply_model_action` → transcript note |
| Switch application | EXISTING `apply_model_action` | Restore-then-convert, convert-when-fits, in-place swap; planner threads routed `effort` through it |
| Thinking budget | EXISTING harness `resolve_model(..., effort=)` | Effort→provider-field mapping; CLI must start passing `effort` explicitly |
| Session toggle | `loop.py` (session-sticky holder, Phase 4/6 precedent) | Routing on/off; `/model` warn-and-cancel flips it off |
| Slash commands | EXISTING `router.py dispatch` branches | Toggle/setup/validate/status as reply actions; USAGE_HINT extension |
| Visibility | `print_plain` + `cost_context.py` | One transcript line per routed ask; `/cost` routing section + decision-call spend rows |
| Side asks | `loop.py _build` closure + `btw.py` | Same strategy, flagged `side:true`; routed model passes to `build_btw_agent` via parent kwargs |
| Candidate stats | EXISTING almanac (`live_pricing` + `cost_context` + `model_switch` verdicts) | Price/window/capability rows feeding the decision prompt |

## Standard Stack

No new dependencies. Every engine call goes over stdlib `urllib`, following the `live_pricing.py` precedent ("Public endpoint: per-model pricing + context_length, no key needed" [VERIFIED: `live_pricing.py:41-42`, verbatim]).

### Core (already installed — versions verified via `uv pip list` this session)

| Package | Installed | Role in this phase |
|---------|-----------|--------------------|
| `strands-harness` | 0.1.2 | `resolve_model(..., effort=)` thinking-budget mapping; `create_harness(model=, effort=)` factory; `supports_thinking` verdicts |
| `strands-agents` | 1.58.1 | `Model`/`ModelRouter` types (ModelRouter considered and REJECTED — see Architecture Patterns) |
| `pyyaml` | 6.0.3 | Strategy file parse/dump (same as `ProviderConfig` / `model_capabilities`) |
| `platformdirs` | 4.12.3 | Global strategy path (`user_config_dir("strands-code")` precedent) |
| `prompt-toolkit` | 3.0.53 | `radio_choice` guided setup picker (owned-keys control) |
| `rich` | 15.0.0 | `print_plain` transcript notes |
| `boto3` | 1.43.109 (optional `agentcore` extra) | Lazy-only Bedrock candidate discovery reuse; never imported at module top |
| Python | 3.14.8 (`python3 --version`); classifiers cover 3.10–3.13 | `X \| None` syntax OK (repo already uses it) |
| `uv` | 0.12.23 | Toolchain |

### Supporting (no install; runtime services / stdlib)

| Piece | Source | Role |
|-------|--------|------|
| stdlib `urllib` + `json` | Python stdlib | OpenRouter chat completions + `/models`; Ollama `/api/chat` + `/api/tags`. Precedent: `fetch_openrouter_models` uses `urllib.request.Request(... headers={"User-Agent": "strands-code"})` with `FETCH_TIMEOUT_SECONDS = 15` [VERIFIED: `live_pricing.py:32-33,366-379`] |
| Ollama daemon | `/usr/local/bin/ollama` installed, daemon NOT running [VERIFIED: `ollama list` → "could not connect to ollama app, is it running?"] | Local decision engine host (`http://127.0.0.1:11434` default) |
| OpenRouter API | Network reachable, `/models` HTTP 200, 458 models [VERIFIED: live curl] | Default decision engine transport + setup catalog |

### Alternatives (considered, not recommended)

| Alternative | Verdict |
|-------------|---------|
| `openrouter/auto` as the decision engine | REJECTED: it executes the turn on OpenRouter's pool and only reveals its pick in the response `model` field — it cannot route Bedrock-first turns, cannot pick thinking budgets, and takes no freeform directives. Its `allowed_models`/`cost_tier` plugin settings are request-scoped turn config, not a decision API [CITED: https://openrouter.ai/docs/features/model-routing]. |
| `strands.models.ModelRouter` with a custom `RoutingStrategy` | REJECTED: strategies are async (`strategy must implement RoutingStrategy: an async select(context) method` [VERIFIED: harness-adjacent `strands 1.58.1` source via `inspect.getsource` this session]), switching happens mid-invocation on failure (violates Phase 5 D-01 one-model-per-turn / idle-only), and it hides decisions from the transcript contract. Pre-turn `apply_model_action` reuse is strictly simpler. |
| Bedrock Intelligent Prompt Routing as the engine | REJECTED for now (this is the "until Bedrock offers decision models" future): it routes between two models inside one family via a Bedrock-managed small LM [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html], which cannot express cross-provider candidate sets, freeform directives, or thinking-level routing. Revisit when Bedrock ships a general decision API. |
| `ollama` / `openai` / `litellm` Python packages | REJECTED: none installed (`ModuleNotFoundError` on all three [VERIFIED this session]); raw HTTP covers both engines with zero new deps. |
| llama.cpp server (`llama-server`) | VIABLE fallback local engine: OpenAI-compatible `/v1/chat/completions`, reachable by the same `urllib` POST as OpenRouter with a different base URL [ASSUMED — standard llama.cpp server behavior, not probed here; binary presence not checked]. Recommend supporting it as a base-URL variant of the local engine, not a third engine. |
| Bedrock-hosted cheap models (Haiku, Nova micro/lite) as decision model | VIABLE alternative engine transport: same routing prompt via Bedrock Converse on e.g. `nova-micro` ($0.035/$0.14 per 1M [VERIFIED: `cost_context.py:37-38`, verbatim rows]). Recommend as a documented strategy option (engine: bedrock + decision model id), reusing `model_summarize`'s direct-`generate` precedent [VERIFIED: `cost_context.py:412-440`]. Costs AWS calls but needs no new key. |

## Package Legitimacy Audit

No new packages are recommended, so no `package-legitimacy` check is required. Audit statement: the decision engines are reached over stdlib `urllib` (OpenRouter HTTPS, Ollama/llama.cpp localhost HTTP) and the harness `resolve_model` seam — the Standard Stack above contains only packages already in `pyproject.toml` / the lockfile. IF the planner later adds an optional local-engine package (e.g. `ollama` PyPI client), that plan MUST run `node /home/csaba/.codex/gsd-core/bin/gsd-tools.cjs query package-legitimacy check --ecosystem pypi ollama` and gate on the verdict before merging.

## Architecture Patterns

### Decision flow (per ask, pre-turn)

```text
idle prompt → user text → dispatch → "agent"
    │
    ▼
routing enabled? (strategy configured AND session toggle on)
    │ no → current model, no note (routing stays off per D-01)
    │ yes
    ▼
build decision prompt: directives + candidate table
(price/window/benchmark/tier from almanac) + ask text (+ side flag)
    │
    ▼
engine chain (fail-soft, first success wins):
    1. OpenRouter chat completions on decision model → JSON pick
    2. local model (Ollama /api/chat) → JSON pick
    3. hold current model (deterministic fallback, D-08)
    │
    ▼
pick parses + names a strategy candidate?
    │ no → hold current (malformed pick behaves as engine failure)
    │ yes
    ▼
apply_model_action(agent, pick.model, effort=pick.level, ...)
(reuses restore/convert/fit/swap; no-op fast path when pick == current)
    │
    ▼
transcript note (print_plain, suppressible) → _invoke_agent → record spend
(decision-call tokens recorded as routing rows in session_turns for /cost)
```

### Project structure (recommended; planner owns final names)

```text
strands_code_cli/
  routing.py            # NEW: decision prompt builder, engine calls, pick parser, spend record
  routing_strategy.py   # NEW (or fold into routing.py): strategy file load/merge/validate
  loop.py               # EDIT: session toggle holder, pre-turn hook, /model warn path
  router.py             # EDIT: routing slash branches (reply actions) + USAGE_HINT
  cost_context.py       # EDIT: /cost routing section + decision-call spend
  model_switch.py       # EDIT: thread effort through apply_switch (effort kwarg → resolve_model)
  live_pricing.py       # REUSE: fetch_openrouter_models/_store_openrouter/cache for setup catalog
  main.py               # REUSE: build_agent kwargs stash carries routed effort to /btw rebuilds
tests/
  test_routing.py            # NEW: prompt build, pick parse, chain order, hold-current
  test_routing_strategy.py   # NEW: fail-soft load, repo-wins merge, validate
  test_loop_routing.py       # NEW (or extend test_loop_cancel.py): pre-turn hook, toggle, /model warn
```

### Patterns to follow

1. **Fail-soft layering** — "Nothing here ever raises to a caller: any failure ... yields None and the next layer is tried" [VERIFIED: `live_pricing.py:14-16`, verbatim]. The engine chain (API → local → hold) and strategy load both inherit this exactly, including the TTL + 10-minute in-process cooldown shape (`CACHE_TTL_SECONDS`, `_COOLDOWN_SECONDS`, `_note_failure` [VERIFIED: `live_pricing.py:29-36,82-83`]).
2. **Reply-only router actions** — new slashes return `("reply", message)` or `("model", selection)`; "the router never swaps inline" [VERIFIED: `router.py:132-133`, verbatim]. Dispatch contract: "`(action, message)` where action is `"agent"` ..., `"exit"` ..., `"reply"` ..., or `"model"`" [VERIFIED: `router.py:158-163`, verbatim].
3. **Loop owns session-sticky state** — toggle holder lives in `run_loop` next to `ModeState`/`MemoryModeState` (Phase 4/6 precedent); disk only via config file when explicitly decided.
4. **Constructor-kwarg configuration, never env sniffing** — engine choice and strategy paths are explicit config; only runtime credentials follow harness env precedent and are never persisted.
5. **Transcript-first UX** — "silent actions still log visibly"; every routed ask gets one `print_plain` line (markup off, style kwarg) [VERIFIED: `output.py:34-42`].
6. **Switch-first resolve** — "resolve raises before any history mutation, so a bad selection leaves the session (model AND messages) untouched" [VERIFIED: `loop.py:1095-1096`, verbatim]. The routed pick resolves (model + effort validation) before `convert_history` runs.
7. **Warn-and-skip config** — "malformed entries warn and skip — a typo here must never break startup or conversion" [VERIFIED: `model_capabilities.py:15-16`, verbatim]; symlink refusal precedent (`ValueError ... must not be a symlink` [VERIFIED: `provider_config.py:47-48`]).
8. **Pair-atomic history ops + verbatim IDs** — routed switches flow through `convert_history`/`canonical_prefix_hash`, never hand-rolled JSON; "never hand-roll vendor JSON" [VERIFIED: `model_switch.py:7-8`, verbatim].

### Anti-patterns (do not do these)

- **No heuristic model picking of any kind** — not length-based, not keyword-based, not "obvious trivial ask" shortcuts. "even a short ask can mean deep thinking work" (locked skepticism). A malformed/empty decision response holds current; it never triggers a fallback heuristic.
- **No mid-turn or mid-invocation switching** — ModelRouter-style failure switching violates idle-only; `/btw` routing resolves at spawn time from the same pre-turn decision, not inside the side run.
- **No `openrouter/auto` turn execution** — the CLI's turns stay on the resolved model via the harness; OpenRouter only serves the cheap decision call and the setup catalog.
- **No decision-call spend hidden** — decision tokens are metered rows in `/cost`, not silent overhead.
- **No keys in repo or strategy files** — OpenRouter key is runtime-supplied (prompt or harness-precedent env at call time); strategy YAML holds model ids, directives, descriptors only.
- **No blocking the turn on a slow decision call** — hard timeout (15s precedent `FETCH_TIMEOUT_SECONDS`; recommend tighter, ~10s, at planner discretion) then hold-current; never retry the decision call within one ask (one attempt per engine per ask; "retrying next ask" per D-08).

## Don't Hand-Roll

| Capability | Use instead | Why |
|------------|-------------|-----|
| Vendor thinking/request fields | `resolve_model(model, default, effort=...)` | One `effort` maps to Bedrock `additional_request_fields`, Anthropic `params`, OpenAI `reasoning.effort` etc. [VERIFIED: harness `models.py:161-182` `_bedrock_thinking`, `:193-240` provider builders] |
| Thinking support verdicts | `supports_thinking` (harness) via `supports_reasoning` | Fail-closed, override-aware [VERIFIED: `model_switch.py:140-161`] |
| History conversion on switch | `convert_history` + `apply_model_action` | Reasoning/media/tool-pair handling with live-probe precedent [VERIFIED: `model_switch.py:265-340`, `loop.py:1064-1148`] |
| OpenRouter catalog fetch/cache | `fetch_openrouter_models` + `_store_openrouter` + `_openrouter_cache` | TTL + cooldown + fail-soft already built [VERIFIED: `live_pricing.py:366-423`] |
| Price/window lookups | `price_for` / `window_for` / `price_provenance` | Most-precise-first layering with provenance [VERIFIED: `cost_context.py:110-138`] |
| Token estimates | `estimate_messages_tokens` | chars/4 offline estimate [VERIFIED: `cost_context.py:330-347`] |
| Guided setup picker | `radio_choice` (owned-keys control) | Stdin-guard + typeahead-drain choke point [VERIFIED: `choice.py:148-186`] |
| Transcript printing | `print_plain(console, text, style=...)` | Markup-off, MarkupError-proof [VERIFIED: `output.py:34-42`] |
| CLI arg parsing for slashes | `dispatch` head/arg split | Lowercased head, reply/model tri-state [VERIFIED: `router.py:164-169`] |

## Common Pitfalls

1. **Decision latency on every ask** — a 1–3s HTTPS call precedes each turn. Mitigate: cheap fast decision model, tight timeout, skip the call when the strategy has one candidate (nothing to choose; still log nothing — or a debug-level line at planner discretion), and never call during `/btw` queue drains more than once per spawn (D-04 discretion: per-ask call vs derived — researcher recommends ONE decision per side spawn, derived reuse while the side run is live).
2. **Decision-call cost creep** — small but nonzero per ask; at scale it dominates cheap turns. Mitigate: cap prompt size (candidate table compacted to one line per model; truncate ask to ~2000 chars), prefer `:free` or cheapest-tier decision models, and surface spend in `/cost` so users see it (D-12).
3. **Malformed picks** — local small models especially may emit non-JSON or name non-candidates. Mitigate: `response_format: {"type": "json_object"}` on OpenRouter [CITED: API reference Request Schema `response_format?: ResponseFormat`], `format` JSON schema on Ollama `/api/chat` [CITED: ollama api.md "Structured outputs ... providing a JSON schema in the `format` parameter"], strict parse (unknown model id → hold-current, never fuzzy-match to a candidate — fuzzy matching is heuristic picking by another name).
4. **Effort/model mismatch** — a routed `high` effort on a model with no thinking levels raises `ValueError` from `resolve_model` ("Effort ... is not supported by ..." [VERIFIED: harness `models.py:151-158` `_bedrock_effort`]). Mitigate: validate `(model, effort)` with `supports_thinking`-family checks BEFORE `apply_switch` (switch-first rule), and constrain the decision prompt to per-candidate advertised levels.
5. **Oscillation between models** — per-ask routing can flip A→B→A across turns, churning history conversion (thinking strip/text-ify each hop). Mitigate: the decision prompt includes the current model + a "prefer staying unless clearly better" directive default; `apply_model_action` no-op fast path when pick == current (planner: skip conversion entirely, still emit the transcript line).
6. **Stale catalog/benchmark data** — `/models` prices drift; benchmark snapshots age. Mitigate: reuse the 24h disk cache for setup enumeration; stamp benchmark snapshots with a `pulled:` date in the strategy file; decision prompt uses live `price_for`/`window_for` at call time (already TTL-cached), not the snapshot, for cost impact.
7. ** `/model` vs routing race** — user re-points manually while routing is on. Locked answer (D-10): warn + cancel offer + routing-off on confirm; the planner must ensure the warn dialog runs at idle only (mid-turn slashes already refuse via `MODEL_REFUSAL` [VERIFIED: `model_switch.py:27`, verbatim]).
8. **`reasoningContent` resume hazard (pre-existing)** — "resumed opus history fails validation on non-reasoning Bedrock models" (STATE.md blocker, survives since Phase 4). Routing across vendors amplifies exposure to this; routed switches MUST go through `convert_history` (which strips/text-ifies), never raw assignment.
9. **Leaking the ask to a third party** — the decision call ships ask text to OpenRouter even for Bedrock-only users. Mitigate: document it in setup (consent-by-config: routing is off until configured, D-01), truncate/redact, and offer the local-only engine chain (D-09). Never send tool results or file contents — ask text only.
10. **Over-fitting to Laya/Kev names** — they do not exist in the catalog today. Any hardcoded default decision model must be validated against the live catalog at setup; unknown ids warn-and-fall-back to catalog enumeration, never fail startup.

## Code Examples (verified patterns)

All examples below are verified against code read this session; adapt names to the planner's final module layout.

### 1. Decision call over stdlib urllib (OpenRouter engine)

Follows `fetch_openrouter_models` exactly [VERIFIED: `live_pricing.py:366-379`]:

```python
import json
import urllib.request

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

def decide_via_openrouter(api_key, decision_model, system, user, timeout=10):
    """One routing decision; returns the raw assistant text or None."""
    body = json.dumps({
        "model": decision_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "temperature": 0,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices", [])
        if not choices:
            return None
        return choices[0].get("message", {}).get("content")
    except Exception:
        return None  # fail soft: caller tries the next engine
```

Endpoint + auth shape [CITED: https://openrouter.ai/docs/api_reference/overview + auto-router Python example using `requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": "Bearer <OPENROUTER_API_KEY>"})`]. `response_format` is a documented Request field [CITED: same]. Usage for spend accounting rides `payload["usage"]` (`prompt_tokens`/`completion_tokens`) [CITED: auto-router Response example].

### 2. Decision call (Ollama local engine)

```python
import json
import os
import urllib.request

def decide_via_ollama(model, system, user, timeout=30):
    """One routing decision via a local daemon; None on any failure."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "effort": {"type": "string"},
                "why": {"type": "string"},
            },
            "required": ["model", "effort", "why"],
        },
        "stream": False,
        "keep_alive": "5m",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return (payload.get("message") or {}).get("content")
    except Exception:
        return None
```

`POST /api/chat` with `model`/`messages`/`format`/`stream`/`keep_alive` [CITED: https://github.com/ollama/ollama/blob/main/docs/api.md]. Host default `http://127.0.0.1:11434` matches the harness `_ollama` builder (`os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")` [VERIFIED: harness `models.py` `_ollama`]). Local enumeration for setup: `GET /api/tags` [CITED: same api.md]. Timeout is longer (cold model load); planner may pre-warm or accept first-ask latency with a transcript note.

### 3. Routing prompt skeleton (directives + candidate stats, D-07)

```text
SYSTEM:
You route coding asks to exactly one candidate model. Reply with JSON only:
{"model": "<candidate id>", "effort": "<level>", "why": "<=12 words>"}.
Rules:
- "model" MUST be one id from the candidate table verbatim.
- "effort" MUST be one of the candidate's advertised levels.
- Prefer STAYING on the current model unless another is clearly better.
User directives:
<trivial asks go cheap, deep refactors go big...>
Candidate table (id | $in/$out per 1M | window | benchmark | tier | levels):
...
Current model: <id>. Side ask: <true|false>.
USER:
<ask text, truncated>
```

Strict-parse rule: `pick["model"]` must equal a candidate id exactly (no normalization, no fuzzy match); `pick["effort"]` must be in that candidate's levels; `why` truncated to one line. Anything else → hold-current.

### 4. Threading effort through the switch (planner implements)

Today: `apply_switch` calls `resolve_model(new_string, default or new_string)` with implicit `effort="auto"` [VERIFIED: `model_switch.py:626-646`]. Routed switches need:

```python
model = resolve_model(routed_id, routed_id, effort=routed_effort)
agent.model = model
```

with `routed_effort` validated against the provider levels first (`EFFORT_LEVELS` + `_bedrock_levels`-family behavior [VERIFIED: harness `models.py:307, 151-158`]). Note `resolve_model` raises `ValueError` for unknown providers ("Unknown model provider ... Supported providers: ..." [VERIFIED: harness `models.py:441-446`]) — the switch-first rule means this raise must happen before history mutation, which `apply_model_action` already guarantees by resolving first [VERIFIED: `loop.py:1094-1097`].

### 5. Setup catalog enumeration (reuse, do not re-fetch raw)

```python
from strands_code_cli import live_pricing

models = live_pricing.fetch_openrouter_models()  # public, no key; None on failure
```

Entry fields available per model: `id`, `name`, `description`, `context_length`, `pricing.prompt`/`pricing.completion` (per-token strings → ×1M), `architecture.input_modalities`/`output_modalities`, `supported_parameters[]`, `top_provider.max_completion_tokens` [VERIFIED: live `/models` response + keys list this session]. Filter setup choices to chat-capable entries (TEXT in/out analogue: `output_modalities` contains `text`, id not matching rerank/embed) mirroring `_is_chat_model` [VERIFIED: `model_switch.py:354-370`].

### 6. Transcript line + /cost (visibility, D-12)

```python
from strands_code_cli.output import print_plain
print_plain(console, f"Routed → {model} ({effort}): {why} · ~${delta}/ask vs {prev}")
```

`print_plain(console, text, style=...)` — markup off, dynamic-safe [VERIFIED: `output.py:34-42`]. Decision-call spend: append rows to `session_turns` with the decision model id so `cost_report` prices them at their own rates ("Each row prices at its own turn model" [VERIFIED: `cost_context.py:178-179`, verbatim]); the routing section details pick history.

## State of the Art

- **OpenRouter Auto Router (`openrouter/auto`, `openrouter/auto-beta`)**: market-spend-share ranking over ~30 task types, 7-day trailing window, `cost_tier` bands (low/medium/high/xhigh/max), `allowed_models`/`excluded_models` wildcard plugin settings, per-response `model` field, session stickiness via `session_id`, graceful degradation "to a default model set" when classification is unavailable [CITED: https://openrouter.ai/docs/features/model-routing]. Relevant as prior art for the *concept*, not as this phase's engine (see rejection rationale in Standard Stack).
- **OpenRouter rankings**: task-spend views at `openrouter.ai/rankings#task-spend` feed the Auto Router [CITED: same]. Candidate for the "compound benchmark" pull at setup time (market-share signal, not a quality benchmark — label it as such).
- **Bedrock Intelligent Prompt Routing**: Bedrock-managed small-LM routing between two models in one family, up to ~30% cost reduction claimed [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html and https://aws.amazon.com/blogs/machine-learning/build-generative-ai-solutions-with-amazon-bedrock/]. The "until Bedrock offers decision models" condition in D-06 refers to something more general than this; today's prompt routers cannot express this phase's strategy.
- **Strands `ModelRouter` (strands-agents 1.58.1)**: candidate-set router with async `RoutingStrategy.select`, `FallbackStrategy` default (fewest-failures-first), `max_switches` cap, `Agent(model=router)` attachment [VERIFIED: `inspect.getsource(ModelRouter)` this session]. Right tool for failure-failover, wrong tool for deliberate pre-turn routing — rejected with rationale above.
- **Benchmark sources for candidate ranking (plan-time pulls, staleness-stamped)**: SWE-bench Verified / SWE-bench Pro leaderboards [CITED: https://benchlm.ai/benchmarks/swe-bench-pro, https://www.swebench.com], LMArena coding board (blind human votes, coding Elo) [CITED: https://lmarena.ai], Artificial Analysis Intelligence Index [CITED: https://artificialanalysis.ai], OpenRouter rankings [CITED: https://openrouter.ai/rankings]. Researcher recommendation: compound rank = small table in the strategy file (`swe_verified`, `lmarena_coding`, `aa_index` + `pulled:` date), user-editable like capability overrides; the decision prompt carries one compact rank column, not raw scores.
- **Cheap decision-model class in the live catalog**: 37 `qwen3*` entries, 11 `llama*` entries, 5 `haiku` entries (incl. `anthropic/claude-haiku-4.5`) [VERIFIED: live catalog grep]. Setup should default-sort by price ascending and let the user pick; Laya/Kev are not available names today.
- **Harness thinking-level single knob**: `EFFORT_LEVELS = ("auto", "off", "minimal", "low", "medium", "high", "xhigh", "max")` with per-provider validation and `recommended_thinking` defaults (`"high"` for bedrock/anthropic/openai/google, `None` for ollama/litellm) [VERIFIED: harness `models.py:81-87, 296-307`]. Claude 4.6+ uses adaptive thinking (`output_config.effort`), older uses extended `budget_tokens` (`_EXTENDED_THINKING_BUDGETS`: low 2048 → max 49152) [VERIFIED: harness `models.py:96-128`].

## Assumptions Log

| # | Claim | Status |
|---|-------|--------|
| A-01 | llama.cpp `llama-server` exposes OpenAI-compatible `POST /v1/chat/completions` usable by the same urllib POST as OpenRouter with a different base URL | [ASSUMED] — not probed; binary presence unchecked. Planner: verify or drop the variant. |
| A-02 | OpenRouter `response_format: {"type": "json_object"}` is honored by cheap open-weights decision models | [ASSUMED] — field is documented, per-model support varies (`supported_parameters` lists `response_format`/`structured_outputs` per model [VERIFIED in live entry]). Planner: filter decision-model choices by `supported_parameters` containing `response_format` or `structured_outputs`. |
| A-03 | A ~10s decision timeout keeps turn-start latency acceptable; users tolerate one extra ante-turn pause | [ASSUMED] — UX judgment. Planner: make timeout a strategy constant; note in transcript when the decision call is slow. |
| A-04 | `session_turns` row shape (`turn`, `input_tokens`, `output_tokens`, `model`) accepts routing rows without report changes | [ASSUMED] — shape inferred from `cost_report` row reads [VERIFIED: `cost_context.py:192-208`]; planner confirms no other consumer breaks. |
| A-05 | Bedrock-hosted cheap models (Nova micro/lite, Haiku) can serve the decision call via the session model's direct-`generate` path when the engine is `bedrock` | [ASSUMED] — `model_summarize` proves direct `generate(prompt)` works on the session model [VERIFIED: `cost_context.py:412-440`]; planner verifies a *separate* cheap-model handle resolves without disturbing the session model. |
| A-06 | One decision per `/btw` spawn (derived reuse while live) satisfies D-04's "same strategy" without per-token re-routing | [ASSUMED] — discretion-area recommendation (side-ask mechanics), not a locked reading. |
| A-07 | Benchmark snapshots (SWE/LMArena/AA) are pullable at setup time in a parseable form | [ASSUMED] — sources verified to exist with leaderboards; exact fetch format (HTML vs API) left to planner spike. If unparseable, fall back to user-entered descriptors only (D-02 "potentially"). |

## Open Questions

1. **OpenRouter key supply UX**: prompt-at-setup (stored where? never the repo — keychain? `~/.config` with 0700 like `ProviderConfig.save` [VERIFIED: `provider_config.py:100-104`]?) vs runtime env (harness precedent reads `OLLAMA_API_KEY`/`LITELLM_API_KEY` env [VERIFIED: harness `models.py` `_ollama`/`_litellm`]). Planner owns this; researcher leans runtime env + setup-time validation call.
2. **Routed-effort persistence**: does the routed thinking level persist across turns (sticky per model) or re-decide every ask? D-05 says the router picks it automatically per ask; planner decides whether `current_model` tracking gains an `effort` companion and whether `/model` manual switches reset it.
3. **`/btw` side-agent effort plumbing**: `build_btw_agent(parent_kwargs, ...)` replays stashed kwargs — routed effort must ride `parent_kwargs["effort"]` [VERIFIED stash: `main.py:130-171`, replay: `loop.py:612-619`]. Planner confirms `create_harness` accepts `effort` through that path (it is a top-level factory param [VERIFIED: signature list this session]).
4. **Benchmark pull mechanics**: live-scrape at setup vs curated snapshot shipped in docs vs user-entered only. Depends on A-07 spike outcome.
5. **Decision-model default when the user skips setup choice**: cheapest `structured_outputs`-capable catalog entry, or force explicit choice? Pick the latter if A-02 shows spotty support.
6. **Transcript suppression granularity**: global boolean vs per-level (routed-switch vs hold-current notes). D-12 says "suppressible via config"; hold/pause notes are the planner's discretion item.

## Environment Availability

Probed this session (2026-10-11):

| Dependency | Status | Evidence |
|------------|--------|----------|
| `python3` | ✅ 3.14.8 | `python3 --version` |
| `uv` | ✅ 0.12.23 | `uv --version` |
| `node` (commit tooling) | ✅ v22.17.1 | `which node` |
| `ollama` binary | ✅ installed, daemon DOWN | `/usr/local/bin/ollama`; `ollama list` → "could not connect to ollama app, is it running?" |
| Network → `openrouter.ai` | ✅ HTTP 200 | `curl /api/v1/models` → 458 models, full entry shape captured |
| Network → `pypi.org` | ✅ HTTP 200 | `curl /simple/` |
| `ollama` PyPI pkg | ❌ missing (OK — not needed) | `ModuleNotFoundError` via `uv run python` |
| `openai` PyPI pkg | ❌ missing (OK — not needed) | `ModuleNotFoundError` |
| `litellm` PyPI pkg | ❌ missing (OK — not needed) | `ModuleNotFoundError` |
| AWS creds / Bedrock | NOT PROBED | Planner's integration tests must gate on live creds like existing `integration` marker tests |

**Missing for full live verification:** running Ollama daemon with at least one small model pulled (`ollama serve` + `ollama pull llama3.2` or a qwen3 small); an `OPENROUTER_API_KEY` for decision-call integration tests; AWS credentials for Bedrock candidate tests. None block unit-testable planning: engines are seam-injectable (`urllib` response fakes) and the chain is fully testable offline with `STRANDS_CODE_NO_LIVE_PRICING=1` precedent [VERIFIED: `live_pricing.py:57-59`, `tests/conftest.py` referenced].

## Validation Architecture

Nyquist enabled. Test framework: `pytest>=8` (locked 9.1.1 per AGENTS.md stack section; `addopts = "-m 'not integration'"` deselects live tests by default [VERIFIED: `pyproject.toml:63-67`]).

| Framework | Command | Scope |
|-----------|---------|-------|
| Unit (offline, default) | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py -q` | Prompt build, strict parse, chain order, fail-soft load, merge precedence |
| Loop integration (offline) | `uv run pytest tests/test_loop_routing.py -q` | Pre-turn hook, toggle stickiness, `/model` warn path, transcript lines |
| Regression | `uv run pytest tests/ -q` | Full suite; routing must not change unconfigured behavior (D-01: off without strategy) |
| Live (gated) | `uv run pytest -m integration -q` | Decision call against OpenRouter/Ollama with real keys; daemon-gated skips when down |

### Req→Test map (MODEL-03)

| Requirement facet | Test |
|-------------------|------|
| Per-ask decision selects model + thinking budget from candidates | Decision prompt contains directives + full candidate table; parsed pick applied via `apply_model_action` with routed effort; mocked engines return canned JSON |
| OpenRouter default engine / local alternative | Engine chain order test: API success short-circuits; API failure → local attempted; both fail → hold-current; offline (`URLError`) → local-or-hold per D-09 |
| Deterministic fallback + manual `/model` override | Hold-current is byte-identical model + messages; `/model` warns, cancel keeps routing, confirm disables routing (toggle off) |
| Visibility (which/why/cost) | Transcript-line test (one line, model+why+delta, suppression flag); `/cost` routing section + decision-spend rows test |
| No heuristic ever picks | Negative tests: malformed JSON → hold; unknown model id → hold (no fuzzy match); empty candidates → routing off; timeout → hold |
| Side asks route through same strategy | `/btw` spawn passes side-flagged decision; derived reuse while live (A-06) |

### Sampling Rate

Every engine boundary gets both a success and a failure test (2× coverage at API/local/parse/validate seams); every fallback transition gets an explicit hold-current assertion. Strategy file tests cover: missing file → routing off; corrupt YAML → warn + off; unknown keys → warn + skip entry (never widen); repo-wins merge with global; `validate` command output for each failure class.

### Wave 0 Gaps

- No live OpenRouter key in CI → decision-call integration tests must skip cleanly without a key (env-gated), same as AWS-credential gating precedent.
- No Ollama daemon in CI → local-engine tests use a stub HTTP server (stdlib `http.server` in-test) or URL-mocked `urlopen`; document the manual `ollama serve` verification step.
- Benchmark-pull format unknown (A-07) → Wave 0 ships descriptors as user-editable snapshot schema with `pulled:` date; live pull is a stretch goal, not a gate.

## Security Domain

Enforcement ON. ASVS L1. Block on high.

| ASVS L1 category | Applicability | Control |
|------------------|---------------|---------|
| V2 Authentication (credential storage) | HIGH — OpenRouter API key | Never persist to repo or strategy YAML; runtime env or 0700-dir secret file; scrub from transcripts via `scrub_credentials` precedent [VERIFIED: `cost_context.py:383-396`]. Recommend extending `_CRED_PATTERNS` with OpenRouter key shapes if observable. |
| V3 Session / V4 Access Control | LOW — local CLI, single actor | Strategy files: symlink refusal precedent; repo strategy file is read (untrusted content) but never executed — directives are prompt text, never code. |
| V5 Validation | HIGH — decision JSON, strategy YAML, catalog payloads | `yaml.safe_load` only; strict JSON schema parse (exact id match, level allowlist); catalog entries type-checked field-by-field like `_store_openrouter` [VERIFIED: `live_pricing.py:382-405`]. |
| V7 Logging | MEDIUM — ask text + keys in logs | Decision prompts contain user ask text: never log full prompts at info; transcript shows only model/why/cost. API keys never in cache files or error strings. |
| V9 Communications | HIGH — HTTPS + localhost HTTP | OpenRouter over HTTPS with timeout; Ollama over localhost HTTP (document: no secret sent; `OLLAMA_API_KEY` Bearer only for proxied hosts per harness precedent). Fail-soft on TLS/network errors. |
| V10 Malicious code / prompt injection | MEDIUM — directives + catalog descriptions enter the decision prompt | Treat strategy directives and `/models` descriptions as untrusted prompt content: delimit with clear framing, truncate lengths, and constrain output to the strict JSON schema so injected text cannot widen the pick beyond exact candidate ids. |
| V14 Configuration | MEDIUM — new config surface | Fail-soft load, warn-and-skip entries, `validate` slash command; repo file wins over global (D-03) — document that cloning a repo can change routing behavior (consent-by-config, same as policy files). |

### Known threat patterns for this stack

- **Decision-prompt injection via candidate metadata**: `/models` descriptions are third-party text; a malicious description could steer the pick. Control: exact-id output constraint + truncate descriptions (or exclude them — ids + stats suffice).
- **Strategy file as an attack surface**: a malicious repo's strategy could list an attacker model id. Control: routed ids still resolve through `resolve_model` (unknown providers raise before mutation); document repo-wins implications in setup; `validate` command flags unknown ids against the catalog.
- **Key exfiltration via error paths**: `urllib` errors echo URLs — never put the key in the URL (header only, per Example 1).
- **SSRF-ish base URLs**: custom local-engine base URL is user config, not remote input — acceptable; still validate scheme (`http`/`https` only).

## Sources

### Primary (tool-confirmed this session)

- In-repo: `strands_code_cli/live_pricing.py` (full read), `model_switch.py` (full read), `model_capabilities.py` (full read), `provider_config.py` (full read), `cost_context.py` (partial, :1-500), `router.py` (`:1-180`), `loop.py` (run_loop `:1486-1722`, `apply_model_action` `:1064-1148`, `_btw_context_for` `:603-626`, turn block `:1723-1790`), `main.py` (full read), `output.py` (full read), `choice.py` (`radio_choice`), `btw.py` (outline), `pyproject.toml` (full read), `AGENTS.md` (full read), `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `08-CONTEXT.md`.
- Installed harness `strands_harness/models.py` 0.1.2 via `uv run python` + `sed`/`grep`: `_PROVIDERS` registry (`:296-306`), `EFFORT_LEVELS` (`:307`), `_bedrock_effort` (`:151-158`), `_bedrock_thinking` (`:161-176`), provider builders (`:178-262`), `supports_thinking` (`:374-383`), `resolve_model` (`:413-474`), `_ollama` host default, `create_harness` signature (`model`, `effort`, ... top-level).
- Installed `strands-agents` 1.58.1 `ModelRouter` via `inspect.getsource`/`signature`.
- Live `GET https://openrouter.ai/api/v1/models`: 458 models, entry shape + keys, candidate greps (`qwen3` 37, `llama` 11, `haiku` 5, `laya`/`kev`/`jevi` 0).
- Environment probes: `python3 3.14.8`, `uv 0.12.23`, `ollama` binary present/daemon down, `node v22.17.1`, `uv pip list` versions, `ModuleNotFoundError` for `ollama`/`openai`/`litellm` packages.

### Secondary (official docs, fetched)

- [OpenRouter Auto Router](https://openrouter.ai/docs/features/model-routing) — slugs, plugins (`auto-router` id, `allowed_models`, `excluded_models`, `cost_tier`), response `model` field, session stickiness, graceful degradation.
- [OpenRouter API Reference](https://openrouter.ai/docs/api-reference/overview) — chat-completions schema, `response_format`, OpenAI compatibility.
- [Ollama API (`api.md`)](https://github.com/ollama/ollama/blob/main/docs/api.md) — `POST /api/chat` params (`model`, `messages`, `format` JSON schema, `stream`, `keep_alive`, `think` levels), `GET /api/tags`.

### Tertiary (web search, cited claims only)

- [Bedrock prompt routing user guide](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html) + [AWS ML blog](https://aws.amazon.com/blogs/machine-learning/build-generative-ai-solutions-with-amazon-bedrock/) — same-family two-model intelligent routing.
- [TechCrunch/Bedrock prompt routing + caching](https://techcrunch.com/2024/12/04/aws-brings-prompt-routing-and-caching-to-its-bedrock-llm-service) — small-LM prediction background.
- Benchmark boards: [SWE-bench Pro leaderboard](https://benchlm.ai/benchmarks/swe-bench-pro), [LMArena](https://lmarena.ai), [Artificial Analysis](https://artificialanalysis.ai), [OpenRouter rankings](https://openrouter.ai/rankings).

## Metadata

| Field | Value |
|-------|-------|
| Confidence breakdown | Architecture HIGH (all seams verified in-repo + harness); Standard Stack HIGH (zero new deps, versions pinned by probe); Pitfalls HIGH (drawn from locked decisions + live-probe precedent); Benchmarks MEDIUM (sources exist, pull format unverified — A-07); Local-engine timeouts MEDIUM (daemon down, cold-load behavior unprobed) |
| Overall | HIGH |
| Date | 2026-10-11 |
| Valid until | 2026-11-11 (re-verify: OpenRouter catalog names, `strands-harness` effort levels, Ollama API if daemon behavior matters) |
| Skills checked | `.agents/skills/`, `.codex/skills/` — both absent [VERIFIED: `ls` this session]; AGENTS.md confirms "No project skills found" |
