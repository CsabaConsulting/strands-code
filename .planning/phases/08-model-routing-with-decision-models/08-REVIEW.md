---
phase: 08-model-routing-with-decision-models
reviewed: 2026-10-11T00:00:00Z
depth: standard
reviewer: gsd-code-reviewer (generic-agent workaround — typed gsd-code-reviewer dispatch unavailable in this runtime)
files_reviewed: 11
files_reviewed_list:
  - docs/ROUTING.md
  - strands_code_cli/cost_context.py
  - strands_code_cli/loop.py
  - strands_code_cli/model_switch.py
  - strands_code_cli/router.py
  - strands_code_cli/routing.py
  - strands_code_cli/skills.py
  - tests/test_loop_routing.py
  - tests/test_routing.py
  - tests/test_routing_strategy.py
  - AGENTS.md
findings:
  critical: 1
  warning: 6
  info: 7
  total: 14
status: issues_found
---

# Phase 8: Code Review Report

- Phase: 08-model-routing-with-decision-models
- Reviewed: 2026-10-11T00:00:00Z
- Depth: standard
- Reviewer: gsd-code-reviewer (generic-agent workaround — typed gsd-code-reviewer dispatch unavailable in this runtime)
- Scope: 7 source files + ROUTING.md read fully; 3 test files read for behavior confirmation only (no test-style findings per scope)
- Cross-referenced (read-only, out-of-scope context): `strands_code_cli/live_pricing.py`, `strands_code_cli/model_capabilities.py`, `strands_code_cli/btw.py`, installed `strands_harness` signatures

## Summary

The routing implementation is well-structured: strict parse, hold-on-failure semantics, symlink refusal on strategy load/save, `yaml.safe_load` throughout, no hardcoded secrets, and the API key stays header-only at call time. The test suite covers the main/hook/side/cost paths credibly.

One critical security defect was proven by execution: `save_strategy` follows a symlinked temp file, so a planted `./.agent/routing.yaml.tmp` symlink turns `/route setup` (repo scope) into an arbitrary file overwrite. Six warnings follow, the most important being that the pre-turn hook lets pricing/validation exceptions escape and kill the session (proven with a poisoned cache), and that composed prompts carrying untrusted skill instructions and memory content are sent to the external decision model despite the documented "ask text only" guarantee. Seven info notes cover docs nits and latent traps. All findings cite `file:line` and carry concrete fixes.

Checks run clean and not reported: no bare `except`, no `eval`/`exec`, no mutable defaults, `with` used for network/file ops, no unused imports in new code, absolute imports per AGENTS.md, `print` only in the CLI prompt layer (established router pattern).

## Critical Issues

### CR-01: `save_strategy` follows a symlinked temp file — arbitrary file overwrite

`strands_code_cli/routing.py:386-388` refuses a symlinked strategy target (`resolved.is_symlink()`, line 350) but writes through an unchecked temp path:

```python
tmp = resolved.with_suffix(".yaml.tmp")
tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
os.replace(tmp, resolved)
```

`Path.write_text` follows symlinks. Proven by execution: with `/tmp/probe/w/r.yaml.tmp` symlinked to a victim file, `save_strategy(..., repo_path="/tmp/probe/w/r.yaml")` overwrote the victim with the strategy YAML. Attack shape: a malicious repo ships `./.agent/routing.yaml.tmp` as a symlink (e.g. to `~/.bashrc`); the victim runs `/route setup` with repo scope and any user-owned file gets clobbered. This contradicts the module's own fail-loud symlink policy (same file, lines 256-257, 350-351).

Fix — refuse (or unlink) a symlinked temp path before writing:

```python
tmp = resolved.with_suffix(".yaml.tmp")
if tmp.is_symlink() or tmp.exists():
    raise ValueError(f"Refusing to write through existing temp file: {tmp}")
tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
os.replace(tmp, resolved)
```

(Alternative: `os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL)` + `os.fdopen`.)

## Warnings

### WR-01: Pre-turn hook lets pricing/validation exceptions escape and kill the session

`strands_code_cli/loop.py:1349` (`decide`), `loop.py:1371` (`validate_routed_effort`), and `loop.py:1450` (`format_routed_line`) run outside any `try`, and the enclosing `run_loop` turn `try` (`loop.py:2077`) only handles `KeyboardInterrupt` (`loop.py:2198`). Any exception here propagates out of `run_loop` and ends the session with a traceback — violating the D-08 hold-on-failure contract.

