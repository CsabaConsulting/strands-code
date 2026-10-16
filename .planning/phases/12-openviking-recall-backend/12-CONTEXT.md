# Phase 12: OpenViking Recall Backend - Context

**Gathered:** 2026-10-16
**Status:** Ready for planning

<domain>
## Phase Boundary

An opt-in OpenViking backend (`viking://` virtual filesystem, embedded in-process) behind the same memory seam as Strands native memory. Native serves first with OpenViking as fallback recall for long-term preferences, repeated fixes, and project constraints; recall injects source-labeled summaries into the prompt prefix. In scope: embedded backend, Store ABC seam, prefix injection with drill-down, curate-gated macro capture, three opt-in surfaces. Out of scope: cloud endpoints, Hindsight (explicitly out), sidecar daemons, memsearch implementation (stays a future sibling backend).

</domain>

<decisions>
## Implementation Decisions

### Deployment shape
- **D-01:** Embedded library — OpenViking runs in-process in the CLI; no sidecar daemon, no extra process to manage.
- **D-02:** Local only — no cloud endpoints this phase; deployment stays fully offline-capable.
- **D-03:** The `viking://` store lives under repo `.agent/` (e.g. `.agent/viking/`): git-trackable, per-project, matching the memory-file precedent. — **Reversibility:** costly — the store path is a user-facing on-disk contract; moving it later needs a migration.
- **D-04:** Real OpenViking dependency — add the package (supply-chain review applies); do not reimplement the tree/summaries in stdlib.

### Seam composition
- **D-05:** Native first — OpenViking is consulted only when native memory has nothing relevant; today's behavior is preserved exactly when native answers.
- **D-06:** Native wins conflicts — when both backends disagree, native memory wins (same precedence as the `.agent/MEMORY.md` file rule).
- **D-07:** Store ABC — one MemoryStore interface with native and OpenViking implementations behind it (planner designs the ABC). OpenViking is an optional feature just like memsearch.
- **D-08:** Byte-identical when off — with OpenViking disabled, behavior matches today exactly. Exception: the planner may choose seam-always-live if it benefits memsearch too and is architecturally nice, with written justification.

### Recall surfacing
- **D-09:** Prefix injection — OpenViking hits inject into the prompt prefix like native memory, under the same cap; zero new UX.
- **D-10:** Summaries first — L0/L1 summaries in the prefix; full L2 content only on explicit drill-down.
- **D-11:** Label source — injected recall is tagged native vs openviking so the agent knows the provenance.
- **D-12:** On-demand drill-down — the agent can pull L2 full content on demand; planner picks the mechanism (slash, tool, or auto-escalation).

### Capture/write path
- **D-13:** Macro only — OpenViking keeps long-term preferences, repeated fixes, and project constraints; it never mirrors native memory or session transcripts.
- **D-14:** Curate-gated writes — OpenViking writes flow through the `/memory` curate loop (approve/deny) like native proposals, per the deny-first posture.
- **D-15:** Supersede on conflict — new writes supersede outdated OpenViking entries via OpenViking's contradiction resolution; no ask-on-conflict prompts.
- **D-16:** Deletes cascade — deleting from native memory also removes the corresponding OpenViking entries; one delete clears both.

### Opt-in surface
- **D-17:** All three surfaces: `/memory` toggle (primary), config key, and startup flag — mirroring the `/codeact` surface trio.
- **D-18:** Persisted choice — enable once and OpenViking stays on across sessions (differs from `/codeact`'s per-session default; memory is stickier than interface mode). — **Reversibility:** costly — persistence shapes the config contract and session-start behavior; flipping it later changes every-session behavior.
- **D-19:** Toggle writes config — the `/memory` toggle writes through to the config key, so toggle and config are one persisted thing.
- **D-20:** Flag first — precedence is startup flag > session toggle > config key; explicit invocation always wins.

### the agent's Discretion
Drill-down mechanism (D-12), exact config key and flag names, `/memory` toggle UX wording, and the Store ABC shape are left to planner/executor judgment within the locked decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/REQUIREMENTS.md` — SKILL-05 (opt-in OpenViking recall behind the memory seam; Hindsight explicitly out)
- `.planning/ROADMAP.md` — Phase 12 goal, SKILL-05 requirement, 3 success criteria (per-session/per-task opt-in, non-blocking cross-session recall, offline posture)

### Memory seam (the integration surface)
- `strands_code_cli/memory_file.py` — load/parse/dump, inject cap, mtime reload, precedence line — the seam to build behind
- `.planning/phases/06-skills-memory-file/06-CONTEXT.md` — Dual-file contract (D-04), curate surface (D-06), memory modes (D-07) — locked precedents

### Prior-phase precedents
- `.planning/phases/11-codeact-action-interface/11-CONTEXT.md` — Three-surface opt-in (D-02), flag-first precedence, CodeAct ls/grep navigation synergy
- `.planning/phases/04-*/04-CONTEXT.md` — Deny-first approval gate, curate loop patterns (D-14 integration context)

Note: `.planning/codebase/*.md` maps are stale (2026-09-22, pre-CLI layout) — researcher should verify current `strands_code_cli/` paths directly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `memory_file.py` (`strands_code_cli/memory_file.py`): MemorySnapshot, load/parse/dump, MEMORY_INJECT_CAP (16000), mtime reload notes — the native side of the seam
- `/memory` curate loop: approve/deny proposal flow for D-14 gated writes
- `/codeact` surface trio (`--codeact` flag, config keys, slash toggle): the D-17 implementation template
- `provider_config.py` fail-loud config validation: the D-19 persisted-key pattern

### Established Patterns
- Session-sticky toggles with manual user choice winning (Phases 4/8/11) — D-17/D-20 follow this
- Deny-first approvals, curate-by-default (Phases 3/6) — D-14 follows this
- Display-only cost, labeled provenance (Phases 5/10/11) — D-11 follows this
- Embedded, offline, zero-daemon posture (project constraint) — D-01/D-02 follow this

### Integration Points
- Memory load/inject path (`memory_file.py` + loop prompt assembly): Store ABC seam (D-07), native-first fallback (D-05), labeled summaries under cap (D-09/D-10/D-11)
- `/memory` command: recall toggle (D-17), curate-gated OpenViking writes (D-14), cascading deletes (D-16)
- Session startup + config: startup flag, config key with toggle write-through, flag-first precedence (D-17/D-19/D-20)
- Drill-down path: L2 full-content retrieval mechanism (D-12, planner's choice)

</code>

<specifics>
## Specific Ideas

- User stressed OpenViking is "an optional feature just like memsearch" — optionality is a first-class requirement, not just a default; the disabled path must be byte-identical (D-08) unless the planner justifies seam-always-live for memsearch's benefit too.
- Persistence (D-18) deliberately differs from `/codeact`'s per-session default: the user views memory enablement as stickier than interface mode.

</specifics>

<deferred>
## Deferred Ideas

- OpenViking cloud endpoints — local-only this phase (D-02); revisit only on explicit demand.
- memsearch implementation as a sibling backend — stays future work; D-08 notes the seam should not preclude it.
- Sidecar-daemon deployment — rejected in favor of embedded (D-01).

None of the above belong in Phase 12 scope.

</deferred>

---

*Phase: 12-OpenViking Recall Backend*
*Context gathered: 2026-10-16*
