# Feature Specifications — Strands Code v2.0

**Researched:** 2026-11-21
**Milestone:** `v2.0` (Phases 13–19)
**Scope:** Nine milestone requirements across seven phases (`UPSTREAM-01`, `MODEL-06`, `UPSTREAM-02`, `SKILL-03`, `SANDBOX-01`, `LOOP-06`, `TOOL-05`, `REVIEW-01`, `EVAL-01`).

---

## 1. Upstream SDK & Harness Resync (`UPSTREAM-01` — Phase 13)

- Upgrade `uv.lock` to `strands-agents >=1.65` and `strands-harness >=0.4.0`.
- Retire/verify upstream-fixed workarounds:
  - Cross-family `reasoningContent` restoration (`#5166` `BedrockModel._rejects_reasoning_block` + `v1.62.0` `drop_block`), resolving the Phase 4 `STATE.md` restore blocker while keeping `convert_history()` on explicit `/model` swaps to preserve readable `[Thinking trace]` text.
  - `ContextInjector` (`InjectedBlock`) support in `estimate_messages_tokens` (`cost_context.py`) and `canonical_prefix_hash` (`model_switch.py`), leveraging `#5158` OpenAI/LiteLLM tool-result adjacency.
  - Consume `Model.model_info.limits.context_window` before static `MODEL_LIMITS` fallback in `window_for()` / `estimate_fit()`.
  - Unlock Nova 2 `reasoningConfig` (`#4853`) and Claude Haiku 5.5 adaptive thinking (`#5159`).
  - Preemptively set `streaming=False` on `BedrockModel` for `_NO_STREAMING_TOOLS` (Llama 3/4) following upstream closure of `#4857`/`#4937` so Llama 3/4 works with tools out of the box.
  - Reconcile `harness-py v0.4.0` dropping `"todos"` from default built-in plugins.

---

## 2. First-Class Google Gemini & Provider-Aware Startup (`MODEL-06` — Phase 14)

- **Provider-aware credential preflight (`first_run.py`, `main.py`):**
  - Load `ProviderConfig` *before* checking credentials.
  - Check ambient/configured non-AWS providers (`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ollama/`).
  - Verify **non-empty presence only** (never vendor key prefixes, preserving compatibility with Strands Box `strands_box_...` phantom tokens) and skip live `sts.get_caller_identity()` when `STRANDS_BOX=1`.
- **Native `google/` model support:**
  - `gemini` optional extra (`strands-agents[gemini]`) + `_SDK_EXTRA_HINTS["google"] = "gemini"`.
  - Enable `"google"` in `supports_reasoning()` (delegating to `_harness_supports_thinking` / `_GOOGLE_LEVELS`).
  - Strip `toolUse["reasoningSignature"]` on cross-vendor `convert_history()` switches (preventing `LiteLLMModel` `tool_calls[].id` corruption) while keeping it in `RichHistory`.
  - Fix `_vendor_family()` dot-split bug on `google/gemini-2.5-pro`.
  - Fix `live_pricing.litellm_entry()` to check `gemini/<tail>` and `<tail>`, add curated Gemini context/pricing fallback, and add `/model` Gemini discovery via `genai.Client().models.list()`.
  - Document the compliant **Google AI Studio API Key + Google AI Ultra (\$40–\$100/mo Developer Program credits)** one-time claim setup in `docs/QUICKSTART.md`.

---

## 3. Decision Routing Convergence (`UPSTREAM-02` — Phase 15)

- Refactor `strands_code_cli/routing/` engine transports onto `strands.decisions.DecisionModel`:
  - Wrap `TypeSafeDecisionModel` for TypeSafe Jev.
  - Implement `OpenRouterDecisionModel(DecisionModel)` (keeping `64 KiB` body cap + inline `usage.cost` capture).
  - Implement `OllamaDecisionModel(DecisionModel)` (keeping `GET /api/version >= 0.35`, `0.35.1` for `clef*`, loopback-safe auth, `"keep_alive": "5m"`).
  - Support optional `LLMDecisionModel` fallback when desired.
- Preserve all tested CLI routing guarantees:
  - `asyncio.run` bridge inside pre-turn `_route_pre_turn` and `_route_side_spawn`.
  - `uncertainty=False` with `result.metadata.probabilities` read directly so `0.62` confidence threshold and `0.04` tie-margin gate enforce identically to v1.0 baseline (or recalibrate if prompt shape changes).
  - Pre-turn `apply_model_action` in `loop/core.py` (do **not** swap for `ModelRouter`), preserving two-call model + effort routing, hold-on-failure (`D-08`), `RoutingState.pause()`, `/route` commands, and `/cost` reporting.

---

## 4. Skills Marketplaces & Lockfile Installer (`SKILL-03` — Phase 16)

- **Slash surface (`/skills`):**
  - `/skills marketplace add <owner/repo | https-url | local-path> [--name <alias>] [--ref <tag|sha>]`
  - `/skills marketplace list | update [<name>] | remove <name>`
  - `/skills browse [<marketplace>]`
  - `/skills install <marketplace>:<skill> | <owner/repo[@ref]> [--skill <name>]` (accepting `<skill>@<marketplace>` alias)
  - `/skills update [<name|ns:name>]` (displays `old_sha -> new_sha` and any added/changed `scripts/*` warnings)
  - `/skills sync` (restores pinned `commit_sha` entries from `./.agent/skills-lock.json` and verifies `computed_hash`)
  - `/skills remove <name|ns:name>` (alias `uninstall`) + lockfile eviction + atomic `_skills_reload()`.
