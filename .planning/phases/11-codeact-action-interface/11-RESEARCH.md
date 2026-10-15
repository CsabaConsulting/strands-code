# Phase 11: CodeAct Action Interface - Research

**Researched:** 2026-10-15
**Domain:** Opt-in code-generation-first action interface for a Strands-harness CLI (session toggles, whole-block deny-first approval, sandboxed Python execution)
**Confidence:** HIGH

> Note on provenance: the `gsd_run` research-plan/classify-confidence seam is not installed in this
> environment (generic-agent workaround dispatch), so confidence tiers below are assigned directly per
> the documented tag semantics. All in-repo claims were read from source this session; web claims were
> fetched via Tavily this session.

## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Opt-in surface
- **D-01:** `/codeact` slash command is the primary interface switch (session toggle, like other session toggles).
- **D-02:** All three selection surfaces exist: `--codeact` startup flag, a config key, and `/codeact`.
- **D-03:** Every session starts on tool-calling; a global config option may switch the behavior to remember-last-choice. — **Reversibility:** costly — the default posture shapes the turn loop and session-start contract; flipping the default later changes every-session behavior.
- **D-04:** Mode-system integration only if it fits naturally without upsetting other mode logic; otherwise slash + flag + config only.

#### Approval reconciliation
- **D-05:** Approvals gate the whole generated code block before execution (diff-like code preview, one prompt per code action). No per-effect prompts inside execution. — **Reversibility:** one-way — the approval-unit contract shapes the executor boundary and the prompt UX; splitting it later breaks the preview/approve interaction users learn.
- **D-06:** On denial, the agent revises: the denial feeds back and the agent can revise the code or try a different approach (the turn stays alive).
- **D-07:** Remembered Always/Never rules apply to CodeAct approvals exactly like tool approvals — one rule system.
- **D-08:** Approval prompts appear at the code-action boundary only, never nested inside a running orchestration step.

#### CodeAct scope
- **D-09:** Full tool parity: generated code can call the same file/edit/shell tools as functions.
- **D-10:** Sandboxed local backend — reuse the library's `SandboxedPythonInterpreter` (smolagents allowlist + timeout); offline-safe, no new required backend.
- **D-11:** REPL state (variables, imports) persists across code actions within a CodeAct stint.
- **D-12:** Keep the library timeout defaults (180s agent / 60s interpreter); no user-visible timeout setting this phase.

#### Both-mode meaning
- **D-13:** "Both" means the user routes per ask at send time — explicit, no model guessing. — **Reversibility:** costly — user-routed vs model-routed shapes the send path and turn setup; changing it later reworks the ask pipeline.
- **D-14:** One interface per turn; the turn's interface is fixed when the ask is sent (no mixing tool calls and code actions within a turn).
- **D-15:** The transcript labels each turn with the interface used (tool/codeact).
- **D-16:** `/cost` rows are identical for both interfaces — no interface column or split.

#### Mid-session switching
- **D-17:** Switching interfaces resets the REPL; each CodeAct stint starts fresh.
- **D-18:** Remembered approval rules carry across switches unchanged.
- **D-19:** Switches apply at the next ask only; a running turn always finishes on its starting interface.
- **D-20:** Full conversation history is preserved across switches; only the action interface changes.

### Agent's Discretion

No "you decide" items — the user answered every question directly. Naming of the config key, exact `/codeact` UX wording, and transcript label format are left to planner/executor judgment within the locked decisions above.

### Deferred Ideas (OUT OF SCOPE)

- Per-effect sandbox-pausing approvals (prompt when generated code attempts a side effect mid-execution) — considered during discussion, explicitly rejected; do not resurrect without re-discussing.
- AgentCore remote execution backend as a CodeAct option — not discussed; local-only this phase.
- Model-picks-interface-per-step ("both" as automatic) — rejected in favor of user routing (D-13).

None of the above belong in Phase 11 scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-07 | User can opt into code-generation-first (CodeAct) actions reconciled with deny-first approvals; tool-calling stays the default and CodeAct is never mandatory | Session-toggle holder pattern (§Pattern 1), whole-block approval via existing HITL `python_repl` path (§Pattern 3), stint-scoped `SandboxedPythonInterpreter` with interior file/shell functions (§Pattern 4), per-turn interface fixing at send (§Pattern 2) |

## Project Constraints (from AGENTS.md)

Actionable directives extracted from `./AGENTS.md` (read this session). Treat with the same authority as locked decisions:

