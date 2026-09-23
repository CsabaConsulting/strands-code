# Stack Research

**Domain:** Python conversational coding CLI on Strands harness (SUBSEQUENT milestone)
**Researched:** 2026-09-23
**Confidence:** HIGH (versions verified against PyPI 2026-09-23; Strands docs via gap analysis)

Existing system is NOT re-researched here. This file prescribes only the NEW CLI-layer
stack. Already owned — do not re-decide: `strands-agents`, `strands-harness`,
`smolagents`, `Jinja2`, `Rich`, `PyYAML`, `boto3` (optional extra), `uv`, pytest.
See `.planning/codebase/STACK.md` and `docs/competitive-gap-analysis.md`.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| strands-agents | 1.57.0 (locked; = latest on PyPI) | Agent loop, tools, sessions, hooks, providers | Already adopted; FileSessionManager + provider strings + AgentSkills are native — building the CLI on anything lower-level means rebuilding shipped primitives |
| strands-harness | 0.1.2 (locked; = latest on PyPI) | Batteries-included defaults: `create_harness()`, file/shell tools, `./.agent/sessions`, `./.agent/memory`, skills loading, effort presets, interventions | Gap analysis decision: compose `CodeAgent` from harness defaults instead of bare `Agent`; keep wrapper thin (both packages flagged Experimental upstream, no upper pins) |
| Python | >=3.10 (classifiers 3.10–3.13) | Language runtime | Existing constraint; `X \| Y` syntax and `match` available; no change |
| Typer | 0.27.2 | CLI framework: `strands-code` entry point, subcommands (`run`, `resume`, `skills`, …), `--session-id` routing | Standard choice 2026: type-hint-driven, auto help + shell completion, built on Click, `typer.testing.CliRunner` for smoke tests; consensus successor to raw Click for new CLIs (HIGH) |
| prompt_toolkit | 3.0.53 | Interactive conversational REPL: multiline editing, history, slash-command + `@`-file completers, bottom toolbar (mode/cost/context), anytime-steering input at tool-call boundary | Focused REPL library — the central interaction is typing, not a fullscreen app. Line-streaming REPL matches Claude Code/Codex UX and composes with Rich streaming output; Textual fullscreen fights it (HIGH) |
| Rich | 15.0.0 (already dep; = latest) | Terminal rendering: Markdown answers, Syntax diffs, Live streaming, cost/context panels | Already owned and is the callback handler's renderer; zero new deps, pairs natively with Typer + prompt_toolkit (HIGH) |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| questionary | 2.1.1 | One-off confirms/selects (approval prompts, `/model` picker, permission ask/allow) | For single prompts inside the CLI — much simpler API than raw prompt_toolkit dialogs; built on prompt_toolkit so no renderer conflict (HIGH) |
| PyGithub | 2.10.0 | Full GitHub loop: read issues/PRs, create issues, branch/PR open, review comments, CI checks status | Typed, testable, no subprocess; `GITHUB_TOKEN` env contract keeps headless + CI working (MEDIUM-HIGH) |
| httpx | 0.28.1 | Marketplace downloads (skill packs/manifests over HTTPS) | Modern `requests` replacement, sync+async; only needed for the marketplace install path (MEDIUM) |
| platformdirs | 4.11.12 | Global config/cache dirs (`~/.config/strands-code/config.yaml`, model prefs, marketplace registry) | Project-local state stays in `./.agent/` (harness convention); platformdirs only for per-user global config — XDG-compliant on all OSes (MEDIUM) |
| PyYAML | 6.0.3 (already dep) | Skills frontmatter, permissions policy file, config file | Already owned; skill packs are markdown+YAML-frontmatter per AgentSkills convention (HIGH) |
| ripgrep (external binary) | system install, optional | Grep-first code understanding backend (`@`-mention file search, agentic grep) | PROJECT.md defers the semantic index — rg is the fast lexical backend; shell out, never a Python dep; degrade gracefully when absent (MEDIUM) |
| fzf (external binary) | system install, optional passthrough only | Power-user fuzzy file picker when present | Optional `fzf` subprocess fallback only; never a hard dependency (MEDIUM) |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv 0.9.x | Toolchain: sync, lock, run | Existing; new CLI deps go in `dependencies`, marketplace/test-only in groups |
| pytest ≥9 (+ `typer.testing.CliRunner`) | CLI smoke tests, slash-registry tests, PyGithub mocked tests | Existing runner; CliRunner needs no extra install (ships with Typer) |
| Ruff | Lint/format (replaces Black/isort/Flake8) | Standard 2026 single-tool gate; add only if repo adopts a linter at all — no config exists today |

## Installation

