# Phase 8: Model Routing with Decision Models - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-11
**Phase:** 8-model-routing-with-decision-models
**Areas discussed:** Routing scope, Decision engine, Override UX

---

## Routing scope — default posture

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-on (Recommended) | Every ask routed unless disabled or overridden; matches SC1 per-ask selection | ✓ |
| Opt-in per session | Routing off until enabled; safest for distrustful users | |
| Propose + confirm | Router proposes each ask, user confirms before the turn | |

**User's choice:** Auto-on (Recommended)
**Notes:** "Auto-on only if the user already configured a set of models and a strategy for them. Ideally globally, but can be per workspace too. If that's not available then there's not enough information to just turn it on." Raised user directives (scenario→model guidance) and thinking-level routing as config dimensions.

## Routing scope — strategy config shape

| Option | Description | Selected |
|--------|-------------|----------|
| Models + directives (Recommended) | Candidate list + freeform scenario directives interpreted per ask | ✓ |
| Preset strategies | Named presets (cost-saver/balanced/quality-first) + model list | |
| Per-model rules | Structured per-model when/budget/never rules | |

**User's choice:** Models + directives (Recommended)
**Notes:** "Let's not forget about automatic thinking level routing within a model if it is thinking capable."

## Routing scope — /btw side coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Main + side (Recommended) | Side asks route through the same strategy, flagged as side; closes Phase 7 D-07 revisit | ✓ |
| Main turns only | Side keeps the same-model rule | |
| Side pinned cheap | Side always cheapest configured model, no decision call | |

**User's choice:** Main + side (Recommended)
**Notes:** None.

## Routing scope — config level

| Option | Description | Selected |
|--------|-------------|----------|
| Both, repo wins (Recommended) | Global base, workspace override; Phase 3 D-08 precedent | ✓ |
| Global only | One strategy for everything | |
| Workspace only | Each workspace configures its own | |

**User's choice:** Both, repo wins (Recommended)
**Notes:** None.

---

## Decision engine — decision-model path

| Option | Description | Selected |
|--------|-------------|----------|
| Laya via API (Recommended) | Roadmap default: cheap, fast, needs network + key | ✓ |
| Kev | Alternative cheap API model; researcher compares | |
| Self-hosted first | No API dependency; needs local serving, quality TBD | |

**User's choice:** Laya via API (Recommended), redirected
**Notes:** "OpenRouter has a decision model API. Until Bedrock offers decision models we should default to that one. We can support local models as an alternative. OpenRouter will have an ample set of open model selection besides just Kev and Laya, we can enumerate that and offer choices for the user. This could be a guided configuration flow potentially." Decision: OpenRouter decision API default, local alternative.

## Decision engine — fallback inputs

| Option | Description | Selected |
|--------|-------------|----------|
| Directive matching (Recommended) | Match ask against scenario directives by keyword/cues | ✓ |
| Complexity cues | Static cues: length, code-vs-prose, file refs | |
| Cheapest that fits | Cheapest candidate whose window fits | |

**User's choice:** Directive matching (Recommended), with skepticism
**Notes:** "Directive should drive the scenario, but the decision model might factor in length and other complexity cues. Without a decision model I'm not sure if it's possible to estimate with heuristics, because even a short ask could mean a deep thinking work." Later superseded: no heuristic picks models at all (see correction round).

## Decision engine — offline behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Local then heuristic (Recommended) | Local model if configured, else heuristic on static almanac | |
| Routing pauses | Current model holds until connectivity returns | |
| Heuristic only | Heuristic only, never a local model | |

**User's choice:** Freeform — "None of the above"
**Notes:** "Local decision model if configured, otherwise routing pauses (doesn't happen, current model is used)." No heuristic path offline.

## Decision engine — transient failure posture

| Option | Description | Selected |
|--------|-------------|----------|
| Hold current (Recommended) | Turn runs on current model, routing retries next ask | ✓ |
| Directive heuristic | Fall back to directive matching | |
| Ask the user | Prompt for which model to use | |

**User's choice:** Hold current (Recommended)
**Notes:** None.

## Decision engine (correction round) — directives in the call

| Option | Description | Selected |
|--------|-------------|----------|
| Directives always in (Recommended) | Models + directives + stats into every decision call | ✓ |
| Fallback only | Decision model sees ask + stats; directives apply to fallback | |

