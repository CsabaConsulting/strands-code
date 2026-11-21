# Phase 8: Model Routing with Decision Models - Pattern Map

**Mapped:** 2026-10-11
**Files analyzed:** 12 (10 extend/touch, 2 new)
**Analogs found:** 11 / 12

> Note: this phase is a Decision-API **rework** of an already-implemented chat-JSON
> routing stack. Most "new" code is rebuilt function bodies inside existing modules,
> so the closest analog is usually the module itself (extension target). Self-analogs
> are marked `self-extend`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/routing.py` (EXTEND: Decision-API engines + gate + question builders + new strategy keys + format lines) | service | request-response | `strands_code_cli/routing.py` (self: `decide_via_openrouter`, `_chain_for`, `decide`, `parse_pick`) | exact (self-extend) |
| `strands_code_cli/router.py` (EXTEND: split-catalog setup enumeration) | controller | request-response | `strands_code_cli/router.py` (self: `_setup_catalog_entries`, `_setup_pick_decision`, `_route_setup_message`) | exact (self-extend) |
| `strands_code_cli/loop.py` (TOUCH: hooks read new verdict incl. confidences) | controller | event-driven | `strands_code_cli/loop.py` (self: `_route_pre_turn`, `_route_side_spawn`, `_record_routing_event`) | exact (self-extend) |
| `strands_code_cli/cost_context.py` (TOUCH: routing entry + decision spend) | utility | transform | `strands_code_cli/cost_context.py` (self: `_routing_line`, `cost_report`) | exact (self-extend) |
| `strands_code_cli/live_pricing.py` (EXTEND: `?output_modalities=decisions` read) | service | request-response | `strands_code_cli/live_pricing.py` (self: `fetch_openrouter_models`, `_store_openrouter`) | exact (self-extend) |
| `strands_code_cli/btw.py` (TOUCH: side-spawn verdict shape) | service | event-driven | `strands_code_cli/loop.py` `_route_side_spawn` (the side decision mechanics live in the hook, not in `btw.py`) | role-match |
| `tests/test_routing.py` (EXTEND: gate math, answer validation, transports) | test | batch | `tests/test_routing.py` (self: `_FakeResponse` + `_fake_urlopen` seam) | exact (self-extend) |
| `tests/test_routing_strategy.py` (EXTEND: new knobs/criteria keys, 26-cap) | test | batch | `tests/test_routing_strategy.py` (self) | exact (self-extend) |
| `tests/test_loop_routing.py` (EXTEND: two-call flow, hold notes, transcript lines) | test | batch | `tests/test_loop_routing.py` (self) | exact (self-extend) |
| `scripts/uattest/driver.py` (EXTEND: r1–r4 scenario updates) | test | batch | `scripts/uattest/driver.py` (self: R1 setup+validate, R3 routing round-trip) | exact (self-extend) |
| probe runner + probe set (NEW: `scripts/route-probe.py` or `routing/probe.py` + 20 labeled asks; planner decides location) | utility | batch | `scripts/uattest/driver.py` (scenario-runner shape: send/wait/assert over live sessions) | partial |
| `evals/routing-probe/promptfooconfig.yaml` (NEW, only if promptfoo available) | config | batch | — none (first promptfoo config in repo; use RESEARCH.md + promptfoo docs) | no analog |

## Pattern Assignments

### `strands_code_cli/routing.py` (service, request-response)

**Analog:** `strands_code_cli/routing.py` (self-extend). All analog paths below are
git-tracked (verified via `git ls-files`).

**Imports pattern** (lines 13-33):

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
    window_for,
)
from strands_code_cli.model_switch import supports_reasoning

logger = logging.getLogger(__name__)
```

New code needs no new imports: `urllib.request` is imported lazily inside engine
functions (routing.py:782,873), and the gate reuses the already-imported
`price_for` for the D-14 almanac cheaper-substitution.

**Engine transport pattern — rebuild target** (`decide_via_openrouter`, lines 766-834):

