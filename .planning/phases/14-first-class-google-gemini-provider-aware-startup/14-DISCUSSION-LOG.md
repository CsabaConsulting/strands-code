# Phase 14: First-Class Google Gemini & Provider-Aware Startup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `14-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-21
**Phase:** `14-first-class-google-gemini-provider-aware-startup`
**Areas discussed:** Startup opening model & `--model` flag (`D-02`), Mutually exclusive Google auth fail-fast (`D-03`), `/model` Gemini discovery & static fallback (`D-05`), Gemini 2.5 vs. 3 compatibility guard & `driver.py g1` UAT (`D-07`)

*(Pre-decided anchors from Roadmap & `v2.0` research not re-asked: `gemini` optional extra + `_SDK_EXTRA_HINTS["google"]`, non-prefix env presence + `STRANDS_BOX=1` STS bypass, `toolUse["reasoningSignature"]` cross-vendor strip, `_vendor_family` dot-split fix, `litellm_entry` `gemini/` lookup, and `docs/QUICKSTART.md` Google AI Ultra credit guide.)*

---

## Startup Opening Model & `--model` CLI Flag (`D-02`)

Q1: When `config.yaml` has no model yet and no AWS creds exist, how should startup pick the opening model?

| Option | Description | Selected |
|--------|-------------|----------|
| Env auto-pick + `--model` CLI flag | Auto-pick an opening model from ambient env (e.g. `google/gemini-2.5-flash` when `GOOGLE_API_KEY`/`GEMINI_API_KEY` is set; `anthropic`/`openai` when keyed) + add `--model` CLI flag. | ✓ |
| Env auto-pick only | Auto-pick an opening model from ambient env only (no new `--model` CLI flag). | |
| Require explicit selection | Require explicit `config.yaml` or `--model` when non-AWS (never guess a default model). | |

**User's choice:** Auto-pick an opening model from ambient env + add `--model` CLI flag.

---

## Mutually Exclusive Google Auth Handling (`D-03`)

Q2: How should preflight handle mutually exclusive Google auth vars (both `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_API_KEY`/`GEMINI_API_KEY` set)?

| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast + Vertex project check | Fail fast in preflight with an actionable message naming the conflicting vars; Vertex mode checks `GOOGLE_CLOUD_PROJECT`. | ✓ |
| Warn only | Warn at launch and let `google-genai` raise its own `ValueError` on first turn. | |

**User's choice:** Fail fast in preflight with an actionable message naming the conflicting vars; Vertex mode checks `GOOGLE_CLOUD_PROJECT`.

---

## `/model` Gemini Discovery & Static Fallback (`D-05`)

Q3: How should `/model` discover and display Google Gemini models?

| Option | Description | Selected |
|--------|-------------|----------|
| Live when keyed + gated fallback | Live `genai.Client().models.list()` (`generateContent` `gemini-*` only) when Google-keyed, merged with Bedrock if AWS-keyed; curated static Gemini fallback only when Google creds exist (don't clutter AWS-only users). | ✓ |
| Always show static Gemini | Always show curated static Gemini models in `/model` even without Google creds (surface install/key hint if selected). | |
| Live only (no static fallback) | Live discovery only when Google-keyed (no static fallback list; manual entry via `/model google/<id>`). | |

**User's choice:** Live `genai.Client().models.list()` when Google-keyed (merged with Bedrock if AWS-keyed), with curated static Gemini fallback only when Google credentials exist.

---

## Live Gemini UAT & Harness Compatibility Guard (`D-07`)

Q4: How should we handle live Gemini UAT and any `harness-py` Gemini 2.5 vs. 3 `thinking_config` quirks?

| Option | Description | Selected |
|--------|-------------|----------|
| Hermetic CI + `driver.py g1` + fail-soft guard | Hermetic unit/contract tests + add repeatable `driver.py g1` scenario (run live if a Google key is set) + fail-soft local guard for any Gemini 2.5 vs. 3 harness thinking mismatch (+ draft upstream issue if hit). | ✓ |
| Hermetic tests only | Hermetic unit/contract tests only for Phase 14 (no new live `driver.py` scenario). | |
| Require live Gemini UAT | Add `driver.py g1` and require a live Google AI Studio UAT run before closing Phase 14. | |

**User's choice:** Hermetic unit/contract tests + repeatable `driver.py g1` scenario (run live if a Google key is set) + fail-soft local guard for any Gemini 2.5 vs. 3 harness thinking mismatch (+ draft upstream issue if hit).
