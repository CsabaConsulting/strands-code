---
phase: 08-model-routing-with-decision-models
reviewed: 2026-10-12T07:34:08Z
depth: standard
reviewer: gsd-code-reviewer (generic-agent workaround — typed gsd-code-reviewer dispatch unavailable in this runtime)
files_reviewed: 4
files_reviewed_list:
  - strands_code_cli/routing.py
  - scripts/route-probe.py
  - tests/test_routing.py
  - tests/test_routing_strategy.py
findings:
  critical: 0
  warning: 0
  info: 6
  total: 6
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-10-12T07:34:08Z (scoped gap-closure re-review; full-phase review 2026-10-12T07:01:22Z below)
**Depth:** standard
**Files Reviewed:** 4 (gap-commit scope; prior full review covered 16)
**Status:** issues_found

## Summary

**Re-review (2026-10-12T07:34:08Z, generic-agent workaround):** scoped
re-review of the 08-06 gap-closure commits (`08d6d4a..0109ef6`: GAP-01
YAML-bool level fold, GAP-02 unhashable-choice guard, GAP-03 lazy local
tag) across the 4 gap-commit files. Both prior warnings verified fixed
by source inspection plus execution (see Resolved Warnings). The 5
prior infos carry over unchanged — their regions/files are untouched by
the gap diff (verified via `git diff`; IN-04 line ref shifted +6). One
new info (IN-06) on the fresh GAP-01 diff. Supporting evidence: 231
passed, 2 deselected (integration) across `tests/test_routing.py` and
`tests/test_routing_strategy.py`.

**Full-phase review (2026-10-12T07:01:22Z):** reviewed the phase 08
Decision-API rework (5 plans, commits `5683d8d..HEAD`):
typed Decision-API transports plus one-retry policy, answer validation with the
code-side threshold/tie gate, sequential two-call routing, preflight gating,
the retry matrix with turn-scoped pause, the 64 KiB body bound, split-catalog
setup, the compact `/cost` routing entry, and the probe runner with its
20-probe set and recorded baseline.

Library code (`strands_code_cli/`) and scripts received full standard-depth
review against the diff; tests received reliability-scoped checks (live-test
gating, fixture consistency); docs and eval data received targeted accuracy
and validity checks. No critical issues. The two warnings are a contract
violation in choice validation (proven by execution: unhashable `choice`
raises `TypeError` instead of holding) and a local-daemon prerequisite that
needlessly blocks cloud-only probe runs. Supporting evidence: 366 passed,
2 deselected (integration) across the five routing test files; probe data
validated (20 unique ids, 20+20 baseline verdicts); no stale references to
the removed chat-JSON surface (`parse_pick`, `build_routing_prompt`,
`OPENROUTER_CHAT_URL`, `why`) remain in source.

## Resolved Warnings

### WR-01: Unhashable `choice` raises TypeError instead of holding — RESOLVED

**File:** `strands_code_cli/routing.py:1305`

**Issue:** `_validate_choice_shape` tests `answer.get("choice") not in probs`
where `probs` is a dict. A malformed vendor answer with a non-string
`choice` (`["a"]`, `{"x": 1}`) raises `TypeError: unhashable type` instead
of returning None as the "None holds" contract promises. The same shape
flows through `validate_choice_answer` (`routing.py:1325`, `not in live`
against a set) and `_validate_effort_answer`, so both decision calls are
affected. Verified by execution: list and dict choices raise, while None
and int choices correctly return None. Production impact is muted because
both hook call sites catch broad `Exception` around `decide()`, but the
hold is then misreported as `decide failed` and any direct caller of
`decide()` / `validate_choice_answer` (e.g. `run_probe` in
`scripts/route-probe.py`) crashes outright.

**Fix:**

```python
choice = answer.get("choice")
if not isinstance(choice, str) or choice not in probs:
    return None
```

(JSON object keys are always strings, and both membership sets — candidate
ids and effort levels — are strings, so the `str` guard rejects nothing
legitimate. Apply the same guard at the `not in live` check, or rely on
the shape check alone since `validate_choice_answer` runs after it.)

