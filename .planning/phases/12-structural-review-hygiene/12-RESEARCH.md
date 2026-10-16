# Phase 12: Structural Review + Hygiene - Research

**Researched:** 2026-10-16
**Domain:** Python static-analysis gating (radon/xenon, ruff, import-linter), package repackaging with history preservation, dead-code removal
**Confidence:** HIGH

**Dispatch note:** Produced via generic-agent workaround (typed `gsd-phase-researcher` dispatch unavailable). This file follows the researcher role contract: provenance tags on factual claims, Runtime State Inventory (refactor phase), Validation Architecture, Security Domain. The `gsd_run` seams (`research-plan`, `classify-confidence`, `package-legitimacy`) were not available in this sandbox, so provider routing and the legitimacy gate were executed manually (Tavily for docs/web, PyPI metadata + package source inspection for legitimacy). Confidence tiers below are the researcher's honest assessment under that constraint.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Measurement gate
- **D-01:** radon/xenon for cyclomatic complexity plus an import-graph coupling check (new dev deps, supply-chain review applies).
- **D-02:** Persistent gate — thresholds enforced on every run (CI + pre-commit), not a one-shot report.
- **D-03:** Standard grades — fail on functions worse than C (complexity > 20), warn on C.
- **D-04:** Committed report — the numbers live in a committed report the breakup cites.

#### Breakup scope
- **D-05:** Full repackage — reorganize the whole flat `strands_code_cli/` layout into feature packages, not just the three giants. — **Reversibility:** one-way — the package layout is a published import contract; undoing it means a second flag-day move.
- **D-06:** By feature, keeping layers in mind — group by feature area (loop/, routing/, dispatch/) with layer sensibility, not strict layering.
- **D-07:** Tests mirror — `tests/` moves with the new package layout (all 45 files).
- **D-08:** CLI only — `strands_code_agent/` keeps its shape so the fork can still receive upstream updates. The sole exception is the knowledge-module removal (D-15), which is fork-added code.
- **D-09:** Clean break — old `strands_code_cli.<module>` paths break; all in-repo imports move; no re-export shims.
- **D-10:** Entry reorganization allowed if CLI-internal and upstream-merge safe (main.py moves with its feature).
- **D-11:** In-repo only — external importers break loudly; no migration note published.
- **D-12:** The CLI-internal bound is the merge-safety rule: nothing in the repackage may touch `strands_code_agent/` except D-15 or the repo-root layout.

#### Rig split shape
- **D-13:** Shared lib — tmux/send/wait/save plumbing extracts into one uattest library; scenarios import it.
- **D-14:** Per area — one scenario file per area (side, routing, native, cost, codeact); `driver.py` stays a thin dispatch entry with the same command; contract tests split to mirror.

#### Cleanup scope
- **D-15:** Remove both — `examples/pdf_to_okf_bundle` plus `strands_code_agent/knowledge` (fork-added per git history: "Feature Request: Document processing library set"; planner must confirm no upstream overlap before deleting).
- **D-16:** Full README rewrite of the features table for the post-cleanup tree (not just dropping the OKF row).
- **D-17:** Cleanup first — dead code is deleted before measurement, so the numbers describe the tree being repackaged.

#### Lint and format (added post-discussion 2026-10-16, discussed same day)
- **D-18:** Ruff governs general lint + format (`ruff check` and `ruff format`); config lives in `pyproject.toml`. The whole tree is formatted once during the phase, and the persistent gate (D-02) enforces ruff-clean on every run alongside the complexity thresholds.
- **D-19:** Ruff formatting lands before the repackage moves (with cleanup first, D-17), so later diffs show moves, not reformatting.
- **D-20:** Rule scope is F+E+I core (pyflakes + pycodestyle errors + isort); radon/xenon keep the complexity gate — no ruff C901 overlap (D-01 unchanged).
- **D-21:** Format style is ruff defaults: 88 columns, double quotes.
- **D-22:** All pre-existing violations are fixed in one pass (no grandfathering); waivers are per-line `noqa` with a reason only — no file-level ignores.
- **D-23:** Auto-fix runs freely (`ruff format` plus `ruff check --fix`); the green suite is the safety proof.
- **D-24:** Fork-added code only (user pressed twice — amends D-01/D-02/D-18): ruff AND the complexity gate apply exclusively to code added in this fork (`strands_code_cli/`, `tests/`, `scripts/`, and other fork-owned paths). Inherited upstream code (`strands_code_agent/` minus fork-added parts) is neither measured, gated, formatted, nor fixed — keeping it byte-pristine for upstream merges. — **Reversibility:** costly — the gate's path scope shapes CI config and merge hygiene; widening it later re-opens the upstream question.

### the agent's Discretion

Exact package names and boundaries, the coupling metric choice, report location and format, pre-commit wiring details, the fork-added path list derivation, and README prose are left to planner/executor judgment within the locked decisions above.

### Deferred Ideas (OUT OF SCOPE)

- Agent-library restructuring — out of scope for upstream-merge safety (D-08).
- External-importer migration note — rejected (D-11); break loudly instead.

None of the above belong in Phase 12 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRUCT-01 | Codebase passes a measurement-first structural review: complexity and coupling measured, oversized modules broken up, CLI organized into packages, rig split into per-area files — full suite and rig green throughout | Standard Stack (radon/xenon/ruff/import-linter + verified invocations), Architecture Patterns (sequencing, git-mv history preservation, rig-split import pattern), Validation Architecture (gate exit codes verified: xenon/ruff exit 1 on breach) |
| CLEANUP-01 | Repo contains no dead example code; README references only shipped surfaces (examples/pdf_to_okf_bundle removed) | CF-01 upstream-overlap finding + merge-consequence analysis, README/test_readme_examples pin inventory, removal target file list |
</phase_requirements>

## Project Constraints (from AGENTS.md)

Actionable directives extracted from `AGENTS.md` (read this session). Planner must verify compliance:

- **Python >= 3.10, `uv` toolchain.** All gates run via `uv run` / `uvx`; CI uses `astral-sh/setup-uv`, never bare `pip`. New tools go in the `dev` dependency group in `pyproject.toml` [VERIFIED: AGENTS.md:13,30-32].
- **AWS-optional, never AWS-required.** Gates must be hermetic — no credentials, no network at gate time. (Xenon's `--url` POST option must NOT be used.)
- **No upper pins during the experimental phase.** Declare dev deps without upper bounds (bare names or lower bounds); `uv.lock` records the resolved pins [VERIFIED: AGENTS.md:15].
- **Absolute imports rooted at the package, no relative imports** [VERIFIED: AGENTS.md:106]. Applies to the repackaged CLI tree AND the uattest split (this rules out `from .lib import …` in scenario files unless the loader changes — see CF-07).
- **`snake_case.py` modules; tests mirror the module under test** (`tests/test_<module>.py`) [VERIFIED: AGENTS.md:85-86]. Reinforces D-07.
- **Triple-double-quoted docstrings on every public function/class/method; `UPPER_SNAKE_CASE` module constants; leading-underscore privates** [VERIFIED: AGENTS.md:89-94,129]. Ruff F+E+I does not check docstrings — this convention stays manual; the repackage must carry docstrings along.
- **`# noqa` precedent exists** (`# noqa: F401` in `strands_code_agent/__init__.py`) — compatible with D-22 per-line waivers [VERIFIED: AGENTS.md:102].
- **SUPERSEDED by D-18:** "No formatter or linter is configured … Match the surrounding file's existing style by hand" [VERIFIED: AGENTS.md:98]. After this phase that paragraph is false; planner should include an AGENTS.md conventions refresh (and the `codebase/CONVENTIONS.md` source it is generated from) as a trailing task.
- **Docs drift:** `AGENTS.md` architecture section documents the `knowledge/` subsystem that D-15 removes [VERIFIED: AGENTS.md:161-164,188-190]. Same refresh task covers it.

## Summary

Phase 12 is a pure-structure phase: measure complexity and coupling on the fork-owned tree, gate them persistently (CI + pre-commit), repackage the flat 28-module `strands_code_cli/` layout (~15k lines) into feature packages, split the 1069-line uattest driver into a shared lib plus five per-area scenario files, adopt ruff for lint+format, and delete the dead OKF example plus its knowledge module. No behavior changes; the suite (45 test files) and the rig stay green throughout.

The locked decisions are implementable as specified with tooling verified working in this environment (radon 6.0.1, xenon 0.9.3, ruff 0.17.1 all trial-ran on the repo's Python 3.14.8). Three findings need planner attention before tasking: (1) D-15's own precondition fails — the knowledge module and example exist byte-identical in `upstream/main`, so deletion removes upstream code with merge consequences; (2) the complexity gate provably FAILS on the current tree (`run_loop` F(75), `_pump_parallel` F(46)), so enforcement must be staged, not flipped on day one; (3) D-12's "don't touch `strands_code_agent/`" collides with D-09's "all in-repo imports move" at exactly one line (`search_tool.py:18`, itself fork-added). Details in Critical Findings.

**Primary recommendation:** Sequence cleanup → ruff format+fix → measure+commit report → repackage → rig split → README; wire xenon (`-b C`), ruff (`check` + `format --check`), and import-linter (forbidden + layers contracts) as fork-path-scoped gates in a new CI workflow and a new pre-commit config with `force-exclude = true`; escalate CF-01 and CF-02 to the user before planning.

## Critical Findings for Planner

### CF-01 — D-15's no-upstream-overlap precondition FAILS (escalate to user)
D-15 says "planner must confirm no upstream overlap before deleting." Overlap confirmed:
- Commit `b1de584` ("Feature Request: Document processing library set") is contained in `upstream/main` [VERIFIED: `git branch -r --contains b1de584` lists `upstream/main`; commit dated 2026-06-29, author Emilio Monti].
- The fork's copies are byte-identical to upstream: `git diff upstream/main..HEAD -- strands_code_agent/knowledge/ examples/pdf_to_okf_bundle/` is empty [VERIFIED: this session].
- Consequence: deleting these paths deletes upstream code. A later `git merge upstream/main` stays clean only while upstream never touches those paths; if upstream modifies them, the merge yields delete/modify conflicts [ASSUMED — standard git merge semantics]. This also tensions D-24's "byte-pristine for upstream merges" rationale.
- Planner action: re-confirm D-15 with the user (delete upstream-identical code anyway vs descope code deletion to README-only). Research does not override the locked decision; it reports the failed precondition.

### CF-02 — D-12 vs D-09 collide at one import line (needs D-12 amendment)
- `strands_code_agent/search_tool.py:18` contains verbatim `from strands_code_cli.scope import confine` [VERIFIED: strands_code_agent/search_tool.py:18] — a real agent→CLI runtime dependency (backwards layering; prime coupling-review exhibit).
- `search_tool.py` is fork-added (`git log` shows only `ad5d7c5 feat(phase-2)…`) [VERIFIED: this session], so editing it is merge-safe in practice — but D-12 forbids touching `strands_code_agent/` except D-15, while D-09 requires ALL in-repo imports to move. One of them must yield for this line.
- Planner action: amend D-12 to permit import-line updates in fork-added files under `strands_code_agent/` (exactly one file: `search_tool.py`), or route `confine()` ownership through the breakup design. (The `strands_code_cli` mention in `code_agent.py:13` is a comment only — leave it per D-12.)

### CF-03 — The complexity gate is RED on the current tree (stage enforcement)
Trial run on Python 3.14.8 [VERIFIED: this session]:
- `radon cc strands_code_cli/loop.py` reports `run_loop - F (75)`, `_pump_parallel - F (46)`, `_route_pre_turn - D (25)`, plus seven C-rank blocks (11–19).
- `xenon -b C strands_code_cli/loop.py` exits 1 [VERIFIED: exit code captured].
- Planner action: D-02's "persistent gate" cannot be flipped to enforcing before the breakup reduces these blocks (or the breakup plan explicitly re-shapes them). Recommended staging: wire gates in report/non-blocking mode during measure → flip CI to blocking after breakup lands → pre-commit hooks last (they only see changed files; see CF-06).

### CF-04 — E501 fires under the locked F+E+I scope (recommend `ignore = ["E501"]`)
- Empirical probe: with `select = ["E", "F", "I"]`, ruff 0.17.1 flags a 96-char line as `E501 Line too long (96 > 88)` [VERIFIED: /tmp probe this session]. Explicit `E` select includes E501 (it is only excluded from ruff's *default* rule set).
- Standard practice is that the formatter owns line length and E501 stays off when `ruff format` governs (D-18/D-21 lock the formatter). A global `ignore = ["E501"]` is rule-scope configuration, not a file-level ignore, so it does not violate D-22's "no file-level ignores" — but it does narrow D-20's `E`. Planner decides: `ignore = ["E501"]` (recommended) vs fix-every-overlong-line including strings/comments the formatter cannot split (formatter leaves long strings/comments; each becomes a manual fix or per-line `noqa`).
- `ruff check` exits 1 on violations; `ruff format --check` exits 1 when reformatting is needed [VERIFIED: exit codes captured].

### CF-05 — `force-exclude = true` is REQUIRED for D-24 (verified docs)
- "Files that are passed to `ruff` directly are always analyzed … unless `force-exclude` is also enabled" and "This is useful for `pre-commit`, which explicitly passes all changed files" [CITED: https://docs.astral.sh/ruff/configuration/ and https://docs.astral.sh/ruff/settings/#force-exclude]. Without it, pre-commit's explicit filenames bypass `exclude`, and a commit touching upstream code would gate upstream code — a D-24 violation.

### CF-06 — Xenon has no verified pre-commit-hooks manifest (use `repo: local`)
- Fetching `rubik/xenon`'s `.pre-commit-hooks.yaml` failed (no manifest found at the `master` path) [VERIFIED: fetch error this session; branch-name variant not ruled out — see A1]. Xenon's README documents pre-commit `args` (`['--max-absolute=B', …]`, `=` or split-list form) [CITED: https://github.com/rubik/xenon] but the hook `repo:` side could not be confirmed.
- Planner action: define xenon (and import-linter) as `repo: local` hooks invoking `uv run --group dev …` with explicit fork paths + D-24 `exclude:` regex. This is robust regardless of upstream manifests and matches the uv-only constraint.

### CF-07 — The rig-split import pattern is constrained by the test loader
- `tests/test_uattest_driver.py` (and `test_routing_calibration.py`) load the driver via `importlib.util.spec_from_file_location("uattest_driver", DRIVER)` as a *top-level* module [VERIFIED: tests/test_uattest_driver.py:25-29]. Relative imports (`from .lib import …`) inside split files BREAK under this loader (no parent package context).
- Compatible options: (a) `driver.py` + siblings use a `sys.path` insert of the `scripts/uattest/` dir with absolute sibling imports (keeps loader + AGENTS.md absolute-import rule); (b) package-ify `scripts/uattest/` (`__init__.py`) and change the loader to a package import (touches the contract tests' loading mechanism itself).
- The contract tests also assert on *source text*: `DRIVER.read_text()` must contain `"a1"`/`"a2"` (dispatch table stays in `driver.py` — consistent with D-14's thin dispatch), and `inspect.getsource(driver.scenario_*)` / `monkeypatch.setattr(driver, "pane_text", …)` require the split tests to import the same objects from their new homes (D-14's "split to mirror" covers this, but every assertion in the inventory in Pitfalls P5 must be re-homed, not dropped).

### CF-08 — The installed console script freezes the entry import (re-sync per move)
- `.venv/bin/strands-code` contains verbatim `from strands_code_cli.main import main` [VERIFIED: .venv/bin/strands-code:4], generated at install time from `[project.scripts] strands-code = "strands_code_cli.main:main"` [VERIFIED: pyproject.toml:43-44]. Moving `main.py` (D-10) breaks `uv run strands-code` until `[project.scripts]` is updated AND `uv sync` regenerates the script. Every move commit touching the entry path must re-sync to keep the "suite and rig green" criterion (the rig shells out to the `strands-code` CLI via a hardcoded `uv run --project … strands-code` command [VERIFIED: scripts/uattest/driver.py:30]).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Complexity measurement + report | Dev machine (one-shot radon runs) | — | Produces the D-04 committed report; human reads numbers before breakup |
| Complexity gate enforcement | CI runner (new workflow) | Dev machine (pre-commit) | D-02 persistent gate; CI is the source of truth, pre-commit is the fast feedback |
| Lint + format enforcement | CI runner | Dev machine (pre-commit) | Same shape as complexity gate (D-18); ruff hooks precede format hooks |
| Coupling contracts | CI runner | Dev machine (pre-commit) | import-linter is deterministic and fast; same two-tier wiring |
| Package repackage + import moves | Repo tree (`strands_code_cli/`, `tests/`) | — | Flag-day move; suite green at every commit is the guardrail |
| Rig split | Repo tree (`scripts/uattest/`, rig contract tests) | — | Same CLI command surface; scenario files are fork-owned scripts |
| Cleanup + README | Repo tree + docs | — | Deletion first (D-17), README rewrite last (D-16) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| radon | 6.0.1 | Cyclomatic complexity + raw metrics measurement | The Python CC standard; xenon builds on it; trial-ran on this repo's Python 3.14.8 [VERIFIED: PyPI index + trial run this session] |
| xenon | 0.9.3 | Complexity threshold gate (exits non-zero on breach) | Purpose-built radon monitor with grade thresholds and pre-commit/CI usage; trial-ran here [CITED: https://github.com/rubik/xenon; VERIFIED: PyPI index + trial run] |
| ruff | 0.17.1 | Lint (`check`, F+E+I) + format | Single-tool lint/format standard; pyproject-native config; E501-under-`E` and exit codes verified [CITED: https://docs.astral.sh/ruff/; VERIFIED: PyPI index + probes] |
| import-linter | 2.15 | Import-graph coupling contracts (forbidden/layers), CI-gatable | Purpose-built architecture gate; `pyproject.toml [tool.importlinter]` support verified in its own source [CITED: https://import-linter.readthedocs.io/; VERIFIED: PyPI index + source inspection] |
| pre-commit | 4.7.0 | Local hook framework for D-02's pre-commit half | Standard hook runner; ruff ships an official hook repo [VERIFIED: PyPI index; CITED: https://github.com/astral-sh/ruff-pre-commit] |

Radon rank scale (D-03's "standard grades"), verified in radon 6.0.1's own test suite (`radon/tests/test_complexity_utils.py:20-31`): A 0–5, B 6–10, C 11–20, D 21–30, E 31–40, F 41+. D-03 "fail worse than C (> 20)" maps exactly to xenon `--max-absolute C`, because xenon thresholds are inclusive: `-b B` fails blocks ranked C or worse [CITED: https://github.com/rubik/xenon]. "Warn on C" has no xenon switch — C-rank blocks surface in the radon report (D-04), not the gate.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv / uvx | 0.12.23 (installed) | Runs all gates (`uv run --group dev …`); `uvx` for one-shot probes | Every gate invocation, local and CI [VERIFIED: `uv --version` this session] |
| astral-sh/setup-uv | v8.1.0+ (pin a full tag) | Installs uv + Python in the gate workflow | New CI workflow [CITED: https://docs.astral.sh/uv/guides/integration/github] |
| astral-sh/ruff-pre-commit | pin `rev:` == dev ruff version (v0.17.1) | Official ruff + ruff-format hooks | `.pre-commit-config.yaml`; keep rev in lockstep with the dev dep to avoid skew |
| git mv + rename detection | git 2.55.0 (installed) | History-preserving moves | Every repackage/test-mirror commit [VERIFIED: `git --version`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| xenon gate | complexipy | Modern, fast, pyproject-native — but D-01 locks radon/xenon; keep as fallback if xenon ever breaks on a future interpreter |
| import-linter | pydeps 3.0.9 | Graph visualization for the D-04 report figure, but no threshold gate and needs graphviz for images; use only if the report wants a picture |
| import-linter | stdlib `ast` import-graph script | Fine for a one-shot report graph; do NOT hand-roll the persistent gate (contract drift, no ecosystem) |
| ruff C901 | (rejected) | D-20 explicitly keeps complexity with radon/xenon; no C901 overlap |

**Installation:**

```bash
uv add --dev radon xenon ruff import-linter   # no upper pins per AGENTS.md; uv.lock records resolution
uv tool install pre-commit                    # environment tool, not a project dep
pre-commit install                            # registers hooks in .git/hooks (per-clone step)
```

**Version verification:** all versions above were confirmed against the PyPI registry via `pip index versions` this session (radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15, pydeps 3.0.9, pre-commit 4.7.0). Compatibility: xenon 0.9.3 declares `radon<7,>=4` (radon 6.0.1 satisfies it) [VERIFIED: xenon 0.9.3 wheel METADATA]; import-linter 2.15 declares `Requires-Python: >=3.10` (matches the project's `>=3.10`) [VERIFIED: wheel METADATA]; radon/xenon wheels declare no `Requires-Python` (absence, not a constraint — but both were trial-executed on Python 3.14.8 here with pasted output, which is the operative proof).

## Package Legitimacy Audit

> The automated `package-legitimacy` seam was unavailable in this sandbox (generic-agent workaround); the audit below was performed manually against PyPI metadata, wheel METADATA, and official repos. Planner: treat as MEDIUM confidence and re-run the seam check at plan time if available.

| Package | Registry | Age signal | Source Repo | Verdict | Disposition |
|---------|----------|-----------|-------------|---------|-------------|
| radon 6.0.1 | PyPI | Versions back to 0.2 (10+ yrs) | github.com/rubik/radon (per wheel Home-page/Project-URL) | OK | Approved |
| xenon 0.9.3 | PyPI | Versions back to 0.1; MIT; 282 stars | github.com/rubik/xenon | OK | Approved (note: README claims testing only through 3.12; verified working on 3.14.8 this session) |
| ruff 0.17.1 | PyPI | Versions back to 0.0.13; Astral-published binary wheels | github.com/astral-sh/ruff (per docs.astral.sh/ruff) | OK | Approved |
| import-linter 2.15 | PyPI | Versions back to 1.0; BSD-2-Clause | seddonym/import-linter (per readthedocs badges) | OK | Approved |
| pre-commit 4.7.0 | PyPI | Versions back to 0.2.x | github.com/pre-commit/pre-commit [ASSUMED — canonical repo, not re-verified this session] | OK | Approved (env tool) |

**Packages removed due to SLOP verdict:** none.
**Packages flagged as suspicious (SUS):** none.
**Transitives pulled in:** mando, colorama (radon); requests, PyYAML (xenon — PyYAML already a main dep); click, grimp, rich, typing-extensions (import-linter — rich already a main dep). All are established packages; no `postinstall` concept executes for wheels under pip/uv [ASSUMED — standard installer behavior].

## Architecture Patterns

### System Architecture Diagram

Data flow through the phase ( gates are the persistent product; moves are the one-shot work):

```text
  developer edit
       │
       ▼
 ┌─────────────┐   changed .py files    ┌──────────────────────┐
 │  pre-commit  │ ─────────────────────▶ │ ruff check --fix     │──▶ re-stage fixes
 │  (local)     │                        │ ruff format          │──▶ re-stage format
 └─────────────┘                        │ xenon -b C (local)   │──▶ block commit on D/E/F
       │                                │ lint-imports (local) │──▶ block on contract break
       │ commit                         └──────────────────────┘  (upstream paths excluded
       ▼                                                          per D-24 at hook level)
 ┌─────────────┐
 │  git push   │
 └─────────────┘
       │
       ▼
 ┌─────────────────────────────────────────────────────────┐
 │ CI gate workflow (new file; only publish.yml exists now)│
 │  1. setup-uv + uv sync (locked)                         │
 │  2. pytest tests/ -q               (suite green)        │
 │  3. ruff check + ruff format --check (fork paths)       │
 │  4. xenon -b C <fork paths>         (fail > C)          │
 │  5. lint-imports                    (contracts kept)     │
 └─────────────────────────────────────────────────────────┘
       │ pass/fail
       ▼
  merge decision

  one-shot flow (phase execution order, locked by D-17/D-19):
  cleanup ──▶ ruff format+fix ──▶ radon measure ──▶ D-04 report ──▶ repackage
      ──▶ rig split ──▶ README rewrite ──▶ flip gates to blocking (CF-03)
```

### Recommended Phase-Internal Sequencing

Order is largely locked (D-17 cleanup first, D-19 format before moves); the research addition is the staged gate flip from CF-03:

1. Add dev deps + configs (pyproject `[tool.ruff]`, `[tool.importlinter]`), run `ruff format` + `ruff check --fix` once (D-19, D-23).
2. Delete removal targets (D-17 first — before measurement; blocked on CF-01 re-confirmation).
3. Run radon over fork paths, commit the D-04 report the breakup cites.
4. Repackage `strands_code_cli/` by feature (D-05/D-06) with `git mv` move-only commits; mirror `tests/` (D-07); update `[project.scripts]` + `uv sync` when the entry moves (CF-08).
5. Split the rig (D-13/D-14); re-home the source-text assertions (CF-07/P5).
6. Rewrite README features (D-16); refresh AGENTS.md conventions (superseded paragraph).
7. Flip CI gates to blocking; install pre-commit hooks; final full-suite + spot-rig green.

### Recommended Project Structure

Package names are planner/executor discretion (D-06 hints `loop/`, `routing/`, `dispatch/`). Non-negotiable structural properties from research:

- Feature packages with `__init__.py` re-exports kept minimal (today's root `__init__.py` re-exports only `main` [VERIFIED: strands_code_cli/__init__.py:1-5]); every module keeps absolute imports.
- `tests/` mirrors the new layout file-for-file (mechanical: no test-to-test imports exist [VERIFIED: grep this session]; `tests/__init__.py` exists so it stays a package).
- `scripts/uattest/`: `driver.py` (thin dispatch, same `driver.py {s1|…|a2}` command [VERIFIED: driver `__main__` chain]) + one lib + five scenario files; sibling imports absolute via `sys.path` insert (CF-07 option (a)) unless the planner takes option (b) deliberately.

### Pattern 1: History-preserving package move
**What:** `git mv` old path new path in a commit that contains ONLY renames; follow with separate commits for import rewrites and body edits.
**When to use:** Every repackage and test-mirror step.
**Why:** Git stores no rename metadata — "Turn off rename detection" (`git diff --no-renames`) exists because detection is similarity-based at diff/log time [VERIFIED: git 2.55.0 man text this session]. Pure-move commits maximize similarity so `git log --follow` and `blame` survive the flag day; mixing edits into the move commit degrades detection below threshold and severs history.
**Example:**
```bash
# Source: git-mv(1) / git-diff(1) man pages, git 2.55.0
mkdir -p strands_code_cli/loop
git mv strands_code_cli/loop.py strands_code_cli/loop/core.py
git commit -m "chore(12): move loop.py into loop/ (pure move, no edits)"
# then: rewrite imports, run uv run pytest tests/ -q, commit separately
```

### Pattern 2: D-24 three-layer path scoping
**What:** Scope every gate to fork-owned paths at three independent layers: (1) pyproject `exclude` + `force-exclude = true` for ruff; (2) explicit fork path args in CI invocations (`xenon -b C strands_code_cli tests scripts`); (3) pre-commit hook-level `exclude: ^strands_code_agent/(?!search_tool\.py)` regex so changed upstream files never reach a gate.
**When to use:** All gate wiring. Layer 3's lookahead keeps the single fork-added agent file (`search_tool.py` — the ONLY added file under `strands_code_agent/` vs `upstream/main` [VERIFIED: `git diff --diff-filter=A`]) gated while the rest of the package stays untouched.
**Fork-added derivation (discretion input):** `git diff upstream/main --name-only --diff-filter=A` = added (fork-owned); `--diff-filter=M` under `strands_code_agent/` = `callback_handler.py code_agent.py python_environments/base.py utils.py` (upstream files the fork already modified — note: "byte-pristine" is already aspirational, which does not change the locked D-24 scope but the planner should know).

### Anti-Patterns to Avoid
- **Re-export shims for old import paths:** explicitly rejected (D-09 clean break). Also note shims would double the import graph the coupling gate must reason about.
- **Relative imports in new packages:** violates the AGENTS.md absolute-import rule; in the rig split it additionally breaks the importlib test loader (CF-07).
- **Move+edit in one commit:** kills rename detection (Pattern 1); never combine.
- **Formatting after moves:** locked against (D-19); format first so move diffs are pure.
- **Gating `strands_code_agent/` wholesale** (bare `xenon .` / `ruff check .` in CI): violates D-24. Always use the three-layer scoping.
- **Deleting first, asking later (CF-01):** the removal targets are upstream-identical; deletion without the CF-01 re-confirmation risks an unapproved upstream-code delete.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cyclomatic complexity numbers | AST-walking counter | `radon cc` / `radon mi` | Decision-point counting has subtle rules (boolean ops, comprehensions, asserts); radon is the reference implementation |
| Threshold enforcement | Exit-code wrapper parsing radon text | `xenon -b C` | Inclusive grade semantics, module/average thresholds, `--exclude/--ignore` globs out of the box |
| Lint + format | Regex/style scripts | `ruff check` + `ruff format` | 800+ rules, autofix with safety model, formatter-linter compatibility handling |
| Coupling / layering gate | grep-based import audit | import-linter contracts (`forbidden`, `layers`, `independence`) | Transitive (indirect) import detection; grep only sees direct imports |
| Commit-time hooks | Custom `.git/hooks` shell scripts | pre-commit framework + `ruff-pre-commit` + `repo: local` hooks | Cross-hook arg passing, file filtering, rev pinning, `pre-commit run --all-files` for CI parity |
| Import rewriting at scale | Hand-editing 60+ files | Scripted rewrite (python `ast`/regex pass) + `pytest` to catch stragglers | 33 test files + 19 CLI modules + 2 scripts + pyproject reference `strands_code_cli` [VERIFIED: grep counts]; plus 2 driver string literals (driver.py:295-296) and the route-probe re-exec import |

**Key insight:** this phase's persistent value is the *gates*, not the moves. A hand-rolled gate script rots (threshold drift, no ecosystem); a declarative gate (xenon grades, ruff rules, import-linter contracts) is self-documenting and fails loudly on upgrade.

## Runtime State Inventory

> Refactor/repackage phase — all five categories answered explicitly. Canonical question: *after every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?*

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None. No databases/datastores in this repo. `.agent/` session snapshots contain `strands_code_cli` only as inert transcript text, and `.agent/` is gitignored + untracked (`git ls-files .agent` empty [VERIFIED]) | None — code edit only; no data migration |
| Live service config | None — verified by survey: no services, UIs, or external configs exist (repo is a local CLI; `.github/` holds only the release `publish.yml` + dependabot) | None |
| OS-registered state | None. `crontab -l` empty [VERIFIED]; no systemd/pm2/launchd unit files in repo. System-wide unit scan not performed (see A6) | None |
| Secrets/env vars | None found. No module-path-derived secret names; AGENTS.md records no `os.environ` reads in the agent package [VERIFIED: AGENTS.md:61]. CLI-side env use not exhaustively grep-audited (see A5) | Planner: one `grep -rn "os.environ\|os.getenv" strands_code_cli/ scripts/` to close A5; expected none |
| Build artifacts | **FOUND (3 items):** (1) `.venv/bin/strands-code` console script hardcodes `from strands_code_cli.main import main` [VERIFIED: file content] — breaks when `main.py` moves; (2) `__pycache__/` dirs in every package (gitignored; orphan `.pyc` after moves is harmless but untidy); (3) `uv.lock` must gain the new dev deps | (1) Update `[project.scripts]` + `uv sync` in the same move step (CF-08); (2) `find . -name __pycache__ -prune -exec rm -rf {} +` hygiene at phase end; (3) `uv add --dev …` regenerates the lock |

## Common Pitfalls

### Pitfall 1: Flipping the gate to blocking on day one
**What goes wrong:** CI/pre-commit wired as blocking before the breakup fails every commit (`run_loop` F(75) alone fails `-b C`).
**Why it happens:** D-02 "persistent gate" reads as "enforced from the start"; CF-03 proves the tree isn't green.
**How to avoid:** Staged flip (measure → report → breakup → blocking). Pre-commit hooks last.
**Warning signs:** First gate run exits 1 — expected; a plan that treats it as executor error is mis-sequenced.

### Pitfall 2: Ruff `exclude` silently bypassed under pre-commit
**What goes wrong:** Upstream files get gated on commit despite pyproject `exclude`, violating D-24.
**Why it happens:** Pre-commit passes explicit filenames; ruff analyzes explicit paths "regardless … unless `force-exclude` is also enabled" [CITED: ruff configuration docs].
**How to avoid:** `force-exclude = true` in `[tool.ruff]` (CF-05) + hook-level `exclude:` regex (Pattern 2).
**Warning signs:** `pre-commit run --all-files` reports violations in `strands_code_agent/` files the fork didn't add.

### Pitfall 3: Xenon `-e` vs `-i` confusion
**What goes wrong:** Trying to skip directories with `-e` (or files with `-i`) silently gates the wrong set.
**Why it happens:** `-e/--exclude` matches *filenames* against glob patterns; `-i/--ignore` matches *directory names* and xenon "won't even descend into them" [CITED: https://github.com/rubik/xenon].
**How to avoid:** Prefer explicit path args (`xenon -b C strands_code_cli tests scripts`) over exclusion flags; use `-i` only for directory pruning.
**Warning signs:** Gate output lists files outside the intended scope.

### Pitfall 4: Relative imports in the rig split
**What goes wrong:** Scenario files using `from .lib import …` crash under the test loader (`spec_from_file_location` top-level module has no package context).
**Why it happens:** Packaging instinct says "same directory = relative import"; the loader says otherwise (CF-07).
**How to avoid:** `sys.path` insert + absolute sibling imports (option (a)), or deliberately re-engineer the loader (option (b)).
**Warning signs:** `ImportError: attempted relative import with no known parent package` in rig contract tests.

### Pitfall 5: Dropping source-text assertions in the test mirror
**What goes wrong:** Split contract tests lose coverage because assertions referenced the old module object or file text.
**Why it happens:** The assertions below bind to `driver` (module object) or `DRIVER` (file path); both change meaning after the split.
**How to avoid:** Re-home every one (inventory from `tests/test_uattest_driver.py` [VERIFIED: full-file read]): `DRIVER.read_text()` contains `"a1"`/`"a2"` (dispatch stays in driver.py); `inspect.getsource` on `scenario_r2/r3/r4`, `_native_strategy`, `scenario_r3`, `scenario_c1/c2`, `scenario_a1/a2` (+`callable(driver.scenario_a1/a2)`); `RIG_NOVA_MICRO`/`CHEAP_OPENROUTER_ID`/`COST_RE`/`ACTUAL_USAGE_RE`/`ACTUAL_ROW_RE`/`SPLIT_RE` attribute presence; `monkeypatch.setattr(driver, "pane_text", …)` in TestFailFast/TestWaitForNewBaseline (patch target becomes the lib module); `inspect.signature(driver.start_cli)` has `cli_args`.
**Warning signs:** Mirrored test files with fewer assertions than the original, or tests passing vacuously.

### Pitfall 6: Stale console script after the entry move
**What goes wrong:** `uv run strands-code` (and every rig scenario) fails with `ModuleNotFoundError` after `main.py` moves.
**Why it happens:** Install-time generated script freezes the import (CF-08).
**How to avoid:** Update `[project.scripts]` + `uv sync` atomically with the move; smoke `uv run strands-code --help` in the same step.
**Warning signs:** Suite green but rig fails to boot the CLI.

### Pitfall 7: README rewrite breaks `test_readme_examples.py`
**What goes wrong:** D-16's "full rewrite" removes or alters the CodeAgent/Toolkit snippets the tests mirror.
**Why it happens:** The test file's contract is "mirror every code example in README.md" [VERIFIED: tests/test_readme_examples.py:1-6]; current snippets (public imports, `CodeAgent(system_prompt=…)`, Toolkit construction, builtin toolkits, `calculate_roi` domain code, combined toolkits) must keep working verbatim.
**How to avoid:** Keep all tested snippets intact, or update tests in lockstep in the same commit. Note the "features table" is the `Library essentials` table (Knowledge row at README.md:76 [VERIFIED]) plus the stale `CLI status` section (says "Phase 7 complete" — phases 8–11 shipped since).
**Warning signs:** `test_readme_examples.py` failures after the README commit.

### Pitfall 8: `ruff-pre-commit` rev skew vs dev ruff
**What goes wrong:** Hook uses a different ruff version than `uv run ruff`, producing fix/format flip-flops between local runs and commits.
**Why it happens:** `rev:` pinned once and forgotten while the dev dep floats (no upper pins policy).
**How to avoid:** Pin `rev: v0.17.1` to match the locked dev version; add a plan note to bump both together.
**Warning signs:** `pre-commit run --all-files` reformats files `uv run ruff format --check` just passed.

### Pitfall 9: Forgetting the two driver string literals + route-probe re-exec
**What goes wrong:** Import rewrite scripts catch `import` statements but miss `"from strands_code_cli.live_pricing import …"` / `"from strands_code_cli.router import …"` string literals in driver.py:295-296 [VERIFIED] and the `import strands_code_cli.routing` re-exec probe in route-probe.py [VERIFIED: scripts/route-probe.py:103] plus its `from strands_code_cli.routing import …` block.
**Why it happens:** AST-based rewriters don't see strings; the re-exec import looks like dead code.
**How to avoid:** Plain-text `grep -rn "strands_code_cli"` sweep as the move-completeness check (D-09 "all in-repo imports move" + D-11 "break loudly" — a missed string breaks at rig runtime, the worst place).
**Warning signs:** `grep` still hits after the "final" move commit.

## Code Examples

Verified patterns from official sources (adapt paths/scopes to the planner's package layout):

### Ruff config in pyproject.toml (D-18/D-20/D-21/D-24)

```toml
# Sources: https://docs.astral.sh/ruff/configuration/ (project configuration layout),
# https://docs.astral.sh/ruff/settings/#force-exclude (force-exclude semantics),
# https://docs.astral.sh/ruff/linter/ (select guidance: start small, e.g. ["E", "F"])
[tool.ruff]
target-version = "py310"          # matches requires-python >=3.10
force-exclude = true              # REQUIRED for D-24 under pre-commit (CF-05)
exclude = [
    "strands_code_agent",          # inherited upstream code; see search_tool.py note below
]
# NOTE: strands_code_agent/search_tool.py is fork-added and SHOULD be gated,
# but ruff exclude has no except-one-file form. Options for the planner:
# (a) list upstream files explicitly instead of the directory (4 known-modified
#     + unknowns — brittle); (b) gate search_tool.py via explicit CI path arg
#     WITHOUT force-exclude applying... no — force-exclude blocks explicit too.
# (c) simplest: exclude the dir for ruff, and rely on the xenon/import-linter
#     CI invocations (explicit paths, no force-exclude concept) to cover
#     search_tool.py. Ruff-cleanliness of that one file is enforced by review.

[tool.ruff.lint]
select = ["E", "F", "I"]          # D-20: pyflakes + pycodestyle errors + isort
ignore = ["E501"]                 # DISCRETION (CF-04): formatter owns line length

[tool.ruff.lint.isort]
known-first-party = ["strands_code_cli", "strands_code_agent"]
```

### Xenon gate invocation (D-01/D-02/D-03)

```bash
# Source: https://github.com/rubik/xenon (threshold semantics), verified flags via --help
uv run --group dev xenon --max-absolute C --max-modules B --max-average A \
  strands_code_cli tests scripts
# -b C fails blocks ranked D/E/F, i.e. complexity > 20 (D-03). --max-modules /
# --max-average grades are planner discretion (D-03 locks only the absolute
# threshold); B/A above are starting suggestions, tighten from the D-04 numbers.
```

### import-linter contracts in pyproject.toml (coupling check, discretion)

```toml
# Source: import-linter 2.15 source (adapters/user_options.py: TomlFileUserOptionReader
# reads [tool.importlinter] with a `contracts` list); contract semantics from
# https://import-linter.readthedocs.io/en/stable/ (forbidden/layers/independence)
[tool.importlinter]
root_package = "strands_code_cli"

[[tool.importlinter.contracts]]
name = "CLI packages stay independent of the agent package direction"
type = "forbidden"
source_modules = ["strands_code_agent.search_tool"]
forbidden_modules = ["strands_code_cli"]
# NOTE: this contract documents the CF-02 violation. Until D-12 is amended and
# the import is resolved, EITHER exclude it or mark the contract broken-by-design
# with `ignore_imports`. Planner decides once package names exist.
```

### Pre-commit config sketch (D-02; xenon/import-linter via local hooks)

```yaml
# Sources: https://github.com/astral-sh/ruff-pre-commit (hook ids, --fix ordering:
# lint hook before format hook when using --fix),
# https://github.com/rubik/xenon (xenon args = or split-list form)
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.1                      # keep == dev ruff version (Pitfall 8)
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: xenon
        name: xenon complexity gate
        entry: uv run --group dev xenon --max-absolute C --max-modules B --max-average A
        language: system
        types: [python]
        exclude: ^strands_code_agent/(?!search_tool\.py).*
        pass_filenames: true
      - id: lint-imports
        name: import-linter contracts
        entry: uv run --group dev lint-imports
        language: system
        types: [python]
        pass_filenames: false         # contracts analyze the whole package graph
```

### CI gate workflow sketch (D-02; new file — only publish.yml exists today)

```yaml
# Source: https://docs.astral.sh/uv/guides/integration/github (setup-uv usage)
name: gates
on: [push, pull_request]
jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8   # pin a full tag at plan time
      - run: uv sync --locked --group dev
      - run: uv run pytest tests/ -q
      - run: uv run ruff check strands_code_cli tests scripts
      - run: uv run ruff format --check strands_code_cli tests scripts
      - run: uv run xenon --max-absolute C strands_code_cli tests scripts
      - run: uv run lint-imports
```

### Rig driver sys.path pattern (CF-07 option (a))

```python
# Keeps spec_from_file_location loading + absolute-import rule intact.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import send, start_cli, stop_cli, save, wait_for  # sibling lib, absolute
from scenarios_routing import scenario_r1, scenario_r2  # per-area modules, absolute
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| flake8 + black + isort (3 tools) | ruff `check` + `format` (1 binary) | ruff 0.1 stable 2024; now 0.17.x | D-18 adopts the consolidated standard; no multi-tool config drift |
| mccabe / flake8-C901 inline complexity | radon measure + xenon gate | Long-standing split; xenon 0.9.x current | D-01/D-20 match this split exactly (measure vs enforce separated) |
| Manual import review / grep audits | import-linter contracts in CI | import-linter 2.x; pyproject-native config verified in 2.15 source | D-01's "coupling check" gets a real gate, not a one-shot eyeball |
| setup.cfg / tox.ini tool config | pyproject.toml `[tool.*]` + uv | uv 0.x era (repo already uv-managed) | D-18's pyproject config is the native home; xenon is the exception (CLI args / `.xenon.yml` — it has no pyproject reader; `-c` defaults to `.xenon.yml` [VERIFIED: --help]) |
| Release-only CI | Gate workflow on push/PR | — | This phase ADDS the repo's first CI gate (only `publish.yml` exists [VERIFIED]) |

**Deprecated/outdated:**
- `layer_linter` package: deprecated in favor of import-linter [CITED: https://github.com/seddonym/layer_linter]. Do not use.
- Xenon `--url` POST reporting: irrelevant here (would violate the hermetic/AWS-optional posture); thresholds via exit codes only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No `.pre-commit-hooks.yaml` manifest exists in `rubik/xenon` (fetch failed; a `main`-vs-`master` branch variant could exist) | CF-06 | Low — `repo: local` hooks work regardless; worst case a redundant local hook where a remote one would do |
| A2 | Wheels execute no install-time code under pip/uv (no postinstall concept) | Legitimacy Audit | Low — mitigated by `uv.lock` + `--locked` CI; sdists would be the exception |
| A3 | `git merge upstream/main` after D-15 deletion stays clean unless upstream touches the deleted paths (then delete/modify conflict) | CF-01 | Medium — shapes the CF-01 user decision; executor can dry-run with a scratch merge |
| A4 | Ruff infers `target-version` from `requires-python` when unset (explicit `py310` set anyway) | Code Examples | None — explicit setting makes the inference moot |
| A5 | No `os.environ`/`os.getenv` reads in `strands_code_cli/` or `scripts/` derive secret names from module paths | Runtime Inventory | Low — one grep closes it (planner task) |
| A6 | No systemd/pm2/launchd registrations reference repo paths (crontab verified empty; unit dirs not scanned) | Runtime Inventory | Low — module renames wouldn't affect service registrations anyway absent path coupling |
| A7 | pre-commit installs via `uv tool install pre-commit` on this machine (tool not currently installed) | Standard Stack | Low — fallback is `pipx` or the `pre-commit` PyPI package in any venv |
| A8 | Full-suite runtime unknown (1553 passed per CONTEXT; not timed this session) | Validation | Low — planner time-boxes; suite is the mandated guardrail regardless |
| A9 | pre-commit canonical repo is `github.com/pre-commit/pre-commit` (not re-verified) | Legitimacy Audit | Negligible — hook `repo:` URL is planner-verified at write time |

## Open Questions

1. **D-15 re-confirmation (CF-01) — BLOCKING user question**
   - What we know: removal targets are byte-identical to `upstream/main`; deletion removes upstream code with delete/modify merge risk.
   - What's unclear: whether the user still wants both deleted given the failed precondition.
   - Recommendation: planner asks before writing any removal plan; offer (a) delete both anyway, (b) README-only + leave code, (c) delete example only.
2. **D-12 amendment for `search_tool.py:18` (CF-02)**
   - What we know: exactly one fork-added agent file needs an import-line update for D-09.
   - What's unclear: whether to amend D-12 (allow) or redesign `confine()` ownership.
   - Recommendation: amend D-12 with a one-file carve-out; cheapest merge-safe path.
3. **E501: `ignore` vs fix-all (CF-04)**
   - What we know: E501 fires under F+E+I; formatter cannot split long strings/comments.
   - What's unclear: planner/executor taste within D-20/D-22.
   - Recommendation: `ignore = ["E501"]` (formatter owns line length); document in pyproject comment.
4. **D-04 report location and format (discretion)**
   - What we know: must be committed and cited by the breakup.
   - What's unclear: `docs/STRUCTURE-REPORT.md` vs phase dir vs `STRUCTURE.md` at root.
   - Recommendation: `docs/STRUCTURE.md` (durable, discoverable, beside QUICKSTART/ROUTING); radon tables + xenon thresholds + import-linter contracts + breakup rationale citing numbers.
5. **Xenon `--max-modules` / `--max-average` grades (D-03 locks only absolute)**
   - What we know: `-b C` is locked; module/average thresholds are free.
   - What's unclear: current module/average numbers (measure step produces them).
   - Recommendation: set from the D-04 measurement (suggested start: modules B, average A); tighten, never loosen.
6. **AGENTS.md + `codebase/*.md` refresh scope**
   - What we know: conventions paragraph superseded by D-18; architecture docs describe removed `knowledge/`.
   - What's unclear: whether the planner folds the refresh into Phase 12 or leaves it.
   - Recommendation: fold in as a trailing task — stale agent instructions rot the next session.
7. **`docs/competitive-gap-analysis.md` OKF prose (D-16 covers README only)**
   - What we know: doc mentions the OKF module in prose (lines 38, 168, 190, 196–197).
   - What's unclear: whether D-15's spirit covers prose docs.
   - Recommendation: leave unless the user says otherwise (D-16 is README-scoped); note in the plan.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.14.8 (`python3 --version`) | — |
| uv | Gate runs, dep adds | ✓ | 0.12.23 | — |
| git | Moves, history | ✓ | 2.55.0 | — |
| pytest | Suite guardrail | ✓ | 9.1.1 (locked, dev group) | — |
| tmux | Rig scenarios | ✓ | 3.7c | — |
| radon | Measurement | ✗ (add as dev dep) | 6.0.1 on PyPI | — (install step, not blocking) |
| xenon | Complexity gate | ✗ (add as dev dep) | 0.9.3 on PyPI | — (install step) |
| ruff | Lint+format gate | ✗ (add as dev dep) | 0.17.1 on PyPI | — (install step) |
| import-linter | Coupling gate | ✗ (add as dev dep) | 2.15 on PyPI | stdlib one-shot graph for the report only (gate would be uncovered — planner must still add the dep) |
| pre-commit | Local hooks | ✗ (env install) | 4.7.0 on PyPI | CI-only gating if the user declines the framework (D-02 names pre-commit, so prefer installing) |
| graphviz | pydeps figures (optional) | ✗ (unchecked) | — | Skip figures; tables suffice |

**Missing dependencies with no fallback:** none — all missing items are install steps the phase itself performs.
**Missing dependencies with fallback:** graphviz (figures optional).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked; declared `pytest>=8`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (markers: `integration`; `addopts = "-m 'not integration'"`) — no `pytest.ini`/`conftest.py` at root; suite conftest is `tests/conftest.py` (hermetic pricing guard) |
| Quick run command | `uv run pytest tests/ -q` (moves are global — no safe subset; quick == full) |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRUCT-01 | Suite green throughout/after moves | unit/integration (existing 45 files) | `uv run pytest tests/ -q` | ✅ |
| STRUCT-01 | No block worse than C (complexity > 20) | gate (exit code) | `uv run xenon --max-absolute C strands_code_cli tests scripts` → exit 0 | ❌ Wave 0 (new gate) |
| STRUCT-01 | Ruff-clean + formatted (fork paths) | gate (exit code) | `uv run ruff check …` + `uv run ruff format --check …` → exit 0 | ❌ Wave 0 (new gate) |
| STRUCT-01 | Coupling contracts kept | gate (exit code) | `uv run lint-imports` → exit 0 | ❌ Wave 0 (new gate) |
| STRUCT-01 | Rig boots + contract tests mirror | contract tests (split to mirror) + live spot runs | `uv run pytest tests/test_uattest* -q` + `driver.py <id>` spot runs | ✅ loader exists; split is the work |
| CLEANUP-01 | Removal targets absent | shell assertion | `test ! -e examples/pdf_to_okf_bundle && test ! -e strands_code_agent/knowledge` | ❌ Wave 0 (new CI step) |
| CLEANUP-01 | No dangling knowledge imports | shell assertion | `grep -rn "knowledge\|OKFBundle\|pdf_to_okf" --include="*.py" strands_code_cli tests scripts` → empty | ❌ Wave 0 (new CI step) |
| CLEANUP-01 | README ships-only + examples work | existing tests | `uv run pytest tests/test_readme_examples.py -q` | ✅ |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -q`
- **Per wave merge:** full suite + all four gates (xenon, ruff check, ruff format --check, lint-imports)
- **Phase gate:** full suite green + all gates exit 0 + one live rig scenario per split area (or documented rig-runner evidence per existing UAT precedent) before `$gsd-verify-work`

### Wave 0 Gaps

- New dev deps + lock: `uv add --dev radon xenon ruff import-linter`
- New gate configs: `[tool.ruff]`, `[tool.importlinter]` in `pyproject.toml`
- New CI workflow file (name at planner discretion; only `publish.yml` exists today)
- New `.pre-commit-config.yaml` + `pre-commit install` (per-clone step; CI does not need the framework)
- D-04 committed report (location/format at planner discretion; `docs/STRUCTURE.md` suggested)

*(No pytest infrastructure gaps — existing suite covers all phase requirements' testable surface.)*

## Security Domain

> `security_enforcement: true`, ASVS L1. This phase makes no behavior changes and adds dev-only, gate-time tooling. No auth/session/crypto/data-handling surface changes.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | No | — |
| V6 Cryptography | No | — |
| V7 Error Handling/Logging | No | Gate output is local/CI logs; no secrets involved |
| V8 Data Protection | No | — |
| V9 Communications | No | Gates run offline (no xenon `--url`, no networked hooks) |
| V10 Malicious Code | Partial | New dev deps from PyPI — see controls below |
| V11 Business Logic | No | — |
| V12 Files/Resources | No | — |
| V13 API/Web Service | No | — |
| V14 Configuration/Build | **Yes** | Pinned hook revs, locked deps, `--locked` CI sync |

### V10/V14 Controls (supply-chain review per D-01)

- Exact dependency names verified on the correct registry (PyPI, not npm): radon, xenon, ruff, import-linter, pre-commit [VERIFIED: `pip index versions` this session] — mitigates typosquat/dependency-confusion at introduction time.
- `uv.lock` records the resolved tree; CI syncs with `--locked` so a floating re-resolution can never silently swap artifacts.
- Pre-commit `rev:` pins: `ruff-pre-commit` tag pinned to the dev ruff version (Pitfall 8); xenon/import-linter run as `repo: local` (no third-party hook repos added at all).
- No secrets in gate configs; no new workflow permissions beyond default `contents: read`.

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Typosquatted dev dep (e.g. `radonn`) | Tampering | Exact-name verification + lockfile; review `uv add` diffs |
| Compromised hook repo serving malicious hooks | Tampering | Only official `ruff-pre-commit` pinned by tag; everything else `repo: local` |
| Gate bypass (`--no-verify`, direct push) | Elevation of privilege | CI workflow is the blocking authority, not local hooks; branch protection out of scope for this repo's `none` branching strategy (noted, not tasked) |

## Sources

### Primary (HIGH confidence — tool-verified this session + authoritative source)

- PyPI registry via `pip index versions`: radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15, pydeps 3.0.9, pre-commit 4.7.0
- Wheel METADATA inspection: xenon `radon<7,>=4`; import-linter `Requires-Python: >=3.10`; radon/xenon Home-page/Project-URL → rubik repos
- radon 6.0.1 source (`radon/tests/test_complexity_utils.py:20-31`): A 0–5 / B 6–10 / C 11–20 / D 21–30 / E 31–40 / F 41+
- import-linter 2.15 source (`importlinter/adapters/user_options.py:48,86`): reads `setup.cfg`, `.importlinter`, and `pyproject.toml [tool.importlinter]` with `contracts` list
- Trial executions on Python 3.14.8: `radon cc` (F(75)/F(46)/D(25) in loop.py), `xenon -b C` exit 1 / exit 0, `ruff check` E501 probe + exit 1, `ruff format --check` exit 1
- [Official docs] https://docs.astral.sh/ruff/configuration/ + https://docs.astral.sh/ruff/settings/#force-exclude (force-exclude semantics)
- [Official docs] https://docs.astral.sh/ruff/rules/line-too-long/ + https://docs.astral.sh/ruff/linter/ (E501, select guidance, noqa)
- [Official docs] https://github.com/rubik/xenon (inclusive thresholds, `-e` vs `-i`, pre-commit args form)
- [Official docs] https://import-linter.readthedocs.io/en/stable/ (contract types)
- [Official docs] https://github.com/astral-sh/ruff-pre-commit (hook ids, --fix ordering)
- [Official docs] https://docs.astral.sh/uv/guides/integration/github + https://github.com/astral-sh/setup-uv (CI pattern)
- In-repo files read this session: `pyproject.toml`, `README.md`, `AGENTS.md`, `tests/test_uattest_driver.py`, `tests/test_readme_examples.py`, `tests/conftest.py`, `scripts/uattest/driver.py` (structure), `scripts/route-probe.py` (re-exec), `.github/workflows/publish.yml`, `.gitignore`, `strands_code_cli/__init__.py`, `strands_code_agent/knowledge/__init__.py`, `.planning/config.json`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `12-CONTEXT.md`
- git evidence: `git branch -r --contains b1de584`, empty `upstream/main..HEAD` diff on removal targets, `git diff --diff-filter=A/M` fork-added derivation, `git mv`/`git diff` man texts (git 2.55.0)

### Secondary (MEDIUM confidence — corroboration, not sole basis)

- xenon README "tested with Python 2.7 and 3.6 to 3.12" (superseded by the 3.14.8 trial run here)
- Community guides on ruff+pre-commit wiring and import-linter CI usage (consistent with official docs above)

### Tertiary (LOW confidence / explicitly assumed)

- Items A1–A9 in the Assumptions Log; the manual (non-seam) legitimacy audit

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — versions from the registry, behavior from trial runs and official docs
- Architecture: HIGH — sequencing derived from locked decisions; move/split patterns verified against repo mechanics (loader, console script, git behavior)
- Pitfalls: HIGH — each grounded in a verified repo fact or cited doc behavior
- Legitimacy audit: MEDIUM — manual method (seam unavailable); planner should re-run the seam at plan time
- D-15 merge consequences: MEDIUM — precondition failure is HIGH (verified git evidence); downstream merge mechanics are [ASSUMED] standard git behavior

**Research date:** 2026-10-16
**Valid until:** 2026-11-15 (stable domain; ruff releases fast — re-verify the pinned version at plan time and keep hook `rev:` in lockstep)