```python
def decide_via_openrouter(
    *,
    decision_model: str,
    system: str,
    user: str,
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    import urllib.request

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not decision_model:
        return EngineResult(text=None)
    body = json.dumps({...}).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return EngineResult(text=None)
    # ... strict shape-walk, _count() for usage fields ...
```

Copy this skeleton for the Decision-API transports: keep the keyword-only
signature, env-at-call-time key, `User-Agent: strands-code`, try/except →
degraded return, and the defensive shape-walk. Change: URL to
`/api/alpha/decisions`, payload `{model, state, questions}`, `usage.cost`
passthrough, response-`model` snapshot logging, and max-1 retry on retryable
codes only (429/500/502/503/524/529 + timeouts; never on 4xx).

**Ollama loopback/no-key pattern — survives** (lines 837-853):

```python
_OLLAMA_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")

def _ollama_headers(base: str) -> dict[str, str]:
    from urllib.parse import urlsplit
    headers = {"Content-Type": "application/json", "User-Agent": "strands-code"}
    try:
        loopback = urlsplit(base).hostname in _OLLAMA_LOOPBACK_HOSTS
    except ValueError:
        loopback = False
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key and not loopback:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
```

Rebuild `decide_via_ollama` to POST `{base}/v1/systemone` with `keep_alive`
(`OLLAMA_KEEP_ALIVE = "5m"`, line 54) but keep `_ollama_headers` and
`_valid_base_url` (lines 170-178) unchanged.

**Chain + HOLD pattern — survives, extended** (`_chain_for`, lines 998-1019;
`decide`, lines 1022-1079):

```python
register_engine("openrouter", _openrouter_attempt)
register_engine("local", _ollama_attempt)

def _chain_for(strategy: RoutingStrategy) -> list[tuple[str, EngineAttempt]]:
    primary = strategy.engine.primary or "openrouter"
    if primary == "off":
        return []
    names = ["local"] if primary == "local" else ["openrouter", "local"]
    ...
```

