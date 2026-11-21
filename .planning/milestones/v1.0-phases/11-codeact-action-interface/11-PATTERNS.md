# Phase 11: CodeAct Action Interface - Pattern Map

**Mapped:** 2026-10-15
**Files analyzed:** 9 (2 new, 7 modified)
**Analogs found:** 9 / 9

> Provenance: produced by a `gsd-pattern-mapper` dispatch running under the
> generic-agent workaround (typed dispatch unavailable). All analog paths below
> were verified git-tracked via `git ls-files` this session.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/codeact.py` (NEW) | service (holder + stint lifecycle + prefix) | request-response | `strands_code_cli/mode.py` | exact |
| `tests/test_codeact.py` (NEW) | test | batch | `tests/test_mode.py` | exact |
| `strands_code_cli/loop.py` (MOD) | controller | request-response | itself (turn setup 2264-2289, dispatch call 2190-2206, post-turn `print_plain` 1916-1920) | exact |
| `strands_code_cli/router.py` (MOD) | route | request-response | itself (`_mode_holder`/`_mode_message` 1331-1348, `/route` branch 227-230) | exact |
| `strands_code_cli/main.py` (MOD) | config (entry/flags) | request-response | itself (`--session-id` flag 205-211, `build_agent` interpreter 119) | exact |
| `strands_code_cli/provider_config.py` (MOD) | config | file-I/O | itself (`_KNOWN_KEYS` 19, `load` 40-70, `save` 79-105) | exact |
| `strands_code_cli/skills.py` (MOD) | config | request-response | itself (`BUILTIN_SLASH_HEADS` 19-43) | exact |
| `strands_code_cli/policy_gate.py` (MOD) | middleware | request-response | itself (`_detail_line` 643-651, `_derive_rule` 361-379) + `strands_code_agent/callback_handler.py` render (110-113) | exact |
| `tests/test_policy_gate.py` (MOD) | test | batch | itself (existing ask/deny shapes) + `tests/test_mode.py` event helper | role-match |

## Pattern Assignments

### `strands_code_cli/codeact.py` (NEW; service, request-response)

**Analog:** `strands_code_cli/mode.py` (holder shape), `strands_code_cli/routing.py:2257-2317`
(RoutingState alt holder), `strands_code_cli/memory_modes.py:117-149` (third holder
confirmation — all three share VALID/set/announce verbatim).

**Imports pattern** (`mode.py:12`, `routing.py:15-32`):

```python
from __future__ import annotations
# stdlib (json/logging/os/dataclasses/pathlib/typing), then third-party
# (platformdirs, yaml), then absolute strands_code_cli.* imports — never relative.
from strands_code_cli.scope import confine, resolve
from strands_code_agent.python_environments.local_sandboxed import SandboxedPythonInterpreter
```

**Holder core pattern** (`mode.py:35-76` — mirror exactly, VALID becomes
`("tool", "code", "both")`, default `"tool"`):

```python
class ModeState:
    VALID = ("plan", "act")

    def __init__(self, initial: str = "act") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown mode {initial!r}: expected plan|act")
        self._mode = initial
        self._pending_plan = False

    @property
    def mode(self) -> str:
        return self._mode

    def set(self, mode: str) -> str:
        if mode not in self.VALID:
            raise ValueError(f"unknown mode {mode!r}: expected plan|act")
        self._mode = mode
        self._pending_plan = False
        return MODE_PLAN_REPLY if mode == "plan" else MODE_ACT_REPLY

    def announce(self) -> str:
        return MODE_PLAN_REPLY if self._mode == "plan" else MODE_ACT_REPLY