- **Stack:** Python >= 3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform.
- **AWS posture:** AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports. (Reinforces D-10 local-only.)
- **Compatibility:** No upper pins during the experimental phase; resync upstream deliberately.
- **Conventions:** `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants; absolute imports rooted at `strands_code_agent` / `strands_code_cli`; no relative imports.
- **No formatter/linter configured** — match surrounding file style by hand (4-space, double quotes, ~100–120 col).
- **Error handling:** interpreters return `(stdout, stderr)` tuples, never raise to the agent; salvage partial output; fail-soft on read paths; log-and-continue only for best-effort cleanup.
- **Logging:** `rich` only for human-facing transcript rendering; never `print()` in library code (CLI transcript code uses `print_plain` with markup off); no new logging on the `python_repl` observation path.
- **Comments:** one-to-two-line why-notes only; triple-double-quoted docstrings with `Args:`/`Returns:` on public units.
- **Architecture:** execution backends stay swappable behind the `PythonInterpreter` ABC; single-threaded sync model; per-call timeouts bound long runs.
- **No project skills** — all five skill dirs (`.claude/skills`, `.agents/skills`, `.cursor/skills`, `.github/skills`, `.codex/skills`) are absent (verified this session); no skill patterns to follow.
- **GSD workflow:** edits flow through GSD commands (planner/executor concern, not research).

## Summary

Phase 11 adds an opt-in CodeAct action interface to a CLI whose turn loop, approval gate, and session toggles are mature (Phases 1–10). Almost every building block already exists in-repo: the `SandboxedPythonInterpreter` execution backend (D-10), the single-HITL deny-first approval gate with Always/Never remembered rules (D-05/D-07), the session-sticky toggle-holder pattern (`ModeState`, `RoutingState`, `MemoryModeState`) for `/codeact` (D-01), the per-turn input-prefix pattern (`PLAN_PREFIX`) for per-turn interface shaping (D-14), and the `ProviderConfig` YAML + typer-flag precedents for the config key and `--codeact` flag (D-02).

The research-validated shape is: a loop-owned interface holder (`tool`/`code`/`both`, default `tool`) read once per turn at send time; CodeAct turns shaped by a code-first input prefix plus a stint-scoped `SandboxedPythonInterpreter` whose `additional_functions` expose sync, scope-confined file/shell operations (D-09); every generated code block approved through the existing HITL `python_repl` prompt with a full-code preview (D-05); denial returning the standard skip-and-continue verdict so the turn stays alive for revision (D-06). No new dependencies and no new backend: this phase is CLI wiring plus prompt/UX work over the library.

**Primary recommendation:** Build CodeAct as session-toggle + per-turn prompt shaping + stint-scoped interpreter reuse, gating whole blocks through the existing HITL `python_repl` path — no new packages, no SDK-private-API coupling, no history surgery.

Two reconciliations the planner must carry (both verified this session): (1) ROADMAP's "harness sandbox primitive" phrasing is superseded by locked D-10 (`SandboxedPythonInterpreter`; the SDK `strands.sandbox` ABC is async/Docker-oriented and out of scope). (2) D-05 + D-09 jointly force interior functions to be direct (ungated) sync implementations — the HITL `ask` cannot run inside execution (worker thread; blocking stdin there is fatal), and the gated `write`/`edit` wrappers are `async` + `tool_context`-bound, hence uncallable from the sync executor.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Interface selection (`/codeact`, flag, config) | CLI session | — | Session toggles are loop-owned holders; no agent/SDK involvement |
| Per-turn interface fixing | CLI turn loop | — | Read once at send time alongside `mode`/`routing` pre-turn hooks |
| Code-first turn shaping | CLI prompt assembly | — | Input-prefix pattern (`PLAN_PREFIX` precedent), no persistent agent mutation |
| Whole-block approval UX | CLI approval gate | — | Existing HITL `ask` path renders the preview; classifier unchanged |
| Remembered Always/Never rules | CLI policy store | — | One rule system (`policy.toml`); no new store |
| Code execution + REPL state | Library interpreter | — | `SandboxedPythonInterpreter` already owns state/timeout/allowlist |
| Interior file/shell functions | Library/CLI seam | — | Sync callables passed as `additional_functions`; scope-confined |
| Transcript labels + `/cost` rows | CLI transcript | — | `print_plain` post-turn label; cost rows untouched (D-16) |
| Conversation history | SDK agent (untouched) | — | D-20 forbids history surgery; interface is invocation-scoped only |

## Standard Stack

All CodeAct machinery is already in the dependency tree. **No new packages.**

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `smolagents` | 1.26.0 (installed, verified this session via `importlib.metadata`) | `LocalPythonExecutor` backing `SandboxedPythonInterpreter` (D-10) | Already the locked backend; allowlist + timeout + `additional_functions` verified by live probe |
| `strands-agents` | 1.58.1 (installed; AGENTS.md/lockfile cite 1.57.0 — minor drift, no API impact observed) | `Agent`, `@tool`, `ToolRegistry`, HITL interventions | The platform; CLI pads it, never forks it |
| `strands-harness` | 0.1.2 (installed) | `create_harness()` session-agent factory, builtin tools, session persistence | Sole agent-construction path (`main.build_agent`) |
| `typer` | 0.27.3 (installed) | `--codeact` startup flag | Existing CLI framework; `--session-id` precedent |
| `prompt-toolkit` | 3.0.53 (installed) | Approval dialogs (`radio_choice`), REPL input | Existing prompt/dialog stack |
| `platformdirs` | 4.12.3 (installed) | Config home for the CodeAct config key | `ProviderConfig`/`PolicyConfig`/`DiffConfig` precedent |
| `pyyaml` | 6.0.3 (installed) | `config.yaml` persistence | `ProviderConfig` precedent |
| `rich` | 15.0.0 (per AGENTS.md stack record) | Code-preview `Syntax` rendering | Callback-handler precedent |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 9.1.1 (installed; `test_mode.py` 32 passed this session) | Validation Architecture test runs | Every task commit + wave merge + phase gate |
| stdlib `difflib` | — | Diff-like code preview assembly | If the preview diffs old-vs-new REPL-affecting state; plain `Syntax` otherwise |
| stdlib `subprocess` | — | Interior `shell()` implementation | D-09 shell parity inside the executor (no `shell=True`) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `SandboxedPythonInterpreter` (D-10) | SDK `strands.sandbox.Sandbox` ABC (`PosixShellSandbox`/Docker) | Rejected by D-10: async API, Docker-oriented, new required backend; violates offline-safe + AWS-optional posture |
| `SandboxedPythonInterpreter` (D-10) | `ExecPythonInterpreter` (unrestricted `exec`) | Rejected: no allowlist/timeout boundary; D-10 locks the sandboxed backend |
| Per-turn prompt shaping | Per-turn `ToolRegistry` narrowing (remove non-CodeAct tools) | Weaker: the SDK exposes `register_tool`/`replace`/`register_dynamic_tool` but no public unregister [VERIFIED: `.venv/.../strands/tools/registry.py` method list read this session], so narrowing needs private-dict surgery; prompt shaping matches the `PLAN_PREFIX` precedent with zero private-API risk |
| Per-turn prompt shaping | `ToolChoice(tool=python_repl)` forcing | Wrong tool: `tool_choice` flows from model/stream config per model call [VERIFIED: `.venv/.../strands/models/bedrock.py:350,421`], not per-turn caller kwargs, and forcing a tool on *every* model call inside a multi-step turn breaks text/code interleaving |

**Installation:**

```bash
# Nothing to install — all CodeAct dependencies ship in the existing tree (D-10).
uv sync
```

## Package Legitimacy Audit

No external packages are installed by this phase. No registry lookups, no `postinstall` surface, no new supply-chain risk.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none — no new packages)* | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
                     ┌─────────────────────────────┐
                     │  Session start              │
                     │  --codeact flag / config key│
                     │  → interface holder = tool  │
                     └──────────────┬──────────────┘
                                    ▼
                     ┌─────────────────────────────┐
                     │  Idle prompt                │
                     │  /codeact flips holder      │
                     │  (next-ask only, D-19)      │
                     └──────────────┬──────────────┘
                                    ▼ user sends ask
                     ┌─────────────────────────────┐
                     │  Turn setup (fixed at send) │
                     │  holder → tool | code       │
                     │  both → user routes per ask │
                     │  code ⇒ CODEACT_PREFIX +    │
                     │         stint interpreter   │
                     └──────────────┬──────────────┘
                                    ▼
              ┌─────────────┐  turn runs  ┌──────────────────┐
              │ tool turn   │             │ codeact turn     │
              │ (unchanged  │             │ model emits code │
              │  default)   │             │ via python_repl  │
              └──────┬──────┘             └────────┬─────────┘
                     │                           ▼
                     │              ┌──────────────────────────┐
                     │              │ Whole-block approval     │
                     │              │ full-code preview +      │
                     │              │ [y/n/always/never] (D-05)│
                     │              └──────┬───────────┬───────┘
                     │                  approve      deny
                     │                     ▼           ▼
                     │              ┌──────────┐  ┌────────────────┐
                     │              │ execute  │  │ skip+continue; │
                     │              │ in stint │  │ model revises  │
                     │              │ REPL     │  │ (turn alive)   │
                     │              └──────────┘  └────────────────┘
                     │                           (D-06)
                     ▼
              ┌─────────────────────────────┐
              │  Turn boundary              │
              │  transcript label (D-15) +  │
              │  usage line; /cost rows     │
              │  unchanged (D-16)           │
              └─────────────────────────────┘
```

