# Requirements: Strands Code

**Defined:** 2026-09-22
**Core Value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

## v1 Requirements

### Task Loop

- [x] **LOOP-01**: User can hold a multi-ask conversation where the CLI plans and executes each ask with subagents and tools
- [ ] **LOOP-02**: User can steer a running task with freeform input applied at the next tool-call boundary
- [ ] **LOOP-03**: User can ask a side question mid-task via a `/btw`-style escape answered by a subagent without disturbing the main task
- [ ] **LOOP-04**: User can cancel a running task with Ctrl-C without quitting the CLI

### Modes

- [ ] **MODE-01**: User can work in Plan mode (read-only, presents a plan) and approve before Act executes
- [ ] **MODE-02**: User can cycle modes without restarting the session

### Tools & Safety

- [ ] **TOOL-01**: Agent can read, write, and edit files and run shell commands as first-class tools
- [ ] **TOOL-02**: User can review pending changes in a `/diff` viewer before they apply
- [ ] **TOOL-03**: User is prompted for approval before edits, shell, and network actions per a deny-first policy file
- [ ] **TOOL-04**: Agent navigates repos with agentic grep/READ without an index to maintain

### Session & Context

- [x] **SES-01**: User can resume a session by UUID across runs (`--session-id`, `/resume`)
- [ ] **SES-02**: User can compact, clear, and inspect context usage (`/compact`, `/clear`, `/context`)
- [x] **SES-03**: Sessions flush on exit so resume never silently loses work

### Models & Cost

- [ ] **MODEL-01**: User can switch providers mid-session via `/model` (Bedrock default, override-friendly)
- [ ] **MODEL-02**: User can see cost and token usage per session and task via `/cost` (display only, no enforcement)

### Skills & Memory

- [ ] **SKILL-01**: CLI loads skills from local `./.agent/skills` and the user can list and invoke them
- [ ] **SKILL-02**: CLI auto-loads the repo memory file and the user can scaffold and edit it (`/init`, `/memory`)

### GitHub

- [ ] **GITHUB-01**: User can drive read-issue → branch → implement → test → open-PR from a single ask
- [ ] **GITHUB-02**: User can create issues, comment on reviews, and check CI status from the CLI

### Review

- [ ] **REVIEW-01**: User can request a code review of pending changes via `/review`

## v2 Requirements

### Extensibility

- **SKILL-03**: User can add marketplaces and install skills from them (after local skills proven)
- **SKILL-04**: CLI consumes MCP servers as tools via user config (on first integration request)

### Automation

- **LOOP-05**: User can run the CLI non-interactively with JSON output for CI and scripts (on first CI user)

### Memory

- **SKILL-05**: User can opt into Hindsight cross-session recall behind the same memory seam (on team demand)

### Interaction

- **TOOL-05**: User can attach files and symbols with an `@`-triggered picker (typing filters, up/down navigates, tab selects); start simple, sophistication only if a later phase calls for it
- **TOOL-06**: User can export trimmed session content to a text file via `/copy` (trailing whitespace stripped, optional back-scroll limit)
- **MODE-03**: User can pick fast/thorough effort presets layered over Plan/Act (on demand)
- **REVIEW-02**: User can run review flows with modes, locally and in CI through the headless runner

## Out of Scope

| Feature | Reason |
|---------|--------|
| Persistent semantic code index | A project of its own; grep-first suffices for v1, index gets its own later phase |
| Enforced token budgets | Display builds trust; halting mid-task is a policy decision for later |
| Auto model/effort routing | Opaque and provider-coupled while the harness moves fast; manual first |
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
| LOOP-02 | Phase 4 | Pending |
| LOOP-03 | Phase 7 | Pending |
| LOOP-04 | Phase 4 | Pending |
| MODE-01 | Phase 4 | Pending |
| MODE-02 | Phase 4 | Pending |
| TOOL-01 | Phase 2 | Pending |
| TOOL-02 | Phase 2 | Pending |
| TOOL-03 | Phase 3 | Pending |
| TOOL-04 | Phase 2 | Pending |
| SES-01 | Phase 1 | Complete |
| SES-02 | Phase 5 | Pending |
| SES-03 | Phase 1 | Complete |
| MODEL-01 | Phase 5 | Pending |
| MODEL-02 | Phase 5 | Pending |
| SKILL-01 | Phase 6 | Pending |
| SKILL-02 | Phase 6 | Pending |
| GITHUB-01 | Phase 8 | Pending |
| GITHUB-02 | Phase 8 | Pending |
| REVIEW-01 | Phase 8 | Pending |

**Coverage:**

- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-22*
*Last updated: 2026-09-22 after initial definition*
