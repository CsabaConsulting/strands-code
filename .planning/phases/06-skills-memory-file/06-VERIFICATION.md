---
phase: 06-skills-memory-file
verified: 2026-10-05T01:06:38Z
status: passed
score: 23/23 must-haves verified
covered_files:
  - .planning/phases/06-skills-memory-file/06-01-PLAN.md
  - .planning/phases/06-skills-memory-file/06-01-SUMMARY.md
  - .planning/phases/06-skills-memory-file/06-02-PLAN.md
  - .planning/phases/06-skills-memory-file/06-02-SUMMARY.md
  - .planning/phases/06-skills-memory-file/06-03-PLAN.md
  - .planning/phases/06-skills-memory-file/06-03-SUMMARY.md
  - .planning/phases/06-skills-memory-file/06-04-PLAN.md
  - .planning/phases/06-skills-memory-file/06-04-SUMMARY.md
  - .planning/phases/06-skills-memory-file/06-CONTEXT.md
  - .planning/phases/06-skills-memory-file/06-REVIEW.md
  - strands_code_cli/completer.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/memory_file.py
  - strands_code_cli/memory_modes.py
  - strands_code_cli/router.py
  - strands_code_cli/skills.py
  - tests/test_memory_curate.py
  - tests/test_memory_file.py
  - tests/test_skills.py
covered_digest: "v1:sha256:a3f269431eebf3445b7e7dffa1417ce968f5462757d43bdd12cf11d4817ab9ee"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 16/17
  gaps_closed:
    - "Autocomplete matches on the bare skill name and completes the full local:<name> form; /skills lists, shows, and removes local skills (per D-03)"
  gaps_remaining: []
  regressions: []
---

# Phase 6 Verification: Skills + Memory File (SKILL-01, SKILL-02)

**Phase Goal:** Users can extend the CLI with local skills and persistent repo conventions
**Verified:** 2026-10-05T01:06:38Z
**Status:** passed
**Re-verification:** Yes — after 06-04 gap closure (previous: gaps_found, 16/17)

**Verifier:** gsd-verifier under the generic-agent workaround (typed
dispatch unavailable this session; independent read of code, not
SUMMARY claims)

**Scope:** prior 17 truths (16 passed + 1 gap) + 06-04 gap-plan
must_haves (6 truths, 6 artifacts, 2 key_links) + SKILL-01/SKILL-02 +
D-01..D-13 + 06-REVIEW.md re-review (WR-06 new, IN-01..IN-04 carried).

**Test runs (this session):** full `tests/` → **790 passed,
5 deselected** (baseline 775 + 15 new gap tests; same 5 pre-existing
integration deselects); phase-6 files → **122 passed, 0 skipped**;
independent T3 + WR-06 probes run live (see Behavioral Spot-Checks).

