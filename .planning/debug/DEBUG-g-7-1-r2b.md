# DEBUG G-7-1-R2b — Mid-turn dialog input lag + phantom repeats

- gap_id: G-7-1-R2b
- truth: "Mid-turn approval dialogs respond to input promptly with no phantom repeats, even while the other agent streams"
- severity: medium
- status: ROOT CAUSE FOUND (static, code-evidenced; live repro still needed to measure, not to confirm mechanism)
- date: 2026-10-07

## Symptoms (user-observed)

1. Approve? dialog: felt an unnecessary queued/duplicate approval (approved twice;
   transcript shows each box once, so swallowed inputs likely forced repeats);
   selector movement very delayed, "swallowing every second input" while main
   streamed around the open dialog.
2. Cancel-which chooser: same lag — cursor moved only every ~3rd keypress, Enter
   needed multiple presses, dialog seemingly repeated.
3. Environment: terminal shows "WARNING: your terminal doesn't support cursor
   position requests (CPR)".

## Root cause

**RC-1 (primary, both symptoms): two threads concurrently read the same stdin fd
during mid-turn dialogs — the steering reader steals the dialog's key bytes.**

- The dialog app reads stdin through its asyncio event loop (`loop.add_reader`
  on fd 0; prompt_toolkit `application.py::read_from_input`).
- The steering reader thread simultaneously `select()`s + `os.read(fd, 4096)`s
  the same fd (`steering.py:354-410`). Whoever wakes first eats all available
  bytes; a multi-byte escape sequence (arrows) split across the two readers is
  garbage on both sides.
- Stolen bytes are *silently* lost: in the dialog's raw mode, arrow keys and
  Enter (`\r`, no `\n`) never complete a line, so they sit forever in the
  reader's `buf` without emitting (`steering.py:407-410`). Textbook "swallowing
  every Nth input".
- Why the reader is awake — two holes in the `gate_open` exclusion:
  - (a) **Chooser path never gated.** Repo-wide search: the ONLY `gate_open`
    set/clear sites are `policy_gate.py:572/579` inside `ask()`. The cancel
    chooser (`loop.py:220-233` `ask_cancel_target`, called from the pump's
    KeyboardInterrupt path) sets nothing, so the reader races the chooser for
    its whole lifetime. Matches the chooser lagging worst (every ~3rd key).
  - (b) **Approve path gate is a non-refcounted Event shared by concurrent
    asks.** Worker A clears it in `ask()`'s `finally` (`policy_gate.py:579`)
    after worker B already set it (`:572`) but before the pump serves B's
    dialog — B's dialog then runs with the reader awake. R2t1 had overlapping
    main+side approvals ("approved twice"); the overlap window (A's post-answer
    `_apply_answer`/prints vs B's ask entry) is wide under two streaming
    workers, not a ~100ns race.
- The pre-existing select→read race guard (`steering.py:380-396`, tested in
  `test_steering.py:255`) covers only the gate *transition*, not a gate that is
  legitimately clear (chooser) or prematurely cleared (overlap).

**RC-2 (phantom repeats): mashed retries leak forward into the next dialog.**

- prompt_toolkit typeahead is keyed `fd-{fileno}` (`input/vt100.py:135-136`) —
  shared across ALL dialogs on stdin — and fed first at the next app start
  (`application.py::run_async` "Feed type ahead input first"). Keys mashed
  during a lagged dialog N (plus kernel-buffered typeahead) auto-confirm
  dialog N+1: "unnecessary queued approval / approved twice / dialog seemingly
  repeated", each box still shown once.

**AND-gate: yes.** RC-1 (loss) forces mashing; RC-2 (forward leak) turns mashed
keys into phantom confirms. Either alone under-explains the report.

## Ruled out / downgraded (with evidence)

- **patch_stdout re-render churn (secondary at most, cannot drop keys).**
  `StdoutProxy._write` buffers until `\n` (no per-token flushes), and callback
  prints are per-message-block (`callback_handler.py:96-137`) — a few
  erase/redraw cycles/sec, each sub-frame for a 4-row dialog, fairly
  interleaved on the asyncio loop. Adds flicker/latency, never loss (the
  parser queues; nothing discards).
- **CPR (explains the WARNING only, not lag).** Input is attached BEFORE the
  CPR request and `wait_for_cpr_responses` runs only post-run
  (`application.py::run_async`); the CPR handshake never blocks key
  processing. One-shot per dialog (fresh output each time, `choice.py:139`) +
  2s background timer (`renderer.py CPR_TIMEOUT`) = the warning line, nothing
  slower.
- **Nested `output_context`** (turn proxy + ask proxy) works as designed;
  dialog output bypasses proxies via `create_output(stdout=sys.__stdout__)`
  (`choice.py:139`).

## Reasoning checkpoint

- hypothesis: Two stdin readers (steering thread + dialog event loop) race
  during mid-turn dialogs because exclusion is missing (chooser) or
  non-refcounted (overlapping asks); losers' bytes drop silently (no `\n` in
  raw-mode keys), and mashed retries auto-confirm the next dialog via
  fd-keyed typeahead.
