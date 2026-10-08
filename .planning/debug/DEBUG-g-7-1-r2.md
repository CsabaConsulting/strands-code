# DEBUG G-7-1-R2: idle side approval hidden until next turn, unservable at idle, silently dropped on exit

- gap: G-7-1-R2 (round 2, test 1, severity high)
- truth: "An idle side approval is visible and servable at idle — never hidden until the next turn, never silently dropped on exit (D-11)"
- status: ROOT CAUSE FOUND (read-only investigation; no source edits)
- scope note: G-7-1a mechanism CONFIRMED WORKING in R2 (nesting refcount holds the session pump; request enqueues, no self-deny, next turn serves a tagged dialog). This gap rejects the bounded-wait UX contract itself, not the mechanism.

## Symptoms (user-observed)

1. Side approval queued while idle stayed invisible until an unrelated second turn was SUBMITTED with Enter (not while typing) — "had I waited 24h it would hide for a day"; looked stuck/gone.
2. No idle affordance to serve a queued approval without typing a dummy turn.
3. Exit path cancels the parked side during shutdown join with no transcript note — side work silently dropped.

## Reasoning checkpoint

```yaml
reasoning_checkpoint:
  hypothesis: "All three symptoms are structural consequences of the D-11 bounded-wait fallback: the main thread parks in a blocking sync prompt_toolkit prompt at idle, so nothing observes or serves the broker queue until the prompt returns a line or the session exits."
  confirming_evidence:
    - "_drain_idle_btw (only BTW_IDLE_APPROVAL print site) runs exclusively after the idle prompt returns (loop.py:1542) or at exit (loop.py:1760)"
    - "Empty input continues at loop.py:1540-1541 BEFORE the drain at 1542 — even pressing Enter on an empty line announces nothing"
    - "All req.run_prompt() serve sites live inside turn pumps; at idle the main thread is inside session.prompt() (loop.py:1535), which owns the terminal"
    - "Exit cancels the live side (loop.py:1761-1764) with no transcript note; the drain at 1760 can print 'will prompt when the next turn starts' immediately before the cancel kills it"
  falsification_test: "Find any main-thread execution path that runs while session.prompt() is blocked (a watcher thread, an async prompt task, a key binding) — none exists; or find a BTW_IDLE_APPROVAL print reachable during the idle wait — the sole print is loop.py:727 inside the drain."
  fix_rationale: "Fixes must either observe/serve the queue while the prompt is open (multiplex, watcher, key binding) or move announce/serve to code that runs at the turn boundary and exit — the blocked prompt is the root cause, not the broker or the latch."
  blind_spots: "Live-TTY behavior of prompt_toolkit suspend/re-issue not re-probed here (no TTY in this environment); G-7-1-R2b input-lag interplay with streaming churn not investigated."
  candidate_causes:
    - "code: drain/serve sites unreachable while the sync idle prompt blocks (loop.py:1535 vs 1542)"
    - "config: bounded-wait fallback shipped per 07-03 spike without an idle-serve affordance (design gap, not misconfig)"
  and_gate: "No — single structural cause (blocked main thread at idle) explains all three symptoms; symptom 3 adds a missing-transcript-note defect at the exit site."
```

## Per-symptom root cause

### S1 — queued idle approval invisible until next turn submitted

**Root cause: the only announce print is structurally unreachable during the idle wait.**

- `BTW_IDLE_APPROVAL` text lives at `strands_code_cli/btw.py:60`; its SOLE print site is `strands_code_cli/loop.py:727`, inside `_drain_idle_btw` (`loop.py:693-730`).
- `_drain_idle_btw` has exactly two call sites: `loop.py:1542` (after the idle prompt returns a line) and `loop.py:1760` (exit path). Its own docstring (`loop.py:700-708`) says it "runs when the idle prompt returns a line and once on session exit."
- The idle prompt is the blocking sync call `text = session.prompt("> ")` at `loop.py:1535` inside `output_context()`. While the user idles, the main thread is parked inside prompt_toolkit; the side worker's `broker.request()` enqueues on the worker thread (`policy_gate.py:312-313`, pumping held by the session pump via the G-7-1a refcount `policy_gate.py:254-277`), and nothing on the main thread polls `broker.has_pending` (`policy_gate.py:341-349`) until the prompt returns.
- Typing cannot trigger it (prompt not yet returned); only submitting a non-empty line does. Worse, empty input `continue`s at `loop.py:1540-1541` BEFORE the drain at `loop.py:1542`, so even pressing Enter on an empty line announces nothing.
- Secondary gap: no turn-boundary announce exists either. After `_invoke_agent` returns (`loop.py:1635-1642`) and usage prints, control flows back to the blocking prompt with no `has_live and has_pending` check — an approval already queued at main-end is equally silent.

**Verdict:** not a timing flake or latch bug — the latch (`btw.approval_announced`, `btw.py:316`, set `loop.py:728`, re-armed `loop.py:729-730`) works as designed; the print is simply downstream of a blocking call. Any idle duration hides the notice for that whole duration.

