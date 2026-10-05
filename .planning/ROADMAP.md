# Roadmap: Strands Code

## Overview

From a bare library to a conversational coding CLI: first a resumable REPL skeleton wired to file-local sessions, then real actuation (file/shell tools plus `/diff`), gated immediately by deny-first permissions, then the Plan/Act + steering interaction model, followed by model/cost/context visibility, local skills plus the project memory file, the `/btw` subagent side channel, then decision-model routing and the opt-in CodeAct action interface as the v1 close (no GitHub loop phase: `gh` flows ride on general tool competence, as in Claude Code). Each phase lands as whole CLI modules over composed harness defaults — prevention (budgets, truncation, flush-on-exit, provenance) ships with the capability it protects, never as later polish.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Session Wiring + REPL Skeleton** - Resumable conversation loop over file-local sessions (completed 2026-09-24)
- [x] **Phase 2: File/Edit/Shell Surface + /diff** - Real agent actuation with change review (completed 2026-09-24)
- [x] **Phase 3: Permissions Gate** - Deny-first approval before every side effect (completed 2026-09-25)
- [x] **Phase 4: Plan/Act Modes + Steering** - Read-only plans, approval checkpoint, anytime steering, cancel (completed 2026-09-26)
- [x] **Phase 5: Model + Cost + Context Commands** - Provider switching, spend visibility, context controls (completed 2026-10-04)
- [ ] **Phase 6: Skills + Memory File** - Local skills loading and repo conventions file
- [ ] **Phase 7: Subagents + /btw Side Channel** - Side questions without disturbing the main task
- [ ] **Phase 8: Model Routing with Decision Models** - Per-ask model + thinking-budget selection, manual override kept
- [ ] **Phase 9: CodeAct Action Interface** - Opt-in code-generation-first action, tool-calling stays default

## Phase Details

### Phase 1: Session Wiring + REPL Skeleton

**Goal**: Users can hold a multi-ask conversation that survives restarts via session resume
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: LOOP-01, SES-01, SES-03
**Success Criteria** (what must be TRUE):

  1. User can type an ask, watch the agent work it with subagents and tools, and ask a follow-up in the same conversation
  2. User can resume a previous session by UUID (`--session-id`, `/resume`) and continue where they left off
  3. User can kill the CLI process and resume without silently losing conversation state

**Plans**: TBD

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md
- [x] 01-03-PLAN.md

### Phase 2: File/Edit/Shell Surface + /diff

**Goal**: The agent can act on real repos and users can review pending changes before they apply
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: TOOL-01, TOOL-02, TOOL-04
**Success Criteria** (what must be TRUE):

  1. User can ask the agent to read, write, edit files and run shell commands and see it done
  2. User can open a `/diff` viewer showing pending changes before they apply
  3. User can ask the agent to find code in an unfamiliar repo and get an answer grounded in grep/READ navigation, with no index to maintain

**Plans**: TBD
**UI hint**: yes

### Phase 3: Permissions Gate

**Goal**: Users are prompted for approval before edits, shell, and network actions under a deny-first policy
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: TOOL-03
**Success Criteria** (what must be TRUE):

  1. User is prompted to approve or deny before the agent edits files, runs shell commands, or touches the network
  2. User can encode standing allow/deny rules in a policy file so routine actions stop prompting while dangerous ones stay gated

**Plans**: TBD

### Phase 4: Plan/Act Modes + Steering

**Goal**: Users can plan read-only first, approve, then steer or cancel a running task without leaving the conversation
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: MODE-01, MODE-02, LOOP-02, LOOP-04
**Success Criteria** (what must be TRUE):

  1. User can work in Plan mode (read-only proposal), approve it, and watch Act execute it
  2. User can cycle between modes mid-session without restarting
  3. User can type freeform steering input mid-task and see it applied at the next tool-call boundary
  4. User can cancel a running task with Ctrl-C and stay in the CLI

**Plans**: TBD

### Phase 5: Model + Cost + Context Commands

**Goal**: Users can switch providers, see what a session costs, and manage context pressure
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: MODEL-01, MODEL-02, SES-02
**Success Criteria** (what must be TRUE):

  1. User can switch providers mid-session via `/model` (Bedrock default) and continue the same conversation
  2. User can see cost and token usage per session and task via `/cost` (display only)
  3. User can compact, clear, and inspect context usage (`/compact`, `/clear`, `/context`) without losing their place

**Plans**: TBD

### Phase 6: Skills + Memory File

**Goal**: Users can extend the CLI with local skills and persistent repo conventions
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: SKILL-01, SKILL-02
**Success Criteria** (what must be TRUE):

  1. User can list and invoke skills loaded from local `./.agent/skills`
  2. User can scaffold a repo memory file with `/init` and have the CLI auto-load it, editing it via `/memory`

**Plans**: 3/3 plans executed

Plans:
**Wave 1**

- [x] 06-01-PLAN.md — Skills spine: index, slash invocation, /skills, autocomplete

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — Memory file contract: dual-load injector, reload, modes

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-03-PLAN.md — Memory curation: curate loop, revise rounds, /init

### Phase 7: Subagents + /btw Side Channel

**Goal**: Users can ask side questions mid-task without disturbing the main task
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: LOOP-03
**Success Criteria** (what must be TRUE):

  1. User can ask a side question mid-task via a `/btw`-style escape and get an answer from a subagent
  2. User can see the main task continue untouched while the side question is answered

**Plans**: TBD

### Phase 8: Model Routing with Decision Models

**Goal**: The CLI picks the right model and thinking budget per ask via a cheap decision model, with manual override kept
**Mode:** mvp
**Depends on**: Phase 7 (sequencing; uses Phase 5 almanac: capabilities, live pricing/windows)
**Requirements**: MODEL-03
**Success Criteria** (what must be TRUE):

  1. Per ask, a decision model (Jev via API; Kev/Laya self-host path evaluated) selects the model and thinking budget from almanac candidates
  2. Deterministic heuristic fallback plus manual `/model` override when the decision call fails or is disabled
  3. Routing decisions are visible (which model, why, cost impact) in the turn transcript or `/cost`

**Plans**: TBD

### Phase 9: CodeAct Action Interface

**Goal**: Users can opt into code-generation-first actions where they beat gated tool-calling; tool-calling stays the default and CodeAct is never mandatory
**Mode:** mvp
**Depends on**: Phase 7 (sequencing; builds on Phase 2/3 tools)
**Requirements**: TOOL-07
**Success Criteria** (what must be TRUE):

  1. User can choose the action interface per session or task: traditional tool-calling (default), CodeAct, or both
  2. CodeAct executes code-first actions through the harness sandbox primitive with deny-first approvals still gating side effects (reconciled with no-prompt-inside-orchestration; Risk 9 currently disables it)
  3. Switching interfaces mid-session keeps history and approvals coherent

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Session Wiring + REPL Skeleton | 3/3 | Complete    | 2026-09-24 |
| 2. File/Edit/Shell Surface + /diff | 1/1 | Complete    | 2026-09-24 |
| 3. Permissions Gate | 1/1 | Complete    | 2026-09-25 |
| 4. Plan/Act Modes + Steering | 1/1 | Complete    | 2026-09-26 |
| 5. Model + Cost + Context Commands | 1/1 | Complete    | 2026-10-04 |
| 6. Skills + Memory File | 3/3 | In Progress|  |
| 7. Subagents + /btw Side Channel | 0/TBD | Not started | - |
| 8. Model Routing with Decision Models | 0/TBD | Not started | - |
| 9. CodeAct Action Interface | 0/TBD | Not started | - |
