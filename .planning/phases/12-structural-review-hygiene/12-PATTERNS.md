# Phase 12: Structural Review + Hygiene - Pattern Map

**Mapped:** 2026-10-16
**Files analyzed:** 16 (8 new, 6 modified, 2 deletion targets)
**Analogs found:** 15 / 16

> Dispatch note: produced via generic-agent workaround (typed `gsd-pattern-mapper`
> dispatch unavailable). Role contract (`gsd-pattern-mapper.md`) followed:
> read-only codebase analysis; this file is the only write. Every analog path
> below was verified git-tracked via `git ls-files` this session.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.pre-commit-config.yaml` (new) | config | event-driven | `.github/dependabot.yml` + RESEARCH.md sketch | partial |
| `.github/workflows/gates.yml` (new, name at planner discretion) | config | batch | `.github/workflows/publish.yml` | exact |
| `docs/STRUCTURE.md` (new, D-04 report; location at planner discretion) | doc | batch | `docs/ROUTING.md` | exact |
| `strands_code_cli/<feature>/__init__.py` (new package roots) | config | request-response | `strands_code_cli/__init__.py` | exact |
| Repackaged CLI modules, e.g. `loop/core.py` (moves) | service | request-response | `strands_code_cli/scope.py` | role-match |
| `scripts/uattest/<lib>.py` (new shared lib, D-13) | utility | file-I/O | `scripts/uattest/driver.py` (lines 21-157) | exact |
| `scripts/uattest/scenarios_<area>.py` x5 (new, D-14) | service | event-driven | `scripts/uattest/driver.py` (scenario fns) | exact |
| `tests/test_uattest_<area>.py` (new splits, D-14) | test | batch | `tests/test_uattest_driver.py` | exact |
| `pyproject.toml` (modify: dev deps, `[tool.ruff]`, `[tool.importlinter]`, entry) | config | batch | `pyproject.toml` itself | exact |
| `tests/` mirror moves, 45 files (D-07) | test | batch | `tests/test_cli_entry.py` | role-match |
| `scripts/uattest/driver.py` (modify: thin dispatch, D-14) | service | event-driven | itself (`__main__` chain) | exact |
| `README.md` (modify: features table rewrite, D-16) | doc | batch | itself (lines 69-101) | exact |
| `AGENTS.md` + `.planning/codebase/CONVENTIONS.md` (modify: refresh) | doc | batch | themselves | exact |
| `strands_code_agent/search_tool.py:18` (modify: one import line) | service | batch | `scripts/route-probe.py` (import pattern) | role-match |
| `scripts/route-probe.py` (modify: import rewrites) | utility | batch | itself (lines 95-130) | exact |
| `examples/pdf_to_okf_bundle/` + `strands_code_agent/knowledge/` (delete, D-15) | — | — | (no analog; `git rm`) | n/a |

## Pattern Assignments

### `.pre-commit-config.yaml` (new) (config, event-driven)

**Analog:** `.github/dependabot.yml` (partial — repo's only committed YAML automation
config; no pre-commit config exists in-repo, so hook structure comes from the
RESEARCH.md "Pre-commit config sketch").

**YAML header-comment pattern** (`.github/dependabot.yml`, lines 1-3):

```yaml
# Dependabot watches PyPI for our deps (notably strands-agents / strands-harness
# from the strands-agents/harness-sdk monorepo) and opens review-gated bump PRs.
# Docs: https://docs.github.com/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
```

Copy: a 2-3 line `#` comment block at the top explaining what the file gates,
plus a `Docs:` URL line. New file should carry an equivalent header naming the
D-02 persistent gate and the ruff / xenon / import-linter docs URLs.

**Hook content pattern:** no in-repo analog — use RESEARCH.md "Pre-commit config
sketch" verbatim as the base: `astral-sh/ruff-pre-commit` rev pinned to the dev
ruff version with `ruff` (`--fix`) before `ruff-format`, plus `repo: local`
hooks for xenon (`exclude: ^strands_code_agent/(?!search_tool\.py).*`,
`pass_filenames: true`) and `lint-imports` (`pass_filenames: false`).

---

