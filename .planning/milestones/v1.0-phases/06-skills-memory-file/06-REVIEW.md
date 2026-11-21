---
phase: 06-skills-memory-file
reviewed: 2026-10-05T01:03:22Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - strands_code_cli/skills.py
  - strands_code_cli/completer.py
  - strands_code_cli/memory_file.py
  - strands_code_cli/memory_modes.py
  - strands_code_cli/router.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 6: Code Review Report (re-review after 06-04 gap closure)

**Reviewed:** 2026-10-05
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Re-reviewed Phase 6 after the 06-04 gap commits (`c49683c`, `4f7424d`,
`aa5082a`; 4 source files, 285 insertions). All five prior warnings
(WR-01..WR-05) are verified fixed against current source, each by probe
or exact line re-read; the four prior info items (IN-01..IN-04) were out
of gap scope and remain open unchanged. One new warning (WR-06) was
introduced by the gap diff: the new D-13 skill-match echo prints an
unescaped skill description through Rich markup, which provably garbles
output and can raise `MarkupError` out of `run_loop`. Phase tests pass
(`test_skills.py`, `test_memory_file.py`, `test_memory_curate.py`: 122
passed, up from 107 — gap tests included, WR-01 assertions updated).

Prior-finding verification (all confirmed fixed, no residual):

- **WR-01 (fixed):** `_skill_words` now pairs
  `(entry.name, f"/{entry.namespaced}")` (`loop.py:936`); probe through
  the real `FuzzyCompleter` confirms `/mys` completes to `/local:myskill`
  with `start_position=-4`, so the accepted line re-enters dispatch as a
  slash. Bare-name matching is untouched. Test assertions updated to the
  `/local:pdf-tools` form (`tests/test_skills.py:405,425,454`).
- **WR-02 (fixed):** All four bare-`input()` curate/revise sites
  (`loop.py:573,617,717,755`) now sit inside `try` blocks with an
  `except EOFError` fail-closed path: review breaks with proposals
  pending (`loop.py:620-621`), revise disarms with the revert note
  (`loop.py:759-761`). `answer` cannot be read unbound on the
  exception path (both handlers exit before use). The only other
  `input()` in the package (`policy_gate.py:420`) is pre-existing
  Phase 4 scope, untouched by this phase.
- **WR-03 (fixed):** `CurateQueue.approve` (`memory_modes.py:244-256`)
  now reads with `.get`, runs `apply_fn` before any mutation, and only
  then deletes from pending and records approval — exactly the
  suggested ordering. A raising write leaves the entry pending.
- **WR-04 (fixed):** `apply_memory_proposal` (`router.py:519-532`) now
  stamps/refreshes the freshness marker with logic identical to the
  sibling writers: glued marker above the heading in both the
  new-section and existing-section branches. This matches the
  `diff_sections` read (`memory_file.py:714`, `lines[head_idx - 1]`),
  so just-approved sections scan as fresh. Index handling is safe
  (body insert at `end` precedes marker ops at `head_idx`).
- **WR-05 (fixed):** All three `queue.approve` callers are guarded:
  the boundary review (silent + curate paths, `loop.py:985-993`) and
  the explicit `/memory approve` path (`router.py:634-637`) both catch
  `(OSError, ValueError)` into transcript lines. The "kept pending"
  wording is accurate given the WR-03 ordering. Probes confirm
  ordinary `OSError` text (including `[Errno N]`) prints safely, so
  the new error lines cannot crash on realistic failures.

## Narrative Findings (AI reviewer)

## Warnings

### WR-06: New skill-match echo prints unescaped description through Rich markup (garble + crash path)

