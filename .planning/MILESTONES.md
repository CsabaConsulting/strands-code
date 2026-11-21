# Milestones

## v1.0 — Conversational Coding CLI

- **Status:** Shipped 2026-10-16 · Archived 2026-11-21
- **Git tag:** `v1.0`
- **Git range:** `4a23ae2..faecd77` (517 commits above `upstream/main`; 370 files changed, `+90,802` / `-1,162` lines)
- **Scope:** 12 phases, 41 plans, 129 tasks, 40,840 Python LOC across `strands_code_cli`, `tests`, and `scripts`, 1,549 automated tests
- **Timeline:** 2026-09-22 → 2026-10-16 (initial build retrospective: `docs/initial_build/RETROSPECTIVE.md`, $25.39 total build spend across 2.27B tokens at 91.6% prompt-cache hit rate)
- **Archives:**
  - [v1.0 Roadmap](milestones/v1.0-ROADMAP.md)
  - [v1.0 Requirements](milestones/v1.0-REQUIREMENTS.md)

### Key Accomplishments

1. **Resumable Coding REPL & Diff-Gated Tooling (Phases 1–2):** File-local `./.agent/sessions` (`--session-id`, `/resume`, `/rename`, `/forget`), grep-first `/search`, and diff-gated `write`/`edit` with `/diff` review.
2. **Deny-First Approval Gate, Plan/Act & Anytime Steering (Phases 3–4):** Main-thread `ApprovalBroker` with standing TOML `/policy` rules, session-sticky Plan → `/approve` → Act (`/mode`), tool-boundary steering, and clean Ctrl-C turn cancellation.
3. **Multi-Provider `/model`, `/cost` Actuals+Estimates & Context Controls (Phases 5 & 10):** Idle-safe `/model` switching with `[Thinking trace]` history conversion, OpenRouter actuals + catalog estimates in `/cost`, and pair-atomic `/compact`, `/clear`, `/context` (80% auto-compact).
4. **Local Skills & Curated Dual-File Memory (Phase 6):** Live-reloadable `./.agent/skills` slash invocation (`/skills`) plus dual `STRANDS.md` + `.agent/MEMORY.md` auto-load with `/init` drafting and `/memory` NL curate/revise loops.
5. **Parallel `/btw` Side Channel & Calibrated Decision Routing (Phases 7–9):** Concurrent `/btw` subagent answers under shared `[main]`/`[btw]` approvals, plus per-ask model + effort routing (`/route`) across OpenRouter, Ollama, and Native TypeSafe Jev (`0.62`/`0.04` probe-calibrated gate).
6. **Opt-In CodeAct & Gated 10-Package Architecture (Phases 11–12):** `--codeact` / `/codeact` (`tool|code|both`) with whole-block syntax approvals, backed by a 10-package breakup enforced in CI by `ruff`, `xenon --max-absolute C`, `import-linter`, and 1,549 tests.
