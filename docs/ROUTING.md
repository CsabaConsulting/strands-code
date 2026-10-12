# Model Routing

Per-ask model and thinking-budget routing via a cheap decision model (MODEL-03).
Routing is off until a strategy is configured — without one the CLI behaves
exactly as before.

## Concepts

- **Strategy**: a candidate model set plus freeform scenario directives
  (for example "trivial asks go cheap, deep refactors go big"). Lives globally
  (`~/.config/strands-code/routing.yaml`) or per repo (`./.agent/routing.yaml`);
  the repo file wins whole-file on conflict.
- **Decision calls**: before each ask, at idle, the CLI makes up to two
  sequential decision calls — first a model `choice` over the candidates,
  then an effort `choice` over only the picked model's levels.
  Single-candidate strategies skip the model call but still ask the
  effort question. Each call carries your directives, the candidate
  criteria prose, and the current ask text only (truncated) — never
  history, tool results, or file contents. Prices and windows never
  enter the call; the model judges, code computes.
- **Engines**: true Decision APIs only — OpenRouter
  `/api/alpha/decisions`, a local Ollama daemon (`/v1/systemone`,
  needs Ollama ≥0.35 plus a decision-model pull), and the native
  TypeSafe engine (`POST https://api.typesafe.ai/v1/systemone`,
  keyed by env-only `TYPESAFE_API_KEY`, pinned to `jev-1.13.0`).
  The chain follows your ordered engines list, then holds the
  current model — no heuristic ever picks a model, and a short ask
  can still mean deep work.
- **Gate**: a `confidence_threshold` knob holds the current model when
  the top pick's probability falls below it (retrying next ask); only
  the model confidence gates — a weak effort read still routes.
- **Override**: a manual `/model` switch always wins over routing (it warns
  and offers cancel first); routed switches never fire mid-turn.
- **Visibility**: every routed ask prints one `Routed →` line (choice,
  both confidences, `~$/ask` delta); `/cost` carries the compact Routing
  entry including reported decision spend. `quiet: true` suppresses the
  routine line only — hold and failure notes always print.
- **Tie-break**: when the top two probabilities fall within the
  `tie_margin` knob, code substitutes the cheaper candidate per live
  prices and notes it on the line.

## Quick start

1. Run `/route setup` and follow the guided flow: scope, an ordered
   engines list, candidate picks from the live OpenRouter chat catalog,
   model ids for the listed engines only (an explicit decision-model
   choice from the separate decisions catalog, your Ollama tag, the
   pinned Jev list), then your directives. Setup proposes an order
   from availability — native first when the TypeSafe key is present,
   else OpenRouter then local — and the native engine stays hidden
   until the key exists; an empty line accepts the proposal.
2. Run `/route validate` to check the written file.
3. Ask normally — each ask routes pre-turn. `/route off` disables routing for
   the session; `/route on` re-enables it; `/route status` reports the toggle
   plus the winning strategy file.

## Native engine

The native engine talks to TypeSafe's System One API directly instead
of through OpenRouter. It joins the ordered engines list like any
other engine; a listed native link with no `TYPESAFE_API_KEY` is
skipped with a one-line note, printed once per session (set
`skip_notes: false` to suppress it — the note prints even under
`quiet`, like hold notes).

`/route validate` live-pings the native engine with a cheap decision
call whenever native is listed and the file is otherwise valid. A
served ping appends `native: engine ok` naming the serving snapshot;
a rejected key (401/403) or an unknown model string (400) fails the
report with a fix line; transport failures append a warning leaving
validity unchanged, and a missing key skips the ping the same way.

Native spend is computed code-side from the reported input tokens at
the published flat rate ($0.042 per 1M input, output free) and
renders inline on the `/cost` routing line, folding into the session
totals; the `Prices:` provenance line marks it `native computed input
rate` since the API never reports spend itself. A native call never
renders as silent $0.

Calibration shares the 0.62/0.04 knobs and the shared baseline unless
probes prove divergence — same Jev model, different transport, so
identical verdicts are expected. A native-vs-OpenRouter verdict
disagreement is investigated as a bug, never resolved by preferring
either side.

Native model ids are full-semver or alias only: `jev-1.13.0` is the
pin, `jev-latest` is the explicit opt-in alias (it drifts — every
verdict logs the serving snapshot so moves stay visible).
Minor-only (`jev-1.13`) and prefixed (`typesafe/jev-1.13`) forms are
invalid on native and 400; use the pin.

## Example strategies

Starting points only — model ids and prices drift. Each example carries the
date it was written; run `/route setup` to enumerate the live catalog and
`/route validate` after any manual edit.

