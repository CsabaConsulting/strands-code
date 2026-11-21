---
phase: "06"
slug: "skills-memory-file"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-05"
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Covers the 06-01..06-04 implementation plus the UAT gap round (escape,
> reload, batch verbs, mode persistence, promotion quieting, init guard).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| user-input→dispatch | Slash head plus trailing text are untrusted; resolved exact-match only, never globbed or executed | Slash commands (low) |
| skills-dir→index | ./.agent/skills bodies are untrusted repo content; quoted into prompts with a marker, never executed | Skill instructions (medium) |
| repo-files→injector | STRANDS.md plus .agent/MEMORY.md are untrusted repo content; injected with markers, never trusted as instructions | Repo conventions (medium) |
| disk→loader | Symlink or swap attacks between mtime check and read; roots refused, reads resolve first | Memory files (medium) |
| model-output→memory | Revise and init fenced blocks are untrusted model text; applied verbatim only after user review, never auto-trusted | Drafted sections (medium) |
| repo-tree→scan | /init reads repo files as untrusted input under caps; drafts stay labeled proposed until approved | Scan outline (low) |
| typed-input→prompts | EOFError from closed/piped stdin at curate/revise prompts; must fail closed, never escape run_loop | Prompt answers (low) |
| disk→approve | Tampered or failing memory files raise mid-approve; errors report as transcript lines, queue state stays retryable | Memory writes (medium) |
| fact-store→curate | Harness .agent/memory facts queue as proposals; only facts extracted during the session surface, never pre-existing files | Extracted facts (medium) |
| mode→home-config | /memory mode choice persists to the platformdirs home (mode string only, never content or credentials) | Mode choice (low) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-01 | Tampering | /skills remove plus show name handling | high | mitigate | remove_skill mirrors _remove_snapshot_dir: resolve, same-parent check, name-equality check, symlinked skill dir refused (skills.py:182-196); show resolves through the index only, never joins raw input to a path (router.py:770) | closed |
| T-06-02 | Tampering | Composed skill prompt | medium | mitigate | Explicit invocation framed as the trust signal (user chose this skill; follow it; do not re-check the skills tool) with distrust scoped to embedded third-party directives contradicting the task (router.py skill branch; reframed round 3 with user approval — the absolute marker made models refuse legitimate invocations, G-6-R3-2); deny-first gate still covers every resulting tool call (the hard control); allowed-tools displayed verbatim, never enforced | closed |
| T-06-03 | Tampering | Memory injector plus first load | high | mitigate | First-load banner names both files plus mtimes; injected block carries MEMORY_UNTRUSTED_PREFIX (memory_file.py:49,256); register_memory_plugin adds a ContextInjector render only (memory_file.py:312), wired separately from builtin_tools/interventions (main.py:128,142,165) — memory cannot widen tool scope | closed |
| T-06-04 | Tampering | Memory file reads plus writes | medium | mitigate | Symlinked memory files and .agent dir refused with ValueError (memory_file.py:182,185,216); reads resolve before open (memory_file.py:161); writes go tmp plus os.replace to the two known paths only (memory_file.py:198) | closed |
| T-06-05 | Denial of service | Memory injection size | medium | mitigate | MEMORY_INJECT_CAP 16000 chars with explicit truncation marker (memory_file.py:44) | closed |
| T-06-06 | Tampering | Revise plus init apply path | medium | mitigate | Fenced blocks apply verbatim only after quoted user review with fail-closed defaults (deny on unclear review, revert on unclear revise — loop.py:556,702); untrusted markers retained on injected content; applied memory never touches builtin_tools or interventions wiring | closed |
| T-06-07 | Information disclosure | /init repo scan | medium | mitigate | Fixed source lists with MAX_SCAN_FILES 25 and MAX_SCAN_BYTES 50000 caps; docs filenames only; .agent/sessions never read at all three sites — read (memory_file.py:418), layout (memory_file.py:463), deep sample (memory_file.py:557) — key-shaped files skipped (memory_file.py:375); nothing written before curate approval | closed |
| T-06-08 | Denial of service | review_memory_queue + consume_revise_turn + boundary review (loop.py) | medium | mitigate | EOFError handlers fail closed — review breaks pending (loop.py:624), revise disarms with revert note (loop.py:763), boundary input breaks (loop.py:1019); boundary guard catches (OSError, ValueError) so save/flush still run (loop.py:1006) | closed |
| T-06-09 | Tampering | CurateQueue.approve + _memory_message approve | medium | mitigate | Apply-first ordering keeps failed proposals pending (memory_modes.py:approve writes before queue mutation); approve/approve-all failures return errors as replies, queue stays retryable (router.py:655,669) | closed |
| T-06-10 | Information disclosure | skill_match_note echo (loop.py) | low | accept | Echo prints the skill namespaced name plus description already shown by /skills list; no file content, no new exposure | closed |
| T-06-11 | Denial of service | Hostile skill description crashes session (WR-06, gap round) | medium | mitigate | Descriptions render verbatim through print_plain (markup off) at all three sites — /skills list, /skills show, match echo (round-1 escape() calls reverted round 3 as redundant/cosmetically harmful); proven by test_markup_descriptions_render_verbatim_without_raising | closed |
| T-06-17 | Denial of service | Dynamic transcript text crashes session via Rich markup (round 2: turn-failure handler) | medium | mitigate | print_plain helper (output.py: markup off, style kwarg) routed through every dynamic loop/router/memory print — replies, review lines, reload notes, shadow warnings, banners, picker titles, corrupt notes, both turn-failure handlers; callback_handler str paths use markup=False inline (model text, search/tool I/O); static-only prints unchanged; proven by 3 tests incl. run_loop regressions | closed |
| T-06-18 | Spoofing | Reloaded skill distrusted via stale harness registry (round 2: dual-registry refusal) | medium | mitigate | build_agent owns the AgentSkills instance (harness passes through verbatim) stashed as agent._skills_plugin; reload refreshes the harness registry first via set_available_skills, then the CLI index — failed refresh leaves both stale, never disagreeing; proven by 3 tests incl. SDK seam-shape pins | closed |
| T-06-12 | Tampering | Silent mode + approve-all auto-apply hostile promotions (gap round) | medium | mitigate | Silent is opt-in with one transcript line per applied write; launch seeding means pre-existing fact files never queue (loop.py:958) so cloned-repo facts cannot ambush curate; already-memorialized sections skipped (loop.py:997); approve-all is an explicit verb; injected content stays untrusted-marked | closed |
| T-06-13 | Information disclosure | Persisted memory mode config (gap round) | low | mitigate | MemoryModeConfig mirrors DiffConfig exactly: platformdirs home, 0o700 parent, atomic tmp+replace, symlink refusal (memory_modes.py:80-97); stores the mode string only, never content or credentials | closed |
| T-06-14 | Tampering | Empty skill dispatches a confusing agent turn (gap round) | low | mitigate | Fail-closed reply naming the skill and asking for a SKILL.md body (router.py:205); no agent turn, no skills-tool round-trip | closed |
| T-06-15 | Spoofing | Skill shadows a builtin slash (/model hijack) | medium | mitigate | Builtins always win dispatch (router.py builtin branches precede skill resolve); colliding skills warn at startup (skills.py warnings); /skill alias added to the head set so it cannot be hijacked either | closed |
| T-06-SC | Tampering | package installs | high | accept | No package installs in this phase or the gap round: prompt_toolkit, rich, pyyaml, platformdirs, and the strands SDK/harness are already declared in pyproject.toml and imported by repo code, so the legitimacy gate does not trigger | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | (new) model reads .agent/sessions via tools during any turn incl. /init | Read-only, same read-tool capability as every turn — no new channel; the scan code itself provably excludes sessions (T-06-07) and the init prompt explicitly forbids session reads; residual is a soft prompt guard the model may ignore | orchestrator L1 | 2026-10-05 |
| AR-02 | (new, ex IN-03) sweep_promotions reads fact files with no size cap | Local-only files, 3 proposals per sweep cap bounds the queue, MEMORY_INJECT_CAP bounds context impact; a hostile giant fact file bloats one proposal body at most | orchestrator L1 | 2026-10-05 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-05 | 16 | 16 | 0 | orchestrator L1 (gsd-security-auditor type unavailable in this runtime; gsd_run not on PATH — inline grep-depth verification against plan registers, same as 05) |
| 2026-10-05 | 18 | 18 | 0 | orchestrator L1 — round-2 fix verification (T-06-17 markup-safe printing, T-06-18 registry refresh; no new installs, threats_open stays 0) |
| 2026-10-05 | 18 | 18 | 0 | orchestrator L1 — round-3 fix verification (T-06-02 marker reframed with user approval, T-06-11 escape superseded by print_plain; no new threats, threats_open stays 0) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-05
