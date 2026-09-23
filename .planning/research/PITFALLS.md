# Pitfalls Research

**Domain:** Conversational coding-agent CLI on strands-agents 1.x + strands-harness 0.1.x (both Experimental upstream), built as a follow-on milestone on an existing agent library
**Researched:** 2026-09-23
**Confidence:** HIGH for CLI-generic failure modes (empirical bug study of Claude Code / Codex / Gemini CLI + widespread incident reports); MEDIUM for Strands-specific churn details (upstream lifecycle docs + locked versions 1.57.0 / 0.1.2)

## Critical Pitfalls

### Pitfall 1: Runaway tool loops burn money silently

**What goes wrong:**
An agent hits an obstacle, tries to fix it, hits another obstacle inside the fix, and recurses until the original task is forgotten. Each iteration is a full billed model call with the full history attached. Documented incidents: a looping agent burning $4,200 in 63 hours, a $6,531 AWS bill from an unscanned hobby network scan in days, two agents ping-ponging for 11 days for a $47,000 bill. This repo currently has no turn cap, no output cap, and no budget enforcement — display-only cost with no halting is the v1 plan.

**Why it happens:**
No `max_turns` / step budget, no loop detector (repeated identical tool calls), no spending gate outside the agent loop. Context accumulation makes each successive call more expensive than the last, so cost accelerates as the loop continues.

**How to avoid:**
Enforce turn/step budgets at the harness layer (not as agent instructions the model can ignore); add a loop circuit-breaker (same tool + same args N times in a row → stop and ask); keep per-session cost display from day one and add a hard session cap as a non-bypassable gate outside the agent loop, even if the default cap is generous. Treat budget as a pre-execution gate, not post-hoc logging.

**Warning signs:**
Session token counts climbing with no new files changed; same `read`/`shell` command repeating with identical arguments; `/cost` output growing 10x between user-visible progress; tests failing identically three turns in a row while the agent says "interesting, let me try another approach".

**Phase to address:**
First CLI loop phase (task loop + subagent orchestration) — budgets and loop-breakers must ship with the loop itself, not as later polish. Enforcement (hard caps) can be a follow-up, but the counting/plumbing must be in the loop from the start.

---

### Pitfall 2: Context-window blowup degrades quality before it errors

**What goes wrong:**
Long sessions accumulate tool outputs, dead ends, and wrong assumptions until the model silently gets worse — forgetting earlier instructions and earlier file states around 70–80% capacity — then either errors or produces confident garbage. Truncation-based recovery loses the agent's memory of its own earlier work. The harness `context_manager` surface that is supposed to handle this is flagged Experimental upstream, so its behavior will shift under us.

**Why it happens:**
No staged pressure response (warn → prune old tool outputs → mask observations → compact); bulky tool results (full test logs, whole-file reads) dumped verbatim into history; compaction that summarizes away the one critical constraint (e.g. "never use ExecPythonInterpreter as default").

**How to avoid:**
Keep harness wrappers thin and pin the verified harness minor version; implement staged context management (token-pressure thresholds with prune-then-compact, mirroring the ~0.70 warn / 0.80 mask / 0.85 prune / 0.99 compact pattern proven in terminal-agent scaffolding); truncate bulky tool results at ingest (~1500 tokens with a pointer to the full log on disk); make `/compact` take a focus instruction and always preserve the permissions/policy block verbatim; give `/clear` (fresh start, session saved) equal prominence to `/compact` since compacting over a poisoned assumption preserves the poison.

**Warning signs:**
Agent re-asking for information already established in-session; edits that contradict decisions made 20 turns earlier; compaction summaries that omit the safety policy; steadily growing time-to-first-token with no task progress.

**Phase to address:**
Context/observability phase (context commands + `/cost` + tracing), with the ingest-truncation rule landing in the file/edit-tools phase. Add a regression test: compact a session containing a safety rule and assert the rule survives.

---

