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

## First run

Without AWS credentials the CLI stops with a Bedrock setup pointer (exit 2).
With credentials it uses Bedrock; the provider choice persists to a config
file for later `/model` switching (Phase 5).

## REPL basics (Phase 1)

- Type an ask, get a streamed answer, keep asking — one conversation.
- `/resume`, `/rename`, `/exit` work; unknown `/slash` shows a usage hint.
- Ctrl-C cancels the current line; Ctrl-D exits with state saved.
- `kill -9` mid-idle is survivable: relaunch with the same session id.
