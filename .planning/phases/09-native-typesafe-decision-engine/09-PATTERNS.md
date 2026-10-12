# Phase 9: Native TypeSafe Decision Engine - Pattern Map

**Mapped:** 2026-10-12
**Files analyzed:** 9 (7 extend/touch + 2 test-group entries covering 3 test files)
**Analogs found:** 9 / 9
**Dispatch note:** Produced by gsd-pattern-mapper 09 via the generic-agent workaround (typed dispatch unavailable); results labeled accordingly.

> Every Phase 9 change extends an existing Phase 8 file in place — there are no
> brand-new modules. Each analog below is therefore the file itself (same-file
> extension), with the exact sections to mirror cited by line number.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/routing.py` (native transport + ordered chain + schema) | service | request-response | `strands_code_cli/routing.py` (`decide_via_openrouter`, `_post_decision`, `_parse_engine`, `_chain_for`) | exact (same-file) |
| `strands_code_cli/router.py` (setup native branch + validate live-ping) | controller | request-response | `strands_code_cli/router.py` (`_route_setup_message`, `_setup_pick_decision`, `_route_validate_message`) | exact (same-file) |
| `strands_code_cli/cost_context.py` (native spend rendering) | utility | transform | `strands_code_cli/cost_context.py` (`_routing_line`, `_reported_spend`) | exact (same-file) |
| `strands_code_cli/loop.py` (D-03 skip-note rendering, maybe) | controller | event-driven | `strands_code_cli/loop.py` (pre-turn routing hook ~1399-1473) + `routing.py` `format_hold_line` | role-match |
| `scripts/route-probe.py` (`--run native` + native faults) | utility | batch | `scripts/route-probe.py` (`run_probe`, `_FaultContext`, `cmd_run`) | exact (same-file) |
| `evals/routing-probe/baseline.json` (native run section) | config | file-I/O | `evals/routing-probe/baseline.json` (`verdicts.openrouter` record shape) | exact (same-file) |
| `docs/ROUTING.md` (native engine docs) | config | file-I/O | `docs/ROUTING.md` (Concepts/Quick start sections) | exact (same-file) |
| `tests/test_routing.py` + `tests/test_routing_strategy.py` (native/chain/strategy tests) | test | batch | themselves (`_FakeResponse`, `_with_preflight`, `monkeypatch` seams) | exact (same-file) |
| `tests/test_loop_routing.py` (skip-note / setup-validate hook tests) | test | batch | itself + `tests/test_routing.py` stub helpers | role-match |

## Pattern Assignments

### `strands_code_cli/routing.py` (service, request-response)

**Analog:** `strands_code_cli/routing.py` itself — OpenRouter transport + chain + schema (all git-tracked).

**Imports pattern** (lines 15-34):

```python
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import platformdirs
import yaml

from strands_code_cli.cost_context import (
    cost_for,
    estimate_messages_tokens,
    price_for,
)
from strands_code_cli.model_switch import supports_reasoning