### Pitfall 3: Destructive file/git actions with no reversibility

**What goes wrong:**
The agent runs `rm -rf`, overwrites the wrong file, force-pushes, drops a database table, or applies an edit to a path outside the project. YOLO/`--dangerously-skip-permissions` style modes make this a one-incident catastrophe. Competitor post-mortems ("Claude Code almost deleted my database") converge on the same lesson: instructions in CLAUDE.md/AGENTS.md are not a safety boundary — a confused or injected agent ignores them.

**Why it happens:**
Allow-list-only thinking (permit what you anticipate, prompt on everything else fatigues the user into allow-all); no deny-list enforced below the model layer; no snapshot/undo before edits; git operations (push, reset --hard, clean -fd) treated like any other shell command.

**How to avoid:**
Deny-first permissions enforced outside the agent loop: a policy file with hard `deny` rules (credential paths, `rm -rf`, `git push --force`, `git reset --hard`, `DROP/DELETE`, writes outside project dirs) that override any allow; snapshot every file before edit (`/diff` viewer + `/undo`); keep `git push` behind an explicit approval in v1; never ship a skip-permissions flag without a denylist that survives it. Our `interventions="ask"|"smart"|policy` harness seam plus a permissions-policy UX is exactly this layer — build it in the permissions phase, not later.

**Warning signs:**
Users reaching for allow-all to stop prompt fatigue; edits landing outside the working tree; `git status` showing unexpected deletions after an agent turn; approval prompts for reads (noise) while writes sail through.

**Phase to address:**
Permissions/HITL phase (policy file + approval prompts + env scrub + sandbox presets), wired before the GitHub-loop phase that gives the agent push/branch/PR powers.

---

### Pitfall 4: Prompt injection via repo content, issues, and tool output

**What goes wrong:**
Attacker plants instructions in a trusted-looking file (`README.md`, `LICENSE.md`, `.cursorrules`, issue text, PR comments, MCP tool descriptions); the agent reads it during normal operation and obeys — installing malicious automation, exfiltrating secrets, or rewriting config. Multi-stage variants achieve persistent arbitrary code execution across sessions. Our CLI's home turf (reading issues/PRs, deep-researching repos, loading skills from `./.agent/skills`) maximizes exposure to untrusted text.

**Why it happens:**
Treating retrieved content as instructions instead of data; no boundary between system prompt and tool output; skills/config auto-loaded without provenance checks; MCP servers with unaudited tool descriptions treated as trusted system content.

**How to avoid:**
Structural mitigations, not model-layer hope: delimit and label untrusted content as data-only at prompt-construction time; block writes to agent config files (skills dirs, policy file, hooks) without explicit user approval — an injected instruction must not be able to persist itself; sandbox execution so a successful injection still can't act (least-privilege tools, network egress controls); verify MCP server sources and audit tool descriptions; never auto-execute shell snippets found in repo content. The HiddenLayer prompt-injection integration and guardrails in the native stack are a starting point, not the whole answer.

**Warning signs:**
Agent proposing config/skill edits unprompted after reading a repo file; tool calls referencing URLs or commands that appear verbatim in issue text; `curl|sh` patterns in proposed commands; skill files changing without a user `/skill install` action.

**Phase to address:**
Permissions/HITL phase for the structural controls (config-write gating, sandbox, egress); slash-registry/skills phase for skill provenance + auto-load policy; GitHub-loop phase for issue/PR-content-as-data handling. Add a quarterly red-team test: plant an injection in a test repo file and assert it is treated as data.

---

### Pitfall 5: Session resume that silently loses work

**What goes wrong:**
Sessions fail to persist, resume as a blank slate, reset agent state mid-task, or restore context inconsistently so follow-ups contradict earlier decisions. The empirical bug study of Claude Code/Codex/Gemini CLI puts session/state failures at ~6% of all reported bugs (persistence, resumption, state reset, compaction errors, history loss). Our gap analysis notes the current `CODE_AGENT_INSTRUCTIONS` literally tells the model the interpreter "resets completely with each new user message" — the wiring doesn't exist yet, so v1 will invent it.

