# v2 Ecosystem Alignment & Architecture Brief

**Explored:** 2026-11-20 (`/gsd-explore` following completion of v1 Phases 1–12)
**Status:** Captured for `/gsd-complete-milestone` -> `/gsd-new-milestone` (v2 planning)

---

## 1. Context & Strategic Positioning

Since v1 Phase 12 wrapped on 2026-10-16, the upstream Strands ecosystem has evolved significantly (`strands-agents` moved into `strands-agents/harness-sdk/strands-py` alongside `harness-py`, `strands-py` reached `v1.65+`, `harness-py` reached `v0.4.0+`, `strands-agents/box` shipped Linux support, `@strands-agents/cli` reached `v0.3.0`, and `strands-agents-evals` expanded trajectory/red-team tooling). Meanwhile `aws-samples/sample-strands-code-agent` (`upstream` remote) remains frozen at `v0.4.0` + `4c7f25a`.

### Positioning vs. `@strands-agents/cli` (`strands-cli/`)
- **`strands-code` stays 100% Python** on `harness-py` (`strands-harness`) + `strands-py` (`strands-agents`) with **zero TypeScript dependencies**.
- `@strands-agents/cli` (`v0.3.0`) is TypeScript-only (`harness-ts`) and targets generic agent prototyping, quick terminal chats, and exporting starter `.py`/`.ts` scaffolding.
- `strands-harness` (`harness-py`) ships **no Python CLI or console script** — leaving a clear, unoccupied niche for `strands-code` as an opinionated **Python software-engineering & CodeAct CLI**.
- **Conventions already aligned (via `strands_harness.defaults`):** workspace directories (`./.agent/sessions`, `./.agent/skills`, `./.agent/memory`), `"provider/model"` IDs, and core slash verbs (`/model`, `/clear`, `/compact`).
- **Intentional divergence & SWE differentiators:** isolated global config (`~/.config/strands-code/config.yaml` vs. `~/.strands/cli/config.json`), diff-gated `write`/`edit` + `/diff`, session-sticky Plan/Act (`/mode`, `/approve`), anytime steering, parallel `/btw` side channel, calibrated `/route`, `/cost` actuals+estimates, and opt-in `--codeact`.
- **Selective CLI ergonomics to borrow:** explicit `/help` listing built-in slash commands and loaded skills, plus `@file` / `/file` fuzzy file/image attachment (`TOOL-05`) and `/review` (`REVIEW-01`).

### Byproduct-Only Upstreaming Policy
- **No standalone upstream side projects.** Upstream contributions to `strands-agents/harness-sdk` or `aws-samples/sample-strands-code-agent` will only be opened when they fall out directly from `strands-code` v2 work and provide mutual benefit:
  - **`strands-agents/harness-sdk`:** Only targeted issues/PRs if v2 implementation exposes concrete gaps (for example, if `harness-py` `resolve_model("google/...")` lacks clean handling for `GEMINI_API_KEY` or Vertex ADC / `location="global"`).
  - **`aws-samples/sample-strands-code-agent`:** Optionally contribute a small, self-contained PR for dependency version bumps and `strands-agents >=1.65` library adjustments discovered during our own upgrade (leaving the full `strands-code` CLI in this fork).

---

## 2. Pillar 1 — Full Convergence with `strands-py` (`v1.65+`) & `harness-py` (`v0.4.0+`)

- **Lockfile bump:** Upgrade `strands-agents` (`1.58.1` -> `>=1.65.0`) and `strands-harness` (`0.1.2` -> `>=0.4.0`) in `uv.lock`, keeping wrappers thin.
- **Decision routing convergence (`strands_code_cli/routing/`):**
  - Migrate custom Decision-API HTTP transports onto upstream `strands.decisions.DecisionModel` (`TypeSafeDecisionModel`, `DecisionsAPIDecisionModel`, `LLMDecisionModel`) + `ClassifierStrategy`.
  - **Preserve our tested CLI UX & calibration:** keep the `0.62` confidence threshold, `0.04` tie-margin gate, two-stage model + effort routing, `/route` commands/validation, Ollama local engine option, and `/cost` decision spend accounting on top of `DecisionModel`.
