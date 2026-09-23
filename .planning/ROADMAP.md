# Roadmap: Strands Code

## Overview

From a bare library to a conversational coding CLI: first a resumable REPL skeleton wired to file-local sessions, then real actuation (file/shell tools plus `/diff`), gated immediately by deny-first permissions, then the Plan/Act + steering interaction model, followed by model/cost/context visibility, local skills plus the project memory file, the `/btw` subagent side channel, and finally the GitHub loop with `/review` closed against the Claude Code parity checklist. Each phase lands as whole CLI modules over composed harness defaults — prevention (budgets, truncation, flush-on-exit, provenance) ships with the capability it protects, never as later polish.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Session Wiring + REPL Skeleton** - Resumable conversation loop over file-local sessions
- [ ] **Phase 2: File/Edit/Shell Surface + /diff** - Real agent actuation with change review
- [ ] **Phase 3: Permissions Gate** - Deny-first approval before every side effect
- [ ] **Phase 4: Plan/Act Modes + Steering** - Read-only plans, approval checkpoint, anytime steering, cancel
- [ ] **Phase 5: Model + Cost + Context Commands** - Provider switching, spend visibility, context controls
- [ ] **Phase 6: Skills + Memory File** - Local skills loading and repo conventions file
- [ ] **Phase 7: Subagents + /btw Side Channel** - Side questions without disturbing the main task
- [ ] **Phase 8: GitHub Loop + Review + Parity** - Single ask from issue to open PR, reviewed against parity bar

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
**Plans**: TBD

### Phase 7: Subagents + /btw Side Channel
**Goal**: Users can ask side questions mid-task without disturbing the main task
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: LOOP-03
**Success Criteria** (what must be TRUE):
  1. User can ask a side question mid-task via a `/btw`-style escape and get an answer from a subagent
  2. User can see the main task continue untouched while the side question is answered
**Plans**: TBD

### Phase 8: GitHub Loop + Review + Parity
**Goal**: A single ask drives read-issue, branch, implement, test, open-PR, and the v1 bar is the parity checklist
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: GITHUB-01, GITHUB-02, REVIEW-01
**Success Criteria** (what must be TRUE):
  1. User can go from a GitHub issue to an open PR (branch, implement, test) from a single ask
  2. User can create issues, comment on reviews, and check CI status from the CLI
  3. User can request a code review of pending changes via `/review`
  4. The CLI satisfies the Claude Code parity checklist as the v1 acceptance bar
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Session Wiring + REPL Skeleton | 0/TBD | Not started | - |
| 2. File/Edit/Shell Surface + /diff | 0/TBD | Not started | - |
| 3. Permissions Gate | 0/TBD | Not started | - |
| 4. Plan/Act Modes + Steering | 0/TBD | Not started | - |
| 5. Model + Cost + Context Commands | 0/TBD | Not started | - |
| 6. Skills + Memory File | 0/TBD | Not started | - |
| 7. Subagents + /btw Side Channel | 0/TBD | Not started | - |
| 8. GitHub Loop + Review + Parity | 0/TBD | Not started | - |
