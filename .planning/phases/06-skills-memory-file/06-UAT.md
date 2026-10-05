---
status: testing
phase: 06-skills-memory-file
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md]
started: 2026-10-05T01:20:00Z
updated: 2026-10-05T01:20:00Z
---

## Current Test

number: 1
name: Invoke a skill via slash
expected: |
  Create ./.agent/skills/greet/SKILL.md (name: greet, description: says hello).
  Type `/greet hello there` — skill runs with "hello there" as input.
awaiting: user response

## Tests

### 1. Invoke a skill via slash
expected: Skill runs from ./.agent/skills with trailing text as input
result: [pending]

### 2. Autocomplete + match echo + typo
expected: Partial name completes to /namespace:skill; typed full name echoes a match; typo shows no match
result: [pending]

### 3. Builtin collision
expected: Skill named like a builtin (e.g. model) warns at startup; builtin still wins the slash
result: [pending]

### 4. /skills list, show, remove
expected: /skills lists skills with descriptions; show displays one; remove deletes it (traversal-guarded)
result: [pending]

### 5. /init scan-draft through curate
expected: /init drafts .agent/MEMORY.md + thin root STRANDS.md pointer as approvable proposals; re-run merge-scans only
result: [pending]

### 6. /memory curate loop
expected: Approve one proposal, deny one, revise one in words with accept/revert/iterate; file state matches
result: [pending]

### 7. Memory modes + reload + flush
expected: Curate/silent toggle works (silent still logs); external edit auto-reloads with a note; short run loses nothing on exit
result: [pending]

### 8. Match echo with markup characters (WR-06 residual)
expected: Skill whose description contains Rich markup chars (e.g. [/]) echoes cleanly without garble or crash
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