- **Upstream fixes & breaking defaults to reconcile on upgrade:**
  - **`#5166` (`BedrockModel._rejects_reasoning_block`) + `v1.62.0` (`drop_block` retry):** Resolves the Phase 4 `STATE.md` cross-family `reasoningContent` session-restore blocker at the Bedrock wire layer. **Keep `convert_history()` on explicit `/model` switches** so prior reasoning is preserved as readable `[Thinking trace]` text rather than dropped silently.
  - **`#5158` (`ContextInjector` tool-result adjacency):** Protects `OpenAIModel` / `LiteLLMModel` (OpenRouter) turns when `STRANDS.md` / `.agent/MEMORY.md` / `environment` injectors append user-role context alongside `toolResult` blocks.
  - **`#4853` & `#5159`:** Unlocks Nova 2 `reasoningConfig` thinking (`supports_thinking("bedrock/amazon.nova-2-lite-v1:0") == True`), regional Bedrock `web_fetch` summarizer mappings (`amazon.`, `meta.`, `mistral.`), and Claude Haiku 5.5 adaptive thinking (128k max tokens).
  - **`#5121` & `#5165`:** Keeps compaction markers out of `messages[0]` and surfaces `content_filtered` / `refusal` subagent stops as errors instead of fake successes.
  - **`harness-py v0.4.0` breaking default:** `todos` dropped from default built-in plugins — audit tests and system prompt expectations during upgrade.
  - **Shim audits:** Evaluate upstream `Agent.cancel()` (`v1.62.0`) vs. `steering.py`, SDK `model_info` vs. `model_capabilities.py` / `cost_context.py`, and preemptively setting `streaming=False` for `_NO_STREAMING_TOOLS` (Bedrock Llama 3/4, following upstream closure of `#4857`/`#4937`).

---

## 3. Pillar 2 — First-Class Google AI Gemini (`google/...`) & Personal Google AI Ultra

### How Personal Google AI Ultra Works via AI Studio API Key (Solved & ToS-Compliant)
- **Consumer OAuth piggybacking is explicitly Out of Scope:** Reusing or proxying Gemini CLI / Code Assist OAuth sessions (`cloudcode-pa.googleapis.com`) in third-party apps violates Google Terms of Service.
- **Official credit bridge (`Google Developer Program`):** Personal Google subscriptions bundle monthly promotional Google Cloud / Gemini API credits claimable in **Google AI Studio** (`aistudio.google.com`) with the same personal `@gmail.com` account:
  - **Google AI Pro:** $10 USD/month
  - **Google AI Ultra 5x:** $40 USD/month
  - **Google AI Ultra 20x:** $100 USD/month
  - Unused monthly grants accumulate and each monthly drop remains valid for 12 months.
- **One-time claim & setup flow:**
  1. Sign into `aistudio.google.com` with the personal `@gmail.com` account holding Google AI Ultra.
  2. Open **Billing** and activate a prepaid Google Cloud Billing account (Google requires a one-time $5 minimum prepaid deposit to move keys off the tight Free Tier rate limits; monthly plan credits are spent *first*, keeping the $5 deposit untouched unless credits are exhausted).
  3. Complete the **Claim Google Cloud Credits** flow in AI Studio.
  4. Enable **auto-apply** on the project / **AI Studio API Key** (`GOOGLE_API_KEY` or `GEMINI_API_KEY`).
  - *(Optional alternative)* The same credit-backed Cloud billing account also covers keyless Vertex AI ADC (`gcloud auth application-default login` with `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`).

### Required Changes in `strands-code`
1. **Provider-aware startup preflight (`strands_code_cli/entry/first_run.py`, `main.py`):** Replace the unconditional Bedrock STS check (`Bedrock-or-stop`, exit 2 before reading `config.yaml`) with a provider-aware check so users with `GOOGLE_API_KEY` / `GEMINI_API_KEY`, Vertex ADC, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, or a configured `ollama/` model launch cleanly with zero AWS credentials (honoring `AWS-optional, never AWS-required`).
2. **Packaging (`pyproject.toml`):** Add a `gemini` optional extra (`strands-agents[gemini]` / `google-genai`) and consider documenting/including `uv sync --extra gemini` alongside `--extra litellm`.
3. **Reasoning & routed effort (`strands_code_cli/model/model_switch.py`):** Remove the `provider not in ("bedrock", "anthropic")` gate in `supports_reasoning()` so `google/` delegates to `_harness_supports_thinking` (which ships per-model `_GOOGLE_LEVELS` in `harness-py v0.3.3+`).
4. **Model picker discovery, `/cost` coverage & docs:** Support `google/` discovery (`client.models.list()` when Google creds exist + static curated fallback), verify Gemini context windows and `/cost` pricing entries, and document the AI Studio + Google AI Ultra monthly credit setup in `docs/QUICKSTART.md`. *(Inspect `strands_harness.models.resolve_model` during implementation for `GEMINI_API_KEY` vs. `GOOGLE_API_KEY` and Vertex ADC edge cases; open a targeted upstream issue/PR only if needed.)*

---

## 4. Pillar 3 — Strands Box on Linux (`strands-agents/box`)

