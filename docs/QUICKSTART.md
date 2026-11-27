# Quickstart: running strands-code

First-time setup (once, from this repo):

```bash
uv sync
```

This creates the project-local `.venv` with an editable install, including the
`strands-code` console script. Nothing is installed globally.

## Run it

From this repo:

```bash
uv run strands-code
```

From any other directory (sessions stay local to that directory):

```bash
uv run --project /home/csaba/repos/AWS/strands-code strands-code
```

or directly:

```bash
/home/csaba/repos/AWS/strands-code/.venv/bin/strands-code
```

## Sessions

- Sessions live in `./.agent/sessions` **relative to your working directory** —
  each project directory gets its own session store. `cd` into the repo you
  want to work on, then launch.
- Resume with `strands-code --session-id <uuid>`, or pick from the
  resume picker at launch (`/resume` works too, inside the REPL).
- Delete with the picker's `Delete a session…` row (nested confirm), or
  `/forget <id-or-prefix>` inside the REPL. Either way removes the
  snapshots, the thinking-stash sidecar, and the index entry; the active
  session is always refused.

## First run

Startup preflight is provider-aware:

- If you pass `--model <provider/model>` (for example `strands-code --model google/gemini-3.8-flash`)
  or already saved a model via `/model`, preflight checks only that provider's
  credentials and skips AWS STS. `--model` is strictly session-scoped and never
  writes `config.yaml`.
- Without `--model` or a saved model, preflight auto-picks from your environment
  (`GOOGLE_API_KEY` / `GEMINI_API_KEY` or Vertex ADC -> `google/gemini-3.8-flash`,
  `ANTHROPIC_API_KEY` -> `anthropic/claude-sonnet-5-5`,
  `OPENAI_API_KEY` -> `openai/gpt-6.2-sol`,
  `MODEL_API_KEY` / `META_API_KEY` -> `meta/muse-spark-1.3-contributor`, or exits 2
  with a `--model litellm/openrouter/...` pointer when `OPENROUTER_API_KEY` is
  set alone), before falling back to Amazon Bedrock
  (`AWS_BEARER_TOKEN_BEDROCK` or the ambient boto3 chain via `sts:GetCallerIdentity`).
- `STRANDS_BOX=1` skips AWS STS and checks non-empty env presence only so Strands
  Box sessions pass without static prefix checks. Without credentials for the
  target provider, the CLI stops with a setup pointer (exit 2) before touching
  session directories.

## Optional providers

Base install covers Bedrock and direct-provider ids. Opt-in extras:

```bash
uv sync --extra agentcore   # Bedrock model discovery + AgentCore sandbox (boto3)
uv sync --extra litellm     # OpenRouter / exotic providers via litellm/ ids
uv sync --extra gemini      # Google Gemini (strands-agents[gemini] / google-genai)
uv sync --extra openai      # Native OpenAI Responses API (strands-agents[openai], openai>=2.0.0)
uv sync --extra anthropic   # Native Anthropic Messages API (strands-agents[anthropic], anthropic)
uv sync --extra meta        # Meta Model API (api.meta.ai / Muse via OpenAIResponsesModel)
```

### OpenAI (zero AWS required)

Install the `openai` extra once (`openai>=2.0.0` is required by the native
`OpenAIResponsesModel`), then export your OpenAI API key:

```bash
export OPENAI_API_KEY="<your-openai-key>"
strands-code --model openai/gpt-6.2-sol   # or omit --model to auto-pick from env
```

