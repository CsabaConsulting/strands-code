# Technology Stack — Strands Code v2.0

**Researched:** 2026-11-21
**Milestone:** `v2.0` (Phases 13–19)
**Constraint:** Pure Python (`>=3.10`), `uv` toolchain, zero TypeScript runtime dependencies, AWS-optional (`agentcore` and `gemini` extras remain opt-in).

---

## 1. Core Platform Upgrades (`strands-py >=1.65` & `harness-py >=0.4`)

| Package | v1.0 Lock | v2.0 Target | New Primitives & Key Changes |
| :--- | :---: | :---: | :--- |
| **`strands-agents`** (`strands-py`) | `1.58.1` | `>=1.65.0` | `strands.decisions` (`DecisionModel`, `LLMDecisionModel`, `TypeSafeDecisionModel`, `DecisionsAPIDecisionModel`, `SageMakerDecisionModel`), `strands.models.routing.ClassifierStrategy`, `Model.model_info` (`ModelLimits.context_window`), `Agent.cancel(*, message=None, after_current_tools=False)`, `BedrockModel._rejects_reasoning_block` (`#5166`), `OpenAIModel` `ContextInjector` tool-result adjacency (`#5158`), `ContextInjector` persisting `InjectedBlock` (`{"injected": {"text": ...}}`), `strands-agents-tools` formally deprecated (`v1.64+`). |
| **`strands-harness`** (`harness-py`) | `0.1.2` | `>=0.4.0` | Per-model `_GOOGLE_LEVELS = ("minimal", "low", "medium", "high")`, `"google"` registered in `_PROVIDERS` with `supports_thinking("google/...") == True` (`v0.3.3+`), `_WEB_FETCH_MODELS["google"] = "gemini-3.5-flash"`, Nova 2 `reasoningConfig` + regional Bedrock `web_fetch` maps (`#4853`), Haiku 5.5 adaptive thinking & 128k output (`#5159`), compaction preserving `messages[0]` (`#5121`), subagent `content_filtered`/`refusal` error propagation (`#5165`), removal of default `"todos"` built-in plugin (`v0.4.0`). |

---

## 2. Google AI Gemini Provider (`MODEL-06`, Phase 14)

- **Optional extra (`pyproject.toml`):** `gemini = ["strands-agents[gemini]"]` (pulls `google-genai` lazily only when installed; `_SDK_EXTRA_HINTS["google"] = "gemini"` in `strands_code_cli/dispatch/core.py`).
- **Model class:** `strands.models.gemini.GeminiModel` (instantiated by `strands_harness.models._gemini(model_id, effort, web_search, caching)`).
- **Supported authentication modes:**
  1. **Google AI Studio API Key (including Personal Google AI Ultra credits):** `GOOGLE_API_KEY` or `GEMINI_API_KEY` (`google.genai.Client()` reads both; `GOOGLE_API_KEY` takes precedence). Personal **Google AI Pro** (\$10/mo), **Google AI Ultra 5x** (\$40/mo), and **Google AI Ultra 20x** (\$100/mo) plans include monthly **Google Developer Program** promotional credits claimable inside `aistudio.google.com` (one-time \$5 prepaid Cloud Billing activation required so keys leave Free Tier quotas; monthly grants spend first and accumulate for 12 months).
  2. **Vertex AI ADC (optional keyless GCP OAuth):** `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` (e.g. `global`) backed by `gcloud auth application-default login`.

---

## 3. Decision Routing Stack (`UPSTREAM-02`, Phase 15)

- **Upstream classes (`strands.decisions`):**
  - `DecisionModel` (ABC with `async def ask(state, questions, *, invocation_context=None, **kwargs) -> DecisionResult` and `@abstractmethod async def _ask(...)`)
  - `TypeSafeDecisionModel` (`TYPESAFE_API_KEY`, `https://api.typesafe.ai/v1/systemone`)
  - `DecisionsAPIDecisionModel` (`JEV_API_KEY`, `https://decisionapi.net/v1/systemone`)
  - `LLMDecisionModel` (optional LLM fallback engine over any `strands.models.Model`)
