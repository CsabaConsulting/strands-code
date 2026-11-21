# Phase 13: Upstream SDK & Harness Resync - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `13-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-21
**Phase:** `13-upstream-sdk-harness-resync`
**Areas discussed:** Dependency floors, Context window precedence (`Model.model_info`), Bedrock `_NO_STREAMING_TOOLS` unary mode UX, Session restore history handling

---

## Dependency Bounds (`D-01`)

Q1: In Phase 13, how should we declare the new Strands dependency floors in `pyproject.toml` alongside bumping `uv.lock`?

| Option | Description | Selected |
|--------|-------------|----------|
| Raise lower bounds | Set `strands-agents>=1.65.0` and `strands-harness>=0.4.0` in `pyproject.toml` with zero upper pins and upgrade `uv.lock`. | ✓ |
| Keep `>=0.1` floors | Leave lower bounds at `>=0.1` with `getattr` fallbacks and upgrade `uv.lock` only. | |

**User's choice:** Raise lower bounds in `pyproject.toml` to `strands-agents>=1.65.0` and `strands-harness>=0.4.0` (still zero upper pins).

---

## Context Window Precedence (`D-02`)

Q2: Where should SDK `Model.model_info.limits.context_window` sit in `window_for()` precedence?

| Option | Description | Selected |
|--------|-------------|----------|
| Route-aware SDK first | Consult OpenRouter live first for `litellm/openrouter/*` routes (endpoint caps), SDK `model_info` first for direct providers, then LiteLLM -> static `MODEL_LIMITS`. | ✓ |
| SDK first always | Check `model_info` unconditionally before OpenRouter live for every model. | |
| SDK last before static | Check OpenRouter live -> LiteLLM bundled first, using `model_info` only before `MODEL_LIMITS`. | |

**User's choice:** SDK `model_info` first for direct providers; OpenRouter live first for `litellm/openrouter/*` routes (endpoint caps), then LiteLLM -> static `MODEL_LIMITS`.

---

## Bedrock `_NO_STREAMING_TOOLS` Unary Mode (`D-03`)

Q3: Once Phase 13 sets `streaming=False` automatically for Bedrock `_NO_STREAMING_TOOLS` (Llama 3/4) — which renders identically in `CodeAgentCallbackHandler` — what should the transcript show?

| Option | Description | Selected |
|--------|-------------|----------|
| Info note on launch & `/model` | Replace `"turns will fail"` warnings with `"Note: streaming disabled for <model> (Bedrock unary tool mode)."` on launch and `/model` (quiet on `/route`). | ✓ |
| Silent | Set `streaming=False` automatically with zero transcript note. | |
| Warn everywhere | Print a yellow note on launch, `/model`, and `/route` whenever `streaming=False` applies. | |

**User's choice:** Replace the old `"turns will fail"` warning with a brief info note (`"Note: streaming disabled for <model> (Bedrock unary tool mode)."`) on launch and `/model` (quiet on `/route`).

---

## Session Restore History Handling (`D-04`)

Q4: When resuming a persisted session (`--session-id` / `/resume`) onto a different configured model, how should history conversion work alongside upstream PR `#5166`?

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid restore | Let upstream `#5166` / `drop_block` handle Bedrock wire stripping untouched on media-capable Bedrock targets, AND run `convert_history()` on resume when the opening model is non-Bedrock or media-less. | ✓ |
| Wire strip only | Rely purely on upstream `#5166` / `drop_block` on resume; run `convert_history()` only on explicit `/model` switches. | |
| Convert on every model mismatch | Always run `convert_history()` on resume whenever opening model differs from last session model. | |

**User's choice:** Hybrid: let upstream `#5166` handle Bedrock wire stripping untouched, AND run `convert_history()` on resume if the opening model is non-Bedrock or media-less.