### Recommended Project Structure

No new top-level layout. Follow the established one-module-per-concern CLI shape:

```text
strands_code_cli/
├── codeact.py          # NEW: interface holder (ModeState mirror) + CODEACT_PREFIX +
│                       #      stint-interpreter lifecycle + interior functions
├── loop.py             # turn setup reads holder; post-turn label; reset-on-switch
├── router.py           # /codeact branch + USAGE_HINT entry
├── main.py             # --codeact flag → holder initial value
├── provider_config.py  # config key (extend _KNOWN_KEYS)
├── skills.py           # "codeact" joins BUILTIN_SLASH_HEADS
└── policy_gate.py      # full-code preview render in ask (python_repl detail)

tests/
└── test_codeact.py     # NEW: holder, routing, stint lifecycle, labels (Wave 0)
```

### Pattern 1: Session-Sticky Toggle Holder (D-01/D-03/D-19)

**What:** A tiny loop-owned holder class mirroring `ModeState`/`RoutingState`: validated values, `set()` returning the transcript announcement, `announce()` for the bare command. The loop constructs one instance; the router takes it as an optional parameter defaulting to a throwaway (standalone/test callers untouched).
**When to use:** For `/codeact` and every session toggle in this codebase — this is the locked house pattern.
**Example:**

```python
# Source: strands_code_cli/mode.py:35-91 (read this session) — mirror exactly.
class ModeState:
    VALID = ("plan", "act")  # codeact mirror: ("tool", "code", "both")

    def __init__(self, initial: str = "act") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown mode {initial!r}: expected plan|act")
        ...

    def set(self, mode: str) -> str:
        ...
        return MODE_PLAN_REPLY if mode == "plan" else MODE_ACT_REPLY

    def announce(self) -> str:
        return MODE_PLAN_REPLY if self._mode == "plan" else MODE_ACT_REPLY
```

Router-branch precedent (reply-only, holder-or-throwaway) [VERIFIED: `strands_code_cli/router.py:1331-1348`]:

```python
def _mode_holder(mode: ModeState | None) -> ModeState:
    """Loop-owned holder when present, else a throwaway Act default."""
    return mode if mode is not None else ModeState()

def _mode_message(rest: str, mode: ModeState | None) -> str:
    holder = _mode_holder(mode)
    verb = rest.strip().lower()
    if not verb:
        return holder.announce()
    if verb in ("plan", "act"):
        return holder.set(verb)
    return _MODE_USAGE
```

### Pattern 2: Per-Turn Input Prefix + Fix-at-Send (D-13/D-14/D-19)

**What:** The turn's interface is resolved once, before `_invoke_agent`, exactly where `mode` and `routing` hooks run today [VERIFIED: `strands_code_cli/loop.py:2264-2289`]: `bind_turn`, `set_gate_mode(mode.mode)`, `agent_text` composition, `_route_pre_turn`. A CodeAct turn prepends a `CODEACT_PREFIX` to `agent_text` (the `PLAN_PREFIX` precedent [VERIFIED: `strands_code_cli/loop.py:2273-2275`]: `agent_text = message if message is not None else text` / `if mode.mode == "plan": agent_text = f"{PLAN_PREFIX}\n\n{agent_text}"`). Because the holder is read only here, D-19 (switches apply next-ask only) holds by construction, and mid-turn slash commands never touch the running turn.
**When to use:** Every per-turn behavioral switch. Never mutate persistent agent state (`system_prompt`, registries) for a per-turn choice — the prefix keeps the choice invocation-scoped, which is also what makes D-20 (history preserved, interface-only change) trivially true.

