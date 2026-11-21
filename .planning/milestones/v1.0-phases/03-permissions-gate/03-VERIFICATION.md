---
phase: 03-permissions-gate
verified: 2026-09-25T07:36:10Z
status: passed
score: 4/4 must-haves verified
covered_files:
  - .planning/phases/03-permissions-gate/03-CONTEXT.md
  - .planning/phases/03-permissions-gate/03-PLAN-SUMMARY.md
  - .planning/phases/03-permissions-gate/03-PLAN.md
  - .planning/phases/03-permissions-gate/03-RESEARCH.md
  - strands_code_agent/code_agent.py
  - strands_code_cli/diff_gate.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/policy.py
  - strands_code_cli/policy_gate.py
  - strands_code_cli/router.py
  - strands_code_cli/scope.py
covered_digest: "v1:sha256:53b5ad268f9635bdbe4a74404838760fce528f87259f010e689294a880604d5f"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: none
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 3 Verification: Permissions Gate (TOOL-03)

**Verified:** 2026-09-25 (gsd-verifier, independent read of code, not test descriptions)
**Scope:** 03-PLAN.md must_haves (4 truths, 6 artifacts, 5 key_links, 6 prohibitions) + TOOL-03
**Test runs (this session):** focused `tests/test_policy.py tests/test_policy_gate.py tests/test_cli_entry.py tests/test_diff_gate.py tests/test_tool_surface.py` → **135 passed**; full `tests/` → **375 passed, 5 deselected**
**Phase dir note:** no 03-SECURITY.md or 03-UAT.md exists in `.planning/phases/03-permissions-gate/` (only CONTEXT, DISCUSSION-LOG, PLAN-CHECK, PLAN, PLAN-SUMMARY, RESEARCH); nothing to cover there.

## Truths

