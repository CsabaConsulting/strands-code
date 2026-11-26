# Strands Code — Engineering & Discussion Rules

> Committed project rules for AI coding agents working on this repository.
> Kept outside GSD-managed sections in `AGENTS.md` (which sits near the 24 KB per-file rule limit).
> Full per-layer checklists live in [.planning/INVARIANTS.md](.planning/INVARIANTS.md).

## 1. Five Habits for Design Discussions & Planning

Apply these rules in every `/gsd-discuss-phase`, `/gsd-plan-phase`, design review, or cross-cutting PR:

1. **Present a Peer Parity Matrix before asking design questions.**
   Whenever a task touches a recurring cross-cutting axis — model providers, routing engines, protected/sensitive paths, config/cache persistence, `/cost` spend lanes, env vars, or CLI/slash surfaces — show a compact 1-table view of how *every existing peer* behaves today before presenting options. Label any option that diverges from peers with `⚠️ Breaks parity with Phase X`.

2. **Enforce one atomic decision per question (reject bundled options).**
   Never combine two independent design choices into a single option row (for example, coupling two separate opt-in flags, or bundling policy-protection scope with integration-test scope). Split independent axes into separate single-axis questions.

3. **Make "Match Existing Pattern" the default burden of proof.**
   Treat cross-peer symmetry as the baseline. Any option proposing a special case (e.g., opt-in flag instead of auto-detection, config-only instead of `/route setup`, `actual` instead of `estimated` spend, fail-soft instead of fail-loud) must state the specific technical or security threat that justifies the exception.

4. **Verify constraint claims with `file:line` references and live metrics.**
   Never justify a compromise or deferral with an unverified *"we can't because of `xenon` / upstream SDK / default-deny / Dogwood"* claim. Inspect the exact `file:line` and run live checks (e.g., `.venv/bin/radon cc`, upstream `.venv` source inspection) before presenting options or locking a plan.

5. **Maintain Cross-Cutting Checklists and apply the Horizontal Backport Rule.**
   - **Cross-cutting axes:** Before adding or updating a model provider, routing engine, protected path, or persisted store, touch every column of the matching checklist in [.planning/INVARIANTS.md](.planning/INVARIANTS.md) (`pyproject.toml`, `_SDK_EXTRA_HINTS`, `first_run.py`, `supports_reasoning`, `discover_*_models`, `live_pricing.py`, `scrub_credentials`, `sandbox/box.py`, `tests/conftest.py`, etc.).
   - **Horizontal backport:** Whenever a phase hardens or fixes a shared pattern (e.g., network timeout/retry caps, `mkstemp` + `0o600` + ancestor/target symlink refusal, credential scrubbing regexes, unsafe-char validation, protected-path downgrades), sweep **all existing peer functions** across `strands_code_cli/` in the same phase/PR rather than hardening only the newest addition.

## 2. Non-Negotiable Repository Invariants

- **Upstream fork boundary (`D-24`):** Keep `strands_code_agent/` unmodified on `main` (`git diff ee42ea2 -- strands_code_agent/` empty) so upstream resyncs stay conflict-free. Put CLI-specific code and temporary upstream-PR workarounds in `strands_code_cli/` as isolated, auto-retiring bridges; only edit `strands_code_agent/` on a dedicated upstream-PR branch or with explicit user approval when wrapping from `strands_code_cli/` is impossible.
- **Restricted-module hygiene:** Zero `os.environ`/`os.getenv` tokens and zero unnegated `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings in `entry/main.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, or `cost/cost_context.py`.
- **Static CI gates:** Every code change must pass `ruff format --check`, `ruff check`, `xenon --max-absolute C` (`CC <= 20`), `lint-imports`, and `uv lock --check`.
- **No unilateral shifts in pre-decided anchors:** Never bury parity breaks or cross-phase overrides inside "pre-decided / not re-asked" preambles; surface them explicitly.