**File:** `strands_code_cli/loop.py:880` (format), `strands_code_cli/loop.py:1029` (print)
**Issue:** The gap-added `skill_match_note` interpolates
`entry.description` — SKILL.md frontmatter, i.e. repo content the
codebase itself labels untrusted (`router.py:199`) — into a string
printed with `console.print`, and `console` is a default `Console()`
with markup enabled (`loop.py:85`). Proven by probe against the
installed Rich: a description containing a valid-tag fragment such as
`[b]` or `[link=foo]` is silently swallowed (output corruption), and a
closing-tag fragment such as `[/]` raises `MarkupError`. The print sits
outside the agent-turn `try`, so the exception escapes `run_loop` with
a traceback, skipping `explicit_save`, `flush_memory`, and
`index.ensure` — the same save-skipping crash class as WR-02/WR-05.
Unlike the pre-existing `/skills` prints below, this echo fires
automatically on every matching skill turn, so one hostile or
bracket-heavy local skill description breaks all of its invocations.
The two pre-existing sibling prints share the pattern and should be
fixed together: `/skills` list (`router.py:726`) and `/skills show`
(`router.py:739`).
**Fix:** Escape at the format site (preferred — travels with the data):
```python
from rich.markup import escape
return f"Matched skill '{entry.namespaced}' — {escape(entry.description)}"
```
and the same `escape(...)` around both `entry.description`
interpolations in `_skills_message`. Alternative: `console.print(...,
markup=False)` at the three print sites (none of these strings carry
intentional markup).

## Info

### IN-01: `MEMORY_FRONTMATTER_DEFAULTS` stamps `date.today()` at import time and is a shared mutable

**File:** `strands_code_cli/memory_file.py:37-40`
**Issue:** Carried forward — unchanged by the gap diff and re-verified
present. The `updated` default is frozen at first import, so a session
spanning midnight scaffolds files with yesterday's date; the
module-level dict is also one missed `dict()` copy away from
cross-call mutation (all current call sites — `router.py:514,566`,
`memory_file.py:768,787` — still copy correctly).
**Fix:** Replace with a `fresh_frontmatter()` function returning a new dict with
`date.today().isoformat()` per call.

### IN-02: Model-emitted `## ` headings inside accepted revise/init blocks splice raw section structure into MEMORY.md

**File:** `strands_code_cli/router.py:555-581`, `strands_code_cli/memory_file.py:754-782`
**Issue:** Carried forward — unchanged by the gap diff and re-verified
present. `apply_memory_section` / `apply_init_proposal` still insert
the accepted block verbatim (`lines[head_idx + 1 : end] = [block]`). If
the model includes a `## ` line, it becomes a real heading: a same-name
forgery truncates all later reads of that section at the forged line
(orphaning the tail from future replaces), and any other forgery splits
the span. The user does see the block quoted before accept, which
mitigates this to Info.
**Fix:** On accept, demote leading `## ` lines inside the block to `### ` (or reject
blocks containing them with a note asking to iterate).

### IN-03: `sweep_promotions` reads fact files with no size cap

**File:** `strands_code_cli/memory_modes.py:298-299`
**Issue:** Carried forward — unchanged by the gap diff and re-verified
present. Unlike the `/init` scan budget (`MAX_SCAN_FILES`/`MAX_SCAN_BYTES`),
promotion reads the whole file: a runaway fact file becomes a huge
proposal body, printed in full to the transcript at review and appended
unbounded to `.agent/MEMORY.md` on approve.
**Fix:** Cap per-file promotion reads (e.g. reuse a slice helper with an honest
truncation note) and skip files over the cap with a transcript line.

### IN-04: `register_memory_plugin` swallows all exceptions from the idempotency stash

**File:** `strands_code_cli/memory_file.py:334-338`
**Issue:** Carried forward — unchanged by the gap diff and re-verified
present. `except Exception: pass` around the `agent._memory_plugin`
setattr (meant for frozen test doubles) also masks real errors such as
`__slots__`/`__setattr__` failures on actual agents, silently disabling
the idempotency guard so a second registration double-injects.
**Fix:** Narrow to `except (AttributeError, TypeError): pass`.

---

_Reviewed: 2026-10-05_
_Reviewer: generic-agent workaround for gsd-code-reviewer (typed dispatch unavailable)_
_Depth: standard_