### T1 — Prompt to approve/deny before edits, shell, network via exactly one HumanInTheLoop: PASS
- `strands_code_cli/policy_gate.py:259-276` — `build_interventions` is the ONLY construction site; returns exactly one `HumanInTheLoop(allowed_tools=["read", "search"], classifier=..., ask=...)`.
- `strands_code_cli/main.py:112` — `build_agent` passes `interventions=build_interventions()` (single-element list); comment at `main.py:109-111` records never-a-second-instance, never sugar strings.
- `strands_code_cli/policy_gate.py:156-188` — `PolicyClassifier.__call__` reads `event.tool_use` name+input, calls `decide()`; Allow → no approval, Prompt → approval with reason, Deny → approval with `DENY:`-prefixed reason so ask short-circuits (fail-closed; docstring `policy_gate.py:8-13` explains the deliberate deviation from PLAN resolved-item-5's literal text, which would have fail-open Proceeded the denied tool).
- `strands_code_cli/policy_gate.py:190-242` — `ask` renders full detail (command/code/path + one-line risk reason, D-01) inside `output_context`, answers y/n/always/never; errors return `"n"` (never raise into the HITL run).
- Tests: `tests/test_policy_gate.py:109-129` (single-HITL constructs; two instances collide; interventions reach `create_harness` as single-HITL kwargs).

### T2 — Standing TOML allow/deny quiets routine actions; dangerous stay gated; deny-wins: PASS
- `strands_code_cli/policy.py:158-194` — `PolicyConfig.load` layered UNION (home + repo), repo-first for explanation order only; missing → defaults; ANY parse/schema violation → warning + built-in defaults = prompt-all-mutating (fail-closed); symlinked path → `ValueError` fail-loud (`policy.py:173-175`).
- `strands_code_cli/policy.py:468-520` — `decide()`: deny match → hard `Deny` naming the rule; allow match → `Allow`; built-in read/search + web_fetch/web_search (D-16 any-host) + GET-shaped curl/`git fetch` → `Allow`; everything else → `Prompt`.
- `strands_code_cli/policy.py:196-228` — `append_rule` writes narrow derived rules only (`tool="*"` refused, `policy.py:210-211`), atomic tmp+replace, 0o700 parent dir, symlink refusal; D-03 write happens inside ask (`policy_gate.py:219-237`), evaluate stays default.
- Tests: `tests/test_policy.py:35-116` (layering union, trust overlay, corrupt/unknown-key/unknown-tool/missing-selector fail-closed, both symlink refusals, append round-trip + star refusal + symlink refusal); `tests/test_policy.py:151-220` (deny-wins, allow-silent, no-rule-prompts, builtin fetch allows, GET-vs-POST, sh-c detection, outside-path deny/granted).

### T3 — Gate approval and /diff never double-prompt: PASS
- `strands_code_cli/diff_gate.py:350-358,401-409` — `make_gated_write`/`make_gated_edit` take `gate_active: bool = False` (default keeps Phase 2 contract).
- `strands_code_cli/diff_gate.py:272-284` — when `gate_active`, approve-each skips its per-hunk `ask` and falls through to the exact-once re-read+apply path; invariant commented: `/diff apply` never re-prompts (`apply_stashed` uses `_fs_write`, not a tool call, invisible to interventions).
- `strands_code_cli/main.py:95-96` — production wires `gate_active=True` into both wrappers.
- `strands_code_cli/diff_gate.py:41` — `AskCallable` bool contract untouched (resolved item 5: HITL ask is the separate `policy_ask(prompt, **kwargs) -> str` returning `"y"`/`"n"`, `policy_gate.py:284-292`).

### T4 — python_repl prompts with code shown (Phase 2 bypass closed): PASS
- `strands_code_cli/policy.py:502-504` — `decide` returns `Prompt(reason=f"Python execution: {code[:200]}")` for every non-allowed `python_repl` call (all-or-nothing per execution; interior confinement limit documented in module docstring `policy.py:42-47`).
- `strands_code_cli/main.py:92-93` — `python_repl` (via `interpreter.get_tool()`) rides the consumer `tools` list, not pinned off, so `before_tool_call` sees every execution; `programmatic_tool_caller` is the one pinned off (`main.py:103-107`, risk 9 fail-closed with comment).
- `strands_code_agent/code_agent.py:139-150` — `python_repl` assembly unchanged (no tool-code change needed; gate is at the intervention layer).
- Tests: `tests/test_policy_gate.py:277-283` (repl prompted with code), `tests/test_policy.py:207-210` (repl prefix match).

## Artifacts

- `strands_code_cli/policy.py` (TOML store + match engine + network classification): PRESENT, verified above (`normalise_command` one-level unwrap `policy.py:323-344`; `match_rule` path-fnmatch/command-prefix `policy.py:360-390`; `is_fetch_get`/`is_network_command` `policy.py:393-432`).
- `strands_code_cli/policy_gate.py` (classifier + ask + BatchState + build_interventions): PRESENT (`BatchState` turn cache + `bind_turn` `policy_gate.py:53-87`; `bind_main_agent` D-12 `policy_gate.py:295-299`; module-level `bind_turn`/`last_covered` `policy_gate.py:302-313`).
- `strands_code_cli/main.py` (interventions=[single HITL] wiring): PRESENT (`main.py:112,120` + `gate_active=True` + `programmatic_tool_caller: False` pin).
- `strands_code_cli/router.py` (/policy show branch): PRESENT (`router.py:68-69` dispatch, `_policy_message` `router.py:111-140`, USAGE_HINT `router.py:17-21`).
- `tests/test_policy.py` / `tests/test_policy_gate.py`: PRESENT (28 + 21 test methods, all green).

## Key links

- main.py passes `interventions=[HumanInTheLoop(allowed_tools, classifier, ask)]`, never "ask"/"smart"/NL-string/Cedar: PASS — `main.py:112` instance only; the words appear solely in a prohibitive comment (`main.py:109-111`) and docstrings.
- policy_gate.py classifier owns TOML matching (event tool name + input); ask owns rendering only: PASS — `policy_gate.py:156-188` vs `policy_gate.py:190-242`; evaluate stays default (no custom `evaluate=` anywhere; grep confirms no `enable_trust`/`LLMClassifier` in source).
- diff_gate.py approve-each passes through when gate_active=True; no second prompt by construction: PASS — `diff_gate.py:272-284`, production `gate_active=True` (`main.py:95-96`).
- scope.py confine admits union(cwd, /tmp, allow-rule roots); policy match before confine: PASS — `effective_roots` `scope.py:76-96` (+ `_rule_base_dir` `scope.py:59-73`); `confine(path, cwd, extra_roots)` `scope.py:36-56` keeps ValueError-naming-roots shape; callers pass `_policy_roots(cwd)` union (`diff_gate.py:229-241,266,379,430`); `decide()` docstring states policy-before-confine ordering (`policy.py:474-480`).
- router.py /policy show is reply-only; approval prompts in gate layer, never router replies: PASS — `/policy` returns `("reply", ...)` (`router.py:68-69`); `router.py` contains zero `input(` calls (grep count 0); prompt rendering lives in `policy_gate.py:190-242` inside `output_context`.

## Prohibitions

- No two HumanInTheLoop instances: PASS — single construction site (`policy_gate.py:268`); repo-wide grep finds `HumanInTheLoop(` only there; collision test `tests/test_policy_gate.py:115-119` proves two collide.
- No "smart", NL-policy strings, LLMClassifierConfig, Cedar: PASS — grep over `strands_code_cli/` + `strands_code_agent/` finds none outside prohibitive comments/docstrings; `build_interventions` takes an instance, never a sugar string.
- No Phase 4 mode vocabulary (plan/act/yolo/auto, effort presets) in policy schema: PASS — schema keys are exactly `{options, allow, deny}` / `{trust_delegated}` / `{tool, path, command}` (`policy.py:69-71`); no plan/act/yolo/effort strings in `policy.py`/`policy_gate.py`.
- No semantic/LLM risk classification or host allowlist: PASS — classification is prefix/substring/flag parsing only (`policy.py:323-432`); D-16 any-host explicit (`policy.py:493-494`); no host-matching code anywhere.
- No approval prompts through router reply actions: PASS — router has no `input(`, no ask, no classifier imports at module level (lazy `PolicyConfig`/`last_covered` imports inside `_policy_message` for read-only reporting).
- No enable_trust=True: PASS — string appears only in `policy_gate.py:21` docstring stating it is NOT used; no `enable_trust` kwarg passed to any constructor.

## Findings / residuals (accepted per plan, not failures)

- `policy_gate.py:8-13` documents the intentional deviation from 03-PLAN.md resolved item 5's literal "Deny → requires_approval False" text (would fail open); implemented as requires-approval + `DENY:` reason → ask short-circuits to refusal + `"n"`. Correct fail-closed call.
- Accepted residuals carried per D-14/risk 5: `VAR=` indirection, exotic binaries, `python_repl` interior `open()`/`socket` unconfined (documented `policy.py:42-47`).
- Shell 120 s timeout still upstream default (T-03-10 accepted); GET-param exfiltration accepted (T-03-09).