- **Storage & UX contracts:**
  - Home catalog registry (`~/.config/strands-code/marketplaces.yaml`, `0o700`) + cache (`~/.cache/strands-code/marketplaces/<name>.json`).
  - Project installs in `./.agent/skills-marketplaces/<marketplace>/<skill>/SKILL.md` + `./.agent/skills-lock.json` (`local:<skill>` wins bare-name collisions; `BUILTIN_SLASH_HEADS` always win slash collisions; dynamic `/<marketplace>:` completion in `SlashCompleter`).
  - Deny-first safety: reject all symlinks/submodules/zip-slip, cap unpacked files/bytes, keep `allowed-tools` informational-only, warn on `scripts/*`, protect `.agent/skills*` from broad repo `[[allow]]` globs, and frame third-party provenance explicitly (`@ <short_sha>`).

---

## 5. Strands Box Linux Sandbox Floor & Dogwood Policy (`SANDBOX-01` — Phase 17)

- Wrapper-first CLI support (`strands-code box init` helper / generator + vetted templates) emitting repo-scoped `box.toml` and `policy.dw`:
  - Resolves realpaths for `.venv`, `uv`-managed Python interpreters, workspace RW roots, `~/.config/strands-code`, `~/.cache/strands-code`, `/tmp`, and passes `TERM` / `PATH` / `HOME` / `STRANDS_BOX=1`.
  - Ships 5 vetted egress profiles: Bedrock SigV4 (`aws://` without opening `sts.amazonaws.com`), Google Gemini (`header = "x-goog-api-key"`), Anthropic (`header = "x-api-key"`), path-scoped OpenRouter (`inject = "always"` or `/api/v1/chat/*` + `/api/alpha/decisions` so unauthenticated `/api/v1/models` works), and TypeSafe.
  - Ships deterministic Dogwood `policy.dw` rules including default-deny egress, `.env` read forbids, and a canonical MFOTL temporal rule (`when temporal { formerly within ... }`, e.g. `git push` requiring recent passing tests), logging a formal v2.0 scoped revisit of v1 decision `D-05`.
  - Protects `box.toml` / `policy.dw` outside `[agent.filesystem].write` so the agent cannot weaken its own next-launch sandbox.
  - Routes `codeact_shell` (`strands_code_cli/policy/codeact.py`) through `["sh", "-c", shlex.join(argv)]` when `STRANDS_BOX=1` so CodeAct commands flow through `strands-box-sock-alias` and Dogwood temporal history.
  - Documents Linux `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE` and Ubuntu 24.04+ `/etc/apparmor.d/strands-box` setup in `docs/QUICKSTART.md`.

---

## 6. CLI Ergonomics (`LOOP-06`, `TOOL-05`, `REVIEW-01` — Phase 18)

- **`LOOP-06` (`/help`):** Registered in `BUILTIN_SLASH_HEADS` (`dispatch/help.py`); declarative command table shared with `USAGE_HINT`; supports `/help` (grouped commands + dynamic Loaded Skills list with shadow warnings) and `/help <cmd>`, rendered via `print_plain` (zero Rich markup tags).
- **`TOOL-05` (`@file` & `/file` attachment picker):** Gitignore-filtered fuzzy picker (`ui/attachments.py`, `rg --files` + stdlib fallback) confined to `effective_roots(cwd, policy)`; `@file` triggers `FuzzyCompleter(AtFileCompleter)` inline via `merge_completers`; bare `/file` opens TTY picker. Source/text files inline safely; images (`png`/`jpeg`/`gif`/`webp`) & docs (`pdf`/`doc`/`docx`/`xls`/`xlsx`) attach as native `ContentBlock`s gated by `supports_media(current_model)` *after* `/route` runs, with `model_switch.py` extended to convert `"document"` blocks on model switches.
- **`REVIEW-01` (`/review`):** Registered in `BUILTIN_SLASH_HEADS` (`dispatch/review.py`); supports `/review` (uncommitted `git diff HEAD`), `/review --staged`, and `/review <base-ref>` (flag-injection safe); pre-collects `git diff` in Python (since Plan mode denies `shell`); invokes one-shot turn-scoped read-only Plan gating (`set_gate_mode("plan")`, `turn_interface = "tool"`) without mutating sticky `ModeState` or recording `note_plan_proposed()`, using an untrusted-diff `REVIEW_PREFIX` with `path:line` citation prompt.

---

## 7. Strands Evals & Red-Team Suite (`EVAL-01` — Phase 19)

- Dev dependency `strands-agents-evals >=1.10.0` (`[dependency-groups] dev` only) organized under `scripts/evals/` + `tests/evals/` so `gates.yml` (`ruff`, `xenon --max-absolute C`, `import-linter`) covers all eval code automatically.
- **Offline CI tier (`uv run pytest tests/ -q`):**
  - Deterministic `Evaluator` invariants over `StrandsInMemorySessionMapper` trajectories: Plan-mode read-only enforcement, `/review` tool-mode enforcement, `/route` fallback hold behavior, and prompt-injection canary tests against poisoned `SKILL.md`, `STRANDS.md`, and `.agent/MEMORY.md` fixtures using scripted fake models.
  - Mocked judge `Model` covering `Experiment.run_evaluations` and JSON suite schema validation (`Experiment.from_file`).
- **Live-gated tier (`@pytest.mark.integration` + CLI driver):**
  - `TrajectoryEvaluator`, `ToolParameterAccuracyEvaluator`, and `ActorSimulator` multi-turn Plan→Approve→Act + CodeAct checks supporting Bedrock, Google, and OpenRouter judge models (`--model`).
  - `RedTeamExperiment` using `CrescendoStrategy`, `GoatStrategy`, and `PairStrategy` with `AttackSuccessEvaluator` targeting skill/memory prompt injection, data exfiltration, and privilege escalation.