(Digest method: `gsd_run query verification.fingerprint 06 <files>`,
value pasted verbatim — never hand-computed.)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ------- | ---------- | -------------- |
| 06-01 T1 | /\<name\> invokes with trailing text composed with skill instructions (D-01) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-01 T2 | Builtin wins collisions with exact warning; completer omits shadowed | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-01 T3 | Autocomplete completes local:\<name\>; /skills lists/shows/removes (D-03) | ✓ VERIFIED (gap closed) | `loop.py:936` slashed pair; live probe: `/mys` → `/local:myskill` → skill-branch dispatch; `test_accepted_completion_dispatches_to_skill_branch` green |
| 06-01 T4 | Missing skills dir is empty, never a crash; empty trailing text runs | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-01 T5 | /skills list sorted by bare name, stable across runs | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-02 T1 | Dual files auto-load every turn, .agent wins, precedence stated (D-04) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-02 T2 | Frontmatter keys and section markers round-trip (D-05) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-02 T3 | External edits reload at next boundary, one note per file (D-06) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-02 T4 | /memory mode shows/flips curate/silent holder; silent logs writes (D-07) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-02 T5 | Atomic writes; corrupt frontmatter degrades, never crashes | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T1 | /memory review: approve applies, deny skips and never re-queues | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T2 | Approve-with-edit NL revise rounds: quoted review, accept/revert/iterate (D-08) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T3 | /init scans and drafts through curate: full to .agent, thin pointer to root (D-09/D-10) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T4 | /init re-runs merge-scan: only missing/stale drafted, approved never clobbered (D-11) | ✓ VERIFIED (regression) | Prior line evidence stands; WR-04 churn fixed by 06-04 G5 (see below) |
| 06-03 T5 | Shallow scan default; /init deeper adds sources, manifests, tests (D-12) | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T6 | Promotion poll surfaces new fact files capped per sweep; never auto-deletes | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-03 T7 | Interrupted or denied rounds leave both memory files byte-identical | ✓ VERIFIED (regression) | Prior line evidence stands; full suite green, no regressions |
| 06-04 G1 | Accepted skill completion yields /local:\<name\> dispatching to the skill branch (T3 closed) | ✓ VERIFIED | `loop.py:933-940`; `completer.py:20` docstring; end-to-end test + live probe (see T3 detail) |
| 06-04 G2 | Typed /\<name\> match prints visible confirmation; typos stay silent (D-13) | ✓ VERIFIED | `loop.py:858-880` + wiring `loop.py:1027-1030`; `TestSkillMatchNote` (4 tests) green |
| 06-04 G3 | EOF at curate/revise prompts fails closed; session still saves/flushes (WR-02) | ✓ VERIFIED | `loop.py:620-621`, `loop.py:759-761`; 3 EOF tests green |
| 06-04 G4 | Approve writes before queue mutation; failed writes stay pending (WR-03) | ✓ VERIFIED | `memory_modes.py:244-256` get→apply→mutate; retry test green |
| 06-04 G5 | Curate approve stamps/refreshes freshness markers; next /init not stale (WR-04) | ✓ VERIFIED | `router.py:519-532` mirroring sibling `router.py:570-577`; marker + diff-fresh tests green |
| 06-04 G6 | Approve write failures surface as transcript lines, never session crashes (WR-05) | ✓ VERIFIED | `loop.py:985-993` boundary guard + `router.py:634-637` explicit guard; error-reply tests green |

**Score:** 23/23 truths verified (0 present, behavior-unverified)

### Gap closure detail (full 3-level verification on prior gap + new 06-04 truths)

#### 06-01 T3 — CLOSED — Slash-prefixed completions dispatch end to end

- `strands_code_cli/loop.py:933-940` — `_skill_words` now pairs skills
  as `(entry.name, f"/{entry.namespaced}")`, matching the builtin
  `(head, f"/{head}")` shape on line 934. The accepted line keeps its
  leading slash and re-enters dispatch as a slash.
- `strands_code_cli/completer.py:20` — docstring names the
  `/local:<name>` completion form.
- `strands_code_cli/skills.py:117-134` — `resolve` already accepted the
  `/local:<name>` form (re-read this session); no router change was
  needed, as the gap plan predicted.
- Test evidence: `tests/test_skills.py:458`
  `test_accepted_completion_dispatches_to_skill_branch` takes the real
  accepted completion text for `Document("/pd")` and asserts dispatch
  returns `("agent", ...)` containing
  `Skill 'local:pdf-tools' instructions:` plus the trailing text — the
  exact end-to-end assertion the gap demanded. All other
  `TestSkillCompleter` assertions moved to the slashed form
  (`test_skills.py:396-456`); shadowed/trailing-space/fuzzy behavior
  unchanged.
- Independent probe (this session, `/tmp/phase6_reverify_probe.py`,
  mirroring `loop._skill_words` exactly): completions for `/mys` →
  `['/local:myskill']`; accepted line starts with `/` → True;
  `dispatch(...)` → `agent` with the instructions marker. The prior
  session's FAIL (`local:myskill` → plain turn) now passes.

#### 06-04 G2 — PASS — D-13 match echo (D-13: "visible match confirmation ... agent's discretion")

- `strands_code_cli/loop.py:858-880` — module-level
  `skill_match_note(skills, text)` mirrors the dispatch head split
  (strip, slash head before first space), returns `None` for
  non-slash lines, `None` index, unresolvable heads, and shadowed
  entries, else `Matched skill '<namespaced>' — <description>`.
