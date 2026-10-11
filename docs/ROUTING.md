# Model Routing

Per-ask model and thinking-budget routing via a cheap decision model (MODEL-03).
Routing is off until a strategy is configured — without one the CLI behaves
exactly as before.

## Concepts

- **Strategy**: a candidate model set plus freeform scenario directives
  (for example "trivial asks go cheap, deep refactors go big"). Lives globally
  (`~/.config/strands-code/routing.yaml`) or per repo (`./.agent/routing.yaml`);
  the repo file wins whole-file on conflict.
- **Decision call**: before each ask, at idle, the CLI asks a cheap decision
  model to pick one candidate plus a thinking level. The prompt carries your
  directives, one candidate-table line per model, and the current ask text only
  (truncated) — never history, tool results, or file contents.
- **Engines**: the OpenRouter chat-completions API is the default engine; a
  local Ollama daemon is the alternative. The chain is API, then local, then
  hold the current model — no heuristic ever picks a model, and a short ask
  can still mean deep work.
- **Override**: a manual `/model` switch always wins over routing (it warns
  and offers cancel first); routed switches never fire mid-turn.
- **Visibility**: every routed ask prints one `Routed →` line (model, why,
  cost impact); `/cost` carries the fuller Routing section including
  decision-call spend. `quiet: true` suppresses the routine line only —
  hold and failure notes always print.
- **Tie-break**: when no candidate is clearly better the decision prompt
  prefers staying on the current model.

## Quick start

1. Run `/route setup` and follow the guided flow: scope, engine, candidate
   picks from the live OpenRouter catalog, an explicit decision-model choice,
   then your directives.
2. Run `/route validate` to check the written file.
3. Ask normally — each ask routes pre-turn. `/route off` disables routing for
   the session; `/route on` re-enables it; `/route status` reports the toggle
   plus the winning strategy file.

## Example strategies

Starting points only — model ids and prices drift. Each example carries the
date it was written; run `/route setup` to enumerate the live catalog and
`/route validate` after any manual edit.

Cheap default — two inexpensive candidates behind one decision model:

```yaml
# Example: cheap default — written 2026-10-11. Starting point only; run
# /route setup for live ids, then /route validate.
candidates:
  - id: bedrock/amazon.nova-micro-v1:0
  - id: bedrock/anthropic.claude-haiku-4-5-20251001-v1:0
directives: >-
  Trivial asks go cheap; deep refactors go big.
  Prefer staying on the current model unless another is clearly better.
engine:
  primary: openrouter
  # Example id — replace with a live structured-output-capable id from setup.
  decision_model: openrouter/qwen/qwen3-32b
```

Tiered team file — small/mid/mega tiers with levels and a benchmark snapshot:

```yaml
# Example: tiered team file — written 2026-10-11. Starting point only; run
# /route setup for live ids, then /route validate.
candidates:
  - id: bedrock/amazon.nova-micro-v1:0
    tier: small
    note: Trivial asks, spelling, one-liners.
    levels: [low]
  - id: bedrock/anthropic.claude-haiku-4-5-20251001-v1:0
    tier: mid
    note: Everyday feature work.
    levels: [low, high]
  - id: bedrock/anthropic.claude-sonnet-4-6
    tier: mega
    note: Deep refactors and architecture.
    levels: [medium, high]
    benchmarks:
      # Illustrative values — replace with current leaderboard rows.
      swe_verified: 80.9
      pulled: '2026-10-01'
directives: >-
  Route by depth of thought, not length of ask: one-line questions can still
  need the mega tier. Side (`/btw`) questions stay cheap unless they ask for
  depth. Prefer staying on the current model unless another is clearly better.
engine:
  primary: openrouter
  # Example id — replace with a live structured-output-capable id from setup.
  decision_model: openrouter/qwen/qwen3-32b
```

## Manual edits

Manual file edits are allowed and expected — the schema is plain YAML:

- Top level: `candidates` (list), `directives` (string), `engine` (mapping),
  `quiet` (true/false). Unknown top-level keys are ignored with a warning.
- Each candidate needs `id` plus optional `tier`, `note`, `levels`, and
  `benchmarks`. Unknown keys skip that entry only — `/route validate`
  reports the skip reason with a fix.
- `levels` should use the harness effort names (`low`, `medium`, `high`,
  …); a routed level the model cannot serve holds the current model instead
  of coercing down.
- `benchmarks` is a user-editable snapshot (`swe_verified`, `lmarena_coding`,
  `aa_index`) stamped with a `pulled:` date; live prices come from the
  catalog at decision time, never from the snapshot.
- `engine.primary` is `openrouter`, `local`, or `off` (`off` disables
  routing; the decision model should advertise `response_format` or
  `structured_outputs` support). `local_model` names your Ollama tag when
  `primary` is `local`.
- Repo wins whole-file over global; delete or fix the repo file to fall back.
- Re-run `/route validate` after every manual edit — it judges the real file.

## Keys

Strategy files never hold keys. The OpenRouter key is runtime-supplied via
`OPENROUTER_API_KEY` (read at call time, sent header-only, never logged);
the local daemon uses `OLLAMA_HOST` with no key on loopback. Guided setup
never prompts for keys and drops any `api_key`-shaped key it finds.

## Troubleshooting

- `/route validate` names the winning source file and one line per candidate
  (`ok` or the skip reason), the engine checks, and the directives note —
  each failure class carries a manual-edit fix.
- A corrupt repo file falls back to the global file with a warning; validate
  reports the fallback so the broken file gets fixed, not silently skipped.
- Decision calls that fail hold the current model and retry next ask; the
  hold note names the failed engine.