### S2 — no idle affordance to serve a queued approval

**Root cause: every serve site requires a running turn; at idle the terminal is owned by the blocking prompt.**

- Serving = `req.run_prompt()` — sync `radio_choice` via prompt_toolkit `.run()` (`choice.py:146-177`, `.run()` at `:172`). All serve sites are inside turn pumps (`_pump_parallel` sites per G-7-2, plus the `_invoke_agent` pump loop `loop.py:684-687`).
- At idle, the main thread is inside `session.prompt()` (`loop.py:1535`). A second prompt_toolkit app (the approve dialog) cannot run concurrently on the same thread, and there is no code path that suspends/yields the idle prompt: no `prompt_async` task, no key binding, no `/approve`-style idle command, no watcher thread. The session pump stays *entered* (entered `loop.py:1495-1497`, exited `loop.py:1768-1769`) so requests enqueue safely — but nothing serves them until the next turn's pump starts, which requires submitting a line.
- Why bounded-wait shipped this way: D-11's PRIMARY was `prompt_async` multiplex (idle prompt multiplexed against `broker.poll`); the 07-03 timeboxed spike rejected it — probe 1 showed the serve path (`req.run_prompt()` is sync via `radio_choice`) cannot run *inside* the multiplex loop thread, and with no live TTY the prompt suspend/re-issue dance could not be validated at all (`07-03-SUMMARY.md:119-120,139,151`). Per resolved item 4 the fallback shipped: wait for the next turn's pump with a one-time transcript announcement. The spike disproved "serve inside the loop", not "suspend prompt, serve sync on main thread, re-issue prompt" — see fix options.

**Verdict:** the fallback delivered half its contract (queue safely) and deferred the other half (announce promptly, serve at idle). The missing piece is any mechanism that yields the idle prompt.

### S3 — exit silently drops the parked side

**Root cause: the exit path cancels without a transcript note, and can announce-then-kill.**

- `loop.py:1756-1766`: `_drain_idle_btw(...)` at `:1760`, then `btw_session.cancel_event.set()` at `:1762` and `side_pool.shutdown(wait=True)` at `:1764`. No print names the dropped side question or its state (running vs parked on an approval). The in-code comment (`loop.py:1756-1759`) acknowledges D-11's never-cut rule "yields to a clean exit" — but yields silently, violating D-12's no-silent-drop rule (`07-CONTEXT.md:29`) and the transcript-first UX.
- Actively misleading sub-case: if the side is parked on an approval at exit, the drain at `:1760` prints `BTW_IDLE_APPROVAL` ("will prompt when the next turn starts") and the very next lines cancel the side — a promise made and broken within microseconds.

**Verdict:** small, independent defect at a single site; fixable without touching the idle architecture.

## Fix-shape options (ranked)

### Quick win A — turn-boundary announce (fixes S1-at-boundary only; ~10 lines)

At the top of the idle loop (before `session.prompt("> ")`, `loop.py:1526-1535`) or right after the turn result handling, if `btw_session.has_live and broker.has_pending and not btw.approval_announced`: print `BTW_IDLE_APPROVAL` (or a richer variant naming the side question) and set the latch. Optionally move the `_drain_idle_btw` call at `loop.py:1542` above the empty-input `continue` at `loop.py:1540` so empty-Enter also announces.
- D-11: fully compatible — transcript-only, no lifecycle change; bounded-wait letter unchanged.
- Limitation: approvals arriving *mid-idle* still hide until next submit. Partial fix; pair with C or D.

### Quick win B — exit-path transcript note (fixes S3 fully; ~10 lines)

In `loop.py:1760-1766`: before `cancel_event.set()`, if `btw_session.has_live`, print a fenced/note line naming the question (`btw.live_question`) and state (`broker.has_pending` → "waiting on approval", else "still running"), e.g. `Side answer dropped on exit — "<question>" (was waiting on approval).` Suppress or reword the `BTW_IDLE_APPROVAL` print when it fires from the exit-path drain (pass a flag or check `has_live` after reap) so exit never promises a next turn.
- D-11: compatible — the never-cut rule already yields at exit per the in-code comment; this makes the yield visible per D-12. No lifecycle change.

### Full fix C — explicit idle-serve affordance: serve on empty-Enter or key binding (fixes S2 without async; medium)

- Variant C1 (empty-Enter serves): move drain above the empty check; when idle with `has_live and has_pending` and the user submits an empty line, serve one request inline on the main thread (`req = broker.poll(); req.run_prompt()` — legal: main thread, no prompt open at that instant, session pump entered) instead of `continue`. Announce this in the S1 notice text ("press Enter to serve it").
- Variant C2 (key binding): add a PromptSession key binding (e.g. F2/Ctrl-O) that aborts the prompt with a sentinel; the loop catches the sentinel, serves the queued approval sync on the main thread, then re-issues the prompt (preserving the buffer via `default=`). No nested prompt_toolkit apps — strictly sequential.
- D-11: compatible — serving the side's approval at idle *is* the D-11 primary's intent ("lands when ready, even at the idle prompt"); lifecycle unchanged, only the serve site moves earlier. Bounded-wait's "never a lost prompt" guarantee is preserved (request stays queued until served or cancelled).
- Risk: C1 overloads empty-Enter (currently a no-op); C2 needs prompt_toolkit binding care (must not fire mid-turn — the idle session object is turn-free, so scope is clean).