```

**Module constants pattern** (`mode.py:14-32`, `routing.py:2257-2261`): reply strings and
usage as `UPPER_SNAKE_CASE` module constants (`MODE_PLAN_REPLY`, `MODE_USAGE`,
`ROUTING_ON_REPLY`, `ROUTE_USAGE`). The new `CODEACT_PREFIX` follows the
`PLAN_PREFIX` precedent (`mode.py:14-25`, a module-level triple-quoted prompt block).

**Stint-interpreter lifecycle** (`local_sandboxed.py:12-49`): construct once with
`authorized_imports` + `additional_functions` + `timeout_seconds=60` (D-12 default);
`execute_code` returns `(stdout, stderr)`, never raises; `clear_state()` re-runs the
preamble. CodeAct owns ONE stint instance, lazy on first code turn, `clear_state()`
on every interface switch (D-17). Keep it separate from the always-on tool-turn
interpreter built in `main.py:119` (`interpreter = SandboxedPythonInterpreter("",
authorized_imports=set())`).

**Interior-function confinement** (`scope.py:22-56` + `diff_gate.py:401-403` call shape):
sync callables only (never the `async` gated wrappers at `diff_gate.py:393-394` /
`make_gated_edit`). Confine every path via the shared seam:

```python
# Source: strands_code_cli/scope.py:22-56 (resolve + confine) and the
# diff_gate.py:401-403 application shape inside gated_write.
old_text = await _current_text(
    str(confine(resolve(path, cwd), cwd, _policy_roots(cwd))), reader, tool_context
)
```

Interior `read` mirrors `_fs_read` semantics (`diff_gate.py:213-217`: missing file
returns None, never raises); interior `write` mirrors `_fs_write` (`diff_gate.py:220-223`:
`target.parent.mkdir(parents=True, exist_ok=True)` then write). Interior `shell` uses
stdlib `subprocess` argv-list, no `shell=True` (no in-repo sync precedent — planner
uses RESEARCH.md; keep it a plain function in `codeact.py`).

**Error handling pattern:** holder raises `ValueError` on unknown values (programmer
error, `mode.py:47-48`); interior functions return error strings / None like the
`(stdout, stderr)` tuple contract (`local_sandboxed.py:39-49`), never raise into the
executor. Fail-soft read paths per AGENTS.md.

---

### `strands_code_cli/loop.py` (MOD; controller, request-response)

**Analog:** itself — holder ownership, dispatch wiring, per-turn prefix, post-turn label.

**Holder ownership pattern** (`loop.py:2072-2096` — `run_loop` constructs all holders):

```python
mode = ModeState()
# ... RoutingState(initial=...) from boot strategy, MemoryModeState(initial=...) ...
memory_mode = MemoryModeState(initial=initial_mode)
curate_queue = CurateQueue()
```

CodeAct adds `interface = CodeactState(initial=...)` here (`"tool"` unless `--codeact`
flag or remember-last config says otherwise).

**Dispatch wiring pattern** (`loop.py:2190-2206`): pass the loop-owned holder as a keyword
alongside the existing holders:

```python
action, message = dispatch(
    text,
    session_id=session_id,
    index=index,
    mode=mode,
    ...
    routing=routing,
    routing_events=routing_events,
)
```

**Per-turn prefix + fix-at-send pattern** (`loop.py:2264-2289`): resolve interface once
before `_invoke_agent`, next to the mode/routing hooks; shape code turns via prefix:

```python
bind_turn(turn_id)
steering.bind_turn(turn_id)
slot.state = steering
set_gate_mode(mode.mode)
reader = start_steering_reader(...)
agent_text = message if message is not None else text
if mode.mode == "plan":
    agent_text = f"{PLAN_PREFIX}\n\n{agent_text}"
current_model = _route_pre_turn(...)
```

(CodeAct: `if interface resolves to code: agent_text = f"{CODEACT_PREFIX}\n\n{agent_text}"`.
The revise-round path repeats the prefix at `loop.py:1901-1902`:
`if mode.mode == "plan": follow_up = f"{PLAN_PREFIX}\n\n{follow_up}"` — planner decides
whether code turns need the same repeat.)

**Post-turn label pattern** (`loop.py:1916-1920` — the D-15 site):

```python
usage = record_turn_metrics(
    follow_result, current_model, session_turns, model=getattr(agent, "model", None)
)
if usage is not None:
    print_plain(console, usage, style="dim")