**Resolution (verified 2026-10-12T07:34:08Z):** fixed by `e27b322`
(GAP-02) exactly as suggested — `str` guard added in both
`_validate_choice_shape` (`strands_code_cli/routing.py:1313-1315`) and
`validate_choice_answer` (`strands_code_cli/routing.py:1334-1335`); the
effort path inherits the fix via `_validate_choice_shape`
(`routing.py:1347`). Verified by execution: list, dict, tuple, None,
and int choices all return None (hold) with no raise through both
`validate_choice_answer` and `_validate_effort_answer`. New
`TestUnhashableChoiceHolds` (`tests/test_routing.py:352-368`) locks the
contract. (The second `isinstance` is strictly redundant given the
shape check runs first, but harmless defense-in-depth — not flagged.)

### WR-02: `--run openrouter` aborts without a local Ollama daemon — RESOLVED

**File:** `scripts/route-probe.py:473`

**Issue:** `cmd_run` unconditionally resolves the local tag (`tag =
local_model or resolve_local_model()`) before dispatching on engine, and
`resolve_local_model` raises `SystemExit` when neither `nimble` nor
`tev1:0.8b` is ready. For `--run openrouter` the local tag is unused (the
OpenRouter transport never reads it; the record `pin` is the decision
model), so a cloud-only calibration machine fails with the misleading "no
decision model pulled" error despite needing no daemon at all.

**Fix:**

```python
tag = local_model or (
    resolve_local_model() if engine == "local" else LOCAL_MODEL_PIN
)
```

(Resolve lazily for local runs only; record the pin constant or an
explicit `"n/a"` for cloud runs.)

**Resolution (verified 2026-10-12T07:34:08Z):** fixed by `eb7db12`
(GAP-03) as suggested — `cmd_run` (`scripts/route-probe.py:476-479`)
resolves via `resolve_local_model()` on the local path only and falls
back to `LOCAL_MODEL_PIN` otherwise; `_warm_local` stays local-gated
(`route-probe.py:480-481`). Verified by execution: `cmd_run('openrouter',
...)` with `resolve_local_model` stubbed to raise completes rc=0
without touching the daemon, an explicit `--local-model` is still
honored on the cloud path, and the local path still resolves (raises
through the stub). The openrouter transport path
(`decide_via_openrouter`, `route-probe.py:313-318`) takes no local tag
and the record `pin` uses the decision model (`route-probe.py:335`),
so the pin-valued tag is inert there.

## Info

_Carry-over note (2026-10-12T07:34:08Z re-review): IN-01–IN-05 remain
open with their prior dispositions — none of their regions changed in
the gap diff (`08d6d4a..0109ef6` touches only the WR-01/WR-02/GAP-01
hunks plus tests). IN-04's line ref is updated for the +6 shift from
the GAP-03 hunk; all other refs verified current._

### IN-01: Dead `structured` field on chat-catalog entries

**File:** `strands_code_cli/router.py:634-644`

**Issue:** `_setup_catalog_entries` still scans `supported_parameters` and
stores a `"structured"` key per entry, but the split-catalog rework removed
its only reader (the `_setup_pick_decision` eligibility filter now takes
pre-filtered decisions-catalog entries). No remaining readers in source,
scripts, or tests — the key is computed and carried for nothing.

**Fix:** Drop the `structured` computation and key (and the
`supported_parameters` scan) from `_setup_catalog_entries`; if kept
deliberately as a debugging aid, note why in a comment.

### IN-02: Duplicated OpenRouter fetch transport

**File:** `strands_code_cli/live_pricing.py:387-399`

**Issue:** `fetch_openrouter_decision_models` duplicates the request/parse
body of `fetch_openrouter_models` (~14 lines: Request build, urlopen,
decode, `data`-list extraction, blanket-None failure). Timeout, header, or
payload-shape changes must now land twice to stay consistent.

**Fix:** Extract a shared `_fetch_openrouter_models(url)` helper taking the
endpoint URL, with both public fetchers delegating to it.

