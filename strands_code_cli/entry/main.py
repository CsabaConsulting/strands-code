"""strands-code entry point: no-arg REPL with --session-id routing."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import typer
from strands._identifier import Identifier
from strands.session.snapshot_session_manager import validate_identifier
from strands.vended_plugins.skills import AgentSkills
from strands_harness import create_harness
from strands_harness.defaults import DEFAULT_SESSION_DIR, DEFAULT_SKILLS_DIR

from strands_code_agent.code_agent import (
    CODE_AGENT_INSTRUCTIONS,
    DEFAULT_CODE_AGENT_CALLBACK_HANDLER,
)
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.dispatch.core import show_picker
from strands_code_cli.entry.first_run import (
    BEDROCK_SETUP_POINTER,
    preflight_credentials,
)
from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.loop.btw import LockedHandler
from strands_code_cli.loop.core import run_loop
from strands_code_cli.loop.steering import register_steering_hook
from strands_code_cli.memory.memory_file import load_memory, register_memory_plugin
from strands_code_cli.memory.skills import discover_plugin_sources
from strands_code_cli.model.model_switch import (
    _provider_of,
    build_meta_model,
    configure_base_url_for_model,
    configure_gemini_for_model,
    configure_openai_for_model,
    configure_streaming_for_model,
    model_id_of,
    normalize_model_ref,
    resolve_harness_model,
    scoped_base_url,
    upstream_supports_meta,
)
from strands_code_cli.platform_io import ensure_private_dir
from strands_code_cli.policy.diff_gate import (
    PendingStore,
    bind_session,
    make_gated_edit,
    make_gated_write,
)
from strands_code_cli.policy.policy_gate import build_interventions
from strands_code_cli.sandbox.box import box_app
from strands_code_cli.session.session_index import SessionIndex

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="Conversational coding CLI. Runs the REPL immediately; resumes with --session-id.",
)
app.add_typer(
    box_app,
    name="box",
    help="Strands Box Linux sandbox config, diagnostics, and execution.",
)

Bedrock_SETUP_POINTER = BEDROCK_SETUP_POINTER

_SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _validate_session_id(value: str) -> str:
    """Run a CLI-supplied id through the SDK identifier validator.

    Raises:
        ValueError: When the id is malformed (separators, blank, dot-segments,
            or characters outside ``[A-Za-z0-9._-]``).
    """
    checked = validate_identifier(value, Identifier.SESSION)
    if (
        not checked.strip()
        or checked in (".", "..")
        or not _SESSION_ID_RE.fullmatch(checked)
    ):
        raise ValueError(f"session_id is not a valid session identifier: {value!r}")
    return checked


def _preflight_credentials(
    *, model: str | None = None, base_url: str | None = None
) -> str | None:
    """Validate credentials for the target provider or infer an opening model."""
    return preflight_credentials(model=model, base_url=base_url)


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


def model_for_config(
    model: str | None,
    base_url: str | None = None,
    api_mode: str | None = None,
) -> Any:
    """Map a persisted model string (+ optional endpoint host / api_mode) to a model.

    Plain ``provider/name`` strings — including ``openai/`` and ``anthropic/``
    with a custom ``base_url`` in default ``responses`` mode — pass through as
    strings so ``create_harness`` retains ``effort``, ``CacheConfig``, and
    native ``web_search``, with ``base_url`` post-applied by ``build_agent``.
    Custom ``litellm/`` gateways or explicit ``api_mode == "chat"`` on
    ``openai/`` build a legacy Chat Completions ``OpenAIModel`` (stripping the
    ``openai/`` prefix). Falls back to the string when the optional provider
    SDK is unavailable.
    """
    if model is None:
        return None
    raw_prefix, _, rest = (
        model.partition("/") if "/" in model else ("bedrock", "", model)
    )
    prefix = raw_prefix.lower()
    if prefix == "meta" and not upstream_supports_meta():
        try:
            return build_meta_model(model, base_url=base_url)
        except ImportError:
            return model
    use_chat_completions = base_url and (
        prefix == "litellm" or (prefix == "openai" and api_mode == "chat")
    )
    if use_chat_completions:
        try:
            from strands.models.openai import OpenAIModel

            chat_id = rest if prefix == "openai" else model
            resolved = OpenAIModel(model_id=chat_id, client_args={"base_url": base_url})
            resolved._strands_model_ref = model
            return resolved
        except ImportError:
            pass  # provider SDK missing: harness resolve reports it
    return model


def _build_web_fetch_model(model: str, base_url: str, api_mode: str | None) -> Any:
    """Resolve web_fetch summarizer with the custom base_url when possible."""
    try:
        return resolve_harness_model(
            model,
            effort="off",
            base_url=base_url,
            api_mode=api_mode,
            web_search=False,
            caching=False,
        )
    except Exception:
        return model


def build_agent(
    session_id: str,
    session_dir: str | Path,
    model: Any = None,
    *,
    base_url: str | None = None,
    api_mode: str | None = None,
):
    """Construct the session agent through the harness factory only.

    The harness default tool set (shell/read/write/edit live) is edited via
    an explicit ``builtin_tools`` MAPPING — not a pin list — so future
    upstream defaults still flow: shell/read stay on, builtin write/edit are
    pinned off in favor of the diff-gated wrappers of the same names
    (name-collision rule), and the local ``search`` tool rides the
    consumer ``tools`` list.
    """
    session_path = ensure_private_dir(
        session_dir, "session dir", mode=0o700, max_ancestors=1
    )
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    cwd = os.getcwd()
    store = PendingStore(session_path)
    bind_session(session_id, store)
    # Owned skills plugin (G-6-R2-6): the harness passes AgentSkills
    # instances through verbatim, so this handle lets /skills reload
    # refresh the model's registry via set_available_skills instead of
    # leaving it stale behind the CLI index. Always constructed (even
    # when the dir is missing — the tool then reports no skills, and a
    # later reload picks up the created dir).
    skills_plugin = AgentSkills(
        skills=discover_plugin_sources(Path(DEFAULT_SKILLS_DIR))
    )
    # Deferred: search_tool imports strands_code_cli at module level, so a
    # top-level import here would cycle (cli root -> main -> search_tool).
    from strands_code_agent.search_tool import search as search_tool

    kwargs: dict[str, Any] = {
        "tools": [
            interpreter.get_tool(),
            search_tool,
            make_gated_write(cwd=cwd, store=store, gate_active=True),
            make_gated_edit(cwd=cwd, store=store, gate_active=True),
        ],
        "builtin_tools": {
            "shell": True,
            "read": True,
            "write": False,
            "edit": False,
            # Risk 9: programmatic_tool_caller inner tool calls are
            # unverifiable through before_tool_call without a live model,
            # so the convenience tool stays off (fail-closed); airtightness
            # over convenience until the tracer proves inner-call gating.
            "programmatic_tool_caller": False,
        },
        # Single deterministic PolicyGateHandler on Strands InterventionHandler;
        # never a second instance (name-collision rule) and never
        # "ask"/"smart"/NL-string/Cedar (D-05 determinism).
        "interventions": (interventions := build_interventions()),
        "instructions": CODE_AGENT_INSTRUCTIONS,
        "session": {"id": session_id, "dir": str(session_path)},
        # Render-locked proxy (LOOP-03): main message blocks stay
        # contiguous against fenced /btw side blocks on RENDER_LOCK.
        "callback_handler": LockedHandler(DEFAULT_CODE_AGENT_CALLBACK_HANDLER),
        # Phase 6: explicit skills + memory seams — the owned
        # AgentSkills loads ./.agent/skills and MemoryManager runs the
        # ./.agent/memory fact store. The dual conventions file
        # (STRANDS.md + .agent/MEMORY.md) injects via the CLI-owned
        # register_memory_plugin below.
        "skills": skills_plugin,
        "memory": True,
    }
    if (
        base_url
        and isinstance(model, str)
        and model.partition("/")[0].lower() in ("openai", "anthropic", "meta")
    ):
        kwargs["builtin_tools"]["web_fetch"] = {
            "model": _build_web_fetch_model(model, base_url, api_mode)
        }
    if model is not None:
        kwargs["model"] = model
        if isinstance(getattr(model, "_strands_model_ref", None), str):
            # Pre-built adapter already carries config/CacheConfig; avoid harness warning.
            kwargs["caching"] = False
    agent = create_harness(**kwargs)
    resolved_model = getattr(agent, "model", None)
    target_id = model if isinstance(model, str) else model_id_of(resolved_model, "")
    if base_url:
        owner = _provider_of(normalize_model_ref(target_id)) if target_id else None
        if owner is not None:
            kwargs["_base_url"] = base_url
            kwargs["_base_url_provider"] = owner
            agent._base_url = base_url
            agent._base_url_provider = owner
            if api_mode:
                kwargs["_api_mode"] = api_mode
                agent._api_mode = api_mode
    # Stash the factory kwargs for /btw side-agent rebuilds (LOOP-03):
    # the loop replays this dict through create_harness with the
    # delegate overrides, so the child is built the way the parent was.
    agent._harness_kwargs = kwargs
    configure_streaming_for_model(target_id, resolved_model)
    configure_gemini_for_model(target_id, resolved_model)
    configure_openai_for_model(target_id, resolved_model)
    configure_base_url_for_model(target_id, resolved_model, base_url=base_url)
    if isinstance(model, str):
        # Initial-build wrap (D-07): a session starting on an OpenRouter
        # id captures from turn one. In-place promotion preserves the
        # resolved config; the stash keeps the STRING for side rebuilds
        # (which fresh-copy per build). Fail soft to the estimate path.
        try:
            import strands_code_cli.cost.live_pricing as live_pricing
            from strands_code_cli.cost.reported_cost import wrap_for_openrouter

            resolved = getattr(agent, "model", None)
            if (
                live_pricing.is_openrouter_id(model)
                and callable(getattr(resolved, "format_chunk", None))
                and not callable(getattr(resolved, "take_reported_costs", None))
            ):
                agent.model = wrap_for_openrouter(model, resolved)
        except Exception:
            pass
    agent._skills_plugin = skills_plugin  # owned handle for /skills reload
    gate = interventions[0]
    agent._policy_gate = gate
    gate.bind_main_agent(agent)  # D-12 delegated-turn detection
    # Phase 4: single steering hook (BeforeToolCallEvent at SDK_FIRST, so
    # it runs before PolicyGateHandler) closed over a session slot swapped per
    # turn; PolicyGateHandler checks event.cancel_tool directly and starts in Act.
    register_steering_hook(agent)
    # Phase 6: single memory injector (dual STRANDS.md + .agent/MEMORY.md
    # auto-load, .agent wins); idempotent per agent like the hook above.
    register_memory_plugin(agent, load_memory)
    gate.set_mode("act")
    return agent


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    session_id: str | None = typer.Option(
        None, "--session-id", help="Resume the session with this id."
    ),
    codeact: str | None = typer.Option(
        None,
        "--codeact",
        help="Start the session on this action interface (tool|code|both); the bare form implies code.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model reference for this session only (for example: google/gemini-3.8-flash).",
    ),
) -> None:
    """Open the REPL immediately (D-01); --session-id resumes directly (D-02)."""
    if ctx.invoked_subcommand is not None:
        return
    if session_id is not None:
        try:
            _validate_session_id(session_id)
        except ValueError as exc:
            raise typer.BadParameter(f"invalid --session-id: {exc}") from exc
    if codeact is not None and codeact not in ("tool", "code", "both"):
        raise typer.BadParameter("invalid --codeact: expected tool|code|both")
    if model is not None and not model.strip():
        raise typer.BadParameter("invalid --model: must be non-empty")
    config = ProviderConfig.load()
    effective_model = model.strip() if model is not None else config.model
    owner_provider = (
        _provider_of(normalize_model_ref(config.model))
        if config.model is not None
        else None
    )
    effective_base_url = (
        scoped_base_url(config.base_url, owner_provider, effective_model)
        if owner_provider is not None
        else None
    )
    effective_api_mode = config.api_mode if effective_base_url is not None else None
    # Gate runs before construction and before any session or index side
    # effect (D-05; reversing this to offline-first reworks launch).
    detected_model = _preflight_credentials(
        model=effective_model, base_url=effective_base_url
    )
    if effective_model is None:
        effective_model = detected_model
    # Index construction creates directories, so it runs only after the
    # side-effect-free validation and the credential gate above.
    index = SessionIndex(Path(DEFAULT_SESSION_DIR).parent / "session_index")
    if session_id is not None:
        resolved = resolve_session_id(session_id, index)
    else:
        picked = show_picker(index, session_dir=DEFAULT_SESSION_DIR)
        resolved = index.ensure(picked)["id"] if picked is not None else index.mint()
    agent = build_agent(
        resolved,
        DEFAULT_SESSION_DIR,
        model=model_for_config(effective_model, effective_base_url, effective_api_mode),
        base_url=effective_base_url,
        api_mode=effective_api_mode,
    )
    run_loop(
        agent,
        session_id=resolved,
        index=index,
        codeact=codeact,
        model_id=effective_model,
    )


def _expand_bare_codeact(argv: list[str]) -> list[str]:
    """Insert the implied code value after a value-less --codeact token.

    The pinned typer never forwards flag_value/is_flag to click, so a bare
    --codeact dies at parse time before any project code runs. Rewriting
    argv ahead of parsing gives the valued-only option its missing
    optional-value path while leaving every downstream site untouched.

    Only the exact --codeact token matches (--codeact=value passes
    through); expansion fires when the next token is missing or starts
    with a dash. Scanning stops at a bare -- sentinel, whose remainder
    is copied verbatim. The input list is never mutated.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            out.extend(argv[i:])
            break
        if token == "--codeact":
            out.append(token)
            nxt = argv[i + 1] if i + 1 < len(argv) else None
            if nxt is None or nxt.startswith("-"):
                out.append("code")
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def main() -> None:
    """Console script entry."""
    sys.argv[:] = _expand_bare_codeact(list(sys.argv))
    app()
