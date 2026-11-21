# Walking Skeleton — Strands Code

**Phase:** 1 (Session Wiring + REPL Skeleton)
**Generated:** 2026-09-24

## Capability Proven End-to-End

A user runs `strands-code`, types an ask, gets a streamed agent answer, exits, and resumes the same conversation with full transcript state on the next launch.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent factory | strands-harness `create_harness()` only, never bare `Agent`/`CodeAgent` | Harness-first project direction; snapshot session wiring comes free |
| Session persistence | SDK `SnapshotSessionManager` via `session={"id"}` (project-local `./.agent/sessions`) | Whole-agent atomic blobs, per-message saves, restore-on-init; no custom format |
| Session identity | Fresh `str(uuid.uuid4())` per session; `--session-id` resume; picker on launch | D-02/D-03; harness sanitizer passes UUIDs through unchanged |
| Session titles | CLI-owned sidecar JSON index `{id → title/created_at/updated_at}` | Snapshot blobs are SDK-owned schema with no title field |
| REPL | prompt_toolkit `PromptSession` + `FileHistory`, synchronous turn with prompt suspended | Standard component; anytime-steering is Phase 4 scope |
| Entry | Typer app, no subcommands in Phase 1 | Type-hint-driven help; `CliRunner` smoke tests |
| Provider config | YAML via owned PyYAML under platformdirs user config dir | D-06; config feeds constructors, never env sniffing |
| First-run gate | Preflight credential probe before construction; stop-with-pointer, non-zero exit | D-05; SDK failure would otherwise surface deep in first invoke |
| Rendering | Existing `CodeAgentCallbackHandler` (Rich) reused as the only renderer | AGENTS.md: Rich only in callback-handler/REPL-render path |
| Directory layout | New `strands_code_cli/` package; library stays CLI-dep-free | Library importable without CLI deps per project constraint |

## Stack Touched in Phase 1

- [ ] Project scaffold (`strands_code_cli/` package, `strands-code` console script, `typer`/`prompt-toolkit`/`platformdirs` via `uv add`)
- [ ] Routing — leading-`/` dispatch stub (`/resume` `/rename` `/exit`)
- [ ] Database — N/A (no DB in this project; persistence analog is snapshot sessions: at least one real write AND one real cross-process read/restore)
- [ ] UI — REPL prompt wired to a real `create_harness` agent turn with streamed Rich output
- [ ] Deployment — N/A (no server; dev-run analog is `uv run strands-code` exercising the full loop locally)

## Out of Scope (Deferred to Later Slices)

- Real actuation beyond the harness-composed `python_repl` turn (Phase 2 owns file/edit/shell surface + `/diff`)
- Permissions/approval gating (Phase 3)
- Plan/Act modes, steering, Ctrl-C cancel of a running turn (Phase 4; Phase 1 Ctrl-C is line-cancel/exit only)
- `/model` switching (Phase 5; Phase 1 only persists the config choice)
- Skills + memory file (Phase 6), `/btw` side channel (Phase 7), GitHub loop (Phase 8)
- Global (cross-directory) session home; Phase 1 sessions are project-local under `./.agent/sessions`
- Custom session file formats, titles inside snapshot blobs, `os.environ` credential reads

## Subsequent Slice Plan

- Phase 2: agent acts on real repos (read/write/edit/shell) with `/diff` review
- Phase 3: deny-first approval gate before every side effect
- Phase 4: Plan/Act modes + mid-task steering and cancel
- Phase 5: provider switching, `/cost`, context controls
- Phase 6: local skills + repo memory file
- Phase 7: `/btw` subagent side channel
- Phase 8: issue-to-PR GitHub loop + `/review` parity bar