- **CLI-retained custom subclasses/wrappers:**
  - Custom `OpenRouterDecisionModel(DecisionModel)` (`OPENROUTER_API_KEY`, `https://openrouter.ai/api/alpha/decisions`, `64 KiB` body cap vs. upstream adapter's `32 KiB` cap, capturing inline `usage.cost` USD actuals).
  - Custom `OllamaDecisionModel(DecisionModel)` (`GET /api/version >= 0.35`, `0.35.1` for `clef*`, loopback-safe auth, `"keep_alive": "5m"` on `POST /v1/systemone`).
  - Pre-turn `apply_model_action` (with `convert_history()`, `RichHistory` stash/restore, `0.62` top-1 probability threshold, `0.04` tie-margin gate, two-call model + effort flow) rather than `ModelRouter` / `ClassifierStrategy` per-invocation switching.

---

## 4. Skills Marketplaces & Lockfile (`SKILL-03`, Phase 16)

- **No new runtime dependencies:** Uses Python stdlib (`urllib.request`, `tarfile`, `hashlib`, `json`, `pathlib`, `re`, `os`) + existing `pyyaml`, plus `strands.vended_plugins.skills` (`AgentSkills`, `Skill.from_directory`, `Skill.from_file(..., strict=True)`).
- **Manifest compatibility:** `.agent-plugin/marketplace.json` and `.claude-plugin/marketplace.json` (catalog monorepo format) plus direct GitHub `owner/repo[@ref]` auto-discovery (`skills.sh` convention).
- **Storage layout:**
  - User catalog registry: `~/.config/strands-code/marketplaces.yaml` (`0o700`, symlink-refused) + `~/.cache/strands-code/marketplaces/<name>.json`.
  - Project-local local skills (unchanged): `./.agent/skills/<skill>/SKILL.md` (`local:<skill>`).
  - Project-local marketplace skills: `./.agent/skills-marketplaces/<marketplace>/<skill>/SKILL.md` (satisfies `Skill` `skill_dir.name == skill.name` invariant without colons).
  - Project lockfile: `./.agent/skills-lock.json` (immutable 40-char `commit_sha` + SHA-256 `computed_hash` + `has_scripts`).

---

## 5. Strands Box OS Containment (`SANDBOX-01`, Phase 17)

- **External native Rust binaries (`strands-agents/box`, `v0.2.3+`) — zero Rust build or PyPI package in `strands-code`:**
  - Three co-located Linux executables installed via official `download.sh` or Cargo release build:
    1. `box` (host controller, embedded **Dogwood Local Engine**, TLS/SigV4 egress proxy, Strands Shell/Monty runtime, MCP broker)
    2. `strands-box-contain-trampoline` (`CLONE_NEWUSER`, `CLONE_NEWNS`, `CLONE_NEWPID`, `CLONE_NEWIPC`, `CLONE_NEWUTS`, `CLONE_NEWNET`, `PR_SET_NO_NEW_PRIVS`, `seccomp-bpf`)
    3. `strands-box-sock-alias` (UNIX socket bridge + `PATH` `sh`/`bash`/`zsh` proxies)
  - Optional companion: `dogwood-cli` (`dogwood validate`, `dogwood format`, `dogwood lower`, `dogwood replay`).
  - Linux `x86_64` gate: requires `EXPERIMENTAL_X86_SUPPORT=TRUE` (`aarch64` is GA).
  - No `bwrap` or Landlock required; Ubuntu 24.04+ requires `/etc/apparmor.d/strands-box` `userns` profile (or `kernel.apparmor_restrict_unprivileged_userns=0` in ephemeral dev/CI).

---

## 6. CLI Ergonomics (`LOOP-06`, `TOOL-05`, `REVIEW-01`, Phase 18)

- **No new dependencies:** Built on existing `prompt_toolkit` (`FuzzyCompleter`, `merge_completers`, `DynamicCompleter`, `PromptSession`), `ripgrep` (`rg --files` with stdlib walk fallback), `git` (`git diff`, `git rev-parse`), `policy.scope.confine`, and SDK `ContentBlock` (`ImageContent`, `DocumentContent`).

---

## 7. Automated Evals & Red-Teaming (`EVAL-01`, Phase 19)

- **Dev dependency (`pyproject.toml [dependency-groups] dev`):** `strands-agents-evals>=1.10.0` (import package: **`strands_evals`**; CLI: **`strands-evals`**).
- **OTel stack already present in lockfile:** `opentelemetry-api==1.44.0`, `opentelemetry-sdk==1.44.0` wrapped by `strands_evals.telemetry.StrandsEvalsTelemetry` + `StrandsInMemorySessionMapper`.
- **CI integration:** Kept strictly under `scripts/evals/` and `tests/evals/` so existing `.github/workflows/gates.yml` checks (`pytest`, `ruff`, `xenon --max-absolute C`, `import-linter`) enforce the eval suite automatically without `boto3` or live network creds in default CI (`@pytest.mark.integration` gates live judge/red-team tests).
