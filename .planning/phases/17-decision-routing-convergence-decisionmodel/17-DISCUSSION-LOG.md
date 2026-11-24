# Phase 17: Decision Routing Convergence (`DecisionModel`) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `17-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-24
**Phase:** `17-decision-routing-convergence-decisionmodel`
**Areas discussed:** Hybrid vs unified `DecisionModel` transports (`D-01`), `LLMDecisionModel` opt-in & gating semantics (`D-03`), `DecisionsAPIDecisionModel` inclusion (`D-02`), Offline & opportunistic live verification scope (`D-07`)

*(Pre-decided anchors from Roadmap, Requirement `UPSTREAM-02`, and `v2.0` project constraints not re-asked: keep `apply_model_action` + `convert_history()` + `RichHistory` stashes rather than `ModelRouter`, preserve `0.62` confidence threshold + `0.04` tie-margin gate over raw probabilities with `uncertainty=False` on System One engines, preserve two-call model + effort routing and hold-on-failure `D-08`, keep `/cost` actuals intact, stay within `xenon C <= 20` and `lint-imports` boundaries, and keep `strands_code_agent/` pristine under `D-24`.)*

---

## Round 1: Transport Architecture, Upstream Engine Additions & Verification Scope

### Q1: Wire-shape strategy across `TypeSafeDecisionModel`, OpenRouter & Ollama (`D-01`)

In `strands-agents 1.66.0`, `strands.decisions` ships `TypeSafeDecisionModel`, `DecisionsAPIDecisionModel`, and `LLMDecisionModel` (no OpenRouter/Ollama classes), and `TypeSafeDecisionModel` sends `state` as a string with `criteria={choice: null}` (putting prose in `instructions`). How should Phase 17 converge the transports?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Hybrid: upstream `TypeSafeDecisionModel` + CLI `OpenRouterDecisionModel` & `OllamaDecisionModel` | Upstream `TypeSafeDecisionModel` uses folded `Question["question"]` + string `state`; CLI `DecisionModel` subclasses preserve `criteria` dicts, 64 KiB body fit & OpenRouter inline `usage.cost`. | ✓ |
| Unified folded-instructions wire shape across all engines | Every `DecisionModel` sends `state: str` + `criteria: {c: null}` + prose inside `Question["question"]`. | |
| Keep custom HTTP transport for TypeSafe too | Custom HTTP instead of upstream `TypeSafeDecisionModel` to keep raw wire `{state, criteria}` identical. | |

**User's choice:** Hybrid approach — upstream `TypeSafeDecisionModel` (`state: str` + criteria folded into `Question["question"]`) plus CLI-owned `OpenRouterDecisionModel` and `OllamaDecisionModel` subclassing `DecisionModel`.

---

### Q2: `LLMDecisionModel` integration & probability gating (`D-03`)

Upstream `LLMDecisionModel` returns `metadata.probabilities=None` and `confidence=None` (so numeric `0.62`/`0.04` gating cannot run; it relies on `Uncertain` instead). How should `LLMDecisionModel` be integrated?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Opt-in `llm` engine in `routing.yaml` (config-only) | `engine.llm_model` via `resolve_harness_model()`, uses `uncertainty=True` to hold on `Uncertain`, skips `0.62`/`0.04` prob gate, records `model_confidence=None` & estimated `cost_for()` spend in `/cost`. | ✓ |
| Opt-in `llm` engine in `routing.yaml` AND interactive `/route setup` picker | Expose in `/route setup` too (with helper refactor for `xenon`). | |
| Defer `LLMDecisionModel` wiring | Focus strictly on `TypeSafeDecisionModel`, `OpenRouterDecisionModel`, and `OllamaDecisionModel`. | |

**User's choice:** Opt-in `"llm"` engine in `routing.yaml` (config-only, keeping `/route setup` focused), `uncertainty=True` holding on `Uncertain`, skipping numeric `0.62`/`0.04` gating, `model_confidence=None`, and `cost_for()` spend tracking in `/cost`.

---

### Q3: `DecisionsAPIDecisionModel` (`decisionapi.net` / `JEV_API_KEY`) scope (`D-02`)

`strands-agents 1.66.0` also includes `DecisionsAPIDecisionModel` (`decisionapi.net`, `JEV_API_KEY`). Should it be included in Phase 17 or kept out of scope?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Keep `DecisionsAPIDecisionModel` out of Phase 17 scope | Focus cleanly on `native`/TypeSafe, `openrouter`, `local`/Ollama, and optional `llm`. | |
| Also wire `DecisionsAPIDecisionModel` (`decisionapi.net` / `JEV_API_KEY`) as an opt-in engine in `routing.yaml` | Register opt-in `"decisions_api"` engine in `routing.yaml` using upstream `DecisionsAPIDecisionModel`. | ✓ |

**User's choice:** Also wire `DecisionsAPIDecisionModel` (`decisionapi.net` / `JEV_API_KEY`) as an opt-in engine (`"decisions_api"`) in `routing.yaml`.

---

### Q4: Verification & live probe scope (`D-07`)

What live verification scope do you want for Phase 17?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Full offline hermetic tests across all `DecisionModel` transports + opportunistic live probes | Hermetic tests (mocked `httpx`/transports, async-to-sync bridge from main & `/btw` threads, stub server) + opportunistic live probes for whichever keys exist in `.env`. | ✓ |
| Offline hermetic tests + stub HTTP server only | No live network calls in Phase 17. | |
| Require full live-tmux `driver.py r3` and `n4` runs against OpenRouter and TypeSafe APIs | Require live `OPENROUTER_API_KEY` and `TYPESAFE_API_KEY` tmux scenarios. | |

**User's choice:** Full offline hermetic tests across all 5 `DecisionModel` transports + opportunistic live probes for whichever keys exist in `.env`.
