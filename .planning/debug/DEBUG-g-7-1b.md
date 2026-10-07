# DEBUG G-7-1b — Side agent adopts the main task

- gap_id: G-7-1b (phase 07 UAT, test 1, severity high)
- truth: "Side agent answers ONLY the btw question and never continues the main task (D-04/D-09 scope)"
- status: ROOT CAUSE FOUND (read-only investigation; no source edits)
- agent: gsd-debugger (generic-agent workaround)

## Symptoms (user-observed, twice)

1. Main `Write an essay about the history of computers` + btw `list /tmp`: after the
   listing, the side agent issued `python_repl` containing the MAIN essay and rendered the
   essay inside the btw fence (essay rendered twice: main + btw).
2. Main `Run sleep 30 via shell` + btw `list /tmp`: the side agent ran `sleep 30` itself
   (`Approval needed: [btw] shell / Detail: sleep 30`).

## Root cause: CONFIRMED (suspected cause verified + one sharpening)

The fork carries the **in-flight main user turn** (directive, no assistant response yet) and the
framing never forbids performing it, so the model answers the side question and then continues
with the unanswered main directive. Mechanism, end to end:

1. **Spawn-time snapshot includes the live main turn.** The build closure snapshots the parent's
   live history at spawn (`loop.py:572-574`: `history = getattr(agent, "messages", None)` →
   `build_btw_agent(parent_kwargs, list(history), question)`), which runs ~1s into the main turn.
   The current main user message is already in `agent.messages` (SDK appends turn messages as the
   turn proceeds; `agent.py:1885,1898` append chokepoint), with no assistant response yet.
2. **Absorb branch merges main directive + btw question into ONE user message.**
   `fork_btw_history` (`btw.py:168-172`) appends the framed question into the trailing message when
   it is user-role. Mid-turn that trailing message is the raw main directive, so the side prompt's
   final user turn reads as: `[main task text...] + [BTW_FORK_PREAMBLE + btw question]`.
3. **The harness recipe never meets this case — the replication does.** Upstream
   `_with_history` (`subagent.py:399-407`) documents the absorb branch as "A trailing user turn
   (tool results) absorbs the task": harness children spawn from inside a tool call, so a trailing
   user turn is always already-answered tool results. The btw mid-turn spawn is the only flow where
   the absorbed trailing user turn is an **unanswered directive**. `btw.py:140-173` replicates the
   algorithm verbatim (per 07-RESEARCH) without handling this new case.
