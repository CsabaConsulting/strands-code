# Phase 03 Plan Check: Permissions Gate

**Verdict: PASS** — plan is executable, covers TOOL-03, all 16 context decisions, and all open research items. No blocking issues. Three non-blocking observations below (accepted deviations, explicitly documented in the plan).

**Checked:** `03-PLAN.md` + `03-PLAN-SUMMARY.md` against ROADMAP.md Phase 3, `03-CONTEXT.md` D-01..D-16, `03-RESEARCH.md` (esp. one-HITL, deny-wins, no-double-prompt, fail-closed direction, Phase 4 vocabulary), REQUIREMENTS.md TOOL-03.

## Coverage matrix

| Source | Requirement | Plan location | Status |
|---|---|---|---|
| Roadmap crit 1 | Prompt before edits/shell/network | must_haves truths 1, tracer + gate + repl tasks | covered |
| Roadmap crit 2 | Standing allow/deny quiets routine, gates dangerous | must_haves truth 2, store + engine + gate tasks | covered |
| TOOL-03 | Deny-first policy file over edits/shell/network | whole plan; success_criteria both map to roadmap criteria | covered |
| D-01 | Full-detail prompt (command/diff + risk line) | policy_ask task, threat T-03 register | covered |
| D-02 | Deny skips, turn continues | tracer probe (b) + wiring task, FLAGGED ASSUMPTION | covered |
| D-03 | always-deny appends standing rule | ask task (always/never append in policy_ask), T-03-06 | covered (see O-1) |
| D-04 | Batch repeated actions, one prompt | BatchState turn-cache, resolved item 4 | covered (see O-2) |
| D-05 | Deterministic TOML, no NL/smart/Cedar | prohibitions + store task, acceptance "no LLM/NL" | covered |
| D-06 | tool + path-glob / command-prefix matching | engine task (match_rule) | covered |
| D-07 | Deny-wins | engine task + resolved item 1 (union) | covered |
| D-08 | Repo overrides home | resolved item 1 layered UNION + store task | covered (see O-3) |
| D-09 | Reads/search pre-allowed, mutations prompt | built-in defaults, tracer/gate allowlists | covered |
| D-10 | No double-prompt with /diff | resolved item 6 option 1, subsumption task, ask-count==1 test | covered |
| D-11 | python_repl prompts with code | repl task (a), risk 5 documented | covered |
| D-12 | Delegated turns inherit + trust flag | gate bind_main_agent + repl task (b), default False | covered |
| D-13 | Policy owns scope expansion | ordering task, resolve→decide→confine, T-03-03 | covered |
| D-14 | Network by command pattern, exotic bypass accepted | engine substring-scan + residuals doc | covered |
| D-15 | GET/fetch pre-allowed, uploads prompt | engine flag-parsing rules | covered |
| D-16 | Any host, no host allowlist | prohibitions ("MUST NOT build host allowlist"), engine fetch-class allows | covered |
| Research risk 1 | Exactly one HITL (collision BLOCKING) | prohibitions, key_links, tracer (a), T-03-01 | covered |
| Research risk 2 | Shell 120 s timeout unpinned | T-03-10 accept+document (re-recorded) | covered |
| Research risk 3 | Deny mechanics unverified | tracer live-turn probe + Guide fallback note | covered |
| Research risk 4 | sh -c/pipe/VAR evasion | resolved item 3 NORMALISE-THEN-SPLIT + residuals | covered |
| Research risk 5 | python_repl all-or-nothing | engine/gate docstrings, T-03-08 | covered |
| Research risk 6 | Scope/policy ordering | resolved + ordering task, T-03-03 | covered |
| Research risk 7 | Policy write safety | narrow-only appender, atomic, symlink refusal, T-03-06 | covered |
| Research risk 8 | Batcher location | resolved item 4 (gate-layer BatchState, no time window) | covered |
| Research risk 9 | programmatic_tool_caller bypass | resolved item 8 conditional tracer task, T-03-05 | covered |
| Research risk 10 | Phase 4 vocabulary collision | prohibitions + schema acceptance + summary fence + verification grep | covered |
| Research risk 11 | Fail-closed direction | resolved item 7 FAIL-CLOSED, T-03-02 | covered |
| Research §7 | §5 /diff options pick one | option 1 chosen, 2/3 rejected with reasons | covered |
| Research §7 | Ask-contract reconciliation | resolved item 5 KEEP BOTH divided by layer | covered |

## Structural checks

- Tracer-first ordering: yes — tracer task leads, all build tasks follow the proven spine.
- Reversibility ratings: present on all 8 tasks (7 reversible, store + diff-subsumption costly-but-migratable, no checkpoints — consistent with summary "zero one-way doors").
- File:line grounding: sampled `main.py:73-109` (build_agent mapping confirmed), `diff_gate.py:41` (AskCallable), `diff_gate.py:229-272` (_gate_and_apply), `diff_gate.py:318-320` (_default_ask) — all resolve to the cited symbols. Remaining refs (scope.py, router.py, code_agent.py, .venv HITL/harness lines) are specific enough to be verifiable at execution.
- Wave markers: header `wave: 1`; task `[~]` tracer → `[P1]` ×4 → `[P2]` ×3 is a coherent priority chain within one wave (tracer first, spine before polish).
- Threat model: 12 threats map 1:1 onto risks/decisions; 5 BLOCKING items each have a green-gate test.
- Scope bleed: none — no mode system, no semantic/LLM classification, no host allowlist, no NL policy; "Phase 4" mentions are downstream-handoff notes only, fenced by the schema-freeze prohibition and the pre-merge grep gate.
- Summary fidelity: `03-PLAN-SUMMARY.md` accurately reflects the plan (single-HITL, union+fail-closed, subsumption, conditional pin, residuals); no claims beyond the plan.

## Observations (non-blocking, no plan edit needed)

- O-1 (D-03 symmetric extension): CONTEXT phrases D-03 as "always deny this" after a deny; the plan implements always/never (both directions) in the HITL ask. Harmless symmetric completion of the Claude-Code reference model; executor should keep derived rules narrow per T-03-06 either way.
- O-2 (D-04 honest narrowing): CONTEXT asks for a batch prompt "listing each action"; the plan documents sequential execution makes pre-listing impossible and implements per-(rule-key, turn) single-prompt instead. Explicitly flagged, not silently dropped — accept.
- O-3 (D-08 "overrides" → union): CONTEXT says repo "overrides" home; the plan resolves the research-flagged merge-vs-override opening as layered UNION with a safety rationale (replace would drop home denies). Deliberate and documented — accept; executor must keep repo-first ordering explanation-only.
