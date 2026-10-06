---
status: complete
phase: 06-skills-memory-file
source: [06-UAT-round1.md]
round: 2
started: 2026-10-05T08:00:00Z
updated: 2026-10-05T08:30:00Z
---

## Current Test

[testing complete — round 2: 6 passed, 2 issues, 0 pending]

## Tests

### 1. Empty-skill guard
expected: /greet replies "Skill 'local:greet' has no instructions — add a markdown body to its SKILL.md." (no agent turn)
result: pass

### 2. Memory volume at startup
expected: Fresh CLI launch in a repo with existing .agent/memory facts shows zero stale proposals; only facts extracted during the session surface; /memory approve-all clears a batch in one reply
result: pass
note: "Startup silent across launch + 2 turns (was 3 dialogs/launch); empty approve-all correct live, batch path covered by unit tests"

### 3. Markup descriptions render
expected: /skills and /local:markup (description containing [/]) render the description literally with no MarkupError crash
result: issue
reported: "Match echo rendered literally after /skills reload, but the following agent turn crashed the session: upstream OTel context error failed the turn, then the turn-failed handler raised MarkupError (closing tag '[/red]' doesn't match) rendering the exception text"
severity: major
note: "Description-escape half PASSED (list + echo literal); crash is a new same-class site (dynamic exception text through markup parsing)"

### 4. Mode persists across restarts
expected: /memory mode silent, restart CLI, bare /memory mode still reports silent
result: pass

### 5. Colon completion
expected: /local: + TAB lists local skills only; /local:gr filters by tail; /other: offers nothing
result: pass
reported: "Worked"

### 6. Skill reload
expected: New skill dir created mid-session appears after /skills reload (also /skills refresh) with "Reloaded N skills." — no restart; removable skill resolves immediately after
result: issue
reported: "Reloaded 2 skills + match echo worked, but the model refused the reloaded skill twice: 'No such skill exists — only markup is listed, not reloader' (it cross-checked the harness skills tool, whose registry is stale)"
severity: major
note: "Reload mechanics PASSED; new gap is the dual-registry mismatch (CLI index reloaded, harness AgentSkills load-once) combined with the untrusted marker teaching distrust"

### 7. Init avoids session internals
expected: /init drafts sections through curate; transcript shows no reads of .agent/sessions or the session index during the draft turn
result: pass
note: "Zero .agent/sessions reads; model explicitly treated .agent/ as excluded/off-limits. It still tool-explored repo files (read/find/ls + 2 shell approvals) despite the no-exploration line — soft-guard limits, out of gap scope. Silent mode (persisted, home-level) auto-applied all 5 drafts + 3 promotions with log lines, as designed."

### 8. /skill alias
expected: /skill lists exactly what /skills lists
result: pass
reported: "The skill alias works."

## Summary

total: 8
passed: 6
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-6-R2-3
  truth: "Turn-failure and transcript prints render dynamic text without crashing"
  status: fixed
  reason: "User reported: agent turn failed with upstream OTel context error, then loop.py:1114 turn-failed handler raised MarkupError rendering the exception text, killing the session"
  severity: major
  test: 3
  root_cause: "Same class as WR-06: dynamic text (str(exc)) interpolated into Rich-markup-parsed console.print; any markup-shaped content in exceptions/filenames/replies can kill the session."
  fix: "print_plain helper (output.py: markup off, style kwarg) routed through all dynamic loop/router/memory prints; callback_handler str paths use markup=False inline (avoids CLI→agent import). Proven by 3 tests incl. run_loop regressions with hostile exc/reply text; old expression shape verified to raise identically to the live crash."
  artifacts: []
  missing: []
- gap_id: G-6-R2-6
  truth: "Reloaded skills are trusted and followed when invoked"
  status: fixed
  reason: "User reported: after /skills reload the model refused the new skill twice, citing the harness skills tool listing only the old skill ('No such skill exists — only markup is listed, not reloader')"
  severity: major
  test: 6
  root_cause: "Dual registry: CLI SkillIndex reloads but harness AgentSkills (skills=True at build_agent) is load-once; model cross-checks the stale tool registry and, primed by the untrusted-content marker, refuses the composed instructions."
  fix: "build_agent owns an AgentSkills instance (harness passes through verbatim) stashed as agent._skills_plugin; reload verb refreshes the harness registry FIRST via set_available_skills then the CLI index (failed refresh leaves both stale, never disagreeing). Proven by 3 tests incl. SDK seam-shape pins (passthrough identity + rescan no-raise)."
  artifacts: []
  missing: []