```bash
# CLI layer (new)
uv add "typer>=0.27" "prompt_toolkit>=3.0" "questionary>=2.1" "PyGithub>=2.10" "httpx>=0.28" "platformdirs>=4.11"

# Already owned — do NOT re-add
# strands-agents strands-harness smolagents jinja2 rich pyyaml (+ boto3 via .[agentcore])

# Optional system binaries (never pip deps)
# rg (ripgrep) for grep-first search; fzf for power-user picking; gh CLI as auth fallback
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Typer 0.27.2 | Click 8.5.0 direct | Only if custom command-loading/control over contexts is needed — Typer already sits on Click, so drop down only with a concrete reason |
| Typer 0.27.2 | argparse (stdlib) | Never for this CLI — no completion/help generation, more code for less UX; stdlib is not a virtue here |
| prompt_toolkit REPL | Textual 8.2.8 fullscreen TUI | Only for a later full-screen mode (browse/dashboard); v1 competitors are line-streaming REPLs and Textual fights streaming agent output — hybrid pattern at most (REPL default, Textual as a suspendable mode) |
| prompt_toolkit FuzzyCompleter (built-in) | pyfzf / iterfzf | Only as optional passthrough when the `fzf` binary exists; they couple pip installs to an external binary — never hard-dep them |
| PyGithub 2.10.0 | `gh` CLI via subprocess | Fallback when no `GITHUB_TOKEN` but `gh auth login` exists (reuse user auth); primary stays PyGithub for testability — document both, default to PyGithub |
| PyGithub 2.10.0 | raw httpx REST to api.github.com | Only if PyGithub misses a new endpoint (it lags new APIs); thin supplement, not the base |
| FileSessionManager (Strands native) | custom JSON session files | Never — resume-by-UUID, S3 swap-in, and flush semantics already ship; custom files duplicate tested upstream |
| httpx 0.28.1 | requests / urllib | Never for new code — httpx is the 2026 default (sync+async, HTTP/2); requests only if a dep drags it in |
| git-repo + YAML-manifest marketplace | PyPI-packaged skills | Prefer git+manifest: skills are markdown packs, not code distributions; PyPI adds versioning overhead that skill UX doesn't need |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Textual as the v1 REPL | Fullscreen App owns the screen and fights streaming agent output; proven competitor UX is a line-streaming REPL; adds event-loop complexity to anytime-steering | prompt_toolkit REPL + Rich Live; Textual only as a later suspendable mode |
| argparse / hand-rolled parser | No completion, no help generation, slash-command registry still hand-built on top anyway | Typer for argv; thin leading-`/` registry for in-REPL commands (ours per gap analysis) |
| pyfzf / iterfzf as hard deps | pip package that shells to a non-pip binary — breaks installs where `fzf` is absent; reported flakiness pattern in automation | prompt_toolkit FuzzyCompleter built-in; optional `fzf` passthrough |
| Custom session/memory JSON store | Duplicates `FileSessionManager` (resume, flush/close) and `MemoryStore` tiers already adopted (local markdown → Hindsight → memsearch) | Strands-native `session_manager` + `memory={"stores": [...]}` seam |
| Vector DB / embedding infra in v1 | PROJECT.md explicitly defers the semantic index; Milvus/pgvector is a project of its own with ops/billing cost | ripgrep-backed grep-first; memory tiers behind the existing `MemoryStore` interface |
| Auto model/effort routing in v1 | PROJECT.md defers it; thinking-budget routing needs calibration data we don't have | Manual `/model` picker (questionary) over Strands provider strings; `effort` presets are static CLI config |
| Enforced token budgets in v1 | PROJECT.md: display only; halting on cost is a policy decision for later | Cost/context display from existing Bedrock metrics + harness telemetry; no kill-switch |
| `requests` for new HTTP | Legacy sync-only API; ecosystem has moved | httpx |

## Stack Patterns by Variant

**If AWS credentials absent (local/offline default):**
- FileSessionManager + local markdown memory + Ollama/LiteLLM provider string + `agentcore` extra never imported (lazy `boto3`)
- Because: AWS-optional-never-required constraint; CLI must boot with zero AWS

**If `GITHUB_TOKEN` absent but `gh` installed:**
- Fall back to `gh` subprocess for read operations; error clearly on write operations
- Because: reuse existing user auth instead of failing hard

**If `fzf` / `rg` binaries present:**
- Prefer them as picker/search backends; else prompt_toolkit fuzzy + Python `grep` fallback
- Because: best tool when available, zero hard dependency either way

**If team wants temporal repo memory later:**
- `pip install hindsight-strands` behind the `memory={"stores": [...]}` seam
- Because: opt-in tier per gap analysis; no CLI rewrite

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Typer 0.27.2 | Click 8.5.0 (transitive) | Typer pulls Click automatically; do not pin Click separately |
| questionary 2.1.1 | prompt_toolkit 3.0.53 | questionary rides prompt_toolkit — keep both, versions move together |
| PyGithub 2.10.0 | httpx-independent (uses `requests` internally) | Tolerate its `requests` transitive dep; do not unify — ours uses httpx |
| strands-agents 1.57.0 / strands-harness 0.1.2 | Python ≥3.10 | Locked versions ARE latest PyPI as of 2026-09-23; no upper pins per experimental-phase constraint |
| Rich 15.0.0 | Typer + prompt_toolkit | Shared renderer; `rich_markup_mode="rich"` on the Typer app |

## Sources

- PyPI JSON API (`pypi.org/pypi/{typer,prompt_toolkit,rich,PyGithub,questionary,textual,strands-agents,strands-harness,click,pyyaml,platformdirs,httpx}/json`) — all versions above verified 2026-09-23 — HIGH
- `docs/competitive-gap-analysis.md` — Strands-native session/skills/model/memory mapping, harness-first direction — HIGH
- `.planning/codebase/STACK.md` (2026-09-22) — locked versions, owned deps — HIGH
- `.planning/PROJECT.md` — v1 scope bars (no semantic index, no budgets, no auto-routing, AWS-optional) — HIGH
- Web ecosystem consensus: Typer-over-Click default for new Python CLIs; prompt_toolkit for REPL-typing interaction vs Textual fullscreen; PyGithub-over-subprocess for testable automation with `gh`-fallback for auth reuse — MEDIUM (corroborated across multiple 2026 sources)

---
*Stack research for: strands-code conversational CLI milestone*
*Researched: 2026-09-23*
