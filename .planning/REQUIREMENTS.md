# Requirements: Strands Code

**Defined:** 2026-11-21
**Milestone:** `v2.0` (Ecosystem Alignment, Marketplaces, Sandbox & Evals)
**Core Value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

---

## v2.0 Requirements

### Upstream & Routing

- [x] **UPSTREAM-01**: Resync `uv.lock` onto `strands-agents >=1.65` and `strands-harness >=0.4`, adapt `estimate_messages_tokens` and `canonical_prefix_hash` for `ContextInjector` `InjectedBlock`, consume `Model.model_info.limits.context_window`, close the Phase 4 restore-reasoning blocker (`#5166` / `drop_block`), preemptively configure `streaming=False` for `_NO_STREAMING_TOOLS` (Bedrock Llama 3/4), and audit `todos` plugin removal while preserving `steering.py` boundary steering
- [ ] **UPSTREAM-02**: Migrate `strands_code_cli/routing/` engine transports onto `strands.decisions.DecisionModel` (`TypeSafeDecisionModel`, `OpenRouterDecisionModel` keeping 64 KiB body caps & inline USD `cost`, `OllamaDecisionModel`, and optional `LLMDecisionModel`), keeping `uncertainty=False` raw probability reading, `0.62`/`0.04` gate, two-call model + effort routing, `apply_model_action`, `/route` UX, and `/cost` actuals

### Models & Auth

- [ ] **MODEL-06**: First-class `google/` Gemini provider support (`gemini` optional extra + `_SDK_EXTRA_HINTS`), Box-compatible provider-aware startup preflight replacing the unconditional `Bedrock-or-stop` STS gate, `google/` reasoning support via `_harness_supports_thinking`, cross-vendor `toolUse["reasoningSignature"]` stripping in `convert_history()`, `_vendor_family()` dot-split fix, `litellm_entry` `gemini/` lookup + Gemini discovery/cost tables, and Google AI Studio + Google AI Ultra (\$40–\$100/mo Developer Program credit) setup docs

### Skills & Extensibility

- [ ] **SKILL-03**: Remote skills marketplace management and lockfile installer (`/skills marketplace add|list|update|remove`, `/skills browse|install|update|sync|remove`), supporting `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, and direct GitHub `owner/repo[@ref]` sources into `./.agent/skills-marketplaces/<ns>/<skill>/` with `./.agent/skills-lock.json` 40-char `commit_sha` + SHA-256 `computed_hash` pinning, dynamic `/<ns>:` tab completion, and deny-first symlink/zip-slip/protected-path/`allowed-tools` safeguards

### Sandbox & Policy

- [ ] **SANDBOX-01**: First-class Strands Box (`strands-agents/box` `v0.2.3+`) Linux wrapper workflow (`box.toml` + deterministic Dogwood `policy.dw` generator and 5-provider egress profiles with `x-goog-api-key` / `x-api-key` / OpenRouter path-scoping), protected outside `[agent.filesystem].write`, at least one canonical MFOTL temporal rule (with formal `v2.0` scoped revisit of `D-05`), `STRANDS_BOX=1` `codeact_shell` `sh -c` alignment, and Linux `x86_64` + Ubuntu 24.04 AppArmor setup docs

### Interaction & Review

- [ ] **LOOP-06**: Explicit `/help` command (`dispatch/help.py`) registered in `BUILTIN_SLASH_HEADS` sharing a single declarative command table with `USAGE_HINT` and listing loaded skills + shadow warnings via `print_plain`
- [ ] **TOOL-05**: `@file` inline fuzzy attachment picker and `/file` TTY picker (`ui/attachments.py`) confined to gitignore-aware `effective_roots`, only resolving real existing files (never `@dataclass` / `@pytest.mark` code tokens), attaching images and binary docs (`ImageContent`/`DocumentContent`) when `supports_media(current_model)` holds post-routing via strictly allowlisted content-block construction (`text`/`image`/`document` only, never caller-supplied `"toolUse"` blocks; CVE-2026-18830 guard), and extending `model_switch.py` to convert `"document"` blocks across switches
- [ ] **REVIEW-01**: Read-only `/review` command (`dispatch/review.py`) pre-collecting uncommitted (`git diff HEAD`), `--staged`, or `<base-ref>` diffs in Python inside an untrusted-diff boundary and running under a turn-scoped read-only Plan gate (`turn_interface = "tool"`) without mutating sticky `ModeState`

### Evaluation & Red-Teaming

- [ ] **EVAL-01**: Automated evaluation and red-team suite on `strands-agents-evals >=1.10` (`[dependency-groups] dev`) split cleanly under `scripts/evals/` and `tests/evals/` (passing `ruff`, `xenon --max-absolute C`, `import-linter`), running offline deterministic/mocked `TrajectoryEvaluator` + OTel span invariant and prompt-injection canary tests in default CI alongside `@pytest.mark.integration` live `ActorSimulator` + `RedTeamExperiment` (Crescendo/GOAT/PAIR) runs

---

## Future Requirements (`v2.1+`)

- **SKILL-04**: CLI consumes MCP servers as tools via user config (`create_harness(mcp_servers=...)`)
- **LOOP-05**: Non-interactive headless / JSON output mode for scripts and CI (any JSON/headless input loader must explicitly strip or reject caller-supplied `"toolUse"` blocks; CVE-2026-18830 / CoreBreak boundary)
- **TOOL-06**: Export trimmed session content to text file via `/copy`
- **MODE-03**: Fast/thorough effort presets layered over Plan/Act
- **REVIEW-02**: Headless / CI review runner modes

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Persistent semantic code index | Separate multi-phase project; grep-first suffices |
| Enforced token budgets | Display builds trust; halting mid-task is a separate policy decision |
| Consumer OAuth piggybacking on Gemini CLI / Code Assist | Violates Google ToS; personal Google AI Pro/Ultra plans already provide \$10–\$100/mo Developer Program credits usable via a standard AI Studio API key |
| Replacing `apply_model_action` with `strands.models.routing.ModelRouter` | `ModelRouter` pre-instantiates all candidate models, skips `convert_history()` + `RichHistory` stashes, and falls back to candidate 0 instead of holding current model |
| Replacing `BeforeToolCallEvent.cancel_tool` with `Agent.cancel()` | `Agent.cancel()` terminates the entire turn rather than redirecting at the next tool boundary |
| Honoring remote skill `allowed-tools` as permission grants | Remote `SKILL.md` frontmatter cannot bypass deny-first `PolicyClassifier` or diff gates |
| TypeScript runtime dependency (`@strands-agents/cli`) | `strands-code` remains 100% Python on `harness-py` + `strands-py` |
| Heavy external recall backends (Hindsight / OpenViking) | Rejected in `v1.0` Phase 12; Strands native markdown memory stays the backend |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UPSTREAM-01 | Phase 13 | Complete |
| MODEL-06 | Phase 14 | Pending |
| UPSTREAM-02 | Phase 15 | Pending |
| SKILL-03 | Phase 16 | Pending |
| SANDBOX-01 | Phase 17 | Pending |
| LOOP-06 | Phase 18 | Pending |
| TOOL-05 | Phase 18 | Pending |
| REVIEW-01 | Phase 18 | Pending |
| EVAL-01 | Phase 19 | Pending |

**Coverage:**
- `v2.0` requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0 ✓

---
*Requirements defined: 2026-11-21 (Milestone v2.0)*
