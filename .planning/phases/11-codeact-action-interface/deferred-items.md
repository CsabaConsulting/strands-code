## Deferred Items

- `_serialise_rule` writes multi-line commands unescaped, invalidating the whole policy file
  status: open
  **What:** `strands_code_cli/policy.py::_serialise_rule` emits `command = "<raw>"` with no
  escaping, so answering Always/Never on a multi-line input writes invalid TOML; the next
  `PolicyConfig.load` warns and falls back to prompt-all defaults, silently dropping every
  remembered rule.
  **Found during:** 11-03 task 2 (D-07 one-rule-system pins) — probe-verified with a
  multi-line `shell` rule, so it predates CodeAct and is tool-agnostic. CodeAct makes it
  load-bearing: approved code blocks are routinely multi-line.
  **Fix sketch:** escape `\\`, `"`, and control chars in `_serialise_rule` (or emit TOML
  multi-line basic strings) plus a round-trip test; out of scope for the tests-only task.

- `reasoningContent is not supported` warning repeats once per API round-trip
  status: open
  **What:** with OpenRouter models returning reasoning content over multi-turn Chat
  Completions, the harness logs `reasoningContent is not supported in multi-turn
  conversations with the Chat Completions API.` once per round-trip (7 lines observed
  in one UAT turn). Pre-existing provider/harness noise, unrelated to Phase 11.
  **Found during:** 11-UAT test 1 (user transcript, 2026-10-16).
  **Fix sketch:** dedupe to a single warning per turn (or per session) at the layer that
  surfaces harness warnings; out of scope for Phase 11.
