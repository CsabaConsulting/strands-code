# Phase 6: Skills + Memory File - Pattern Map

**Mapped:** 2026-10-04
**Files analyzed:** 11 (4 new modules, 3 modified modules, 1 folded plugin, 3 test files)
**Analogs found:** 9 / 11 (2 partial — new API surfaces, RESEARCH.md sketches cover the gap)

> Produced by the generic-agent workaround for `gsd-pattern-mapper`
> (typed dispatch unavailable this session). All analog paths verified
> git-tracked via `git ls-files` this session.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/skills.py` (NEW) | service | file-I/O | `strands_code_cli/session_index.py` | role-match |
| `strands_code_cli/memory_file.py` (NEW) | service | file-I/O | `strands_code_agent/knowledge/bundle.py` + `strands_code_cli/session_index.py` | role-match |
| `strands_code_cli/memory_modes.py` (NEW, or fold into `memory_file.py`) | store | transform | `strands_code_cli/mode.py` | exact |
| `strands_code_cli/completer.py` (NEW, or fold into `skills.py`) | utility | event-driven | `strands_code_cli/choice.py` | partial |
| Memory injector plugin (NEW, lives in `memory_file.py`) | provider | event-driven | `strands_code_cli/steering.py` | role-match |
| `strands_code_cli/router.py` (MOD) | route | request-response | self (`router.py` branches) | exact |
| `strands_code_cli/loop.py` (MOD) | controller | event-driven | self (`loop.py` turn boundary) | exact |
| `strands_code_cli/main.py` (MOD) | config | request-response | self (`main.py` `build_agent`) | exact |
| `tests/test_skills.py` (NEW) | test | batch | `tests/test_session_resume.py` | role-match |
| `tests/test_memory_file.py` (NEW) | test | batch | `tests/test_session_resume.py` | role-match |
| `tests/test_memory_curate.py` (NEW) | test | batch | `tests/test_session_resume.py` + `tests/test_mode.py` | role-match |

## Pattern Assignments

### `strands_code_cli/skills.py` (NEW) (service, file-I/O)

**Analog:** `strands_code_cli/session_index.py` (CLI-owned state over a
directory: fail-soft load, symlink refusal, `0o700` dirs). Skill *parsing*
itself is NOT hand-rolled — RESEARCH Pattern 1 mandates
`Skill.from_directory` (installed SDK, untracked `.venv` precedent, not a
repo analog).

**Imports pattern** (`session_index.py` lines 8-16):

```python
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
```

`skills.py` mirrors this with `yaml` unnecessary (SDK parses frontmatter):
`from __future__ import annotations`, stdlib block, then the SDK import
(`from strands.vended_plugins.skills import Skill`) in the third-party slot.
Absolute imports rooted at the package per AGENTS.md.

**Core pattern — fail-soft load + fail-loud tamper** (`session_index.py`
lines 69-89):

```python
def _ensure_loaded(self) -> None:
    if self._entries is not None:
        return
    self._entries = {}
    path = self._index_path()
    if path.is_symlink():
        raise ValueError(f"Session index must not be a symlink: {path}")
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
```

`SkillIndex` copies this shape: missing `./.agent/skills` dir → empty index
(harness `_skills_plugin` already returns None when the dir is absent);
corrupt single skill → warn-and-skip (SDK does this internally);
symlinked skills root → `ValueError` (T-03-02 precedent).

**Validation pattern — id-as-key, never path segment**
(`session_index.py` lines 208-214, plus `rich_stash_path` lines 28-37):

```python
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", session_id):
    return None
```

`SkillIndex.resolve` applies the same fail-soft discipline to skill names:
names that fail the SDK regex are unloadable + warned, never resolved.

**Traversal-guard pattern for `remove`** — see `router.py`
`_remove_snapshot_dir` (lines 609-625) under the router assignment below;
`skills.py` removal helper reuses that resolve + same-parent check verbatim.

---

### `strands_code_cli/memory_file.py` (NEW) (service, file-I/O)

**Analogs:** `strands_code_agent/knowledge/bundle.py` (frontmatter
parse) + `strands_code_cli/session_index.py` (atomic save, perms).

**Frontmatter pattern** (`bundle.py` lines 19-28):

```python
def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter + markdown body from text."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return fm, body
```

Copy as-is for `STRANDS.md` / `.agent/MEMORY.md` reads: no-frontmatter →
`({}, full_text)`; `yaml.safe_load` only (never `yaml.load`). Corrupt
frontmatter → defaults + transcript note (Phase 3 T-03-02 fail-closed
precedent; planner: wrap the `safe_load` in try/except `yaml.YAMLError` —
`bundle.py` itself lets it raise, but the memory loader must not).

**Atomic-save pattern** (`session_index.py` lines 91-98):

```python
def _save(self) -> None:
    assert self._entries is not None
    path = self._index_path()
    if path.is_symlink():
        raise ValueError(f"Session index must not be a symlink: {path}")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