- **Standard env vars honored automatically by the OpenAI SDK:**
  `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, and `OPENAI_PROJECT`
  (keys are never written to `config.yaml`).
- **Custom endpoints (`base_url` + optional `api_mode: chat`):**
  Point `~/.config/strands-code/config.yaml` at an OpenAI-compatible gateway:

  ```yaml
  model: openai/gpt-6.2-sol
  base_url: https://your-proxy.example/v1
  # Optional: api_mode: chat   # default "responses" preserves effort, CacheConfig & web_search
  ```

  Default `responses` mode passes `openai/<model>` through `create_harness` so
  Harness features (`effort`, prompt caching, native `web_search`, and `web_fetch`)
  remain active and `base_url` is post-applied on `client_args`. Set
  `api_mode: chat` only for legacy Chat-Completions-only gateways (builds
  `OpenAIModel` with the `openai/` prefix stripped).
- **Mannerisms & API extras:**
  - `configure_openai_for_model()` strips `reasoning.effort` on non-reasoning
    models (`gpt-4o`, `gpt-4.1*`, `gpt-4-turbo`, `chat-latest`, `gpt-3.5*`) and
    clamps unsupported effort levels on `o1`/`o3`/`o4-mini`, `gpt-5`..`gpt-5.2`,
    and `gpt-6-astra`/`gpt-6.1-sol`/`gpt-6.2-*` so mid-session switches never
    trigger HTTP 400 errors.
  - Native extras (`service_tier`, `prompt_cache_retention`,
    `prompt_cache_options`, `use_native_token_count`) work via `params` / SDK
    model config; see upstream `#3389` for stateless encrypted reasoning item
    replay across client-side `OpenAIResponsesModel` turns.
  - `/model` discovery lists only Responses-capable chat/reasoning models
    (filtering out embeddings, Whisper/TTS/audio/transcribe/realtime,
    DALL-E/gpt-image, Sora, moderation, and legacy completions).

### Anthropic (zero AWS required)

Install the `anthropic` extra once, then export your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="<your-anthropic-key>"
strands-code --model anthropic/claude-sonnet-5-5   # or omit --model to auto-pick
```

- **Standard env vars & custom gateways:**
  `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` are read natively by the
  Anthropic SDK; non-secret gateway hosts can be persisted in
  `~/.config/strands-code/config.yaml` under `base_url` while keeping full
  Harness caching and native `web_search` intact.
- **API mannerisms, safety & metadata caching:**
  - **Exclusive usage counts & caching:** Anthropic's API reports uncached input
    tokens separately from `cache_read_input_tokens` and
    `cache_creation_input_tokens`; `strands-code` normalizes these alongside
    OpenAI's inclusive counts so context `%` and cache-discounted `/cost` are
    consistent.
  - **Signed thinking & `SummaryBlock` isolation:** Switching between
    `anthropic/claude-*` and `bedrock/anthropic.claude-*` converts raw signed
    thinking blocks (`TRACE_LABEL`) and server-side compaction `SummaryBlock`s
    (`SUMMARY_LABEL`) into text while stashing originals in `RichHistory` for
    lossless restore on return.
  - **SDK defaults & betas:** With `anthropic>=2.0`, default
    `anthropic-version: 2026-10-21` removes sampling parameters (`temperature`,
    `top_p`, `top_k`) on newer Claude models; `max_tokens` (e.g., 128K output),
    PDF/plain-text document blocks, and `/v1/models` live metadata (`max_input_tokens`,
    retirements shown in `/model` picker for 24h in `anthropic-models.json`) are
    wired automatically.

### Google Gemini (zero AWS required)

Install the `gemini` extra once, then export an API key (or set up Vertex ADC). No
AWS credentials are needed:

```bash
export GOOGLE_API_KEY="<your-aistudio-key>"   # or GEMINI_API_KEY
strands-code --model google/gemini-3.8-flash  # or omit --model to auto-pick from env
```

- **Google AI Pro & Google AI Ultra credits:** Personal subscriptions include
  monthly **Google Developer Program** GenAI API credits (`Google AI Pro`:
  \$10/month; `Google AI Ultra 5x`: \$40/month; `Google AI Ultra 20x`:
  \$100/month). Claim your credits and generate an API key in
  `aistudio.google.com` (a one-time \$5 Cloud Billing activation may be needed to
  move keys out of Free Tier rate limits). This funds current Gemini 3.8 and
  Gemini 4 models (`google/gemini-3.8-flash`, `google/gemini-4-hydrogen`,
  `google/gemini-4-neon`, `google/gemini-4-argon`, `google/gemini-4-carbon`);
  deprecated Gemini 2.5 ids remain supported for explicit `--model` / saved
  configs until AI Studio automatic rerouting on Dec 1, 2026.
- **Consumer OAuth unsupported:** Piggybacking on consumer Gemini CLI / Code
  Assist OAuth tokens (`cloudcode-pa.googleapis.com`) is intentionally unsupported
  (Google ToS violation); use AI Studio API keys or Vertex ADC.
- **Vertex AI ADC:** Set Vertex env vars without any API key:

  ```bash
  gcloud auth application-default login
  export GOOGLE_GENAI_USE_VERTEXAI=true
  export GOOGLE_CLOUD_PROJECT="<your-gcp-project>"
  export GOOGLE_CLOUD_LOCATION="global"   # recommended for Gemini 3.x / 4.x models
  strands-code --model google/gemini-3.8-flash
  ```

  **Mutual exclusion:** Do **not** set `GOOGLE_API_KEY` or `GEMINI_API_KEY` at the
  same time as `GOOGLE_GENAI_USE_VERTEXAI=true`; startup fails fast (exit 2) when
  both are set or when `GOOGLE_CLOUD_PROJECT` is missing.

### Meta Model API (`api.meta.ai` / Muse, zero AWS required)

Install the `meta` extra once (reuses `strands-agents[openai]` + `openai>=2.0.0`,
no new dependencies), then export `MODEL_API_KEY` (`META_API_KEY` is also
accepted as a fallback; `META_BASE_URL` optionally overrides
`https://api.meta.ai/v1`):

