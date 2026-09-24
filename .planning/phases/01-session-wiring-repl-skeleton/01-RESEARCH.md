# Phase 1: Session Wiring + REPL Skeleton - Research

**Researched:** 2026-09-24
**Domain:** Conversational CLI front-end (REPL + entry) over Strands harness session persistence
**Confidence:** HIGH (session mechanics verified against installed source this session; REPL/CLI library details from training + project research)

## Summary

Phase 1 builds a new `strands_code_cli/` package beside the existing `strands_code_agent/` library: a Typer entry point (`strands-code`, no subcommands) opening a prompt_toolkit REPL that drives an agent built from harness defaults with file-local snapshot sessions. The single most important finding is that the installed `strands-harness 0.1.2` already owns every hard part of the session contract: `create_harness(session={"id": ..., "dir": ...})` constructs a `SnapshotSessionManager` over `LocalFileStorage` with `save_latest_on="message"` (most durable setting), persists the whole agent as one atomic snapshot blob, and restores it on `AgentInitializedEvent` when a new agent is constructed with the same session id [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/agent.py:474-485]. Resume is therefore "construct again with the same id" — there is no separate restore call for the planner to design.

The composition question (harness `create_harness` returns a plain `Agent`, while the repo's `CodeAgent` subclass owns the `python_repl` tool and prompt assembly) resolves by passing CodeAgent's machinery into the harness factory: build the `python_repl` tool from `SandboxedPythonInterpreter(...).get_tool()` and the preamble/instructions from CodeAgent's toolkit merge, then call `create_harness(tools=[python_repl], instructions=..., session={"id": ...}, model=<config provider>)`. This honors the CONTEXT-mandated "harness defaults, not a bare Agent" direction while keeping the tested prompt/tool assembly. Session titles (UUID + rename, model auto-title) must live in a CLI-owned sidecar index because snapshot storage is keyed purely by session id with no title field.

**Primary recommendation:** New `strands_code_cli/` package (entry, loop, router stub, session index, config) with `create_harness()` as the only agent factory, `session={"id"}` as the only resume mechanism, per-message snapshot saves as the kill-safety mechanism, and an explicit save + `flush`-equivalent on clean exit.

## User Constraints

Copied verbatim from `01-CONTEXT.md`. The planner MUST honor these.

### Entry experience
- **D-01:** `strands-code` with no arguments opens the REPL conversation immediately; there are no subcommands in Phase 1.
- **D-02:** On launch with existing sessions, show a resume picker (recent sessions + start-new); `--session-id <uuid>` still resumes directly.

### Session identity
- **D-03:** Sessions get auto-generated UUIDs; the user can rename a session when it matters.
- **D-04:** The model auto-titles each session from the first exchange; the user can rename anytime so the picker stays readable with zero effort.

### First-run provider
- **D-05:** First run without AWS credentials stops with a Bedrock setup pointer rather than falling back to local providers — **Reversibility:** costly — an offline-first entry path later would rework launch, session defaults, and the AWS-optional project constraint.
- **D-06:** After first run the provider lives in a config file; `/model` switching is out of scope for this phase (Phase 5) but the config choice must persist for it.

### Kill-resume guarantee
- **D-07:** A resumed session after SIGKILL restores full state: transcript plus pending tool state and working plan, not just history.
- **D-08:** Session state persists after every completed turn, so a kill loses at most the in-flight turn.

### the agent's Discretion
None — the user decided every area directly.

### Deferred Ideas
None — discussion stayed within phase scope.

## Project Constraints (from AGENTS.md)

Directives the planner must not violate (sources: repo-root `AGENTS.md`, `.planning/PROJECT.md` constraints):

- Python >= 3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform.
- AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports. (Note: D-05 tightens this for the CLI entry path — first run stops without credentials instead of going offline.)
- No upper pins during the experimental phase; resync upstream deliberately, not continuously.
- Constructor-kwarg configuration — no `os.environ`/`os.getenv` reads in library code; the CLI config file feeds constructors. (AWS credentials resolve through the ambient boto3 chain, never read directly.)
- Absolute imports rooted at the package (`from strands_code_agent...` / `from strands_code_cli...`); no relative imports, no `sys.path` manipulation.
- `rich` rendering only in the callback-handler/REPL-render path; never `print()` in library code.
- Do not add logging to the `python_repl` observation path; agent-visible output flows through the `(stdout, stderr)` tuple.
- Comments stay one or two lines; no narrative or design-deliberation comments.
- Symbols: `PascalCase` classes, `snake_case` functions, `UPPER_SNAKE` constants; tests mirror modules as `tests/test_<module>.py`.
- New CLI code lives in a separate package (per SUMMARY.md: `strands_code_cli/`, one module per CLI gap); the library stays importable without CLI deps.
- No direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Agent loop + tool dispatch | strands-harness `create_harness` | — | Harness-first direction; never rebuild the loop |
| Session persistence + restore | SDK `SnapshotSessionManager` via `session={"id","dir"}` | CLI session index (titles only) | Snapshots capture the whole agent atomically; titles are CLI presentation state the SDK has no field for |
| Session identity (UUID mint, `--session-id` routing, resume picker) | New CLI (`session_cli.py` equivalent) | — | Genuinely new; SDK mints random ids but has no picker/index concept |
| REPL input/editing/history display | prompt_toolkit `PromptSession` | — | Standard component for this UX class |
| Entry point + argv (`--session-id`) | Typer | — | Type-hint-driven help; `CliRunner` enables smoke tests |
| Provider config file persistence | New CLI config module (YAML via owned PyYAML) | platformdirs user config dir | SDK resolves model strings; only the CLI persists the choice |
| First-run credential gate | New CLI launch path (preflight check, then stop-with-pointer) | — | Policy decision D-05; SDK would just fail deep in the first invoke |
| Per-turn durability | `save_latest_on="message"` (harness already sets this) | Explicit save on clean exit | Crash safety comes from per-message saves; exit path adds determinism |
| Output rendering | Existing `CodeAgentCallbackHandler` reused/extended | — | Owned asset; keep rendering in one place per AGENTS.md |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `strands-harness` | 0.1.2 (locked) | `create_harness()` agent factory: model, tools, session, memory, context defaults | Project-locked platform; CONTEXT mandates composing session wiring here [VERIFIED: pyproject.toml:27-34] |
| `strands-agents` | 1.57.0 (locked) | `Agent`, `SnapshotSessionManager`, `FileSessionManager`, `LocalFileStorage` | Project-locked runtime under the harness [VERIFIED: pyproject.toml:27-34] |
| `typer` | unpinned (`typer>=0.9`, no upper pin) | `strands-code` entry, `--session-id` option | Project research consensus for new Python CLIs [CITED: .planning/research/SUMMARY.md:18-26]; no-upper-pin per AGENTS.md compatibility constraint |
| `prompt_toolkit` | unpinned (`prompt-toolkit>=3.0`, no upper pin) | REPL: multiline editing, history, slash completer, bottom toolbar | Project research direction [CITED: .planning/research/SUMMARY.md:18-26] |
| `rich` | 15.0.0 (already owned) | Transcript/streaming render via existing callback handler | Zero new deps; already the shared renderer [VERIFIED: strands_code_agent/callback_handler.py:1-9] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `platformdirs` | unpinned, no upper pin | Per-user global config path for the provider config file | Config-file home for D-06 [ASSUMED] |
| `pyyaml` | >=6.0 (already owned) | Provider config file format | Already a dependency; no new package for config [VERIFIED: pyproject.toml:27-34] |
| `questionary` | unpinned, no upper pin | Resume picker + first-run confirm prompts | Only if prompt_toolkit dialogs prove heavier than needed; rides prompt_toolkit so no renderer conflict [CITED: .planning/research/SUMMARY.md:18-26] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Typer | Click (raw) / argparse | 2026 consensus is Typer-over-Click for new CLIs [CITED: .planning/research/SUMMARY.md:199]; Click adds nothing here |
| prompt_toolkit REPL | Textual fullscreen | Textual fights line-streaming agent output; deferred to an optional later mode [CITED: .planning/research/SUMMARY.md:18-26] |
| Snapshot sessions | `FileSessionManager` message-log sessions (`./.agent/sessions` per CONTEXT) | Message logs persist each message individually, not whole-agent state; snapshots are the SDK-recommended path and the harness default — D-07 full-state restore maps to snapshots, not message logs |
| CLI sidecar title index | Stuffing titles into snapshot blobs | Snapshot schema is SDK-owned; writing foreign keys risks clobbering on restore — keep titles out-of-band |

**Installation:**

```bash
uv add typer prompt-toolkit platformdirs
uv add --group dev questionary  # only if picker needs it; prefer prompt_toolkit dialogs first
```

(Use `uv add`, not pip, per `uv` toolchain constraint. No upper pins per AGENTS.md.)

**Version verification:** The sandbox `pip index` reports stale versions (`typer 0.10.0`, `prompt_toolkit 3.0.36`, `platformdirs 2.4.0`), contradicting the project's 2026-09-23 PyPI JSON API verification (`Typer 0.27.2`, `prompt_toolkit 3.0.53`, `questionary 2.1.1`, `platformdirs 4.11.12` [CITED: .planning/research/SUMMARY.md:18-26,183]). Treat the sandbox index as a stale mirror: specify floor versions only (`typer>=0.9`, `prompt-toolkit>=3.0`, `platformdirs>=4.0`) with no upper pin, and let `uv lock` resolve current versions at plan time.

## Package Legitimacy Audit

Phase installs `typer`, `prompt-toolkit`, (`platformdirs`, possibly `questionary`). All are long-lived, high-download, foundation-backed packages named in the project's own verified research — not names discovered via web search this session.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `typer` | PyPI | ~6 yrs (est.) | very high (est.) | github.com/fastapi/typer (well-known) | OK | Approved |
| `prompt-toolkit` | PyPI | ~10 yrs (est.) | very high (est.) | github.com/prompt-toolkit/python-prompt-toolkit (well-known) | OK | Approved |
| `platformdirs` | PyPI | ~5 yrs (est.) | very high (est.) | github.com/tox-dev/platformdirs (well-known) | OK | Approved |
| `questionary` | PyPI | ~7 yrs (est.) | high (est.) | github.com/tmbo/questionary (well-known) | OK | Approved (only if needed) |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

*Age/download cells are estimates [ASSUMED] — the sandbox registry mirror is stale (see above) so exact counts were not confirmable here; all four are unambiguous established packages corroborated by project research [CITED: .planning/research/SUMMARY.md:18-26]. No `postinstall` risk class exists for these pure-Python wheels beyond standard install. Planner: `uv lock` at plan time is the freshness gate.*

## Architecture Patterns

### System Architecture Diagram

```text
$ strands-code [--session-id UUID]
        │
        ▼
┌───────────────┐  first run, no creds   ┌────────────────────┐
│ Typer entry   │ ──────────────────────▶│ STOP + Bedrock     │
│ (main.py)     │                        │ setup pointer (D-05)│
└───────┬───────┘                        └────────────────────┘
        │ creds OK
        ▼
┌───────────────┐  no --session-id       ┌────────────────────┐
│ Resume picker │ ──────────────────────▶│ Session index      │
│ (recent + new)│  (D-02)                │ (id → title sidecar)│
└───────┬───────┘                        └────────────────────┘
        │ session id (picked | --session-id | fresh UUID)
        ▼
┌───────────────────────────────────────────────────────┐
│ create_harness(                                       │
│   tools=[python_repl], instructions=<code preamble>,  │
│   session={"id": ..., "dir": ./.agent/sessions},      │
│   model=<config provider>)                            │
│   → SnapshotSessionManager + LocalFileStorage,        │
│     save_latest_on="message", restore on init         │
└───────┬───────────────────────────────────────────────┘
        │
        ▼
┌───────────────┐  leading "/"  ┌────────────────┐
│ prompt_toolkit│ ─────────────▶│ Router stub:   │
│ REPL loop     │               │ /resume /rename│
│ (loop.py)     │               │ /exit; else →  │
└───────┬───────┘               │ agent as task  │
        │ agent turn            └────────────────┘
        ▼
┌───────────────┐  each message ┌────────────────────────┐
│ CodeAgentCall-│ ─────────────▶│ snapshot_latest.json   │
│ backHandler   │  auto-save    │ (+ title index update  │
│ render (Rich) │               │ after turn 1: D-04)    │
└───────────────┘               └────────────────────────┘
        │ clean exit (Ctrl-D / /exit / SIGTERM)
        ▼
  explicit save_snapshot + session flush (SES-03); kill -9 safe by
  construction — at most the in-flight turn is lost (D-08)
```

A reader traces the primary use case: launch → picker → agent constructed with session id (old state restored automatically) → type ask → streamed answer → per-message snapshot → exit flushes → next launch lists the session with its auto-title.

### Recommended Project Structure

```text
strands_code_cli/          # NEW package; library stays CLI-dep-free
├── __init__.py            # exports main() only
├── main.py                # Typer app: `strands-code`, --session-id option, first-run gate
├── loop.py                # prompt_toolkit PromptSession loop, Ctrl-C/D + slash dispatch
├── router.py              # leading-"/" dispatch stub (/resume /rename /exit); else → agent
├── session_index.py       # UUID mint, sidecar {id → title/created/updated}, recent-list
├── provider_config.py     # YAML provider config load/save (platformdirs home)
└── first_run.py           # AWS credential preflight + Bedrock setup pointer (D-05)
tests/
├── test_cli_entry.py      # Typer CliRunner: no-arg opens REPL, --session-id routes
├── test_session_index.py  # mint/list/rename round-trips
├── test_session_resume.py # construct → turn → re-construct same id → history intact
├── test_kill_resume.py    # no-exit-flush restore (SIGKILL simulation)
└── test_first_run.py      # no-creds → stop-with-pointer exit code
```

### Pattern 1: Harness factory as the only agent constructor
**What:** All agent construction goes through `create_harness()`, never a bare `Agent(...)` or a bare `CodeAgent(...)` without harness wiring. CodeAgent's value (toolkit merge → authorized imports + preamble + `python_repl` tool) enters as inputs: `tools=[<python_repl tool>]`, `instructions=<usage/preamble text>`.
**When to use:** Always in CLI code; the library keeps `CodeAgent` for non-CLI consumers.
**Example:**
```python
# Source: strands_harness/agent.py (installed 0.1.2) + strands_code_agent/code_agent.py
from strands_code_agent.python_environments.local_sandboxed import SandboxedPythonInterpreter

interpreter = SandboxedPythonInterpreter(code_preamble, authorized_imports={...})
agent = create_harness(
    tools=[interpreter.get_tool()],   # consumer tools ride alongside built-ins
    instructions=usage_instructions,  # appended after the harness contract
    session={"id": session_id},       # resume = same id next run
    model=provider_string,            # from CLI config file (D-06)
)
```
`tools` are "consumer tools, added alongside the built-in tools" and `session` accepts a `SessionConfig` mapping with only `id`/`dir` keys [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/agent.py:287-288,355-363]. Unknown `session` keys raise `ValueError` [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/options.py:157-159]. An explicit `session_manager` in `agent_kwargs` beats the `session` sugar [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/agent.py:474-478] — escape hatch if the dict form ever proves insufficient.

### Pattern 2: Resume-by-reconstruction + sidecar title index
**What:** Listing = scan the session dir for stored snapshots (oldest scope: `LocalFileStorage.list()` exists as an async byte-blob primitive [VERIFIED: .venv/lib/python3.14/site-packages/strands/storage/local_file_storage.py:216]); titles/renames live in a CLI-owned JSON index (`{session_id: {title, created_at, updated_at}}`), never in snapshot blobs. New sessions mint `str(uuid.uuid4())` — already lowercase hex+dashes, so the harness sanitizer (`[^a-z0-9_-] → "-"`, lowercase) passes them through unchanged [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/options.py:28-29].
**When to use:** Picker (D-02), UUID mint (D-03), rename + model auto-title after the first exchange (D-04).
**Example:**
```python
# Shape only — exact snapshot key layout is SDK-owned, so enumerate via
# storage list / directory scan and join against the sidecar index. [ASSUMED]
entry = {"id": str(uuid.uuid4()), "title": "untitled", ...}
# after first exchange: title = agent("Summarize this conversation in <= 6 words")
```

### Pattern 3: Kill-safe persistence without an exit handler dependency
**What:** Rely on `save_latest_on="message"` (the harness already configures this — "most durable, highest I/O" [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/agent.py:483-485] and snapshot docs: "`"message"`: after every message added (most durable, highest I/O)" [VERIFIED: .venv/lib/python3.14/site-packages/strands/session/snapshot_session_manager.py:57-66]) so SIGKILL loses at most the in-flight turn (D-08). Clean exits (Ctrl-D, `/exit`, SIGTERM) additionally trigger an explicit save + index update for determinism (SES-03). Never depend on `atexit` for correctness — it does not run on SIGKILL.
**When to use:** All session writes in this phase.

### Anti-Patterns to Avoid
- **Bare `Agent(...)`/`CodeAgent(...)` in CLI code:** loses harness defaults (context manager, skills, memory, snapshot wiring) and re-creates the "fork the platform" violation. Use `create_harness` per the project constraint.
- **Custom session file format:** the SDK owns two formats already (snapshot blobs recommended; message-log `FileSessionManager` legacy). A third format is pure liability — see Don't Hand-Roll.
- **Titles inside snapshot blobs:** SDK-owned schema, restored verbatim; foreign keys risk clobbering. Sidecar index instead.
- **Thread-kill interruption / signal-based turn abort:** out of scope (Phase 4 owns Ctrl-C-cancel); Phase 1 Ctrl-C behavior is line-cancel/exit only.
- **`os.environ` credential sniffing in CLI library code:** constructor-kwarg rule; credentials stay on the ambient boto3 chain.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conversation persistence | JSONL transcript writer | `SnapshotSessionManager` via `session={"id"}` | Whole-agent atomic blobs; per-message saves; restore-on-init; symlink-attack guards and atomic writes already implemented [VERIFIED: .venv/lib/python3.14/site-packages/strands/session/file_session_manager.py:119-157 for the legacy manager's hardening; snapshot manager persists "the whole agent in one atomic blob" per its module docstring] |
| Session id validation | Regex check | SDK `validate_identifier` (runs inside the managers) | Rejects separators/`.`/`..`/empty with `ValueError` [VERIFIED: .venv/lib/python3.14/site-packages/strands/session/snapshot_session_manager.py:261-266] |
| REPL editing/history/completion | readline wrappers | prompt_toolkit `PromptSession` + `FileHistory` | History persistence, multiline, completers, toolbar are solved problems [ASSUMED] |
| argv parsing/help | argparse bespoke | Typer + `CliRunner` smoke tests | Help text and testability free [ASSUMED] |
| Config home discovery | `~/.strands-code` hardcode | platformdirs `user_config_dir` | XDG/macOS/Windows correctness [ASSUMED] |
| First-run prompts | Custom picker widgets | prompt_toolkit dialogs (questionary only if needed) | Renderer conflicts avoided; questionary rides prompt_toolkit [CITED: .planning/research/SUMMARY.md:18-26] |

**Key insight:** Every persistence primitive this phase needs already exists in the installed SDK/harness and is already wired together by `create_harness`. The phase is burn-down of *wiring and UX* (entry, picker, index, config, loop), not storage engineering. Any plan task that writes a session file format by hand is wrong.

## Common Pitfalls

### Pitfall 1: No auto-resume — a fresh run starts a fresh session
**What goes wrong:** Developer assumes `session=True` continues the last conversation; every launch starts empty.
**Why it happens:** With no `id`, the harness mints `uuid.uuid4().hex[:8]` per run and documents "This does not auto-resume across runs … pass it back as `session={"id": ...}` on the next run" [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/agent.py:355-363,480-482].
**How to avoid:** The CLI always resolves an id before constructing (picker choice, `--session-id`, or fresh UUID) and always passes `session={"id": resolved}`. Test: two consecutive constructs with the same id share history.
**Warning signs:** Manual testing "works" because the tester reuses one process; resume only breaks across processes.

### Pitfall 2: D-07 over-read — expecting mid-turn tool state to survive SIGKILL
**What goes wrong:** Plan demands byte-identical restoration of a half-executed tool call.
**Why it happens:** Snapshots persist on message/invocation lifecycle events, not mid-tool-execution; D-08 explicitly bounds the guarantee ("loses at most the in-flight turn").
**How to avoid:** Define "full state" as transcript + `agent.state` (todos/working plan live on `agent.state` per harness code comments) as of the last completed message. The kill-resume test asserts conversation + state continuity, not in-flight tool replay.
**Warning signs:** Acceptance test kills mid-`execute_code` and expects the tool result to exist after resume.

### Pitfall 3: Agent-id mismatch silently forks a session
**What goes wrong:** Resume constructs with the same session id but a different `agent_id` (default `"default"` [VERIFIED: .venv/lib/python3.14/site-packages/strands/agent/agent.py:156,357]) and sees empty history — snapshot keys are scoped `<session_id>/scopes/agent/<agent_id>/snapshots/`.
**How to avoid:** Never set a per-run `agent_id` in Phase 1; always use the default so every construct lands in the same scope. If a custom agent id is ever introduced, it must be derived deterministically from the session id.
**Warning signs:** Resume "loses" history while the snapshot files are visibly present on disk.

### Pitfall 4: Session dir confusion (project-local vs home)
**What goes wrong:** Picker shows nothing after resume because one run used `./.agent/sessions` (harness `DEFAULT_SESSION_DIR` [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/defaults.py:35]) and another used `~/.strands/sessions` (legacy `FileSessionManager` default [VERIFIED: .venv/lib/python3.14/site-packages/strands/session/file_session_manager.py:66-72]).
**Why it happens:** Two SDK defaults for two manager generations; `create_harness` uses the project-local one.
**How to avoid:** Always go through `create_harness(session={...})` without overriding `dir` in Phase 1; document `./.agent/sessions` as the single home. Never mix a hand-built `FileSessionManager` with harness sessions.
**Warning signs:** Sessions "vanish" when launching from a different cwd — which also flags that project-local sessions are cwd-relative (acceptable for Phase 1; global session home is a later-phase question, listed in Open Questions).

### Pitfall 5: First-run gate placed after agent construction
**What goes wrong:** Credential failure surfaces as a deep SDK exception mid-invoke instead of the clean D-05 stop-with-pointer.
**Why it happens:** `create_harness` resolves the model string lazily; ambient-credential failure only materializes at first model call [ASSUMED].
**How to avoid:** Preflight before constructing: a cheap credential probe (e.g. STS `get_caller_identity` via the ambient chain), and on failure print the Bedrock setup pointer and exit non-zero without creating sessions/config. Test asserts the exit code and that no session dir was created.
**Warning signs:** First-run test needs AWS mocks to pass — the gate must be testable without credentials.

### Pitfall 6: Blocking the event loop / stdout interleaving with Rich rendering
**What goes wrong:** prompt_toolkit input corrupts while the Rich callback handler streams agent output.
**Why it happens:** Two renderers sharing one terminal; the agent `__call__` is synchronous and long-running.
**How to avoid:** Phase 1 runs the agent turn synchronously with the prompt suspended (standard `patch_stdout` pattern [ASSUMED]); anytime-steering input during a turn is explicitly Phase 4 scope. Keep the callback handler side-effect-only per AGENTS.md.
**Warning signs:** Garbled prompt after the first long agent turn.

## Code Examples

Verified patterns from sources read this session:

### Session dict → snapshot manager (what the harness builds for you)

```python
# Source: .venv/lib/python3.14/site-packages/strands_harness/agent.py:474-485
session_manager = agent_kwargs.pop("session_manager", None)
session_dir: str | None = None
if session_manager is None:
    if isinstance(session_option, SessionManager):
        session_manager = session_option
    elif session_option is not None:
        session_id = session_option.get("id")
        session_dir = session_option.get("dir") or defaults.DEFAULT_SESSION_DIR
        resolved_id = _sanitize_session_id(session_id) if session_id else uuid.uuid4().hex[:8]
        session_manager = SnapshotSessionManager(
            resolved_id,
            storage=LocalFileStorage(session_dir),
            save_latest_on="message",
        )
```

### SessionConfig shape (only `id` + `dir`)

```python
# Source: .venv/lib/python3.14/site-packages/strands_harness/types/agent.py:144-154
class SessionConfig(TypedDict, total=False):
    """Session persistence settings for ``session=``.

    Attributes:
        id: Session id; sanitized to ``[a-z0-9_-]``. Omit to mint a fresh short id per agent.
        dir: Directory the session (and offloaded context) is stored under. Default
            ``./.agent/sessions``.
    """

    id: str
    dir: str
```

### CodeAgent constructor seam (kwargs forward to `Agent`, callback default)

```python
# Source: strands_code_agent/code_agent.py:77-86,131-149
def __init__(self,
             system_prompt: str | None = None,
             tools: list | None = None,
             ...
             callback_handler=DEFAULT_CODE_AGENT_CALLBACK_HANDLER,
             **kwargs):
    ...
    self.python_repl = python_interpreter_class(...)
    python_repl_tool = self.python_repl.get_tool()
    ...
    kwargs.update({
        "system_prompt": system_prompt,
        "tools": tools,
        "callback_handler": callback_handler
    })
    super().__init__(**kwargs)
```

`CodeAgent` forwards `**kwargs` to `strands.Agent`, so `session_manager=` passes through — but CLI code should prefer `create_harness(session={"id"})` to also get model/context/skills/memory defaults. The default interpreter is `SandboxedPythonInterpreter` [VERIFIED: strands_code_agent/code_agent.py:83].

### Snapshot save strategies (why `"message"` is the kill-safety setting)

```python
# Source: .venv/lib/python3.14/site-packages/strands/session/snapshot_session_manager.py:52-66
SaveLatestStrategy = Literal["message", "invocation", "trigger"]
"""Controls how often ``snapshot_latest`` is saved automatically.

- ``"invocation"``: after every agent invocation completes (default; balances durability and I/O).
- ``"message"``: after every message added (most durable, highest I/O).
- ``"trigger"``: only when ``snapshot_trigger`` fires (or manually via ``save_snapshot``).
```

The harness hard-codes `"message"` (see first example) — no CLI work needed to enable per-message durability.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Message-log sessions (`FileSessionManager`, per-message JSON) | Snapshot sessions (whole-agent atomic blob, recommended) | strands-agents 1.x | D-07 full-state restore maps to snapshots; message logs are legacy |
| Manual `Agent(session_manager=FileSessionManager(...))` wiring | `create_harness(session={"id","dir"})` sugar | harness 0.1.x | One dict instead of manager+storage construction |
| `~/.strands/sessions` home default | `./.agent/sessions` project-local default | harness 0.1.x | Sessions are project-scoped; cwd matters (Pitfall 4) |
| Textual fullscreen REPL experiments | prompt_toolkit line REPL consensus | 2026 community | Matches Claude Code/Codex UX; composes with streaming [CITED: .planning/research/SUMMARY.md:18-26] |

**Deprecated/outdated:**
- `session="auto"` string form: rejected — "no longer a value, the default is True" [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/options.py:151-154]. Pass `True`, a dict, a manager, `False`/`None` — never a string.
- Bare `Agent(...)` construction in new CLI code: superseded by `create_harness` per project direction.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | prompt_toolkit `PromptSession` + `FileHistory` + `patch_stdout` is the right REPL suspension pattern | Patterns, Pitfall 6 | Low — standard pattern; verify at implementation, fallback is plain `input()` loop |
| A2 | Model credential failure materializes at first invoke, so a preflight probe is needed for a clean D-05 stop | Pitfall 5 | Medium — if the SDK raises at construction, the gate simplifies; probe-first still works |
| A3 | STS `get_caller_identity` (or equivalent cheap probe) is an acceptable credential preflight | Pitfall 5 | Low — any cheap ambient-chain probe works; exact call is planner detail |
| A4 | platformdirs `user_config_dir("strands-code")` + YAML is the right D-06 config home/format | Standard Stack | Low — user-confirmable path; project-local fallback also viable |
| A5 | Session titles live in a CLI sidecar JSON index; snapshot blobs carry no title field | Patterns | Low — verified no title concept in `SessionConfig`; blob schema not exhaustively audited |
| A6 | `agent.state` (todos/working plan) is captured by whole-agent snapshots, satisfying D-07's "working plan" clause | Pitfall 2 | Medium — snapshot module docstring claims whole-agent capture; kill-resume test must assert `state` round-trips |
| A7 | Sandbox `pip index` versions are a stale mirror; SUMMARY.md 2026-09-23 PyPI versions are authoritative | Standard Stack | Low — floors + `uv lock` make exact versions non-critical per no-upper-pin rule |
| A8 | LocalFileStorage file permissions are restrictive enough for conversation data at rest | Security | Low — legacy manager used `0o700` dirs; snapshot storage perms not audited this session — verify at plan time |

## Open Questions

1. **Project-local vs global session home**
   - What we know: harness default is `./.agent/sessions` (cwd-relative); picker only sees the current project's sessions.
   - What's unclear: whether users expect cross-directory session visibility (Claude Code shows recent across projects).
   - Recommendation: Phase 1 uses the harness default (project-local); note global-home as a Phase 5+ consideration, no user confirmation needed now.

2. **Picker ordering signal**
   - What we know: sidecar index can store `updated_at`; snapshot keys embed no reliable timestamp for listing.
   - What's unclear: whether "recent" means last-opened or last-written (equivalent in Phase 1 — every open writes).
   - Recommendation: order by sidecar `updated_at`, updated on every construct. No user question.

3. **Auto-title model call cost/latency**
   - What we know: D-04 requires a model-generated title from the first exchange — one extra inference per session.
   - What's unclear: whether to use the full agent or a cheap direct model call.
   - Recommendation: direct cheap call on the configured model with a ≤6-word prompt; fall back to first-ask truncation on failure. No user question.

4. **`HARNESS_CONTRACT` export**
   - What we know: exists in `strands_harness.prompt` (project SUMMARY lists it as unverified [CITED: .planning/research/SUMMARY.md:178]).
   - What's unclear: nothing Phase 1 needs from it.
   - Recommendation: ignore in Phase 1.

## Environment Availability

Phase 1 has no live-service dependencies: file sessions, local REPL, and the credential preflight's *negative* path (no creds → clean stop) are all testable offline. Bedrock credentials are intentionally absent in CI.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.7 (dev interp); project floor 3.10 | — |
| `uv` | installs/lock | ✓ (repo uses `uv.lock`) | 0.9.26 (per STACK.md) | — |
| pytest | validation gate | ✓ (locked 9.1.1) | 9.1.1 | — |
| AWS credentials | first-run gate *negative* test + later live turns | ✗ (expected) | — | D-05 stop-with-pointer IS the behavior; live-turn tests need creds and stay manual |
| typer / prompt_toolkit / platformdirs | new CLI code | ✗ (not installed; confirmed absent from `.venv`) | floors at plan-time `uv lock` | none — Wave 0 installs them |

**Missing dependencies with no fallback:** none blocking (Wave 0 `uv add` covers the new CLI deps).
**Missing dependencies with fallback:** AWS credentials — the fallback (clean stop) is the specified behavior.

## Validation Architecture

`nyquist_validation` is enabled (key present and not `false` in `.planning/config.json` [VERIFIED: .planning/config.json workflow block]).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`-m 'not integration'`) [VERIFIED: pyproject.toml:56-60] |
| Quick run command | `uv run pytest tests/test_session_resume.py tests/test_cli_entry.py -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-01 | Multi-ask conversation: ask → agent works → follow-up in same session | integration (REPL loop + agent turn) | `uv run pytest tests/test_repl_loop.py::test_multi_ask_same_session -x` | ❌ Wave 0 |
| SES-01 | Resume by UUID: `--session-id` / `/resume` continues where left off | unit+integration | `uv run pytest tests/test_session_resume.py -x` | ❌ Wave 0 |
| SES-03 | Flush on exit + kill-resume: no silent state loss | unit+integration | `uv run pytest tests/test_kill_resume.py tests/test_cli_exit.py -x` | ❌ Wave 0 |
| D-05 | First run without creds stops with Bedrock pointer, creates nothing | unit (CliRunner, no creds) | `uv run pytest tests/test_first_run.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** quick run command above for the touched area
- **Per wave merge:** `uv run pytest tests/ -q` (full suite must stay green — 177-test baseline per PROJECT.md)
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `uv add typer prompt-toolkit platformdirs` — new CLI deps (questionary only if picker needs it)
- [ ] `strands_code_cli/` package skeleton + `strands-code` console script entry in `pyproject.toml`
- [ ] `tests/test_cli_entry.py` — Typer `CliRunner` no-arg/`--session-id` routing (covers D-01/D-02 wiring)
- [ ] `tests/test_session_resume.py` — construct → turn → re-construct same id → transcript + `agent.state` intact (covers SES-01, D-07/D-08)
- [ ] `tests/test_kill_resume.py` — restore without exit flush; subprocess `SIGKILL` mid-idle then resume (covers SES-03, Pitfall 5 in project PITFALLS.md)
- [ ] `tests/test_first_run.py` — no-creds → non-zero exit + setup pointer + no session dir created (covers D-05)
- [ ] `tests/test_session_index.py` — UUID mint, rename, auto-title update, recent ordering (covers D-03/D-04)

## Security Domain

`security_enforcement` is enabled at ASVS Level 1 (`.planning/config.json`: `"security_enforcement": true, "security_asvs_level": 1` [VERIFIED]).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Ambient AWS credential chain (never handled in code); first-run gate stops cleanly without creds |
| V3 Session Management | yes | SDK-owned session ids; `validate_identifier` rejects separators/`..`/empty [VERIFIED: snapshot_session_manager.py:261-266]; symlink-attack guards on session file I/O |
| V4 Access Control | no | Single local actor; no multi-user surface (out of scope per REQUIREMENTS.md) |
| V5 Input Validation | yes | `--session-id` flows into a validated identifier (SDK raises `ValueError` on bad input — CLI must surface, not crash); REPL freeform input is agent content, never executed by the CLI |
| V6 Cryptography | no | No crypto in Phase 1; conversation at rest relies on OS file perms (see A8) |
| V14 Configuration | yes | Provider config file: parse defensively (schema-validate keys, reject unknowns like `_session_config` does); never log secrets |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Session-id path traversal (`--session-id ../../x`) | Tampering | SDK `validate_identifier` raises; CLI catches and shows usage error (add a test) |
| Symlinked session files (planted read/write target) | Tampering | SDK refuses symlink read/write with `SessionException` (legacy manager verified; snapshot path goes through the same storage layer) |
| Conversation data at rest (prompts may contain secrets) | Information disclosure | Restrictive file perms on session dir; verify `LocalFileStorage` perms at plan time (A8) |
| Prompt injection via resumed content | Spoofing | Out of scope structurally until Phase 3 permissions; note only — resumed transcript is trusted-to-self in Phase 1 |

---

*Research completed: 2026-09-24. Sources: installed `strands-harness 0.1.2` + `strands-agents 1.57.0` source read this session; repo files (`pyproject.toml`, `code_agent.py`, `callback_handler.py`, `AGENTS.md`, `.planning/*`) read this session; project research SUMMARY.md cited; REPL/CLI library specifics assumed from training where tagged.*
