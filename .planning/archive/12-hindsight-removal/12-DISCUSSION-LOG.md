# Phase 12: OpenViking Recall Backend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-16
**Phase:** 12-openviking-recall-backend
**Areas discussed:** Deployment shape, Seam composition, Recall surfacing, Capture/write path, Opt-in surface

---

## Deployment shape

Q1: How should OpenViking run in strands-code?

| Option | Description | Selected |
|--------|-------------|----------|
| Embedded library | OpenViking runs inside the CLI process as a library; viking:// is an on-disk tree under .agent/. Zero new processes, fully offline. | ✓ |
| Sidecar daemon | A background daemon owns the viking:// store; the CLI queries it. Better isolation, another process to manage. | |
| On-disk tree only | No OpenViking runtime at all — the CLI reads/writes a viking://-shaped on-disk tree directly with its own tools. | |

**User's choice:** Embedded library
**Notes:** None

Q2: Should OpenViking cloud endpoints be in scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Local only | Local/embedded only this phase. Cloud endpoints can come later if ever. | ✓ |
| Cloud option too | Support OpenViking cloud endpoints as a config option alongside local. | |

**User's choice:** Local only
**Notes:** None

Q3: Where should the viking:// store live?

| Option | Description | Selected |
|--------|-------------|----------|
| Repo .agent/ | viking:// lives under .agent/viking/ in the repo. Git-trackable, per-project, matches the memory-file precedent. | ✓ |
| Global home dir | A global ~/.strands/viking store shared across projects. Cross-project recall, outside git. | |
| Both layers | Repo store by default with an optional global overlay. Most flexible, most complexity. | |

**User's choice:** Repo .agent/
**Notes:** None

Q4: Real OpenViking dependency or stdlib reimplementation?

| Option | Description | Selected |
|--------|-------------|----------|
| Real dependency | Add the OpenViking package as a dependency. Real integration, supply-chain review applies. | ✓ |
| Reimplement stdlib | Implement the viking:// tree + tiered summaries ourselves with stdlib only. Zero new deps, more code. | |

**User's choice:** Real dependency
**Notes:** None

---

## Seam composition

Q1: How do native memory and OpenViking compose behind the seam?

| Option | Description | Selected |
|--------|-------------|----------|
| Native first | Native memory serves first; OpenViking is consulted only when native has nothing relevant. Cheapest, preserves today's behavior exactly. | ✓ |
| Parallel merge | Both backends are queried and their results merged into one recall block. Richest recall, most tokens. | |
| Per-query route | Each query goes to exactly one backend based on the query kind (session facts vs long-term recall). Most precise, routing logic to maintain. | |

**User's choice:** Native first
**Notes:** None

Q2: When both backends disagree, which wins?

| Option | Description | Selected |
|--------|-------------|----------|
| Native wins | When both backends answer differently, native memory wins — same precedence as the .agent/MEMORY.md file rule. | ✓ |
| Newest wins | Newer information wins regardless of backend. Recency over source. | |
| Show both | Both answers surface with their sources labeled and the agent/user decides. Most transparent, most noise. | |

**User's choice:** Native wins
**Notes:** None

Q3: What should the seam look like in code?

| Option | Description | Selected |
|--------|-------------|----------|
| Store ABC | One MemoryStore interface with native and OpenViking implementations behind it. Clean seam, planner designs the ABC. | ✓ |
| Inline calls | OpenViking calls stay inline at the existing memory call sites. Less abstraction, more coupling. | |

**User's choice:** Store ABC
**Notes:** "I also want to press that OpenViking is an optional feature just like memsearch"

Q4: When OpenViking is disabled, how close to today's behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Byte-identical | With OpenViking disabled, behavior is byte-identical to today — no extra latency, no code paths touched. | ✓ |
| Seam always live | The seam abstraction is always in the path even when OpenViking is off. Simpler code, tiny overhead. | |

**User's choice:** Byte-identical
**Notes:** "unless a seam always live would be beneficial for memsearch as well, and architecturally nice"

---

## Recall surfacing

Q1: How should OpenViking recall reach the turn?

| Option | Description | Selected |
|--------|-------------|----------|
| Prefix injection | OpenViking hits are injected into the prompt prefix like native memory, under the same cap. Zero new UX. | ✓ |
| Filesystem tools | Recall arrives as viking:// paths the agent explores with ls/grep/cat tools. CodeAct-native, more turns. | |
| Curate proposals | Recall surfaces as /memory curate proposals the user approves before injection. Most control, most friction. | |

**User's choice:** Prefix injection
**Notes:** None

Q2: Summaries or full content in the injected recall?

| Option | Description | Selected |
|--------|-------------|----------|
| Summaries first | Use OpenViking's L0/L1 summaries for the prefix; full L2 content only on explicit drill-down. Token-efficient. | ✓ |
| Full content | Inject full recall content up to the cap. Simpler, burns more tokens. | |

**User's choice:** Summaries first
**Notes:** None

Q3: Should injected recall name its backend?

| Option | Description | Selected |
|--------|-------------|----------|
| Label source | Injected recall is tagged with its backend (native vs openviking) so the agent knows the source. Auditable. | ✓ |
| No labels | Recall is recall — no source tags. Cleaner prompts, less traceable. | |

