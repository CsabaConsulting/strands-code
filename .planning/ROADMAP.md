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
- [x] **Phase 6: Skills + Memory File** - Local skills loading and repo conventions file (completed 2026-10-04)
- [x] **Phase 7: Subagents + /btw Side Channel** - Side questions without disturbing the main task (completed 2026-10-11)
- [x] **Phase 8: Model Routing with Decision Models** - Per-ask model + thinking-budget selection, manual override kept (completed 2026-10-12)
- [x] **Phase 9: Native TypeSafe Decision Engine** - Direct Jev API alongside OpenRouter and Ollama engines (completed 2026-10-12)
- [x] **Phase 10: Provider-Reported Turn Spend** - OpenRouter actuals for main turns instead of catalog estimates
- [x] **Phase 11: CodeAct Action Interface** - Opt-in code-generation-first action, tool-calling stays default (completed 2026-10-16)
- [ ] **Phase 12: Structural Review + Hygiene** - Measurement-first breakup (CLI packages, rig files), dead example removal

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

**Plans**: 3/3 plans executed

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

**Plans**: 1/1 plans executed

Plans:

- [x] 02-PLAN.md

**UI hint**: yes

### Phase 3: Permissions Gate

**Goal**: Users are prompted for approval before edits, shell, and network actions under a deny-first policy
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: TOOL-03
**Success Criteria** (what must be TRUE):

  1. User is prompted to approve or deny before the agent edits files, runs shell commands, or touches the network
  2. User can encode standing allow/deny rules in a policy file so routine actions stop prompting while dangerous ones stay gated

**Plans**: 1/1 plans executed

Plans:

- [x] 03-PLAN.md

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

**Plans**: 1/1 plans executed

Plans:

- [x] 04-PLAN.md

### Phase 5: Model + Cost + Context Commands

**Goal**: Users can switch providers, see what a session costs, and manage context pressure
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: MODEL-01, MODEL-02, SES-02
**Success Criteria** (what must be TRUE):

  1. User can switch providers mid-session via `/model` (Bedrock default) and continue the same conversation
  2. User can see cost and token usage per session and task via `/cost` (display only)
  3. User can compact, clear, and inspect context usage (`/compact`, `/clear`, `/context`) without losing their place

**Plans**: 1/1 plans executed

Plans:

- [x] 05-PLAN.md

### Phase 6: Skills + Memory File

**Goal**: Users can extend the CLI with local skills and persistent repo conventions
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: SKILL-01, SKILL-02
**Success Criteria** (what must be TRUE):

  1. User can list and invoke skills loaded from local `./.agent/skills`
  2. User can scaffold a repo memory file with `/init` and have the CLI auto-load it, editing it via `/memory`

**Plans**: 4/4 plans executed

Plans:

- [x] 06-04-PLAN.md

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

**Plans**: 5 plans

Plans:
**Wave 1**

- [x] 07-01-PLAN.md — Tracer: parallel /btw side answer fenced while main continues, plus idle dispatch and cost merge

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md — Shared-gate parallel correctness: tagged prompts, namespaced batch, per-request cancel, Ctrl-C chooser

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md — Side-question queue plus outliving-main idle lifecycle

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 07-04-PLAN.md — Gap closure: nesting-safe pump, scoped side prompt, clean cancel-in-flight, dialog attribution

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 07-05-PLAN.md — Round-2 gap closure: multiplexed idle prompt (E), exit-drop note, reentrant stdin guard plus typeahead hygiene

### Phase 8: Model Routing with Decision Models

**Goal**: The CLI picks the right model and thinking budget per ask via a cheap decision model, with manual override kept
**Mode:** mvp
**Depends on**: Phase 7 (sequencing; uses Phase 5 almanac: capabilities, live pricing/windows)
**Requirements**: MODEL-03
**Success Criteria** (what must be TRUE):

  1. Per ask, a decision model (Jev via API; Kev/Laya self-host path evaluated) selects the model and thinking budget from almanac candidates
  2. Deterministic heuristic fallback plus manual `/model` override when the decision call fails or is disabled
  3. Routing decisions are visible (which model, why, cost impact) in the turn transcript or `/cost`

**Plans**: 7/7 plans executed (Decision-API rework; prior chat-JSON plans archived; 08-07 UAT gap closure complete)

Plans:
**Wave 1**

- [x] 08-01-PLAN.md — Tracer: Decision-API transports plus gate plus hook plus /cost entry, model-choice end to end

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — Effort call-2 plus fast-path rewrite plus both confidences plus side-ask parity

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-03-PLAN.md — Local preflight plus retry matrix plus offline pause plus body guards

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 08-04-PLAN.md — Split-catalog setup plus validate plus docs plus uattest r1-r4

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 08-05-PLAN.md — Probe runner plus calibration plus live engine tests

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 08-06-PLAN.md — Gap closure: YAML-bool levels fix plus choice str-guard plus lazy probe tag (gap_closure)

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 08-07-PLAN.md — UAT gap closure: rig us. profile ids plus fail-fast plus persistence fence (gap_closure, G-08-1)

### Phase 9: Native TypeSafe Decision Engine

**Goal**: Routing can use Jev via TypeSafe's native API directly, alongside the OpenRouter and Ollama engines
**Mode:** mvp
**Depends on**: Phase 8 (engine chain, strategy, calibration)
**Requirements**: MODEL-04
**Success Criteria** (what must be TRUE):

  1. User with a `TYPESAFE_API_KEY` can select the native TypeSafe engine in `/route setup` and validate it
  2. Native-engine decisions return the same verdict shape (answers, confidences, reported spend) as the other engines
  3. Engine chain, preflight, retry, and calibration cover the native engine like the others

**Plans**: TBD (not yet planned)