### Full fix D — watcher-thread live announce (fixes S1-mid-idle visibility; medium, pairs with C)

A daemon thread (or piggyback on the side-pool monitor) polls `broker.has_pending` during idle and prints the notice through the active `output_context` proxy — the same "streams above the prompt line" shape the outliving side already uses (`loop.py:1530-1533`). Visibility without yielding the prompt; servability still needs C (or E).
- D-11: compatible — transcript-only. Must respect the announce-once latch across threads (latch is currently main-thread-only; needs a lock or atomic handoff).
- Risk: thread-print interleaving against an open prompt — but this is exactly the already-shipped D-11 idle-streaming shape, so precedent exists.

### Full fix E — revisit D-11 multiplex primary: `prompt_async` + FIRST_COMPLETED (fixes S1+S2 completely; large, needs live TTY)

Run the idle prompt as `prompt_async`, `asyncio.wait(FIRST_COMPLETED)` against a broker-poll coroutine; on approval arrival, cancel the prompt future, run the sync `radio_choice` dialog on the main thread *after the loop quiesces* (sequential, not nested), then re-issue the prompt with the preserved buffer.
- What the 07-03 spike actually proved: probe 1 disproved serving *inside* the multiplex loop thread (sync dialog + running loop = `run_async never awaited`); probe 2 validated the FIRST_COMPLETED plumbing with stand-ins. The suspend→serve-sync→re-issue dance was NEVER disproved — it was unvalidated for lack of a live TTY (`07-03-SUMMARY.md:151`). The primary is revivable in this sequential shape, but the TTY validation gap that killed it still gates it: needs a live-terminal spike before committing.
- D-11: this *is* the D-11 primary — full compatibility by definition.
- Risk: highest complexity; prompt_toolkit app teardown/re-issue edge cases (terminal state, buffer restore, Ctrl-C during handoff); G-7-1-R2b input-lag evidence suggests prompt_toolkit + concurrent streaming already strains — multiplex adds more concurrency surface.

**Recommended sequencing:** A + B now (cheap, no architecture risk, fixes S3 and the common S1 case) → C1 or C2 (real idle servability without async) → D if mid-idle visibility still bites → E only if C's explicit-gesture UX is rejected in UAT.

## D-11 compatibility summary

| Option | D-11 verdict |
|---|---|
| A turn-boundary announce | Compatible (transcript-only) |
| B exit note | Compatible (makes the documented exit-yield visible; satisfies D-12) |
| C idle-serve affordance | Compatible (serve site moves earlier; lifecycle untouched) |
| D watcher announce | Compatible (transcript-only; needs latch thread-safety) |
| E multiplex revisit | IS the D-11 primary (sequential suspend/serve/re-issue shape; spike never disproved it) |

None of the options cut, pause, or rebuild side runs; the session-scoped `BtwContext` and nesting refcount are untouched. The outliving-main non-approval path (fenced idle landing) is unaffected by all options.

## Regression-test sketches

1. `test_turn_boundary_announces_live_pending_approval` (A): fake agent + `BtwContext` with attached live future + broker with one enqueued req; call the new boundary-announce helper; assert `BTW_IDLE_APPROVAL` printed once and latch set; call again → no second print; clear queue → latch re-armed.
2. `test_empty_enter_drains_at_idle` (A/C1): drive the idle-loop slice with `text=""`, live side + pending req; assert drain ran (announce printed) rather than bare `continue`.
3. `test_idle_serve_serves_queued_approval` (C1/C2): idle state + one queued req with stub prompt fn; invoke idle-serve branch; assert stub ran on main thread, `wait_answer` unblocked, `has_pending` False.
4. `test_exit_notes_dropped_side` (B): live side + pending req; invoke exit-drain sequence; assert transcript contains the question and "waiting on approval"; assert `BTW_IDLE_APPROVAL` ("next turn") NOT printed on the exit path.
5. `test_exit_completed_side_no_drop_note` (B boundary): done-unreaped live future, empty queue; exit drain lands it (history + metrics) with no drop note.
6. `test_watcher_announce_once` (D, if built): start watcher with pending req; assert exactly one notice across 3 poll windows; drop req → re-enqueue → asserts second-episode notice.
7. `test_multiplex_serves_at_idle_live_tty` (E, pty-only marked): pty-driven idle prompt + worker-enqueued approval; assert dialog appears without submitting a turn and prompt buffer survives re-issue. Cannot run headless — same TTY gate as the 07-03 spike.
