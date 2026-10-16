# Phase 12: Structural Review + Hygiene - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-16
**Phase:** 12-structural-review-hygiene
**Areas discussed:** Measurement gate, Breakup scope, Import compatibility, Rig split shape, Cleanup scope

---

## Measurement gate

Q1: What should measure complexity and coupling?

| Option | Description | Selected |
|--------|-------------|----------|
| Radon + coupling | Use radon/xenon for cyclomatic complexity plus a coupling check (e.g. import graph). Purpose-built, new dev deps. | ✓ |
| Ruff C901 | Adopt ruff with complexity rules (C901) as the single tool. Also buys linting, bigger change. | |
| Stdlib only | Line counts + hand-rolled import analysis with stdlib only. Zero new deps, least rigorous. | |

**User's choice:** Radon + coupling
**Notes:** None

Q2: Should the measurement gate persist or is it one-shot?

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent gate | Thresholds are recorded and enforced on every run (CI + pre-commit). No regressions allowed. | ✓ |
| One-shot report | Measure once to drive this breakup, then drop the tooling. No ongoing enforcement. | |

**User's choice:** Persistent gate
**Notes:** None

Q3: What complexity thresholds should the gate enforce?

| Option | Description | Selected |
|--------|-------------|----------|
| Standard grades | Standard radon grades: fail on functions worse than C (complexity > 20), warn on C. Industry default. | ✓ |
| Monsters only | Fail only on F-grade monsters (complexity > 30+). Minimal churn, catches the worst. | |
| Calibrate first | Measure the tree first, then set thresholds from the actual distribution. Data-driven, planner proposes. | |

**User's choice:** Standard grades
**Notes:** None

Q4: Where should the measurement report live?

| Option | Description | Selected |
|--------|-------------|----------|
| Committed report | The numbers live in a committed report (e.g. .planning or docs/) that the breakup cites. Auditable. | ✓ |
| CI output only | Numbers stay in CI output and planner notes. No committed artifact. | |

**User's choice:** Committed report
**Notes:** None

---

## Breakup scope

Q1: How far should the CLI breakup go?

| Option | Description | Selected |
|--------|-------------|----------|
| Giants only | Split loop.py, routing.py, router.py (all 2000+ lines) into coherent submodules. The measured pain. | |
| Giants + mid-size | Also split mid-size modules (500-800 lines: memory_file, policy_gate, model_switch, cost_context). Deeper change. | |
| Full repackage | Reorganize the whole flat layout into feature packages regardless of size. Biggest diff. | ✓ |

**User's choice:** Full repackage
**Notes:** None

Q2: What package layout should the breakup follow?

| Option | Description | Selected |
|--------|-------------|----------|
| By feature | Group by feature area (loop/, routing/, dispatch/) with related helpers together. Matches how work is discussed. | ✓ |
| By layer | Group by technical layer (core/, ui/, config/, tools/). Cleaner layering, splits features apart. | |

**User's choice:** By feature
**Notes:** "but also keep layers in mind"

Q3: Should tests mirror the new package layout?

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror layout | Mirror the new package layout in tests/ (45 files move too). Consistent, large diff. | ✓ |
| Leave flat | Leave tests/ flat; only update imports. Smaller diff, layout diverges. | |

**User's choice:** Mirror layout
**Notes:** None

Q4: CLI only, or does the agent library get restructured too?

| Option | Description | Selected |
|--------|-------------|----------|
| CLI only | Review covers the CLI only. The agent library keeps its shape. | ✓ |
| Whole tree | The agent library gets measured and restructured too. Whole-tree review. | |

**User's choice:** CLI only
**Notes:** "The aim is to be able to receive updates from the forked upstream"

---

## Import compatibility

Q1: Do old import paths keep working after the repackage?

| Option | Description | Selected |
|--------|-------------|----------|
| Shims | Old paths (strands_code_cli.loop) keep working via re-export shims. Zero breakage for external importers. | |
| Clean break | Old paths break; all imports (code, tests, scripts) move to the new layout. Clean, no legacy cruft. | ✓ |

**User's choice:** Clean break
**Notes:** None

Q2: Does the CLI entry point stay put?

| Option | Description | Selected |
|--------|-------------|----------|
| Unchanged | The strands-code entry point and CLI surface stay byte-identical. Only internal paths move. | |
| Reorganize too | Reorganize the entry point too (e.g. __main__ layout changes). More churn, no user gain. | ✓ |