**Why it happens:**
Forgetting `flush()` before shutdown (memory extraction runs in background ~every 5 turns and is lost on kill); no session start/end + reclaim policy; actor identity missing so `--session-id` routes to the wrong store; conflating conversation management (stay in window) with session management (resume later) with memory (knowledge across sessions).

**How to avoid:**
Wire `session_manager` (file-based locally) + explicit `flush()`-on-exit from the first session phase; add `--session-id` routing with actor identity and a session list/reclaim policy; keep the three Strands concepts separated (session / conversation / memory) exactly as upstream defines them — do not build a custom session store for v1; test kill-and-resume (`SIGKILL` mid-task → resume → assert task state intact) as an acceptance test.

**Warning signs:**
"Resumed" sessions that greet the user with no memory of prior work; background memory tools (`add_memory`) with no `flush()` call on the shutdown path; session files growing without a reclaim/expiry story; two CLI instances sharing one session id.

**Phase to address:**
Session-wiring phase (first in build order) — this is the foundation everything else resumes on. Memory tiers (markdown → Hindsight → memsearch) layer on afterward behind the same interface.

---

### Pitfall 6: Building on Experimental upstream without a churn bulkhead

**What goes wrong:**
A routine `uv sync` pulls a new `strands-agents` 1.x minor or `strands-harness` 0.1.x release and the CLI breaks: message content shapes consumed directly by the callback handler change, harness flag semantics shift, experimental context-management behavior moves. Strands policy explicitly excludes experimental features from semver/back-compat guarantees between minors and advises pinning to a specific minor. Our `pyproject.toml` currently has unbounded floors (`strands-agents>=0.1.0`, `strands-harness>=0.1`) and the callback handler indexes message shapes directly.

**Why it happens:**
Depending on pre-1.0/0.x APIs as if they were stable; consuming upstream internals positionally (`message['content']`, `tool_use['input']['code']`, metrics-dict indexing in `utils.py`); resyncing upstream continuously instead of deliberately.

**How to avoid:**
Deliberate-resync discipline per PROJECT.md: lock working versions, upgrade on a schedule with the full 177-test suite + a message-shape regression test as the gate; keep harness wrappers thin (string flags + passthrough kwargs, never a fork of harness internals); use `.get()`-with-fallback access on all upstream message/metrics shapes; add the missing CI test gate (currently only a PyPI publish workflow) so breakage is caught before merge; consult the harness `HARNESS_CONTRACT` export to detect contract drift.

**Warning signs:**
`KeyError` in callback rendering or metrics after a dependency bump; `uv.lock` diff touching strands packages without a corresponding test run; new `DeprecationWarning` churn from `smolagents`/`strands` introspection paths; code that imports harness internals rather than the documented `create_harness` surface.

**Phase to address:**
Project setup / CI phase first (test gate + pinned-and-gated resync policy), then enforced as a standing rule in every phase that touches harness seams. No phase may add a new upstream-internal dependency without a shape-tolerant accessor + regression test.

---

### Pitfall 7: AWS coupling that breaks the offline default

**What goes wrong:**
Bedrock-as-default-model, AgentCore session/memory managers, or an unconditional `import boto3` make the CLI require AWS credentials to start — destroying the local/offline story and failing in CI, on planes, and for non-AWS users. CONCERNS.md already flags that `AgentCorePythonInterpreter` imports `boto3` unconditionally while `pyproject.toml` lists it as an optional extra, so a fresh install without the extra crashes on `import strands_code_agent`.

**Why it happens:**
Taking the harness/AWS happy path as the only path; eager imports of optional backends; defaulting config to AgentCore managers instead of file/markdown; logging session IDs or shipping local source to AgentCore without documenting what leaves the machine.