### Pattern 3: Whole-Block Approval Through the Existing HITL Path (D-05/D-06/D-07/D-08)

**What:** CodeAct approvals reuse the single-`HumanInTheLoop` `python_repl` verdict path unchanged: classifier `decide()` → batch coverage → `ask` with `[y/n/always/never]`. The phase's only approval work is *rendering*: show the full generated block as a `Syntax(python)` preview (the callback handler already renders `python_repl` input this way [VERIFIED: `strands_code_agent/callback_handler.py:110-113`]) instead of the 500-char `_detail_line` truncation [VERIFIED: `strands_code_cli/policy_gate.py:647-648`: `return str(tool_input.get("code", ""))[:500]`].
**When to use:** Always — D-07 ("one rule system") forbids a second approval implementation, and D-08 forbids prompts anywhere but the code-action boundary.
**Denial semantics (D-06, free):** the ask layer returns `"n"` and the turn continues ("Denied by policy rule … skipped, continuing") — the denial observation feeds the model, which revises. The planner should ensure the denial observation carries a revise hint ("revise the code or try a different approach"); no executor/loop machinery is needed to "keep the turn alive".
**Remembered rules (D-07, free with a caveat):** `_derive_rule` already derives narrow `python_repl` rules from the code prefix [VERIFIED: `strands_code_cli/policy_gate.py:368-372`]: `Rule(tool="python_repl", command=normalise_command(code)[:500])`. Caveat for the planner: prefix-matching on code bodies means Always/Never rules match only identical-prefix blocks — same system, naturally narrow. Do not build fuzzy code matching.

### Pattern 4: Stint-Scoped Interpreter + Sync Interior Functions (D-09/D-10/D-11/D-17)

**What:** The CodeAct stint owns one `SandboxedPythonInterpreter` (lazy on first codeact turn; `clear_state()` on every interface switch per D-17; untouched across turns within a stint per D-11). `additional_functions` carries sync, scope-confined `read`/`write`/`edit`/`shell` callables. Verified live-probe facts about the backend (run this session against the repo venv):
- state persists across `execute_code` calls; `clear_state()` re-runs the preamble (a probe variable `x=41` read back `41` after clear);
- `additional_functions` are callable by bare name from generated code;
- unauthorized imports fail closed (`Import of os is not allowed. Authorized imports are: [...]`);
- `open()` is forbidden by default (`Forbidden function evaluation: 'open' is not among the explicitly allowed tools…`).
**When to use:** D-10/D-11/D-17 exactly. Keep this interpreter *separate* from the always-on `python_repl` tool's interpreter built in `main.build_agent` [VERIFIED: `strands_code_cli/main.py:119`] so tool-mode and code-mode REPL state never bleed into each other; reset-on-switch then only touches the CodeAct stint.

### Pattern 5: Transcript Label After the Turn, Cost Rows Untouched (D-15/D-16)

**What:** After each turn the loop prints the post-turn usage line via `print_plain(console, usage, style="dim")` [VERIFIED: `strands_code_cli/loop.py:1919-1920`]. D-15 rides the same site: one `print_plain` label line naming the turn's interface (`tool`/`codeact`/… — exact format is agent's discretion). D-16 is satisfied by *not touching* `session_turns` row shape or `cost_report` — keep interface records in a loop-owned parallel structure (or a row key the report ignores), never a rendered column.
**When to use:** Any per-turn transcript annotation. All dynamic transcript text routes through `print_plain` (markup off) per the WR-06 precedent.

### Anti-Patterns to Avoid

- **History surgery on switch:** never `convert_history`/truncate/rewrite `agent.messages` for an interface change (D-20). That machinery is model-switch-only.
- **Prompting inside execution:** never call `ask`/dialogs/`input()` from interior functions or the executor path — the worker thread cannot block on stdin (fatal), and D-05/D-08 forbid it regardless.
- **Async interior functions:** never expose the gated `write`/`edit` `@tool` wrappers (they are `async def …(…, tool_context=None)` [VERIFIED: `strands_code_cli/diff_gate.py:393-394,444-445`]) inside the sync executor — expose sync direct-apply callables instead.
- **Second rule/policy store:** never a codeact-specific allowlist file or in-memory rule cache — D-07/D-18 mandate the one `policy.toml` system carrying across switches.
- **Registry narrowing via private dicts:** `ToolRegistry` has no public unregister [VERIFIED: method list `register_tool/replace/register_dynamic_tool/…` read from installed `strands/tools/registry.py` this session] — do not mutate `.registry` to "enforce" D-14; prompt shaping + fix-at-send is the house mechanism.
- **`ToolChoice` forcing:** model-call-level config, not a per-turn interface switch (see Alternatives Considered).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sandboxed Python execution | Custom AST walker / `exec` sandbox | `SandboxedPythonInterpreter` (D-10) | Allowlist + timeout + state mgmt already tested (`tests/test_sandboxed_python_interpreter.py`); smolagents upstream handles the AST edge cases |
| Approval prompting + batching + remembered rules | CodeAct-specific gate | Single HITL `PolicyClassifier` + `BatchState` + `policy.toml` | One rule system is locked (D-07); batch/deny-never-covers/tag-namespacing semantics took 3 phases to harden |
| Session toggle state | Ad-hoc string flag in loop | Holder class mirroring `ModeState` | Validation, announcements, bare-command status, and throwaway-default router params come with the pattern |
| Config persistence | New config file/format | `ProviderConfig` (`config.yaml`, `_KNOWN_KEYS` + new key) | Atomic tmp+replace save, symlink refusal, 0o700 home already handled |
| Code preview rendering | Custom highlighter | `rich.syntax.Syntax(body, "python")` | Callback-handler precedent; ANSI-safe under `output_context` |
| Path confinement for interior file funcs | New scope checks | `strands_code_cli.scope.confine/resolve` | Same confinement as the gated wrappers; one definition of "in scope" |
| Per-turn metrics rows | New accounting | `record_turn_metrics` unchanged | D-16 requires identical rows; any new field must be report-invisible |

