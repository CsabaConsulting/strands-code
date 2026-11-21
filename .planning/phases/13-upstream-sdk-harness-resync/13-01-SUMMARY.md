---
phase: 13-upstream-sdk-harness-resync
plan: "01"
subsystem: packaging-context-memory
tags: [strands-agents, strands-harness, ContextInjector, InjectedBlock, uv]
dependency_graph:
  requires: []
  provides:
    - strands-agents==1.65.0 in .venv and uv.lock
    - strands-harness==0.4.0 in .venv and uv.lock
    - InjectedBlock accounting in estimate_messages_tokens, canonical_prefix_hash, fork_btw_history
  affects:
    - Wave 2 (13-02) Model.model_info, BedrockModel._format_bedrock_messages, and streaming=False integration
tech_stack:
  added:
    - opentelemetry-processor-baggage==0.66b2 (transitive via strands-agents 1.65.0)
  updated:
    - strands-agents: 1.58.1 -> 1.65.0
    - strands-harness: 0.1.2 -> 0.4.0
key_files:
  modified:
    - pyproject.toml
    - uv.lock
    - strands_code_cli/cost/cost_context.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/loop/btw.py
    - tests/cost/test_cost_context.py
    - tests/model/test_model_switch.py
    - tests/loop/test_btw.py
    - tests/memory/test_memory_file.py
decisions:
  - D-01: Raised lower bounds to strands-agents>=1.65.0 and strands-harness>=0.4.0 with zero upper pins.
  - D-05: InjectedBlock ({"injected": {"text": ..., "source": ...}}) counted in estimate_messages_tokens, ignored in canonical_prefix_hash, and stripped in fork_btw_history.
  - D-06: Preserved BeforeToolCallEvent.cancel_tool in steering.py; verified todos removal causes zero prompt or test issues.
  - D-07: Kept strands_code_agent/ byte-pristine (D-24).
metrics:
  completed_date: "2026-11-21"
  tests_passed: 441
  tests_deselected: 6
---

# Phase 13 Plan 01: Lockfile Bump & `InjectedBlock` Summary

**One-liner:** Upgraded `strands-agents` (`1.58.1` -> `1.65.0`) and `strands-harness` (`0.1.2` -> `0.4.0`), reconciled the `ContextInjector` test stub, and wired `InjectedBlock` handling across token accounting, prefix hashing, and `/btw` history forks.

---

## Key Changes & Findings

1. **Dependency Floor Bump & Lockfile Sync (`D-01`):**
   - Updated [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml#L27-L31) to `strands-agents>=1.65.0` and `strands-harness>=0.4.0` (zero upper pins).
   - Ran `/home/csaba/.local/bin/uv lock --upgrade-package strands-agents --upgrade-package strands-harness` and `/home/csaba/.local/bin/uv sync --locked --extra litellm --group dev` (`strands-agents==1.65.0`, `strands-harness==0.4.0`, `opentelemetry-processor-baggage==0.66b2`).
2. **Upstream Compatibility & `D-07` Audit (`D-06`, `D-07`):**
   - `ContextInjector.init_agent` (`strands.vended_plugins.context_injector.plugin:115`) now registers middleware directly via `agent.add_middleware(InvokeModelStage.Input, self._inject)` instead of `agent._middleware_registry.add_middleware(...)`. Updated the `SimpleNamespace` stub in `tests/memory/test_memory_file.py:167-169`; production `register_memory_plugin` required zero changes.
   - Verified `strands_code_agent/` (`tests/agent/`) passed all tests untouched (`D-24`, zero `git diff strands_code_agent/`). Note for optional future `aws-samples/sample-strands-code-agent` PR (`D-07`): `smolagents` introspection on upgraded `scipy` emits `DeprecationWarning`s (already shielded at `_init_executor` creation time, surfaced only when test modules import subpackages directly), and `strands/models/model.py:486` warns when custom test models lack `context_window_limit`.
   - Verified `harness-py 0.4.0`'s removal of default `"todos"` introduces zero regressions, and `steering.py`'s `BeforeToolCallEvent.cancel_tool` boundary redirection stays green.
3. **`InjectedBlock` Accounting (`D-05`):**
   - `cost_context.estimate_messages_tokens()` now adds character lengths from `block["injected"]["text"]` (failing soft on non-dicts or `None`).
   - `model_switch.canonical_prefix_hash()` ignores `"injected"` blocks so memory reloads never break `RichHistory` stashes.
   - `btw.fork_btw_history()` strips `"injected"` blocks and drops injected-only messages while keeping alternating role invariants.
   - Verified `CodeAgentCallbackHandler` silently ignores `"injected"` blocks with zero console output.

---

## Verification Evidence

- `.venv/bin/pytest tests/agent/ tests/memory/test_memory_file.py tests/loop/test_steering.py tests/cost/test_cost_context.py tests/model/test_model_switch.py tests/loop/test_btw.py -q`: **441 passed, 6 deselected** (exit `0`).
- `.venv/bin/ruff check strands_code_cli tests scripts`: **All checks passed** (exit `0`).
- `.venv/bin/ruff format --check strands_code_cli tests scripts`: passed.
- `git diff strands_code_agent/`: empty (`D-24` honored).