Cheap default — two candidates with criteria prose behind one decision model:

```yaml
# Example: cheap default — written 2026-10-12. Starting point only; run
# /route setup for live ids, then /route validate.
candidates:
  - id: bedrock/us.amazon.nova-micro-v1:0
    tier: small
    criteria: Cheapest small model for trivial asks and one-liners.
    levels: [low]
  - id: bedrock/anthropic.claude-haiku-4-5-20251001-v1:0
    tier: mid
    criteria: Mid-size model for everyday feature work and debugging.
    levels: [low, high]
directives: >-
  Trivial asks go cheap; deep refactors go big.
  Judge the ask, not its length: short asks can still need depth.
# Gate knobs (current defaults; omit either to inherit it).
tie_margin: 0.04
confidence_threshold: 0.62
engine:
  primary: openrouter
  # Decisions-catalog id — pick from /route setup, never an alias.
  decision_model: typesafe/jev-1.13
```

Single-candidate local file — the model call is skipped, effort still asks:

```yaml
# Example: single-candidate local file — written 2026-10-12. Starting
# point only; run /route setup for live ids, then /route validate.
candidates:
  - id: bedrock/anthropic.claude-haiku-4-5-20251001-v1:0
    tier: mid
    criteria: Everyday model; the effort question still runs each ask.
    levels: [low, high]
directives: >-
  Single candidate: the model call is skipped but the effort choice
  still asks how much thinking each ask needs.
engine:
  primary: local
  local_model: nimble
  # Unused while primary is local; kept so flipping primary needs no edit.
  decision_model: typesafe/jev-1.13
```

## Manual edits

Manual file edits are allowed and expected — the schema is plain YAML:

- Top level: `candidates` (list, at most 26), `directives` (string),
  `engine` (mapping), `quiet` (true/false), `tie_margin` and
  `confidence_threshold` (0..1 numbers; omit to inherit the defaults).
  Unknown top-level keys are ignored with a warning.
- Each candidate needs `id` plus optional `tier`, `note`, `levels`,
  `criteria`, and `benchmarks`. `criteria` is the prose the decision
  call judges (cost words like "cheapest" plus role notes); without it
  the note, tier, or bare id stands in. Unknown keys skip that entry
  only — `/route validate` reports the skip reason with a fix.
- `levels` should use the harness effort names (`low`, `medium`, `high`,
  …); a routed level the model cannot serve holds the current model instead
  of coercing down. A picked candidate with no levels holds — advertise at
  least one level per candidate.
- `benchmarks` is a user-editable snapshot (`swe_verified`, `lmarena_coding`,
  `aa_index`) stamped with a `pulled:` date; live prices come from the
  catalog at decision time, never from the snapshot.
- `engine.primary` is `openrouter`, `local`, or `off` (`off` disables
  routing). `decision_model` must be a decisions-catalog id (never an
  alias); `local_model` names your Ollama tag when `primary` is `local`
  (`nimble` is the default tag). `local_base_url` optionally re-points a
  non-loopback daemon. New files use the ordered shape instead:
  `engine.order` lists engines in try order (`native`, `openrouter`,
  `local`), `native_model` carries the pinned Jev id when native is
  listed, and `skip_notes` (true/false, default true) governs the
  keyless-skip note. An explicit `order` wins over `primary`.
- Repo wins whole-file over global; delete or fix the repo file to fall back.
- Re-run `/route validate` after every manual edit — it judges the real file.

## Keys

Strategy files never hold keys. The OpenRouter key is runtime-supplied via
`OPENROUTER_API_KEY` (read at call time, sent header-only, never logged);
the native key is runtime-supplied via `TYPESAFE_API_KEY` under the same
posture; the local daemon uses `OLLAMA_HOST` with no key on loopback.
Guided setup never prompts for keys and drops any `api_key`-shaped key
it finds.

## Troubleshooting

- `/route validate` names the winning source file and one line per candidate
  (`ok` or the skip reason), the gate knobs, the engine checks (the decider
  is judged against the cached decisions catalog — run `/cost refresh`
  first), and the directives note — each failure class carries a
  manual-edit fix.
- A corrupt repo file falls back to the global file with a warning; validate
  reports the fallback so the broken file gets fixed, not silently skipped.
- Decision calls that fail hold the current model and retry next ask; the
  hold note names the engine and cause (`Routing held on … (openrouter
  503; retrying next ask)`). Below-threshold picks hold with both numbers
  named; an all-unreachable ask pauses routing for the turn instead.
