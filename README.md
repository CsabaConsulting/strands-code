# Strands Code

A Claude Code / Codex-class coding CLI built on the [Strands harness](https://github.com/strands-agents/harness-sdk).
Forked from [aws-samples/sample-strands-code-agent](https://github.com/aws-samples/sample-strands-code-agent);
its code-first agent library is preserved as the core differentiator, and the CLI is layered on top.

> Experimental: tracks fast-moving upstream (`strands-agents`, `strands-harness`). Expect churn; wrappers stay thin on purpose.

## Design directives

1. **Harness-first, gaps-only.** Adopt `strands-harness` (`create_harness()`) for tools, sessions, skills, memory, context management, and effort presets. Build only genuine CLI gaps: slash commands, permissions UX, file picker, memory-tier backends.
2. **Code-generation-first.** `CodeAgent` + `Toolkit` stay the paradigm: the agent writes Python in a persistent REPL with domain capabilities as importable functions, instead of orchestrating sequential tool calls.
3. **AWS-optional, never AWS-required.** Bedrock (LLM, KB memory, embeddings) and AgentCore are first-class *choices* behind config flags. Defaults are local: file sessions, markdown memory, sandboxed interpreter. The `agentcore` extra stays optional.
4. **Tiered memory.** Local markdown/SQLite by default (offline, private) → Hindsight opt-in (team, temporal reasoning) → memsearch/Milvus (enterprise scale). All behind one `MemoryStore` seam.
5. **Loose dependencies, thin wrappers.** No upper pins during the experimental phase; upstream syncs via the `upstream` remote.

Details: [docs/competitive-gap-analysis.md](docs/competitive-gap-analysis.md).

## Quick start

```bash
uv sync                   # project-local .venv + lockfile, incl. strands-harness
```

```python
from strands_code_agent import CodeAgent

agent = CodeAgent()
response = agent("What is 2 ** 10?")
```

The agent receives a `python_repl` tool automatically and solves tasks by writing and executing Python code.

## Library essentials

| Piece | What it is |
|---|---|
| `CodeAgent` | `strands.Agent` subclass; auto-registers `python_repl`, assembles the system prompt from toolkits (`strands_code_agent/code_agent.py`). Extra tools via `tools=[...]`; model etc. via `**kwargs`. |
| `Toolkit` | Domain bundle: `libraries` → interpreter allowlist, `initialization_code` → REPL preamble, `usage_instructions` → prompt guidance, `domain_specific_code` → auto-imported + documented symbols. Ships `VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT`. |
| Interpreters | `SandboxedPythonInterpreter` (default, allowlisted), `ExecPythonInterpreter` (trusted, unrestricted), `AgentCorePythonInterpreter` (remote Bedrock AgentCore sandbox; needs `pip install .[agentcore]` + AWS creds). Selected via `python_interpreter_class`. |
| Knowledge (OKF) | `strands_code_agent.knowledge`: convert PDFs to OKF concept bundles, navigate via `find` / `read` / `children` / `toc`. See `examples/pdf_to_okf_bundle/`. |
| Callback | `CodeAgentCallbackHandler`: Rich terminal rendering (code highlighting, Markdown/JSON detection). |

```python
from strands_code_agent import CodeAgent, Toolkit
from strands_code_agent.toolkits import DATA_ANALYSIS_TOOLKIT, VISUALIZATION_TOOLKIT

agent = CodeAgent(
    system_prompt="You are a data analyst.",
    toolkits=[DATA_ANALYSIS_TOOLKIT, VISUALIZATION_TOOLKIT],
)
```

## CLI direction

The CLI composes harness defaults with this library: `create_harness(tools=[python_repl, ...], instructions=..., plugins=..., memory=..., session=...)`, keeping `CodeAgent` as the agent class. Planned surface: `/model /resume /compact /clear /memory /cost /diff /review`, `--session-id`, fuzzy file picker, approval prompts. The harness `strands` CLI is the UX reference.

## Upstream sync

```bash
git fetch upstream   # aws-samples/sample-strands-code-agent
git merge upstream/main
```

## Tests

```bash
uv run pytest tests/ -v
```

Live AgentCore tests need `uv sync --extra agentcore`, AWS credentials, and `AWS_REGION`.

## License

MIT-0. See [LICENSE](LICENSE).
