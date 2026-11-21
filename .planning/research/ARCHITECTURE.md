# Architecture & Integration Seams — Strands Code v2.0

**Researched:** 2026-11-21
**Milestone:** `v2.0` (Phases 13–19)

---

## 1. Structural & CI Invariants That Constrain Every v2.0 Change

1. **`import-linter` Composition-Root Contract (`pyproject.toml:87-101`):**
   - `strands_code_cli.*` feature packages MUST NOT import `strands_code_cli.entry.main`.
   - Top-level `scripts/evals/` (like `scripts/uattest/`) CAN import `strands_code_cli.entry.main:build_agent` cleanly without violating the contract.
2. **Cyclomatic Complexity Ceiling (`gates.yml`: `xenon --max-absolute C` -> CC <= 20):**
   - Existing touchpoints already sit near the ceiling (`run_loop` = `C (18)` at `loop/core.py:2380`, `apply_model_action` = `C (19)`, `_setup_decision_entries` = `C (20)` at `dispatch/core.py:833`).
   - **Rule:** Never inline complex new branches into `run_loop` or `dispatch/core.py`. Factor new features into small, focused helper modules:
     - `strands_code_cli/dispatch/help.py` (`/help`, shared `USAGE_HINT` table)
     - `strands_code_cli/dispatch/review.py` (`/review` git collection + prompt builder)
     - `strands_code_cli/ui/attachments.py` (`@file` / `/file` gitignore lister + payload builder)
     - `strands_code_cli/memory/marketplace.py` (catalog fetch, lockfile, SHA/hash verification, safe unpack)
     - `strands_code_cli/policy/box.py` (or `entry/box_init.py`) (`box.toml` / `policy.dw` renderer)
     - `scripts/evals/` & `tests/evals/` (instead of top-level `evals/`, ensuring `ruff` + `xenon` coverage and clean Hatchling wheel builds)
3. **Pristine Upstream Agent Library (`D-24`, `pyproject.toml:76-78`):**
   - `strands_code_agent/` stays untouched except for deliberate upstream syncs; CLI changes live in `strands_code_cli/`.

---

## 2. Routing & SDK Seams (`UPSTREAM-01`, `UPSTREAM-02`)

### 2.1 Keep `apply_model_action` + `BeforeToolCallEvent.cancel_tool`
- **Why NOT `strands.models.routing.ModelRouter` (`strands/models/routing/router.py:38-45`):**
  `ModelRouter` only swaps `context.model` inside `InvokeModelStage` (leaving `agent.model` on candidate 0), requires pre-instantiating every candidate `Model` upfront, skips `convert_history()` + `RichHistory` stash/restore, and falls back to `candidates[0]` on decline instead of `D-08`'s `"hold current_model byte-identical"`.
  - **Pattern:** Keep pre-turn `apply_model_action` in `loop/core.py`; swap *only* the underlying HTTP engine transports in `routing/` onto `strands.decisions.DecisionModel` subclasses (`TypeSafeDecisionModel`, `OpenRouterDecisionModel`, `OllamaDecisionModel`, optional `LLMDecisionModel`) bridged synchronously via `asyncio.run`.
- **Why NOT replace steering with `Agent.cancel()` (`strands/agent/agent.py`):**
  `Agent.cancel()` terminates the entire `agent()` turn (`stopReason="cancelled"`). Boundary steering (`D-11`, `steering.py:238-262`) cancels *one* `BeforeToolCallEvent` with `STEERING_REDIRECT_TEMPLATE` so the **same turn redirects mid-flight**. Keep `cancel_signal=cancel_event` and `steering.py` intact; optionally call `agent.cancel(after_current_tools=True)` on user Ctrl-C from the main pump thread.

### 2.2 History & Context Accounting (`InjectedBlock` & `ContentBlock`)
- `harness-py v0.4.0` `ContextInjector` writes `{"injected": {"text": ...}}` (`InjectedBlock`) into `agent.messages`:
  - Update `estimate_messages_tokens()` (`cost/cost_context.py:445-465`) to count `"injected"`.
  - Update `canonical_prefix_hash()` (`model/model_switch.py:249-275`) so `"injected"` blocks stay deterministic across stashes/switches.
- `model.model_info.limits.context_window` (`strands-py v1.63+`) integrates at the top of `window_for()` (`cost/cost_context.py:122`) before static `MODEL_LIMITS`.

---

## 3. Google Gemini & Box Credential Coordination (`MODEL-06`, `SANDBOX-01`)

### 3.1 Coordinated `first_run.py` + `entry/main.py` Startup Flow
Currently `entry/main.py:234-235` runs `_preflight_credentials()` (hardcoded `boto3.client("sts").get_caller_identity()`) **before** `ProviderConfig.load()`. Under both non-AWS setups (Google AI Studio key, Vertex ADC, OpenRouter) *and* Strands Box (`STRANDS_BOX=1`, where `sts.amazonaws.com` is blocked by default egress policy and API keys are `strands_box_...` phantom strings), this exits `2` before launch.

