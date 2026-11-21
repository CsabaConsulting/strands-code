# Phase 9: Native TypeSafe Decision Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 9-native-typesafe-decision-engine
**Areas discussed:** Chain position, Key and setup, Calibration

---

## Chain position

**Q: Where does the native TypeSafe engine sit in the decision chain?**

| Option | Description | Selected |
|--------|-------------|----------|
| First when keyed (Recommended) | Native first when TYPESAFE_API_KEY is present, else the current order. Direct API, no proxy hop. | |
| Last resort | OpenRouter → Ollama → native → pause. Native only fills gaps. | |
| User-ordered | Strategy lists engine order explicitly; user controls the sequence per workspace. | ✓ |

**User's choice:** User-ordered
**Notes:** User should choose; multiple API keys may be available; user picks primary plus fallbacks and order.

**Q: How should the user express the engine order?**

| Option | Description | Selected |
|--------|-------------|----------|
| Primary+fallbacks (Recommended) | Setup asks for primary engine, then optional ordered fallbacks. | ✓ |
| Ordered list | Strategy holds engines list in try order; setup edits the sequence. | |
| You decide | Leave the exact expression to the planner. | |

**User's choice:** Primary+fallbacks
**Notes:** End result is effectively an ordered engines list; setup offers an intelligent default based on API key and Ollama availability.

**Q: When setup proposes the default order, what should it prefer?**

| Option | Description | Selected |
|--------|-------------|----------|
| Native first (Recommended) | When TYPESAFE_API_KEY exists, native leads; otherwise current OpenRouter-Ollama order. | ✓ |
| Current order | Keep OpenRouter-Ollama base; slot native in only by availability. | |
| Measured best | Researcher probes latency/cost; setup proposes cheapest-fastest first. | |

**User's choice:** Native first

**Q: A listed engine has no key (or local is down). What should the chain do?**

| Option | Description | Selected |
|--------|-------------|----------|
| Skip silently (Recommended) | Skip to the next listed engine. | |
| Skip with note | Skip, but print a one-line note naming the skipped engine and why. | ✓ |
| Hold and tell | Hold routing and tell the user to add the key or reorder. | |

**User's choice:** Skip with note
**Notes:** User can opt to suppress notes if they get too noisy.

---

## Key and setup

**Q: Native has no models catalog. How should setup offer the Jev model pick?**

| Option | Description | Selected |
|--------|-------------|----------|
| Pinned list (Recommended) | Setup offers verified Jev strings (jev-1.13, jev-latest); no catalog fetch. | ✓ |
| Freeform + validate | User types the model string; validate checks it live. | |
| Catalog if exposed | Researcher checks for a native catalog endpoint first; falls back to pinned list. | |

**User's choice:** Pinned list

**Q: No TYPESAFE_API_KEY in env at setup time. Show the native engine?**

| Option | Description | Selected |
|--------|-------------|----------|
| Hide until keyed (Recommended) | Setup lists native only when TYPESAFE_API_KEY is present. | ✓ |
| Show with hint | Always list native; hint at exporting the key when absent. | |
| You decide | Leave the exact behavior to the planner. | |

**User's choice:** Hide until keyed

**Q: What should /route validate check for the native engine?**

| Option | Description | Selected |
|--------|-------------|----------|
| Live ping (Recommended) | Validate makes a cheap live native call. | ✓ |
| Key + shape | Key presence plus strategy shape only; works offline. | |
| You decide | Leave the exact checks to the planner. | |

**User's choice:** Live ping

**Q: Native failure handling (bad key, offline): same chain rules as other engines?**

| Option | Description | Selected |
|--------|-------------|----------|
| Same rules (Recommended) | Skip/hold/pause with distinct note, like other engines. | ✓ |
| Native-specific | Its own failure handling, distinct from OpenRouter/Ollama. | |
| You decide | Leave failure semantics to the planner. | |

**User's choice:** Same rules

---

## Calibration

**Q: Native thresholds: reuse the shared 0.62/0.04 knobs or calibrate separately?**

| Option | Description | Selected |
|--------|-------------|----------|
| Shared unless proven (Recommended) | Same model, probes confirm, split only on evidence. | ✓ |
| Calibrate separately | Probe native and ship native-specific defaults regardless. | |
| You decide | Leave the knob strategy to the planner. | |

**User's choice:** Shared unless proven

**Q: Probe runner: cover native with the same probe set?**

| Option | Description | Selected |
|--------|-------------|----------|
| Full 20 (Recommended) | Add --run native over the same 20 probes; compare against shared baseline. | ✓ |
| Subset | Probe a small native-only subset for smoke coverage. | |
| You decide | Leave probe coverage to the planner. | |

**User's choice:** Full 20

**Q: Calibration baseline: shared with other engines or native-specific?**

| Option | Description | Selected |
|--------|-------------|----------|
| Shared baseline (Recommended) | One baseline for all engines. | ✓ |
| Separate file | Record a separate native baseline file alongside. | |
| You decide | Leave baseline shape to the planner. | |

**User's choice:** Shared baseline

**Q: Native and OpenRouter Jev disagree on a probe. How to treat it?**

| Option | Description | Selected |
|--------|-------------|----------|
| Investigate (Recommended) | Treat divergence as a bug to investigate, not a preference. | ✓ |
| Trust native | Native is the source of truth on conflict. | |
| Trust OpenRouter | OpenRouter is the battle-tested path on conflict. | |

**User's choice:** Investigate

---

## the agent's Discretion

- Spend reporting when native usage lacks cost (unknown vs estimate)
- Ordered-list strategy schema details and note-suppression knob shape
- Bare vs prefixed model strings and exact endpoint/auth (researcher verifies live)

## Deferred Ideas

None — discussion stayed within phase scope