Memory writes use tmp + `os.replace`, symlink refusal, `.agent` dir at
`0o700` (`main.py` lines 113-115 show the `mkdir` + `os.chmod` pair).
Root `STRANDS.md` inherits repo perms (it is a checked-in interop file,
not a secret sidecar) — do NOT chmod the repo root.

**Mtime-tracking pattern** — no direct analog; the shape is a tiny
`dict[Path, float]` of `st_mtime` snapshots with a `changed() -> list[Path]`
sweep. The *check placement* is the loop turn boundary (see loop assignment).

**Dual-load precedence:** load both files, strip frontmatter before
injection, emit `.agent/MEMORY.md` content last with a precedence line
(D-04 ".agent wins"). Mirrors the deny-wins union-report shape of
`_policy_message` (`router.py` lines 471-494): one block per source, winner
named explicitly.

---

### `strands_code_cli/memory_modes.py` (NEW) (store, transform)

**Analog:** `strands_code_cli/mode.py` — exact match (D-07 explicitly cites
the Phase 4 D-07 precedent: session-sticky, in-memory holder).

**Holder pattern** (`mode.py` lines 35-76):

```python
class ModeState:
    """Session-sticky plan/act holder plus the pending-plan flag. ..."""

    VALID = ("plan", "act")

    def __init__(self, initial: str = "act") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown mode {initial!r}: expected plan|act")
        self._mode = initial
        self._pending_plan = False
```

`MemoryModeState` copies this exactly: `VALID = ("curate", "silent")`,
`__init__(initial="curate")` (curate default per D-07 deny-first posture),
`ValueError` on anything else, `set()` returning the transcript
announcement, `announce()` for bare `/memory mode`. Module-level reply
constants (`MODE_PLAN_REPLY`/`MODE_ACT_REPLY` analogues) keep copy in one
place.

**Router branch shape** (`router.py` lines 401-413):

```python
def _mode_message(rest: str, mode: ModeState | None) -> str:
    holder = _mode_holder(mode)
    verb = rest.strip().lower()
    if not verb:
        return holder.announce()
    if verb in ("plan", "act"):
        return holder.set(verb)
    return _MODE_USAGE
```

`/memory mode [curate|silent]` is the same ten lines with the new holder
and a `_MEMORY_MODE_USAGE` string. Note `_mode_holder` (lines 396-398):
`mode if mode is not None else ModeState()` — the throwaway-default keeps
`dispatch` testable without a loop-owned holder; the memory holder needs
the identical fallback.

**Curate-queue pattern:** `BatchState` (`policy_gate.py` lines 79-122) —
`bind_turn` reset, `mark` (approvals cover) vs `record` (denials never
cover):

```python
def bind_turn(self, turn_id: str) -> None:
    """Start a new turn: clear per-turn coverage, keep the log."""
    self._turn = turn_id
    self._covered = set()
```

The curate proposal queue reuses this vocabulary: approve applies +
marks; deny skips-and-continues via `record` (Phase 3 D-02 shape per
CONTEXT). If the planner folds the queue into `memory_modes.py`, keep
`BatchState` semantics (per-turn coverage, session log) rather than
inventing a second cache.

---

### `strands_code_cli/completer.py` (NEW) (utility, event-driven)

**Analog:** `strands_code_cli/choice.py` — partial match (prompt_toolkit
ownership conventions; no existing `Completer` subclass in the repo).

**prompt_toolkit import discipline** (`choice.py` lines 77-83 — deferred
imports inside the builder):

```python
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
```

