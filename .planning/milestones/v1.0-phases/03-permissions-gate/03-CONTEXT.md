# Phase 3: Permissions Gate - Context

**Gathered:** 2026-09-25
**Status:** Ready for planning

## Phase Boundary

The agent moves from advisory review to enforced approval: a deny-first gate prompts before edits, shell, and network actions, with a standing TOML allow/deny policy file so routine actions stop prompting while dangerous ones stay gated. In scope: full-detail approval prompts, deny-wins TOML policy (repo-local override + home default), read-only pre-allows, single-prompt coordination with `/diff`, `python_repl` under the gate, policy-owned scope expansion, network pattern classification. Out of scope: general auto/yolo mode (Phase 4), persistent indexes, semantic risk classification.

## Implementation Decisions

### Approval prompt UX
- **D-01:** Every prompt shows full detail: the exact command or diff plus a one-line risk reason. Transparency over quietness.
- **D-02:** A deny skips the action and the agent continues the turn, explaining what it didn't do. No turn-abort on a single deny.
- **D-03:** After a deny, the prompt offers "always deny this", appending a standing rule to the policy file. Fast path from one-shot to standing rule.
- **D-04:** Repeated similar actions in one turn collapse into a single batch prompt listing each action.

### Policy file design
- **D-05:** TOML allow/deny lists (not natural-language policy — deterministic over flexible). — **Reversibility:** costly — the file format is a user-facing contract; changing it later needs a migration of existing policy files.
- **D-06:** Rules match on tool name plus path globs (file tools) or command prefixes (shell), so safe subcommands can be pre-allowed.
- **D-07:** On conflict, deny wins. Deny-first stays airtight.
- **D-08:** Repo `./.agent/policy.toml` overrides the home default (`~/.config` home file). Per-project rules travel with the repo. — **Reversibility:** costly — the lookup order is a behavioral contract users will depend on.

### Defaults & double-prompting
- **D-09:** Fresh install pre-allows reads (`read`, `search` never prompt). Everything that mutates (`write`, `edit`, `shell`, `python_repl`) prompts until policy says otherwise.
- **D-10:** Gate approval and `/diff` never double-prompt: one prompt total covers the write; `/diff` review remains available on demand but never re-asks for the same change.
- **D-11:** `python_repl` executions prompt under the gate with the code shown. This closes the Phase 2 documented bypass.
- **D-12:** Delegated (subagent) turns inherit the gate and prompt by default; "trust parent approval" is available as a policy config option for users who want quieter delegations.

### Scope expansion & network
- **D-13:** The policy file owns D-07 expansion: paths outside cwd+`/tmp` are denied unless an allow rule names them. Expansion is just another rule.
- **D-14:** Network actions are identified by pattern-matching shell commands (`curl`, `wget`, `ssh`, `git fetch`, etc.). Documented limitation: exotic binaries bypass classification.
- **D-15:** Read-only fetches (curl GET, git fetch) are pre-allowed; uploads and mutations prompt. Chosen for convenience over strictness (GET URLs can still exfiltrate via params — accepted).
- **D-16:** Pre-allowed fetches may hit any host. No host allowlist in this phase; a policy host restriction is a possible later tightening.

### the agent's Discretion
- Exact TOML schema (key names, rule fields, glob vs regex syntax).
- Prompt rendering shape (layout inside `output_context`, batch list format).
- Network command pattern list contents.
- Deny-skip agent messaging (how the agent phrases what it skipped).

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints
- `.planning/REQUIREMENTS.md` — TOOL-03 (this phase); all other REQ-IDs belong elsewhere
- `.planning/ROADMAP.md` — Phase 3 goal, success criteria, dependencies

### Prior phases (locked)
- `.planning/phases/01-session-wiring-repl-skeleton/01-CONTEXT.md` — harness-first, straight-to-REPL, `output_context` raw stdout, Bedrock-or-stop entry
- `.planning/phases/02-file-edit-shell-surface-diff/02-CONTEXT.md` — D-04/D-05 diff modes, D-06 full shell, D-07 scope (cwd+subdirs+`/tmp`), D-08/D-09 grep; general auto/yolo explicitly deferred
- `.planning/phases/02-file-edit-shell-surface-diff/02-RESEARCH.md` §4.2 — gate mechanism candidates (harness `interventions` vs wrapper tools vs SDK hooks); §6.2/§6.6 shell + `python_repl` bypass analysis
- `.planning/phases/02-file-edit-shell-surface-diff/02-SECURITY.md` — residual risks carried into this phase (shell/`python_repl` bypass T-02-03/T-02-04, shell timeout)

### Codebase orientation
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution layers
- `.planning/codebase/STACK.md` — `strands-agents` 1.57.0, `strands-harness` 0.1.2, `uv` toolchain, pytest gate
- `.planning/codebase/INTEGRATIONS.md` — no network layer in repo today; shell is the only wire path

## Existing Code Insights

### Reusable Assets
- `diff_gate.py` (`strands_code_cli/`): wrapper-tool gate with `ask` callable and sidecar pending state — the pattern the permissions gate extends to all tools
- `DiffConfig` (`strands_code_cli/diff_config.py`): ProviderConfig-shape persisted user choice (fail-soft load, symlink refusal, atomic save, platformdirs home) — template for policy file loading
- `scope.py` (`strands_code_cli/`): `resolve`+`confine` path guard — the enforcement point policy rules wrap
- `SessionIndex` (`strands_code_cli/session_index.py`): sidecar-JSON pattern for derived state

### Established Patterns
- Constructor-kwarg configuration: options arrive via constructors, not env sniffing
- Reply-only router actions: approval prompts live in the gate/turn layer, never as router replies
- All turn output flows through `output_context` raw stdout

### Integration Points
- `create_harness(interventions=...)` in `strands_code_cli/main.py:build_agent`: harness-native approval seam (ask/smart/policy-string) — presumed mechanism, planner confirms
- `dispatch` in `strands_code_cli/router.py`: policy-adjacent commands (if any) route here
- Subagent turns inherit tools + interventions (`agent.py:331-333`) — D-12 rides on this

## Specific Ideas

Claude Code's permission prompt UX (`Allow once / Allow always for this command / Deny`) is the reference model for D-01/D-03.

## Deferred Ideas

- Host allowlist for pre-allowed fetches — possible later tightening of D-16.
- Natural-language policy classification — rejected for now (nondeterministic); revisit if TOML proves too rigid.

---

*Phase: 3-Permissions Gate*
*Context gathered: 2026-09-25*