### `.github/workflows/gates.yml` (new) (config, batch)

**Analog:** `.github/workflows/publish.yml` (exact — repo's only workflow file).

**Workflow skeleton** (lines 1-13):

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
```

Copy: `name:` first, `on:` trigger block, `jobs:` with `runs-on: ubuntu-latest`,
`actions/checkout@v4` as step one. Diverge per RESEARCH.md: trigger on
`[push, pull_request]`, minimal `permissions` (default `contents: read` only —
no `id-token: write`; that is publish-specific), `astral-sh/setup-uv` instead
of `setup-python` (uv-only constraint), then `uv sync --locked --group dev`
followed by the five gate steps (pytest, ruff check, ruff format --check,
xenon, lint-imports). Keep the same terse one-`run`-per-step style.

---

### `docs/STRUCTURE.md` (new, D-04 report) (doc, batch)

**Analog:** `docs/ROUTING.md` (exact — feature doc in the same directory).

**Doc open pattern** (`docs/ROUTING.md`, lines 1-5):

```markdown
# Model Routing

Per-ask model and thinking-budget routing via a cheap decision model (MODEL-03).
Routing is off until a strategy is configured — without one the CLI behaves
exactly as before.
```

Copy: `# Title` + 2-3 sentence scope paragraph naming the requirement id
(here STRUCT-01) and the steady-state claim. Then `##` sections — ROUTING.md
uses `## Concepts` (definition list), `## Quick start` (numbered steps),
`## Native engine` (deep dives). The D-04 report maps to: `## Method`
(radon/xenon invocations + thresholds), `## Numbers` (per-module tables),
`## Contracts` (import-linter), `## Breakup rationale` (citing the numbers).

**Pin caution:** `tests/test_uattest_driver.py:55-63` asserts on ROUTING.md
content (`test_docs_example_uses_profile_form`). The new report must not move
or alter the `PROFILE_FORM` string in ROUTING.md — add a new file, do not edit
ROUTING.md to "make room".

---

### `strands_code_cli/<feature>/__init__.py` (new) (config, request-response)

**Analog:** `strands_code_cli/__init__.py` (exact — package root the repackage
grows from).

**Full file** (lines 1-5):

```python
"""strands-code conversational CLI (Phase 1 tracer slice)."""

from strands_code_cli.main import main

__all__ = ["main"]
```

Copy: one-line module docstring, absolute import(s) rooted at the package,
`__all__` listing exactly the re-exports. Keep feature-package re-exports
minimal (today's root re-exports only `main`) — no convenience re-export of
every submodule (that would double the import graph the coupling gate reasons
about, and D-09 forbids re-export shims for old paths).

**Re-export-with-noqa variant** (`strands_code_agent/__init__.py`, lines 1-7):

```python
from . import solution_user_agent  # noqa: F401 - registers the AWS Solutions user-agent ID

from strands_code_agent.code_agent import CodeAgent
from strands_code_agent.toolkits import Toolkit
from strands_code_agent.python_environments.agentcore import AgentCorePythonInterpreter

__all__ = ["CodeAgent", "Toolkit", "AgentCorePythonInterpreter"]
```

Copy only if a feature `__init__.py` needs a side-effect import: the
`# noqa: F401 - <reason>` form with a reason is the D-22-compatible waiver
precedent (per-line with reason, no file-level ignores).

---

### Repackaged CLI modules, e.g. `loop/core.py` (moves) (service, request-response)

**Analog:** `strands_code_cli/scope.py` (role-match — small, clean CLI module
showing every applicable convention; the moved modules keep their own bodies,
so this pattern governs import blocks and new-module shape only).

**Module open pattern** (`strands_code_cli/scope.py`, lines 1-19):

```python
"""Default filesystem scope for file tools: cwd + subdirs + /tmp (D-07).

The harness builtins (``read``/``write``/``edit``) only require absolute
...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable
```

Copy: triple-double-quoted module docstring (first line imperative summary,
decision refs like `(D-07)` inline), blank line, `from __future__ import
annotations`, blank line, stdlib imports one-per-line. Third-party then
first-party absolute imports follow in separate groups — see
`strands_code_cli/main.py` lines 10-44 (typer/strands group, then
`strands_code_agent.*`, then `strands_code_cli.*`, each alphabetical).

**Function pattern** (`strands_code_cli/scope.py`, lines 36-56):

```python
def confine(path: str | Path, cwd: str | Path, extra_roots: Iterable[str | Path] = ()) -> Path:
    """Admit ``cwd`` + subdirs, ``/tmp`` + subdirs, plus policy-granted roots.
    ...
    Raises:
        ValueError: Naming the allowed roots when the path is out of scope.
    """
```

Copy: `snake_case` names, `X | Y` union annotations (py310 style), docstring
with `Args:`/`Returns:`/`Raises:` in plain text, `UPPER_SNAKE_CASE` module
constants, leading-underscore privates (`_rule_base_dir`). Ruff F+E+I does not
check docstrings — moves must carry them verbatim.

**Move mechanics:** pure `git mv` commits, no edits mixed in (RESEARCH.md
Pattern 1). Completeness check is plain-text `grep -rn "strands_code_cli"`,
not AST-only (catches the driver string literals and route-probe re-exec).

---

### `scripts/uattest/<lib>.py` (new shared lib, D-13) (utility, file-I/O)

**Analog:** `scripts/uattest/driver.py`, lines 21-157 (exact — the extraction
source; the lib IS these lines moved).

**Import + constants block** (lines 21-46):

```python
import os
import re
import subprocess
import sys
import time

LOGDIR = "/tmp/uatr4"
LOGDIR8 = "/tmp/uatr8"
CLI = "/home/csaba/.local/bin/uv run --project /home/csaba/repos/AWS/strands-code strands-code"
WORKDIR = "/tmp/uattest"
WORKDIR8 = "/tmp/uatr8"
COST_RE = re.compile(r"\((?:\d+%|n/a)\) \$", re.MULTILINE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RIG_NOVA_MICRO = "bedrock/us.amazon.nova-micro-v1:0"
FAIL_RE = re.compile(r"Turn failed[^\n]*")
```

**Plumbing functions** (lines 48-157): `tmux`, `pane_text`, `wait_for`,
`wait_for_new` (with baseline-count docstring), `send`, `start_cli`
(`cli_args` kwarg — contract test asserts its signature),
`stop_cli`, `save`, `wait_main_end` (fail-fast + mid-turn dialog assist).

**Critical loader constraint** (CF-07): the contract tests load the driver via
`importlib.util.spec_from_file_location("uattest_driver", DRIVER)` as a
top-level module. Relative imports (`from .lib import …`) BREAK under this
loader. The lib and scenario files must use the RESEARCH.md CF-07 option (a)
pattern: `sys.path` insert of the `scripts/uattest/` dir + absolute sibling
imports. Note this is a deliberate, documented exception to the AGENTS.md
"no sys.path manipulation" rule (the rule was written for library code; the
rig scripts have no package path).

**Module docstring for the new lib:** follow the driver.py docstring shape
(lines 1-20): `#!/usr/bin/env python3` shebang, one-line purpose, usage/shape
paragraph, then the "Key insight" operational note. The lib's docstring must
state which functions it owns (tmux/send/wait/save) so the D-13 boundary is
auditable.

---

### `scripts/uattest/scenarios_<area>.py` x5 (new, D-14) (service, event-driven)

**Analog:** `scripts/uattest/driver.py` scenario functions (exact — moved
bodies): `scenario_s1` (lines 159-194, side area with retry loop),
`scenario_c1` (lines 899-925, cost area, canonical shape).

**Canonical scenario shape** (`scenario_c1`, lines 899-925):

```python
def scenario_c1():
    """C1: an OpenRouter main turn shows the marked actual (UAT test 3).

    Switch to the pinned cheap id, run one minimal turn, and assert
    the usage line plus the /cost row carry the ``actual`` marker.
    Pure-actual session: plain total, no split line (D-11).
    """
    _require_openrouter_key()
    workdir = ensure_workdir("w9")
    sess = "uatr8c1"
    start_cli(sess, workdir)
    try:
        _switch_model(sess, CHEAP_OPENROUTER_ID)
        after = len(COST_RE.findall(pane_text(sess)))
        send(sess, "Reply with the single word: ok. ...", "Enter")
        text, _ = wait_main_end(sess, after=after)
        assert ACTUAL_USAGE_RE.search(text), (
            f"usage line lacks the actual marker: {text[-300:]}"
        )
        ...
        print("C1 PASS", flush=True)
    finally:
        save(sess, "c1", LOGDIR8)
        stop_cli(sess)
```

Copy per scenario file: area helpers + regexes move with their scenarios
(routing: `ensure_workdir`/`write_strategy`/`strategy_*`/`wait_routed` lines
232-350; native: `_setup_*`/`_native_strategy` lines 647-668/775-791; cost:
`CHEAP_OPENROUTER_ID`/`ACTUAL_*_RE`/`SPLIT_RE`/`_require_openrouter_key`/
`_switch_model` lines 872-897). Each scenario keeps: docstring with `<ID>:`
prefix + UAT-test ref, `sess = "uatr8<id>"` naming, `try/finally` with
`save` + `stop_cli`, `<ID> PASS` print with `flush=True`.

**Command surface:** `driver.py {s1|…|a2}` stays identical (D-14) — the thin
driver imports scenario functions from the new files; the `__main__` chain
shape (lines 1035-1069, `which = sys.argv[1] … elif … else: sys.exit("usage:
…")`) is preserved, only the function homes change.

---

### `tests/test_uattest_<area>.py` (new splits, D-14) (test, batch)

**Analog:** `tests/test_uattest_driver.py` (exact — the file being split).

**Loader pattern** (lines 12-32) — every split file copies this, pointed at
its new module home:

```python
import importlib.util
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("uattest_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = _load_driver()
```

**Assertion re-homing inventory** (must ALL be re-homed, none dropped —
Pitfall P5): `DRIVER.read_text()` contains `"a1"`/`"a2"` (stays in the
thin-driver test — dispatch table stays in driver.py); `inspect.getsource`
on `scenario_r2/r3/r4`, `_native_strategy`, `scenario_r3`, `scenario_c1/c2`
(+ `callable(driver.scenario_a1/a2)`); `RIG_NOVA_MICRO` /
`CHEAP_OPENROUTER_ID` / `COST_RE` / `ACTUAL_USAGE_RE` / `ACTUAL_ROW_RE` /
`SPLIT_RE` attribute presence (follow the constant to its new home);
`monkeypatch.setattr(driver, "pane_text", …)` becomes the lib module;
`inspect.signature(driver.start_cli)` has `cli_args`.

**Test class style** (lines 35-63): `TestRigModelId`-style PascalCase classes
grouping one behavior area, `test_<behavior>` methods, module constants for
shared fixtures (`PROFILE_FORM`, `BARE_FORM`, `FAILED_TURN`, `CLEAN_*`).

---

### `pyproject.toml` (modify) (config, batch)

**Analog:** itself (exact — new `[tool.*]` blocks follow the existing block).

**Config-block pattern** (lines 63-67):

```toml
[tool.pytest.ini_options]
markers = [
    "integration: live integration tests requiring AWS credentials (deselected by default)",
]
addopts = "-m 'not integration'"
```

Copy: `[tool.<name>]` table headers, list values one-per-line with trailing
comma, inline `#` comments for rationale. New blocks: `[tool.ruff]` (+
`[tool.ruff.lint]`, `[tool.ruff.lint.isort]`) and `[tool.importlinter]` (+
`[[tool.importlinter.contracts]]`) per the RESEARCH.md code examples, including
the `force-exclude = true` + `search_tool.py` caveat comment and the CF-02
contract note.

**Dev-dep pattern** (lines 46-56):

```toml
[dependency-groups]
# Test-only runtime needs: toolkit wiring tests execute real numpy/pandas
# plotting code, so a bare install shows 4 failures without these.
dev = [
    "pytest>=8",
    ...
]
```

Copy: comment above the group explaining a non-obvious membership, lower-bound
pins only (`radon`, `xenon`, `ruff`, `import-linter` with no upper bounds per
AGENTS.md). Added via `uv add --dev` so `uv.lock` regenerates.

**Entry pattern** (lines 43-44, CF-08):

```toml
[project.scripts]
strands-code = "strands_code_cli.main:main"
```

When `main.py` moves (D-10), this line moves atomically in the same commit +
`uv sync` regenerates `.venv/bin/strands-code`; smoke with
`uv run strands-code --help`.

---

### `tests/` mirror moves, 45 files (D-07) (test, batch)

**Analog:** `tests/test_cli_entry.py` (role-match — representative CLI test
showing the file conventions the mirror must preserve).

**Test file pattern** (lines 1-30):

```python
"""Entry UX: slash dispatch, resume picker, session routing (D-02/D-03/D-04)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from strands_code_cli.router import USAGE_HINT, dispatch, show_picker


def _fresh_index(tmp_path):
    from strands_code_cli.session_index import SessionIndex

    return SessionIndex(tmp_path / "index")
...
# ---------------------------------------------------------------------------
# Slash dispatch
# ---------------------------------------------------------------------------


class TestSlashDispatch:
    def test_plain_text_is_agent_turn(self, tmp_path):
```

Copy/preserve through the move: module docstring, `__future__` first, stdlib /
third-party / first-party import groups, leading-underscore helpers,
`# ---…---` section banners, one PascalCase class per behavior area. Only the
`strands_code_cli.*` import paths change (D-09 clean break); nothing else in
the file body is touched in the move commit.

**Stays at root:** `tests/conftest.py` (suite-wide `_no_live_pricing`
autouse fixture, lines 8-17) and the empty `tests/__init__.py` (package
marker) do not move — new test subpackages get their own `__init__.py`
matching the existing empty-file marker. Verified: no test-to-test imports
exist, so mirroring is mechanical.

---

### `scripts/uattest/driver.py` (modify: thin dispatch) (service, event-driven)

**Analog:** itself, `__main__` chain (exact).

**Dispatch pattern** (lines 1035-1069):

```python
if __name__ == "__main__":
    os.makedirs(LOGDIR, exist_ok=True)
    os.makedirs(LOGDIR8, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "s1":
        scenario_s1()
    elif which == "s2":
        scenario_s2()
    ...
    elif which == "a2":
        scenario_a2()
    else:
        sys.exit("usage: driver.py {s1|s2|r1|r2|r3|r4|n1|n2|n3|n4|c1|c2|a1|a2}")
```

Keep: the `if/elif` chain shape (not a dict dispatch — the contract test
asserts `"a1"`/`"a2"` appear in `DRIVER.read_text()`, which the elif literals
satisfy), the usage string listing every scenario id, the `os.makedirs` boot.
The thinned driver keeps the module docstring usage block (lines 1-20),
constants the dispatch needs (`LOGDIR`, `LOGDIR8`), the `sys.path` insert,
scenario imports, and this chain — everything else moves to the lib/scenario
files.

---

### `README.md` (modify: D-16 rewrite) (doc, batch)

**Analog:** itself, lines 69-101 (exact — the two sections under rewrite).

**Features-table pattern** (lines 69-77):

```markdown
## Library essentials

| Piece | What it is |
|---|---|
| `CodeAgent` | `strands.Agent` subclass; auto-registers `python_repl`, ... |
| `Toolkit` | Domain bundle: ... Ships `VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT`. |
| Interpreters | `SandboxedPythonInterpreter` (default, allowlisted), ... |
| Knowledge (OKF) | `strands_code_agent.knowledge`: convert PDFs to OKF concept bundles, ... |
| Callback | `CodeAgentCallbackHandler`: Rich terminal rendering ... |
```

The D-16 rewrite drops the `Knowledge (OKF)` row and rewrites the table for
the post-cleanup tree — same two-column `| Piece | What it is |` shape,
backticked symbol names, one row per shipped surface.

**Status-section pattern** (lines 89-101): `## CLI status` — currently stale
("Phase 7 complete" while phases 8-11 shipped). Rewrite both the staleness
and the "Coming next" tail (decision-model routing and CodeAct already
shipped) in the same pass.

**Hard constraint** (Pitfall P7): `tests/test_readme_examples.py` mirrors
every README code example — keep all tested snippets (`CodeAgent(system_prompt
=…)`, Toolkit construction, builtin toolkits, `calculate_roi` domain code)
working verbatim, or update tests in lockstep in the same commit.

---

### `AGENTS.md` + `.planning/codebase/CONVENTIONS.md` (modify: refresh) (doc, batch)

**Analog:** themselves (exact — surgical paragraph updates, not rewrites).

Two known-stale spots from RESEARCH.md: (1) the "No formatter or linter is
configured … Match the surrounding file's existing style by hand" paragraph
(`AGENTS.md:98`, sourced from `CONVENTIONS.md`) is SUPERSEDED by D-18 —
replace with the ruff invocation + config location; (2) the `knowledge/`
subsystem architecture section (`AGENTS.md:161-164,188-190`) describes the
D-15-removed module — delete. Edit `CONVENTIONS.md` (the GSD source) and the
corresponding `AGENTS.md` section together; both files use the same
`<!-- GSD:<section>-start source:... -->` markers, so keep marker lines
intact.

---

### `strands_code_agent/search_tool.py:18` (modify) (service, batch)

**Analog:** `scripts/route-probe.py` import pattern (role-match — post-move
absolute import referencing a new package path).

**Re-exec + E402 import pattern** (`scripts/route-probe.py`, lines 95-130):

```python
    try:
        import strands_code_cli.routing  # noqa: F401
    except ModuleNotFoundError:
        ...
        os.execvpe("uv", argv, env)


_ensure_production_imports()

from strands_code_cli.routing import (  # noqa: E402
    RoutingCandidate,
    ...
```

For `search_tool.py:18` (`from strands_code_cli.scope import confine`) the
takeaway is narrower: after the repackage it becomes
`from strands_code_cli.<feature>.scope import confine` (exact path at planner
discretion) — a plain absolute import update, no `noqa` needed (no E402
situation in library code). This is the single D-12 exception (CF-02: the
only fork-added file under `strands_code_agent/`); the planner must record
the one-line carve-out explicitly.

---

### `scripts/route-probe.py` (modify: import rewrites) (utility, batch)

**Analog:** itself, lines 95-130 (exact — shown above).

Both the re-exec probe (`import strands_code_cli.routing`, line ~103) and the
`from strands_code_cli.routing import (…)` block (line ~124+) move to the new
routing path in the same commit as the module move; the `# noqa: F401` /
`# noqa: E402` markers stay. Plus the two driver string literals
(`driver.py:295-296`, `"from strands_code_cli.live_pricing import …"`) — plain
text, invisible to AST rewriters; the move-completeness check is
`grep -rn "strands_code_cli"`.

---

### Deletion targets (D-15): `examples/pdf_to_okf_bundle/` + `strands_code_agent/knowledge/`

No code analog — `git rm -r` both paths (CF-01 resolved: user ruled
delete-anyway 2026-10-16 knowing both are byte-identical to `upstream/main`).
Implied co-deletion the planner must task: `tests/test_okf_bundle.py` ONLY
(the sole importer of the removed package — verify first).
`tests/test_search.py` is NOT a co-deletion (zero knowledge references; the
13-test TOOL-04 contract suite for the kept `search_tool` module). Also task:
the `examples/pdf_to_okf_bundle` README/docs refs, and the README Knowledge
row (covered under the README rewrite above). Post-delete completeness check
(anchored — the bare `knowledge` alternative false-positives on ordinary
English like "acknowledges" and "general knowledge only"):
`grep -rn "strands_code_agent\.knowledge\|strands_code_agent/knowledge\|OKFBundle\|pdf_to_okf" --include="*.py" strands_code_cli tests scripts`
returns empty (CLEANUP-01 gate).

## Shared Patterns

### Absolute imports rooted at the package

**Source:** `strands_code_cli/main.py:17-44`, `strands_code_cli/scope.py:17-19`
**Apply to:** Every repackaged CLI module, mirrored test, and the rig split.

```python
from strands_code_agent.code_agent import (
    CODE_AGENT_INSTRUCTIONS,
    DEFAULT_CODE_AGENT_CALLBACK_HANDLER,
)
from strands_code_cli.btw import LockedHandler
```

No relative imports anywhere in the new tree. Multi-name imports use the
parenthesized one-per-line form, alphabetical, grouped stdlib / third-party /
first-party with blank lines between groups. The rig split's `sys.path`
insert is the sole documented exception (CF-07 option (a)).

### Triple-double-quoted docstrings with decision refs

**Source:** `strands_code_cli/scope.py:1-13`, `scripts/uattest/driver.py:1-20`
**Apply to:** Every new file (`__init__.py`, lib, scenario files, report-adjacent
scripts) and every moved module (carried verbatim).

First line imperative summary; decision ids inline (``(D-07)``); `Args:` /
`Returns:` / `Raises:` in plain text. Ruff F+E+I never checks these — the
repackage must not drop them.

### Per-line `noqa` with reason, never file-level ignores

**Source:** `strands_code_agent/__init__.py:1`,
`scripts/route-probe.py:103,124`
**Apply to:** All D-22 waivers.

```python
from . import solution_user_agent  # noqa: F401 - registers the AWS Solutions user-agent ID
```

Form is `# noqa: <CODE> - <reason>` (F401) or bare `# noqa: <CODE>` where the
surrounding comment already explains (E402 after `_ensure_production_imports`).
No `per-file-ignores` in `[tool.ruff]`; the recommended `ignore = ["E501"]`
is rule-scope configuration, not a file ignore (CF-04).

### Test file skeleton

**Source:** `tests/test_cli_entry.py:1-30`, `tests/test_uattest_driver.py:1-32`
**Apply to:** All mirrored tests and split contract tests.

Module docstring → `__future__` → stdlib / third-party / first-party imports →
module constants → `_private` helpers → `# ---` section banners →
`Test<Area>` classes with `test_<behavior>` methods. Suite-wide fixtures stay
in root `tests/conftest.py` (`_no_live_pricing` autouse fixture) — do not
duplicate it into mirrored subpackages.

### `uv`-only invocation

**Source:** `README.md:22-24,112-114`, `scripts/uattest/driver.py:29`
**Apply to:** CI workflow, pre-commit hooks, report-generation commands.

```bash
uv run pytest tests/ -q
uv run --project <path-to-repo> strands-code
```

Every gate runs via `uv run --group dev …`; CI uses `astral-sh/setup-uv`
with `uv sync --locked`; never bare `pip`/`python`. Hermetic at gate time:
no network, no credentials, no xenon `--url`.

### Commit discipline for moves

**Source:** RESEARCH.md Pattern 1 (git-man verified); no in-repo analog needed.
**Apply to:** Every repackage, test-mirror, and rig-split step.

`git mv` in a commit containing ONLY renames → separate commit for import
rewrites → separate commit for body edits. `uv run pytest tests/ -q` green
at every commit, not just at wave end. Sequence: cleanup → ruff format+fix →
measure+report → repackage → rig split → README → flip gates to blocking.

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md
patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.pre-commit-config.yaml` hook bodies | config | event-driven | No pre-commit config exists in-repo; YAML style copies `dependabot.yml`, hook structure comes from RESEARCH.md sketch |
| `[tool.ruff]` / `[tool.importlinter]` block contents | config | batch | No linter/complexity config exists in-repo; TOML table style copies `[tool.pytest.ini_options]`, rule/contract contents come from RESEARCH.md code examples |
| Xenon / import-linter CI step shape | config | batch | `publish.yml` has no gate steps (build+publish only); step commands come from RESEARCH.md CI sketch |
| Deletion targets (D-15) | — | — | Removals need no pattern; `git rm -r` + grep-completeness checks |

## Metadata

**Analog search scope:** `strands_code_cli/`, `strands_code_agent/__init__.py`,
`strands_code_agent/search_tool.py`, `scripts/uattest/`, `scripts/route-probe.py`,
`tests/`, `.github/`, `docs/`, `pyproject.toml`, `README.md`, `AGENTS.md`
**Files scanned:** 16 direct reads + directory listings + `git ls-files` tracking
verification (all analogs confirmed tracked)
**Pattern extraction date:** 2026-10-16