- `strands_code_cli/loop.py:1027-1030` — `run_loop` prints the note via
  `console.print` after dispatch returns `("agent", ...)` and before
  the turn runs (accept-echo, per the planner's D-13 resolution; no
  prompt_toolkit lexer surgery).
- Test evidence: `TestSkillMatchNote` (`test_skills.py:524-552`) —
  exact echo for `/pdf-tools` and `/local:pdf-tools hi`, `None` for
  typo `/pdff`, unknown `/nope`, shadowed `/model`, non-slash
  `plain turn`, and `None` index. All green.
- WR-06 caveat (residual, not a gap — see Residuals): hostile
  descriptions can garble/raise through Rich markup. Normal-path
  behavior is exactly as specified.

#### 06-04 G3 — PASS — WR-02 EOF fails closed

- `strands_code_cli/loop.py:620-621` — `except EOFError: break` beside
  the `KeyboardInterrupt` handler in `review_memory_queue`: EOF at the
  approve/deny/revise prompt or the revise-instruction read leaves all
  unreviewed proposals pending; the idle prompt's EOF → break path
  then exits through save/flush.
- `strands_code_cli/loop.py:759-761` — `except EOFError` in
  `consume_revise_turn` disarms and returns the existing revert string
  (return, not re-raise). Docstring (`loop.py:737-738`) documents the
  Ctrl-D contract.
- Test evidence: `test_review_eof_at_prompt_keeps_proposal_pending`,
  `test_review_eof_at_revise_instruction_keeps_proposal_pending`,
  `test_consume_eof_disarms_with_revert_note` (byte-identical tmp
  file asserted) — all green; KeyboardInterrupt behavior unchanged
  (existing tests green).

#### 06-04 G4 — PASS — WR-03 apply-first approve ordering

- `strands_code_cli/memory_modes.py:244-256` — `approve` now
  get-first (`.get`, unknown ids still return `unknown_proposal`),
  then `apply_fn(proposal)`, then `del` + approved-add + the unchanged
  `Approved {id} → {section}.` return. A raising write leaves the
  entry pending for retry or next turn.
- Test evidence:
  `test_approve_failed_write_stays_pending_for_retry` (raising write
  keeps p1 pending with zero approved ids; retry with a working write
  succeeds) — green; success-reply and deny/no-nag tests unchanged
  and green.

#### 06-04 G5 — PASS — WR-04 freshness markers on curate writes

- `strands_code_cli/router.py:519-532` — `apply_memory_proposal`
  computes `marker = fresh_marker() + "\n"` once, prepends it above
  the heading for new sections, and refreshes the glued marker line
  (`UPDATED_MARKER_RE` on `lines[head_idx - 1]`) or inserts one for
  existing sections — mirroring `apply_memory_section`
  (`router.py:570-577`) exactly, including the `head_idx > 0` guard.
  Body placement (append-at-end-of-section) and the atomic dump path
  are untouched. The marker position matches the `diff_sections` read
  (`memory_file.py:714`, `lines[head_idx - 1]`).
- Test evidence:
  `test_apply_memory_proposal_stamps_freshness_marker` (marker line
  immediately above `## Build`, body inside section),
  `test_approved_section_reads_fresh_to_diff` (no `Build` entry from
  `diff_sections`), plus refresh-not-duplicate coverage — all green.
  The 06-03 T4 re-draft churn caveat is resolved.

#### 06-04 G6 — PASS — WR-05 errors as transcript lines

- `strands_code_cli/loop.py:985-993` — turn-boundary
  `review_memory_queue` call wrapped in `try/except (OSError,
  ValueError)`, yielding `Memory review skipped — write failed: {exc}`
  (covers both silent auto-apply and curate paths, since both flow
  through the same call).
- `strands_code_cli/router.py:634-637` — explicit `/memory approve`
  wraps `queue.approve` in the same pair, returning `Memory write
  failed — proposal {target} kept pending: {exc}`. The "kept pending"
  wording is accurate given the G4 ordering.