**Unified v2 Startup Order:**
1. Parse & validate CLI flags (`--session-id`, `--codeact`).
2. `config = ProviderConfig.load()` (read configured `model`, e.g. `google/gemini-2.5-pro`, `litellm/openrouter/...`, `bedrock/...`).
3. Run provider-aware `preflight_credentials(config)`:
   - Resolve effective target provider (`config.model` or ambient env when `config.model is None`).
   - Accept any configured provider with **non-empty credential env presence** (`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ollama/`). **Never inspect key-format prefixes** (must accept `strands_box_<random>` phantoms).
   - For Bedrock: if `STRANDS_BOX == "1"` (or `AWS_CA_BUNDLE` + `HTTPS_PROXY` + synthetic `boto3.Session().get_credentials()` / `AWS_BEARER_TOKEN_BEDROCK`), verify local credential presence **without** calling `sts.get_caller_identity()`. Otherwise keep the STS probe.

### 3.2 `GeminiModel` Cross-Provider History Seam (`model_switch.py`)
- Add `"google"` to `supports_reasoning()` (`model/model_switch.py:160`) to delegate to `_harness_supports_thinking`.
- Strip `toolUse["reasoningSignature"]` inside `convert_history()` (`L338`) whenever `not (supports_reasoning(new_id) and same_vendor(old_id, new_id))` (while keeping `toolUse["reasoningSignature"]` intact inside `RichHistory` stashes and ignoring it inside `canonical_prefix_hash`).
- Fix `_vendor_family()` (`L563-582`) so `"gemini-2.5-pro"` is not split on `"."` before checking `/` or vendor conventions.

---

## 4. Skills Marketplaces Seam (`SKILL-03`)

Because `strands.vended_plugins.skills.Skill` enforces `^[a-z0-9-]+$` (no `:`) and `skill_dir.name == skill.name`, while `AgentSkills._load_skill_paths` scans one subdirectory level per root:
- **`./.agent/skills/<skill>/SKILL.md`** remains exclusively `local:<skill>`.
- **`./.agent/skills-marketplaces/<marketplace>/<skill>/SKILL.md`** houses marketplace skills (preserving `skill_dir.name == skill.name`).
- **`./.agent/skills-lock.json`** records `source`, `repo_url`, `subdir`, `ref`, 40-char `commit_sha`, SHA-256 `computed_hash`, `has_scripts`, `installed_at`.
- **`~/.config/strands-code/marketplaces.yaml` (`0o700`)** + **`~/.cache/strands-code/marketplaces/<name>.json`** track registered marketplace catalogs.
- `AgentSkills` receives `[*marketplace_dirs, DEFAULT_SKILLS_DIR]` so `local:` wins ties in `AgentSkills.skills`, while `SlashCompleter.get_completions` (`ui/completer.py:42-60`) dynamically derives valid `<namespace>:` prefixes from `SkillIndex`.
- Every mutating `/skills` verb calls `_skills_reload` (`set_available_skills` on `agent._skills_plugin` first, then `SkillIndex.reload()`).

---

## 5. Strands Box Host-Containment Architecture (`SANDBOX-01`)

```text
Host Process (box — Rust, holds real keys + Dogwood Policy Engine + Audit Log)
  ├── Egress Proxy & SigV4 / Header Injector (AWS, x-goog-api-key, x-api-key, OpenRouter, TypeSafe)
  ├── Strands Shell & Dogwood policy.dw evaluator (MFOTL temporal history)
  └── Containerized Child Namespace (strands-box-contain-trampoline: USER/MNT/PID/NET + seccomp-bpf)
        └── strands-code (.venv/bin/strands-code)
              ├── Env: empty except [agent].env (TERM, HOME, PATH) + phantom tokens + HTTPS_PROXY/CA
              ├── tool: read/write/edit -> OS mount-namespace confined ([agent.filesystem])
              ├── tool: shell -> PATH sh alias (strands-box-sock-alias) -> Dogwood policy.dw
              └── CodeAct: python_repl + codeact_shell (routes via sh -c when STRANDS_BOX=1) -> Kernel + Dogwood
```

- Protect `.agent/box/box.toml` and `.agent/box/policy.dw` outside `[agent.filesystem].write` (or store under `~/.config/strands-box/<repo-id>/`) so an in-session write cannot alter next-launch containment.

---

## 6. Interactive UX Seams (`LOOP-06`, `TOOL-05`, `REVIEW-01`)

- **`/help` (`dispatch/help.py`):** Single command registry backing both `/help` and `USAGE_HINT`; appends live `skills.list_entries()` + shadow notes via `print_plain`.
- **`@file` / `/file` (`ui/attachments.py`):**
  - `PromptSession` uses `DynamicCompleter(lambda: merge_completers([FuzzyCompleter(SlashCompleter), FuzzyCompleter(AtFileCompleter)]))`.
  - Payload assembly runs in `loop/core.py` *after* `_route_pre_turn` chooses `current_model` (so `supports_media(current_model)` gates binary `ImageContent`/`DocumentContent` blocks accurately, keeping `ask_text: str` for router & auto-title).
  - Extend `model_switch.py` (`convert_history`, `_media_placeholder_block`, `_MEDIA_PLACEHOLDER_RE`, `canonical_prefix_hash`) to cover `"document"` alongside `"image"`/`"video"`.
- **`/review` (`dispatch/review.py`):**
  - Collects `git diff` / `git status` in Python (since Plan mode denies `shell`), wraps diff in an untrusted-content marker + `REVIEW_PREFIX`, and triggers a turn-scoped read-only Plan gate (`set_gate_mode("plan")`, `turn_interface = "tool"`) restored in `run_loop`'s `finally:` without touching sticky `ModeState` or calling `mode.note_plan_proposed()`.
