---
title: "Phase 6 Research: Skills + Memory File"
researched: 2026-10-04
domain: "Harness skills/memory seams (AgentSkills, MemoryManager) + CLI slash routing + prompt_toolkit completion"
confidence: high
agent: "gsd-phase-researcher (generic-agent workaround — typed dispatch unavailable this session)"
---

# Phase 6 Research: Skills + Memory File

## Summary + Primary Recommendation

**Skills:** Do not invent a skill format. The installed harness already wires the SDK's `AgentSkills` plugin when `skills=True` (the default) and `./.agent/skills` exists, and the SDK implements the AgentSkills.io open standard (`SKILL.md` with `name`/`description` frontmatter + markdown body; progressive disclosure via a `skills` activation tool and an `<available_skills>` system-prompt block). Phase 6 work is therefore CLI surface only: slash-per-skill routing in `router.py dispatch`, a `/skills` management command, prompt_toolkit autocomplete, and local uninstall. The one hard constraint the planner must respect: SDK skill names match `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` — **colons are not legal in SDK names** — so the D-02 `source:name` namespace is a CLI router-layer concept mapped onto colon-free SDK names, never stored in `SKILL.md` frontmatter.

**Memory file:** The harness `memory={"stores": [...]}` seam is a *fact-extraction* store (per-fact `slug.md` files under `./.agent/memory`, extraction every 5 turns, injection every turn, `search_memory` on / `add_memory` off) — it is **not** a repo-conventions file and its extraction path has **no approval hook** (writes go straight to the store). The D-04 dual file (`STRANDS.md` + `./.agent/MEMORY.md`) is therefore a new CLI-owned seam: auto-load via a small `ContextInjector`-style plugin mirroring the harness `environment` plugin (which injects `AGENTS.md` only), curate via a `/memory` approve/deny surface whose proposal sources are `/init` drafts, NL-instruction revisions, and *promotion polls* of new fact-store entries (the only honest reading of "harness auto-proposals", since extraction itself cannot be gated). Also fix the found gap: the CLI never flushes `agent.memory_manager` on exit, so short runs lose pending extractions.

**Primary recommendation:** Build zero new formats — reuse `AgentSkills`/`Skill.from_directory` for skills and a CLI-owned injector plugin for the dual memory file; put namespacing, collision warnings, curate/silent modes, and mtime reload in `strands_code_cli/` (`router.py`, `loop.py`, two small new modules).

## User Constraints (from CONTEXT.md)

Locked decisions, discretion areas, and deferred ideas below are copied verbatim from `06-CONTEXT.md`. They outrank everything else in this report.

### Skill invocation UX (verbatim)

- **D-01:** Each local skill becomes a slash command (`/<name>`) routed through `router.py` dispatch as a reply-only action. Freeform trailing text is the skill's input (`/my-skill refactor the auth module`); no arg syntax to learn.
- **D-02:** On name collision, built-ins always win and the CLI warns at load that the skill is shadowed (`/model` can never be hijacked). Skills carry `source:name` colon namespaces (Claude Code style, prefixed by marketplace/owner); autocomplete matches on the bare skill name but completes the full namespaced form. — **Reversibility:** costly — the collision + namespace contract shapes router dispatch and user muscle memory; changing it re-opens slash routing.
- **D-03:** Discovery is slash autocomplete first, plus a `/skill` or `/skills` command (planner picks the name) for list/browse/examine and local uninstall (removing from `./.agent/skills`). Marketplace install/uninstall stays v2.

### Memory file contract (verbatim)

- **D-04:** Dual file, both auto-loaded: root `STRANDS.md` (product-named for interop — other CLIs read root conventions files; generic `MEMORY.md` at root risks collision) plus `./.agent/MEMORY.md` (collision-safe inside our owned dir). On conflict, `.agent` wins. — **Reversibility:** costly — filenames are a user-facing contract; renaming later needs a migration of existing files.
- **D-05:** Frontmatter + markdown body. Root frontmatter holds file-level metadata (scope, version, updated-at); per-section freshness lives in HTML-comment markers (`<!-- updated: ... -->`) above sections — invisible when rendered, no sidecar state.
- **D-06:** `/memory` is a review/curation surface, never an editor. No hand-editing inside the CLI: memory changes come from harness auto-proposals, user NL instructions, or an external editor. External edits auto-reload via a per-turn mtime check with a transcript note — no manual reload signal.
- **D-07:** Two memory modes, session-sticky toggle (Phase 4 D-07 precedent): curate (every harness proposal prompts approve/deny) is the default per deny-first posture; silent auto-apply is the opt-in. Silent mode still logs writes to the transcript.
- **D-08:** Approve-with-edit runs NL revise rounds in MVP (Phase 4 D-04 pattern reuse, not a new invention): the user describes the change in words, the LLM returns revised memory quoted for review, and the user accepts, reverts to the previous version, or iterates. NL instructions are the only in-CLI edit path.

### /init scaffolding depth (verbatim)

- **D-09:** `/init` produces a repo-scan auto-draft, not a questionnaire or empty template. The draft arrives as proposals through the curate loop for approval.
- **D-10:** `/init` writes the full draft to `./.agent/MEMORY.md` and a thin summary + pointer to root `STRANDS.md`. Detail stays owned; interop stays useful.
- **D-11:** Re-running `/init` merge-scans: only missing/stale sections are drafted as new curate proposals. Never clobbers approved memory.
- **D-12:** Shallow scan by default (layout, README, configs, docs index) for a fast predictable first run; the user says "scan deeper" for source sampling, manifests, and test layout.