- Test evidence:
  `test_review_silent_mode_propagates_write_failure_to_caller`
  (OSError reaches the caller guard),
  `test_memory_approve_reports_write_failure_as_reply` (kept-pending
  prefix + p1 still in `list_pending` against a tampered file) — both
  green.

### 06-04 key links — both hold

- K1 completion → dispatch: skill completion text starts with `/`
  (`loop.py:936`), so `SlashCompleter` output re-enters dispatch as a
  slash resolving through `SkillIndex.resolve` to the `("agent",
  composed)` branch — proven by the end-to-end test and live probe.
- K2 approve ordering + guards: writes run before queue mutation
  (`memory_modes.py:253-254`), and every raising write on the
  boundary (`loop.py:992`) and explicit (`router.py:636`) paths is
  caught into a transcript line with the proposal pending — proven by
  the retry and error-reply tests.

### Regression method (16 prior-passed truths)

Quick regression per re-verification mode: all seven phase files
present and substantive (no stub-outs), all prior line anchors
re-confirmed by the re-review's exact line re-reads
(WR-01..WR-05 fix verification), and the full suite green at
790 passed / 5 deselected with zero skipped tests in the three
phase-6 files (122 passed). No regressions.

### Deferred Items

None — no later phase covers skill completion or memory curation
(Phases 7/8/9 are subagents, routing, CodeAct).

### Advisory (New Scope, Unevidenced)

None. (WR-06 is new-scope but *evidenced* — live probe this session —
and dispositioned as a residual/recommendation below, not advisory.)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `strands_code_cli/skills.py` | SkillIndex + SkillEntry + shadow warnings + guarded remove | ✓ VERIFIED | Unchanged by gap round; regression green |
| `strands_code_cli/completer.py` | SlashCompleter + build_completer factory | ✓ VERIFIED | Docstring names `/local:<name>` form (`completer.py:20`); wired |
| `strands_code_cli/router.py` (skill/memory branches) | skills kwarg, dynamic /skill, /skills, /memory, /init, USAGE_HINT | ✓ VERIFIED | Approve error-as-reply (`router.py:634-637`) + markers (`router.py:519-532`); all branches live |
| `strands_code_cli/loop.py` (wiring) | Completer, shadow warnings, snapshot/sweep/banner, flush, review + consumers | ✓ VERIFIED | Slashed words (`loop.py:936`) + match echo (`loop.py:858-880,1027-1030`) + EOF arms + boundary guard |
| `strands_code_cli/memory_modes.py` | Mode holder + queue + revise/init states + sweep | ✓ VERIFIED | Apply-first approve (`memory_modes.py:244-256`); wired |
| `strands_code_cli/memory_file.py` | Dual loader + atomic saver + injector + sweep + flush + scan/diff/apply | ✓ VERIFIED | Unchanged by gap round; regression green |
| `strands_code_cli/main.py` (registration) | Explicit skills/memory kwargs + injector registration | ✓ VERIFIED | Unchanged by gap round; regression green |
| `tests/test_skills.py` | Index/routing/command/completer/match-note tests | ✓ VERIFIED | Slashed assertions + end-to-end dispatch test + `TestSkillMatchNote`; green |
| `tests/test_memory_file.py` | Contract + reload + modes tests | ✓ VERIFIED | Unchanged; green |
| `tests/test_memory_curate.py` | Curate + revise + init + gap tests | ✓ VERIFIED | EOF + ordering + marker + error-reply tests; green |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| Prior K1–K9 | — | prior report anchors | ✓ WIRED | All hold; re-review re-read confirms; suite green |
| 06-04 K1 skill completion | dispatch skill branch | leading-slash text → `SkillIndex.resolve` → `("agent", composed)` | ✓ WIRED | End-to-end test + live probe |
| 06-04 K2 approve writes | transcript | apply-first + `(OSError, ValueError)` guards on boundary + explicit paths | ✓ WIRED | Retry + error-reply tests |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
| -------- | ------------- | ------ | --------- | ------ |
| SkillIndex | entries | `Skill.from_directory(skills_dir)` SDK seam | Yes — real SKILL.md loads | ✓ FLOWING |
| dispatch /skill | composed | skill instructions + trailing text | Yes — composed into the agent turn | ✓ FLOWING |
| completer | words | loop-owned `SkillIndex.list_entries()` per keystroke | Yes — live index, slash-prefixed (T3 fixed) | ✓ FLOWING |
| match echo | note | `SkillIndex.resolve` of the typed head | Yes — namespaced name + description | ✓ FLOWING |
| injector render | block | `load_memory()` on mtime change | Yes — both files, frontmatter stripped | ✓ FLOWING |
| boundary sweep | changed | live `st_mtime` vs snapshot | Yes — reload + notes | ✓ FLOWING |
| curate queue | proposals | promotion sweep + init consumer | Yes — fact files / labeled fences | ✓ FLOWING |
| approve/deny | files | atomic `dump_memory_file` / record-only | Yes — writes + no-nag | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Skill completion invokes the skill | `/tmp/phase6_reverify_probe.py` T3 half (SlashCompleter + dispatch) | `/local:myskill`, `/`-prefixed → skill branch with instructions marker | ✓ PASS (was ✗ FAIL) |
| Match echo prints; typos silent | `TestSkillMatchNote` (4 tests) | exact echo + 5 silent cases | ✓ PASS |
| EOF fails closed | 3 EOF tests in test_memory_curate.py | pending + revert note + byte-identical file | ✓ PASS |
| Approve retry + markers + error lines | ordering/marker/error-reply tests | all green | ✓ PASS |
| Full suite green | `uv run pytest tests/ -q` | 790 passed, 5 deselected | ✓ PASS |
| Phase-6 tests unskipped | real skip-marker grep over the 3 test files | no matches | ✓ PASS |
| WR-06 markup crash | `/tmp/phase6_reverify_probe.py` WR-06 half | `MarkupError` on `[/]` description (residual, see below) | ⚠️ KNOWN (not a gap) |

