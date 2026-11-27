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
  `primary: local` routes an ask through a real Ollama daemon over
  `/v1/systemone` (needs a decision-capable pull such as `tev1:0.8b`):
  expects a `Routed →` line with measured latency, a served turn, and
  `/cost` showing `via local` with zero decision spend and no hold.
- **r3** — Phase 8 end-to-end on Bedrock: decision via the live decisions
  catalog's cheapest id, routed turn served with both confidences on the
  `Routed →` line, `/cost` Routing entry with reported spend; then
  `/route off` suppresses routing for a turn and `/route on` restores it.
- **r4** — Phase 8 live `/btw` side ask: mid-turn spawn routes through
  the shared strategy, expects a `Routed (btw)` line and a side-flagged
  `/cost` Routing entry.
- **u1** — Phase 13 Bedrock unary tool mode: boots built-in `_NO_STREAMING_TOOLS`
  model `mistral.mistral-large-2402-v1:0` with no capability override, asserts
  the `streaming=False` unary launch note, executes a live unary `Converse`
  `read` tool turn end-to-end (`UNARY_TOOL_SENTINEL_13`), and verifies
  `/model` toggles between Nova 2 Lite (silent) and Pixtral Large 25.02 (unary
  note).
- **u2** — Phase 13 cross-family resume + SDK `model_info`: boots on
  Sonnet 4.6 (with `MEMORY.md` `InjectedBlock`), verifies `1M` `/context`
  window, computes `17 * 23`, flushes session, resumes via `--session-id`
  on Nova 2 Lite (confirming `#5166` wire compatibility + recall + `1M`
  `/context`).
- **u3** — Phase 13 live `PolicyGateHandler`: approves one `shell` command
  interactively via `Approve? [main] shell` (`Up` + `Enter`), triggers a `[deny]`
  rule refusal (`DENIED: Denied by policy rule ...`) without prompting, and runs
  `/mode plan` confirming no file mutation or prompt.
- **g1** — Phase 14 zero-AWS Google Gemini launch: strips AWS env vars,
  launches `--model google/gemini-3.8-flash` under isolated
  `XDG_CONFIG_HOME`, verifies `config.yaml` is absent prior to `/model`,
  checks `1M` `/context`, runs a `read` tool turn (`GEMINI_SENTINEL_14`),
  checks `/cost` (`$` + `Display only`), and switches to
  `/model google/gemini-4-hydrogen`.
- **o1** — Phase 15/16 zero-AWS native OpenAI launch: strips AWS env vars,
  launches `--model openai/gpt-6.2-sol` under isolated `XDG_CONFIG_HOME`,
  verifies `config.yaml` stays absent prior to `/model`, checks `1.05M`
  `/context`, runs a `read` tool turn (`OPENAI_SENTINEL_15`), checks `/cost`
  (`$` + `Display only`), and switches to `/model openai/gpt-6.1-terra`.
- **an1** — Phase 15 zero-AWS native Anthropic launch: strips AWS env
  vars, launches `--model anthropic/claude-sonnet-5-5` under isolated
  `XDG_CONFIG_HOME`, verifies `config.yaml` stays absent prior to `/model`,
  checks `1.00M` `/context`, runs a `read` tool turn
  (`ANTHROPIC_SENTINEL_15`), checks `/cost` (`$` + `Display only`), and
  switches to `/model anthropic/claude-haiku-5-5`.
- **m1** — Phase 16 zero-AWS Meta Model API launch: strips AWS env vars,
  launches `--model meta/muse-spark-1.3-contributor` under isolated
  `XDG_CONFIG_HOME`, verifies `config.yaml` stays absent prior to `/model`,
  checks `1.05M` `/context`, runs a `read` tool turn (`META_SENTINEL_16`),
  checks `/cost` (`$` + `Display only`), and switches to
  `/model meta/muse-ember-1.0`.

## Usage

Requires `tmux`, `uv`, and model credentials in the environment (`r2`
also needs an Ollama daemon ≥0.35 with a decision-capable pull; `u1`/`u2`/`u3`
use Bedrock credentials and isolate their config under `XDG_CONFIG_HOME`
in `/tmp/uatr8/`; `g1` needs `uv sync --extra gemini` plus `GOOGLE_API_KEY`
or `GEMINI_API_KEY` with zero AWS credentials; `o1` needs `uv sync --extra openai`
plus `OPENAI_API_KEY`; `an1` needs `uv sync --extra anthropic` plus
`ANTHROPIC_API_KEY`; `m1` needs `uv sync --extra meta` plus `MODEL_API_KEY`
or `META_API_KEY` — all with zero AWS credentials):

```sh
cd /tmp && python3 /path/to/scripts/uattest/driver.py s1 --runs 2
cd /tmp && python3 /path/to/scripts/uattest/driver.py s2
cd /tmp && python3 /path/to/scripts/uattest/driver.py r1
cd /tmp && python3 /path/to/scripts/uattest/driver.py r2
cd /tmp && python3 /path/to/scripts/uattest/driver.py r3
cd /tmp && python3 /path/to/scripts/uattest/driver.py r4
cd /tmp && python3 /path/to/scripts/uattest/driver.py u1
cd /tmp && python3 /path/to/scripts/uattest/driver.py u2
cd /tmp && python3 /path/to/scripts/uattest/driver.py u3
cd /tmp && python3 /path/to/scripts/uattest/driver.py g1
cd /tmp && python3 /path/to/scripts/uattest/driver.py o1
cd /tmp && python3 /path/to/scripts/uattest/driver.py an1
cd /tmp && python3 /path/to/scripts/uattest/driver.py m1
```

Output lands in `/tmp/uatr4/`. Timing knobs (start wait, key spacing) are
constants at the top of `uattest_lib.py`; tune per model speed. Live runs cost
real model calls — use the cheap default model.

## Notes

- Transcripts (`*.log`) are run artifacts: do not commit them.
- The rig needs a real terminal-capable pexpect child; it does not run
  under `pytest` or in CI.
