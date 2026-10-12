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
  `/api/alpha/decisions` is the default, a local Ollama daemon
  (`/v1/systemone`, needs Ollama ≥0.35 plus a decision-model pull) is
  the alternative. The chain is API, then local, then hold the current
  model — no heuristic ever picks a model, and a short ask can still
  mean deep work.
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

1. Run `/route setup` and follow the guided flow: scope, engine, candidate
   picks from the live OpenRouter chat catalog, an explicit decision-model
   choice from the separate decisions catalog, then your directives.
2. Run `/route validate` to check the written file.
3. Ask normally — each ask routes pre-turn. `/route off` disables routing for
   the session; `/route on` re-enables it; `/route status` reports the toggle
   plus the winning strategy file.

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
  non-loopback daemon.
- Repo wins whole-file over global; delete or fix the repo file to fall back.
- Re-run `/route validate` after every manual edit — it judges the real file.

## Keys

Strategy files never hold keys. The OpenRouter key is runtime-supplied via
`OPENROUTER_API_KEY` (read at call time, sent header-only, never logged);
the local daemon uses `OLLAMA_HOST` with no key on loopback. Guided setup
never prompts for keys and drops any `api_key`-shaped key it finds.

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