Step 7c probes: N/A — no `probe-*.sh` declared by any plan,
summary, or success criterion, and none exist under `scripts/`.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| SKILL-01 | 06-01, 06-04 | CLI loads skills from local `./.agent/skills`; user can list and invoke them | ✓ SATISFIED | Load/list/invoke (T1/T2/T4/T5) + completion-to-dispatch (T3 closed, G1) + match echo (G2, D-13) |
| SKILL-02 | 06-02, 06-03, 06-04 | CLI auto-loads the repo memory file; user can scaffold and edit it (`/init`, `/memory`) | ✓ SATISFIED | T1–T5 (06-02) + T1–T7 (06-03) + EOF/approve/marker/error hardening (G3–G6) |

Every ID from every plan frontmatter (`06-01: SKILL-01`,
`06-02: SKILL-02`, `06-03: SKILL-02`, `06-04: SKILL-01, SKILL-02`)
is accounted for above. Orphan check: REQUIREMENTS.md maps exactly
SKILL-01/SKILL-02 to Phase 6 — no orphaned IDs. (REQUIREMENTS.md and
the traceability table already show SKILL-01/SKILL-02 checked /
Complete — the prior report's flip follow-up is done; observed, not
performed by this report.)

### Decision coverage

D-01..D-12 held per the prior report (12/12 CONTEXT decisions
honored); D-13 (typed-name match confirmation, agent's discretion on
rendering) is implemented as accept-echo per the 06-04 planner
resolution and verified under G2. 13/13 honored.

### Anti-Patterns Found

