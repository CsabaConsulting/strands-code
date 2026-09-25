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
from strands_code_agent.search_tool import search as search_tool
from strands_code_cli.diff_gate import (
    PendingStore,
    bind_session,
    make_gated_edit,
    make_gated_write,
)
from strands_code_cli.first_run import BEDROCK_SETUP_POINTER, preflight_credentials
from strands_code_cli.loop import run_loop
from strands_code_cli.provider_config import ProviderConfig
from strands_code_cli.router import show_picker
from strands_code_cli.session_index import SessionIndex

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="Conversational coding CLI. Runs the REPL immediately; resumes with --session-id.",
)

Bedrock_SETUP_POINTER = BEDROCK_SETUP_POINTER


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
    preflight_credentials()


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
    """Construct the session agent through the harness factory only.

    The harness default tool set (shell/read/write/edit live) is edited via
    an explicit ``builtin_tools`` MAPPING — not a pin list — so future
    upstream defaults still flow: shell/read stay on, builtin write/edit are
    pinned off in favor of the diff-gated wrappers of the same names
    (name-collision rule), and the local ``search`` tool rides the
    consumer ``tools`` list.
    """
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    os.chmod(session_path, 0o700)
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    cwd = os.getcwd()
    store = PendingStore(session_path)
    bind_session(session_id, store)
    kwargs: dict[str, Any] = {
        "tools": [
            interpreter.get_tool(),
            search_tool,
            make_gated_write(cwd=cwd, store=store),
            make_gated_edit(cwd=cwd, store=store),
        ],
        "builtin_tools": {
            "shell": True,
            "read": True,
            "write": False,
            "edit": False,
        },
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
    # Gate runs before construction and before any session or config side
    # effect (D-05; reversing this to offline-first reworks launch).
    _preflight_credentials()
    config = ProviderConfig.load()
    # Index construction creates directories, so it runs only after the
    # side-effect-free validation and the credential gate above.
    index = SessionIndex(Path(DEFAULT_SESSION_DIR).parent / "session_index")
    if session_id is not None:
        resolved = resolve_session_id(session_id, index)
    else:
        picked = show_picker(index, session_dir=DEFAULT_SESSION_DIR)
        resolved = index.ensure(picked)["id"] if picked is not None else index.mint()
    agent = build_agent(resolved, DEFAULT_SESSION_DIR, model=config.model)
    run_loop(agent, session_id=resolved, index=index)


def main() -> None:
    """Console script entry."""
    app()