### IN-03: Discarded `int()` results read as dead expressions

**File:** `strands_code_cli/cost_context.py:205-206`

**Issue:** `_routing_line` calls `int(...)` on both token fields purely for
their `TypeError`/`ValueError` side effect inside the `try`, discarding the
results. Correct, but bare expression-statements trip B018-style
"useless expression" linters and read as leftover code.

**Fix:** Assign to `_` with a brief comment, e.g. `_ = int(...)  #
validate shape; values unused in the compact entry`.

### IN-04: `--compare` ignores `--out`

**File:** `scripts/route-probe.py:658-664`

**Issue:** `cmd_compare` hardcodes both run paths to
`/tmp/route-probe-<engine>.jsonl` while `--run` accepts `--out`. A
`--run --out custom.jsonl` + `--compare` workflow silently diffs stale
`/tmp` files (or reports them missing) instead of the just-written run.

**Fix:** Derive the compare input from `--out` when given (or document that
`--compare` only reads the default paths).

### IN-05: `expand_ask` crashes the run on malformed pad specs

**File:** `scripts/route-probe.py:158-164`

**Issue:** `pad["target_chars"]` / `pad["filler"]` raise bare `KeyError` on
a malformed probe row, and an empty `filler` raises `ZeroDivisionError` in
the repeat computation — aborting the whole run with no probe id context,
unlike `load_probes`, which reports file and line. Risk is low (versioned
data), but the failure mode is needlessly opaque.

**Fix:** Validate `ask_pad` inside `load_probes` (or wrap per-probe
expansion errors in `SystemExit` naming the probe id), matching the
existing invalid-JSON handling.

### IN-06: Bool-level fold maps every YAML-bool spelling to on/off (new in re-review)

**File:** `strands_code_cli/routing.py:224-227`

**Issue:** The GAP-01 fold (`08d6d4a`) maps `True`/`False` to
`"on"`/`"off"`, but `yaml.safe_load` (`routing.py:364`) folds every
YAML 1.1 bool spelling — `yes`/`no`, `true`/`false`, `y`/`n` as well
as `on`/`off` — so a level spelled `yes` silently becomes `"on"` and
`no` becomes `"off"`. The parser discards the original spelling, so
the fold cannot distinguish them. Risk is negligible (level
vocabularies are `low`/`high`/`auto`-shaped; a `yes`/`no` level name
is implausible) and the gate/parser stay consistent
(`_candidate_skip_reason` accepts the same `(str, bool)` set at
`routing.py:195`, `validate_strategy` shares the gate so its report
stays truthful, and the `is True`/`is False` identity checks correctly
exclude ints like `1`). Flagged only so the lossy corner is on record.

**Fix:** Document that only `on`/`off` spellings round-trip (or quote
anything else) in the strategy docs; no code change required.

---

_Checked but not flagged: threshold-hold verdicts intentionally record zero
usage (pre-existing hold contract, unchanged); `_version_tuple` fails
closed on suffixed versions (conservative, correct); pause/resume ordering
across pre-turn and side hooks matches D-09; `decision_model_for` safely
returns None for synthetic engines (`paused`, `decide`, `resolve`,
`none`); tie-break keeps the argmax on unpriced or equal-priced pairs per
D-14; live engine tests are env-gated plus `integration`-marked and fail
loudly on drift by design._

_Re-review checked but not flagged: the second `isinstance` in
`validate_choice_answer` is redundant post-shape-check but harmless;
the doubled `if engine == "local"` in `cmd_run` is trivially
mergeable but clear; new tests (`TestUnhashableChoiceHolds`,
`TestBoolLevelNormalization`, incl. the YAML round-trip) assert
directly on return values with no flaky patterns._

_Reviewed: 2026-10-12T07:34:08Z (re-review; full review 2026-10-12T07:01:22Z)_
_Reviewer: gsd-code-reviewer (generic-agent workaround — typed gsd-code-reviewer dispatch unavailable in this runtime)_
_Depth: standard_
