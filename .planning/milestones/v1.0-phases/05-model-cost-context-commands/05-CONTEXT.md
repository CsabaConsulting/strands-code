# Phase 5: Model + Cost + Context Commands - Context

**Gathered:** 2026-09-27
**Status:** Ready for planning

## Phase Boundary

Users can switch providers mid-session via `/model` (Bedrock default, override-friendly) and continue the same conversation; see token spend and context pressure automatically plus on-demand via `/cost` (display only, never enforcement); and manage context with `/compact`, `/clear`, `/context` without losing their place. In scope: turn-boundary-only model switching with history conversion-or-compaction, provider-aware model discovery plus custom IDs/ARNs/endpoints, auto token + context-% + money-if-available display, auto-compact preserving tool history. Out of scope: automatic model routing (locked), cost budgets/enforcement (locked), general auto/yolo mode (prior deferred), `/btw` side-channel (Phase 7).

## Implementation Decisions

### Model switching scope and safety
- **D-01:** `/model` switches only at the idle prompt, never mid-turn. An in-flight turn holds approvals and broker state tied to the old model; mid-task switching corrupted session manifests in comparable harnesses. — **Reversibility:** costly — turn Machinery and approval paths assume one model per turn; relaxing it re-opens the broker contract.
- **D-02:** Every model id is a distinct capability set (context window plus feature flags). Model family membership implies nothing: smaller windows (e.g. Haiku vs Sonnet/Opus) and vendor rule differences (observed live: `reasoningContent` rejected cross-vendor) each break switches independently. Check per switch, never assume.
- **D-03:** Non-Bedrock providers are in scope via adapters (MODEL-01 says providers, Bedrock default). Do not hand-roll translation: reuse LiteLLM/OpenRouter-style mapping; researcher to confirm the strands LiteLLM provider. Cautionary precedent: Claude Code Router does not translate tool semantics (open issue: tool calls lost in translation).

### History portability on switch
- **D-04:** Convert portable blocks when the new window fits; compact when it does not. Thinking traces become text/event form, tool semantics go through the adapter layer; replay recent turns verbatim, summarize older context, replay the last user message after compaction (convergent field pattern). Verbatim-only and strip-only were both rejected by the user.
- **D-05:** Fallback for models without native function calling is text-serialized tool prompts (OpenHands precedent), only if such a target is ever selected.

### Model selection UX
- **D-06:** Provider-aware discovered list plus custom entry — never a static curated list. For Bedrock, enumerate from the configured region; preserve exact ARN form including global versus regional prefixes (`us.`, `eu.`); accept OpenAI-compatible IDs/endpoints and Mantle targets. If discovery is unavailable, fall back to configured/custom entries rather than guessing. — **Reversibility:** costly — persisted provider/model choice shape plus discovery caching would need migration if redone.

### Cost display
- **D-07:** Automatic display shows abbreviated token value with fractional digits plus context percentage, e.g. `451.27K (45%)`, whenever cheap to compute; money appears only if pricing is already available without expensive lookup. `/cost` gives the fuller per-session/per-task breakdown (MODEL-02). Display only — budgets stay out of scope.

### Context pressure
- **D-08:** Auto-compact at the threshold, preserving structured tool calls/results and summarizing prose. The live context-% from D-07 keeps pressure visible either way, so no separate warning UI is needed.

### the agent's Discretion
- Exact `/clear` semantics (wipe history vs new session id; what carries over).
- Full `/context` content beyond usage percentage (message counts, window details, task breakdown shape).
- Pricing source for money display (static table vs provider data) and compact summarizer choice, within D-07/D-08.
- Mid-turn `/model` refusal UX (error text vs queue-until-idle), within D-01.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints (manual switching only; AWS-optional; no keys in repo)
- `.planning/REQUIREMENTS.md` — MODEL-01, MODEL-02, SES-02 (this phase)
- `.planning/ROADMAP.md` — Phase 5 goal, success criteria, dependencies