Keep the registry + `_chain_for` + `decide()` signature shape. Rebuild inside
`decide()`: two sequential calls (model choice, then effort choice over the
picked model's levels only — never parallel), typed `validate_choice_answer`
replacing `parse_pick` (lines 921-954), and `gate_model` (threshold on top-1
probability + tie-margin cheaper substitution). Rewrite the single-candidate
fast path (lines 1045-1054): skip call 1 but still run call 2 (Pitfall 6 —
zero-call verdicts are gone).

**Strict validation pattern — template for `validate_choice_answer`** (from
`parse_pick`, lines 921-954):

```python
if not isinstance(text, str) or not text.strip():
    return None
try:
    data = json.loads(text)
except ValueError:
    return None
if not isinstance(data, dict):
    return None
...
candidate = next((entry for entry in candidates if entry.id == model), None)
if candidate is None:
    return None
```

Every failure returns None (HOLD); verbatim id match, no fuzzy matching, no
defaults. Apply the same discipline to the typed answer: `type == "choice"`
check, `probabilities` presence/range/sum checks, `choice ∈ live candidates`
(stale pick after a strategy edit holds, never routes).

**Strategy loader pattern — survives, extend keys** (`_candidate_skip_reason`
lines 114-148, `_parse_engine` 181-223, `_parse_strategy` 226-258, `load_strategy`
280-305, `save_strategy` 322-398, `validate_strategy` 505-680):

- Single source of truth: `_candidate_skip_reason` feeds both the loader warning
  and `validate_strategy` output. New candidate key `criteria` and top-level
  `tie_margin` / `confidence_threshold` extend `_CANDIDATE_KEYS` /
  `_TOP_LEVEL_KEYS` (lines 57-60) plus this function.
- Fail-soft: warn-and-skip entries, warn-and-default unknown keys; YAML-bool
  fold for `primary: off` (lines 196-200); symlink refusal raises `ValueError`
  (lines 263-264, 523-531).
- `save_strategy`: atomic tmp-write + `os.replace`, parent dir 0700,
  `_is_secret_shaped_key` drop-on-save at top level + inside `engine`
  (lines 308-380).
- `validate_strategy`: `_read_strategy_data` (417-434) reads raw YAML without
  the loader, `_candidate_fix` (437-461) gives manual-edit fix lines, decision
  model checked against `_cached_catalog_ids()` disk-cache-only (464-482).
  New checks: >26 candidates fail with a fix line, `criteria` key type,
  knob ranges, decider id against the *decisions* catalog (not the chat cache).

**Transcript format pattern — rebuild signatures** (lines 1140-1155):

```python
def format_routed_line(
    *, model: str, effort: str, why: str, prev_model: str, ask: str, side: bool = False
) -> str:
    delta = route_cost_delta(model, prev_model, ask)
    head = "Routed (btw)" if side else "Routed"
    return f"{head} \u2192 {model} ({effort}): {why} \u00b7 ~${delta}/ask vs {prev_model}"

def format_hold_line(*, current: str, engine: str) -> str:
    return f"Routing held on {current} ({engine} failed; retrying next ask)"
```

New shapes per D-12/D-16: routed line carries choice + BOTH confidences inline +
code-computed `~$/ask` delta (via `route_cost_delta`, lines 1121-1137, which
survives); threshold-hold gets its own distinct note
(`Routing held (confidence 41% < 70%)`); tie-break substitutions noted; no
free-text `why` (remove `RoutingPick.why`, lines 95-101).

**Error handling pattern:** fail-soft everywhere — transport/parse/gate failures
yield HOLD values (`EngineResult(text=None)`, `None` pick), never raise to the
hook. `logger.warning("...", ...)` with `%s` args; debug-only for raw payloads
(may contain ask text); keys never logged.

---

### `strands_code_cli/router.py` (controller, request-response)

**Analog:** `strands_code_cli/router.py` (self-extend).

**Catalog-entry filter pattern — template for the decisions-catalog filter**
(`_setup_catalog_entries`, lines 586-647):

```python
def _setup_catalog_entries(models: object) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not isinstance(models, list):
        return entries
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        lowered = model_id.lower()
        if "embed" in lowered or "rerank" in lowered:
            continue
        arch = model.get("architecture")
        if isinstance(arch, dict):
            ...  # modality checks, missing keys fail open
        ...  # pricing label + numeric sort key, unpriced sorts last
    entries.sort(key=lambda entry: (entry["sort"], entry["id"]))
    return entries
```

Never raises; hostile payload yields a shorter list. Rebuild adds a parallel
`_setup_decision_entries` over `GET /models?output_modalities=decisions`:
keep entries whose `architecture.output_modalities` contains `decisions`,
drop `~`-prefixed aliases, drop `context_length == 0` entries (respan),
sort by prompt price asc then id. Reuse the same label/sort-key/id dict shape
so `_setup_ask` pickers work unchanged.

**Setup flow pattern — survives, split catalogs** (`_route_setup_message`,
lines 877-956):

```python
from strands_code_cli.live_pricing import fetch_openrouter_models
from strands_code_cli.routing import save_strategy
...
try:
    models = fetch_openrouter_models()
except Exception:
    models = None
entries = _setup_catalog_entries(models)
if entries:
    ...tty or typed pickers...
else:
    print("Live catalog unreachable — enter model ids manually ...")
    candidates = _setup_typed_id_list(...)
```

Lazily import the new decisions-catalog fetch alongside `fetch_openrouter_models`;
every choice stays catalog-driven, never hardcoded (D-06), never key prompts.
`_setup_pick_decision` (lines 781-832) is rebuilt onto the decisions entries but
keeps its shape: radio on tty, validated typed id off-tty with one re-prompt,
typed-id fallback when the catalog is unreachable, no default ever assumed.
`_setup_local_model` (lines 835-846) keeps its typed-tag prompt; default local
tag becomes `nimble` per RESEARCH pinning. All aborts return `_SETUP_ABORTED`
(line 583) with no writes.

**Reply-only router pattern** (`_route_message`, lines 966-991): slash branches
return message strings; prompts live in the router's setup helpers but agent
turns and approval prompts never do. New subcommand verbs (if any) follow the
`verb in (...)` dispatch + `ROUTE_USAGE` fallback shape.

---

### `strands_code_cli/loop.py` (controller, event-driven)

**Analog:** `strands_code_cli/loop.py` (self-extend).

**Pre-turn hook pattern — survives, reads new verdict** (`_route_pre_turn`,
lines 1350-1533):

```python
if routing is not None and not routing.is_on():
    return current_model
try:
    strategy = routing_mod.load_strategy()
except ValueError as exc:
    logger.warning("Routing disabled for this ask: %s", exc)
    print_plain(console, f"Routing disabled ({exc}).")
    return current_model
if strategy is None or not strategy.candidates:
    return current_model
try:
    pick, engine, usage = routing_mod.decide(...)
except Exception as exc:
    ...record event, print hold line, return current_model...
if pick is None:
    ...record held event, print hold line, return current_model...
```

Copy the discipline: toggle-off/config-missing skip silently; every decide,
effort-gate (`validate_routed_effort`, survives), and resolve failure holds
with history untouched; hold/failure notes always print even under `quiet`;
routed line suppressed under `quiet` (lines 1520-1532); same-model pick skips
the switch but still prints. Raw typed line only (`ask_text=text`) reaches the
decision call — never composed skill/memory content (lines 2163-2176). Verdict
shape changes: confidences replace `why`; event record gains confidence fields.

**Side-spawn hook pattern — survives** (`_route_side_spawn`, lines 605-736):
same decision mechanics side-flagged (`side=True`), runs synchronously on the
pump thread inside the build closure before `build_btw_agent`; side holds stay
silent on the live model (no side note) but still append a side-flagged event.
Every `_record_routing_event` call site must pass the new verdict fields.

**Event record pattern — extend** (`_record_routing_event`, lines 1309-1347):

```python
routing_events.append(
    {
        "ask": len(routing_events) + 1,
        "side": side,
        "model": model,
        "effort": effort,
        "why": why,
        "engine": engine,
        "input_tokens": usage[0],
        "output_tokens": usage[1],
        "held": held,
        "decision_model": routing_mod.decision_model_for(strategy, decision_engine),
    }
)
```

Held asks record the serving model with empty effort/why. New shape: drop/replace
`why` with model+effort confidences (+ optional tie-break note and decision
`cost`); `decision_model_for` (routing.py:1107-1118) survives for `/cost` pricing.

**Session boot pattern — survives** (lines 1960-1972, 2005, 2026-2027):

```python
_boot_strategy = routing_mod.load_strategy()  # ValueError -> warn + note
routing = routing_mod.RoutingState(
    initial=("on" if _boot_strategy is not None and _boot_strategy.candidates else "off")
)
routing_events: list = []
btw_session = _btw_context_for(agent, routing=routing, routing_events=routing_events)
```

No boot changes expected; new knobs ride inside the loaded strategy.

---

### `strands_code_cli/cost_context.py` (utility, transform)

**Analog:** `strands_code_cli/cost_context.py` (self-extend).

**Routing-line pattern — format change** (`_routing_line`, lines 175-211):

```python
def _routing_line(event: dict[str, Any]) -> str:
    try:
        ask = event.get("ask", "?")
        ...
    except (TypeError, ValueError):
        return "  ask ?: unparseable routing event"
    head = f"  ask {ask}{side}: {model}"
    ...
    cell = f"{head} (decision in {in_tok}, out {out_tok}"
    decision_model = event.get("decision_model")
    if decision_model and (in_tok or out_tok):
        try:
            decision_cost = cost_for(in_tok, out_tok, decision_model)
        except Exception:
            decision_cost = None
        if decision_cost is not None:
            cell += f", ${decision_cost:.4f}"
    return cell + ")"
```

Never raises; missing keys degrade to placeholders; display only. New shape per
D-12: compact entry (choice, confidences, decision spend) with the full
probability table in verbose/debug only. Decision spend: prefer the engine's
reported `usage.cost` (OpenRouter) when present; local engine has no `cost`
field — record $0, never estimate. Pricing helpers `price_for` (lines 110-118),
`window_for` (121-127), `cost_for` (140-145), `estimate_messages_tokens`
(403-413) all survive unchanged and feed the gate (`price_for`) and delta line.

---

### `strands_code_cli/live_pricing.py` (service, request-response)

**Analog:** `strands_code_cli/live_pricing.py` (self-extend).

**Public-catalog fetch pattern** (`fetch_openrouter_models`, lines 366-379):

```python
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"  # line 41

def fetch_openrouter_models() -> list[dict[str, Any]] | None:
    """Raw ``/models`` payload (public, no key), or None on failure."""
    import urllib.request
    try:
        request = urllib.request.Request(
            _OPENROUTER_MODELS_URL, headers={"User-Agent": "strands-code"}
        )
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("data", [])
        return models if isinstance(models, list) else None
    except Exception:
        return None
```

The decisions-catalog read (`?output_modalities=decisions`, also public, no key)
is one more fetch of exactly this shape — add a sibling function, not a
parameterized rewrite. Fail-soft layering precedent: live → cached → static,
nothing raises to callers (`cached_tables`, line 519, is the disk-cache-only
read that `validate_strategy` uses). If the decisions catalog needs caching,
mirror `_store_openrouter` (lines 382-405): parse defensively, `_write_cache`
with `fetched_at`, unknown shapes skip entries.

---

### `strands_code_cli/btw.py` (service, event-driven)

**Analog:** `strands_code_cli/loop.py` `_route_side_spawn` (loop.py:605-736) —
the side decision mechanics live in the loop hook, not in `btw.py`.

`btw.py` itself only needs a touch if the verdict shape flows through
`build_btw_agent(parent_kwargs, history, question)` (btw.py:394-396): routed
model/effort arrive via the mutated `kwargs` (`kwargs["model"] = routed`,
`kwargs["effort"] = pick.effort`, loop.py:708-709). Keep that seam — the hook
passes the new verdict fields through the same two kwargs keys. No new
side-channel API; D-04 side-flagging is already threaded (`side=True` in the
hook, `"side"` in events, `Routed (btw)` head in the format function).

---

### `tests/test_routing.py` (test, batch)

**Analog:** `tests/test_routing.py` (self-extend).

**Hermetic engine-test pattern** (lines 188-233):

```python
class _FakeResponse:
    """Minimal urlopen context manager serving a canned JSON payload."""
    def __init__(self, payload: dict) -> None: ...
    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False

class TestEngineChain:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def test_openrouter_success_short_circuits_with_one_call(self, monkeypatch):
        import urllib.request
        calls: list = []
        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            return _FakeResponse(_chat_payload(_pick_json()))
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage = decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert len(calls) == 1
```

Module docstring rule (lines 1-5): "No live decision calls: the urllib seam
serves canned JSON". New tests reuse `_FakeResponse` with Decision-API shaped
payloads (`{model, answers, usage}`), plus fault-injection variants already in
the file (`_boom` raising, `_slow` timeout — lines 275-288) extended with
HTTPError-by-code (4xx → hold zero-retry; 5xx → 1 retry → fallback → hold).
Strategy/test-data builders `_candidates()` / `_strategy()` (lines 37-51) gain
the new knobs. Gate tests use synthetic probability tables with exact ties and
±ε boundaries (ε ≥ 0.005 — Pitfall 2); stub `price_for` via monkeypatch for
tie-break determinism (prompt tests already stub it, lines 58-59).
Naming: `Test<P area>` classes, one class per behavior area; live tests (if any)
behind the `integration` marker deselected by default (`pyproject.toml`).

---

### `tests/test_routing_strategy.py` (test, batch)

**Analog:** `tests/test_routing_strategy.py` (self-extend, 752 lines).

Extends with: new knob/criteria keys load (valid + warn-and-default on wrong
types), >26 candidates fail `validate_strategy` with a fix line, `off`/symlink
preservation, strategy round-trip through `save_strategy` incl. secret-shaped
key drops. Same hermetic discipline as `test_routing.py` (tmp paths via
`global_path=`/`repo_path=` overrides, never the real home).

---

### `tests/test_loop_routing.py` (test, batch)

**Analog:** `tests/test_loop_routing.py` (self-extend, 1064 lines).

Extends with: two-call flow (model table → gate → effort table → switch +
transcript line with BOTH confidences + delta), threshold-hold distinct note +
retry-next-ask, tie-break substitution note, new verdict fields in routing
events, `/model` pin never re-pointed, toggle round-trip, no mid-turn flip.
Hook tests stub `routing_mod.decide` (or the urllib seam) — never live engines.

---

### `scripts/uattest/driver.py` (test, batch)

**Analog:** `scripts/uattest/driver.py` (self-extend).

R1 (line 277: `/route setup` against the live catalog + `/route validate`) and
the routing round-trip scenarios (setup → validate → on → routed turn with real
decision tokens → off/on) update for the Decision-API flow: split-catalog setup
(directives capture + decisions-catalog pick), confidences-bearing transcript
lines, hold-note variants. Scenario shape stays: `send(sess, "/route ...",
"Enter")` + `wait_for_new(sess, regex, timeout, label)` + text asserts. Uses
tmux live sessions; `OPENROUTER_API_KEY` from env, Ollama daemon local.

---

### Probe runner + probe set (NEW) (utility, batch)

**Analog:** `scripts/uattest/driver.py` (partial — scenario-runner shape, not content).

No calibration-probe runner exists yet; the closest in-repo precedent for a
script that drives live calls and records verdicts is the uattest driver
(scenario functions + session helpers + assertions). Planner decides location
(`scripts/route-probe.py` vs a `routing/probe.py` section): either way copy
the repo's script conventions — stdlib-only HTTP, env-at-call-time key,
JSONL verdict records, exit-nonzero on regression. The 20 labeled asks come
from AI-SPEC §5 (clear cases, ambiguous, no-match, empty/off-topic, negated,
adversarial) run through BOTH pinned engines; thresholds derive from observed
top-1 distributions, never round numbers. `evals/routing-probe/promptfooconfig.yaml`
has no analog (first promptfoo config; use RESEARCH.md + promptfoo docs, JSONL
diffs as fallback).

## Shared Patterns

### stdlib urllib transport + fail-soft reads

**Source:** `strands_code_cli/live_pricing.py:366-379`, `strands_code_cli/routing.py:809-834`
**Apply to:** Decision-API transports, decisions-catalog fetch, probe runner

```python
import urllib.request
request = urllib.request.Request(URL, data=body, headers={"User-Agent": "strands-code", ...})
try:
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    return None  # or EngineResult(text=None); never raise to callers
```

One import per line, absolute imports, lazy `urllib.request` import inside
engine functions. Timeouts: `DECISION_TIMEOUT_SECONDS = 10` (routing.py:42),
`OLLAMA_TIMEOUT_SECONDS = 30` (routing.py:51). New: max-1 retry on retryable
codes only; current code never retries (behavior change).

### Credentials: env-at-call-time, header-only, never logged/persisted

**Source:** `strands_code_cli/routing.py:784` (`os.environ.get("OPENROUTER_API_KEY")`
inside the engine function), `routing.py:841-853` (loopback rule), `routing.py:308-380`
(secret-shaped drop on save)
**Apply to:** Both Decision-API transports, probe runner, any new save path

Keys stay runtime env (`OPENROUTER_API_KEY` / `OLLAMA_API_KEY` / `OLLAMA_HOST`
read at call time inside engine functions only); local loopback sends no key;
`save_strategy` drops `api_key`-shaped keys at top level + inside `engine`.

### Fail-soft loaders with warn-and-continue + symlink refusal

**Source:** `strands_code_cli/routing.py:261-305` (`_load_one`/`load_strategy`),
`strands_code_cli/provider_config.py:40-78` (`ProviderConfig.load`)
**Apply to:** Strategy load/validate/save extensions

```python
if path.is_symlink():
    raise ValueError(f"Routing strategy must not be a symlink: {path}")
if not path.exists():
    return None
try:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
except (OSError, ValueError, yaml.YAMLError) as exc:
    logger.warning("Ignoring unreadable routing strategy %s: %s", path, exc)
    return None
```

Repo wins whole-file over global (`load_strategy`); unknown keys warn and fall
to defaults; single skip-reason function shared by loader and validator.

### Transcript notes via `print_plain` (markup off)

**Source:** `strands_code_cli/output.py:34-42`, `strands_code_cli/loop.py:1520-1532`
**Apply to:** Routed/hold/threshold/tie-break notes

```python
def print_plain(console: Console, text: str, *, style: str | None = None) -> None:
    console.print(text, style=style, markup=False)
```

All transcript prints of non-constant strings route through here. Routed lines
print `style="dim"`, suppressed under strategy `quiet`; hold/failure notes
always print. No `print()` in library code (`routing.py`); prints live in the
turn layer (`loop.py`) and router setup helpers.

### Reply-only router actions

**Source:** `strands_code_cli/router.py:966-991`
**Apply to:** Any new `/route` subcommand verbs

Slash branches return message strings; no agent turns, no approval prompts in
the router. Routing choices never raise approval prompts (D-11).

### Test seams: monkeypatched urllib + canned JSON, tmp-path strategies

**Source:** `tests/test_routing.py:188-233`, `tests/test_routing.py:45-51`
**Apply to:** All new routing tests

`_FakeResponse` + `monkeypatch.setattr(urllib.request, "urlopen",
_fake_urlopen)`; `_strategy()`/`_candidates()` builders; env keys via
`monkeypatch.setenv`; strategy files via `global_path=`/`repo_path=` tmp
overrides. pytest with `integration` marker deselected by default; per-commit
run: `uv run pytest tests/test_routing.py tests/test_routing_strategy.py
tests/test_loop_routing.py -q`.

### Naming and style

**Source:** `AGENTS.md` conventions + `strands_code_cli/routing.py` throughout
**Apply to:** All new code

`snake_case` modules/functions, `UPPER_SNAKE_CASE` constants
(`ASK_TRUNCATE_CHARS`, `DECISION_TIMEOUT_SECONDS`), `PascalCase` dataclasses
(`RoutingStrategy`, `RoutingPick`, `EngineResult`, `ValidationReport`);
`from __future__ import annotations` first; module `logger =
logging.getLogger(__name__)` with `%s`-style args; why-comments only (1-2
lines); docstrings on public functions/classes; constructor-kwarg
configuration, never env sniffing (except runtime credentials at call time).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `evals/routing-probe/promptfooconfig.yaml` | config | batch | First promptfoo config in the repo; planner uses RESEARCH.md §Standard Stack + promptfoo docs (JSONL-diff fallback if promptfoo unavailable) |

## Metadata

**Analog search scope:** `strands_code_cli/` (routing.py full 1231 lines;
router.py setup section 586-956; loop.py hooks 605-736, 1309-1533, boot
1960-2028; cost_context.py routing section 110-270; live_pricing.py fetch/cache
41-42, 366-405, 519-529; btw.py:394-396; choice.py:148-153; output.py:34-42;
provider_config.py:40-83; model_switch.py:140-144, 390-393), `tests/`
(test_routing.py header + seam 1-51, 185-233), `scripts/uattest/driver.py`
(routing scenarios R1+)
**Files scanned:** 14
**Pattern extraction date:** 2026-10-11
**Tracked-source gate:** all named analogs verified git-tracked via `git ls-files`
