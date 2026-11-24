# Phase 16: First-Class Meta Model API (api.meta.ai / Muse) & Upstream Enablement - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `16-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-24
**Phase:** `16-first-class-meta-model-api-muse`
**Areas discussed:** Ambient default & contributor tiers (`D-01`), Ambient provider priority order (`D-02`), Packaging extra & env vars (`D-03`), Live empirical `api.meta.ai/v1` probe & UAT (`D-04`), Folded `1.66.0` / `0.5.0` upstream resync & `gpt-6.2-sol` bump (`D-05`), Held `#6521` upstream probe comment (`D-08`)

*(Pre-decided anchors from Roadmap, Requirement `MODEL-09`, `CsabaConsulting/strands-code#21`, filed upstream issue `strands-agents/harness-sdk#6521`, and `v2.0` patterns not re-asked: thin retireable `meta/` adapter on `OpenAIResponsesModel`, credential-gated `GET /v1/models` filtering out non-chat entries like `muse-voice-transcribe-*` / `sam-*` with `("meta", "muse")` `_vendor_family()` grouping, narrowing `_MEDIA_LESS` from `(None, "meta", None, None)` so multimodal Muse keeps media while Bedrock Llama stays text-only, static fallbacks for `muse-ember-1.0` & 50× contributor cache rates + 1M windows, `MODEL_API_KEY` presence checks kept strictly inside `first_run.py`, `docs/QUICKSTART.md` setup guide, and pristine `strands_code_agent/`.)*

---

## Round 1: Ambient Default, Live Probe, Packaging/Env Vars & Upstream Resync

### Q1: Ambient default model when only `MODEL_API_KEY` is set (`D-01`)

When only `MODEL_API_KEY` is set (no `--model` and no saved config), what should the ambient default behavior be?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Auto-pick `meta/muse-spark-1.3` | Standard non-contributor default; keep `-contributor` opt-in via `--model` or `/model`. | |
| Auto-pick `meta/muse-spark-1.3-contributor` | Cheapest default; 50× cached discount (\$0.10 in / \$0.002 cached / \$0.20 out). | ✓ |
| Require explicit `--model meta/...` | No ambient auto-pick when only `MODEL_API_KEY` is set. | |

**User's choice:** Auto-pick `meta/muse-spark-1.3-contributor` (cheapest default; 50× cached discount).

---

### Q2: Live `api.meta.ai/v1` protocol probe & UAT key availability (`D-04`)

Do you have a Meta `MODEL_API_KEY` available for the live `api.meta.ai/v1` protocol probe and live UAT?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Yes — I have (or will put) `MODEL_API_KEY` in `.env` | Run the live `api.meta.ai/v1` protocol probe and live UAT. | ✓ |
| Offline-first for now | Build the retireable adapter, unit tests, and live probe/UAT scripts ready to run once I add a key later. | |

**User's choice:** Yes — I have (or will put) `MODEL_API_KEY` in `.env` so we can run the live `api.meta.ai/v1` protocol probe and live UAT.

---

### Q3: Packaging extras & environment variables (`D-03`)

How should Phase 16 expose packaging extras and environment variables for Meta Model API?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* `meta` extra alias + `MODEL_API_KEY` primary + `META_API_KEY` fallback (+ optional `META_BASE_URL`) | Reuses `strands-agents[openai]` + `openai>=2.0.0`, accepts `MODEL_API_KEY` primary and `META_API_KEY` fallback, plus optional validated `META_BASE_URL`. | ✓ |
| `meta` extra alias + strictly `MODEL_API_KEY` only | Matching Meta docs & `harness-sdk#6521` without `META_API_KEY`/`META_BASE_URL` aliases. | |
| Reuse `openai` extra + strictly `MODEL_API_KEY` only | No separate `meta` extra. | |

**User's choice:** Add a `meta` extra alias (reusing `strands-agents[openai]` + `openai>=2.0.0`) and accept `MODEL_API_KEY` primary + `META_API_KEY` fallback (+ optional `META_BASE_URL`).

---

### Q4: Upstream coordination & `strands-agents 1.66.0` / `harness 0.5.0` release (`D-05`)

How should Phase 16 coordinate with upstream `strands-agents/harness-sdk` (`#6521` and the recent `1.66.0` / `0.5.0` release)?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Keep Phase 16 strictly scoped to `MODEL-09` on `1.65.0` / `0.4.0` | Keep existing lockfile and post empirical probe findings as a comment on `harness-sdk#6521`. | |
| Fold upstream resync (`1.66.0` / `0.5.0` + `gpt-6.2-sol` default) into Phase 16 | Bump `pyproject.toml`/`uv.lock` to `strands-agents>=1.66.0` / `strands-harness>=0.5.0`, retire temporary GPT-6.2 fallback bridge, and bump OpenAI ambient default to `openai/gpt-6.2-sol`. | ✓ |
| Scope to `MODEL-09` on `1.65.0`/`0.4.0` + prepare upstream PR branch for `#6521` | Include an external upstream PR branch alongside local adapter. | |

**User's choice:** Also fold an upstream resync to `strands-agents 1.66.0` / `harness 0.5.0` (plus bumping OpenAI default to `gpt-6.2-sol`) into Phase 16.

---

## Round 2: Priority Order & Upstream `#6521` Probe Comment Policy

### Q5: Ambient auto-pick priority order (`D-02`)

Where should Meta (`MODEL_API_KEY` / `META_API_KEY` -> `meta/muse-spark-1.3-contributor`) sit in ambient auto-pick priority when multiple provider keys are set?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* After Google, Anthropic, and OpenAI | `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter error -> Bedrock`, so adding `MODEL_API_KEY` never preempts existing provider defaults. | ✓ |
| First priority (`Meta -> Google -> Anthropic -> OpenAI -> Bedrock`) | `MODEL_API_KEY` wins when multiple keys are present. | |

**User's choice:** After Google, Anthropic, and OpenAI (`Google -> Anthropic -> OpenAI -> Meta -> OpenRouter error -> Bedrock`).

---

### Q6: Sharing empirical probe findings on upstream `harness-sdk#6521` (`D-08`)

After our live probe against `api.meta.ai/v1`, how should we handle sharing empirical findings on upstream `harness-sdk#6521`?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Draft held follow-up comment in `docs/upstream/` for review | Same policy as our other issue drafts (`HOLD BEFORE POSTING` for human review before posting to `harness-sdk#6521`). | ✓ |
| Skip drafting an upstream comment on `#6521` for now | Keep probe findings in Phase 16 planning docs only. | |

**User's choice:** Draft a held empirical-probe follow-up comment in `docs/upstream/` for review before posting to `harness-sdk#6521`.
