# Roadmaps & Milestones

## Milestones

- ✅ **v1.0 Conversational Coding CLI** — Phases 1–12 (shipped 2026-10-16) — [Archive](milestones/v1.0-ROADMAP.md)

---

## Future (v2 Candidates — Explored 2026-11-20)

Full alignment brief and phase breakdown: `.planning/research/V2-ALIGNMENT.md` (run `/gsd-new-milestone` to promote into v2).

- [ ] **Upstream SDK/Harness resync & shim retirement** - Bump `strands-agents >=1.65` and `strands-harness >=0.4`, retiring upstream-fixed shims (`#5166` cross-family reasoning strip on restore, `#5158` `ContextInjector` OpenAI/LiteLLM adjacency, `#4853`/`#5159` Nova 2 + Haiku 5.5 thinking), auditing `harness-py v0.4.0` `todos` removal + `Agent.cancel()`, and opening targeted upstream PRs only as direct byproducts of our upgrade (including optional `aws-samples/sample-strands-code-agent` dep sync).
- [ ] **First-class Google Gemini (`google/`) + provider-aware startup** - Add `gemini` extra (`strands-agents[gemini]` / `google-genai`), replace `Bedrock-or-stop` STS gate with provider-aware credential preflight, unblock `google/` in `supports_reasoning()` + `/model` discovery + `/cost`, and document using personal Google AI Ultra monthly credits ($40–$100/mo) with a standard AI Studio API key.
- [ ] **Decision routing convergence (`DecisionModel`)** - Migrate custom Decision-API transports in `strands_code_cli/routing/` onto upstream `strands.decisions.DecisionModel` (`TypeSafeDecisionModel`, `DecisionsAPIDecisionModel`, `LLMDecisionModel`) + `ClassifierStrategy` while preserving calibrated `0.62`/`0.04` gating, `/route` UX, and `/cost` reporting.
- [ ] **Sandbox floor: Strands Box + Dogwood (Linux landed 2026-11)** - Linux support (`Landlock` + namespaces + Bubblewrap `bwrap`) cleared the Oct 2026 blocker. Spike `box run strands-code` (`box.toml` + deterministic Dogwood `policy.dw` + out-of-band credential egress proxy) as a non-overridable floor beneath our HITL dialogs for both `shell` and `python_repl`; formally revisit locked decision D-05 ("never Cedar") for deterministic Dogwood. Full evaluation: `.planning/research/SANDBOX.md`.
- [ ] **Strands Evals + selective CLI ergonomics** - Add a `strands-agents-evals` suite (`TrajectoryEvaluator`, `ActorSimulator`, prompt-injection red-teaming on skills/memory) alongside `scripts/uattest/`, plus `/help`, `@file` / `/file` picker (`TOOL-05`), and `/review` (`REVIEW-01`).
