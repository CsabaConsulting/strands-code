# Live-model UAT rig (tmux + pexpect)

Scripted, live-model confirmation for flows that hermetic pytest cannot cover
(real model latency, real dialog rendering, real Ctrl-C timing). Built during
Phase 7 for the `/btw` side channel; reusable for later phases.

## Scenarios

- **s1** — `/btw` with a tool call while a long main task streams: expects
  interleaved approval dialog, fenced `[btw] ... [/btw]` result after the
  main task completes, no orphan dialogs.
- **s2** — Ctrl-C during a quiet phase → chooser → `Side answer`: expects
  `Cancelled by user`, no orphan dialogs, clean REPL return.
- **r1** — Phase 8 guided `/route setup` (repo scope) against the live
  OpenRouter catalog: expects live prices in the candidate radio, a saved
  strategy round-tripping the enumerated id with no key material, and
  `/route validate` reporting VALID.
- **r2** — Phase 8 local engine: hand-written strategy with
  `primary: local` routes an ask through a real Ollama daemon (needs
  `qwen3:1.7b` pulled): expects a `Routed →` line with measured latency,
  a served turn, and `/cost` showing `via local` with no hold.
- **r3** — Phase 8 end-to-end on Bedrock: decision via the live catalog's
  cheapest structured id, routed turn served, `/cost` Routing section
  with real decision tokens; then `/route off` suppresses routing for a
  turn and `/route on` restores it.
- **r4** — Phase 8 live `/btw` side ask: mid-turn spawn routes through
  the shared strategy, expects a `Routed (btw)` line and a side-flagged
  `/cost` Routing entry.

## Usage

Requires `tmux`, `uv`, and model credentials in the environment (`r2`
also needs an Ollama daemon with structured-output support):

```sh
cd /tmp && python3 /path/to/scripts/uattest/driver.py s1 --runs 2
cd /tmp && python3 /path/to/scripts/uattest/driver.py s2
cd /tmp && python3 /path/to/scripts/uattest/driver.py r1
cd /tmp && python3 /path/to/scripts/uattest/driver.py r2
cd /tmp && python3 /path/to/scripts/uattest/driver.py r3
cd /tmp && python3 /path/to/scripts/uattest/driver.py r4
```

Output lands in `/tmp/uatr4/`. Timing knobs (start wait, key spacing) are
constants at the top of `driver.py`; tune per model speed. Live runs cost
real model calls — use the cheap default model.

## Notes

- Transcripts (`*.log`) are run artifacts: do not commit them.
- The rig needs a real terminal-capable pexpect child; it does not run
  under `pytest` or in CI.