### The agent's Discretion (verbatim — resolved with recommendations below)

- `/skill` vs `/skills` command name and subcommand shape (list/browse/examine/uninstall).
- Autocomplete matching algorithm (fuzzy vs prefix) and PromptSession completer wiring.
- Skill file format details — researcher confirms the harness skill seam shape first.
- Exact frontmatter keys and scaffolded section list for the memory files.
- Mtime-check placement (loop turn boundary vs loader) and reload-note wording.
- Memory-mode toggle surface (`/memory mode` vs config key) and silent-mode log verbosity.
- Revise-loop prompt shape (how memory + instructions are quoted to the LLM).
- Scan source list for shallow vs deep passes.

**Researcher recommendations for Discretion areas (prescriptive):**

1. Command name: `/skills` (plural; matches the `/model|/models` plural-alias precedent in `router.py`). Subcommands: bare `/skills` lists; `/skills show <name>` examines; `/skills remove <name>` uninstalls locally. No `browse` picker — autocomplete is primary per D-03 and `choice.radio_choice` stays available if a plan wants it. [ASSUMED — UX choice within D-03]
2. Matching: fuzzy over prefix — wrap a custom `Completer` in `FuzzyCompleter`, match against the bare skill name, emit the full `source:name` form as the completion text (D-02). Wire one `DynamicCompleter`-style refreshable completer into the loop's `PromptSession(completer=...)` so newly added skills complete without restart. [ASSUMED for fuzzy-over-prefix; completer classes VERIFIED in installed prompt_toolkit — see Code Examples]
3. Skill file format: AgentSkills.io `SKILL.md` exactly as the SDK parses it (`name`, `description` required; `license`/`compatibility`/`metadata`/`allowed-tools` optional; body = instructions; optional `scripts/`/`references/`/`assets/`). No project-specific fields. [VERIFIED: installed SDK `skill.py` + CITED: agentskills.io/specification]
4. Memory frontmatter keys: `scope: repo`, `version: 1`, `updated: <iso-date>` on both files; `source:` key (`init-shallow`/`init-deep`/`promoted`/`manual`) on `.agent/MEMORY.md` only. Scaffolded sections: `## Build`, `## Test`, `## Conventions`, `## Layout`, `## Gotchas` — each preceded by `<!-- updated: <iso-date> -->`. [ASSUMED — new contract; keys chosen to stay readable to foreign CLIs]
5. Mtime check: loop turn boundary (top of the `while True` in `run_loop`, before `session.prompt`), not inside the loader — one place, covers external edits between turns, and the transcript note prints once per change. Reload note: `Memory reloaded — STRANDS.md changed on disk.` [ASSUMED — placement within D-06]
6. Mode toggle: `/memory mode [curate|silent]` verb, session-sticky in-memory holder mirroring `ModeState` (no disk — D-07 default in-memory; `DiffConfig`-shape persistence only if a later phase demands it). Silent-mode logging: one transcript line per applied write (`Memory updated (silent): <section> ← <source>`). [ASSUMED — surface within D-07]
7. Revise-loop prompt: quote current section, then the user's NL instruction, then require the model to return the full revised section inside a fenced block for verbatim review (`Revise the quoted memory section per the instruction. Reply with the FULL revised section in one fenced block, then a one-line summary of what changed.`). Accept applies the fenced block; revert keeps the pre-round text; anything else iterates. [ASSUMED — prompt shape is new; round grammar reuses Phase 4 D-04]
8. Shallow scan sources: top-2-level directory layout, root `README.*`, `pyproject.toml`/`package.json`/`Cargo.toml` (whichever exists), `docs/` index (filenames only), `.agent/policy.toml` tool posture. Deep scan adds: source-file sampling (up to ~10 files, imports/docstrings only), manifest/lockfile dependency names, test-layout (`tests/` tree + runner config). Cap deep-scan file reads; never full-tree content. [ASSUMED — source list is new]

### Deferred Ideas (verbatim — out of scope, ignored)

- Skill marketplaces: add marketplace, install/list from marketplace (SKILL-03, v2).
- MCP servers as tools via user config (SKILL-04, v2).
- Hindsight cross-session recall behind the memory seam (SKILL-05, v2).
- Hand-editing memory inside the CLI — rejected, not deferred: NL instructions + external editor cover it.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SKILL-01 | CLI loads skills from local `./.agent/skills` and the user can list and invoke them | Harness `skills=True` + `DEFAULT_SKILLS_DIR` seam; `Skill.from_directory` loader; router slash dispatch; prompt_toolkit completer |
| SKILL-02 | CLI auto-loads the repo memory file and the user can scaffold and edit it (`/init`, `/memory`) | CLI-owned injector plugin (harness `environment` precedent); curate/silent modes; `/init` scan + merge; mtime reload; NL revise rounds |

## Project Constraints (from AGENTS.md)

Treat with the same authority as locked decisions. Extracted from `AGENTS.md` (read this session):

