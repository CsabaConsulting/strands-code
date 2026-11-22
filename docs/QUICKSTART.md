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
  `ANTHROPIC_API_KEY` -> `anthropic/claude-sonnet-4-6`,
  `OPENAI_API_KEY` -> `openai/gpt-5.4`, or exits 2 with a `--model litellm/openrouter/...`
  pointer when `OPENROUTER_API_KEY` is set alone), before falling back to Amazon Bedrock
  (`AWS_BEARER_TOKEN_BEDROCK` or the ambient boto3 chain via `sts:GetCallerIdentity`).
- `STRANDS_BOX=1` skips AWS STS and checks non-empty env presence only so Strands
  Box sessions pass without static prefix checks. Without credentials for the
  target provider, the CLI stops with a setup pointer (exit 2) before touching
  session directories.

## Optional providers

Base install covers Bedrock and direct-provider ids. Three opt-in extras:

```bash
uv sync --extra agentcore   # Bedrock model discovery + AgentCore sandbox (boto3)
uv sync --extra litellm     # OpenRouter / exotic providers via litellm/ ids
uv sync --extra gemini      # Google Gemini (strands-agents[gemini] / google-genai)
```

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
- `/cost refresh` re-fetches both live sources now (cached 24h in
  `~/.cache/strands-code/`); `/cost table [filter]` lists the cached
  per-1M-token prices without touching the network.
- Set `STRANDS_CODE_NO_LIVE_PRICING=1` to force static-only
  resolution (fully offline, unknown models show tokens without `$`).

## REPL basics (Phase 1)

- Type an ask, get a streamed answer, keep asking — one conversation.
- `/resume`, `/rename`, `/exit` work; unknown `/slash` shows a usage hint.
- Ctrl-C cancels the current line; Ctrl-D exits with state saved.
- `kill -9` mid-idle is survivable: relaunch with the same session id.