prompt_toolkit imports live at module top in `loop.py` (lines 17-18) for
hot-path names and function-local in `choice.py`/`router.py` for dialog
paths. The completer is constructed once per loop, so top-level imports
(`from prompt_toolkit.completion import Completer, Completion,
DynamicCompleter, FuzzyCompleter`) follow the `loop.py` precedent.

**Core pattern** — no repo analog; use the RESEARCH-verified sketch
(RESEARCH.md "prompt_toolkit completer wiring"): `SlashCompleter(Completer)`
matching bare names, yielding namespaced `Completion(display,
start_position=-len(text))`, wrapped in `FuzzyCompleter` inside
`DynamicCompleter(lambda: ...)` so add/remove refreshes without restart
(Pitfall 5). `loop.py` line 543 (`PromptSession(history=_history())`) is
the single wiring point — add `completer=...`.

**tty discipline** (`choice.py` lines 166-167):

```python
if not sys.stdin.isatty():
    raise RuntimeError("radio_choice needs a tty")
```

Non-tty callers never reach interactive surfaces; the completer is inert
without a tty by construction (PromptSession handles it), so no branch is
needed — but any `/skills` picker addition must follow the
`sys.stdin.isatty()` branch + typed-fallback shape from
`_model_message`/`show_picker` (`router.py` lines 218, 691-698).

---

### Memory injector plugin (NEW, in `memory_file.py`) (provider, event-driven)

**Analog:** `strands_code_cli/steering.py` `register_steering_hook`
(lines 213-238) — idempotent per-agent registration stashed on the agent.

**Registration pattern** (`steering.py` lines 213-238):

```python
def register_steering_hook(agent: Any, slot: SteeringSlot | None = None) -> SteeringSlot:
    existing = getattr(agent, "_steering_slot", None)
    if isinstance(existing, SteeringSlot) and getattr(agent, "_steering_hook_registered", False):
        return existing
    from strands.hooks import HookOrder
    from strands.hooks.events import BeforeToolCallEvent

    owned = slot if slot is not None else (
        existing if isinstance(existing, SteeringSlot) else SteeringSlot()
    )
    agent.add_hook(make_steering_hook(owned), BeforeToolCallEvent, order=HookOrder.SDK_FIRST)
    try:
        agent._steering_slot = owned
        agent._steering_hook_registered = True
    except Exception:
        pass
    return owned
```

`register_memory_plugin(agent, loader)` mirrors this: idempotency guard
via `agent._memory_plugin_registered`, `ContextInjector(render,
trigger="userTurn")` instead of `add_hook`, duck-typed `Any` agent so the
module never hard-imports agent internals at module scope. The render
function memoizes `(content, mtime)` per file and re-reads on change;
render output is a `<system-reminder>` block (harness `environment` plugin
precedent — untracked `.venv` source, cited via RESEARCH Pattern 2, not
emitted as an analog path).

**Injection-size cap:** mirror the `_AGENTS_MD_CAP` truncation-marker
discipline (Pitfall 7) — cap injected memory with an explicit
`[... truncated]` marker rather than silent clipping.

---

### `strands_code_cli/router.py` (MOD) (route, request-response)

**Analog:** self — new branches copy existing branch shapes. Built-in
branches stay ABOVE dynamic skill resolution in `dispatch` (D-02:
built-ins always win).

**Dispatch tri-state + branch order** (`router.py` lines 64-75, 119-132):

```python
def dispatch(
    text: str,
    *,
    session_id: str,
    index: SessionIndex,
    ...
) -> tuple[str, str | None]:
```

New signature kwarg: `skills: SkillIndex | None = None` (None → skill
branches report "no skills loaded", keeping existing tests green without
fixtures). Branch placement: `/skills`, `/memory`, `/init` alongside the
`/mode` branch (line 118-119); dynamic `/<skill>` resolution AFTER all
built-ins and BEFORE the `Unknown command` fallthrough (line 132).

**Subcommand-message shape** (`router.py` lines 433-468, `_diff_message`):

```python
config = DiffConfig.load(config_path)
store = store_for(session_id)
pending = store.list() if store is not None else {}
if not rest or rest == "show":
    lines = [f"Diff mode: {config.mode} ({len(pending)} pending)."]
    ...
verb, _, arg = rest.partition(" ")
verb = verb.lower()
if verb in MODES:
    ...
return f"Unknown /diff mode {verb!r}. {_DIFF_USAGE}"
```

