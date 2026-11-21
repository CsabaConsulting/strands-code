# Phase 9: Native TypeSafe Decision Engine - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Routing gains a third decision engine — Jev via TypeSafe's native API — alongside the OpenRouter and Ollama engines. The Phase 8 chain, strategy shape, verdict shape, and calibration baseline are reused; this phase adds the native transport, setup/validate coverage, user-ordered engine priority, and native probe calibration. No new routing capabilities beyond the engine itself.

</domain>

<decisions>
## Implementation Decisions

### Chain position
- **D-01:** Engine priority is user-ordered: the user picks a primary engine plus ordered fallbacks (multiple keys may exist). Stored as an ordered engines list in the strategy. — **Reversibility:** costly — the ordered list is consumed by setup, validate, the chain runner, and probes; reordering semantics touch all four.
- **D-02:** Setup proposes an intelligent default order from availability (keys present, Ollama reachable): native first when `TYPESAFE_API_KEY` exists, else the current OpenRouter → Ollama order.
- **D-03:** A listed engine with no key (or unreachable local) is skipped with a one-line note; the user can suppress these notes via config if noisy (planner scopes the knob).

### Key and setup
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 8 routing (reused chain and contracts)
- `.planning/phases/08-model-routing-with-decision-models/08-CONTEXT.md` — Locked routing decisions D-01..D-16 (chain, strategy, verdict shape, knobs)
- `.planning/phases/08-model-routing-with-decision-models/08-RESEARCH.md` — Decision-API contracts, live probes, top-1-prob gate
- `strands_code_cli/routing.py` — Engine chain, transports, verdict, knobs (native transport lands here)
- `strands_code_cli/router.py` — `/route setup` / `validate` slash surface
- `strands_code_cli/cost_context.py` — Reported-spend pattern for decision calls
- `scripts/route-probe.py` — Probe runner (`--run` / `--compare`); gains `--run native`
- `evals/routing-probe/baseline.json` — Shared calibration baseline
- `docs/ROUTING.md` — User-facing routing docs

### Roadmap and requirements
- `.planning/ROADMAP.md` — Phase 9 goal, success criteria, ordering
- `.planning/REQUIREMENTS.md` — MODEL-04 requirement text

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- OpenRouter Decision-API transport (`decide_via_openrouter` in `strands_code_cli/routing.py`): request/response handling the native transport mirrors, minus provider metadata
- Engine chain runner with preflight, retry classes, and pause-and-hold: native plugs in as a third link
- `/route setup` enumeration + `/route validate` checks: extend with native branch
- Probe runner + 20-probe set + compare mode: extend with `--run native`

### Established Patterns
- Transports use stdlib urllib only, key read from env at call time (OpenRouter precedent)
- `EngineResult` triple (answers, usage tokens, reported cost-or-None) feeds the shared verdict
- Same-model-different-transport is new: OpenRouter-vs-native Jev parity is a probe question, not an assumption

### Integration Points
- Strategy schema: ordered engines list + native model string + key presence
- Setup flow: availability detection (`TYPESAFE_API_KEY`, Ollama) drives the proposed default order
- `/cost` routing lines: native spend reported when the API returns it

</code_context>

<specifics>
## Specific Ideas

- The user pasted three Gemini briefs on native-vs-OpenRouter Jev (endpoint shapes, SDK routing, model strings, $42/B-input pricing claim). Treat these as investigation leads: researcher verifies every claim web-first via Tavily plus live probes before the planner relies on any of it.
- `TYPESAFE_API_KEY` lives in the user's `.bashrc` (shell env). Live probes read it from the environment at call time; it must never land in the repo, logs, or saved files.
- User framing: native Jev is "the original model which sparked this whole field" — direct-from-source is preferred when available (D-02), but availability, not sentiment, drives the default.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 9-Native TypeSafe Decision Engine*
*Context gathered: 2026-10-12*