**How to avoid:**
AWS-optional-never-required as an acceptance gate per CLI phase: lazy `boto3` import with a clear "install with `agentcore` extra" error; local interpreters + file sessions + markdown memory as the zero-credential default; every AWS-backed seam (model provider, session manager, memory store, interpreter) selected via config with graceful fallback when credentials are absent; a CI job that installs without extras and runs the suite offline. Document exactly what source leaves the machine on the AgentCore path.

**Warning signs:**
`import strands_code_agent` failing in a clean venv without extras; CLI refusing to start without `AWS_*` env vars; tests skipped (not passed) offline; AgentCore session-per-interpreter races masked by single-user testing.

**Phase to address:**
Session-wiring phase (choose file-local defaults) and `/model` provider phase (Bedrock as a choice, default override-friendly); verified by an offline-install CI job added in the setup phase.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Route all file ops through `python_repl` instead of adopting harness file/shell tools | No new tool surface to build | No per-tool permission granularity (can't allow `read` while gating `write`); injection in file content executes in the same interpreter as agent code; diff/undo nearly impossible | Never — adopt `strands-agents-tools` file/edit/shell tools from the file-tools phase |
| Display-only cost with no counting plumbing | Ships `/cost` fast | Retrofitting non-bypassable budget gates later means re-plumbing the loop; one runaway incident before enforcement lands | Counting/plumbing now, hard caps later — never ship the loop without counters |
| Custom session/memory store "just for v1" | Full control | Rebuilding tested upstream defaults; divergence from harness upgrades; two sources of truth for state | Never — harness-first, gaps-only per Key Decisions |
| `ExecPythonInterpreter` as CLI default for power | Unrestricted execution "just works" | Unrestricted in-process `exec()` of model-generated code with no timeout (CONCERNS.md: `timeout_seconds` silently dropped); the core attack surface wide open | Never — sandboxed default stays; unrestricted only behind explicit opt-in + timeout |
| Broad `allow` + `--dangerously-skip-permissions`-style escape hatch | Fewer approval prompts, demo flows | Removes the only enforcement layer; one injected instruction from full compromise | Only with a surviving denylist + config-write gating; personal config, never team-shared |
| Storing everything in one session file with no reclaim | Simple persistence | Unbounded growth, slow resume, stale context poisoning new tasks | MVP only — reclaim/expiry policy by the memory-tiers phase |
| Swallowing exceptions into plain `stderr` strings | Uniform tool observations | Agent can't distinguish user errors from system failures; retries the unretryable (CONCERNS.md broad-catch) | Never — prefix `ExceptionClassName: message` from the file-tools phase |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|---------------|------------------|
| strands-harness upgrades | `uv sync` pulling new 0.1.x minors continuously | Pin verified minor, resync deliberately with full suite + message-shape regression test as gate |
| strands-agents model providers | Assuming Bedrock credentials exist; hardcoding one provider class | `/model` picker over provider string (`"provider/name"`); default override-friendly; graceful no-credential fallback |
| AgentCore (sessions/memory/interpreter) | Eager `boto3` import; one session per interpreter shared across concurrent calls; relying on `__del__` for session teardown | Lazy import with helpful error; explicit `close()`/context-manager; session-per-worker or transparent re-establish on expiry; document what source leaves the machine |
| MCP servers (`--mcp-config`) | Trusting third-party tool descriptions as system content | Verify sources, audit descriptions, sandbox third-party servers, least-privilege scoping — descriptions are untrusted input |
| GitHub loop (issues/PRs/CI) | Treating issue/PR bodies as instructions; auto-pushing without approval | Render issue content as data; branch→implement→test→open-PR with push behind approval; read CI checks before declaring done |
| Hindsight / memsearch memory backends | Exposing team/cloud memory with stale API-key scoping or no namespace isolation | Bank-per-repo keys, namespace/writable-store policy, local markdown as the default that needs no credentials |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-history re-send per turn (context accumulation) | Latency and cost per turn grow linearly over a session; 100K-token history re-billed every call | Staged context management + ingest truncation + subagent summaries for exploration | Sessions past ~1 hour or heavy test-log turns |
| `python_repl` state reset per message without session wiring | Agent re-imports, re-computes, re-reads every turn; tools slow to a crawl | Session wiring phase first; pre-warmed interpreters; document expected AgentCore round-trip latency per call | Any multi-turn coding task (i.e. immediately) |
| OKF bundle full-load on first access (`rglob` + read all + rebuild index) | First `find()`/`read()` hangs on large docs; RAM grows with corpus | Mtime-keyed cache across instances; lazy body reads; shard per service | Corpora past thousands of pages |
| O(corpus) substring search per query | Noticeable pause per knowledge query; wrong (substring) matches | Token→postings inverted index with word-boundary matching | Same threshold as above |
| AgentCore round-trip per `execute_code` + session-start on first use | Multi-second tool calls; first call mysteriously slower | Pre-warm session; batch where possible; keep local interpreters the default | Any interactive session on high-latency links |
| `/tmp` scratch dirs never cleaned (one `mkdtemp` per agent) | Disk fills on long runs / CI; stale sensitive intermediates linger | `close()`/context-manager cleanup on `CodeAgent`; platform-default tmp dir (not hardcoded `/tmp`) | Long-running services, test suites constructing many agents |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Switching CLI default to unrestricted `ExecPythonInterpreter` | Arbitrary model-generated code runs in-process with no timeout — RCE by prompt | Keep `SandboxedPythonInterpreter` default; treat local execution as untrusted-code execution (OS sandbox for hostile input); add timeout/resource limits |
| Over-broad import authorization (`extract_imports` dotted entries, `matplotlib.*` wildcards) | Sandbox allowlist noisier than intended; model imports more than policy means | Authorize top-level package names only; pin exact set with a test |
| World-readable/predictable scratch dirs with no cleanup | Sensitive intermediates (diffs, secrets in test output) leak via shared `/tmp` | `0700` + cleanup-on-close + document `tmp_dir` as sensitive |
| Secrets in `initialization_code`/toolkit strings committed to git | Credentials baked into repo and shipped to model context | Scrub env in policy phase; static secret scan in CI; keep secrets out of committed toolkit strings |
| Global `botocore` monkeypatch on package import | Process-wide side effects; double-patch on reload; version drift (`v0.4.0` hardcoded) | Idempotent opt-in registration via botocore events; version from package metadata |
| Uncapped stdout/stderr capture from executed code | Billion-laughs-style DoS via generated output; context flood as attack | Max-bytes caps on captured output with truncation pointers |
| Malformed-file crashes whole-bundle load (naive frontmatter split, uncaught YAML errors) | One crafted `.md` file DoSes knowledge loading for the entire bundle | Per-file parse isolation with path-tagged errors; size caps; line-oriented fences |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Approval prompts for everything (noisy reads, silent writes) | Prompt fatigue → user enables allow-all → no safety left | Gate writes/network/destructive ops; free-pass reads and `git diff`; `interventions="smart"` tuning |
| No anytime-steering; freeform input queued or kills the task | User watches the agent drive off a cliff with no steering wheel | Inject steering at the next tool-call boundary (per Active requirements); `Esc` to interrupt, rewind menu to roll back |
| Compact/clear as hidden lore | Users run 3-hour sessions into mush, blaming the model | Surface pressure visibly (context-size command is already required); suggest `/compact` at ~70% and `/clear` at task boundaries |
| Entangled mega-diffs from long sessions | Review impossible; rollback painful; "one ask = one PR" promise broken | Commit every 15–20 min of agent work; one task per branch; `/diff` viewer before every commit |
| Stale `CLAUDE.md`/policy (3 months old, confidently wrong) | Agent follows outdated conventions with full confidence — worse than no policy | Refresh policy weekly during active dev; `/review` command to audit agent behavior against current policy |
| Subagent work invisible | User can't tell what the side `/btw` question or helper is doing; duplicate work | Checklist + progress surfacing for subagents (harness `todos` plugin); short summaries back to main session |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Task loop:** Often missing loop-breaker + turn budget — verify same-tool-same-args repetition halts and asks
- [ ] **`/cost` display:** Often missing the counting plumbing for enforcement — verify per-session usage object exists independent of rendering
- [ ] **Session resume:** Often missing `flush()`-on-exit — verify `SIGKILL`-then-resume preserves task state, not just conversation text
- [ ] **Permissions:** Often missing the denylist-below-the-model — verify a `deny` rule blocks even when the model insists and even in allow-all mode
- [ ] **`/compact`:** Often missing policy preservation — verify safety rules survive summarization verbatim
- [ ] **GitHub loop:** Often missing push approval + CI check read — verify no push without approval and no "done" while CI is red
- [ ] **Model switching:** Often missing no-credential fallback — verify `/model` switch + cold start without `AWS_*` still yields a working local CLI
- [ ] **Upstream resync:** Often missing the regression gate — verify strands bump runs full suite + message-shape test before lock update
- [ ] **Skill loading:** Often missing provenance — verify skills only load from expected dirs and changes to skill/config files need approval

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Runaway loop / cost blowup | MEDIUM (money spent; code usually intact) | Kill session; session cost report to scope blast radius; rollback uncommitted diffs via `/undo`/snapshots; commit any good partial work; restart with tighter step budget + smaller task slice |
| Context blowup / incoherent agent | LOW | `/clear` and restart with a sharper prompt (preferred over `/compact` when assumptions are poisoned); salvage good diffs first via `/diff` |
| Destructive file/git action | HIGH (data loss possible) | Restore from pre-edit snapshots or git (`git reflog`, `/undo`); if pushed, revert PR immediately; then add the missing `deny` rule so the class can't recur |
| Prompt injection succeeded | HIGH | Treat as compromise: audit config/skills/hooks diffs for persistence, rotate exposed secrets, discard the session; add provenance gate for the vector used |
| Session corruption / lost progress | MEDIUM | Recover last good session snapshot; re-run from last committed checkpoint (commits every 15–20 min bound the loss); fix `flush()`/reclaim gap |
| Upstream churn breakage | MEDIUM | Roll lockfile back to last verified minor; run suite to confirm green; schedule deliberate resync with regression gate; thin the wrapper that broke |
| AWS coupling outage (no-creds failure) | LOW | Fall back to local interpreter + file session + local model; fix lazy import / default config; add offline CI job to prevent recurrence |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls (phase names follow the harness-first build order from `docs/competitive-gap-analysis.md`; adjust numbering when the roadmap lands).

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Runaway tool loops / cost blowup | Task-loop phase (budgets + loop-breaker with the loop); hard caps follow-up | Same-args repetition halts; session cost object exists; kill-test with spend report |
| Context-window blowup | Context/observability phase; ingest truncation in file-tools phase | Pressure thresholds fire in order; bulky outputs truncated with pointers; policy survives `/compact` |
| Destructive file/git actions | Permissions/HITL phase, before GitHub-loop phase | Deny rule blocks in allow-all mode; every edit snapshotted; push requires approval |
| Prompt injection via repo content | Permissions phase (structural) + skills phase (provenance) + GitHub phase (issues-as-data) | Planted injection treated as data in red-team test; config writes need approval |
| Session resume loss | Session-wiring phase (first) | `SIGKILL`-then-resume test green; `flush()` on shutdown path; reclaim policy exists |
| Upstream churn breakage | Setup/CI phase (gate + pin policy), enforced in every harness-touching phase | Full suite + message-shape test gate every strands bump; thin-wrapper review |
| AWS coupling | Session phase (local defaults) + `/model` phase (override-friendly); offline CI job in setup | Cold start with no `AWS_*` works; import without extras works; offline CI green |
| Untrusted-code execution default | Permissions phase (sandbox presets + timeouts) | Default interpreter is sandboxed; `ExecPythonInterpreter` unreachable without explicit opt-in |
| Mega-diff / unreviewable sessions | GitHub-loop phase (branch-per-task, `/diff`, commit cadence) | No task produces an unreviewable diff; `/undo` restores pre-task state |

## Sources

- Empirical bug study of Claude Code / Codex / Gemini CLI session & state failures (~6% of reported bugs: persistence, resumption, state reset, compaction errors, history loss) — [arxiv.org](https://arxiv.org/html/2603.20847)
- Terminal-agent scaffolding with staged context management (warn/prune/mask/compact thresholds) and session/mode/MCP command taxonomy — [arxiv.org](https://arxiv.org/html/2603.05344v1)
- Runaway-cost incidents and budget-guard patterns ($6.5K AWS bill, $47K 11-day agent ping-pong, token budgets + circuit breakers + session caps) — [nexgismo.com](https://www.nexgismo.com/blog/ai-agent-budget-guards-stop-runaway-api-costs), [supra-wall.com](https://www.supra-wall.com/learn/ai-agent-runaway-costs)
- Agent-output truncation gap across Claude Code/AutoGen/Agno/Gemini CLI (expensive work lost, no warning) — [claude-code-gauntlet research](https://github.com/liatrio-labs/claude-code-gauntlet/blob/HEAD/docs/research/artifacts/23-agent-output-truncation-and-recovery.md)
- Indirect prompt-injection mitigations are structural (sandbox controls, block config writes, egress controls, data-vs-instruction separation) — [llm-wiki](https://github.com/vietbui1999ru/llm-wiki/blob/HEAD/docs-site/concepts/indirect-prompt-injection.mdx); repo-file attack via LICENSE/README + MCP description poisoning — [cosai-oasis case study](https://github.com/cosai-oasis/ws3-ai-risk-governance/blob/HEAD/SIG-Security-AI-Assisted-Code-Development/threat-modeling/Case-Studies/Cases/Cranium-Discovers-AI-Coding-Assistant-Hijacking-Exploit.md), [prompt-injection-resistance skill](https://github.com/chloevpin/open-agent-skills/blob/HEAD/skills/prompt-injection-resistance/SKILL.md)
- Claude Code permissions model (allow/deny lists, deny overrides, dangerous-actions hooks, YOLO-mode risk) — [claude-code-ultimate-guide](https://github.com/florianbruniaux/claude-code-ultimate-guide/blob/HEAD/guide/security/enterprise-governance.md), [ClaudeLog](http://claudelog.com/mechanics/dangerous-skip-permissions/)
- Context hygiene practices (`/clear` at boundaries, `/compact` with focus, subagent summaries, short sessions + small diffs) — [openhands.dev](https://www.openhands.dev/blog/claude-code-best-practices-agentic-coding), [blink.new](https://blink.new/blog/agentic-coding-best-practices)
- Strands experimental-feature policy (no semver/back-compat between minors; pin to a specific minor) — [harness-sdk FEATURE_LIFECYCLE.md](https://github.com/strands-agents/harness-sdk/blob/HEAD/team/FEATURE_LIFECYCLE.md); non-breaking-change policy — [COMPATIBILITY.md](https://github.com/strands-agents/harness-sdk/blob/HEAD/team/COMPATIBILITY.md)
- Project context: `.planning/PROJECT.md` (experimental-stack constraints, AWS-optional, display-only budgets v1), `.planning/codebase/CONCERNS.md` (unbounded turns, no timeout/output caps, unconditional boto3 import, no CI gate, callback message-shape fragility), `docs/competitive-gap-analysis.md` (harness-first build order, interventions seam, memory tiers)

---
*Pitfalls research for: conversational coding CLI on strands-agents 1.x + strands-harness 0.1.x*
*Researched: 2026-09-23*
