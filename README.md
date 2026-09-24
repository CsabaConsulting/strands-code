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

Full run guide: [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Run the CLI

From this repo:

```bash
uv run strands-code
```

From any other directory (sessions stay local to that directory):

```bash
uv run --project /home/csaba/repos/AWS/strands-code strands-code
```

Sessions live in `./.agent/sessions` relative to your working directory —
`cd` into the repo you want to work on, then launch. Resume with
`strands-code --session-id <uuid>` or the picker at launch.

First run without AWS credentials stops with a Bedrock setup pointer
(exit 2); the provider choice persists to a config file afterwards.

REPL basics: type an ask, keep asking — one conversation. `/resume`,
`/rename`, `/exit` work; unknown `/slash` shows a usage hint. Ctrl-C
cancels the line, Ctrl-D exits with state saved.

## Library use

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
| Interpreters | `SandboxedPythonInterpreter` (default, allowlisted), `ExecPythonInterpreter` (trusted, unrestricted), `AgentCorePythonInterpreter` (remote Bedrock AgentCore sandbox; needs `uv sync --extra agentcore` + AWS creds). Selected via `python_interpreter_class`. |
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

## CLI status

Working today (Phase 1): resumable multi-ask REPL, resume picker,
`--session-id`, `/resume` `/rename` `/exit`, session auto-titles,
Bedrock-or-stop first-run gate, kill-safe persistence. Coming next:
/model /compact /clear /memory /cost /diff /review, permissions UX,
fuzzy file picker, approval prompts.

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