logger = logging.getLogger(__name__)
```

Conventions: stdlib first, one import per line, absolute `strands_code_cli.*`
imports, module `logger`. `urllib.request`/`urllib.error` import lazily
*inside* functions (`_post_decision` line 1069, `_retryable_error` line 963,
`_preflight_get` line 1167) — copy that for the native path (no new top-level
imports needed).

**Constants pattern** (lines 43-105) — new native constants slot here:

```python
DECISION_TIMEOUT_SECONDS = 10
"""Per-engine network ceiling; a slow decision call holds, never blocks."""

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
"""Default decision engine transport (D-06)."""
```

Add `TYPESAFE_DECISIONS_URL` + `TYPESAFE_INPUT_USD_PER_MTOK` beside
`OPENROUTER_DECISIONS_URL` with the same one-line docstring style.
`_RETRYABLE_STATUS` (line 71) already covers 429/529 — no change.
`_ENGINE_KEYS` (line 105) gains `native_model` (+ ordered-list key per planner).

**Core transport pattern — `decide_via_openrouter`** (lines 1087-1138), the
verbatim template for `decide_via_typesafe`:

```python
def decide_via_openrouter(
    *,
    decision_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not decision_model:
        return EngineResult(answers=None)
    payload, truncated = _fit_decision_payload(
        {"model": decision_model, "state": state, "questions": questions}
    )
    data, error = _post_decision(
        OPENROUTER_DECISIONS_URL,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
        timeout,
    )
    if data is None:
        return EngineResult(answers=None, error=error, truncated=truncated)
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return EngineResult(
            answers=None, error="invalid body", truncated=truncated
        )
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    model = data.get("model")
    return EngineResult(
        answers=answers,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cost=_cost(usage.get("cost")),
        model=model if isinstance(model, str) else None,
        truncated=truncated,
    )
```

Copy points: keyword-only args, env key at call time + fail-soft
`EngineResult(answers=None)`, `_fit_decision_payload` then shared
`_post_decision`, `answers`-must-be-dict guard, `_count`/`_cost` usage
helpers, snapshot `model` passthrough. Native delta per RESEARCH: no
`cost` in usage (compute `input_tokens × rate` or None), key name
`TYPESAFE_API_KEY`. Note `decide_via_ollama` (lines 1231-1286) shows the
`cost=None` variant ("rendered as zero, never estimated").

**Shared POST + retry pattern — `_post_decision`** (lines 1058-1084):

```python
def _post_decision(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> tuple[dict[str, Any] | None, str | None]:
    body = json.dumps(payload).encode("utf-8")
    for attempt_no in range(2):
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — every failure class holds
            if attempt_no == 0 and _retryable_error(exc):
                continue
            return None, _failure_reason(exc)
        if not isinstance(data, dict):
            return None, "invalid body"
        return data, None
```

Reuse unchanged — native passes its own URL/headers. Retry class comes from
`_retryable_error` (lines 957-971, retryable codes + timeouts only, 4xx
holds); failure classes from `_failure_reason` (lines 991-1018,
`HTTP <code>`/`timeout`/`refused`/`unreachable`/`invalid body` — never
secrets).

**Schema-parse pattern — `_parse_engine`** (lines 250-292): fail-soft
normalize with `logger.warning` on unknown keys / wrong types, string-only
loop over known keys, sentinel validation with fallback. The ordered-engines
list + `native_model` + note knob extend this function; keep the
warn-and-default posture (strict judging lives in `validate_strategy`).

**Validate pattern — `validate_strategy`** (lines 603-812): file-only judge
returning `ValidationReport(valid, source, lines)`; every failure line pairs
with a `fix: ...` line. Engine branch shape (lines 746-797): per-primary
model-presence checks, catalog lookup via `_cached_decision_ids()` with an
"unchecked when cache unreachable" graceful line. Native file-checks go
here; the D-07 live-ping is a NEW network branch in
`router._route_validate_message` (see below), NOT in this function.

**Chain pattern — registry + `_chain_for`** (lines 1406-1523):

```python
EngineAttempt = Callable[
    [RoutingStrategy, dict[str, Any], dict[str, Any]], EngineResult | None
]
"""One engine try: (strategy, state, questions) -> result or None when skipped."""

def _openrouter_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """OpenRouter chain link: None without a configured decision model."""
    decision_model = strategy.engine.decision_model
    if not decision_model:
        return None
    return decide_via_openrouter(
        decision_model=decision_model, state=state, questions=questions
    )
```

`None` = skipped-never-attempted (the `_decide_effort` loop `continue`s on
it, line 1568-1569); `EngineResult(answers=None, error=...)` = attempted and
failed. The native link mirrors `_openrouter_attempt`; `_chain_for` (lines
1494-1523) generalises primary-select to the ordered list. Per-link verdict
details come from `_link_detail` (lines 1464-1481: `unready`, `HTTP <code>`
→ `<engine> <code>`, transport classes, legacy `<engine> failed`).

**Error-handling pattern:** fail-soft everywhere — loader warns and defaults
(`_parse_knob` lines 295-313), transports return answers-None, preflight
returns None on any failure (`_preflight_get` line 1175). Only programmer
errors raise (`save_strategy` ValueError on bad scope/symlink/zero
candidates, lines 433-486; symlink `ValueError` in `_load_one`).

---

### `strands_code_cli/router.py` (controller, request-response)

**Analog:** `strands_code_cli/router.py` itself — setup dialog + validate (git-tracked).

**Imports pattern** (lines 4-10 + lazy function imports): top-level stdlib
(`asyncio`, `os`, `shutil`, `sys`, `pathlib`, `typing`), third-party
(`typer`), absolute `strands_code_cli.*` imports. Routing imports are LAZY
inside handlers (`from strands_code_cli.routing import save_strategy` at
`_route_setup_message` line 956; `validate_strategy` at
`_route_validate_message` line 1036; `live_pricing` fetchers lines 954-955).
Native setup/validate additions follow the same lazy-import shape.

**Setup picker pattern — `_setup_ask`** (lines 710-744): radio on tty via
`strands_code_cli.choice.radio_choice`, numbered typed prompt off-tty; ALL
abort paths (ESC/empty/EOF/Ctrl-C/unparseable) fail closed to `None` and the
caller returns `_SETUP_ABORTED` ("Setup cancelled — no changes written.",
line 583). Engine-order + pinned-Jev picks reuse this directly.

**Decision pick pattern — `_setup_pick_decision`** (lines 841-895): tty radio
over entries, off-tty typed id with one re-prompt then fail-closed. The D-05
pinned native list (`jev-1.13.0` + `jev-latest`, NOT `jev-1.13`) is a small
static-entries call to this same shape — no catalog fetch.

**Local-model prompt pattern — `_setup_local_model`** (lines 898-913):
single typed prompt with a bracketed default on empty line, EOF/Ctrl-C
aborts. Template for any native typed fallback.

**Setup flow pattern — `_route_setup_message`** (lines 944-1031): sequential
scope → engine → candidates → decision → directives prompts, each
`None`-checked to `_SETUP_ABORTED`; catalog fetches wrapped in bare
`try/except Exception → None` with typed-id fallback paths; payload dict
assembled then one atomic `save_strategy(payload, scope)`; failure returns
`"Setup failed — {exc} (nothing written)."`; success prints counts + engine +
decision model + "Run /route validate to check the file." Native branch
slots in: availability detection (`os.environ.get("TYPESAFE_API_KEY")` —
note `os` is ALREADY imported top-level in router.py, line 6), D-02 default
order proposal, hidden-until-key native option (D-06), pinned list pick.

**Validate pattern — `_route_validate_message`** (lines 1034-1038):

```python
def _route_validate_message() -> str:
    """Print the strategy validity report; never mutates, never fetches."""
    from strands_code_cli.routing import validate_strategy

    return validate_strategy().format()
```

D-07 ADDS a network live-ping here (the "never fetches" docstring updates):
cheap `decide_via_typesafe` call, map 401/403 → bad/missing-key line,
400 → wrong-model line, answers → ok line. Keep the report-string return
shape so `_route_message` dispatch is untouched.

---

### `strands_code_cli/cost_context.py` (utility, transform)

**Analog:** `strands_code_cli/cost_context.py` itself — reported-spend rendering (git-tracked).

**Spend pattern — `_reported_spend` + `_routing_line`** (lines 182-222):

```python
def _reported_spend(event: dict[str, Any]) -> float | None:
    """Reported decision USD spend (None when absent or non-numeric)."""
    spend = event.get("decision_cost")
    if isinstance(spend, bool) or not isinstance(spend, (int, float)):
        return None
    return float(spend)
```

`_routing_line` renders `via {engine}` + `${spend or 0.0:.4f}` — None
currently means local/zero. Native is the first paid-but-costless engine:
per the planner's spend pick this file gains EITHER nothing (if cost is
computed into `EngineResult.cost` upstream in routing.py — rendering then
works verbatim, plus a provenance note) OR an explicit unknown-spend cell.
Also note `cost_report` (lines 225-303): routing spend folds into session
totals via `_reported_spend`, and `Prices:` provenance lines derive from
`price_provenance(decision_model)` — a code-computed native cost needs its
provenance marked (RESEARCH recommends).

---

### `strands_code_cli/loop.py` (controller, event-driven)

**Analog:** `strands_code_cli/loop.py` pre-turn routing hook (~lines 1399-1473)
+ `routing.py` line formatters (git-tracked).

**Hook pattern:** pre-turn at idle calls `routing_mod.decide(...)`, prints the
hold note via `routing_mod.format_hold_line(current=..., detail=...)` (line
1473), and pause-checks via `routing_mod.is_pause_detail(detail)` (line
1456). Hold/failure notes ALWAYS print, even under `quiet: true` (docstring
lines 1410-1411). D-03 skip-notes slot here or in the verdict detail: one
line per skipped keyless/unready link, suppressible via the planner's knob.
Transcript line shapes to reuse:

```python
# routing.py lines 1948-1955
def format_hold_line(*, current: str, detail: str) -> str:
    return f"Routing held on {current} ({detail}; retrying next ask)"
```

(`format_routed_line`, lines 1913-1945, is the routed-line sibling with
`·`-joined note suffixes — the `·`-suffix style is the template for any
inline skip note.)

---

### `scripts/route-probe.py` (utility, batch)

**Analog:** `scripts/route-probe.py` itself (git-tracked, 668 lines).

**Production-import pattern** (lines 88-129): `_ensure_production_imports()`
re-execs under `uv run` when the direct import fails (guard
`_ROUTE_PROBE_REEXEC`), then imports builders/transports/gate from
`strands_code_cli.routing` — "no duplicated decision logic" (module
docstring line 8). `--run native` imports `decide_via_typesafe` the same
way. Module pins live at lines 55-57 (`DECISION_MODEL_PIN`,
`LOCAL_MODEL_PIN`, `LOCAL_MODEL_FALLBACK`) — add `NATIVE_MODEL_PIN =
"jev-1.13.0"`.

**Fault pattern — `_FaultContext`** (lines 222-262): context manager applying
one fault around a single engine call and restoring after; env-key faults
save/pop/restore `os.environ`:

```python
elif fault == "bad-key" and self._engine == "openrouter":
    self._saved["OPENROUTER_API_KEY"] = os.environ.get(
        "OPENROUTER_API_KEY"
    )
    os.environ["OPENROUTER_API_KEY"] = "probe-bogus-key"
elif fault == "no-key" and self._engine == "openrouter":
    self._saved["OPENROUTER_API_KEY"] = os.environ.get(
        "OPENROUTER_API_KEY"
    )
    os.environ.pop("OPENROUTER_API_KEY", None)
```

Native faults (`bad-key`/`no-key` on `TYPESAFE_API_KEY`, `unknown-model`,
shared `timeout`) mirror these arms with the engine guard `"native"`.
Bogus values only, never the real key (module docstring lines 30-33).

**Run pattern — `run_probe` + `cmd_run`** (lines 270-510): fixed
`calibration_strategy` + shared builders + gate; record dict carries
`probe/category/engine/pin/snapshot/question/fault/tokens/cost/table/top1/
top1_prob/margin/gated/tie_break/detail/match`; non-fault no-answers fails
loudly (lines 502-508). Native path: third engine arm in `run_probe`'s
dispatch (lines 308-330), `--run` choices gain `"native"` (line 623), cloud
runs skip daemon resolve (lines 473-479 — native likewise skips it).
`cmd_compare`'s `run_paths` (lines 660-663) gains the native run file; the
`verdicts` baseline structure already keys per engine.

---

### `evals/routing-probe/baseline.json` (config, file-I/O)

**Analog:** itself — top-level keys `catalog/derivation/derived/
distributions/generated/local_note/pins/probe_count/probe_file/snapshots/
verdicts`; `verdicts` keys per engine (`local`, `openrouter`). The native
run records the same per-probe verdict shape under `verdicts.native` plus
pin/snapshot entries, per D-09/D-10 (shared knobs unless probes prove
divergence; disagreement = bug per D-11).

---

### `docs/ROUTING.md` (config, file-I/O)

**Analog:** itself (git-tracked). Structure: Concepts bullets (Strategy,
Decision calls, Engines, Gate, Override, Visibility, Tie-break) → Quick
start (`/route setup` → `/route validate` → ask) → Example strategies.
Native extension: Engines bullet gains the TypeSafe-native third engine
(`POST /v1/systemone`, `TYPESAFE_API_KEY`, pinned `jev-1.13.0`), Quick
start notes the user-ordered engine list + default-order proposal, plus a
cost-provenance note per the planner's spend pick.

---

### `tests/test_routing.py` + `tests/test_routing_strategy.py` (test, batch)

**Analog:** themselves (git-tracked). Conventions: module docstring states
the hermetic posture ("No live decision calls: the urllib seam serves
canned Decision-API payloads"), `Test*` classes group one behavior area,
PascalCase class per area not per method.

**Stub pattern — `_FakeResponse` + `_http_error`** (test_routing.py lines
115-132):

```python
class _FakeResponse:
    """Minimal urlopen context manager serving a canned JSON payload."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(OPENROUTER_DECISIONS_URL, code, "boom", {}, None)
```

Native transport/fault tests reuse `_FakeResponse` verbatim and parameterise
`_http_error` over the native matrix (400/401/403/422 hold zero-retry;
429/529/5xx retry-once). Env-key hermeticity via `monkeypatch.setenv/
delenv("TYPESAFE_API_KEY", ...)`; stub seams via
`monkeypatch.setattr(routing_mod, ...)` (cf. `price_for` stubbing, lines
218-226). Live native tests go behind the `integration` marker (deselected
by default per `pyproject.toml`).

---

### `tests/test_loop_routing.py` (test, batch)

**Analog:** itself + `tests/test_routing.py` stub helpers (role-match).
Covers the hook-level behaviors: D-03 skip-note emission/suppression, pause
semantics, transcript-line shapes. Reuse `_FakeResponse` + `monkeypatch`
env control from `test_routing.py` rather than inventing new stubs.

---

## Shared Patterns

### Env-Key-At-Call-Time (D-04 posture)

**Source:** `strands_code_cli/routing.py` lines 1104-1106 (+ `decide_via_ollama`
base resolution line 1147, `_ollama_headers` lines 1159-1161)
**Apply to:** `decide_via_typesafe`, `native_engine_ready`, setup
availability detection, probe faults

```python
api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key or not decision_model:
    return EngineResult(answers=None)
```

Header-only `Authorization: Bearer`, never logged, never persisted;
`save_strategy` drops api_key-shaped keys top-level + inside `engine`
(lines 404-476). `TYPESAFE_API_KEY` joins this exact exception list.

### Fail-Soft Read Paths

**Source:** `strands_code_cli/routing.py` (`_parse_knob` lines 295-313,
`_load_one` lines 357-373, `local_engine_ready` lines 1190-1228)
**Apply to:** ordered-list loader (legacy `primary` maps to equivalent
order), native readiness, catalog lookups

Warn-and-default on wrong shapes; `None`/`False` on unreadable/unready;
strictness lives only in `validate_strategy` (INVALID + fix lines) and
`save_strategy` (ValueError backstops).

### Logger + Why-Comments + Docstrings

**Source:** all modules (`logger = logging.getLogger(__name__)` with
`%s`-style args); docstrings on every public function/class; 1-2 line
why-comments only. No `print()` in library code — transcript prints live
in the turn layer via `print_plain` (router.py setup dialogs are the
presentation-layer exception, using `print`/`input` directly).

### Naming

**Source:** AGENTS.md + codebase. `snake_case` modules/functions,
`UPPER_SNAKE_CASE` constants, `PascalCase` classes; test files mirror
modules (`tests/test_<module>.py`); absolute imports rooted at
`strands_code_cli`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| *(none)* | — | — | Every Phase 9 file extends an existing Phase 8 analog in place. The genuinely new concepts (ordered engines list, native transport, skip-note suppression knob) all have same-file templates: `_ENGINE_REGISTRY`/`_chain_for` for the chain, `decide_via_openrouter` for the transport, `quiet` bool knob (`_parse_strategy` lines 338-341) for the suppression knob shape. |

Note for planner: the user-ordered engines list has no *exact* prior
(primary-select is a scalar, not a list), but `_chain_for`'s `names` list
construction (lines 1509-1522) is already list-driven internally — the
migration is to drive it from strategy data instead of the scalar.

---

## Metadata

**Analog search scope:** `strands_code_cli/` (routing.py 2046 lines via
targeted non-overlapping reads, router.py setup/validate ranges,
cost_context.py spend ranges, loop.py hook grep), `scripts/route-probe.py`
(full 668-line read), `evals/routing-probe/baseline.json` (shape probe),
`docs/ROUTING.md` (head), `tests/test_routing.py` (stub helpers + style)
**Files scanned:** 9
**Pattern extraction date:** 2026-10-12
**Tracked-source gate:** all analog paths verified via `git ls-files`
(routing.py, router.py, cost_context.py, loop.py, btw.py, route-probe.py,
ROUTING.md, baseline.json, test_routing.py, test_routing_strategy.py,
test_loop_routing.py — all tracked, no mirror paths)