```bash
export MODEL_API_KEY="<your-meta-model-api-key>"
strands-code --model meta/muse-spark-1.3-contributor   # or omit --model to auto-pick
```

- **Ambient default & contributor tier:** When multiple keys are present, ambient
  auto-pick follows `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter ->
  Bedrock`. When Meta is chosen, `strands-code` defaults to
  `meta/muse-spark-1.3-contributor` for cost efficiency (\$0.10 in / \$0.002
  cached / \$0.20 out per 1M tokens — a 50× cached discount across a
  `1,048,576`-token window). Opt into non-contributor tiers via `--model` or
  `/model`:
  - `meta/muse-spark-1.3` (\$1.25 / \$0.15 cached / \$4.25 per 1M)
  - `meta/muse-wonder-1.0` (\$4.00 / \$0.20 cached / \$20.00 per 1M)
  - `meta/muse-ember-1.0` (\$0.10 / \$0.004 cached / \$0.50 `<200K`; \$0.30 /
    \$0.012 cached / \$1.50 `>200K` per 1M)
- **Protocol, caching & capabilities (empirically verified on `api.meta.ai/v1`):**
  - Uses Meta's native `/v1/responses` endpoint via `OpenAIResponsesModel` with
    automatic prefix caching (`prompt_cache_key`, inclusive `input_tokens`;
    `prompt_cache_options` is rejected by Meta and avoided automatically).
  - Supports native `web_search`, multimodal image inputs across Muse Wonder,
    Muse Spark, and Muse Ember (while Bedrock/OpenRouter Llama models stay
    text-only), and `[minimal, low, medium, high, xhigh, max]` reasoning levels
    (`none`/`off` omits `reasoning`).
  - `/model` discovery calls `GET /v1/models` only when keyed, filters out
    non-chat assets (`muse-image-*`, `muse-voice-transcribe-*`, `sam-*`), and
    groups Muse models cleanly under `meta / muse`.
  - Cross-provider switches into `meta/` convert prior thinking blocks cleanly to
    text while stashing raw signed blocks in `RichHistory` (see upstream `#3389`
    for stateless encrypted reasoning replay on `OpenAIResponsesModel`).

### OpenRouter, custom OpenAI-compatible hosts & Ollama

OpenRouter accepts `OPENROUTER_API_KEY` with an explicit model flag:

```bash
export OPENROUTER_API_KEY="<key>"
strands-code --model litellm/openrouter/anthropic/claude-sonnet-4.6
```

Custom OpenAI-compatible endpoints read two env vars (never stored in the repo):

```bash
export LITELLM_BASE_URL="https://openrouter.ai/api/v1"
export LITELLM_API_KEY="<key>"
```

then `/model litellm/openrouter/<vendor>/<model>`. Local Ollama runs without API
keys via `--model ollama/<model>` (or `--model litellm/ollama_chat/<model>`).