4. **Neither framing line bounds scope.** `BTW_FRAMING` (`btw.py:63-66`: "answer the trailing btw
   question directly and concisely") names the side task but never says ONLY / do-not-perform-main;
   `BTW_FORK_PREAMBLE` (`btw.py:69-72`: "You are its side channel answering the btw question below
   while the main task continues") implies delegation but never marks the earlier turns as
   read-only context owned by someone else. Combined with `CODE_AGENT_INSTRUCTIONS`
   (`code_agent.py:16-17`: "You are a code agent. You solve tasks..."), the model sees an
   unanswered user directive in its own history and task-completes it after the side question.
5. **Attribution is real, not a rendering leak.** Both symptoms prove the side agent itself acted:
   the `[btw]` approval tag classifies by agent identity (`policy_gate.py:83-91`, any non-main
   agent object → `"btw"`), so `sleep 30` under `[btw]` was issued by the side agent; the essay
   inside the fence passed through the side agent's `FencedBtwHandler` (`btw.py:98-125`). A fence /
   tag misattribution hypothesis is ruled out.

```yaml
reasoning_checkpoint:
  hypothesis: "The side agent adopts the main task because fork_btw_history's absorb branch merges the unanswered in-flight main directive with the framed btw question into one trailing user turn, and BTW_FRAMING/BTW_FORK_PREAMBLE never forbid performing the earlier turns."
  confirming_evidence:
    - "Symptom 2: side agent executed main's `sleep 30` under its own [btw] approval tag (agent-identity classified, policy_gate.py:83-91)"
    - "Symptom 1: side agent generated main's essay via python_repl inside its own fenced handler (btw.py:98-125)"
    - "Spawn snapshot takes live agent.messages mid-turn (loop.py:572-574); only path for main-task text into the side prompt is the fork (btw.py:372)"
    - "Absorb branch merges into trailing user message (btw.py:169-170); upstream docstring assumes trailing user = tool results (subagent.py:400-401), never an unanswered directive"
    - "No ONLY/read-only/do-not-perform language in BTW_FRAMING (btw.py:63-66) or BTW_FORK_PREAMBLE (btw.py:69-72)"
  falsification_test: "If the forked prompt excluded (or context-marked) the in-flight main turn AND framing hardened, yet a live repro still shows the side agent performing the main task, this hypothesis is wrong."
  fix_rationale: "Remove or neutralize the unanswered directive from the side prompt (the cause), not the tools that executed it (the symptom); framing alone is soft, marking/exclusion is structural."
  blind_spots: "Exact agent.messages shape at ~1s into a turn not captured live (SDK-version-dependent); multi-turn history + in-flight toolUse interleavings not traced. Live repro should dump the forked prompt."
  candidate_causes:
    - "code: absorb branch + weak framing (primary, confirmed by evidence above)"
    - "data: prompt content — unanswered directive present in side history (same mechanism, input side)"
  and_gate: "No — single mechanism; both symptoms are the same cause via different tools (python_repl vs shell)."
```

## Candidate fix shapes

### A. Framing hardening (prompt-only) — do regardless

Add an explicit scope boundary to both constants: answer ONLY the trailing btw question; all
earlier user turns are read-only context owned by the main agent, which is handling them — never
perform, continue, or anticipate them; end the turn when the side question is answered.

- Reversibility: trivial (string change).
- D-13 compatibility: full (shared history untouched).
- Weakness: soft control; task-completion bias already overrode the current framing twice.

### B. Mark the in-flight main turn as context-only (recommended, with A)

In `fork_btw_history`, when the trailing message is a user turn containing raw `text` blocks that
are NOT `toolResult`s (i.e. an unanswered directive — the mid-turn case), prefix/wrap that block
as quoted context, e.g. `[In-flight main task — context only, owned and handled by the main
agent; do not perform:] ...`. Keep role alternation intact (mark in place; do not split messages).

- Reversibility: easy (one function + tests).
- D-13 compatibility: full — history still shared; only labeled. Preserves the D-13 rationale
  (btw questions about the main task, e.g. "why is this slow?", keep their context).
- Careful: trailing user `toolResult` messages are completed exchanges, not directives — mark only
  raw-text user turns. Detection rule: trailing role == user AND any text block without toolResult.

### C. Exclude the in-flight main turn from the fork (strongest, not recommended alone)

Drop a trailing unanswered user-text turn before appending the framed question.

- Reversibility: easy code-wise, but semantically lossy.
- D-13 compatibility: weakens D-13 precisely when context matters most (btw about the current
  task loses the task). Prefer B unless live testing shows marking insufficient.

Recommended: **A + B** (harden framing, mark in-flight turn). C as fallback if live repro still fails.

## How to verify live

1. Repro 1: main `Write an essay about the history of computers`, immediately btw `list /tmp` →
   expect the btw fence to contain ONLY the listing; no `python_repl` essay call from the side
   agent; essay appears once (main transcript only).
2. Repro 2: main `Run sleep 30 via shell`, immediately btw `list /tmp` → expect NO
   `[btw] shell / sleep 30` approval; side fence contains ONLY the listing.
3. Context check (D-13 guard): main task with prior turns, btw `why is this slow?` referencing main
   history → side answer still demonstrates awareness of main-task context (no over-isolation).
4. Unit: `fork_btw_history` with trailing unanswered user-text turn yields the marker; with
   trailing toolResult/assistant turns yields no marker; roles still alternate; parent unmutated.
5. Suite: `pytest tests/test_btw.py -x` plus full suite green.

## File:line evidence index

- `strands_code_cli/btw.py:63-66` BTW_FRAMING (no scope bound)
- `strands_code_cli/btw.py:69-72` BTW_FORK_PREAMBLE (no do-not-perform)
- `strands_code_cli/btw.py:140-173` fork_btw_history; absorb branch `:169-170`
- `strands_code_cli/btw.py:346-395` build_btw_agent; fork call `:372`, instructions `:392`
- `strands_code_cli/loop.py:572-574` spawn-time live-history snapshot
- `strands_code_cli/policy_gate.py:83-91` agent-identity [btw] tagging (rules out misattribution)
- `.venv/.../strands_harness/tools/subagent.py:399-407` upstream absorb assumes trailing user = tool results
- `strands_code_agent/code_agent.py:16-17` task-completion instructions amplifying adoption
- `.planning/phases/07-subagents-btw-side-channel/07-UAT.md:63-70` gap record
- `.planning/phases/07-subagents-btw-side-channel/07-CONTEXT.md:31` D-13 shared-history rationale