`/skills [show <name>|remove <name>]` and `/memory [...]` copy this:
bare/rest-empty → status list; `verb, _, arg = rest.partition(" ")`;
lowercased verb dispatch; unknown verb → `f"Unknown /skills ... {verb!r}.
{_SKILLS_USAGE}"`. USAGE constants live at module top (`_DIFF_USAGE` line
56, `_SEARCH_USAGE` line 57); add `_SKILLS_USAGE`, `_MEMORY_USAGE`,
`_INIT_USAGE` there and extend `USAGE_HINT` (lines 20-26).

**Router-composes, loop-runs shape** (`router.py` lines 416-430,
`_approve_message`):

```python
mode.approve()
return ("agent", f"{APPROVE_OK}\n{APPROVE_EXECUTE}")
```

`/<skill> <trailing text>` returns `("agent", composed_prompt)` where
`composed_prompt = skill instructions + trailing text` (RESEARCH Pattern 3,
resolving Open Question 1). No new loop action type; steering/cancel ride
the existing `_invoke_agent` path.

**Traversal-guard shape for `/skills remove`** (`router.py` lines 609-625):

```python
def _remove_snapshot_dir(session_dir: str | Path | None, session_id: str) -> None:
    """Delete one snapshot dir; guarded against traversal and outside roots."""
    if session_dir is None:
        return
    root = Path(session_dir, "session")
    candidate = root / session_id
    try:
        resolved = candidate.resolve()
    except OSError:
        return
    try:
        same_parent = resolved.parent == root.resolve()
    except OSError:
        return
    if not same_parent or resolved.name != session_id:
        return  # traversal or relocated root: never delete
    shutil.rmtree(resolved, ignore_errors=True)
```

Copy verbatim with `root = Path("./.agent/skills")`: resolve, same-parent
check, name-equality check, `shutil.rmtree(ignore_errors=True)`. Refuse
symlinked skill dirs (T-03-02 precedent).

**Lazy-import discipline** (`router.py` lines 142-143, 160, 206-211):
heavy/optional imports (`cost_context`, `model_switch`, `choice`) are
function-local inside branch handlers. `skills`/`memory_file` imports in
new `_skills_message`/`_memory_message` handlers stay function-local too —
`router.py` top-level imports stay light so `dispatch` unit tests import
fast.

---

### `strands_code_cli/loop.py` (MOD) (controller, event-driven)

**Analog:** self — three attach points, each with an in-file precedent.

**Attach 1 — completer wiring** (`loop.py` line 543):

```python
session: PromptSession = PromptSession(history=_history())
```

Becomes `PromptSession(history=_history(), completer=...)` with the
`DynamicCompleter`-wrapped skill completer (RESEARCH Code Examples).
Single call site; no other PromptSession exists in the loop.

**Attach 2 — turn-boundary mtime + promotion sweep** (`loop.py` lines
560-562):

```python
while True:
    try:
        text = session.prompt("> ")
```

The sweep sits at the top of the `while True`, BEFORE `session.prompt`
(RESEARCH Discretion rec 5): check both memory files' mtimes, reload on
change, print one transcript note per change
(`Memory reloaded — STRANDS.md changed on disk.`); same boundary sweeps
`./.agent/memory/*.md` for promotion candidates (Open Question 2 —
planner picks N, suggest 3). Precedent for boundary-adjacent per-turn
lifecycle: `bind_turn(turn_id)` / `steering.bind_turn(turn_id)` /
`slot.state = steering` (lines 623-625).

**Attach 3 — memory flush on exit** (`loop.py` lines 94-107,
`explicit_save`):

```python
def explicit_save(agent: Any) -> None:
    manager = getattr(agent, "_session_manager", None)
    save = getattr(manager, "save_snapshot", None)
    if save is None:
        return
    try:
        asyncio.run(save(agent, is_latest=True))
    except Exception as exc:
        logger.warning("Explicit session save on exit failed: %s", exc)
```

Add `flush_memory(agent)` mirroring this exactly: `getattr(agent,
"memory_manager", None)` → `getattr(manager, "flush", None)` →
`asyncio.run(flush())`, guard None/missing for test doubles, log-and-never-
raise. Call it next to `explicit_save(agent)` on the exit path (line 702)
and after `/compact`/`/clear` history mutations (line 586) per Pitfall 4.