**Key insight:** CodeAct in this codebase is a *routing and rendering* phase, not an execution phase — the executor, the gate, and the toggle UX patterns all predate it. Every custom-built parallel (second gate, second rule store, second sandbox) directly violates a locked decision.

## Common Pitfalls

### Pitfall 1: Prompt-Only D-14 Has No Hard Enforcement
**What goes wrong:** A codeact turn shaped only by `CODEACT_PREFIX` can still emit `shell`/`write`/`edit` tool calls; a tool turn can still emit `python_repl` calls. The "one interface per turn" contract is advisory.
**Why it happens:** No public SDK API removes tools per-turn (no unregister on `ToolRegistry`), and `ToolChoice` forcing operates per model call, not per turn.
**How to avoid:** Accept prompt-shaping as the mechanism (it matches the `PLAN_PREFIX` precedent, which is likewise advisory); label the turn by the *selected* interface (D-15), not by observed tool use. Do not add classifier-side off-interface denials without re-discussing — that changes the approval contract.
**Warning signs:** Plans proposing registry mutation, private-attribute surgery, or per-turn agent rebuilds to "enforce" D-14.

### Pitfall 2: Async/Gated Wrappers Inside the Sync Executor
**What goes wrong:** Exposing `make_gated_write`/`make_gated_edit` products as `additional_functions` fails — they are `async def` with a `tool_context` parameter and route through the gate/diff machinery.
**Why it happens:** D-09 says "the same file/edit/shell tools", which reads like reuse of the `@tool` objects.
**How to avoid:** Implement sync interior `read`/`write`/`edit`/`shell` callables that share the *confinement* (`scope.py`) and *direct-apply* semantics, not the `@tool` wrappers. The whole block was already approved (D-05), so interior direct-apply is the coherent reading; `/diff` on-demand stashing does not apply to in-code writes (flag as a planner-visible consequence).
**Warning signs:** `asyncio.run` inside interior functions; `tool_context` threading into the executor.

### Pitfall 3: Two Interpreters Drifting (Stint vs Always-On)
**What goes wrong:** The CLI already registers a `python_repl` tool backed by a `main.build_agent`-owned interpreter. Adding a second stint interpreter without clear ownership causes state-bleed confusion (which REPL holds `x`?).
**Why it happens:** Both interpreters serve identically-named `python_repl` calls from different turn types.
**How to avoid:** Name the ownership explicitly (tool-turn REPL vs CodeAct-stint REPL), reset only the stint on switch (D-17), and document that tool-turn `python_repl` state is unaffected by CodeAct switches. The planner should decide whether tool turns keep their existing interpreter untouched (recommended: yes, zero behavior change on the default path).
**Warning signs:** A single shared interpreter with conditional resets; `clear_state` calls outside the switch path.

### Pitfall 4: `ProviderConfig` Unknown-Key Fail-Loud on the New Key
**What goes wrong:** Adding a CodeAct key to `config.yaml` without extending `_KNOWN_KEYS` raises `ValueError: Unknown provider config keys` on every load.
**Why it happens:** `ProviderConfig.load` fails loud on unknown keys [VERIFIED: `strands_code_cli/provider_config.py:61-63`]: `unknown = set(data) - _KNOWN_KEYS` / `raise ValueError(...)`.
**How to avoid:** Extend `_KNOWN_KEYS`, the dataclass, and `save()` together; cover with a round-trip test. Same for the remember-last-choice global option (D-03).
**Warning signs:** Config tests that only cover `model`/`base_url`.

### Pitfall 5: Skill-Name Collision With `/codeact`
**What goes wrong:** A local skill named `codeact` shadows or steals the builtin command.
**Why it happens:** Dynamic `/<skill>` dispatch resolves any non-builtin head.
**How to avoid:** Add `"codeact"` to `BUILTIN_SLASH_HEADS` [VERIFIED: `strands_code_cli/skills.py:19-43`] and place the `/codeact` branch before the skills-dynamic branch in `dispatch` (the `/btw` and `/route` precedent [VERIFIED: `strands_code_cli/router.py:221-230`]).
**Warning signs:** `/codeact` branch added after the skills-dynamic branch; missing `BUILTIN_SLASH_HEADS` entry.

### Pitfall 6: Plan-Mode + CodeAct Confusion (D-04)
**What goes wrong:** A codeact turn in Plan mode emits `python_repl` calls that are all denied (`python_repl` is in `PLAN_MUTATING_TOOLS` [VERIFIED: `strands_code_cli/policy_gate.py:71`]), producing a turn of pure denials.
**Why it happens:** D-04 leaves mode integration to "fits naturally" judgment.
**How to avoid:** The natural fit is: keep the existing plan-deny (mode vocabulary, no new logic) so plan+codeact proposes code in text while execution is denied — or refuse `/codeact` while in Plan mode with a mode-vocabulary message. Either is small; the planner picks one and pins it with a test. Do not invent a third "plan-codeact" mode.
**Warning signs:** New mode values; classifier branches keyed on interface+mode matrix.