**User's choice:** Label source
**Notes:** None

Q4: Can the agent drill into full L2 content on demand?

| Option | Description | Selected |
|--------|-------------|----------|
| On demand | Provide a way to pull L2 full content on demand (planner picks: slash, tool, or auto-escalation). | ✓ |
| No drill-down | Summaries only this phase; no drill-down path. Narrower scope. | |

**User's choice:** On demand
**Notes:** None

---

## Capture/write path

Q1: What gets written to OpenViking?

| Option | Description | Selected |
|--------|-------------|----------|
| Macro only | Long-term preferences, repeated terminal fixes, and project constraints — the macro layer native memory doesn't keep. | ✓ |
| Mirror native | Mirror everything native memory keeps plus the macro layer. Redundant but complete. | |
| Sessions only | Session transcripts and traces go to OpenViking; durable facts stay native-only. Split by ephemerality. | |

**User's choice:** Macro only
**Notes:** None

Q2: What approval gates OpenViking writes?

| Option | Description | Selected |
|--------|-------------|----------|
| Curate-gated | Writes flow through the /memory curate loop (approve/deny) like native proposals. Deny-first consistent. | ✓ |
| Auto-capture | Background auto-capture with transcript logging, like silent memory mode. Zero friction, less control. | |
| Follow memory mode | Follow the session's memory mode: curate mode gates writes, silent mode auto-captures. One rule. | |

**User's choice:** Curate-gated
**Notes:** None

Q3: How are conflicting writes handled?

| Option | Description | Selected |
|--------|-------------|----------|
| Supersede | New writes supersede outdated OpenViking entries; contradiction resolution is OpenViking's job per its design. | ✓ |
| Ask on conflict | Conflicting writes surface as curate proposals asking which to keep. Most control, most prompts. | |
| Keep both | Both versions persist; recall shows recency. Simplest, recall can contradict itself. | |

**User's choice:** Supersede
**Notes:** None

Q4: Do native deletes cascade to OpenViking?

| Option | Description | Selected |
|--------|-------------|----------|
| Cascade | Deleting from native memory also removes the corresponding OpenViking entries. One delete, both gone. | ✓ |
| Independent | Each backend deletes independently; the user clears OpenViking separately. More control, two steps. | |

**User's choice:** Cascade
**Notes:** None

---

## Opt-in surface

Q1: How should the user enable OpenViking recall?

| Option | Description | Selected |
|--------|-------------|----------|
| /memory toggle | A /memory subcommand or flag toggles OpenViking recall for the session. Lives with memory UX. | ✓ |
| Config key | A config key enables OpenViking recall. Persists, no session UX. | |
| Startup flag | A startup flag boots with OpenViking recall on. Explicit per launch. | |

**User's choice:** /memory toggle — plus "and also config key and startup flag" (all three, mirroring /codeact)
**Notes:** User took all three surfaces, not just the primary

Q2: Session-scoped toggle or persisted choice?

| Option | Description | Selected |
|--------|-------------|----------|
| Session toggle | The toggle lasts for the session; fresh sessions start native-only. Matches the /codeact precedent. | |
| Persist choice | Enable once and it stays on across sessions. Convenient, weakens the default. | ✓ |

**User's choice:** Persist choice
**Notes:** Deliberately differs from /codeact's per-session default

Q3: How does the persisted choice work?

| Option | Description | Selected |
|--------|-------------|----------|
| Toggle writes config | The /memory toggle writes through to the config key, so the choice survives restarts. Toggle and config are one thing. | ✓ |
| Config persists only | Toggle is session-only; only the config key persists. Two mechanisms, explicit split. | |

**User's choice:** Toggle writes config
**Notes:** None

Q4: When surfaces disagree, what wins?

| Option | Description | Selected |
|--------|-------------|----------|
| Flag first | Startup flag beats session toggle beats config key. Explicit invocation always wins. | ✓ |
| Toggle wins | Session toggle beats everything once set; flag and config only set the starting state. | |

**User's choice:** Flag first
**Notes:** None

---

## the agent's Discretion

Drill-down mechanism, exact config key and flag names, `/memory` toggle UX wording, and the Store ABC shape (recorded in CONTEXT.md).

## Deferred Ideas

- OpenViking cloud endpoints, memsearch implementation, sidecar-daemon deployment (recorded in CONTEXT.md).

---

## Scope Supersede (2026-10-16, plan-phase research)

The OpenViking scope discussed above was abandoned before planning: 12-RESEARCH.md proved D-01 embedded-in-process impossible (OpenViking requires a running server; only RAGFS inside the server is in-process) and surfaced the AGPL server license. User rulings: (1) abandon OpenViking, redo Phase 12 as Hindsight support removal; (2) AGPL rejected, no OpenViking implementation. Hindsight confirmed not-in-process either (Postgres + background loop). Phase renamed OpenViking Recall Backend → Hindsight Removal; 12-CONTEXT.md rewritten; 12-RESEARCH.md kept as rejection evidence. This log preserved as audit trail.
