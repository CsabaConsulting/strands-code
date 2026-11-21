# Phase 6: Skills + Memory File - Context

**Gathered:** 2026-10-04
**Status:** Ready for planning

## Phase Boundary

Users can list and invoke skills loaded from local `./.agent/skills` as slash commands with autocomplete, and keep persistent repo conventions in a dual memory file (root `STRANDS.md` + `./.agent/MEMORY.md`) that the CLI auto-loads, scaffolds via `/init` repo-scan drafts, and curates via a `/memory` approve/deny surface with NL revise rounds. In scope: slash-per-skill routing with namespace collisions resolved, skill autocomplete + `/skills` management command, dual-file memory contract with frontmatter + section markers, curate/silent memory modes, `/init` draft/merge-scan, external-edit auto-reload. Out of scope: skill marketplaces + install (SKILL-03, v2), MCP servers (SKILL-04, v2), Hindsight cross-session recall (SKILL-05, v2), hand-editing memory inside the CLI (rejected — NL instructions + external editor instead).

## Implementation Decisions

### Skill invocation UX
- **D-01:** Each local skill becomes a slash command (`/<name>`) routed through `router.py` dispatch as a reply-only action. Freeform trailing text is the skill's input (`/my-skill refactor the auth module`); no arg syntax to learn.
- **D-02:** On name collision, built-ins always win and the CLI warns at load that the skill is shadowed (`/model` can never be hijacked). Skills carry `source:name` colon namespaces (Claude Code style, prefixed by marketplace/owner); autocomplete matches on the bare skill name but completes the full namespaced form. — **Reversibility:** costly — the collision + namespace contract shapes router dispatch and user muscle memory; changing it re-opens slash routing.
- **D-03:** Discovery is slash autocomplete first, plus a `/skill` or `/skills` command (planner picks the name) for list/browse/examine and local uninstall (removing from `./.agent/skills`). Marketplace install/uninstall stays v2.
- **D-13:** Typed skill names get visible match confirmation (competitor-CLI style): when a typed `/<name>` matches a loaded skill, the CLI highlights/confirms the match at type time; a typo or unknown name shows no match, so the user can see the difference without accepting a completion. Exact rendering (inline highlight vs accept-echo) is agent's discretion.

### Memory file contract
- **D-04:** Dual file, both auto-loaded: root `STRANDS.md` (product-named for interop — other CLIs read root conventions files; generic `MEMORY.md` at root risks collision) plus `./.agent/MEMORY.md` (collision-safe inside our owned dir). On conflict, `.agent` wins. — **Reversibility:** costly — filenames are a user-facing contract; renaming later needs a migration of existing files.
- **D-05:** Frontmatter + markdown body. Root frontmatter holds file-level metadata (scope, version, updated-at); per-section freshness lives in HTML-comment markers (`<!-- updated: ... -->`) above sections — invisible when rendered, no sidecar state.
- **D-06:** `/memory` is a review/curation surface, never an editor. No hand-editing inside the CLI: memory changes come from harness auto-proposals, user NL instructions, or an external editor. External edits auto-reload via a per-turn mtime check with a transcript note — no manual reload signal.
- **D-07:** Two memory modes, session-sticky toggle (Phase 4 D-07 precedent): curate (every harness proposal prompts approve/deny) is the default per deny-first posture; silent auto-apply is the opt-in. Silent mode still logs writes to the transcript.
- **D-08:** Approve-with-edit runs NL revise rounds in MVP (Phase 4 D-04 pattern reuse, not a new invention): the user describes the change in words, the LLM returns revised memory quoted for review, and the user accepts, reverts to the previous version, or iterates. NL instructions are the only in-CLI edit path.

### /init scaffolding depth
- **D-09:** `/init` produces a repo-scan auto-draft, not a questionnaire or empty template. The draft arrives as proposals through the curate loop for approval.
- **D-10:** `/init` writes the full draft to `./.agent/MEMORY.md` and a thin summary + pointer to root `STRANDS.md`. Detail stays owned; interop stays useful.
- **D-11:** Re-running `/init` merge-scans: only missing/stale sections are drafted as new curate proposals. Never clobbers approved memory.
- **D-12:** Shallow scan by default (layout, README, configs, docs index) for a fast predictable first run; the user says "scan deeper" for source sampling, manifests, and test layout.

### the agent's Discretion
- `/skill` vs `/skills` command name and subcommand shape (list/browse/examine/uninstall).
- Autocomplete matching algorithm (fuzzy vs prefix) and PromptSession completer wiring.
- Skill file format details — researcher confirms the harness skill seam shape first.
- Exact frontmatter keys and scaffolded section list for the memory files.
- Mtime-check placement (loop turn boundary vs loader) and reload-note wording.
- Memory-mode toggle surface (`/memory mode` vs config key) and silent-mode log verbosity.
- Revise-loop prompt shape (how memory + instructions are quoted to the LLM).
- Scan source list for shallow vs deep passes.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints (harness-first; AWS-optional; no keys in repo)
- `.planning/REQUIREMENTS.md` — SKILL-01, SKILL-02 (this phase)
- `.planning/ROADMAP.md` — Phase 6 goal, success criteria, dependencies