### Pitfall 7: Both-Mode Routing Gesture Left Undefined
**What goes wrong:** `both` ships with no per-ask routing affordance, so turns silently default and D-13 ("user routes per ask at send time") is untestable.
**Why it happens:** D-13 locks the semantics but no surface; the send path currently has no per-ask branching.
**How to avoid:** The planner must specify the gesture (e.g. `/code <ask>` / `/tool <ask>` one-shot prefixes, or a send-time chooser on bare asks while in `both`). Recommend one-shot prefixes: they compose with the existing `dispatch` return contract (`("agent", composed_text)` + interface tag) and leave bare-ask behavior untouched.
**Warning signs:** Plans that implement the holder but no per-ask routing input.

## Code Examples

Verified patterns from in-repo sources (all read this session):

### Session Flag → Holder Initial (D-02/D-03)

```python
# Source: strands_code_cli/main.py:205-211 (typer flag precedent) +
#         strands_code_cli/loop.py:2072 (ModeState ownership precedent).
@app.callback(invoke_without_command=True)
def _root(ctx, session_id: str | None = typer.Option(None, "--session-id", ...)):
    ...
    run_loop(agent, session_id=resolved, index=index)

# loop.py run_loop owns:  mode = ModeState()
# CodeAct adds:           interface = CodeactState(initial=...)  # "tool" unless
#                         --codeact flag or remember-last config says otherwise
```

### Config Key Round-Trip (D-02/D-03)

```python
# Source: strands_code_cli/provider_config.py:19,28-38,72-104.
_KNOWN_KEYS = {"model", "base_url"}  # planner extends with the codeact key(s)

@dataclass
class ProviderConfig:
    model: str | None = None
    base_url: str | None = None
    # planner adds: codeact: str | None = None (+ remember-last global option)
```

### Stint Interpreter Lifecycle (D-10/D-11/D-17)

```python
# Source: strands_code_agent/python_environments/local_sandboxed.py:12-49
#         + live probe results (this session).
from strands_code_agent.python_environments.local_sandboxed import SandboxedPythonInterpreter

stint = SandboxedPythonInterpreter(
    "",
    authorized_imports={"math"},          # minimal; never os/sys/subprocess/pathlib
    additional_functions={                # sync, scope-confined, direct-apply
        "read": codeact_read, "write": codeact_write,
        "edit": codeact_edit, "shell": codeact_shell,
    },
    timeout_seconds=60,                   # D-12: library default, no new setting
)
stdout, stderr = stint.execute_code(block)  # (stdout, stderr) tuple, never raises
stint.clear_state()                         # D-17: on every interface switch
```

### Whole-Block Preview Render (D-05)