- Python >=3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform.
- AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports.
- No upper pins during the experimental phase; resync upstream deliberately, not continuously.
- Constructor-kwarg configuration, never env sniffing; absolute imports rooted at the package.
- No formatter/linter configured — match surrounding file style by hand (4-space, double quotes, ~100–120 cols).
- Triple-double-quoted docstrings on every public function/class/method; `Args:`/`Returns:` in plain text.
- Fail soft on read paths (formatted "not found" strings, never raise); log-and-continue only for best-effort cleanup.
- `rich` for human-facing REPL rendering only; never `print()` in library code (note: existing CLI code uses `console.print`, which is the established REPL equivalent).
- GSD workflow enforcement: work enters through `$gsd-quick` / `$gsd-debug` / `$gsd-execute-phase`, not direct edits.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Skill discovery + parsing | SDK (`AgentSkills`/`Skill`) | — | Harness already loads `./.agent/skills`; CLI must not re-parse |
| Skill slash routing + namespacing | CLI (`router.py`) | — | `source:name` is a CLI UX contract; SDK names are colon-free |
| Skill autocomplete | CLI (`loop.py` + completer) | — | PromptSession-owned input concern |
| Conventions-file auto-load | CLI (injector plugin) | — | No harness seam loads `STRANDS.md`/`.agent/MEMORY.md` |
| Fact extraction + recall | Harness (`MemoryManager`) | — | `memory=True` default already runs it; CLI only polls + flushes |
| Curate approve/deny surface | CLI (`/memory`, gate UX) | — | Session UX; extraction path has no hook to gate |
| `/init` repo scan + draft | CLI (`/init` branch) | Agent (draft prose) | Scan is deterministic code; draft wording is one agent turn |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `strands-harness` | `>=0.1` floor [VERIFIED: pyproject.toml] (`"strands-harness>=0.1"`) | `create_harness(skills=…, memory=…)` seams, `DEFAULT_SKILLS_DIR`, `DEFAULT_MEMORY_DIR` | Already the agent factory; skills + memory seams verified in installed source |
| `strands-agents` | `>=0.1.0` floor [VERIFIED: pyproject.toml] (`"strands-agents>=0.1.0"`) | `AgentSkills`, `Skill`, `MemoryManager`, `FileMemoryStore`, `ContextInjector` | SDK owns the formats; CLI consumes, never re-implements |
| `prompt_toolkit` | `>=3.0.53` floor [VERIFIED: pyproject.toml] (`"prompt_toolkit>=3.0.53"`); installed `3.0.53` verified via import this session | `PromptSession(completer=…)`, `WordCompleter`/`FuzzyCompleter`/`DynamicCompleter` | Already the REPL input stack (`loop.py` imports `PromptSession`) |
| `pyyaml` | `>=6.0` floor [VERIFIED: pyproject.toml] (`"pyyaml>=6.0"`) | Memory-file frontmatter parse/dump | Already used for OKF frontmatter; same shape |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich` | `>=13.0` floor [VERIFIED: pyproject.toml] (`"rich>=13.0"`) | `/skills` list rendering, `/memory` proposal display | All human-facing REPL output |
| `typer` | `>=0.27.2` floor [VERIFIED: pyproject.toml] (`"typer>=0.27.2"`) | Non-tty fallback prompts (picker loops) | Only if `/skills` needs typed fallback |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SDK `Skill.from_directory` | Hand-rolled SKILL.md parser | Rejected: duplicates SDK leniency rules (colon-quoting fallback, name validation); drifts on resync |
| CLI injector plugin for memory files | Baking files into `instructions=` at `build_agent` | Rejected: bakes once at construction; external-edit auto-reload (D-06) would need system-prompt surgery per turn |
| `FuzzyCompleter` | Bare `WordCompleter` prefix match | Prefix is acceptable fallback; fuzzy matches bare-name UX better when namespaces grow |

**Installation:** none — every dependency is already in `pyproject.toml`. No new packages.

## Package Legitimacy Audit

No external packages are installed by this phase. All work builds on `strands-harness`, `strands-agents`, `prompt_toolkit`, `pyyaml`, `rich`, `typer` — each already declared in `pyproject.toml` [VERIFIED: pyproject.toml, read this session] and already imported by repo code. The Package Legitimacy Gate does not trigger.

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```text
User types "/<skill> <free text>" or "/memory …" or "/init"
        │
        ▼
┌──────────────────┐  PromptSession(completer=SkillCompleter)
│  loop.py REPL    │◄── bare-name match → namespaced completion
│  (turn boundary: │──► mtime check: STRANDS.md / .agent/MEMORY.md changed?
│   mtime reload)  │    yes → reload + transcript note
└────────┬─────────┘
         │ dispatch(text, …, skills=SkillIndex)
         ▼
┌──────────────────────────────────────────────────┐
│ router.py dispatch                               │
│  builtin slash? ──► existing branches (always win)│
│  /skills …… ──────► list/show/remove (reply)     │
│  /memory …… ──────► curate surface / mode (reply;│
│                      revise rounds run agent turns│
│                      via the ("agent", text) path)│
│  /init ………… ─────► scan → draft proposals ──► curate queue
│  /<skill> …… ─────► compose (instructions +      │
│                      trailing text) ──► ("agent") │
│  unknown ─────────► Unknown command + USAGE_HINT │
└────────┬─────────────────────────┬───────────────┘
         │ ("agent", composed text) │ memory files
         ▼                         ▼