**User's choice:** Reorganize too
**Notes:** "(if that doesn't hurt potential upstream change merges)"

Q3: With a clean break, what happens to external importers?

| Option | Description | Selected |
|--------|-------------|----------|
| In-repo only | Only in-repo importers (code, tests, scripts) are updated. External importers break loudly. | ✓ |
| Migration note too | Publish a migration note mapping old paths to new ones. Helps anyone importing us. | |

**User's choice:** In-repo only
**Notes:** None

Q4: How far may the entry-point reorganization go?

| Option | Description | Selected |
|--------|-------------|----------|
| CLI-internal | Entry reorganization stays inside strands_code_cli (main.py moves with its feature). Upstream-merge safe. | ✓ |
| Anywhere + proof | Entry may move anywhere including repo-root layout changes. Planner proves merge safety. | |

**User's choice:** CLI-internal
**Notes:** None

---

## Rig split shape

Q1: Should rig plumbing live in one shared library?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared lib | Extract tmux/send/wait/save plumbing into a shared uattest library; scenarios import it. One plumbing owner. | ✓ |
| Self-contained | Each scenario file carries its own copy of the helpers. No shared code, drifts apart. | |

**User's choice:** Shared lib
**Notes:** None

Q2: How should driver.py scenarios be divided?

| Option | Description | Selected |
|--------|-------------|----------|
| Per area | One file per scenario area (side, routing, native, cost, codeact). Matches how UAT uses them. | ✓ |
| Per scenario | One file per scenario (12+ files). Finest grain, most files. | |
| Helpers + rest | Two files: helpers + all scenarios. Smallest diff, scenarios still crowded. | |

**User's choice:** Per area
**Notes:** None

Q3: What happens to the driver.py entry point?

| Option | Description | Selected |
|--------|-------------|----------|
| Thin dispatch | driver.py stays as the thin dispatch entry (usage + scenario routing). Same command, new innards. | ✓ |
| New entry | Replace driver.py with a package CLI (uattest/runner.py or similar). New invocation to learn. | |

**User's choice:** Thin dispatch
**Notes:** None

Q4: Should rig contract tests split with the rig?

| Option | Description | Selected |
|--------|-------------|----------|
| Split to mirror | test_uattest_driver.py splits to mirror the new rig files. Consistent with the tests-mirror-layout rule. | ✓ |
| Single file | One contract test file importing from the new locations. Less churn. | |

**User's choice:** Split to mirror
**Notes:** None

---

## Cleanup scope

Q1: Remove the knowledge module too, or just the example?

| Option | Description | Selected |
|--------|-------------|----------|
| Remove both | Remove the example AND strands_code_agent/knowledge (its only consumer is the example). No dead code left. | ✓ |
| Example only | Remove only examples/pdf_to_okf_bundle + README row; keep the knowledge module for future use. | |

**User's choice:** Remove both
**Notes:** Git history shows knowledge/ is fork-added ("Feature Request: Document processing library set"), so removal is upstream-merge safe; planner to confirm no upstream overlap

Q2: How should the README change?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop row | Drop the OKF row and reword the surrounding section so it reads clean. Minimal diff. | |
| Full rewrite | Rewrite the README features table fully for the post-cleanup tree. Bigger, more coherent. | ✓ |

**User's choice:** Full rewrite
**Notes:** None

Q3: Cleanup before or after the repackage?

| Option | Description | Selected |
|--------|-------------|----------|
| Cleanup first | Delete the example + knowledge module first, then measure and repackage. Dead code out before numbers. | ✓ |
| Cleanup last | Repackage first, clean up at the end. Review first, hygiene last. | |

**User's choice:** Cleanup first
**Notes:** None

---

## the agent's Discretion

Package names and boundaries, coupling metric choice, report format/location, pre-commit wiring, README prose (recorded in CONTEXT.md).

## Deferred Ideas

- Ruff adoption, agent-library restructuring, external-importer migration note (recorded in CONTEXT.md).

---

## Amendment (2026-10-16, post-discussion)

User: "Besides the cyclomatic complexity I also want to add ruff to this phase for general code formatting and hygiene." Recorded as D-18 (ruff check + format, config in pyproject.toml, enforced by the persistent gate) and D-19 (formatting lands before the repackage moves). Ruff removed from Deferred Ideas. Rule selection and line length left to planner/executor discretion.