- confirming_evidence:
  - only gate set/clear sites repo-wide are ask() 572/579; chooser unset
  - reader parks ONLY on gate (steering.py:368,380,418); reader alive whole
    turn (loop.py:1621 start / 1748-49 stop)
  - raw-mode key bytes contain no `\n` → silent buf loss (steering.py:407-410)
  - typeahead shared per fd + fed at next start (vt100.py:135-136)
  - symptom differential: ungated chooser worst (1/3), overlap-gated approve 1/2
- falsification_test: instrumented live repro (below) showing ZERO reader
  consumption during a still-lagging dialog refutes RC-1 → fall back to churn
  instrumentation (run_in_terminal cycles/sec + key-to-render latency).
- fix_rationale: restore the single-reader invariant on stdin during dialogs
  + drain forward-leaking typeahead — addresses loss AND phantoms, not symptoms.
- blind_spots: no live repro run here (read-only, no tty); R2t1 overlap timing
  inferred from "approved twice" + dual approvals, not transcript timestamps;
  kernel-buffer typeahead magnitude unmeasured.
- candidate_causes: code (missing gate on chooser; non-refcounted Event) |
  environment (CPR-less terminal — ruled out as lag cause)
- and_gate: yes (RC-1 + RC-2 combine; see above)

## Fix shapes (ranked by risk)

1. **Gate the chooser (lowest risk).** Set/clear `gate_open` around
   `radio_choice` in `ask_cancel_target`/`_choose_cancel_targets`
   (`loop.py:220-246`), mirroring `ask()`. Must compose with fix 2.
2. **Refcount the guard (low-medium).** Replace the bare Event with a tiny
   reentrant guard (counter + lock, or per-holder tokens) used by `ask()` AND
   the chooser; reader polls `held()`. Closes the overlap window.
3. **Single choke point (medium, most robust).** Acquire the guard inside
   `choice.radio_choice` entry/exit so every current + future mid-turn dialog
   is covered. Guard must live in a cycle-free module (NOT `policy_gate` —
   it lazily imports `choice`; put it in `steering.py` or a new module).
   Boundary/idle dialogs unaffected (reader stopped).
4. **Typeahead hygiene (low risk, do with 1–3).** `clear_typeahead` on dialog
   entry so mashed keys can't auto-confirm the next dialog (kills the phantom
   half). Kernel-buffered bytes remain; `termios.tcflush(TCIFLUSH)` is the
   stronger variant but eats legitimately typed steering — not recommended
   without study.
5. **Not recommended:** stop/restart the reader around dialogs (loses in-flight
   typed lines, join latency); muting streaming during dialogs (kills live
   fences); CPR workarounds (CPR is innocent).

## Regression-test sketch

Hermetic (no tty; pipe patterns exist in `test_steering.py:231-253`):

- Guard unit: two holders acquire; one releases → still held; both release →
  clear. (Needs the guard primitive from fix 2/3.)
- Chooser gating unit: monkeypatch `loop.radio_choice` with a fake asserting
  guard-held during the call (fake pattern exists:
  `test_plan_cancel.py:290-324`).
- Reader-vs-dialog integration: pipe-backed reader (`_PipeStdin`) + guard held
  across a fake dialog window while bytes are written → assert bytes untouched
  until release; overlap case: holder A releases while holder B holds → bytes
  still untouched.
- Typeahead unit: `clear_typeahead` on dialog entry (assert pt buffer empty
  via a dummy/fd input — or assert the call site).

Live (needs pty; also the falsification experiment):

- Instrumentation: wrap `os.read` in `_run_fd` to log (timestamp, nbytes, gate
  state); mark dialog open/close. Repro: mid-turn chooser while the side
  streams + scripted arrows/Enter; overlapping main+side approvals with scripted
  keys. Pass = every keypress reflected (highlight moves, single Enter
  confirms) AND zero reader consumption inside dialog windows. If lag persists
  with zero consumption, RC-1 is refuted → instrument churn instead
  (run_in_terminal cycles/sec, key-to-render latency via invalidate hook).

## Files

- `strands_code_cli/steering.py:354-410` (reader), `:368,380,418` (gate checks)
- `strands_code_cli/policy_gate.py:62,572,579` (gate set/clear — only sites)
- `strands_code_cli/loop.py:220-246` (ungated chooser), `:1621,1748-49`
  (reader lifetime), `:428-500` (pump serve sites)
- `strands_code_cli/choice.py:139,146-177` (dialog; per-dialog fresh output)
- prompt_toolkit 3.0.53: `application.py::run_async`, `input/vt100.py:135-136`
  (fd-keyed typeahead), `patch_stdout.py::StdoutProxy`, `renderer.py`
  (CPR_TIMEOUT=2, one-shot CPR)