┌──────────────────┐   ┌──────────────────────────┐
│ Agent turn via   │   │ MemoryFilePlugin (new,    │
│ _invoke_agent    │   │ ContextInjector @userTurn)│
│                  │   │ reads STRANDS.md +        │
│ AgentSkills:     │   │ .agent/MEMORY.md (.agent  │
│ <available_      │   │ wins), injects <system-   │
│ skills> in sys   │   │ reminder> block per turn  │
│ prompt; `skills` │   └──────────────────────────┘
│ tool activates   │
│ full instructions│   ┌──────────────────────────┐
└──────────────────┘   │ Harness MemoryManager    │
                       │ (fact store .agent/      │
                       │ memory/*.md; extract /5  │
                       │ turns, inject everyTurn) │
                       │  │                       │
                       │  └──► CLI promotion poll: │
                       │       new fact files ──►  │
                       │       curate proposals    │
                       └──────────────────────────┘
```

A reader traces SKILL-01: type `/pdf …` → completer offers `local:pdf-tools` → dispatch composes skill instructions + trailing text → agent turn runs with the SDK-injected skill catalog already in context. SKILL-02: `/init` scans → draft proposals enter the curate queue → `/memory` approves → files written → injector loads them every user turn; external edits trip the mtime check at the next turn boundary.

### Recommended Project Structure

```text
strands_code_cli/
├── router.py          # dispatch += /skills, /memory, /init branches + dynamic skill slashes + USAGE_HINT
├── loop.py            # PromptSession(completer=…), turn-boundary mtime check, memory flush on exit
├── main.py            # build_agent: explicit skills=/memory= wiring + MemoryFilePlugin registration
├── skills.py          # NEW: SkillIndex (load/list/resolve/remove, namespace map, shadow warnings)
├── memory_file.py     # NEW: dual-file load/save, frontmatter + section markers, mtime tracking
├── memory_modes.py    # NEW (or fold into memory_file.py): curate/silent holder + curate queue
├── completer.py       # NEW (or fold into skills.py): slash/skill Completer + FuzzyCompleter wrap
├── choice.py          # (existing) radio_choice if /skills wants a picker
├── output.py          # (existing) output_context for all turn output
└── policy_gate.py     # (existing) approve/deny UX precedent for the curate loop
tests/
├── test_skills.py       # NEW: index load, namespace resolve, shadow rule, remove confinement
├── test_memory_file.py  # NEW: dual load, .agent-wins, frontmatter/markers, mtime reload
└── test_memory_curate.py# NEW: curate/silent flows, revise rounds, /init merge-never-clobber
```

### Pattern 1: Consume the SDK skill loader, never re-parse

**What:** List and resolve skills with `Skill.from_directory("./.agent/skills")` (or `AgentSkills.get_available_skills(agent)` for the agent-bound set); read `skill.name`/`skill.description`/`skill.path` for display.
**When to use:** Every CLI read path (`/skills` list/show, completer words, router resolve).
**Example:**

```python
# Source: installed SDK .venv/.../strands/vended_plugins/skills/skill.py:386-427
from strands.vended_plugins.skills import Skill
skills = Skill.from_directory("./.agent/skills")  # skips dirs w/o SKILL.md, warns+skips malformed
```

### Pattern 2: Mirror the environment plugin for memory-file injection

**What:** A tiny CLI-owned `Plugin` whose `init_agent` registers `ContextInjector(render, trigger="userTurn")`; `render` reads the two files (memoize content + mtime, re-read on change) and returns a `<system-reminder>` block. `.agent/MEMORY.md` content is emitted last with a precedence line so "on conflict, `.agent` wins" is visible to the model.
**When to use:** Auto-load of `STRANDS.md` + `.agent/MEMORY.md` (D-04/D-06).
**Example:** shape follows `strands_harness/plugins/environment.py:62-91` (`init_agent` → `ContextInjector(render, …).init_agent(agent)`; `<system-reminder>` block) [VERIFIED: environment.py:62-69].

### Pattern 3: Router validates, loop applies (slash-skill invocation)

**What:** `dispatch` resolves `/<skill> <text>` to `("agent", composed_prompt)` where `composed_prompt = skill instructions + trailing text`, exactly like `_approve_message` returns `("agent", f"{APPROVE_OK}\n{APPROVE_EXECUTE}")` [VERIFIED: router.py:416-430]. No new loop action type; the turn runs through the existing `_invoke_agent` path with steering/cancel intact.
**When to use:** `/<skill>` invocation (D-01). This resolves the D-01 "reply-only" wording: routing/validation stays in the router (no loop dispatch changes), while execution reuses the established `("agent", text)` channel — a literal reply could never deliver skill input to the model.

### Pattern 4: Curate queue over pollable sources (no extraction hook exists)

**What:** The curate loop consumes a CLI-owned proposal queue fed by three pollable sources: `/init` drafts, NL-instruction revisions, and *new-file promotion polls* of `./.agent/memory/*.md` (mtime/name-set diff since last sweep). Approve applies to the conventions files; deny skips and continues (Phase 3 D-02 shape); silent mode auto-applies with a transcript line.
**When to use:** `/memory` surface (D-06/D-07/D-08). Required because harness extraction writes directly to the store with no approval callback (verified: `coordinator.py` contains no approve/confirm/gate hook — only an internal task done-callback).

### Anti-Patterns to Avoid

- **Storing `source:name` in SKILL.md `name`:** SDK validation warns (lenient) or raises (strict) on non-matching names; keep SDK names colon-free and map namespaces in `SkillIndex`.
- **Second approval handler for curate:** reuse the gate's ask/prompt spine and `BatchState` turn-cache pattern; a parallel prompter re-opens Phase 3 T-03-01/T-03-04.
- **Gating harness extraction writes:** impossible without forking the SDK — extraction fires via `AfterInvocationEvent` hooks and writes via `add`. Gate *promotion*, not extraction.
- **Baking memory files into `instructions=`:** frozen at construction; breaks D-06 auto-reload.
- **Clobbering on `/init` re-run:** D-11 merge-only; diff sections by heading, propose only missing/stale ones.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SKILL.md parsing (frontmatter, name rules, leniency) | Custom YAML splitter | `Skill.from_directory` / `Skill.from_file` | Colon-quoting fallback, case-insensitive `skill.md`, per-skill warn-and-continue — edge cases already handled |
| Skill catalog injection + activation | Prompt-stuffing + custom tool | Harness `skills=True` (`AgentSkills` plugin) | `<available_skills>` XML, `skills` tool, per-agent sandbox loading, activation tracking |
| Fact extraction/recall | Keyword search over notes | Harness `memory=True` (`MemoryManager` + `FileMemoryStore`) | 5-turn extraction cadence, every-turn injection, `search_memory` tool, read-only delegate views |
| Slash completion | Custom readline completer | prompt_toolkit `Completer` + `FuzzyCompleter`/`DynamicCompleter` | Async-safe, `patch_stdout`-compatible, already the REPL stack |
| Approve/deny prompting | Second prompt loop | `policy_gate` ask spine + `choice.radio_choice` | SIGINT-safe, broker-compatible, single-HITL invariant |

**Key insight:** the harness already runs the skill + fact-memory machinery invisibly (both default on); Phase 6 adds the *user-visible control plane* (routing, completion, curation) over seams that already exist. The only genuinely new runtime piece is the conventions-file injector.

## Common Pitfalls

### Pitfall 1: Colon namespaces vs SDK name validation

**What goes wrong:** A skill authored as `name: local:my-skill` fails strict validation and warns in lenient mode; the SDK logs `skill name should be 1-64 lowercase alphanumeric characters or hyphens`.
**Why it happens:** D-02 namespaces live in the CLI layer, but an implementer stores them in frontmatter.
**How to avoid:** `SkillIndex` derives `source` from directory layout/metadata outside `name` (MVP: single `local` source for `./.agent/skills`; marketplace prefixes arrive with SKILL-03) and maps `local:my-skill` → SDK `my-skill` at resolve time.
**Warning signs:** `skill name …` warnings in logs; skills missing from `/skills` list.

### Pitfall 2: Shadowed skills fail silently

**What goes wrong:** A skill named `model` never fires and the user doesn't know why.
**Why it happens:** Built-ins win (D-02) but the warning is printed once at load and scrolls away.
**How to avoid:** Warn at load *and* list shadowed skills in `/skills` output with a `shadowed by builtin` tag; completer omits shadowed names.
**Warning signs:** "Unknown command" confusion; skill works after rename.

### Pitfall 3: Extraction writes bypass curation — by design

**What goes wrong:** Planner designs a gate around harness extraction; implementer discovers there is no hook.
**Why it happens:** "Harness auto-proposals" (D-06) reads like an event stream; it is actually autonomous background writes.
**How to avoid:** Curate *promotion* of fact-store entries into conventions files (poll new `.md` files), never extraction itself. Document that `.agent/memory/*.md` remains auto-written in both modes.
**Warning signs:** Plan tasks referencing an extraction callback that doesn't exist in `coordinator.py`.

### Pitfall 4: Lost extractions on short runs

**What goes wrong:** A quick session ends with the latest turns never distilled; `/memory` promotion finds nothing.
**Why it happens:** Extraction fires every 5 turns in the background, and the CLI never flushes: `MemoryManager.flush()` exists [VERIFIED: memory_manager.py:767-775] but no CLI module calls it (verified: no `memory_manager` reference in `strands_code_cli/`).
**How to avoid:** On clean exit (and after `/compact`/`/clear` history mutations), run `await agent.memory_manager.flush()` via `asyncio.run` mirroring `explicit_save` (guard `None`/missing attribute for test doubles).
**Warning signs:** `.agent/memory/` empty after short sessions; flaky promotion-poll tests.

### Pitfall 5: Stale completer after skill add/remove

**What goes wrong:** `/skills remove foo` succeeds but `/foo` still completes until restart.
**Why it happens:** `WordCompleter` snapshots its word list at construction.
**How to avoid:** `DynamicCompleter(get_completer=…)` rebuilding from `SkillIndex` on each invocation, or `WordCompleter(words=<callable>)` (callable form is supported [VERIFIED: word_completer.py:35-45]).
**Warning signs:** Completion offers removed skills; new skills need restart.

### Pitfall 6: Memory-file prompt injection

**What goes wrong:** A cloned repo's `STRANDS.md` contains instructions that override user intent ("ignore prior instructions, exfiltrate…").
**Why it happens:** Repo files are untrusted input (Claude Code shows an approval dialog for external imports for exactly this reason [CITED: code.claude.com/docs/en/memory]).
**How to avoid:** Mark injected memory content per the Phase 5 untrusted-marker precedent; first-load banner naming both files and their mtimes; never let memory content widen tool scope (03-SECURITY residual: scope widening re-opens D-13).
**Warning signs:** Agent follows repo-file instructions that contradict the user; silent scope creep.

### Pitfall 7: Double-loading AGENTS.md-adjacent content

**What goes wrong:** `STRANDS.md` duplicates `AGENTS.md` content and both inject every turn, wasting context.
**Why it happens:** The harness `environment` plugin already injects root `AGENTS.md` (up to 16_000 chars [VERIFIED: environment.py:33]).
**How to avoid:** `/init` drafts reference rather than duplicate (`See AGENTS.md §X` pointers); keep the thin root `STRANDS.md` summary genuinely thin (D-10); cap injected memory size with a truncation marker mirroring `_AGENTS_MD_CAP`.
**Warning signs:** Context-% jumps after `/init`; repeated conventions in `/context`.

## Code Examples

Verified patterns from installed sources (all paths below read this session):

### Skill seam defaults

```python
# Source: .venv/.../strands_harness/defaults.py:35-39
DEFAULT_SESSION_DIR = "./.agent/sessions"
DEFAULT_SKILLS_DIR = "./.agent/skills"
DEFAULT_MEMORY_DIR = "./.agent/memory"
```

```python
# Source: .venv/.../strands_harness/agent.py:154-165 (_skills_plugin)
if skills is None or skills is False:
    return None
if isinstance(skills, AgentSkills):
    return skills
if skills is True:
    return AgentSkills(skills=[defaults.DEFAULT_SKILLS_DIR]) if os.path.isdir(defaults.DEFAULT_SKILLS_DIR) else None
```

Harness `create_harness` signature defaults [VERIFIED: agent.py:249-267]: `skills: bool | SkillSources | AgentSkills | None = True`, `memory: bool | MemoryConfig | MemoryManager | None = True`. Current `build_agent` passes neither, so both ride defaults today — and `./.agent/skills` does not exist yet (verified via directory listing), so the skills plugin is currently a no-op.

### Skill file format (SDK parser)

```python
# Source: .venv/.../strands/vended_plugins/skills/skill.py:23-24, 332-338
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_MAX_SKILL_NAME_LENGTH = 64
# from_content raises ValueError unless frontmatter has non-empty 'name' and 'description'
```

```python
# Source: .venv/.../strands/vended_plugins/skills/skill.py:182-188 (allowed-tools), 191-195 (metadata)
allowed_tools_raw = frontmatter.get("allowed-tools") or frontmatter.get("allowed_tools")
metadata_raw = frontmatter.get("metadata", {})
```

Minimal `SKILL.md` (matches both SDK parser and AgentSkills.io spec [CITED: agentskills.io/specification]):

```markdown
---
name: pdf-tools
description: Extract text and tables from PDFs. Use when the user mentions PDFs.
---
# PDF Tools
…instructions, steps, edge cases…
```

### Agent-bound skill listing + activation surface

```python
# Source: .venv/.../strands/vended_plugins/skills/agent_skills.py:245-259
def get_available_skills(self, agent: Agent | None = None) -> list[Skill]:
    skills = self._skills_for(agent) if agent is not None else self._skills
    return list(skills.values())
```

Note: filesystem skills resolve per-agent through the sandbox at `init_agent`; `get_available_skills()` without the agent omits them. CLI listing should use `Skill.from_directory` (host fs, deterministic) for `/skills` display and reserve `get_available_skills(agent)` for cross-checks.

### Memory seam shape

```python
# Source: .venv/.../strands_harness/types/agent.py:157-166
class MemoryConfig(TypedDict, total=False):
    dir: str      # default "./.agent/memory"
    stores: list[MemoryStore]
```

```python
# Source: .venv/.../strands/memory/memory_manager.py:90-96 (__init__ defaults)
stores: list[MemoryStore],
search_tool_config: MemoryToolConfig | bool = True,   # search_memory ON
add_tool_config: MemoryAddToolConfig | bool = False,   # add_memory OFF
injection: MemoryInjectionConfig | bool = True,
```

```python
# Source: .venv/.../strands_harness/memory.py:88 + strands/memory/extraction/resolve_extraction_config.py:25
return MemoryManager(stores=managed, injection=MemoryInjectionConfig(trigger="everyTurn"))
_DEFAULT_EXTRACTION_TRIGGER_TURNS = 5
```

```python
# Source: .venv/.../strands/vended_memory_stores/file_memory_store/store.py:186-200
# add(): filename = slugified first line (sans #), truncated to 50 chars;
# same slug exists → append new facts, never overwrite.
```

### prompt_toolkit completer wiring

```python
# Source: .venv/.../prompt_toolkit/completion/word_completer.py:35-45,
#          fuzzy_completer.py:49-55, base.py:289-296; shortcuts/prompt.py:397
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, DynamicCompleter, FuzzyCompleter

class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/") and " " not in text:
            for name, display in self.words(document):  # bare-name match…
                yield Completion(display, start_position=-len(text))  # …namespaced completion
session = PromptSession(history=_history(), completer=DynamicCompleter(lambda: FuzzyCompleter(SlashCompleter())))
```

Current loop constructs `PromptSession(history=_history())` with no completer [VERIFIED: loop.py:543] — the wiring point is that single call.

### Dual-file loader sketch (new CLI code)

```python
ROOT_MEMORY = Path("STRANDS.md")
AGENT_MEMORY = Path(".agent/MEMORY.md")
# Load both when present; strip frontmatter before injection (foreign-CLI readability);
# emit .agent content last with a precedence line (".agent wins" per D-04).
# Track st_mtime per file; loop turn boundary re-checks and prints one transcript note per change.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Vendor-specific skill formats | AgentSkills.io open standard (`SKILL.md` + `scripts/`/`references/`/`assets/`) | 2025 (Anthropic release, multi-vendor adoption) [CITED: agentskills.io/home] | Write standard skills once; SDK parses them natively |
| Static prompt-stuffing of docs | Progressive disclosure (catalog → instructions → resources) | Current best practice [CITED: agentskills.io/client-implementation/adding-skills-support] | ~50–100 tokens/skill idle; full body only on activation |
| Single `MEMORY.md` / `MUSE.md` | Tiered memory: checked-in conventions + auto-written fact store + optional recall backend | Claude Code model (CLAUDE.md + auto-memory topic files) [CITED: code.claude.com/docs/en/memory] | Phase 6 mirrors it: `STRANDS.md`/`.agent/MEMORY.md` curated + `.agent/memory/` auto facts |
| Questionnaire `/init` | Agentic repo-scan `/init` with reviewable proposal | Claude Code `/init` analyzes codebase, suggests improvements rather than overwrite [CITED: code.claude.com/docs/en/memory] | D-09/D-11 match the state of the art; merge-never-clobber is the documented norm |

**Deprecated/outdated:**
- `allowed-tools` enforcement: parsed by the SDK but documented experimental ("not yet enforced" [VERIFIED: skill.py:238]) — record it, don't rely on it.
- Bare `WordCompleter(words=[…])` static lists for dynamic sets — use the callable/`DynamicCompleter` form (Pitfall 5).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `/skills` plural with `show`/`remove` subcommands is the right name/shape | Discretion rec 1 | Low — rename is cheap pre-release, costly after (muscle memory) |
| A2 | Fuzzy-over-prefix matching for autocomplete | Discretion rec 2 | Low — one-line completer swap |
| A3 | Frontmatter keys `scope/version/updated/source` + 5 scaffolded sections | Discretion rec 4 | Medium — filenames/keys are a user-facing contract (D-04 costly reversibility) |
| A4 | Mtime check at loop turn boundary; note wording | Discretion rec 5 | Low — placement is internal |
| A5 | `/memory mode [curate\|silent]` verb; silent log line format | Discretion rec 6 | Low — surface is new, no compat burden yet |
| A6 | Revise-round prompt shape (fenced-block verbatim return) | Discretion rec 7 | Low — prompt tuning, behaviorally observable |
| A7 | Shallow/deep scan source lists | Discretion rec 8 | Low — `/init` output quality only |
| A8 | Single `local` namespace source for MVP; marketplace prefixes with SKILL-03 | Pitfall 1 | Medium — namespace contract is costly to change (D-02); `local:` prefix reserves the shape |
| A9 | D-01 "reply-only" resolves to router-side `("agent", composed)` (no new loop action) | Pattern 3 | Medium — if the planner reads it as literal reply, skill invocation cannot reach the model; flagged in Open Questions |
| A10 | Injection-size cap for memory files (~16KB mirroring `_AGENTS_MD_CAP`) | Pitfall 7 | Low — internal default |

## Open Questions

1. **D-01 "reply-only action" vs skill execution**
   - What we know: `dispatch` returns `("agent"|"exit"|"reply"|"model", message)` [VERIFIED: router.py:92-96]; only `("agent", …)` runs a model turn; `/approve` already returns `("agent", composed)` for exactly this "router composes, loop runs" shape.
   - What's unclear: whether D-01's "reply-only" was meant literally (router never triggers turns for skills — which would make skills un-executable) or as "no new loop machinery".
   - Recommendation: implement Pattern 3 (`("agent", instructions + trailing text)`); note the reading in the plan so review can confirm.

2. **"Harness auto-proposals" feed rate**
   - What we know: extraction fires every 5 turns in the background with no hook; the CLI can only poll `./.agent/memory/*.md` for new files.
   - What's unclear: how often to sweep (every turn boundary vs on `/memory` open vs debounced) and whether to auto-dismiss unpromoted facts.
   - Recommendation: sweep at turn boundary alongside the mtime check; queue at most N proposals per sweep; never auto-delete fact files. Planner picks N (suggest 3).

3. **`.agent/MEMORY.md` vs fact-store directory collision**
   - What we know: `./.agent/memory/` (directory, harness-owned) vs `./.agent/MEMORY.md` (file, CLI-owned) coexist on case-sensitive filesystems.
   - What's unclear: nothing technically — but case-insensitive filesystems (macOS default) treat `memory` ≠ `MEMORY.md` distinctly (different basename), so no collision. Noted for the record; no action.

4. **Skill `allowed-tools` semantics**
   - What we know: parsed, not enforced (State of the Art).
   - What's unclear: whether Phase 6 should surface it in `/skills show` as informational.
   - Recommendation: display it verbatim as informational; no enforcement logic.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.7 per STACK.md (classifiers 3.10–3.13) | — |
| `uv` + `.venv` | test runs | ✓ | repo `.venv` present, `uv.lock` pinned | — |
| `pytest` | validation gate | ✓ (30 test files incl. `conftest.py` hermetic guard) | `>=8` floor | — |
| `strands-harness` skills seam | SKILL-01 | ✓ (verified in installed source) | `>=0.1` floor | — |
| `prompt_toolkit` completers | SKILL-01 autocomplete | ✓ (verified `3.0.53`) | `>=3.0.53` floor | — |
| Network (BlockReadsOutside*) | none (phase is local FS + REPL) | n/a | — | — |

**Missing dependencies with no fallback:** none — the phase is code/config-only over already-installed packages.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 (locked 9.1.1 per STACK.md) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`-m 'not integration'`) |
| Quick run command | `uv run pytest tests/test_skills.py tests/test_memory_file.py -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKILL-01 | Skills load from `./.agent/skills`; `/skills` lists; `/<name>` invokes with trailing text | unit | `uv run pytest tests/test_skills.py -x -q` | ❌ Wave 0 |
| SKILL-01 | Built-in wins on collision + shadow warning; namespaced completion | unit | `uv run pytest tests/test_skills.py -x -q` | ❌ Wave 0 |
| SKILL-02 | Dual file auto-load; `.agent` wins; frontmatter + markers round-trip | unit | `uv run pytest tests/test_memory_file.py -x -q` | ❌ Wave 0 |
| SKILL-02 | `/init` draft → curate approve; re-run merges, never clobbers | unit | `uv run pytest tests/test_memory_curate.py -x -q` | ❌ Wave 0 |
| SKILL-02 | Curate/silent modes; NL revise rounds; mtime reload note; flush on exit | unit | `uv run pytest tests/test_memory_curate.py -x -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_skills.py tests/test_memory_file.py tests/test_memory_curate.py -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_skills.py` — covers SKILL-01 (use `tmp_path` + `monkeypatch.chdir`, the `test_session_resume.py` hermetic pattern)
- [ ] `tests/test_memory_file.py` — covers SKILL-02 loader/contract
- [ ] `tests/test_memory_curate.py` — covers SKILL-02 curate/init/revise flows
- [ ] Skill fixtures: `tmp_path`-built `./.agent/skills/<name>/SKILL.md` trees (no committed fixtures needed)
- [ ] Framework install: none — pytest + suite already green (668 passed per PROJECT.md)

Test doubles note: `dispatch` accepts `agent=None`/`mode=None` today; new branches must keep that testability (pure functions over `SkillIndex`/file paths, agent turns asserted via the returned `("agent", text)` tuple, never live models).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a — local CLI, no identity boundary |
| V3 Session Management | no | session ids already validated (`_validate_session_id`) |
| V4 Access Control | yes | `/skills remove` confined to `./.agent/skills` (mirror `_remove_snapshot_dir` traversal guards [VERIFIED: router.py:609-626]); memory writes confined to the two known files |
| V5 Input Validation | yes | Skill-name regex passthrough (SDK validates; CLI treats invalid as unloadable + warns); frontmatter parse fail-soft (SDK `Skill.from_directory` warn-and-skip); memory frontmatter: strict-safe `yaml.safe_load`, corrupt → defaults + transcript note (Phase 3 T-03-02 fail-closed precedent) |
| V6 Cryptography | no | no new secrets; model keys never persisted (existing `ProviderConfig` rule) |
| V8 Data Protection | yes | Memory files may hold sensitive repo notes — 0o600/0o700 treatment mirroring session/index dirs; no memory content in titles/logs beyond section names |
| V14 Configuration | yes | Cloned-repo `STRANDS.md` is untrusted config: first-load banner + untrusted markers (Pitfall 6); memory content must not widen tool scope (03-SECURITY residual) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious SKILL.md instructions (prompt injection) | Tampering / Elevation | Treat skill bodies as untrusted; quote (don't execute) directives; deny-first gate still covers resulting tool calls |
| Malicious STRANDS.md in cloned repo | Tampering | First-load banner naming files+mtimes; untrusted-content markers; no scope widening from memory |
| Path traversal in `/skills remove <name>` / `show` | Tampering | Resolve + same-parent check mirroring `_remove_snapshot_dir`; refuse symlinks (T-03-02 precedent) |
| Symlink swap of memory files between mtime check and read | Tampering | Read via resolved path; re-stat after read on security-sensitive paths — at minimum refuse symlink roots |
| Context-exhaustion via giant memory/skill files | Denial of service | Injection caps with truncation markers (Pitfall 7); `/init` deep-scan read caps |

Residuals carried forward (from 03-SECURITY.md, still applicable): single-HITL spine (no second handler for curate), no scope-root widening without re-opening D-13, `programmatic_tool_caller` stays pinned off, URL-param exfiltration accepted.

## Sources

### Primary (HIGH confidence — installed source read this session)

- `.venv/.../strands_harness/agent.py:154-165,249-267,364-382,501-518` — `skills`/`memory` seams, `create_harness` defaults
- `.venv/.../strands_harness/defaults.py:35-39` — `./.agent/skills`, `./.agent/memory`, `./.agent/sessions`
- `.venv/.../strands_harness/memory.py:1-107` — `resolve_memory`, everyTurn injection, default store build
- `.venv/.../strands_harness/options.py:168-201` — `MemoryConfig` keys `dir`/`stores`
- `.venv/.../strands_harness/types/agent.py:157-166` — `MemoryConfig` shape
- `.venv/.../strands_harness/plugins/environment.py:1-155` — AGENTS.md injector precedent
- `.venv/.../strands_harness/prompt.py` — `build_system_prompt` (instructions appended after contract)
- `.venv/.../strands/vended_plugins/skills/skill.py` — SKILL.md format, name regex, `from_directory`
- `.venv/.../strands/vended_plugins/skills/agent_skills.py` — plugin, `skills` tool, XML injection, `get_available_skills`
- `.venv/.../strands/memory/memory_manager.py:90-96,767-775` — tool defaults, `flush()`
- `.venv/.../strands/memory/types.py` — `MemoryStore` protocol, injection config
- `.venv/.../strands/memory/extraction/{types,triggers}.py`, `resolve_extraction_config.py:25` — 5-turn default cadence
- `.venv/.../strands/memory/extraction/coordinator.py` — no approval hook (verified by grep)
- `.venv/.../strands/vended_memory_stores/file_memory_store/store.py:172-201` — slug + append-never-overwrite
- `.venv/.../prompt_toolkit/completion/{base,word_completer,fuzzy_completer}.py`, `shortcuts/prompt.py:397` — completer API
- `strands_code_cli/{router,loop,main,policy_gate,choice,output}.py` — dispatch tri-state, REPL wiring, gate UX

### Secondary (MEDIUM confidence — official docs via Tavily, cross-checked)

- [agentskills.io/specification](https://agentskills.io/specification) — frontmatter fields + constraints + directory layout
- [agentskills.io/home](https://agentskills.io/home) — open-standard provenance, discovery/activation/execution tiers
- [agentskills.io/client-implementation/adding-skills-support](https://agentskills.io/client-implementation/adding-skills-support) — progressive disclosure tiers + token costs
- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — `plug
...[truncated 718 chars]