```python
# Source: strands_code_agent/callback_handler.py:110-113 (existing render) +
#         strands_code_cli/policy_gate.py:643-651 (prompt detail site to extend).
from rich.syntax import Syntax

# callback handler today:
if name in self.code_tools:                      # {'python_repl': 'python'}
    syntax = Syntax(tool_use['input']['code'], language)
    self.console.print(syntax)

# planner: render the same full-code Syntax block at the top of the
# python_repl approval prompt (replacing the [:500] _detail_line truncation
# for the preview; keep the 60-char dialog title as-is).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Text/JSON tool-calling as the only agent action space | CodeAct: executable Python as a unified action space (Wang et al., ICML 2024; up to 20% higher success on API-Bank/M³ToolEval) [CITED: https://github.com/xingyaoww/code-act] | 2024 | Evidence base for offering code-first as an opt-in; supports "beats gated tool-calling on some tasks" without mandating it |
| `LocalPythonExecutor` treated as a sandbox | Upstream explicit: "not a security sandbox… must not be used as a security boundary" [CITED: https://github.com/huggingface/smolagents] | 2025 (upstream security guidance) | The deny-first whole-block human approval is the real boundary; post-approval code runs with user privileges, same as an approved `shell` command |
| Strands static tool registration | `ToolRegistry.replace()` for implementation swaps [CITED: https://github.com/strands-agents/sdk-python/discussions/1411] | v1.21.0 | Enables hot-reload patterns; still no per-turn tool-set API — confirms prompt-shaping over registry surgery |
| SDK `Sandbox` ABC (`execute_code`, Docker backends) | Available in installed strands-agents 1.58.1 [VERIFIED: `.venv/.../strands/sandbox/base.py` read this session] | Pre-existing | Deliberately *not* adopted: D-10 locks the library interpreter (offline-safe, no new backend) |

**Deprecated/outdated:**
- ROADMAP's "harness sandbox primitive" phrasing for CodeAct execution: superseded by locked D-10 (`SandboxedPythonInterpreter`). Planner must not build a `strands.sandbox.Sandbox` backend.
- `.planning/codebase/*.md` maps (2026-09-22, pre-CLI layout): stale per CONTEXT.md; all CLI paths in this research were verified against the current `strands_code_cli/` tree.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `rich` installed version is 15.0.0 (taken from AGENTS.md stack record; not re-verified via metadata this session) [ASSUMED] | Standard Stack | Negligible — render API (`Syntax`) is stable and already used |
| A2 | Denied `python_repl` observations reach the model as ordinary tool denials the model can revise from, with no extra loop work for D-06 [ASSUMED] | Pattern 3 | Low — the deny-and-continue path is exercised by existing policy-gate tests; planner pins with one test |
| A3 | One-shot `/code` + `/tool` prefixes are an acceptable per-ask routing gesture for `both` mode (recommendation, not a locked decision) [ASSUMED] | Pitfall 7 | Medium — UX shape; planner may choose a send-time chooser instead within D-13 |
| A4 | Storing the turn interface in a loop-owned parallel structure (not on `session_turns` rows) best satisfies D-15+D-16 [ASSUMED] | Pattern 5 | Low — either placement works if `cost_report` ignores it; planner decides |
| A5 | `/btw` side turns stay tool-calling regardless of the main interface (recommended scope cut; not discussed) [ASSUMED] | Open Questions | Medium — planner must state the scope explicitly; side-agent CodeAct would widen the phase |

## Open Questions (RESOLVED)

1. **Per-ask routing gesture for `both` mode** — RESOLVED: one-shot `/code <ask>` / `/tool <ask>` prefixes → adopted in 11-02 task 3.
   - What we know: D-13 locks user-routing at send time; the send path has no per-ask branching today.
   - What's unclear: One-shot prefixes vs send-time chooser vs another gesture.
   - Recommendation: Planner specifies one-shot `/code <ask>` / `/tool <ask>` prefixes (compose with `dispatch`'s `("agent", …)` contract); needs no new prompt machinery.

2. **`/btw` side-agent interface scope** — RESOLVED: main-turns-only; side agents stay tool-calling → adopted in 11-02 task 2.
   - What we know: Side agents rebuild via `create_harness` with stashed parent kwargs; they are Q&A-shaped.
   - What's unclear: Whether CodeAct selection affects side turns.
   - Recommendation: Main-turns-only this phase; side turns stay default tool-calling. State explicitly in the plan.

3. **Plan-mode + CodeAct behavior (D-04)** — RESOLVED: keep existing plan-deny, pin with test → adopted in 11-03 task 2.
   - What we know: `python_repl` is plan-denied today; both candidate behaviors are small.
   - What's unclear: Propose-in-text-with-denied-execution vs refuse-`/codeact`-in-plan.
   - Recommendation: Planner picks one, pins with a test; keep mode vocabulary.

4. **In-code writes vs `/diff` on-demand stashing** — RESOLVED: direct-apply in-code writes as a D-05 consequence → adopted in 11-02 task 1.
   - What we know: Interior functions must be sync direct-apply (Pitfall 2); the whole block was approved as the review unit (D-05).
   - What's unclear: Whether users expect in-code writes to appear in `/diff` pending review.
   - Recommendation: Direct-apply, documented as a D-05 consequence; do not route stashing through the async diff machinery inside execution.

5. **Tool-turn `python_repl` interpreter ownership** — RESOLVED: separate stint interpreter; tool-turn REPL untouched → adopted in 11-02 tasks 1–2.
   - What we know: `main.build_agent` already registers an always-on `python_repl` tool with its own interpreter.
   - What's unclear: Whether tool turns keep that interpreter untouched while CodeAct owns a separate stint interpreter.
   - Recommendation: Yes — zero behavior change on the default path; name both owners in code and docs.

## Environment Availability

All CodeAct dependencies are already installed in the project venv (verified via `importlib.metadata` this session); D-10 requires no new backend and the phase is offline-safe.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.14.7 (venv) / >=3.10 (supported) | — |
| `smolagents` | D-10 backend | ✓ | 1.26.0 | — |
| `strands-agents` | Agent/`@tool`/HITL | ✓ | 1.58.1 | — |
| `strands-harness` | `create_harness` | ✓ | 0.1.2 | — |
| `pytest` | Validation | ✓ | 9.1.1 | — |
| Network / AWS credentials | Nothing this phase | n/a | — | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (installed; `addopts = "-m 'not integration'"` in `pyproject.toml`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) + `tests/conftest.py` (hermetic live-pricing guard) |
| Quick run command | `.venv/bin/python -m pytest tests/test_codeact.py -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-07 | `/codeact` toggles holder; bare reports; invalid verb → usage | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k toggle` | ❌ Wave 0 |
| TOOL-07 | `--codeact` flag + config key set initial interface; default `tool` | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k startup` | ❌ Wave 0 |
| TOOL-07 | Turn setup fixes interface at send; prefix present only on code turns | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k turn_setup` | ❌ Wave 0 |
| TOOL-07 | Both-mode per-ask routing gesture selects the turn interface | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k both` | ❌ Wave 0 |
| TOOL-07 | Whole-block preview renders full code; one prompt per code action | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k approval` | ❌ Wave 0 |
| TOOL-07 | Denial keeps turn alive (deny-and-continue → revise hint) | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k deny` | ❌ Wave 0 |
| TOOL-07 | Always/Never derive `python_repl` rules; one rule system | unit | `.venv/bin/python -m pytest tests/test_policy_gate.py -q` (extend) | ✅ exists |
| TOOL-07 | Stint REPL persists within stint, resets on switch | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k stint` | ❌ Wave 0 |
| TOOL-07 | Transcript labels each turn; `/cost` rows byte-identical | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k label` | ❌ Wave 0 |
| TOOL-07 | History preserved across switches (no message surgery) | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k history` | ❌ Wave 0 |
| TOOL-07 | Interior file/shell funcs confined to scope; no `os`/`subprocess` imports | unit | `.venv/bin/python -m pytest tests/test_codeact.py -q -k interior` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `.venv/bin/python -m pytest tests/test_codeact.py tests/test_policy_gate.py tests/test_mode.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest -q`
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_codeact.py` — covers TOOL-07 (holder, routing, stint lifecycle, labels, interior confinement)
- [ ] `tests/test_policy_gate.py` — extend: full-code preview render assertions for `python_repl` prompts
- [ ] Framework install: none — `pytest 9.1.1` installed and baseline-green this session

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth surface in this phase |
| V3 Session Management | Partial | Session dirs already 0o700; interface holder is in-memory only, never persisted except the D-03 global option via `ProviderConfig` (same 0o700 home) |
| V4 Access Control | Yes | Deny-first HITL gate unchanged; whole-block approval is the authorization check for code execution |
| V5 Input Validation | Yes | Generated code is untrusted input until approved: full-block human review (D-05) + executor allowlist + `scope.py` confinement on interior file funcs + `subprocess` without `shell=True` |
| V6 Cryptography | No | No crypto in this phase |
| V7 Error Handling/Logging | Yes | Executor returns `(stdout, stderr)` tuples, never leaks tracebacks beyond the observation; no new logging on the REPL path |
| V8 Data Protection | Partial | REPL state is in-process only; `clear_state()` on switch prevents cross-stint data bleed (D-17) |
| V10 Malicious Code | Yes | Minimal `authorized_imports` (never `os`/`sys`/`subprocess`/`pathlib`/`socket`); `open()` stays forbidden; file effects only via reviewed interior functions |
| V12 Secure Communication | No | No network surface (offline-safe, D-10) |
| V14 Configuration | Yes | `ProviderConfig._KNOWN_KEYS` extension with fail-loud unknown keys; `policy.toml` unchanged schema |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious generated code (prompt-injected tool output steering codegen) | Tampering / Elevation | Whole-block human preview + explicit approve before any execution (D-05); the approval is the security boundary since `LocalPythonExecutor` is not one [CITED: https://github.com/huggingface/smolagents] |
| Sandbox escape via imports (`os`, `subprocess`, `pathlib`) | Elevation | Minimal `authorized_imports`; interior capabilities exposed as narrow functions, never as importable modules ("never rely on `additional_authorized_imports` as a shortcut" [CITED: https://www.fox-it.com/be-en/autonomous-ai-agents-a-hidden-risk-in-insecure-smolagents-codeagent-usage]) |
| Direct file writes bypassing review (`open()`, `pathlib`) | Tampering | `open()` forbidden by executor default (verified by probe); writes only through approved-block interior functions reusing `scope.py` confinement |
| Shell injection in interior `shell()` | Injection | `subprocess` argv-list execution, no `shell=True`; command text visible in the approved block |
| Cross-stint state bleed (secrets/paths persisting) | Information disclosure | `clear_state()` on every interface switch (D-17); separate stint interpreter from the tool-turn REPL |
| Over-broad Always rules auto-approving future code | Elevation | `_derive_rule` prefix rule (first 500 chars) is naturally narrow for code bodies; denials never cover (existing fail-closed semantics) |
| Approval fatigue (many blocks per turn) | — (UX risk) | Batch coverage already silences same-signature repeats within a turn; one prompt per code action is the locked unit (D-05) |

## Sources

### Primary (HIGH confidence)

- In-repo sources read this session: `strands_code_cli/loop.py` (turn setup 2264–2304, post-turn label site 1916–1920, holder ownership 2072–2096), `strands_code_cli/router.py` (dispatch 104–249, `/btw`+`/route` branch order 221–230, `_mode_message` 1336–1348), `strands_code_cli/mode.py:35-91` (holder pattern), `strands_code_cli/policy_gate.py` (classifier 382+, `_derive_rule` 361–379, `_detail_line` 643–651, `_dialog_title` 658–672), `strands_code_cli/policy.py:1-90` (schema + `KNOWN_TOOLS` incl. `python_repl`), `strands_code_cli/main.py:106-202` (agent factory + always-on interpreter at 119), `strands_code_cli/provider_config.py` (config pattern), `strands_code_cli/skills.py:19-43` (`BUILTIN_SLASH_HEADS`), `strands_code_cli/diff_gate.py` (async gated wrappers 373–445), `strands_code_cli/cost_context.py:165-269` (usage/cost report), `strands_code_agent/code_agent.py` (prompt assembly), `strands_code_agent/python_environments/base.py` (`get_tool` observation contract), `strands_code_agent/python_environments/local_sandboxed.py` (D-10 backend), `strands_code_agent/callback_handler.py:106-137` (tool/code rendering)
- Live venv probes this session: `SandboxedPythonInterpreter` behavior (state persistence, `clear_state` preamble re-run, bare-name `additional_functions`, import denial text, `open()` denial text); `ToolRegistry` public method list (no unregister); `ToolChoice` model-call-level flow (`strands/models/bedrock.py:350,421`); installed versions (`importlib.metadata`); `pytest 9.1.1` baseline (`tests/test_mode.py`, 32 passed)
- [Official code-act repo](https://github.com/xingyaoww/code-act) — CodeAct definition, unified code action space, benchmark claims
- [smolagents repo](https://github.com/huggingface/smolagents) — `LocalPythonExecutor` is not a security boundary

### Secondary (MEDIUM confidence)

- [Strands ToolRegistry API docs](https://strandsagents.com/docs/api/python/strands.tools.registry) — `register_dynamic_tool` semantics (consistent with installed source)
- [Strands v1.21.0 discussion](https://github.com/strands-agents/sdk-python/discussions/1411) — `ToolRegistry.replace()` purpose (confirmed in installed source)
- [Fox IT smolagents risk analysis](https://www.fox-it.com/be-en/autonomous-ai-agents-a-hidden-risk-in-insecure-smolagents-codeagent-usage) — allowlist best practices (consistent with upstream guidance)

### Tertiary (LOW confidence)

- [AWS Builder Center dynamic tool loading](https://builder.aws.com/content/2zeKrP0DJJLqC0Q9jp842IPxLMm/dynamic-tool-loading-in-strands-sdk-enabling-meta-tooling-for-adaptive-ai-agents) — background on dynamic tools; not load-bearing for any recommendation
- [alphaXiv CodeAct explainer](https://www.alphaxiv.org/abs/2402.01030) and [ICML proceedings entry](https://dl.acm.org/doi/10.5555/3692070.3694124) — corroborating CodeAct benchmark summaries only

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — zero new packages; every version verified against the installed venv this session
- Architecture: HIGH — all five patterns mirror in-repo precedents read line-by-line this session; SDK APIs verified against installed source
- Pitfalls: HIGH — each pitfall names the exact file/line or probe output that motivates it
- Approval/UX details: MEDIUM — whole-block render + revise-hint + both-mode gesture need planner specification within locked decisions

**Research date:** 2026-10-15
**Valid until:** 2026-11-14 (stable domain; in-repo precedents, no fast-moving APIs)