- [x] 09-01-PLAN.md
- [x] 09-02-PLAN.md
- [x] 09-03-PLAN.md

### Phase 10: Provider-Reported Turn Spend

**Goal**: `/cost` shows provider-reported actuals for main turns where the provider supplies them, estimates elsewhere
**Mode:** mvp
**Depends on**: Phase 5 (cost display), Phase 8 (reported-spend pattern)
**Requirements**: MODEL-05
**Success Criteria** (what must be TRUE):

  1. Main turns served via OpenRouter show the provider-reported USD cost in the usage line and `/cost`
  2. Bedrock and offline turns keep the tokens × rate estimate with provenance labeled
  3. Mixed sessions total actuals and estimates without double counting

**Plans**: TBD (not yet planned)

- [x] 10-04-PLAN.md

- [x] 10-01-PLAN.md
- [x] 10-02-PLAN.md
- [x] 10-03-PLAN.md
- [x] 10-05-PLAN.md

### Phase 11: CodeAct Action Interface

**Goal**: Users can opt into code-generation-first actions where they beat gated tool-calling; tool-calling stays the default and CodeAct is never mandatory
**Mode:** mvp
**Depends on**: Phase 7 (sequencing; builds on Phase 2/3 tools)
**Requirements**: TOOL-07
**Success Criteria** (what must be TRUE):

  1. User can choose the action interface per session or task: traditional tool-calling (default), CodeAct, or both
  2. CodeAct executes code-first actions through the harness sandbox primitive with deny-first approvals still gating side effects (reconciled with no-prompt-inside-orchestration; Risk 9 currently disables it)
  3. Switching interfaces mid-session keeps history and approvals coherent

**Plans**:

**Wave 1**

- [x] 11-01-PLAN.md — Tracer: toggle plus shaped code turn end to end

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 11-02-PLAN.md — Stint execution plus both-mode routing

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 11-03-PLAN.md — Whole-block approval plus coherence pins

**Wave 4** *(gap closure, blocked on Wave 1 completion)*

- [x] 11-04-PLAN.md — Bare --codeact implies code (G-11-1)

### Phase 12: Structural Review + Hygiene

**Goal**: Codebase passes a measurement-first structural review and sheds dead example code
**Depends on**: Phase 11 (last feature phase; review covers the whole tree)
**Requirements**: STRUCT-01, CLEANUP-01
**Success Criteria** (what must be TRUE):

  1. Cyclomatic complexity and module coupling are measured and reported; breakup decisions cite the numbers
  2. Oversized modules (loop, routing, router) are broken into coherent packages; the uattest driver is split into helpers plus per-area scenario files
  3. examples/pdf_to_okf_bundle is removed and the README references only shipped surfaces; full suite and rig stay green throughout

**Plans**: 6/6 plans executed

Plans:
**Wave 1**

- [x] 12-01-PLAN.md — Tracer: tooling plus cleanup plus format plus measurement report

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 12-02-PLAN.md — Repackage door checkpoint plus loop-area breakup

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 12-03-PLAN.md — Remaining moves plus test mirror plus tree-wide gates green

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 12-04-PLAN.md — Rig split: shared lib plus per-area scenarios plus mirrored contract tests

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 12-05-PLAN.md — README plus instruction refresh plus blocking gates plus final green proof

**Wave 6** *(gap closure, blocked on Wave 5 completion)*

- [x] 12-06-PLAN.md — Stale-block sweep: AGENTS.md + CONVENTIONS.md re-sync (G-12-1)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Session Wiring + REPL Skeleton | 3/3 | Complete    | 2026-09-24 |
| 2. File/Edit/Shell Surface + /diff | 1/1 | Complete    | 2026-09-24 |
| 3. Permissions Gate | 1/1 | Complete    | 2026-09-25 |
| 4. Plan/Act Modes + Steering | 1/1 | Complete    | 2026-09-26 |
| 5. Model + Cost + Context Commands | 1/1 | Complete    | 2026-10-04 |
| 6. Skills + Memory File | 4/4 | Complete    | 2026-10-04 |
| 7. Subagents + /btw Side Channel | 5/5 | Complete    | 2026-10-11 |
| 8. Model Routing with Decision Models | 7/7 | Complete | 2026-10-12 |
| 9. Native TypeSafe Decision Engine | 3/3 | Complete | 2026-10-12 |
| 10. Provider-Reported Turn Spend | 5/5 | Complete | 2026-10-13 |
| 11. CodeAct Action Interface | 4/4 | Complete | 2026-10-16 |
| 12. Structural Review + Hygiene | 6/6 | In Progress|  |

## Future (post-v1)

- [ ] **Sandbox floor: Strands Box + Dogwood** - Run the CLI inside Strands Box as a
  non-overridable enforcement floor under the HITL approval dialogs (defense in
  depth: policy denies what policy forbids even on a misclicked "Always").
  Blocked on Box Linux support (macOS-only dev preview as of 2026-10-10);
  adopting Dogwood revisits locked decision D-05 ("never Cedar").
  First step: spike `box run strands-code` with an allowlist-mirroring policy and
  compare Box verdicts against gate decisions. Full evaluation + rejected
  alternatives (MXC watch, Dogwood-standalone no-go):
  `.planning/research/SANDBOX.md`.
- [ ] **Semantic policy: Dogwood (standalone or via Box)** - Temporal policy rules
  the stateless TOML allowlist cannot express (precedence, time windows, spend
  caps), evaluated in the Dogwood Local Engine. Approved in principle 2026-10-10
  including a revisit of locked decision D-05 ("never Cedar"): Dogwood-deterministic
  is not NL-string policy, but the letter stands until re-decided. Prefer adoption
  via Box (shared engine + event history); standalone Local Engine only if Box
  Linux slips badly.