**User's choice:** Directives always in (Recommended)
**Notes:** Prompted by user challenge: "Does that mean the OpenRouter decision API call won't use the configured directives?" Addition: candidate entries may note models via descriptors (Sol=mega / Terra=mid / Luna=small though all frontier; same Opus-Sonnet-Haiku); "potentially we could pull compound benchmarks for help."

## Decision engine (correction round) — heuristic survival

| Option | Description | Selected |
|--------|-------------|----------|
| Models only (Recommended) | API → local → pause/hold; SC2 fallback is hold-current | ✓ |
| Heuristic last resort | Directive matching as final fallback per SC2 as written | |

**User's choice:** Models only (Recommended)
**Notes:** Prompted by user challenge: "There shouldn't be the fallback to heuristics only, the decision should use a model." SC2 reinterpreted: deterministic hold-current satisfies "deterministic fallback."

---

## Override UX — manual control shape

| Option | Description | Selected |
|--------|-------------|----------|
| Session toggle (Recommended) | Per-session on/off; /model re-points immediately and wins | ✓ |
| Auto/manual modes | Dedicated mode switch | |
| Config file only | Routing controlled only via strategy file | |

**User's choice:** Session toggle (Recommended)
**Notes:** "User is always warned if the model switch would turn off the routing. The user should be able to cancel the switch to favor the routing to continue. If decides to override then there can be a slash command to turn routing back on. Other slash commands might be needed too."

## Override UX — switch prompting

| Option | Description | Selected |
|--------|-------------|----------|
| Silent + note (Recommended) | Switch happens, transcript notes model + why + cost | ✓ |
| Confirm on switch | Announce pick, wait for Enter/decline | |
| Never prompt | Routed switches never prompt; deny-first stays for tools | |

**User's choice:** Silent + note (Recommended)
**Notes:** None.

## Override UX — decision visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Always (Recommended) | One transcript line per routed ask (model, why, cost) | ✓ |
| On change only | Note only when model/budget differs | |
| /cost only | Transcript clean; detail in /cost | |

**User's choice:** Always (Recommended)
**Notes:** "Always, unless the user configures it to be suppressed to decrease noise. Of course /cost will also have details."

## Override UX — strategy setup

| Option | Description | Selected |
|--------|-------------|----------|
| Guided flow (Recommended) | Interactive setup enumerating OpenRouter models + directives | ✓ |
| Manual file | Hand-written strategy file with docs | |
| Example + assist | Commented example; guided flow only for decision model | |

**User's choice:** Guided flow (Recommended)
**Notes:** "Guided flow, but we can also ship example strategies in the documentation and could allow the user to manually modify. We can have a slash command which checks the configuration's validity."

---

## Additional areas round

Offered: Thinking budget, Decision cost, Side mechanics. User declined all ("None of the above") and added a research direction instead: "we could explore pulling compound and detail benchmarks to rank models, this can ultimately help with the routing in the end." Captured in CONTEXT.md Specific Ideas for the researcher.

## the agent's Discretion

Slash names/shapes; strategy file format/paths; transcript + /cost shapes; hold-current notify behavior; descriptor/benchmark schema; side-ask decision-call mechanics.

## Deferred Ideas

- CodeAct action interface (Phase 9).
- Cost budgets/enforcement (locked: display only).
- Heuristic model-picking — rejected, not deferred.
- Fully automatic routing with no override — locked out.

---

# Revisit 2026-10-11 — Decision-API rework

Trigger: true Decision APIs verified live (OpenRouter `/api/alpha/decisions`, Ollama `/v1/systemone`); chat-completions JSON design superseded. Existing D-01..D-13 carried forward unless revised below.

## Judgment split — cost-awareness

| Option | Description | Selected |
|--------|-------------|----------|
| Code tie-break (Recommended) | Model judges fit; code substitutes cheaper on near-ties | |
| Criteria hints | Rough cost words in choice criteria | ✓ |
| You decide | Agent decides | |

**User's choice:** Criteria hints + mash-up
**Notes:** "plus we can mash up code substitutes the cheaper candidate when top probabilities are near-tied" → D-14.

## Judgment split — descriptors

| Option | Description | Selected |
|--------|-------------|----------|
| Out of the call (Recommended) | Benchmarks leave the decision call | |
| Criteria prose | One-line role notes as criteria prose | ✓ |
| You decide | Agent decides | |

