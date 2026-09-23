---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# External Integrations

**Analysis Date:** 2026-09-22

## APIs & External Services

**LLM / Agent runtime:**

- Strands Agents SDK - Model-agnostic agent loop behind `CodeAgent`; model selection passes through `**kwargs` to `strands.Agent` (`strands_code_agent/code_agent.py`)
  - SDK/Client: `strands-agents>=0.1.0` (locked 1.57.0)
  - Auth: model-provider dependent; no keys handled in this repo

**AWS compute (optional):**

- Amazon Bedrock AgentCore Code Interpreter - Remote stateful Python sandbox used by `AgentCorePythonInterpreter` (`strands_code_agent/python_environments/agentcore.py`)
  - SDK/Client: `boto3>=1.35.0` via the optional `agentcore` extra (`boto3.client("bedrock-agentcore", region_name=...)`)
  - Auth: standard boto3 credential chain (env vars, shared config, IAM role); region defaults to `"us-east-1"`, identifier to `"aws.codeinterpreter.v1"`, session timeout to `900`s (max `28800`s) — all constructor kwargs, no env reads in code
  - API calls: `start_code_interpreter_session`, `invoke_code_interpreter` (`executeCode`, `language: python`), `stop_code_interpreter_session`

**AWS telemetry tag:**

- AWS Solutions User-Agent registration - `strands_code_agent/solution_user_agent.py` monkey-patches `botocore.session.Session.__init__` to append `AWSSOLUTION/SO0353/v0.4.0`; executed on package import (`strands_code_agent/__init__.py`)
  - SDK/Client: `botocore` (via `boto3`)
  - Auth: none (tag-only, no credentials)

**Documentation source (example only):**

- AWS Docs PDF download - `examples/pdf_to_okf_bundle/agent_with_knowledge.py` fetches `https://docs.aws.amazon.com/pdfs/bedrock-agentcore/latest/devguide/bedrock-agentcore-dg.pdf` via stdlib `urllib.request.urlretrieve` when the local PDF is missing
  - SDK/Client: stdlib `urllib` only
  - Auth: none (public URL)

## Data Storage

**Databases:**

- None - No relational, document, vector, or embedded database. `OKFBundle` (`strands_code_agent/knowledge/bundle.py`) lazily loads Markdown files from disk on first access; `KeywordSearchIndex` (`strands_code_agent/knowledge/search.py`) is an in-memory keyword scorer rebuilt per bundle load. Custom embedding backends are a documented extension point (`SearchIndex` ABC) but no implementation ships.

**File Storage:**

- Local filesystem only
  - OKF knowledge bundles: directories of Markdown files with YAML frontmatter, read/written with `pathlib` (`strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/pdf_to_okf_bundle.py`)
  - Agent scratch space: per-`CodeAgent` temp dir under `/tmp` via `tempfile.mkdtemp` (`strands_code_agent/code_agent.py`)
  - Image helper `image_to_base64()` (`strands_code_agent/utils.py`) reads local image files for prompt embedding

**Caching:**

- None - No cache layer, no TTL logic. REPL state persists in-process (`LocalPythonExecutor` state, `exec()` dict, or remote AgentCore session) and resets between user messages by design.

## Authentication & Identity

**Auth Provider:**

- Custom / delegated - This library authenticates to nothing itself
  - Implementation: LLM auth is delegated to the Strands model provider configuration; AWS auth is delegated to the boto3 credential chain. No login flows, tokens, API keys, OAuth, or session cookies exist in `strands_code_agent/`. The `agentcore` extra stays optional so local-only users need zero AWS identity.

## Monitoring & Observability

**Error Tracking:**

- None - No Sentry, Rollbar, or similar service

**Logs:**

- stdlib `logging` in `AgentCorePythonInterpreter` (`strands_code_agent/python_environments/agentcore.py`: session start/stop, stop-failure warnings)
- Rich console rendering in `CodeAgentCallbackHandler` (`strands_code_agent/callback_handler.py`): role-tagged text, syntax-highlighted `python_repl` code, tool-result status
- Usage/cost helper `get_response_metrics()` (`strands_code_agent/utils.py`) reads `response.metrics.get_summary()` (`inputTokens`, `outputTokens`, cycles, duration; optional per-1M-token cost math with Bedrock pricing link in docstring)

## CI/CD & Deployment

**Hosting:**

- PyPI library (`strands-code-agent 0.4.0`) built with `hatchling`; no app server or container target

**CI Pipeline:**

- `.github/workflows/publish.yml` - On GitHub `release: published`: checkout, `setup-python 3.11`, `pip install build`, `python -m build`, `pypa/gh-action-pypi-publish` (OIDC via `id-token: write`). No lint, test, or preview jobs.

## Environment Configuration

**Required env vars:**

- None for local use - `CodeAgent()` with defaults runs fully offline (sandboxed interpreter + local OKF files)
- For `AgentCorePythonInterpreter` only: standard AWS credential chain (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` / `AWS_REGION` or shared config / IAM role) resolved implicitly by boto3; no variable is read directly in this repo

**Secrets location:**

- Outside the repo - AWS credentials via the standard chain; no `.env` files, secret managers, or checked-in credentials detected (`.gitignore` covers standard Python artifacts; never add keys to the repo)

## Webhooks & Callbacks

**Incoming:**

- None - No HTTP server, routes, or webhook receivers

**Outgoing:**

- None - No HTTP callbacks or event posts. The closest analogues are agent-internal: the `python_repl` tool function returned by `PythonInterpreter.get_tool()` (`strands_code_agent/python_environments/base.py`) and the `CodeAgentCallbackHandler.__call__` message hook (`strands_code_agent/callback_handler.py`) — both in-process, not network calls

---

*Integration audit: 2026-09-22*