### Prior phases (locked)
- `.planning/phases/04-plan-act-modes-steering/04-CONTEXT.md` — reply-only router actions; gate/turn layer for prompts; vocabulary lock (plan/act words reserved; /model /cost /compact /context named free); transcript-first UX
- `.planning/phases/03-permissions-gate/03-CONTEXT.md` — single-HITL gate spine; deny-first approvals
- `.planning/phases/03-permissions-gate/03-SECURITY.md` — residual constraints on second handlers and scope widening

### Codebase orientation
- `.planning/codebase/STRUCTURE.md` — repo layout (note: maps predate `strands_code_cli/`; CLI layer orientation below)
- `.planning/codebase/INTEGRATIONS.md` — Strands SDK model-agnostic loop; `get_response_metrics()` token/cycle/duration helper with Bedrock cost math (`strands_code_agent/utils.py`)
- `.planning/codebase/CONVENTIONS.md` — constructor-kwarg config, never env sniffing; absolute imports; no new logging on agent-visible paths
- `strands_code_cli/provider_config.py` — `ProviderConfig` file (`~/.config/strands-code/config.yaml`, `model` key) exists for `/model` to inherit; startup-only today
- `strands_code_cli/router.py` — `dispatch` tri-state; new slash commands route here as reply actions
- `strands_code_cli/session_index.py` — sidecar index plus snapshot files; resume/compaction machinery connects here

## Existing Code Insights

### Reusable Assets
- `ProviderConfig` (`strands_code_cli/`): persisted YAML provider choice with `model` key — `/model` reads and writes this shape
- `get_response_metrics()` (`strands_code_agent/utils.py`): per-turn input/output tokens, cycles, duration, optional per-1M cost math — feeds auto display and `/cost`
- `SessionIndex` + snapshot files (`.agent/sessions/`): persisted history with `reasoningContent` blocks — conversion/compaction operates here
- Choice dialog (`strands_code_cli/choice.py`): owned-keys radio control (arrows, Enter/Space confirm, ESC deny) — reuse for `/model` list selection
- `BatchState` turn-cache pattern (`strands_code_cli/policy_gate.py`): per-turn state precedent if switch/compact state needs it

### Established Patterns
- Constructor-kwarg configuration, never env sniffing (convention — provider auth UX must respect this alongside AWS-optional posture)
- Reply-only router actions; prompts and approvals live in the gate/turn layer
- ApprovalBroker main-thread prompt pump (`strands_code_cli/policy_gate.py`, `strands_code_cli/loop.py`): any new prompt (e.g. compact confirmation) runs on main, never the SDK worker thread
- Denials never cover; only approvals silence retries — any new confirmation follows the same fail-closed shape

### Integration Points
- `main.py build_agent`: model wiring (`config.model` today) — `/model` re-points this mid-session and rebuilds/resumes the agent on the same conversation
- `router.py dispatch`: `/model`, `/cost`, `/compact`, `/clear`, `/context` branches
- Strands model providers (Bedrock/Anthropic/OpenAI/LiteLLM): capability sets per model id; researcher confirms translation coverage

## Specific Ideas

- Field pattern for switches: convert-when-fits, compact-when-needed, replay-last-user-message to re-ground.
- Prior-art pointers for the researcher: OpenCode (event logs + auto-summarize + replay-last-message), Cline (mid-task switch manifest fix; long-output summarization), Kilo condensing, Claude Code Router (proxy routing does NOT translate tool semantics — do translation in our history layer), OpenHands text-serialized tool fallback, Mastra scoped model switching, LiteLLM/OpenRouter/Bifrost adapters for endpoint breadth (Nemotron-class, Chinese, OpenAI-compatible, Mantle).
- User-noted ARN pitfall: global vs regional (`us.`/`eu.`) Bedrock prefixes change identity — preserve verbatim, never normalize.

## Deferred Ideas

- Automatic model routing (locked out of scope per PROJECT.md).
- Cost budgets/enforcement (locked: display only).
- General auto/yolo mode (prior deferred, D-08 Phase 4).
- `/btw` side-channel (Phase 7).

---
*Phase: 5-Model + Cost + Context Commands*
*Context gathered: 2026-09-27*