- **Other multi-model gateways & neocloud aggregators (BYO `base_url`):**
  OpenAI-compatible routers and aggregators — such as **Respan**
  (`https://gateway.respan.ai/v1`) or **AIHubMix** (`https://aihubmix.com/v1`) —
  work without dedicated provider extras by pointing `~/.config/strands-code/config.yaml`
  at their OpenAI-compatible endpoint (see `base_url` / `api_mode: chat` under
  [OpenAI](#openai-zero-aws-required) above, with `OPENAI_API_KEY` holding your
  gateway key), or via `--extra litellm` with `LITELLM_BASE_URL` +
  `LITELLM_API_KEY`.

### Model routing & decision keys

Optional pre-turn routing (`/route setup`, see [ROUTING.md](ROUTING.md)) keeps
provider credentials separate in env vars:

- `TYPESAFE_API_KEY`: direct **TypeSafe System One API** (`api.typesafe.ai`,
  `engine.order: [native]`, pinned `jev-1.13.0`).
- `JEV_API_KEY`: **decisionapi.net** multi-provider aggregator
  (`engine.order: [decisions_api]`, opt-in config defaulting to
  `~typesafe/jev-latest`). Kept separate from `TYPESAFE_API_KEY` so both keys
  coexist cleanly without colliding.
- `OPENROUTER_API_KEY` / Ollama / `engine.order: [llm]`: OpenRouter Decisions,
  local Ollama `/v1/systemone`, or any configured LLM via `engine.llm_model`.

## Model capabilities (advanced)

Mid-session `/model` switches convert history to what the target accepts
(thinking blocks, media). Verdicts come from the harness first, with
fail-closed defaults for the unknown. When a verdict is wrong for a new
model, correct it without waiting for a release in
`~/.config/strands-code/model-capabilities.yaml`:

```yaml
overrides:
  - match: {provider: bedrock, vendor: amazon, family: nova}
    reasoning: true
  - match: {name_contains: gpt-oss}
    media: true
```

First match wins; `/context` shows how many overrides are active. Typos
warn-and-skip — they never break startup. Restart the CLI to reload.

## Cost + live pricing

- `/cost` shows per-turn tokens plus session totals, with a `Prices:`
  line naming the source: live Bedrock Price List, live OpenRouter
  (for `openrouter/...` ids), LiteLLM bundled data, or the static
  fallback. Display only — never budgets or enforcement.
- **Cache-aware usage & normalized tokens:** When prompt cache reads or writes
  occur (`cacheReadInputTokens` / `cacheWriteInputTokens`), post-turn usage lines
  append `(17%, 75% cached)` and `/cost` shows `in 165.60K (125.00K cached,
  40.50K write)` with discounted USD totals (zero-cache turns omit cache tags).
  Anthropic's exclusive input counts and OpenAI/Gemini's inclusive counts are
  normalized automatically (`total_in`). Organization Admin billing APIs
  (`/v1/organizations/...`) remain intentionally out of scope for standard
  developer keys.
- `/cost refresh` re-fetches live pricing tables now (cached 24h in
  `~/.cache/strands-code/`, alongside `anthropic-models.json` populated during
  live Anthropic discovery); `/cost table [filter]` lists cached per-1M prices
  without touching the network.
- Set `STRANDS_CODE_NO_LIVE_PRICING=1` to force static-only
  resolution (fully offline, unknown models show tokens without `$`).

## REPL basics (Phase 1)

- Type an ask, get a streamed answer, keep asking — one conversation.
- `/resume`, `/rename`, `/exit` work; unknown `/slash` shows a usage hint.
- Ctrl-C cancels the current line; Ctrl-D exits with state saved.
- `kill -9` mid-idle is survivable: relaunch with the same session id.

## Skills marketplaces

Add opt-in remote (GitHub HTTPS) or local-directory skill catalogs and pin
third-party skills by commit SHA and directory hash (`strands-code` ships with
zero pre-registered remote marketplaces):

- **Manage catalogs** (persisted in `~/.config/strands-code/marketplaces.yaml`
  with cached indexes in `~/.cache/strands-code/marketplaces/`):
  - `/skills marketplace add <owner/repo|local-path> [--name <alias>] [--ref <ref>]`
  - `/skills marketplace list`
  - `/skills marketplace update [name]`
  - `/skills marketplace remove <name>`
- **Browse, install, update, sync & inspect:**
  - `/skills browse [marketplace] [--refresh]` (reads local cache by default; no unprompted network traffic)
  - `/skills install <ns:skill|skill@ns|owner/repo[@ref]|local-path> [--skill <name>]`
  - `/skills update [name|ns:name]`
  - `/skills sync` (restores drifted or missing marketplace skills to pinned lockfile commits)
  - `/skills show <name|ns:name>` & `/skills remove <name|ns:name>` (alias `uninstall`)
  - Tab completion supports `/<ns>:<skill>` prefixes dynamically alongside `/local:<skill>`.
- **Project layout & precedence:**
  - Project-local skills live under `./.agent/skills/` (`local:<name>`) and
    always win bare-name ties over marketplace skills.
  - Marketplace skills install under `./.agent/skills-marketplaces/<ns>/<skill>/`
    and pin `commit_sha` + deterministic SHA-256 hashes in `./.agent/skills-lock.json`.
  - Any marketplace skill lacking a lock entry, containing a symlink, or failing
    hash verification is warn-and-skipped until `/skills sync` or `/skills remove`.
- **Rate limits & supply-chain safety:**
  - Set optional `GITHUB_TOKEN` or `GH_TOKEN` in your shell environment for higher
    GitHub API rate limits (sent strictly to `api.github.com` over HTTPS, never
    forwarded on redirects or written to disk; zero `git` subprocesses).
  - Unpacking enforces deny-first checks (no symlinks, hardlinks, FIFOs/devices,
    `.gitmodules`, or `..` traversal; 25 MiB tarball / 256 files / 5 MiB unpacked
    caps). Bundled `scripts/*` trigger prominent warnings and remain gated by
    shell/Python HITL approval; `allowed-tools` stays informational only; and
    broad `[[allow]]` rules on `write`/`edit` targeting `.agent/skills*`,
    `.agent/skills-lock.json`, or `~/.config/strands-code/**` downgrade to a prompt.

## Strands Box Linux sandbox floor

Strands Box (`strands-agents/box`) provides an OS-enforced Linux containment
floor underneath `strands-code`'s interactive HITL prompts. Inside the box
(`STRANDS_BOX=1`), host API keys never enter `[agent.env]` (instead, the
host proxy injects credentials out-of-band per egress rule), filesystem mounts
restrict writes to the workspace and isolated session state, and the embedded
Dogwood engine evaluates Cedar + MFOTL temporal rules externally.

- **Linux binary installation (3 co-located binaries):** Install `box`,
  `strands-box-contain-trampoline`, and `strands-box-sock-alias` into the same
  directory (for example `/usr/local/libexec/strands-box/` or `~/.local/bin/`,
  via Strands Box's `install.sh`, `download.sh`, or Cargo build) and ensure `box`
  is on `PATH` or pointed to by `STRANDS_BOX_BIN` / `--box-bin`.
- **Linux `x86_64` requirement:** Set `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux
  `x86_64` hosts (`strands-code box run` exports this automatically for the child
  `box` process when running on `x86_64`).
- **Ubuntu 24.04+ AppArmor userns profile:** When
  `kernel.apparmor_restrict_unprivileged_userns=1` is active, Bubblewrap's
  `/etc/apparmor.d/bwrap` does **not** cover Strands Box. Install
  `/etc/apparmor.d/strands-box` (adjust the binary glob path if installed
  elsewhere, then run `sudo apparmor_parser -r /etc/apparmor.d/strands-box`):

```text
abi <abi/4.0>,
include <tunables/global>

profile strands-box /usr/local/libexec/strands-box/{box,strands-box-contain-trampoline} flags=(unconfined) {
  userns,
  include if exists <local/strands-box>
}
```

- **CLI workflow:**

```bash
strands-code box init        # writes ~/.config/strands-box/repos/<slug>-<hash8>/{box.toml,policy.dw}
strands-code box doctor      # checks x86_64 flag, 3-binary layout, AppArmor userns, config & uv realpath
strands-code box run -- --codeact --model anthropic/claude-sonnet-5-5
```

- **Host-only config storage & runtime alignment:**
  - Repo configs live host-only under `~/.config/strands-box/repos/<slug>-<hash8>/`
    (`0o700` dirs, `0o600` files, symlink-refused) — omitted from
    `[agent.filesystem].write` and downgraded to `Prompt` even under broad
    `allow` rules (`policy/core.py`).
  - Temporary files inside the box use `TMPDIR=~/.cache/strands-code/tmp` (host
    `/tmp` is never mounted). Secret-less egress targets
    (`openrouter.ai/api/v1/models*`, `codeload.github.com`,
    `objects.githubusercontent.com`) are permitted solely in `policy.dw` rather
    than `[egress.*]` entries in `box.toml`.
  - `/policy` and `/policy show` display `Sandbox: Strands Box active (STRANDS_BOX=1)`
    when running boxed.
  - Under `STRANDS_BOX=1`, CodeAct's `codeact_shell` executes commands via
    `["sh", "-c", shlex.join(argv)]` so `shell([...])` calls feed Dogwood's
    `shell:spawn` audit log with shell metacharacter quoting intact.
- **Auto-detected 8-provider egress profiles + `--allow-github-skills` opt-in:**

| Profile | Destination host / path scope | Out-of-band secret / header injection | Notes |
| :--- | :--- | :--- | :--- |
| `bedrock` | `bedrock-runtime.<region>.amazonaws.com` | `aws://<profile>` or `aws://` SigV4 (or `env://AWS_BEARER_TOKEN_BEDROCK` Bearer) | Never opens `sts.amazonaws.com` |
| `google` | `generativelanguage.googleapis.com` | `env://GOOGLE_API_KEY` or `GEMINI_API_KEY` via `x-goog-api-key` | Auto-detected from config / routing / env |
| `anthropic` | `api.anthropic.com` | `env://ANTHROPIC_API_KEY` via `Authorization: Bearer` | Auto-detected |
| `openai` | `api.openai.com` | `env://OPENAI_API_KEY` via `Authorization: Bearer` | Auto-detected |
| `meta` | `api.meta.ai` | `env://MODEL_API_KEY` or `META_API_KEY` via `Authorization: Bearer` | Auto-detected |
| `openrouter` | `openrouter.ai/api/v1/chat/*`, `openrouter.ai/api/alpha/decisions` (+ unauth `openrouter.ai/api/v1/models*`) | `env://OPENROUTER_API_KEY` via `Authorization: Bearer` (policy-only on `/api/v1/models*`) | Path-scoped; keeps `/cost` & `/route setup` catalog fetches working |
| `typesafe` | `api.typesafe.ai` | `env://TYPESAFE_API_KEY` via `Authorization: Bearer` | Auto-detected |
| `decisions_api` | `decisionapi.net` | `env://JEV_API_KEY` via `Authorization: Bearer` | Auto-detected after `typesafe` from `routing.yaml` or `JEV_API_KEY` (`--allow-decisions-api` force-enables) |
| `--allow-github-skills` | `api.github.com`, `codeload.github.com`, `objects.githubusercontent.com` | Optional `GITHUB_TOKEN`/`GH_TOKEN` strictly on `api.github.com` | Opt-in flag on `box init` (download hosts authorized in `policy.dw`) |

- **Dogwood policy & formal scoped revisit of `D-05`:** Generated `policy.dw`
  sets default-deny egress, forbids `fs:read` on `*/.env`, `*/.env.*`, `*/.ssh/*`,
  and `*/.aws/*`, and includes the canonical MFOTL temporal rule
  `push_requires_recent_tests` (`forbid` on `git` `push` `unless temporal` a
  passing `pytest` `shell:spawn::response` with `output.status: 0` ran
  `formerly within 900s`). Per `v2.0`'s scoped revisit of `D-05`, external host-side
  deterministic `.dw` rules are scoped exclusively to Strands Box while in-process
  Python `interventions` remain deterministic TOML + Python only.
