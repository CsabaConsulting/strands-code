# Phase 12: OpenViking Recall Backend - Research

**Researched:** 2026-10-16
**Domain:** Agent long-term memory backend (OpenViking context database + Strands MemoryStore seam)
**Confidence:** MEDIUM

## Summary

OpenViking ([CITED: https://github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking)) is ByteDance Volcengine's open-source context database for AI agents: memories, resources, and skills live in a virtual filesystem under the `viking://` protocol with tiered L0 abstract / L1 overview / L2 detail loading. The Python integration surface is the lightweight `openviking-sdk` HTTP client (httpx-only dependency) talking to a running `openviking-server` (default `http://127.0.0.1:1933`). The critical finding for planning is that **OpenViking runs as a server — "OpenViking runs as a server"** ([CITED: https://docs.openviking.ai/en/getting-started/02-quickstart](https://docs.openviking.ai/en/getting-started/02-quickstart)) and **"Every integration on this page connects to a running OpenViking server"** ([CITED: https://docs.openviking.ai/en/agent-integrations/01-overview](https://docs.openviking.ai/en/agent-integrations/01-overview)). There is no documented embedded in-process library mode. This directly tensions locked decision D-01 (embedded, in-process, no sidecar) and is the phase's top planning risk (see Open Questions).

On the repo side the seam is clean and verified: Strands SDK 1.58.1 ships a `MemoryStore` Protocol (`search` required; `add`/`add_messages`/`initialize`/`get_tools` optional) and the harness `resolve_memory(stores=[...])` accepts consumer-supplied stores, with injection rendering `<entry source="store-name">` provenance labels for free. The recommended shape is an `OpenVikingMemoryStore` adapter over `openviking_sdk.AsyncHTTPClient` plus a CLI-managed localhost server child process with `storage.workspace` pointed at the repo `.agent/viking/` directory.

**Primary recommendation:** Implement a `MemoryStore`-protocol adapter backed by `openviking-sdk` (recall via `find()` QUICK or `search(mode="context", purpose="coding")`), with the CLI spawning and supervising a per-repo localhost `openviking-server` child process (local backends, Ollama VLM); resolve the D-01 embedded-vs-server tension and the SDK license question before planning tasks.

## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Deployment shape

- **D-01:** Embedded library — OpenViking runs in-process in the CLI; no sidecar daemon, no extra process to manage.
- **D-02:** Local only — no cloud endpoints this phase; deployment stays fully offline-capable.
- **D-03:** The `viking://` store lives under repo `.agent/` (e.g. `.agent/viking/`): git-trackable, per-project, matching the memory-file precedent. — **Reversibility:** costly — the store path is a user-facing on-disk contract; moving it later needs a migration.
- **D-04:** Real OpenViking dependency — add the package (supply-chain review applies); do not reimplement the tree/summaries in stdlib.

#### Seam composition

- **D-05:** Native first — OpenViking is consulted only when native memory has nothing relevant; today's behavior is preserved exactly when native answers.
- **D-06:** Native wins conflicts — when both backends disagree, native memory wins (same precedence as the `.agent/MEMORY.md` file rule).
- **D-07:** Store ABC — one MemoryStore interface with native and OpenViking implementations behind it (planner designs the ABC). OpenViking is an optional feature just like memsearch.
- **D-08:** Byte-identical when off — with OpenViking disabled, behavior matches today exactly. Exception: the planner may choose seam-always-live if it benefits memsearch too and is architecturally nice, with written justification.

#### Recall surfacing

- **D-09:** Prefix injection — OpenViking hits inject into the prompt prefix like native memory, under the same cap; zero new UX.
- **D-10:** Summaries first — L0/L1 summaries in the prefix; full L2 content only on explicit drill-down.
- **D-11:** Label source — injected recall is tagged native vs openviking so the agent knows the provenance.
- **D-12:** On-demand drill-down — the agent can pull L2 full content on demand; planner picks the mechanism (slash, tool, or auto-escalation).

#### Capture/write path

- **D-13:** Macro only — OpenViking keeps long-term preferences, repeated fixes, and project constraints; it never mirrors native memory or session transcripts.
- **D-14:** Curate-gated writes — OpenViking writes flow through the `/memory` curate loop (approve/deny) like native proposals, per the deny-first posture.
- **D-15:** Supersede on conflict — new writes supersede outdated OpenViking entries via OpenViking's contradiction resolution; no ask-on-conflict prompts.
- **D-16:** Deletes cascade — deleting from native memory also removes the corresponding OpenViking entries; one delete clears both.

#### Opt-in surface

- **D-17:** All three surfaces: `/memory` toggle (primary), config key, and startup flag — mirroring the `/codeact` surface trio.
- **D-18:** Persisted choice — enable once and OpenViking stays on across sessions (differs from `/codeact`'s per-session default; memory is stickier than interface mode). — **Reversibility:** costly — persistence shapes the config contract and session-start behavior; flipping it later changes every-session behavior.
- **D-19:** Toggle writes config — the `/memory` toggle writes through to the config key, so toggle and config are one persisted thing.
- **D-20:** Flag first — precedence is startup flag > session toggle > config key; explicit invocation always wins.

### the agent's Discretion

Drill-down mechanism (D-12), exact config key and flag names, `/memory` toggle UX wording, and the Store ABC shape are left to planner/executor judgment within the locked decisions above.

### Deferred Ideas (OUT OF SCOPE)

- OpenViking cloud endpoints — local-only this phase (D-02); revisit only on explicit demand.
- memsearch implementation as a sibling backend — stays future work; D-08 notes the seam should not preclude it.
- Sidecar-daemon deployment — rejected in favor of embedded (D-01).

None of the above belong in Phase 12 scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SKILL-05 | User can opt into OpenViking cross-session recall behind the same memory seam (Hindsight explicitly out) | MemoryStore-protocol adapter + managed localhost server + opt-in trio; Hindsight untouched (no Postgres/loop anywhere in this design) |

## Project Constraints (from AGENTS.md)

- Python >= 3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform. (OpenViking adapter must be a `MemoryStore` Protocol implementation fed to harness `resolve_memory`, not a harness patch.)
- AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports. (OpenViking server + local backends + Ollama keeps this; no cloud endpoint.)
- No upper pins during the experimental phase; resync upstream deliberately. (Depend on `openviking-sdk>=...` with a lower bound only.)
- `snake_case.py` modules, `test_<module>.py` mirrors in `tests/`; absolute imports rooted at package; 4-space, double quotes, ~100-120 cols; no formatter/linter configured — match surrounding style by hand.
- Docstrings (triple-double-quoted, imperative first line, `Args:`/`Returns:`) on every public function/class/method; why-not-what comments, 1-2 lines.
- Error handling: fail soft on read paths (return "not found" notes, never raise); raise `TypeError`/`ValueError` for programmer errors; log-and-continue only for best-effort cleanup. Recall against a down server must fail soft (skip injection), never crash the turn.
- Logging: module `logger = logging.getLogger(__name__)`; never `print()` in library code; agent-visible output flows through established observation paths only.
- No GSD-bypass edits; test via `uv run pytest tests/ -v`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Recall serving (vector search, tier assembly) | OpenViking server (localhost child process) | — | Retrieval engine is server-owned; CLI only calls it |
| MemoryStore adapter + fallback composition | CLI (`strands_code_cli/`) | — | Strands seam lives in-process with the agent |
| Prompt-prefix injection | Harness MemoryManager (existing) | CLI recall intent | Injection middleware + `<entry source>` labels already exist; CLI supplies stores |
| Curate gating + opt-in surfaces | CLI (`/memory`, config, flags) | — | Deny-first UX is CLI-owned, mirrors `/codeact` trio |
| Store persistence (AGFS + vector index) | Server workspace dir (`.agent/viking/`) | — | Server owns both storage layers under one workspace path |
| Embedding/VLM model calls | Local models (built-in local embed; Ollama VLM) | — | Offline posture forbids cloud providers |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openviking-sdk` [CITED: https://pypi.org/pypi/openviking-sdk/json](https://pypi.org/pypi/openviking-sdk/json) | 0.1.15 (latest 2026-08-24 line; 0.1.7/0.1.8/0.1.9 seen, info version 0.1.15) | HTTP client for the OpenViking server; `SyncHTTPClient`/`AsyncHTTPClient`, `find`/`search`/`read`/`write`/`mkdir`/`rm`/`abstract`/`overview` | Official lightweight client: "the small package for users who only need to call an existing OpenViking server over HTTP", sole dependency `httpx>=0.25.0`, requires-python `>=3.8` |
| `openviking` (server runtime, deployment prerequisite, NOT a library dep) [CITED: https://pypi.org/pypi/openviking/json](https://pypi.org/pypi/openviking/json) | 0.5.0 (published 2026-10-09), requires-python `>=3.10`, 58 releases | Provides the `openviking-server` entrypoint (`init`/`doctor`/serve) | Only distribution of the server; installed via `uv tool install openviking` per official quickstart |
| Strands `MemoryStore` Protocol (already in tree via strands-agents 1.58.1) [VERIFIED: .venv/lib/python3.14/site-packages/strands/memory/types.py:263-323] | SDK-pinned | The D-07 seam: `async search(query, options) -> list[MemoryEntry]` plus optional `add`/`add_messages`/`initialize`/`get_tools` | Harness `resolve_memory(stores=[...])` consumes exactly this; "A consumer can swap the backend by passing their own `stores`" |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Ollama (local VLM) | 0.40.3 binary present, daemon stopped | Local VLM for L0/L1 generation + memory extraction without cloud | Required: server needs a VLM; Ollama is the documented local option |
| Built-in `local` embedding provider | Server-bundled | Default dense embeddings (`bge-small-zh-v1.5-f16`), no API key | Default when `embedding` is omitted; model downloads to `~/.cache/openviking/models` on first use [CITED: https://docs.openviking.ai/en/guides/01-configuration](https://docs.openviking.ai/en/guides/01-configuration) |
| `httpx` (transitive via SDK) | >=0.25.0 | HTTP transport, timeouts | Comes with the SDK; use its timeout for the recall budget |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `openviking-sdk` | Raw `httpx` against the HTTP API | Rejects SDK error mapping (`OpenVikingError`), config precedence, actor-peer scoping — no benefit |
| `openviking-sdk` | Full `openviking` package as a library dep | Heavy deps (fastapi, uvicorn, litellm, volcengine SDKs, tree-sitter pack, scrapy…) + AGPL main license — never a library dep |
| Managed localhost server | User-runs-their-own server on :1933 | Zero lifecycle code, but violates D-01/D-03 (no per-repo store, extra thing to manage); acceptable only as a documented fallback |
| `search(mode="context")` | `find()` + manual tier reads | `find()` is lower-latency QUICK with no rerank/intent; context mode gives one-shot budgeted assembly with `rendered` block |

**Installation:**

```bash
uv tool install openviking --upgrade        # server runtime (deployment prerequisite, not a project dep)
# project dep (after supply-chain review gates the SUS verdict + license question):
#   dependencies += ["openviking-sdk>=0.1.9"]
```

**Version verification:** `openviking` 0.5.0 / `openviking-sdk` 0.1.15 read from the PyPI registry JSON (`info.version`, `requires_python`, `requires_dist`) via registry fetch on 2026-10-16 [CITED: https://pypi.org/pypi/openviking/json](https://pypi.org/pypi/openviking/json) [CITED: https://pypi.org/pypi/openviking-sdk/json](https://pypi.org/pypi/openviking-sdk/json). Local `pip`/`uv` registry lookups were unavailable (sandbox has no PyPI network route — `pip download` returned "No matching distribution"), so versions rest on the registry JSON documents, cross-checked against the official README/docs. Re-verify with `pip index versions openviking-sdk` on a networked host at plan time.

## Package Legitimacy Audit

Seam verdicts via `query package-legitimacy check --ecosystem pypi` (2026-10-16):

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `openviking` | PyPI | 58 releases; 0.5.0 on 2026-10-09 | unknown (null) | github.com/volcengine/openviking | SUS (`too-new`, `unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify` before install; server runtime only, never a library dep |
| `openviking-sdk` | PyPI | 0.1.15 current; ≥0.1.7 since 2026-08-07 | unknown (null) | none recorded by seam (repo is github.com/volcengine/OpenViking, `sdk/python/`) | SUS (`too-new`, `unknown-downloads`, `no-repository`) | Flagged — planner must add `checkpoint:human-verify` before adding the dependency |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `openviking`, `openviking-sdk` — planner inserts `checkpoint:human-verify` before each install.

Corroborating legitimacy evidence (does not override the required checkpoint): author `ByteDance <noreply@bytedance.com>` on PyPI; repo `volcengine/OpenViking` with 30k+ stars reported by secondary press; official docs domain `docs.openviking.ai`; 58 releases on PyPI. The SUS verdicts are the expected shape for a 2026-new package, but per protocol the planner still gates on human verification, compounded by the license question below.

**License flag (supply-chain review input, D-04):** the main project is AGPLv3; `crates/ov_cli` and `examples/` are Apache 2.0; `integrations/frameworks` adapters "declare AGPLv3 in their package metadata" ([CITED: https://github.com/volcengine/OpenViking README License section](https://github.com/volcengine/OpenViking)). The `sdk/python/` directory contains **no LICENSE file** (verified via repo contents listing: only README.md, README_CN.md, `openviking_sdk/`, pyproject.toml, tests/) and its pyproject declares **no license field** — so the SDK's license is ambiguous and likely inherits root AGPLv3 by default. Our project is MIT-0. In-process import of an AGPL-licensed SDK vs. separate-process server use over localhost HTTP have different copyleft implications — the D-04 supply-chain review must resolve this before the dependency is added. [ASSUMED] risk framing; the file-absence facts are verified fetches.

## Architecture Patterns

### System Architecture Diagram

```text
User ask ──► CLI turn loop ──► agent model call
                                      │
                    ┌─────────────────┴──────────────────┐
                    │  Harness MemoryManager (existing)  │
                    │  injection trigger=everyTurn       │
                    └─────────────────┬──────────────────┘
                                      │ search(query)
                    ┌─────────────────▼──────────────────┐
                    │  Composite store (new, CLI-owned)  │
                    │  1. native FileMemoryStore.search  │── hits? ──► inject native only (D-05)
                    │  2. else OV adapter.search         │── hits? ──► inject OV summaries, source=openviking
                    └─────────────────┬──────────────────┘
                                      │ AsyncHTTPClient (openviking-sdk)
                                      │ find() QUICK or search(mode="context", purpose="coding")
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  openviking-server (managed child,   │
                    │  127.0.0.1:<port>, local backends)  │
                    │  workspace = <repo>/.agent/viking/  │
                    └─────────────────┬───────────────────┘
                                      │ AGFS (localfs) + vectordb (local)
                                      ▼  viking://~/memories/*.md + .abstract/.overview sidecars

Write path: /memory approve ──► native file write AND direct OV write()
              (rm on delete ──► OV rm() cascade, D-16)
```

A reader traces the primary use case: ask → manager injection → native search → (empty) OV search over localhost HTTP → tiered summaries injected with `source="openviking"` → drill-down reads L2 on demand.

### Recommended Project Structure

```text
strands_code_cli/
├── ov_memory.py          # OpenVikingMemoryStore adapter (MemoryStore Protocol) + recall helpers
├── ov_server.py          # Managed localhost server lifecycle (spawn, health-poll, shutdown)
├── memory_file.py        # (existing) native side; composite fallback consults it first
├── router.py             # (extend) /memory toggle subcommand + curate apply/deny hooks for OV
├── provider_config.py    # (extend) persisted OV config key + save_*_choice write-through
├── codeact.py            # (reference only) surface-trio + precedence template
└── main.py               # (extend) startup flag + build_agent wiring
tests/
└── test_ov_memory.py     # adapter unit tests (fake SDK client) + lifecycle tests (fake binary)
```

### Pattern 1: MemoryStore-protocol adapter (D-07 seam)

**What:** Implement the Strands `MemoryStore` Protocol in-process; the harness keeps owning the manager, injection, and `search_memory` tool. The verified contract is [VERIFIED: .venv/lib/python3.14/site-packages/strands/memory/types.py:263-323]:

```python
class MemoryStore(Protocol):
    name: str
    description: str | None
    max_search_results: int | None
    writable: bool
    extraction: ExtractionConfig | bool | None

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]: ...
    async def add(self, content: str, metadata: Metadata | None = None) -> Any: ...          # optional
    async def add_messages(self, messages: list[Message], context=None) -> Any: ...           # optional
    async def initialize(self) -> None: ...                                                   # optional, no-op default
    def get_tools(self) -> list[AgentTool]: ...                                               # optional, [] default
```

with `MemoryEntry(content: str, store_name: str | None = None, metadata: ...)` — "Name of the store this entry came from, set by `MemoryManager.search`. Stores need not set this themselves." Feed it via `resolve_memory(stores=[native_file_store, ov_store])` — harness docstring: "A consumer can swap the backend by passing their own `stores`" [VERIFIED: .venv/lib/python3.14/site-packages/strands_harness/memory.py:1-30].

**When to use:** Always for this phase — it is the D-07 shape, and the injection renderer labels provenance for free: ``f'<entry source="{...entry.store_name}">...'`` [VERIFIED: strands/memory/memory_manager.py:735-754].

### Pattern 2: Native-first fallback composite (D-05/D-06)

**What:** Do NOT rely on the manager's default fan-out: `MemoryManager.search` queries **all** stores concurrently via `asyncio.gather(..., return_exceptions=True)` and "concatenated in target order" [VERIFIED: strands/memory/memory_manager.py:296-357], and injection slices the concatenation to `max_results`. That breaks D-05 (OV consulted only when native has nothing) and D-09 (shared cap semantics). Instead the planner composes fallback explicitly — recommended: a single composite store whose `search` queries native first and only calls the OV adapter when native returns nothing relevant; native entries always sort first (D-06).

**When to use:** Required for D-05/D-06/D-09 compliance.

### Pattern 3: Managed localhost server child process (D-01/D-03 nearest shape)

**What:** On enable, the CLI generates a minimal `ov.conf` (`storage.workspace=<repo>/.agent/viking`, `storage.agfs.backend=local`, `vectordb.backend=local`, local embedding, Ollama VLM, `server.host=127.0.0.1`, free port), spawns `openviking-server --config <file>` as a supervised child (process-group kill on exit, like a test fixture — not a daemon), polls `GET /health` for readiness, and kills it at session exit. Workspace default is `"./data"` and is a plain path field [CITED: https://docs.openviking.ai/en/configuration/01-server](https://docs.openviking.ai/en/configuration/01-server); `OPENVIKING_CONFIG_FILE` or `--config` selects the file. This honors D-01's *spirit* (nothing for the user to manage, no daemon) but NOT its letter ("in-process") — see Open Questions.

**When to use:** The only shape consistent with "server required" + D-03 per-repo store + zero user-managed processes.

### Pattern 4: One-shot budgeted recall (D-09/D-10/D-11)

**What:** Prefer `search(mode="context", purpose="coding", max_tokens=<share of cap>, detail="abstract", rewrite=false, query_expansion="off")` for prefix injection: server-side tier filling inside a token budget with a ready-to-inject `rendered` XML block, per-entry `{uri, category, detail, text}` for D-11 labeling, and `stats.used_tokens` for cap accounting [CITED: https://docs.openviking.ai/en/api/06-retrieval](https://docs.openviking.ai/en/api/06-retrieval). Purpose `coding` uses quotas `events:1, entities:2, preferences:1, experiences:1, resources:3, skills:2`. Use plain `find()` (QUICK, no rerank/intent, lower latency) when the loop only needs candidate URIs, then `abstract()`/`overview()` for summaries and `read()` for D-12 drill-down.

**When to use:** `mode="context"` for turn-prefix injection; `find()` + tier reads for drill-down and tool-driven navigation.

### Pattern 5: Curate-gated direct writes, never session-commit extraction (D-13/D-14)

**What:** Approved `/memory` proposals write macro entries directly to `viking://~/memories/<type>/<slug>.md` via the filesystem `write()`/`mkdir()` API (same API family as `read`/`mkdir`/`rm`/`mv` [CITED: https://docs.openviking.ai/en/concepts/05-storage](https://docs.openviking.ai/en/concepts/05-storage)). Do NOT route CLI turns through `add_message`+`commit()`: default commits archive all messages and run async LLM extraction over transcripts, which mirrors session content and violates D-13 macro-only. Memory types available: `profile`, `preferences`, `entities`, `events`, `identity`, `soul`, `cases`, `trajectories`, `experiences` (+ custom), stored under `viking://user/{user_id}/memories/...` [CITED: https://docs.openviking.ai/en/api/16-memory](https://docs.openviking.ai/en/api/16-memory).

**When to use:** All D-14 writes; session/commit APIs stay out of scope this phase.

### Pattern 6: `/codeact` surface-trio mirror (D-17/D-20)

**What:** Copy the verified trio shape: `typer.Option --<name>` flag with `BadParameter` validation in `main.py` [VERIFIED: strands_code_cli/main.py:212-225], `ProviderConfig` key + `save_*_choice` write-through [VERIFIED: strands_code_cli/provider_config.py:21-106], and `resolve_initial_interface(flag, saved, remember)` precedence (flag first) [VERIFIED: strands_code_cli/codeact.py:377-401] — except D-18 makes persistence unconditional (no `remember` gate) and D-19 makes the toggle write through to the config key.

### Anti-Patterns to Avoid

- **Appending the OV store to the manager's store list and calling it done:** manager fan-out + concatenation breaks D-05/D-09; compose fallback explicitly (Pattern 2).
- **Depending on the full `openviking` package:** ~50 heavy deps + AGPL; depend only on `openviking-sdk`, treat the server as a runtime binary.
- **Routing turns through session commit for capture:** archives transcripts, async nondeterministic extraction, violates D-13; use direct macro writes (Pattern 5).
- **Assuming a server is already running on :1933:** the CLI must own lifecycle (spawn/health/kill) or fail soft with an actionable note; never block the turn loop on a missing server.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector embeddings + similarity index | numpy cosine store, sqlite-vec DIY | Server `local` vectordb backend + built-in local embedding | Dimension migration, delta replay, hybrid index, quantization — server handles; format upgrades are one-way and backup-sensitive |
| Tiered summaries (L0/L1) | Prompt-chaining summarizer in CLI | Server SemanticQueue generation (`.abstract.md`/`.overview.md` sidecars) | Bottom-up refresh, freshness sampling, parent invalidation, OKF frontmatter validation |
| HTTP client + error mapping | Raw httpx calls + hand-parsed errors | `openviking_sdk` (`SyncHTTPClient`/`AsyncHTTPClient`, `OpenVikingError`) | Config precedence (ctor > env > `ovcli.conf`), typed options, server error mapping |
| Injection rendering + provenance | Custom prefix formatter | Manager `_default_injection_format` (`<entry source=...>`) | XML escaping, fail-open on formatter errors, store attribution |
| Recall budgeting | Char-count truncation | `search(mode="context", max_tokens=...)` tier filling | Per-entry caps with step-down (never mid-tier truncation), quota buckets, `stats.used_tokens` |

**Key insight:** Every deceptively-simple piece (budgeting, tier refresh, vector format compat) has server-side queue/lock/version machinery behind it; the CLI's job is adapter + lifecycle + gating, never retrieval internals.

## Common Pitfalls

### Pitfall 1: D-01 says in-process; OpenViking requires a server

**What goes wrong:** Planner designs an embedded library integration that cannot exist; executor discovers mid-phase that every operation needs HTTP to a running server.
**Why it happens:** The `viking://` filesystem metaphor reads like a local library; in reality only the RAGFS binding is in-process *inside the server process*, and all clients (SDK/CLI/MCP/plugins) connect over HTTP.
**How to avoid:** Adopt Pattern 3 (managed child process) and re-confirm D-01's letter-vs-spirit with the user before planning (Open Question 1).
**Warning signs:** Any task saying "import the OpenViking engine" or "call RAGFS directly from the CLI".

### Pitfall 2: AGPL/ambiguous SDK license linked into an MIT-0 project

**What goes wrong:** Adding `openviking-sdk` as a dependency without resolving that the SDK ships no license file/field while the parent project is AGPLv3.
**Why it happens:** "Official SDK, httpx-only" looks supply-chain-clean at a glance.
**How to avoid:** D-04 supply-chain review must rule on the SDK license (and on spawning the AGPL server binary) before the dep is added; planner gates with `checkpoint:human-verify`.
**Warning signs:** Lockfile PR adding the dep with no license note.

### Pitfall 3: Recall blocks the turn loop

**What goes wrong:** Prefix injection waits on embedding + vector search + (worst case) intent LLM + rewrite LLM; a cold Ollama VLM or missing server stalls every turn.
**Why it happens:** Defaults favor quality: intent analysis on when `session_id` present, rewrite available, server timeouts 5s (intent) / 30s (rewrite), plugin client floor 15s/45s [CITED: https://docs.openviking.ai/en/agent-integrations/19-recall-tuning](https://docs.openviking.ai/en/agent-integrations/19-recall-tuning).
**How to avoid:** Recall with `query_expansion="off"`, `rewrite=false`, tight httpx timeout; fail soft to native-only on timeout; never `rewrite=true` on the turn path. Success criterion 2 ("without blocking the turn loop") depends on this.
**Warning signs:** Recall latency tests missing; no timeout configured on the SDK client.

### Pitfall 4: Async write-then-read races

**What goes wrong:** `add_resource`/`commit` return `task_id` before semantic/embedding queues finish; an immediate `find` misses the new content and the turn reports "nothing recalled".
**Why it happens:** Parsing → semantic queue (L0/L1 model calls) → embedding queue → vector index is async by design [CITED: https://docs.openviking.ai/en/concepts/06-extraction](https://docs.openviking.ai/en/concepts/06-extraction).
**How to avoid:** After curate-gated writes, either poll `get_task(task_id)` to `completed` off the turn path or accept eventual consistency and document it; never poll on the recall path.
**Warning signs:** Flaky "write then recall" tests; tests passing only with sleeps.

### Pitfall 5: Score is not a 0..1 relevance gate

**What goes wrong:** Thresholding `score < 0.7 → irrelevant` for D-05 "nothing relevant" silently drops everything or keeps everything depending on backend.
**Why it happens:** "`score` is not universally bounded to `[0, 1]`: its scale depends on the backend, metric and postprocessing" [CITED: https://docs.openviking.ai/en/api/06-retrieval](https://docs.openviking.ai/en/api/06-retrieval).
**How to avoid:** Define "nothing relevant" structurally (native returned zero entries) rather than by OV score; if score-thresholding, calibrate per backend and pin the backend.
**Warning signs:** A `SCORE_THRESHOLD = 0.7` constant with no calibration note.

### Pitfall 6: L0/L1 sidecars may be absent independently

**What goes wrong:** Drill-down assumes `.abstract.md` + `.overview.md` always coexist; `mkdir()` creates only L0 initially, and "callers should not assume every directory always has both sidecars" [CITED: https://docs.openviking.ai/en/concepts/03-context-layers](https://docs.openviking.ai/en/concepts/03-context-layers). Also they are *directory*-level, not per-file.
**How to avoid:** Treat each tier read as fallible with step-down (uri-only floor, like the server's own tier rules); aggregate per-file content at the directory level.
**Warning signs:** `KeyError`/None-deref on `overview` in recall tests.

### Pitfall 7: One workspace per server instance vs per-repo store

**What goes wrong:** D-03 wants `.agent/viking/` per repo, but `storage.workspace` is a server-level path — one long-lived server cannot serve N repos' stores.
**Why it happens:** Server lifecycle designed around one deployment, one workspace.
**How to avoid:** Pattern 3 spawns one server per repo session (free port each); concurrent same-workspace servers risk the `.openviking.lock` process lock — never set `skip_process_lock` to dodge it.
**Warning signs:** Two CLI sessions in one repo fighting over a port or lock file.

### Pitfall 8: `.agent/viking/` git-trackability vs workspace internals

**What goes wrong:** The workspace holds the vector index, `queue/queue.db`, locks, and model caches alongside AGFS content — binary churn and machine-local state committed to git.
**Why it happens:** D-03 says "git-trackable" but the workspace is an operational directory, not a document tree.
**How to avoid:** Planner must decide the git boundary (ignore index/queue/lock paths, track only AGFS content) after inspecting a real workspace layout; document in the plan. [ASSUMED] internal layout details — workspace file inventory unverified (no live server probed).
**Warning signs:** `git status` showing `*.db`/lock churn after a recall session.

### Pitfall 9: VLM + first-run model downloads vs "offline-capable"

**What goes wrong:** Fresh machine: server needs a VLM (Ollama daemon + model pull) and downloads the default embedding model to `~/.cache/openviking/models` on first use — first run is not offline.
**Why it happens:** "Prepare access to an embedding model and a VLM" is a setup prerequisite [CITED: https://docs.openviking.ai/en/getting-started/02-quickstart](https://docs.openviking.ai/en/getting-started/02-quickstart).
**How to avoid:** D-02 holds *after provisioning*: setup flow must pull models once (documented, networked step), then run offline; fail soft with an actionable note when the VLM is unreachable.
**Warning signs:** "Works on my machine" where the cache was warm; CI with no cache.

### Pitfall 10: Context-mode parameter traps

**What goes wrong:** 400s from `target_uri` in context mode ("not supported in context mode yet"), `level` silently ignored (`detail` governs tiers), `limit` ignored when `purpose`/`quotas` active, `read_content` rejected in context mode [CITED: https://docs.openviking.ai/en/api/06-retrieval](https://docs.openviking.ai/en/api/06-retrieval).
**How to avoid:** Use `detail` + `purpose`/`quotas` + `max_tokens` only in context mode; check `stats.ignored` in tests.
**Warning signs:** Recall requests carrying both `target_uri` and `mode="context"`.

### Pitfall 11: Deprecated recall endpoint

**What goes wrong:** Copying older examples using `POST /api/v1/search/recall`.
**Why it happens:** It exists and works (with a `Deprecation: true` header) but "Do not use it for new integrations" — it is a preset over `search(mode="context")` with `purpose="coding"` [CITED: https://docs.openviking.ai/en/api/16-memory](https://docs.openviking.ai/en/api/16-memory).
**How to avoid:** Use `search(mode="context")` directly.

## Code Examples

Verified patterns from official sources (SDK README + docs):

### Recall: one-shot budgeted context block

```python
# Source: https://docs.openviking.ai/en/api/06-retrieval (curl examples) + SDK README client shape
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()

result = client.search(
    query="pytest asyncio plugin preference",
    options={
        "mode": "context",
        "purpose": "coding",      # events:1, entities:2, preferences:1, experiences:1, resources:3, skills:2
        "max_tokens": 1600,
        "detail": "abstract",     # summaries first (D-10); step-down beats truncation
        "rewrite": False,         # no digest LLM on the turn path (Pitfall 3)
        "query_expansion": "off",
    },
)
block = result["result"]["rendered"]   # flat XML, ready to inject
used = result["result"]["stats"]["used_tokens"]
```

### Recall: QUICK find + tier reads for drill-down

```python
# Source: https://docs.openviking.ai/en/concepts/07-retrieval + /en/concepts/03-context-layers
results = client.find(query="OAuth authentication", target_uri="viking://~/memories/")
# results: {memories: [...], resources: [...], skills: [...]}, each hit has uri/level/abstract/overview/score
abstract = client.abstract(uri="viking://~/memories/preferences/")   # L0
overview = client.overview(uri="viking://~/memories/preferences/")   # L1
content = client.read(uri="viking://~/memories/preferences/pytest.md")  # L2 drill-down (D-12)
```

### Capture: direct macro write + cascading delete

```python
# Source: SDK README filesystem ops + storage core-API table (write/mkdir/rm)
client.mkdir(uri="viking://~/memories/preferences")
client.write(uri="viking://~/memories/preferences/pytest.md", data="# pytest\n\nUse asyncio_mode=auto.\n")
client.rm(uri="viking://~/memories/preferences/pytest.md")  # D-16 cascade target
```

Note: exact `write()` signature (`uri, data`) is per the storage Core API table (`write(uri, data)`); the SDK README demonstrates `mkdir`/`ls`/`read` verbatim and the table adds `write`/`rm`/`mv`/`abstract`/`overview`/`find(query, uri)` [CITED: https://docs.openviking.ai/en/concepts/05-storage](https://docs.openviking.ai/en/concepts/05-storage). Executor must confirm kwarg names against the installed SDK (docstrings/source) — see Open Question 5.

### Seam: adapter skeleton honoring the verified Protocol

```python
# Contract source: strands/memory/types.py:263-323 (read this session, see Pattern 1)
from strands.memory import MemoryEntry, MemoryStore, SearchOptions

class OpenVikingMemoryStore(MemoryStore):
    name = "openviking"
    description = "Cross-session macro recall (preferences, fixes, constraints)."
    max_search_results: int | None = 5
    writable = True
    extraction = False  # no manager-driven extraction; writes are curate-gated (D-14)

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]:
        ...  # find()/search(mode="context") via AsyncHTTPClient; fail soft ([]) on timeout
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `POST /api/v1/search/recall` | `search(mode="context")` (+ `purpose="coding"` preset) | v1 deprecation, current docs | New code must use context mode; old endpoint kept with `Deprecation: true` |
| Flat vector memory (black-box index) | `viking://` virtual filesystem + L0/L1/L2 tiered loading | OpenViking 0.3–0.5 (2026) | Inspectable, browsable (`ls`/`tree`/`grep`), token-efficient recall |
| Custom per-harness recall stitching | Server-side context assembly (`rendered` + `stats`) | `mode="context"` introduction | One request, shared budgeting/dedup across harnesses |
| Keyless localhost `trusted` mode | `trusted` requires a root key (localhost follows the auth contract) | Recent `fix(auth)!` commit on main (secondary: commit list) | Pin `auth_mode: dev`/default local (no key needed per quickstart); do not rely on `trusted` without a key |

**Deprecated/outdated:**
- `POST /api/v1/search/recall`: deprecated preset — use `search(mode="context")`.
- `search()` without mode for memory recall: superseded by context mode for injection; keep `find()` for simple QUICK queries.
- `uid`-less `viking://user/memories` spelling: rejected — use the `viking://~/...` home alias form.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No embedded in-process OpenViking mode exists (all clients need a running server) | Summary, OQ1 | LOW reversal risk — stated twice in official docs; if an embed path exists it only eases D-01 |
| A2 | Workspace internal layout (index/queue/lock filenames under `storage.workspace`) | Pitfall 8 | MEDIUM — git-boundary plan needs a live `ls`; executor must inventory first |
| A3 | `client.write(uri=..., data=...)` kwarg names | Code Examples | LOW — executor confirms against installed SDK in minutes |
| A4 | SDK inherits root AGPLv3 absent its own license | Legitimacy Audit | HIGH — legal posture; must be resolved by supply-chain review, not assumed |
| A5 | Local embedding default model size/download cost | Pitfall 9 | LOW — affects setup docs, not architecture |
| A6 | In-process ASGI embedding of the server app is technically possible (docs mention "embedded ASGI applications" once, re restart-unsupported) | OQ6 | MEDIUM — a spike could rescue D-01's letter, or confirm it impossible |

## Open Questions

1. **D-01 embedded-vs-server tension (BLOCKS planning)**
   - What we know: Official docs state twice that every integration needs a running server; no embedded mode is documented. A managed localhost child process honors "nothing to manage, no daemon" but violates "in-process".
   - What's unclear: Whether the user accepts the managed-child interpretation or wants a re-discussion of D-01 (and the Deferred "sidecar-daemon rejected" line).
   - Recommendation: Re-confirm with the user before planning; planner must not silently reinterpret a locked decision.

2. **SDK license (BLOCKS adding the dependency)**
   - What we know: `sdk/python/` has no LICENSE and no pyproject license field; parent project is AGPLv3 (our project is MIT-0).
   - What's unclear: Whether ByteDance intends the SDK as AGPL (like `integrations/frameworks` adapters) or permissive.
   - Recommendation: D-04 supply-chain review rules first; planner gates the dep behind `checkpoint:human-verify` regardless.

3. **D-15 "contradiction resolution" mechanism**
   - What we know: The commit path runs ExtractLoop → MemoryUpdater producing add/edit/delete ops with a `memory_diff.json` audit log; direct `write()` overwrites. No standalone "contradiction resolution" API was found in docs.
   - What's unclear: Whether D-15 means commit-path MemoryUpdater semantics or plain overwrite-on-write.
   - Recommendation: Planner picks "overwrite via `write()` (+ optional `memory_diff`-style audit)" and notes the deviation if the user meant the commit path. Do NOT adopt the commit path just to get the updater (violates D-13).

4. **Per-repo workspace git boundary**
   - What we know: `storage.workspace` is server-level and configurable; AGFS content + vector index + queue share it (dual-layer architecture).
   - What's unclear: Exact on-disk layout (which paths are binary/machine-local).
   - Recommendation: First executor task inventories a live workspace; planner writes the `.gitignore` boundary from that.

5. **Exact SDK method signatures**
   - What we know: Method names verified (`find`, `search`, `read`, `write`, `mkdir`, `rm`, `mv`, `abstract`, `overview`, `get_task`, `health`, `initialize`, `close`); some kwarg shapes confirmed only via docs tables.
   - What's unclear: Precise kwargs/return types of the installed 0.1.x SDK.
   - Recommendation: Executor confirms against installed SDK docstrings in Wave 0; no plan task should hardcode unconfirmed kwargs.

6. **In-process ASGI spike (D-01 rescue attempt)**
   - What we know: Server-config docs mention "embedded ASGI applications" once (restart unsupported); the app is FastAPI-based (dependency-verified).
   - What's unclear: Whether the ASGI app object is importable/configurable for in-process serving (e.g., httpx ASGI transport) with local backends.
   - Recommendation: Optional time-boxed spike in Wave 0; failure keeps Pattern 3 as the plan. Do not promise D-01-letter compliance without a passing spike.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.14.8 (`python3 --version`); project requires >=3.10 | — |
| `uv` + lockfile | Deps/tests | ✓ | 0.12.23; `uv run pytest tests/ -v` per README | — |
| `openviking-server` binary | Recall/capture at runtime | ✗ | — | Install step: `uv tool install openviking` (networked); tests use fake server/SDK doubles |
| `openviking-sdk` importable | Adapter | ✗ (not installed) | PyPI 0.1.15 | Add after license + SUS checkpoints; unit tests run against a fake client regardless |
| Ollama daemon + VLM model | L0/L1 generation, extraction (server-side) | Partial (binary 0.40.3 present, daemon stopped, no models listed) | 0.40.3 | `ollama serve` + pull a small model (networked setup step); recall degrades gracefully without VLM only for vectors-only content |
| Network (first-run model download) | Embedding model warm-up | ✗ in sandbox | — | One-time provisioned step outside sandbox; steady state is offline |
| Strands MemoryStore seam | D-07 | ✓ | strands-agents 1.58.1 in `.venv` | — |

**Missing dependencies with no fallback:**
- None blocking planning; all gaps are provisioned at setup time.

**Missing dependencies with fallback:**
- `openviking-server` binary → install step + fake-server test doubles.
- Ollama daemon/models → start + pull step; recall fails soft until provisioned.
- First-run embedding download → one-time networked provisioning; documented as setup.

## Validation Architecture

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked; `addopts = -m 'not integration'`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| Quick run command | `uv run pytest tests/test_ov_memory.py -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| SKILL-05 | Opt-in trio enables OV recall; default off is byte-identical (D-08) | unit | `uv run pytest tests/test_ov_memory.py -x -q -k opt_in` | ❌ Wave 0 |
| SKILL-05 | Native-first fallback: native hits → OV never consulted (D-05) | unit (fake stores) | `uv run pytest tests/test_ov_memory.py -x -q -k fallback` | ❌ Wave 0 |
| SKILL-05 | Prefix injection under shared cap with `source=openviking` labels (D-09/10/11) | unit (fake SDK payloads) | `uv run pytest tests/test_ov_memory.py -x -q -k inject` | ❌ Wave 0 |
| SKILL-05 | Curate-gated macro write + supersede + delete cascade (D-13/14/15/16) | unit (fake SDK) | `uv run pytest tests/test_ov_memory.py -x -q -k curate` | ❌ Wave 0 |
| SKILL-05 | Server lifecycle: spawn/health/shutdown; fail-soft when binary missing | unit (fake binary) + integration (real server, needs `integration` marker or skip-if-missing) | `uv run pytest tests/test_ov_server.py -x -q` | ❌ Wave 0 |
| SKILL-05 | Non-blocking recall: timeout → native-only, turn unaffected | unit (timeout-injecting fake) | `uv run pytest tests/test_ov_memory.py -x -q -k timeout` | ❌ Wave 0 |

Related existing suites (must stay green): `tests/test_memory_file.py`, `tests/test_memory_curate.py`, `tests/test_codeact.py`, `tests/test_cli_entry.py` (all present in tree).

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_ov_memory.py tests/test_ov_server.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_ov_memory.py` — covers SKILL-05 adapter/recall/capture/opt-in behaviors
- [ ] `tests/test_ov_server.py` — covers lifecycle + fail-soft (fake binary; live-server case skips when binary absent)
- [ ] `tests/conftest.py` — exists; add shared OV fakes (fake SDK client, fake FileMemoryStore) if not present
- [ ] SDK signature confirmation task (Open Question 5) — before freezing adapter kwargs
- [ ] Live workspace inventory task (Open Question 4) — before freezing the git boundary

## Security Domain

ASVS Level 1 (`security_enforcement: true`, `security_block_on: high` in `.planning/config.json`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (localhost) | Default local setup needs no API key [CITED: quickstart]; if auth enabled, user key (never root key for data access) via env/`ovcli.conf`, never logged or echoed; recent `trusted`-requires-root-key change — pin `dev`/default mode for localhost |
| V3 Session Management | No | No browser sessions; CLI session ids already validated (`_validate_session_id`) |
| V4 Access Control | Yes | Bind `127.0.0.1` only (never `0.0.0.0`); per-repo workspace confinement (no `..` escapes in URI→path mapping); managed child inherits CLI user |
| V5 Input Validation | Yes | Validate `viking://` URIs (reject `uid`-less spellings per server rules); treat ALL recalled memory as untrusted repo-equivalent text — memory content must never widen tool scope (same rule as `memory_file.py` untrusted prefix); XML-escape via manager renderer |
| V6 Cryptography | Partial | No hand-rolled crypto; API keys at rest only in `~/.openviking/ovcli.conf` (0600-style) or env — never in `config.yaml` (non-secret precedent in `provider_config.py`) and never in the repo store |
| V7 Errors/Logging | Yes | Fail-soft recall (log + skip, never stack-trace the turn); never log keys, memory bodies, or server tokens |
| V8 Data Protection | Yes | `.agent/viking/` may hold sensitive preferences — repo already 0600s `.agent` files (`dump_memory_file`); extend perms thinking to workspace; deletes cascade (D-16) must actually purge vectors (`rm` "syncs vector deletion" per Core API table) |
| V10 Malicious Code | Supply chain | SUS verdicts + AGPL ambiguity → `checkpoint:human-verify` gates; no upper pins per project policy but deliberate resync; installer scripts (`openviking.ai/install`) are OUT of scope — never curl-pipe in automation |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via recalled memories | Tampering/Elevation | Untrusted-content labeling (D-11 `source` tags + existing `MEMORY_UNTRUSTED_PREFIX` precedent); recalled text never auto-approves tools; deny-first gate unchanged |
| Memory poisoning (malicious repo writes macros) | Tampering | D-14 curate gate on every write; D-13 macro-only (no transcript mirroring); provenance URIs auditable via `ls`/`read` |
| localhost server hijack / port squat | Spoofing | Bind 127.0.0.1, free-port selection + lockfile ownership check, health-check identity (expect our workspace marker), kill-on-exit |
| Credential leak (API keys into memory/vectors) | Information disclosure | Never store keys in memories (scan precedent: `_looks_key_shaped` in `memory_file.py`); keys via env only; `ov` CLI key-empty for local |
| Copyleft contamination (AGPL) | Legal/Compliance | D-04 supply-chain review + human-verify checkpoints before dep add and before any server-binary redistribution |

## Sources

### Primary (HIGH confidence)

- Strands SDK + harness sources in `.venv` (MemoryStore Protocol, MemoryManager fan-out/injection, `resolve_memory`) — read this session, quoted verbatim.
- Repo sources: `strands_code_cli/memory_file.py`, `memory_modes.py`, `codeact.py`, `provider_config.py`, `main.py`, `router.py`, `loop.py`, `btw.py` — read/grepped this session.
- PyPI registry JSON for `openviking` 0.5.0 and `openviking-sdk` 0.1.15 (versions, requires-python, dependencies) — fetched 2026-10-16.

### Secondary (MEDIUM confidence)

- Official docs `docs.openviking.ai` (concepts 00–08, configuration 01-server, guides 00/01, api 06/16, agent-integrations 01/19, quickstart 02) — fetched and quoted this session.
- Official README + `sdk/python` sources via raw.githubusercontent + GitHub contents API (license section, pyproject, SDK README quoted verbatim).
- `openviking-sdk` PyPI long description (client API, config precedence, auth model) — quoted verbatim.

### Tertiary (LOW confidence)

- Tavily search results (FAQ RAGFS in-process note, `trusted`-mode commit message, third-party benchmark/token claims) — used only as cross-checks, not as plan inputs.
- Training knowledge — flagged `[ASSUMED]` wherever it appears (see Assumptions Log).

## Metadata

**Confidence breakdown:**

- Standard stack: MEDIUM — versions + API surface verified against registry + official docs; installability unproven in sandbox (no PyPI route).
- Architecture: MEDIUM — seam mechanics verified in-tree; server-lifecycle shape follows documented config but is unprobed live; D-01 tension unresolved.
- Pitfalls: HIGH — drawn from explicit documented limits (400s, deprecations, async tasks, score scale, sidecar absence rules).

**Research date:** 2026-10-16
**Valid until:** 2026-11-15 (project is Alpha and fast-moving: 58 releases, `fix(auth)!` breaking change on main; re-check SDK signatures + changelog at plan time)