**User's choice:** Criteria prose
**Notes:** "These can be pre-computed configuration time, potentially the user can influence or edit them" → D-02 revision.

## Judgment split — cost line

| Option | Description | Selected |
|--------|-------------|----------|
| Keep in code (Recommended) | ~/ask delta computed from almanac | ✓ |
| Drop delta | Session totals only | |

**User's choice:** Keep in code

## Judgment split — tie margin

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed constant (Recommended) | E.g. top two within 5pp | |
| Strategy knob | Tunable tie_margin in strategy file | ✓ |
| You decide | Agent decides | |

**User's choice:** Strategy knob
**Notes:** "and that knob ships with a reasonable default" → D-14.

## Question mapping — effort

| Option | Description | Selected |
|--------|-------------|----------|
| Second choice (Recommended) | Second choice over picked model's levels | ✓ |
| Score | 1-5 depth score, code maps to levels | |
| You decide | Agent decides | |

**User's choice:** Second choice → D-05 revision, D-15.

## Question mapping — directives

| Option | Description | Selected |
|--------|-------------|----------|
| State context (Recommended) | Ask + directives as state data | |
| Instructions | Directives shape question text | |
| Both | State and instructions | ✓ |

**User's choice:** Both → D-07 revision.

## Question mapping — single candidate

| Option | Description | Selected |
|--------|-------------|----------|
| Code fast path (Recommended) | No call; code routes trivially | ✓ |
| Always call | Call for a confidence signal | |

**User's choice:** Code fast path
**Notes:** "But thinking level is still a question at the second level" → D-15.

## Question mapping — sequence

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential (Recommended) | Model call, then effort call with that model's levels | ✓ |
| Single call | Model + union-levels, code validates | |
| You decide | Agent decides | |

**User's choice:** Sequential → D-15.

## Why replacement — routed line

| Option | Description | Selected |
|--------|-------------|----------|
| Choice + confidence (Recommended) | E.g. haiku (high, 94%) | ✓ |
| Top-two spread | Top-two probabilities inline | |
| You decide | Agent decides | |

**User's choice:** Choice + confidence → D-12 revision.

## Why replacement — cost entry

| Option | Description | Selected |
|--------|-------------|----------|
| Compact + spend (Recommended) | Choice + confidence + spend; full table in verbose only | ✓ |
| Full table | Full distribution per ask | |
| You decide | Agent decides | |

**User's choice:** Compact + spend → D-12 revision.

## Why replacement — tie note

| Option | Description | Selected |
|--------|-------------|----------|
| Note it (Recommended) | Substitution visible on the line | ✓ |
| Silent | Final pick only | |

**User's choice:** Note it → D-12 revision.

## Why replacement — effort confidence

| Option | Description | Selected |
|--------|-------------|----------|
| Model only (Recommended) | Effort confidence in /cost only | |
| Both inline | E.g. haiku (high 88%, 94%) | ✓ |
| You decide | Agent decides | |

**User's choice:** Both inline → D-12 revision.

## Confidence policy — low-confidence action

| Option | Description | Selected |
|--------|-------------|----------|
| Hold + retry (Recommended) | Below threshold holds, retries next ask | ✓ |
| Route anyway | Confidence display-only | |
| You decide | Agent decides | |

**User's choice:** Hold + retry → D-08 extension, D-16.

## Confidence policy — threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Strategy knob (Recommended) | Threshold in strategy file with default | ✓ |
| Fixed | One constant for all | |
| You decide | Agent decides | |

**User's choice:** Strategy knob → D-16.

## Confidence policy — gate scope

| Option | Description | Selected |
|--------|-------------|----------|
| Model only (Recommended) | Only model pick must clear | ✓ |
| Both must clear | Model and effort gate | |
| You decide | Agent decides | |

**User's choice:** Model only → D-16.

## Confidence policy — hold note

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct note (Recommended) | E.g. Routing held (confidence 41% < 70%) | ✓ |
| Same as failure | Reuse engine-failure wording | |

**User's choice:** Distinct note → D-16.

## Additional areas round

Offered round two (decision-model selection/pinning, 2–26 choice cap vs candidate scale). User chose "I'm ready for context" — both captured as the agent's Discretion for the researcher/planner.
