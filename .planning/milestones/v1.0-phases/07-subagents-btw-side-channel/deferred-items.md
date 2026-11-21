## Deferred Items

- `_ACTIVE["broker"]` leaks process-wide after `build_agent` / `build_interventions`
  status: open
  **What:** `test_mode.py::TestWiring` (and any `build_agent` caller) leaves a broker in `policy_gate._ACTIVE` with no cleanup; a later `run_loop` with a `prompt()`-only session double then multiplexed and crashed (worked around defensively in `loop.py` via the `prompt_async` duck-type fallback, 07-05 c27c762). The leak itself is pre-existing and unaddressed.