```

D-15 rides the same site with one more `print_plain` line; D-16 = do not touch
`session_turns` row shape or `cost_report`. Import precedent: `from
strands_code_cli.output import output_context, print_plain` (`loop.py:81`),
`from strands_code_cli.mode import PLAN_PREFIX, ModeState` (`loop.py:66`).

**Error handling pattern** (`loop.py:2230`, `loop.py:1910-1912`): failed pre-turn work
never kills the session — `except Exception as exc: print_plain(console, f"... ({exc});
...")` with `# noqa: BLE001` where the broad catch is deliberate.

---

### `strands_code_cli/router.py` (MOD; route, request-response)

**Analog:** itself — `_mode_holder`/`_mode_message` (1331-1348), `/route` branch (227-230),
`USAGE_HINT` (51-60).

**Holder-or-throwaway + reply-only branch pattern** (`router.py:1331-1348`):

```python
def _mode_holder(mode: ModeState | None) -> ModeState:
    """Loop-owned holder when present, else a throwaway Act default."""
    return mode if mode is not None else ModeState()


def _mode_message(rest: str, mode: ModeState | None) -> str:
    """Handle /mode: report, switch with announcement, or usage — replies only.

    No agent turn ever leaves this branch; approval prompts never live
    here (established reply-only pattern).
    """
    holder = _mode_holder(mode)
    verb = rest.strip().lower()
    if not verb:
        return holder.announce()
    if verb in ("plan", "act"):
        return holder.set(verb)
    return _MODE_USAGE
```

**Dispatch signature pattern** (`router.py:104-124`): new holder arrives as an optional
kwarg with a documented None default, e.g. `routing: RoutingState | None = None`
(`router.py:122`) plus docstring paragraph (`router.py:160-162`: "Session-sticky routing
toggle ... (None → throwaway off holder, keeping standalone/test behaviour without a
loop-owned holder)."). `RoutingState` is imported under `TYPE_CHECKING` (`router.py:47-49`)
to avoid a runtime cycle — follow the same for the CodeAct holder.

**Branch placement pattern** (`router.py:227-230`): builtin branches sit BEFORE the
skills-dynamic branch (`router.py:231`) so the builtin always wins the name:

```python
if cmd == "/route":
    # Before the skills-dynamic branch so the builtin always wins
    # the name (a skill named route stays shadowed).
    return ("reply", _route_message(rest, routing))
```

**USAGE_HINT pattern** (`router.py:51-60`): parenthesized implicit-concat string listing
every command; add `/codeact [tool|code|both]` in the same style (note `/route
[on|off|status|setup|validate]` at line 56 as the closest toggle entry).

---

### `strands_code_cli/main.py` (MOD; config, request-response)

**Analog:** itself — `--session-id` typer flag (205-211), `build_agent` interpreter (119).

**Startup-flag pattern** (`main.py:205-211`):

```python
@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,  # noqa: F841 - callback signature requires the context slot
    session_id: str | None = typer.Option(
        None, "--session-id", help="Resume the session with this id."
    ),
) -> None:
```

`--codeact` follows the same `typer.Option` shape. Validation precedent (`main.py:213-217`):
fail-loud with `typer.BadParameter` before any session/config side effect. Config-load
precedent (`main.py:221`): `config = ProviderConfig.load()` after the credential gate.

**Always-on interpreter note** (`main.py:119` + `main.py:130-136`): the tool-turn
`python_repl` stays registered via `interpreter.get_tool()` in the `tools` list — the
CodeAct stint interpreter is a SEPARATE instance (Pitfall 3); do not touch this site
except to keep it intact.

---

### `strands_code_cli/provider_config.py` (MOD; config, file-I/O)

**Analog:** itself — `_KNOWN_KEYS` (19), dataclass (27-37), `load` (40-70), `save` (79-105).
(`memory_modes.py:35-99` confirms the same fail-soft-load / atomic-save / 0o700 shape for a
second config file.)

**Key-extension pattern** — extend all three together or `load` fails loud (`provider_config.py:61-63`):

```python
_KNOWN_KEYS = {"model", "base_url"}  # add the codeact key(s) here

# load: unknown = set(data) - _KNOWN_KEYS → raise ValueError (lines 61-63)
# then per-key type checks raising ValueError on non-strings (lines 64-69)
```

**Atomic-save pattern** (`provider_config.py:100-105`): `mkdir(parents=True, exist_ok=True)`
→ `os.chmod(parent, 0o700)` → write `resolved.with_suffix(".yaml.tmp")` → `os.replace`.
Symlink refusal at both ends (`provider_config.py:47-48`, `93-94`).

---

### `strands_code_cli/skills.py` (MOD; config, request-response)

**Analog:** itself — `BUILTIN_SLASH_HEADS` (`skills.py:19-43`).

```python
BUILTIN_SLASH_HEADS = frozenset(
    {
        "exit",
        ...
        "btw",
        "route",
    }
)
"""Builtin slash heads (no leading slash) that always win collisions (D-02).

Mirrors the ``dispatch`` branches.
"""
```

Add `"codeact"` (and `"code"`/`"tool"` if the planner picks one-shot routing prefixes —
Pitfall 7) as bare heads, no leading slash. Shadow detection is automatic via
`skill.name.lower() in BUILTIN_SLASH_HEADS` (`skills.py:108`).

---

### `strands_code_cli/policy_gate.py` (MOD; middleware, request-response)

**Analog:** itself (`_detail_line` 643-651, `_dialog_title` 658-672, `_derive_rule` 361-379)
+ `strands_code_agent/callback_handler.py:110-113` for the full-code render.

**Truncation site to extend** (`policy_gate.py:643-651`):

```python
def _detail_line(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Exact command/code/path shown in the prompt (D-01 full detail)."""
    if tool_name == "shell":
        return str(tool_input.get("command", ""))[:500]
    if tool_name == "python_repl":
        return str(tool_input.get("code", ""))[:500]
    if "path" in tool_input:
        return str(tool_input.get("path", ""))[:500]
    return str(tool_input)[:500]
```

D-05 work: render the FULL code block (not `[:500]`) at the `python_repl` prompt.
Keep `_dialog_title`'s 60-char collapse (`_DIALOG_DETAIL_CHARS = 60`,
`policy_gate.py:654-672`) byte-identical.

**Full-code render pattern** (`callback_handler.py:110-113`):

```python
if name in self.code_tools:
    language = self.code_tools[name]
    syntax = Syntax(tool_use['input']['code'], language)
    self.console.print(syntax)
```

Reuse `rich.syntax.Syntax(body, "python")`; console prints inside `output_context`.

**Rule-derivation pattern — unchanged** (`policy_gate.py:368-372`): Always/Never already
derives narrow `python_repl` prefix rules; D-07 rides this with zero changes:

```python
if tool_name == "python_repl":
    code = tool_input.get("code", "")
    if isinstance(code, str) and code.strip():
        return Rule(tool="python_repl", command=normalise_command(code)[:500])
    return None
```

Do not build fuzzy code matching — prefix semantics are the locked one-rule-system
behavior.

---

### `tests/test_codeact.py` (NEW; test, batch)

**Analog:** `tests/test_mode.py` (structure, holder tests, router dispatch tests, vocabulary
guards).

**File header pattern** (`test_mode.py:1-41`): module docstring naming the phase + tracer
observations + invariants pinned. Test-file naming follows `test_<module>.py`
(`test_codeact.py` ↔ `codeact.py`, AGENTS.md convention).

**Import pattern** (`test_mode.py:43-66`):

```python
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from strands.interventions.actions import Confirm, Proceed
from strands.vended_interventions.hitl import HumanInTheLoop

from strands_code_cli.mode import (...)
from strands_code_cli.policy import PolicyConfig, PolicyOptions
from strands_code_cli.policy_gate import PolicyClassifier
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
```

**Fake-event helper pattern** (`test_mode.py:80-89`): `SimpleNamespace` agent/tool_use
shim for classifier tests without a live model:

```python
class _FakeAgent:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def _event(name: str, tool_input: dict[str, Any], agent: Any = None, uid: str = "t1"):
    return SimpleNamespace(
        agent=agent if agent is not None else _FakeAgent(),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )
```

**Vocabulary-guard pattern** (`test_mode.py:69-77`): `BANNED_VOCAB` tuple asserting
replies never leak foreign vocabulary — CodeAct tests add an analogous guard (e.g.
code replies never leak policy-rule words).

**Test classes:** `PascalCase` grouping per behavior area (`TestCodeAgentSystemPrompt`
style, AGENTS.md); RESEARCH test map (`-k toggle/startup/turn_setup/both/approval/
deny/stint/label/history/interior`) defines the areas.

---

### `tests/test_policy_gate.py` (MOD; test, batch)

**Analog:** itself + `tests/test_mode.py` event helper. Extend with full-code preview
render assertions for `python_repl` prompts (Wave 0 gap): assert the approval prompt
carries the complete code block (no `[:500]` cut) while the dialog title keeps its
60-char collapse. Reuse the existing ask/deny test shapes in that file
(`test_ask_error_returns_deny` shape referenced by `test_mode.py:29`).

---

## Shared Patterns

### Session-Sticky Holder (VALID/set/announce)

**Source:** `strands_code_cli/mode.py:35-76` (primary), `strands_code_cli/routing.py:2264-2317`,
`strands_code_cli/memory_modes.py:117-149`
**Apply to:** `codeact.py` holder, `/codeact` router branch, loop ownership

Three independent holders share the shape verbatim: `VALID` tuple, `__init__` with
`ValueError` on unknown, `set()` returning the transcript announcement, `announce()`
for the bare command. Loop owns one instance; router takes `... | None = None` and
falls back to a throwaway default.

### Reply-Only Slash Branches

**Source:** `strands_code_cli/router.py:1336-1348` (`_mode_message` docstring)
**Apply to:** `/codeact` branch (and `/code`/`/tool` prefixes if chosen)

"No agent turn ever leaves this branch; approval prompts never live here." Branches
return `("reply", text)` and sit before the skills-dynamic branch (`router.py:231`).

### Per-Turn Input Prefix

**Source:** `strands_code_cli/mode.py:14-25` (`PLAN_PREFIX`) + `strands_code_cli/loop.py:2273-2275`
**Apply to:** CodeAct turn shaping (`CODEACT_PREFIX`)

```python
agent_text = message if message is not None else text
if mode.mode == "plan":
    agent_text = f"{PLAN_PREFIX}\n\n{agent_text}"
```

Never mutate persistent agent state for a per-turn choice — the prefix keeps the choice
invocation-scoped (this is also what makes D-20 history preservation trivially true).
Prompt-wording tone precedent: `CODE_AGENT_INSTRUCTIONS`
(`strands_code_agent/code_agent.py:16-29`) — short imperative paragraphs, tool names in
backticks, absolute-path + scope rules stated explicitly.

### Whole-Block Approval via Single HITL

**Source:** `strands_code_cli/policy_gate.py` (classifier + `_detail_line` + `_derive_rule`),
`strands_code_cli/main.py:148-151` ("The single HumanInTheLoop ... never a second instance")
**Apply to:** `policy_gate.py` preview render only

No second gate, no second rule store (`policy.toml` carries across switches, D-18).
Denial returns the standard skip-and-continue verdict so the turn stays alive (D-06).

### Transcript Output via `print_plain`

**Source:** `strands_code_cli/loop.py:81` (import), `loop.py:1916-1920` (post-turn site)
**Apply to:** interface labels (D-15), `/codeact` announcements

All dynamic transcript text routes through `print_plain(console, text)` (markup off).
`rich.Syntax` is the code-render vehicle (`callback_handler.py:110-113`).

### Config Persistence (platformdirs YAML)

**Source:** `strands_code_cli/provider_config.py:22-24,40-105`
**Apply to:** CodeAct config key + D-03 remember-last global option

`platformdirs.user_config_dir("strands-code")` home, never repo-relative; fail-soft
load (missing/corrupt → defaults) but fail-loud on unknown keys and symlinks;
atomic tmp+`os.replace` save with 0o700 home.

### Path Confinement

**Source:** `strands_code_cli/scope.py:22-56` (`resolve` + `confine`), applied in
`strands_code_cli/diff_gate.py:401-403`
**Apply to:** interior `read`/`write`/`edit` functions

cwd + subdirs, `/tmp` + subdirs, plus policy-granted roots; symlinks resolved via
realpath; out-of-scope raises `ValueError` naming the allowed roots.

### Executor Tuple Contract

**Source:** `strands_code_agent/python_environments/base.py:37-55` (`get_tool` observation
formatting), `strands_code_agent/python_environments/local_sandboxed.py:39-49`
**Apply to:** stint interpreter use, interior function returns

`execute_code` returns `(stdout, stderr)`, never raises; observation formats via
`STDOUT:`/`STDERR:` labels or `"Code executed successfully."` when both are empty.
No new logging on the REPL observation path (AGENTS.md).

### Test Fakes over Live Models

**Source:** `tests/test_mode.py:80-89` (`_FakeAgent` + `_event`)
**Apply to:** `tests/test_codeact.py`, `tests/test_policy_gate.py` extensions

All offline, no live Bedrock: `SimpleNamespace` events, throwaway holders, tmp-path
config overrides. Run: `.venv/bin/python -m pytest tests/test_codeact.py -q`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `strands_code_cli/codeact.py` (interior `shell()` impl) | service | request-response | No sync argv-list `subprocess` wrapper exists in-repo; planner uses RESEARCH.md guidance (no `shell=True`, command visible in approved block) |
| `strands_code_cli/router.py` (both-mode per-ask routing gesture) | route | request-response | No per-ask branching exists on the send path; planner must specify (RESEARCH recommends `/code <ask>` / `/tool <ask>` one-shot prefixes composing with the `("agent", composed)` contract) |

## Metadata

**Analog search scope:** `strands_code_cli/` (mode, routing, router, loop, main,
provider_config, skills, policy_gate, diff_gate, scope, memory_modes),
`strands_code_agent/` (code_agent, callback_handler, python_environments/base,
python_environments/local_sandboxed), `tests/` (test_mode, test_policy_gate)
**Files scanned:** ~20 (targeted reads + grep-located sections; large files via
non-overlapping offset reads only)
**Pattern extraction date:** 2026-10-15
**Dispatch note:** generic-agent workaround — typed `gsd-pattern-mapper` dispatch
unavailable; role contract (`~/.codex/agents/gsd-pattern-mapper.md`) followed inline,
read-only except this file.