**Reply rendering** (`loop.py` lines 580-583):

```python
if action == "reply":
    if message:
        console.print(message)
```

All `/skills`, `/memory`, `/init` output flows through this — handlers
return strings, never print. Transcript notes (reload, silent-mode writes)
use `console.print` directly at the boundary.

---

### `strands_code_cli/main.py` (MOD) (config, request-response)

**Analog:** self — `build_agent` kwargs-mapping shape (lines 103-157).

**Factory-mapping pattern** (`main.py` lines 120-148):

```python
kwargs: dict[str, Any] = {
    "tools": [...],
    "builtin_tools": {
        "shell": True,
        "read": True,
        ...
    },
    "interventions": build_interventions(),
    "instructions": CODE_AGENT_INSTRUCTIONS,
    ...
}
if model is not None:
    kwargs["model"] = model
agent = create_harness(**kwargs)
```

Phase 6 additions follow the mapping-not-pin-list comment discipline
(lines 106-111): pass `skills`/`memory` explicitly (today both ride
harness defaults — RESEARCH notes `./.agent/skills` doesn't exist yet so
skills is currently a no-op), register the memory injector plugin after
`create_harness` next to `register_steering_hook(agent)` (line 154), and
keep the AWS-optional / lazy-import posture (no new required deps).

**Hook-registration adjacency** (`main.py` lines 149-156): the steering
registration + `bind_steering(slot)` + `set_mode("act")` block is where
`register_memory_plugin(agent, ...)` lands, with the same "single X"
comment discipline (one injector, like one HumanInTheLoop / one steering
hook).

---

### `tests/test_skills.py`, `tests/test_memory_file.py`, `tests/test_memory_curate.py` (NEW) (test, batch)

**Analog:** `tests/test_session_resume.py` (hermetic `tmp_path` + offline
doubles) and `tests/test_mode.py` (state-holder unit shape).

**Hermetic-filesystem pattern** (`test_session_resume.py` lines 85-88):

```python
def test_same_id_reconstruction_restores_transcript_and_state(self, tmp_path):
    session_id = str(uuid.uuid4())
    session_dir = tmp_path / "sessions"
```

Skill/memory tests build `./.agent/skills/<name>/SKILL.md` trees and
`STRANDS.md`/`.agent/MEMORY.md` files under `tmp_path` +
`monkeypatch.chdir` (the hermetic pattern RESEARCH Wave 0 mandates; the
`conftest.py` guard enforces it). No committed fixtures.

**Offline-double pattern** (`test_session_resume.py` lines 24-53,
`_ReplayModel`): model doubles implement the SDK `Model` ABC with canned
`stream()` output so curate revise-round and `/init` draft tests run with
no credentials. `dispatch` testability precedent: new branches keep
`agent=None`-safe pure functions over `SkillIndex`/file paths; agent turns
asserted via the returned `("agent", text)` tuple, never live models
(RESEARCH Test doubles note).

**Test-class grouping** (CONVENTIONS.md + `test_session_resume.py` line 84):
one `Test*` class per behavior area (`TestSkillIndex`,
`TestMemoryFileContract`, `TestCurateLoop`), `# ---...---` section banners
between areas.

## Shared Patterns

### Fail-soft read / fail-loud tamper

**Sources:** `strands_code_cli/session_index.py` (lines 69-89),
`strands_code_cli/diff_config.py` (lines 43-72)
**Apply to:** `skills.py` load, `memory_file.py` load, curate-queue sweeps

```python
# session_index.py:74-81 — the shape every read path copies
if path.is_symlink():
    raise ValueError(f"Session index must not be a symlink: {path}")
if not path.exists():
    return
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    return
```

Missing → defaults/empty. Corrupt → defaults + warning (memory
frontmatter adds a transcript note). Symlink → `ValueError`, never
followed. Unknown config keys → `ValueError` (`diff_config.py` lines
65-67).

### Atomic save + locked-down perms

**Sources:** `strands_code_cli/session_index.py` (lines 91-98),
`strands_code_cli/main.py` (lines 113-115)
**Apply to:** `memory_file.py` writes, `/init` scaffolding writes

