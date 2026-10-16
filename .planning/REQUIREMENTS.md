# Requirements: Strands Code

**Defined:** 2026-09-22
**Core Value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

## v1 Requirements

### Task Loop

- [x] **LOOP-01**: User can hold a multi-ask conversation where the CLI plans and executes each ask with subagents and tools
- [x] **LOOP-02**: User can steer a running task with freeform input applied at the next tool-call boundary
- [x] **LOOP-03**: User can ask a side question mid-task via a `/btw`-style escape answered by a subagent without disturbing the main task
- [x] **LOOP-04**: User can cancel a running task with Ctrl-C without quitting the CLI

### Modes

- [x] **MODE-01**: User can work in Plan mode (read-only, presents a plan) and approve before Act executes
- [x] **MODE-02**: User can cycle modes without restarting the session

### Tools & Safety

- [x] **TOOL-01**: Agent can read, write, and edit files and run shell commands as first-class tools
- [x] **TOOL-02**: User can review pending changes in a `/diff` viewer before they apply
- [x] **TOOL-03**: User is prompted for approval before edits, shell, and network actions per a deny-first policy file
- [x] **TOOL-04**: Agent navigates repos with agentic grep/READ without an index to maintain
- [ ] **TOOL-07**: User can opt into code-generation-first (CodeAct) actions reconciled with deny-first approvals; tool-calling stays the default and CodeAct is never mandatory

### Session & Context

- [x] **SES-01**: User can resume a session by UUID across runs (`--session-id`, `/resume`)
- [x] **SES-02**: User can compact, clear, and inspect context usage (`/compact`, `/clear`, `/context`)
- [x] **SES-03**: Sessions flush on exit so resume never silently loses work

### Models & Cost

- [x] **MODEL-01**: User can switch providers mid-session via `/model` (Bedrock default, override-friendly)
- [x] **MODEL-02**: User can see cost and token usage per session and task via `/cost` (display only, no enforcement)
- [x] **MODEL-03**: CLI auto-selects model and thinking budget per ask via a decision model (Jev/Kev/Laya class), with manual override
- [x] **MODEL-04**: CLI can route decisions through Jev via TypeSafe's native API (`TYPESAFE_API_KEY`), alongside OpenRouter and Ollama engines
- [ ] **MODEL-05**: `/cost` shows provider-reported actuals for main turns where supplied (OpenRouter), estimates elsewhere, without double counting

### Skills & Memory

- [x] **SKILL-01**: CLI loads skills from local `./.agent/skills` and the user can list and invoke them
- [x] **SKILL-02**: CLI auto-loads the repo memory file and the user can scaffold and edit it (`/init`, `/memory`)

## v2 Requirements

### GitHub (no dedicated loop phase: Claude Code has none either — `gh` flows ride on general tool competence, verifiable today)

- **GITHUB-01**: (covered, no build) User can drive read-issue → branch → implement → test → open-PR from a single ask via shell tool + `gh`
- **GITHUB-02**: (covered, no build) User can create issues, comment on reviews, and check CI status from the CLI via shell tool + `gh`
- **REVIEW-01**: User can request a code review of pending changes via a small future `/review` slash

### Extensibility

- **SKILL-03**: User can add marketplaces and install skills from them (after local skills proven)
- **SKILL-04**: CLI consumes MCP servers as tools via user config (on first integration request)

### Automation

- **LOOP-05**: User can run the CLI non-interactively with JSON output for CI and scripts (on first CI user)

### Memory

- **SKILL-05**: No Hindsight integration ships in the repo; heavy recall backends are explicitly out of scope (Hindsight's Postgres + background loop too heavy for a coding harness; OpenViking's AGPL server rejected) — Strands native memory stays the only backend

### Interaction

- **TOOL-05**: User can attach files and symbols with an `@`-triggered picker (typing filters, up/down navigates, tab selects); start simple, sophistication only if a later phase calls for it
- **TOOL-06**: User can export trimmed session content to a text file via `/copy` (trailing whitespace stripped, optional back-scroll limit)
- **MODE-03**: User can pick fast/thorough effort presets layered over Plan/Act (on demand)
- **REVIEW-02**: User can run review flows with modes, locally and in CI through the headless runner

### Structure & Hygiene

- **STRUCT-01**: Codebase passes a measurement-first structural review: complexity and coupling measured, oversized modules broken up, CLI organized into packages, rig split into per-area files — full suite and rig green throughout
- **CLEANUP-01**: Repo contains no dead example code; README references only shipped surfaces (examples/pdf_to_okf_bundle removed)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Persistent semantic code index | A project of its own; grep-first suffices for v1, index gets its own later phase |
| Enforced token budgets | Display builds trust; halting mid-task is a policy decision for later |
| Fully automatic model routing with no override | Opacity violates the manual-control constraint; Phase 8 keeps manual switching + explicit override, routing proposes but never silently decides |
| AgentCore as required path | Couples the CLI to AWS control plane; breaks the offline default (AWS-optional constraint) |
| IDE extension / browser companion | Separate product surface; terminal picker covers the need |
| Auto-commit / auto-push | Silent mutation of shared history conflicts with deny-first posture |
| Real-time multi-user collaboration | Session identity and presence are a second product; one actor per session |
| Custom vector DB / bespoke memory | Duplicates tested upstream `MemoryManager` defaults; tiered adapters instead |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LOOP-01 | Phase 1 | Complete |
| LOOP-02 | Phase 4 | Complete |
| LOOP-03 | Phase 7 | Complete |
| LOOP-04 | Phase 4 | Complete |
| MODE-01 | Phase 4 | Complete |
| MODE-02 | Phase 4 | Complete |
| TOOL-01 | Phase 2 | Complete |
| TOOL-02 | Phase 2 | Complete |
| TOOL-03 | Phase 3 | Complete |
| TOOL-04 | Phase 2 | Complete |
| SES-01 | Phase 1 | Complete |
| SES-02 | Phase 5 | Complete |
| SES-03 | Phase 1 | Complete |
| MODEL-01 | Phase 5 | Complete |
| MODEL-02 | Phase 5 | Complete |
| SKILL-01 | Phase 6 | Complete |
| SKILL-02 | Phase 6 | Complete |
| TOOL-07 | Phase 11 | Complete |
| MODEL-03 | Phase 8 | Complete |
| MODEL-04 | Phase 9 | Complete |
| MODEL-05 | Phase 10 | Complete |
| SKILL-05 | Phase 12 | Pending |
| STRUCT-01 | Phase 13 | Pending |
| CLEANUP-01 | Phase 13 | Pending |
| GITHUB-01 | Covered (no phase) | General tool competence + `gh`, verifiable today |
| GITHUB-02 | Covered (no phase) | General tool competence + `gh`, verifiable today |
| REVIEW-01 | Deferred (v2) | Small future `/review` slash |

**Coverage:**

- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-22*
*Last updated: 2026-10-11 (LOOP-03 marked complete pre-transition)*