Concrete trigger, proven by execution: `strands_code_cli/routing.py:646-657` (`_candidate_row`) and `routing.py:1065-1076` (`route_cost_delta`) call the live-pricing layer unguarded, and that layer raises `ValueError` on valid-JSON-but-wrong-typed caches (unguarded `float(payload.get("fetched_at", 0))` and `float(slot["in"])` in `live_pricing.py`), despite its "nothing here ever raises … corrupt cache yields None" contract. Probe output with a poisoned `openrouter-models.json`:

```text
RAISED: ValueError could not convert string to float: 'not-a-number'
```

A second trigger by code reading: `validate_routed_effort` → `supports_reasoning` → `active_overrides` raises `ValueError` when the capability-overrides file is a symlink (`model_capabilities.py:62-63`, deliberate fail-loud) — uncaught at `loop.py:1371`. Note `cost_context.py:205-208,272-275` already wraps `cost_for` in `try/except Exception`; the routing call sites should follow that precedent.

Fix — hold instead of crash in the hook:

```python
try:
    pick, engine, usage = routing_mod.decide(...)
except Exception as exc:
    logger.warning("Routing decision failed (%s); holding %s", exc, current_model)
    # record held event + print hold note, return current_model
```

and/or wrap the price/window lookups inside `_candidate_row` and `route_cost_delta` to degrade to `n/a` cells.

### WR-02: Composed prompts with untrusted content are sent to the external decision model

`docs/ROUTING.md:15-16` promises the decision prompt carries "the current ask text only (truncated) — never history, tool results, or file contents." But `strands_code_cli/loop.py:2089-2092` routes on the composed agent message, not the raw typed line:

```python
ask_text=message if message is not None else text,
```

Three composed paths violate the guarantee: skill invocations prepend untrusted repo `SKILL.md` instructions (`strands_code_cli/router.py:240-248`); `/memory revise` rounds send the memory section text (`strands_code_cli/loop.py:2000-2001`, template built from `read_memory_section`); `/init` turns send the repo scan report (`strands_code_cli/router.py:1236`). Consequences: (a) repo/memory content the user never typed is exfiltrated to the OpenRouter decision call; (b) a malicious skill's instructions can steer routing picks (e.g. force the priciest tier) within the candidate-id constraint.

Fix — route on the raw typed text:

```python
current_model = _route_pre_turn(
    ...
    ask_text=text,  # raw user input; never the composed skill/revise/init message
    ...
)
```

(or pass both and let the hook prefer the raw line), and re-verify the skill/revise/init tests still route sensibly.

### WR-03: Routed switch discards the streaming-tools advisory reply

`strands_code_cli/loop.py:1396` throws away the reply from `apply_model_action`, which is where the "rejects tool use in streaming mode" warning lives (`strands_code_cli/model_switch.py:1257-1262`). The manual `/model` path prints it (`strands_code_cli/loop.py:2046`); the routed path never does — so routing onto a Llama-class model proceeds silently and subsequent turns fail without the designed warning.

Fix — surface the advisory on the routed path:

```python
if not supports_streaming_tools(pick.model):
    print_plain(console,
        f"Warning: {pick.model} rejects tool use in streaming mode — turns "
        "will fail until a non-streaming fallback lands upstream (/model to switch back).",
        style="yellow")
```

(`supports_streaming_tools` is already imported in `loop.py`.)

### WR-04: Unknown `engine.primary` values are silently accepted as openrouter

`strands_code_cli/routing.py:192-204` (`_parse_engine`) accepts any string for `primary`, `strands_code_cli/routing.py:951-954` (`_chain_for`) maps anything that is not `local`/`off` to the openrouter-first chain, and `strands_code_cli/routing.py:594-626` (`validate_strategy`) reports a bogus primary with a valid decision model as clean. A typo such as `primary: open_route` therefore validates yet silently behaves as `openrouter`.

Fix — reject unknown primaries at parse and validate:

```python
if engine.primary not in ("openrouter", "local", "off"):
    # _parse_engine: logger.warning(...) + fall back to "openrouter"
    # validate_strategy: valid = False + "fix: set engine.primary to openrouter|local|off"
```

### WR-05: Invalid `local_base_url` silently overrides the env chain with the default

`strands_code_cli/routing.py:205-215` replaces a non-http(s) `local_base_url` with `OLLAMA_DEFAULT_HOST` (log warning only), so a typo'd strategy URL discards a working `OLLAMA_HOST` env instead of falling through to it — and `validate_strategy` (`strands_code_cli/routing.py:577-593`) never checks `local_base_url` at all, so `/route validate` stays silent.

