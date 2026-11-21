# Phase 5: Model + Cost + Context Commands - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-27
**Phase:** 5-Model + Cost + Context Commands
**Areas discussed:** Switching models, Cost display, Context commands

---

## Switching models

| Option | Description | Selected |
|--------|-------------|----------|
| Strip bad blocks | Strip incompatible history blocks on switch, keep the rest | |
| Keep all history | Replay history verbatim into the new model | |
| Summarize on switch | Compact unconditionally at every switch | |

**User's choice:** None of the above (free text), reframed through discussion: convert portable blocks when the new window fits, compact when it does not; switch only at the idle prompt, never mid-turn.
**Notes:** User reported the live failure motivating this: opus `reasoningContent` history rejected on a gpt switch (ValidationException). User asked whether same-family switches are safe (answered: no — window sizes and feature flags differ per model id) and whether non-Bedrock endpoints are supported (answered: yes, MODEL-01 says providers). User requested deep prior-art research; findings (OpenCode replay+compact+last-message, Cline mid-task switch fix, CCR tool-loss caution, OpenHands text fallback, Mastra scoped switching, LiteLLM/OpenRouter adapters) informed the locked direction. User confirmed with "go".

## Model selection UX

| Option | Description | Selected |
|--------|-------------|----------|
| Curated list | Static alias list (haiku/sonnet/opus/...) | |
| Freeform id | Raw model id string only | |
| List + custom | Static list plus custom-id escape hatch | |

**User's choice:** None of the above (free text, twice): provider-aware *discovered* list plus custom entry.
**Notes:** For Bedrock, enumerate from the configured region. Accept OpenAI-compatible IDs/endpoints, exact Bedrock ARNs (user-flagged pitfall: global vs regional `us.`/`eu.` prefixes change identity — preserve verbatim), and Mantle targets. Fall back to configured/custom entries when discovery is unavailable.

## Cost display

| Option | Description | Selected |
|--------|-------------|----------|
| Auto line + /cost | Automatic per-task line plus on-demand breakdown | |
| /cost only | Manual command only | |
| Session footer | Persistent session-level line | |

**User's choice:** None of the above (free text): auto-display token consumption and context size as percentage of the selected model's limit when cheap to compute; money only if pricing already available; `/cost` for the fuller breakdown.
**Notes:** Follow-ups locked: abbreviated token values (e.g. `450K`) alongside the percentage; fractional digits allowed (e.g. `451.27K`).

## Context commands

| Option | Description | Selected |
|--------|-------------|----------|
| Auto, keep tools | Auto-compact at threshold, preserve tool history | ✓ |
| Manual only | `/compact` strictly on demand | |
| Always ask first | Confirm every compaction | |

**User's choice:** Auto, keep tools.
**Notes:** Preserve structured tool calls/results, summarize prose. Live context-% from the cost display keeps pressure visible.

## Done check

| Option | Description | Selected |
|--------|-------------|----------|
| Ready for context | Finish discussion, write CONTEXT.md | |
| Explore more | Identify additional gray areas | ✓ |

**User's choice:** Explore more.
**Notes:** Additional areas offered (Provider auth, /clear semantics, /context content) were declined via free text ("None of the above"); those details move to planner discretion within the locked constraints. User then supplied the model-listing and cost-display specifics above and asked to continue the interrupted turn with them in mind — discussion wrapped to CONTEXT.md.

---

## the agent's Discretion

- Exact `/clear` semantics (wipe history vs new session id; what carries over).
- Full `/context` content beyond usage percentage.
- Pricing source for money display and compact summarizer choice.
- Mid-turn `/model` refusal UX, within the idle-only lock.

## Deferred Ideas

- Automatic model routing (locked out of scope per PROJECT.md).
- Cost budgets/enforcement (locked: display only).
- General auto/yolo mode (prior deferred).
- `/btw` side-channel (Phase 7).
