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

Without AWS credentials the CLI stops with a Bedrock setup pointer (exit 2).
With credentials it uses Bedrock; the provider choice persists to a config
file for later `/model` switching (Phase 5).

## Optional providers

Base install covers Bedrock and direct-provider ids. Two opt-in extras:

```bash
uv sync --extra agentcore   # Bedrock model discovery + AgentCore sandbox (boto3)
uv sync --extra litellm     # OpenRouter / exotic providers via litellm/ ids
```

OpenRouter-style endpoints need two env vars (never stored in the repo):

```bash
export LITELLM_BASE_URL="https://openrouter.ai/api/v1"
export LITELLM_API_KEY="<key>"
```

then `/model litellm/openrouter/<vendor>/<model>`.

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

## REPL basics (Phase 1)

- Type an ask, get a streamed answer, keep asking — one conversation.
- `/resume`, `/rename`, `/exit` work; unknown `/slash` shows a usage hint.
- Ctrl-C cancels the current line; Ctrl-D exits with state saved.
- `kill -9` mid-idle is survivable: relaunch with the same session id.