- **Blocker cleared:** As of Nov 2026, `strands-agents/box` (`v0.2.3+`) supports **Linux** via 3 co-located Rust binaries (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`) using unprivileged `CLONE_NEWUSER` / `CLONE_NEWNET` / mount / PID namespaces and `seccomp-bpf` (no `bwrap` or Landlock required; `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64`) alongside macOS Apple Silicon Seatbelt.
- **Defense-in-depth architecture:** Keep our interactive HITL approval UX (`/diff`, deny-first allowlists, Plan/Act) on top, and run `strands-code` inside **Strands Box** as a non-overridable kernel + policy floor beneath both `shell` and `python_repl`.
- **Capabilities gained:**
  - `box.toml` workspace/filesystem/network confinement (mitigating misclicked `"Always"` approvals).
  - Embedded **Dogwood Local Engine** (`policy.dw`) for stateful, temporal rules (e.g., gate git push on recent passing tests) — triggers a formal `v2.0` revisit of v1 decision D-05 ("never Cedar") scoped specifically to deterministic Dogwood.
  - **Out-of-band credential egress proxy:** keeps AWS/Google/Anthropic/OpenRouter/TypeSafe keys outside the agent process and prompt-injected subprocesses (using `strands_box_...` phantom tokens and provider-specific headers like `x-goog-api-key`).

---

## 5. Pillar 4 — Strands Evals (`strands-agents-evals`), Skills Marketplaces & CLI Ergonomics

- **Skills marketplaces (`SKILL-03`):** Support catalog `.agent-plugin/marketplace.json` / `.claude-plugin/marketplace.json` and direct GitHub `owner/repo[@ref]` installs into `./.agent/skills-marketplaces/<ns>/<skill>/` with `./.agent/skills-lock.json` SHA/hash pinning and deny-first symlink/zip-slip/protected-path guards.
- **Selective CLI ergonomics (`strands-cli`-inspired + `v2.0` backlog):**
  - Explicit `/help` listing built-in slash commands and loaded local skills (`LOOP-06`).
  - `@file` / `/file` fuzzy file and image/document attachment picker (`TOOL-05`).
  - `/review` read-only diff review command (`REVIEW-01`).
- **Automated agent quality & security evals (`strands-agents-evals >=1.10`):** Complement `scripts/uattest/` under `scripts/evals/` + `tests/evals/` covering:
  - Offline deterministic/mocked `TrajectoryEvaluator` + OTel span invariants on Plan -> `/approve` -> Act discipline, CodeAct tool gating, and `/route` selection quality.
  - Live `ActorSimulator` + `RedTeamExperiment` (Crescendo/GOAT/PAIR) for prompt-injection resilience across `./.agent/skills`, marketplace skills, `STRANDS.md`, and `./.agent/MEMORY.md`.

---

## 6. Locked `v2.0` Phase Roadmap

| Phase | Focus | Primary Requirements / Anchors |
| :--- | :--- | :--- |
| **Phase 13** | Upstream SDK & Harness Resync (`strands-agents >=1.65`, `strands-harness >=0.4`) + Shim Retirement (`#5166`, `#5158`, `InjectedBlock`, `Model.model_info`, `streaming=False` for `_NO_STREAMING_TOOLS`, `todos` audit, keep `steering.py`) | `UPSTREAM-01`, closes `STATE.md` Phase 4 restore blocker |
| **Phase 14** | First-Class Google Gemini (`google/`) + Box-Compatible Provider-Aware Startup Preflight + `reasoningSignature` / `_vendor_family` / `litellm_entry` Fixes + AI Studio Ultra Credit Docs | `MODEL-06` |
| **Phase 15** | Decision Routing Convergence onto `strands.decisions.DecisionModel` (`TypeSafeDecisionModel`, `OpenRouterDecisionModel`, `OllamaDecisionModel`, optional `LLMDecisionModel`; keeping `apply_model_action`, `0.62`/`0.04` gate & `/cost`) | `UPSTREAM-02`, `MODEL-03`, `MODEL-04` |
| **Phase 16** | Skills Marketplaces & Lockfile Installer (`/skills marketplace\|browse\|install\|update\|sync`, `./.agent/skills-marketplaces/`, `./.agent/skills-lock.json`, deny-first guards) | `SKILL-03` |
| **Phase 17** | Strands Box Linux Sandbox Floor + Deterministic Dogwood Policy (`box.toml` + `policy.dw` generator & 5-provider egress profiles, `codeact_shell` `sh -c` alignment, Linux `x86_64` + Ubuntu 24.04 AppArmor setup, formal D-05 revisit) | `SANDBOX-01` |
| **Phase 18** | CLI Ergonomics (`/help`, `@file` / `/file` attachment picker + `"document"` conversion, Python-collected read-only `/review`) | `LOOP-06`, `TOOL-05`, `REVIEW-01` |
| **Phase 19** | Strands Evals & Red-Team Suite (`strands-agents-evals >=1.10`, `scripts/evals/` + `tests/evals/`, offline invariants + live `ActorSimulator` + Crescendo/GOAT/PAIR red-team) | `EVAL-01` |
