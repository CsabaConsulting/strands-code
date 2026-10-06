---
status: complete
phase: 06-skills-memory-file
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md]
started: 2026-10-05T01:20:00Z
updated: 2026-10-05T07:30:00Z
---

## Current Test

number: none
name: UAT complete — all 11 tests reported, 8/8 gaps fixed
awaiting: user live re-check (esp. T6 volume feel) + commit decision

## Tests

### 1. Invoke a skill via slash
expected: Skill runs from ./.agent/skills with trailing text as input
result: issue
reported: "Skill 'greet' activated (no instructions available). [Assistant] Hello! Nice to meet you! How can I help you today?"
severity: major

### 2. Autocomplete + match echo + typo
expected: Partial name completes to /namespace:skill; typed full name echoes a match; typo shows no match
result: pass

### 3. Builtin collision
expected: Skill named like a builtin (e.g. model) warns at startup; builtin still wins the slash
result: pass

### 4. /skills list, show, remove
expected: /skills lists skills with descriptions; show displays one; remove deletes it (traversal-guarded)
result: pass

### 5. /init scan-draft through curate
expected: /init drafts .agent/MEMORY.md + thin root STRANDS.md pointer as approvable proposals; re-run merge-scans only
result: pass

### 6. /memory curate loop
expected: Approve one proposal, deny one, revise one in words with accept/revert/iterate; file state matches
result: issue
reported: "The memory approvals are extremely annoying and disruptive (3 times after every turn?). The memory seems to excavate things from the past and bring them up. We need to do something about this memory suggestion and approval shenanigan because it's too disruptive right now. We must do something with that memory because it makes the CLI almost unusable."
severity: major

### 7. Memory modes + reload + flush
expected: Curate/silent toggle works (silent still logs); external edit auto-reloads with a note; short run loses nothing on exit
result: issue
reported: "Things seem to work, except the memory mode is not preserved between CLI restarts"
severity: minor

### 8. Match echo with markup characters (WR-06 residual)
expected: Skill whose description contains Rich markup chars (e.g. [/]) echoes cleanly without garble or crash
result: issue
reported: "Even /skills crashed: MarkupError closing tag '[/]' at position 20; /local:markup crashed at position 36. BTW '/skill' should be an alias to '/skills'"
severity: major

### 9. Namespace-prefix completion
expected: Typing /local: + TAB suggests skills in that namespace
result: issue
reported: "it also stop suggesting once I press ':' after '/local'"
severity: minor

### 10. Skill hot-reload
expected: A /skills reload/refresh command (or automatic pickup) makes new skills appear without restarting
result: issue
reported: "I created a dummy skill for the deletion, but it doesn't show. Should the CLI be restarted for a skill to show up? There should be a skill reload or refresh command, the CLI should not need to be restarted for this"
severity: minor

### 11. /init excludes .agent internals
expected: Repo scan skips .agent/ (session snapshots stay out of drafts and reads)
result: issue
reported: "Observed in transcript: scan listed .agent/session snapshots and cat'ed the session index during /init"
severity: minor

## Summary

total: 11
passed: 4
issues: 7
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Invoking /<skill> runs the skill body with trailing text as input"
  status: fixed
  reason: "User reported: Skill 'greet' activated (no instructions available); assistant replied generically, ignoring input"
  severity: major
  test: 1
  root_cause: "Test-artifact greet SKILL.md is frontmatter-only (empty body → empty instructions); router composed an empty-instructions agent turn and the model fell through to the SDK skills tool, which reports 'no instructions available'"
  fix: "router.py fail-closed reply for blank-instructions skills; proven by test_frontmatter_only_skill_refuses_dispatch"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "Memory proposals arrive at a reviewable volume with batch handling"
  status: fixed
  reason: "User reported: memory approvals are extremely annoying and disruptive (3 times after every turn?); proposals excavate stale facts from the past and re-propose them as new; identical proposals return every launch because deny lasts only the session; promotion also re-proposes just-approved init sections in paraphrase"
  severity: major
  test: 6
  root_cause: "promotion_seen started empty every launch so ALL .agent/memory facts re-queued as new each restart (3/turn); no dedup against memorialized sections; no batch verbs"
  fix: "seed_promotion_seen at startup (only in-session facts surface) + skip_sections dedup vs .agent/MEMORY.md + /memory approve-all|deny-all; recency cutoff redundant given seeding (documented); paraphrase re-detection out of scope. Live-session feel still needs user confirmation."
  artifacts: []
  missing: []
  debug_session: ""
- truth: "Typing /<namespace>: + TAB suggests skills in that namespace"
  status: fixed
  reason: "User reported: it also stop suggesting once I press ':' after '/local'"
  severity: minor
  test: 9
  root_cause: "SlashCompleter matched the whole '/local:' query against bare names, so nothing matched after ':'"
  fix: "completer.py namespace-prefix matching (tail after 'local:' filters bare names; skills only; unknown namespaces offer nothing); proven by 4 colon tests incl. fuzzy-wrapped path"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "/skills offers reload/refresh so new skills appear without restarting"
  status: fixed
  reason: "User reported: created dummy skill for deletion but it doesn't show; CLI restart required; there should be a reload/refresh command"
  severity: minor
  test: 10
  root_cause: "SkillIndex is load-once cached (_ensure_loaded); no rescan path existed"
  fix: "SkillIndex.reload() + /skills reload|refresh verb; proven by test_reload_picks_up_new_skill_without_restart + test_refresh_alias_reloads"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "/init scan skips .agent/ internals"
  status: fixed
  reason: "Observed: scan listed .agent/session snapshots and cat'ed the session index during /init"
  severity: minor
  test: 11
  root_cause: "Scan code already excluded .agent/sessions at all 3 sites (read/layout/deep-sample); the reads were the model self-directing its file tools during the init draft turn"
  fix: "format_init_prompt guard forbidding .agent/sessions + session-index reads (soft prompt guard; residual accepted as AR-01 in 06-SECURITY.md); proven by test_init_prompt_guards_agent_internals"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "/memory mode persists across CLI restarts"
  status: fixed
  reason: "User reported: toggle + reload work, but mode resets to curate on restart"
  severity: minor
  test: 7
  root_cause: "MemoryModeState is in-memory session-sticky by design (D-07); no disk persistence"
  fix: "MemoryModeConfig (DiffConfig shape: platformdirs home, 0o700, atomic, symlink refusal); loop loads at startup, router saves on set; proven by 3 persistence tests"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "Skill descriptions with markup chars render without crashing"
  status: fixed
  reason: "User reproduced WR-06 live: /skills and /local:markup both raise MarkupError on '[/]' description (loop.py:1035 and loop.py:1030 console.print paths)"
  severity: major
  test: 8
  root_cause: "Unescaped description through Rich markup console.print (WR-06 residual, now live-confirmed on two paths)"
  fix: "rich.markup.escape at all 3 description sites (router list/show, loop match echo); proven by test_markup_descriptions_render_without_raising rendering all three through Rich"
  artifacts: []
  missing: []
  debug_session: ""
- truth: "'/skill' aliases '/skills'"
  status: fixed
  reason: "User requested: '/skill' should be an alias to '/skills'"
  severity: minor
  test: 8
  root_cause: "No alias existed (new request, not a regression)"
  fix: "dispatch cmd in (/skills, /skill) + 'skill' in BUILTIN_SLASH_HEADS (shadow-safe, completable); proven by test_skill_alias_lists_like_skills"
  artifacts: []
  missing: []
  debug_session: ""