### Prior phases (locked)
- `.planning/phases/05-model-cost-context-commands/05-CONTEXT.md` — reply-only router actions; router validates, loop applies; transcript-first UX
- `.planning/phases/04-plan-act-modes-steering/04-CONTEXT.md` — D-04 freeform revise rounds (reused by D-08); D-07 session-sticky modes (reused by D-07)
- `.planning/phases/03-permissions-gate/03-CONTEXT.md` — single-HITL gate spine; D-08 repo-overrides-home (precedent for D-04); D-02 deny-skips-and-continues (shape for curate denies)
- `.planning/phases/03-permissions-gate/03-SECURITY.md` — residual constraints on second handlers and scope widening

### Codebase orientation
- `.planning/codebase/STRUCTURE.md` — repo layout (note: maps predate `strands_code_cli/`; CLI layer orientation below)
- `.planning/codebase/STACK.md` — `strands-agents` 1.57.0, `strands-harness` 0.1.2, `uv` toolchain, pytest gate
- `.planning/codebase/CONVENTIONS.md` — constructor-kwarg config, never env sniffing; absolute imports; docstring contract
- `strands_code_cli/router.py` — `dispatch` tri-state; `/init`, `/memory`, `/skills`, and dynamic skill slashes route here
- `strands_code_cli/loop.py` — turn Machinery; mtime check and autocomplete provider attach here
- `strands_code_cli/main.py` — `build_agent`; harness skills + `memory={"stores": [...]}` wiring point
- `strands_code_cli/policy_gate.py` — approve/deny prompt UX precedent for the curate loop; `DiffConfig`-shape persisted choice precedent for the mode toggle

## Existing Code Insights

### Reusable Assets
- `router.py dispatch` tri-state (`strands_code_cli/`): new slashes + dynamic skill commands route here as reply actions
- Approval prompt UX (`strands_code_cli/policy_gate.py`): full-detail approve/deny with batch collapse — the curate loop mirrors it, no second handler
- `DiffConfig`/`ProviderConfig`-shape persisted choice (fail-soft load, atomic save, platformdirs home): template for the memory-mode toggle if it ever needs disk (default is in-memory session-sticky per D-07)
- `BatchState` turn-cache pattern (`strands_code_cli/policy_gate.py`): per-turn state precedent if proposal tracking needs it
- Choice dialog (`strands_code_cli/choice.py`): owned-keys radio control — available if `/skills` browse wants a picker, though autocomplete is primary
- `output_context` (`strands_code_cli/output.py`): all turn output including memory diffs and reload notes flows through it

### Established Patterns
- Constructor-kwarg configuration, never env sniffing
- Reply-only router actions; prompts and approvals live in the gate/turn layer
- Denials never cover; only approvals silence retries — curate denies follow the same fail-closed shape
- Transcript-first: silent-mode memory writes still log visibly
- Pair-atomic history ops; untrusted-marker summaries (Phase 5) — memory content re-entering context stays marked

### Integration Points
- `router.py dispatch`: `/init`, `/memory`, `/skills` branches + dynamic skill-slash registration + USAGE_HINT
- `main.py build_agent`: harness `skills` + `memory={"stores": [...]}` seam wiring; researcher confirms seam shape before hand-rolling anything
- `loop.py run_loop`: per-turn mtime check for external memory edits; PromptSession completer for skill autocomplete
- Harness memory loop: auto-proposal source for the curate surface; proposal trigger points confirmed in research

## Specific Ideas

- Claude Code's skill UX is the reference: `marketplace:skill` colon namespacing, name-matching autocomplete completing the full form, trailing-text skill input.
- Root conventions file named `STRANDS.md` for product identity + cross-CLI interop (MUSE.md is the de-facto standard being mirrored, not adopted verbatim).
- The NL revise loop deliberately reuses Phase 4 D-04 (freeform revise rounds) — one UX grammar across plans and memory.

## Deferred Ideas

- Skill marketplaces: add marketplace, install/list from marketplace (SKILL-03, v2).
- MCP servers as tools via user config (SKILL-04, v2).
- Hindsight cross-session recall behind the memory seam (SKILL-05, v2).
- Hand-editing memory inside the CLI — rejected, not deferred: NL instructions + external editor cover it.

---

*Phase: 6-Skills + Memory File*
*Context gathered: 2026-10-04*