```python
# session_index.py:96-98
tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
os.replace(tmp, path)
```

tmp + `os.replace`, never in-place writes. `.agent/` dirs `0o700`,
sidecar files `0o600` (`loop.py` `_history`, lines 82-88). Root
`STRANDS.md` keeps repo perms (interop file, not a secret).

### Turn output and transcript notes

**Sources:** `strands_code_cli/output.py` (lines 21-30),
`strands_code_cli/loop.py` (lines 580-583)
**Apply to:** all `/skills`, `/memory`, `/init` output; reload notes;
silent-mode write lines

```python
# output.py:21-30
@contextmanager
def output_context() -> Iterator[StdoutProxy]:
    """Stdout patch that preserves ANSI escapes (see module docstring)."""
    with StdoutProxy(raw=True) as proxy:
        ...
```

Handlers return strings; the loop renders via `console.print`. Prompts
inside turns (curate approve/deny) print inside `output_context()` like
`PolicyClassifier.ask` (`policy_gate.py` lines 381-382). Never bare
`print()` in library code — except the gate/ask transcript path, which
prints inside `output_context` (`policy_gate.py` lines 401-403).

### Approve/deny prompt UX (curate loop)

**Source:** `strands_code_cli/policy_gate.py` (lines 373-454)
**Apply to:** `/memory` curate surface, NL revise-round review

```python
# policy_gate.py:401-403 — full detail + one-line reason, always
print(f"Approval needed: {tool_name}")
print(f"  Detail: {_detail_line(tool_name, ctx['tool_input'])}")
print(f"  Risk: {verdict.reason}")
```

Curate proposals mirror this: full proposal text quoted + source line,
then an approve/deny prompt with NO second handler (03-SECURITY
residual). `sys.stdin.isatty()` branches to `radio_choice`
(`policy_gate.py` lines 404-420, `choice.radio_choice` defaulting to the
fail-closed index); non-tty keeps the typed `input()` path. Denials
`record` (never cover); approvals `mark`.

### Router validates, loop applies

**Source:** `strands_code_cli/router.py` (lines 92-96, 119-132)
**Apply to:** `/skills`, `/memory`, `/init`, `/<skill>` branches

`dispatch` returns `("agent"|"exit"|"reply"|"model", message)`; prompts
and approvals never live in router branches ("Approval prompts never live
here" — `router.py` lines 404-406, 435-437, 472-475). Skill invocation
returns `("agent", composed)`; mode flips and queue mutations that need
loop state go through the holder the loop owns.

### Docstring + import contract

**Sources:** AGENTS.md Conventions; `strands_code_cli/mode.py` (lines 1-10)
**Apply to:** every new module, class, and public function

Triple-double-quoted docstrings, imperative first line, `Args:`/`Returns:`
in plain text. Module docstring states the decision IDs covered
(`mode.py`: "Plan/Act session modes (MODE-01, MODE-02, D-05..D-08)").
`from __future__ import annotations` first; absolute imports rooted at
`strands_code_cli`; 4-space, double quotes, ~100–120 cols; no formatter
to save you — match by hand.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `strands_code_cli/completer.py` core `Completer` subclass | utility | event-driven | No `prompt_toolkit.completion.Completer` subclass exists in the repo; planner uses the RESEARCH-verified sketch (FuzzyCompleter + DynamicCompleter) instead |
| Memory injector `ContextInjector` render fn | provider | event-driven | Only precedent is the harness `environment` plugin (untracked `.venv` source); planner uses RESEARCH Pattern 2 + the `register_steering_hook` registration shape above |

Both gaps are covered by RESEARCH.md verified excerpts (installed-source
line citations), so no additional research is needed.

## Metadata

**Analog search scope:** `strands_code_cli/` (all 16 modules triaged;
7 read in full), `strands_code_agent/knowledge/bundle.py` (frontmatter),
`tests/test_session_resume.py` (hermetic pattern)
**Files scanned:** ~20 (16 CLI modules via listing + size check, 4 read
fully or in full-range passes: `router.py`, `loop.py`, `policy_gate.py`,
`steering.py`, `main.py`, `mode.py`, `diff_config.py`,
`session_index.py`, `choice.py`, `output.py`)
**Pattern extraction date:** 2026-10-04