Fix — either fall through to the env chain:

```python
engine.local_base_url = None  # invalid entry ignored; OLLAMA_HOST/default applies
```

or keep the default but add a validate line: `engine: INVALID — local_base_url is not an http/https URL` with a manual-edit fix.

### WR-06: `/route setup` does not catch `OSError` from the strategy save

`strands_code_cli/router.py:946-949` catches only `ValueError` around `save_strategy`, but `strands_code_cli/routing.py:384-388` can raise `OSError` (`mkdir`, `chmod`, temp write, `os.replace`) on read-only filesystems, permission errors, or full disks. Since `dispatch` runs outside the turn `try` (`strands_code_cli/loop.py:2003`), the traceback escapes `run_loop` and ends the session.

Fix:

```python
try:
    path = save_strategy(payload, scope)
except (ValueError, OSError) as exc:
    return f"Setup failed — {exc} (nothing written)."
```

## Info

### IN-01: Two ROUTING.md sentences over-claim vs intended behavior

- `docs/ROUTING.md:17-20`: "The chain is API, then local, then hold" ignores `primary: local`, which deliberately skips the API entirely (fully offline, `strands_code_cli/routing.py:954`). Suggest: "The default chain is API, then local, then hold; `primary: local` tries only the daemon."
- `docs/ROUTING.md:25-26`: "hold and failure notes always print" ignores side-spawn holds, which are intentionally silent (`strands_code_cli/loop.py:638-651`, asserted by `test_engine_failure_spawns_on_parent_model_silently`). Suggest scoping the sentence to main-turn asks.

### IN-02: Hold note mislabels effort-validation failure as engine failure

`strands_code_cli/loop.py:1390-1393` prints `"(openrouter failed; retrying next ask)"` when the effort gate — not the engine — rejected the pick. Consider a distinct note (e.g. `Routing held on {current} (routed effort unsupported; retrying next ask)`) so users do not chase engine connectivity for a strategy-leveling problem.

### IN-03: Held-ask usage is dropped, hiding failed decision spend from /cost

`strands_code_cli/routing.py:1015-1023` returns `(0, 0)` usage on every hold path even when the engine response carried token counts, so failed decision calls never appear in the `/cost` Routing section. This matches the documented "zeros on hold" contract, so no behavior change is required — but consider threading the last-attempt usage through so real spend stays visible.

### IN-04: Repo-scope save chmods `./.agent` to 0700

`strands_code_cli/routing.py:384-385` applies `os.chmod(resolved.parent, 0o700)` unconditionally, including for repo scope where `./.agent` may be shared or team-visible. Documented and harmless in most cases, but consider chmodding only the global dir or only when the directory was newly created.

### IN-05: `/route status` reports a symlinked strategy as "none configured"

`strands_code_cli/router.py:980-984` swallows the fail-loud symlink `ValueError` from `load_strategy` and falls through to "Strategy: none configured", while `/route validate` names the symlink properly. Consider surfacing the symlink reason in the status reply for consistency.

### IN-06: Side-spawn path relies on `resolve_model` instead of the explicit effort gate

`strands_code_cli/loop.py:635-669` (`_route_side_spawn`) never calls `validate_routed_effort`, unlike the main hook (`strands_code_cli/loop.py:1371`). Verified against the installed harness that `resolve_model` raises `ValueError` for both unsupported levels (`Effort 'low' is not supported by Bedrock model amazon.nova-micro-v1:0`) and unknown literals, and the side path catches that into a silent hold — so behavior converges and no live bug results. Suggest calling `validate_routed_effort` explicitly before resolving anyway, for one obvious gate and stable event naming.

### IN-07: `routing=None` means ON in the loop hook but OFF in the router holder

`strands_code_cli/loop.py:1339` (`_route_pre_turn`) and `loop.py:624` (`_route_side_spawn`) treat a `None` toggle as enabled, while `strands_code_cli/router.py:520-524` (`_routing_holder`) substitutes a throwaway `off` holder. No live path hits this (`run_loop` always wires a holder), but a future caller passing `None` would get routing without the `/model` warn dialog. Consider making the loop treat `None` as off to match the router.

---

*End of Phase 8 code review. READ-ONLY on sources; this report is the only file written. No commit — orchestrator handles that.*
