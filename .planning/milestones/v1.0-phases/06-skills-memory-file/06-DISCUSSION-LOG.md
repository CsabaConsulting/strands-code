# Phase 6: Skills + Memory File - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-04
**Phase:** 6-Skills + Memory File
**Areas discussed:** Skill invocation UX, Memory file contract, /init scaffolding depth

---

## Skill invocation mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Slash-per-skill | Each skill becomes /<name> via router dispatch, like /model and /cost | ✓ |
| /skill dispatcher | One namespace: /skill list, /skill <name> | |
| Agent auto-trigger | Agent picks matching skills itself from descriptions | |

**User's choice:** Slash-per-skill
**Notes:** None.

## Skill collision rule

| Option | Description | Selected |
|--------|-------------|----------|
| Built-ins win | Built-in always wins; CLI warns at load that the skill is shadowed | ✓ |
| Skills override | Skill takes the slash; built-in stays reachable another way | |
| Fallback namespace | Built-in keeps the slash; colliding skill reachable via /skill <name> | |

**User's choice:** Built-ins win, extended via free text: skills get marketplace/owner colon prefixes (Claude Code style); autocomplete matches on the bare skill name but completes the full `namespace:skill` form.
**Notes:** User specified the autocomplete behavior unprompted: matching on skill name, completing with namespace + colon.

## Skill discovery

| Option | Description | Selected |
|--------|-------------|----------|
| Slash autocomplete | Type / and fuzzy-match skill names; completion inserts namespace:skill | ✓ |
| /skills list | /skills prints names + one-line descriptions | |
| Both | Autocomplete for speed plus /skills for browsing | |

**User's choice:** Slash autocomplete, plus a free-text addendum: a separate /skill or /skills command should also exist to list, browse, examine, and uninstall skills.
**Notes:** Local uninstall (removing from ./.agent/skills) captured as in-scope; marketplace install/uninstall stays v2 per SKILL-03.

## Skill input

| Option | Description | Selected |
|--------|-------------|----------|
| Trailing text | /my-skill <whatever> — trailing text becomes the skill's input | ✓ |
| No args | Skill runs as-is; user steers with plain follow-ups | |

**User's choice:** Trailing text
**Notes:** None.

## Memory file identity

| Option | Description | Selected |
|--------|-------------|----------|
| MUSE.md at root | De-facto standard other CLIs already read | |
| .agent/MEMORY.md | Next to policy, skills, sessions; consistent owned namespace | |
| Both, .agent wins | Read MUSE.md if present, .agent/MEMORY.md wins on conflict | ✓ |

**User's choice:** Both, .agent wins — with a rename: root file is STRANDS.md (product match), not MUSE.md.
**Notes:** User asked whether root MEMORY.md would collide with other conventions; agent answered yes-risk at root (generic name, other agents use it), safe inside owned ./.agent/. Locked: root STRANDS.md + ./.agent/MEMORY.md.

## Memory file shape

| Option | Description | Selected |
|--------|-------------|----------|
| Scaffolded sections | /init writes headed sections; user fills them in | |
| Freeform markdown | User writes whatever; CLI loads it verbatim | |
| Frontmatter + body | YAML frontmatter plus markdown body | ✓ |

**User's choice:** Frontmatter + body, scaffolded by /init.
**Notes:** User asked how timestamps and metadata live beyond root frontmatter — became the next question.

## Memory metadata depth

| Option | Description | Selected |
|--------|-------------|----------|
| Root frontmatter only | updated-at, version, scope only; section freshness untracked | |
| Section markers | HTML-comment updated markers above sections, invisible when rendered | ✓ |
| Sidecar file | .agent/memory.meta.json tracks per-section history | |

**User's choice:** Section markers
**Notes:** None.

## /memory editing model

| Option | Description | Selected |
|--------|-------------|----------|
| $EDITOR round-trip | /memory opens $EDITOR; CLI reloads on save | |
| Inline REPL | /memory view/append/rm sections without leaving the REPL | |
| Both | Inline for tweaks, $EDITOR for real edits | |

**User's choice:** None of the above (free text): no in-CLI editor at all — memory editing is automatic by the harness loop; /memory is a review surface (diff/approve), and hand-editing happens outside the harness.
**Notes:** User challenged the premise ("Why would there be an editor?"). Agent reflected the review-surface model back in plain text and confirmed before locking. External-edit reload resolved as automatic per-turn mtime check, no manual signal.

## Memory default mode

| Option | Description | Selected |
|--------|-------------|----------|
| Curate by default | Every harness proposal prompts approve/deny; silent is one toggle away | ✓ |
| Silent by default | Harness writes silently, transcript logs it | |

**User's choice:** Curate by default
**Notes:** Agent recommended curate per deny-first posture; silent stays opt-in via a session-sticky toggle (Phase 4 D-07 precedent). Silent mode still logs to the transcript.

## NL revise loop scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full loop in MVP | Approve/deny plus revise-in-words with accept/revert/iterate | ✓ |
| Approve-only MVP | Approve/deny only; edits via external editor + auto-reload | |

**User's choice:** Full loop in MVP
**Notes:** User proposed the loop shape: approve-with-edit supplies an instruction prompt, a special loop quotes memory + instructions to the LLM, returns revised memory, user accepts/reverts/iterates. Agent endorsed as Phase 4 D-04 (revise rounds) reuse and confirmed NL instructions are the only in-CLI edit path.

## /init generation strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Repo-scan draft | Scan layout/configs/docs, draft sections, review via curate loop | ✓ |
| Questionnaire | Ask a few questions, then write | |
| Empty template | Empty scaffold + frontmatter; harness fills over time | |

**User's choice:** Repo-scan draft
**Notes:** None.

## /init write targets

| Option | Description | Selected |
|--------|-------------|----------|
| .agent full + root pointer | Full draft in .agent/MEMORY.md; thin summary + pointer in root STRANDS.md | ✓ |
| .agent only | Draft only in .agent/MEMORY.md; root stays fully manual | |
| Root only | Everything in root STRANDS.md | |

**User's choice:** .agent full + root pointer
**Notes:** None.

## /init re-run behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Merge-scan | Re-scan drafts only missing/stale sections as curate proposals | ✓ |
| Refuse if exists | /init refuses when files exist, points to /memory | |
| Overwrite + backup | Fresh full draft, previous file kept as backup | |

**User's choice:** Merge-scan
**Notes:** None.

## /init scan scope

| Option | Description | Selected |
|--------|-------------|----------|
| Shallow + deepen | Layout/README/configs/docs; "scan deeper" for source + manifests | ✓ |
| Shallow only | Top-level only; misses source-level conventions | |
| Deep always | Full sampling every run; slowest, most tokens | |

**User's choice:** Shallow + deepen
**Notes:** None.

## the agent's Discretion

- /skill vs /skills command name and subcommand shape
- Autocomplete matching algorithm and PromptSession completer wiring
- Skill file format details (pending harness-seam research)
- Exact frontmatter keys and scaffolded section list
- Mtime-check placement and reload-note wording
- Memory-mode toggle surface and silent-mode log verbosity
- Revise-loop prompt shape
- Shallow vs deep scan source lists

## Deferred Ideas

- Skill marketplaces (add/install/list from marketplace) — SKILL-03, v2
- MCP servers as tools via user config — SKILL-04, v2
- Hindsight cross-session recall — SKILL-05, v2
- Hand-editing memory inside the CLI — rejected (NL instructions + external editor cover it)