| File | Finding | Severity | Impact |
| ---- | ------- | -------- | ------ |
| loop.py:936 | WR-01 slash-less completions (prior T3 gap) | ✅ Fixed | Closed; end-to-end test + live probe |
| loop.py:620-621,759-761 | WR-02 EOF crash at curate/revise prompts | ✅ Fixed | Fail-closed arms + 3 behavioral tests |
| memory_modes.py:244-256 | WR-03 approve pops before write | ✅ Fixed | Apply-first + retry test |
| router.py:519-532 | WR-04 no freshness marker on curate approve | ✅ Fixed | Stamp/refresh + diff-fresh tests |
| loop.py:985-993, router.py:634-637 | WR-05 approve write failures crash session | ✅ Fixed | Transcript lines + error-reply tests |
| loop.py:880,1029-1030 (+ router.py:726,739 siblings) | WR-06 Rich markup injection via skill-match echo | 📋 Residual | Real but un-specced edge; no must_have invalidated — see Residuals |
| memory_file.py:37-40 | IN-01 frontmatter `updated` frozen at import; shared mutable defaults | ℹ️ Info | Carried; out of gap scope |
| router.py:555-581, memory_file.py:754-782 | IN-02 model-emitted `## ` lines splice section structure | ℹ️ Info | Carried; mitigated by quoted review |
| memory_modes.py:298-299 | IN-03 `sweep_promotions` reads fact files with no size cap | ℹ️ Info | Carried; out of gap scope |
| memory_file.py:334-338 | IN-04 `except Exception: pass` around idempotency stash | ℹ️ Info | Carried; out of gap scope |

Debt-marker gate: zero `TBD`/`FIXME`/`XXX` hits across all seven
phase files (grep this session).

### Human Verification Required

None.

### Gaps Summary

No gaps. The single blocking gap (06-01 T3) is closed with line
evidence plus a new end-to-end behavioral test plus an independent
live probe; all six 06-04 gap-plan truths verify with behavioral
tests; all 16 previously passing truths regress clean (790-test
suite green, zero skips in phase files); all 10 prohibitions hold
(no gap-round change touches their scope); both requirements are
satisfied with every plan-declared ID accounted for.

### WR-06 disposition (does it invalidate any must_have?)

No. WR-06 (Rich markup injection via the D-13 match echo) is real —
independently reproduced this session: a skill description containing
`[/]` makes `console.print(skill_match_note(...))` raise
`MarkupError` out of `run_loop` (`loop.py:85` default `Console()`
with markup enabled; format site `loop.py:880`, print site
`loop.py:1029-1030`), skipping save/flush. But it invalidates no
must_have as worded:

- G2 (D-13) requires the echo on match and silence on
  typo/unknown/shadowed/non-slash — all six cases pass with
  behavioral tests on normal descriptions. No truth covers
  adversarial description content.
- G3's save/flush guarantee is scoped to EOF-at-prompt paths, which
  are unaffected.
- The sibling `/skills` list/show prints (`router.py:726,739`) share
  the pattern and predate the gap round untouched.

This matches the prior verification's precedent exactly: WR-02/WR-05
were the same save-skipping crash class and were judged "no
must_have invalidated (un-specced edge), fix recommended." WR-06
gets the same disposition: **residual/recommendation, not a gap.**

**Recommended fix (fast follow-up, one line + tests):** escape at the
format site — `from rich.markup import escape` and `...
{escape(entry.description)}` in `skill_match_note`, plus the same
`escape(...)` around both `entry.description` interpolations in
`_skills_message` (`router.py:726,739`) — or `console.print(...,
markup=False)` at the three print sites. A regression test with a
`[/]`-bearing fixture description should assert the echo prints
literally without raising.

## Residuals (not gaps — carry, do not close here)

- WR-06 Rich markup injection (above): fix recommended as a fast
  follow-up; re-verify with the `[/]`-fixture test when landed.
- D4 live-terminal check (06-03 SUMMARY): the tty `radio_choice`
  branch of the curate/revise prompts is exercised only via the typed
  path + shared control in tests; one live-terminal pass recommended
  at end-of-phase UAT.
- `.agent/memory` promotion keys on filename diffs; a richer harness
  extraction signal can layer onto the same queue later (06-03 SUMMARY).
- IN-01..IN-04 carried unchanged (explicitly out of gap scope).

## Follow-ups (closeout)

- REQUIREMENTS.md SKILL-01/SKILL-02 flip plus traceability
  Pending → Complete: already done (observed checked/Complete).
- Phase seal: ready — 23/23 truths verified, no gaps, no
  behavior-unverified truths, no overrides.

---
_Verified: 2026-10-05T01:06:38Z_
_Verifier: gsd-verifier (generic-agent workaround — typed dispatch unavailable)_
