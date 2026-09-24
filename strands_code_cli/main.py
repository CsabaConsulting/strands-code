"""strands-code entry point: no-arg REPL with --session-id routing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
from strands_harness import create_harness
from strands_harness.defaults import DEFAULT_SESSION_DIR
from strands.session.snapshot_session_manager import validate_identifier
from strands._identifier import Identifier

from strands_code_agent.code_agent import (
    CODE_AGENT_INSTRUCTIONS,
    DEFAULT_CODE_AGENT_CALLBACK_HANDLER,
)
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.loop import run_loop
from strands_code_cli.router import show_picker
from strands_code_cli.session_index import SessionIndex

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="Conversational coding CLI. Runs the REPL immediately; resumes with --session-id.",
)

Bedrock_SETUP_POINTER = (
    "No AWS credentials found. strands-code runs its model on Amazon Bedrock.\n"
    "Set credentials via the ambient boto3 chain (env vars, ~/.aws/config, or an "
    "IAM role), then relaunch."
)


def _validate_session_id(value: str) -> str:
    """Run a CLI-supplied id through the SDK identifier validator.

    Raises:
        ValueError: When the id is malformed (separators, blank, dot-segments).
    """
    checked = validate_identifier(value, Identifier.SESSION)
    if not checked.strip() or checked in (".", ".."):
        raise ValueError(f"session_id is not a valid session identifier: {value!r}")
    return checked


def _preflight_credentials() -> None:
    """Stop with a Bedrock setup pointer when credentials are absent (D-05)."""
    try:
        import boto3
        from botocore.config import Config

        sts = boto3.client(
            "sts",
            config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 0}),
        )
        sts.get_caller_identity()
    except Exception:
        typer.secho(Bedrock_SETUP_POINTER, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)


def resolve_session_id(explicit: str | None, index: SessionIndex) -> str:
    """Map argv to a session id: validate an explicit id, else mint fresh."""
    if explicit is not None:
        try:
            checked = _validate_session_id(explicit)
        except ValueError as exc:
            raise typer.BadParameter(f"invalid --session-id: {exc}") from exc
        index.ensure(checked)
        return checked
    return index.mint()


def build_agent(session_id: str, session_dir: str | Path, model: Any = None):
    """Construct the session agent through the harness factory only."""
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    os.chmod(session_path, 0o700)
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    kwargs: dict[str, Any] = {
        "tools": [interpreter.get_tool()],
        "instructions": CODE_AGENT_INSTRUCTIONS,
        "session": {"id": session_id, "dir": str(session_path)},
        "callback_handler": DEFAULT_CODE_AGENT_CALLBACK_HANDLER,
    }
    if model is not None:
        kwargs["model"] = model
    return create_harness(**kwargs)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,  # noqa: F841 - callback signature requires the context slot
    session_id: str | None = typer.Option(
        None, "--session-id", help="Resume the session with this id."
    ),
) -> None:
    """Open the REPL immediately (D-01); --session-id resumes directly (D-02)."""
    if session_id is not None:
        try:
            _validate_session_id(session_id)
        except ValueError as exc:
            raise typer.BadParameter(f"invalid --session-id: {exc}") from exc
    # Index construction creates directories, so it runs only after the
    # side-effect-free validation above.
    index = SessionIndex(Path(DEFAULT_SESSION_DIR).parent / "session_index")
    if session_id is not None:
        resolved = resolve_session_id(session_id, index)
    else:
        picked = show_picker(index, session_dir=DEFAULT_SESSION_DIR)
        resolved = index.ensure(picked)["id"] if picked is not None else index.mint()
    _preflight_credentials()
    agent = build_agent(resolved, DEFAULT_SESSION_DIR)
    run_loop(agent, session_id=resolved, index=index)


def main() -> None:
    """Console script entry."""
    app()
