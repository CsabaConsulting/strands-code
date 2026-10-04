"""Leading-slash dispatch and launch resume picker (D-02/D-03)."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import typer

from strands_code_agent.code_agent import DEFAULT_CODE_AGENT_CALLBACK_HANDLER
from strands_code_agent.search_tool import format_hits, run_search
from strands_code_cli.diff_config import MODES, DiffConfig
from strands_code_cli.diff_gate import apply_stashed, store_for
from strands_code_cli.mode import APPROVE_EMPTY, APPROVE_EXECUTE, APPROVE_OK, MODE_USAGE, ModeState
from strands_code_cli.session_index import SessionIndex, rich_stash_path

USAGE_HINT = (
    "Available commands: /resume, /rename <title>, /forget <id>, "
    "/diff [approve-each|on-demand|auto|show|apply [path]|discard [path]], "
    "/search <pattern>, /policy [show|last], /mode [plan|act], /approve, "
    "/model|/models [provider/name|id|ARN], /cost [refresh|table [filter]], "
    "/compact, /clear, /context, /exit"
)

_MODEL_USAGE = "Usage: /model [provider/name|id|ARN]"
_MODEL_CUSTOM = "custom-model-id"
_MODEL_BACK = "back-one-level"
_MODEL_CANCEL = "cancel-stay-with-current"
_FORGET_USAGE = "Usage: /forget <session-id-or-prefix>"
_SESSION_DELETE = "delete-a-session"
_SESSION_DELETE_CONFIRM = "delete-session-confirmed"

_SDK_EXTRA_HINTS = {"litellm": "litellm", "bedrock": "agentcore"}
"""Optional-extra install hints keyed by provider prefix."""


def _sdk_hint(selection: str) -> str:
    """Install hint for a missing provider SDK (ImportError path).

    Bare ids and ARNs resolve through Bedrock (boto3, ``agentcore``
    extra); ``litellm/`` ids need the ``litellm`` extra. Anything else
    keeps the generic pointer.
    """
    if selection.startswith("arn:") or "/" not in selection:
        provider = "bedrock"
    else:
        provider = selection.split("/", 1)[0].lower()
    extra = _SDK_EXTRA_HINTS.get(provider)
    if extra is None:
        return " (provider SDK not installed)"
    return f" (install the '{extra}' extra: pip install strands-code-agent[{extra}])"

_DIFF_USAGE = "Usage: /diff [approve-each|on-demand|auto|show|apply [path]|discard [path]]"
_SEARCH_USAGE = "Usage: /search <pattern> [--glob <glob>] [--limit <n>]"
_POLICY_USAGE = "Usage: /policy [show|last]"
_MODE_USAGE = MODE_USAGE

_PICKER_LIMIT = 10


def dispatch(
    text: str,
    *,
    session_id: str,
    index: SessionIndex,
    cwd: str | Path | None = None,
    diff_config_path: str | Path | None = None,
    mode: ModeState | None = None,
    current_model: str | None = None,
    agent=None,
    session_turns: list | None = None,
) -> tuple[str, str | None]:
    """Route one REPL line: slash commands handled, anything else is an agent turn.

    Args:
        text: Raw input line.
        session_id: Active session id (the rename target).
        index: Sidecar title index backing /resume and /rename.
        cwd: Working directory for /search and scope checks (default: process cwd).
        diff_config_path: Override for the persisted diff mode (tests only).
        mode: Session-sticky mode holder (None → Act default, keeps
            standalone/test behaviour without a loop-owned holder).
        current_model: Active ``provider/name`` string for /model discovery
            fallback context (read-only; the router never swaps inline).
        agent: Live session agent for /compact, /clear, /context (read-only
            except the history mutation those commands own).
        session_turns: Per-turn token rows accumulated by the loop for /cost.

    Returns:
        ``(action, message)`` where action is ``"agent"`` (caller runs the
        model turn), ``"exit"`` (caller leaves the loop), ``"reply"``
        (caller shows message, never an agent turn), or ``"model"`` (a
        validated /model selection the loop applies at the idle prompt).
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return ("agent", None)
    head, _, arg = stripped.partition(" ")
    cmd = head.lower()
    rest = arg.strip()
    if cmd == "/exit":
        return ("exit", None)
    if cmd == "/resume":
        return ("reply", _resume_message(index, rest))
    if cmd == "/rename":
        return ("reply", _rename_message(index, session_id, rest))
    if cmd == "/forget":
        return ("reply", _forget_message(index, session_id, rest))
    if cmd == "/diff":
        return ("reply", _diff_message(session_id, rest, diff_config_path))
    if cmd == "/search":
        return ("reply", _search_message(rest, cwd if cwd is not None else os.getcwd()))
    if cmd == "/policy":
        return ("reply", _policy_message(rest))
    if cmd == "/mode":
        return ("reply", _mode_message(rest, mode))
    if cmd == "/approve":
        return _approve_message(mode)
    if cmd in ("/model", "/models"):
        return _model_message(rest, current_model)
    if cmd == "/cost":
        return ("reply", _cost_message(session_turns, current_model, rest))
    if cmd == "/compact":
        return ("reply", _compact_message(agent))
    if cmd == "/clear":
        return ("reply", _clear_message(agent, session_id))
    if cmd == "/context":
        return ("reply", _context_message(agent, current_model, session_turns))
    return ("reply", f"Unknown command {head!r}. {USAGE_HINT}")


_COST_USAGE = "Usage: /cost [refresh|table [filter]]"


def _cost_message(
    session_turns: list | None, current_model: str | None, rest: str = ""
) -> str:
    """Run /cost: session report, live-price refresh, or table listing."""
    from strands_code_cli.cost_context import cost_report, price_table, refresh_report
    from strands_code_cli.live_pricing import refresh_caches

    head, _, arg = rest.partition(" ")
    word = head.strip().lower()
    if not word:
        return cost_report(list(session_turns or []), current_model or "unknown-model")
    if word == "refresh":
        return refresh_report(refresh_caches())
    if word == "table":
        return price_table(arg.strip() or None)
    return _COST_USAGE


def _compact_message(agent) -> str:
    """Run /compact: summarize-old + keep-recent, pair-atomic, then report."""
    if agent is None:
        return "No active session."
    from strands_code_cli.cost_context import compact_messages, model_summarize

    before = len(getattr(agent, "messages", []) or [])
    if not before:
        return "Nothing to compact — history is empty."
    kept = compact_messages(agent, summarize=lambda old: model_summarize(agent, old))
    return f"Context compacted — {kept} recent messages kept, last ask re-grounded."


def _clear_message(agent, session_id: str) -> str:
    """Run /clear: wipe history in place, keep the session id."""
    if agent is None:
        return "No active session."
    from strands_code_cli.cost_context import clear_messages

    clear_messages(agent)
    return f"Context cleared — session {session_id} kept."


def _context_message(agent, current_model: str | None, session_turns: list | None) -> str:
    """Render /context: the exact item-3 field list, read-only."""
    if agent is None:
        return "No active session."
    from strands_code_cli.cost_context import context_report

    return context_report(agent, current_model or "unknown-model", session_turns)


def _model_count_label(name: str, count: int) -> str:
    """Picker label with correct singular/plural ("moonshot (1 model)")."""
    noun = "model" if count == 1 else "models"
    return f"{name} ({count} {noun})"


def _model_message(rest: str, current_model: str | None) -> tuple:
    """Handle /model: validate a selection or offer the discovered list.

    Never swaps inline — success returns ``("model", new_id)`` for the loop
    to apply at the idle prompt; every other path is a reply. Unknown
    providers surface resolve_model's supported-provider ValueError as a
    reply; uninstallable providers (missing optional SDK deps) reply
    fail-soft instead of raising.
    """
    from strands_harness.defaults import DEFAULT_MODEL
    from strands_harness.models import resolve_model

    from strands_code_cli.model_switch import (
        build_model_tree,
        discover_models,
        normalize_model_ref,
        route_label,
    )

    if not rest:
        configured = [current_model] if current_model else []
        options, _offline = discover_models(configured=configured)
        seen = list(dict.fromkeys(configured + options))
        tree = build_model_tree(seen)
        if sys.stdin.isatty():
            from strands_code_cli.choice import radio_choice

            def _ask(title, items, default):
                try:
                    return radio_choice(title, items, default=default)
                except RuntimeError:
                    return None

            def _default_index(items, contains):
                return next((i for i, item in enumerate(items) if contains(item)), 0)

            def _unchanged():
                return ("reply", "Model unchanged.")

            # Cascade loop: each non-top level offers Back; going back
            # re-shows the previous level with the earlier pick preselected.
            # picks[0..2] = vendor/family/base; deeper picks clear on change.
            picks: list = [None, None, None]
            stage = 0
            backing = False
            vendor = family = ""
            while True:
                if stage == 0:
                    items = [
                        (
                            v,
                            _model_count_label(v, sum(len(m) for _, m in f)),
                        )
                        for v, f in tree
                    ]
                    values = [v for v, _ in items]
                    default = (
                        values.index(picks[0])
                        if picks[0] in values
                        else _default_index(
                            tree,
                            lambda vf: any(
                                current_model in routes
                                for _, models in vf[1]
                                for _, routes in models
                            ),
                        )
                    )
                    cancel_label = (
                        f"Cancel (stay with {current_model})"
                        if current_model
                        else "Cancel"
                    )
                    picked = _ask(
                        "Select vendor",
                        items
                        + [(_MODEL_CUSTOM, "Custom model id / ARN / endpoint…")]
                        + [(_MODEL_CANCEL, cancel_label)],
                        default,
                    )
                    if picked is None or picked == _MODEL_CANCEL:
                        return _unchanged()
                    if picked == _MODEL_CUSTOM:
                        return ("reply", f"Enter a custom model as: {_MODEL_USAGE}")
                    vendor = picked
                    picks = [vendor, None, None]
                    backing = False
                    stage = 1
                elif stage == 1:
                    families = next(f for v, f in tree if v == vendor)
                    if len(families) == 1:
                        if backing:
                            stage = 0
                            continue
                        family = families[0][0]
                        picks[1] = family
                        stage = 2
                        continue
                    backing = False
                    names = [name for name, _ in families]
                    picked = _ask(
                        f"Select {vendor} family",
                        [
                            (name, _model_count_label(name, len(m)))
                            for name, m in families
                        ]
                        + [(_MODEL_BACK, "← Back to vendors")],
                        names.index(picks[1])
                        if picks[1] in names
                        else _default_index(
                            families,
                            lambda fm: any(
                                current_model in routes for _, routes in fm[1]
                            ),
                        ),
                    )
                    if picked is None:
                        return _unchanged()
                    if picked == _MODEL_BACK:
                        backing = True
                        stage = 0
                        continue
                    family = picked
                    picks[1:] = [family, None]
                    stage = 2
                elif stage == 2:
                    families = next(f for v, f in tree if v == vendor)
                    models = next(m for name, m in families if name == family)
                    if len(models) == 1:
                        if backing:
                            stage = 1
                            continue
                        picks[2] = models[0][0]
                        stage = 3
                        continue
                    backing = False
                    bases = [b for b, _ in models]
                    picked = _ask(
                        f"Select {vendor} {family} model",
                        [
                            (b, b if len(r) == 1 else f"{b} ({len(r)} routes)")
                            for b, r in models
                        ]
                        + [(_MODEL_BACK, "← Back to families")],
                        bases.index(picks[2])
                        if picks[2] in bases
                        else _default_index(
                            models, lambda br: current_model in br[1]
                        ),
                    )
                    if picked is None:
                        return _unchanged()
                    if picked == _MODEL_BACK:
                        backing = True
                        stage = 1
                        continue
                    picks[2] = picked
                    stage = 3
                else:
                    families = next(f for v, f in tree if v == vendor)
                    models = next(m for name, m in families if name == family)
                    routes = next(r for b, r in models if b == picks[2])
                    if len(routes) == 1:
                        return ("model", normalize_model_ref(routes[0]))
                    picked = _ask(
                        f"Select route for {picks[2]}",
                        [(route, route_label(route)) for route in routes]
                        + [(_MODEL_BACK, "← Back to models")],
                        0,
                    )
                    if picked is None:
                        return _unchanged()
                    if picked == _MODEL_BACK:
                        backing = True
                        stage = 2
                        continue
                    return ("model", normalize_model_ref(picked))
        if not seen:
            return ("reply", f"No models discovered offline. {_MODEL_USAGE}")
        lines = ["Available models:"]
        for vendor, families in tree:
            lines.append(f"  {vendor}:")
            for family, models in families:
                lines.append(f"    {family}:")
                for base, routes in models:
                    if len(routes) == 1:
                        lines.append(f"      {routes[0]}")
                    else:
                        lines.append(f"      {base}:")
                        lines.extend(f"        {route}" for route in routes)
        lines.append(f"Custom: {_MODEL_USAGE}")
        return ("reply", "\n".join(lines))
    selection = rest.strip()
    try:
        resolve_model(normalize_model_ref(selection), DEFAULT_MODEL)
    except ValueError as exc:
        return ("reply", f"Unknown model {selection!r}: {exc}")
    except ImportError as exc:
        return ("reply", f"Cannot use model {selection!r}: {exc}{_sdk_hint(selection)}")
    return ("model", normalize_model_ref(selection))


def _mode_holder(mode: ModeState | None) -> ModeState:
    """Loop-owned holder when present, else a throwaway Act default."""
    return mode if mode is not None else ModeState()


def _mode_message(rest: str, mode: ModeState | None) -> str:
    """Handle /mode: report, switch with announcement, or usage — replies only.

    No agent turn ever leaves this branch; approval prompts never live
    here (established reply-only pattern).
    """
    holder = _mode_holder(mode)
    verb = rest.strip().lower()
    if not verb:
        return holder.announce()
    if verb in ("plan", "act"):
        return holder.set(verb)
    return _MODE_USAGE


def _approve_message(mode: ModeState | None) -> tuple:
    """Handle /approve: explicit plan handoff gated on a pending plan.

    Empty cases stay replies. On success the session flips to act and
    the caller runs an agent turn carrying the execute prompt — the
    plan text lives in session history, so approval must *run*, not
    just announce (a reply-only /approve flips the mode and drops the
    plan). Approval prompts themselves never live here.
    """
    if mode is None:
        return ("reply", APPROVE_EMPTY)
    if not mode.pending_plan:
        return ("reply", APPROVE_EMPTY)
    mode.approve()
    return ("agent", f"{APPROVE_OK}\n{APPROVE_EXECUTE}")


def _diff_message(session_id: str, rest: str, config_path: str | Path | None) -> str:
    """Handle /diff: mode switch, status show, pending apply/discard — replies only.

    Approval prompts never live here (they would race the prompt); per-hunk
    approval happens inside the turn via the gate's ask callable.
    """
    config = DiffConfig.load(config_path)
    store = store_for(session_id)
    pending = store.list() if store is not None else {}
    if not rest or rest == "show":
        lines = [f"Diff mode: {config.mode} ({len(pending)} pending)."]
        for path in sorted(pending):
            lines.append(f"  {pending[path].get('op', 'edit')}: {path}")
        return "\n".join(lines)
    verb, _, arg = rest.partition(" ")
    verb = verb.lower()
    if verb in MODES:
        config.mode = verb
        config.save(config_path)
        return f"Diff mode set to {verb}."
    if verb == "apply":
        if store is None:
            return "No pending-change store for this session."
        target = arg.strip() or None
        return asyncio.run(apply_stashed(store, target))
    if verb == "discard":
        if store is None:
            return "No pending-change store for this session."
        target = arg.strip()
        if target:
            entry = store.pop(target)
            return f"Discarded pending change to {target}." if entry else f"No pending change to {target}."
        count = len(pending)
        store.clear()
        return f"Discarded {count} pending change(s)."
    return f"Unknown /diff mode {verb!r}. {_DIFF_USAGE}"


def _policy_message(rest: str) -> str:
    """Handle /policy: inspect-only replies (show rules, last covered).

    Approval prompts never live here (they would race the prompt); this
    only reports the effective policy and the gate's covered-action log.
    """
    from strands_code_cli.policy import PolicyConfig
    from strands_code_cli.policy_gate import last_covered

    verb = rest.strip().lower()
    if verb in ("", "show"):
        try:
            config = PolicyConfig.load()
        except ValueError as exc:
            return f"Policy config error: {exc}"
        lines = ["Effective policy (deny-wins across home + repo union):"]
        lines.append("Builtins: allow read, search; allow GET-shaped fetch, git fetch.")
        for rule in config.allow:
            lines.append(f"  allow {rule.describe()}")
        for rule in config.deny:
            lines.append(f"  deny {rule.describe()}")
        if config.options.trust_delegated:
            lines.append("  options: trust_delegated = true")
        return "\n".join(lines)
    if verb == "last":
        covered = last_covered()
        if not covered:
            return "No gated actions this session yet."
        return "Covered actions:\n" + "\n".join(f"  {line}" for line in covered)
    return f"Unknown /policy mode {verb!r}. {_POLICY_USAGE}"


def _search_message(rest: str, cwd: str | Path) -> str:
    """Run the search tool synchronously; never triggers a model turn."""
    pattern, file_glob, limit = _parse_search_args(rest)
    if not pattern:
        return _SEARCH_USAGE
    try:
        output = run_search(pattern, file_glob=file_glob, limit=limit, cwd=cwd)
    except ValueError as exc:
        return f"Cannot search: {exc}"
    return format_hits(pattern, output)


def _parse_search_args(rest: str) -> tuple[str, str | None, int]:
    """Split ``/search <pattern> [--glob <glob>] [--limit <n>]`` args."""
    tokens = rest.split()
    pattern_parts: list[str] = []
    file_glob: str | None = None
    limit = 50
    pos = 0
    while pos < len(tokens):
        token = tokens[pos]
        if token == "--glob" and pos + 1 < len(tokens):
            file_glob = tokens[pos + 1]
            pos += 2
        elif token == "--limit" and pos + 1 < len(tokens):
            try:
                limit = max(1, int(tokens[pos + 1]))
            except ValueError:
                pass
            pos += 2
        else:
            pattern_parts.append(token)
            pos += 1
    return (" ".join(pattern_parts), file_glob, limit)


def _resume_message(index: SessionIndex, rest: str) -> str:
    """Render /resume output: one session hint, or the recent list."""
    if rest:
        for entry in index.list_recent():
            if entry["id"] == rest:
                title = entry.get("title", "untitled")
                return f"To resume '{title}', exit and relaunch with --session-id {entry['id']}."
        return f"Unknown session id {rest!r}. {USAGE_HINT}"
    entries = index.list_recent(limit=_PICKER_LIMIT)
    if not entries:
        return "No previous sessions yet."
    lines = ["Recent sessions:"]
    for entry in entries:
        lines.append(f"  {entry['id'][:8]}  {entry.get('title', 'untitled')}")
    lines.append("Relaunch with --session-id <id> to resume.")
    return "\n".join(lines)


def _rename_message(index: SessionIndex, session_id: str, rest: str) -> str:
    """Apply /rename through index validation; failures stay REPL replies."""
    if not rest:
        return "Usage: /rename <new title>"
    try:
        entry = index.rename(session_id, rest)
    except (ValueError, KeyError) as exc:
        return f"Cannot rename: {exc}"
    return f"Session renamed to '{entry['title']}'."


def _sessions_dir_for_index(index: SessionIndex) -> Path:
    """Sessions dir sibling of the index root (the main.py layout).

    Production: ``./.agent/sessions`` next to ``./.agent/session_index``.
    """
    from strands_harness.defaults import DEFAULT_SESSION_DIR

    return index.root.parent / Path(DEFAULT_SESSION_DIR).name


def _snapshot_ids(session_dir: str | Path | None) -> set[str]:
    """Snapshot dir names on disk (pure orphans included, junk excluded)."""
    if session_dir is None:
        return set()
    try:
        names = [p.name for p in Path(session_dir, "session").iterdir() if p.is_dir()]
    except OSError:
        return set()
    return {n for n in names if rich_stash_path(Path("."), n) is not None}


def _resolve_forget_target(index: SessionIndex, session_dir, target: str) -> tuple[str | None, str | None]:
    """Resolve an id or unique prefix to a full session id.

    Candidates are the union of index ids and snapshot dir names, so
    pure-orphan dirs are forgettable too. Returns ``(id, None)`` or
    ``(None, error-reply)``.
    """
    known = {e["id"] for e in index.list_recent(limit=None)} | _snapshot_ids(session_dir)
    if target in known:
        return (target, None)
    matches = sorted(sid for sid in known if sid.startswith(target))
    if not matches:
        return (None, f"No session matches {target!r}. {_FORGET_USAGE}")
    if len(matches) > 1:
        lines = [f"Ambiguous prefix {target!r} — matches:"]
        lines.extend(f"  {sid}" for sid in matches)
        return (None, "\n".join(lines))
    return (matches[0], None)


def _remove_snapshot_dir(session_dir: str | Path | None, session_id: str) -> None:
    """Delete one snapshot dir; guarded against traversal and outside roots."""
    if session_dir is None:
        return
    root = Path(session_dir, "session")
    candidate = root / session_id
    try:
        resolved = candidate.resolve()
    except OSError:
        return
    try:
        same_parent = resolved.parent == root.resolve()
    except OSError:
        return
    if not same_parent or resolved.name != session_id:
        return  # traversal or relocated root: never delete
    shutil.rmtree(resolved, ignore_errors=True)


def forget_session(
    index: SessionIndex,
    session_dir: str | Path | None,
    target: str,
    *,
    current_id: str | None = None,
) -> tuple[bool, str]:
    """Delete a session everywhere: snapshots, stash sidecar, index entry.

    Shared core behind /forget and the picker delete flow. Refuses the
    active session (deleting it would corrupt the running loop) and
    ambiguous prefixes. A ``session_dir`` of None skips snapshot removal
    (index + sidecar only). Never raises on filesystem trouble: best
    effort per surface, one reply either way.
    """
    resolved, error = _resolve_forget_target(index, session_dir, target)
    if resolved is None:
        assert error is not None
        return (False, error)
    if current_id is not None and resolved == current_id:
        return (False, "Cannot forget the active session — switch away or exit first.")
    title = next(
        (e.get("title", "untitled") for e in index.list_recent(limit=None) if e["id"] == resolved),
        None,
    )
    _remove_snapshot_dir(session_dir, resolved)
    stash = rich_stash_path(index.root, resolved)
    if stash is not None:
        try:
            stash.unlink(missing_ok=True)
        except OSError:
            pass
    index.forget(resolved)
    label = f"'{title}' [{resolved[:8]}]" if title is not None else resolved
    return (True, f"Forgot session {label}.")


def _forget_message(index: SessionIndex, session_id: str, rest: str) -> str:
    """Run /forget: typed explicit id, so no second confirmation."""
    if not rest:
        return _FORGET_USAGE
    _, reply = forget_session(
        index, _sessions_dir_for_index(index), rest.strip(), current_id=session_id
    )
    return reply


def show_picker(index: SessionIndex, *, session_dir: str | Path | None = None) -> str | None:
    """Numbered resume picker over recent sessions plus start-new (D-02).

    A delete row nests a second picker plus an explicit confirm (Cancel
    is the default both times); after a deletion the list refreshes so
    several sessions can go in one visit.

    Args:
        index: Sidecar title index (recency order).
        session_dir: When given, entries without a snapshot prefix on disk
            are treated as untrusted orphans and hidden (T-02-02).

    Returns:
        The chosen session id, or None for start-new, empty list, or an
        aborted prompt.
    """
    if sys.stdin.isatty():
        # Arrow-key dialog (choice.radio_choice): same SIGINT-safe prompt
        # as the approval gate. ESC/failure means start-new (None);
        # Ctrl-C re-raises so startup cancel still works.
        from strands_code_cli.choice import radio_choice

        return _picker_tty_loop(index, session_dir, radio_choice)
    return _picker_typed_loop(index, session_dir)


def _picker_entries(index: SessionIndex, session_dir: str | Path | None):
    """Visible picker entries: recency order minus untrusted orphans."""
    entries = index.list_recent(limit=_PICKER_LIMIT)
    if session_dir is not None:
        entries = [e for e in entries if _has_snapshot(session_dir, e["id"])]
    return entries


def _picker_tty_loop(index: SessionIndex, session_dir, radio_choice) -> str | None:
    """Arrow-key resume picker with a nested delete flow."""
    while True:
        entries = _picker_entries(index, session_dir)
        if not entries:
            return None
        picked = radio_choice(
            "Recent sessions",
            [(e["id"], f"{e.get('title', 'untitled')} [{e['id'][:8]}]") for e in entries]
            + [(_SESSION_DELETE, "Delete a session…"), (None, "Start new session")],
            default=len(entries) + 1,
        )
        if isinstance(picked, str) and picked in {e["id"] for e in entries}:
            return picked  # real ids win over the delete sentinel
        if picked == _SESSION_DELETE:
            _picker_tty_delete(index, session_dir, entries, radio_choice)
            continue
        return None


def _picker_tty_delete(index: SessionIndex, session_dir, entries, radio_choice) -> None:
    """Nested delete picker + confirm; prints the forget reply."""
    console = DEFAULT_CODE_AGENT_CALLBACK_HANDLER.console
    target = radio_choice(
        "Delete a session",
        [(e["id"], f"{e.get('title', 'untitled')} [{e['id'][:8]}]") for e in entries]
        + [(None, "Cancel")],
        default=len(entries),
    )
    if not isinstance(target, str):
        return
    title = next(
        (e.get("title", "untitled") for e in entries if e["id"] == target), target
    )
    confirm = radio_choice(
        f"Delete '{title}' [{target[:8]}]?",
        [(_SESSION_DELETE_CONFIRM, "Delete permanently"), (None, "Cancel")],
        default=1,
    )
    if confirm != _SESSION_DELETE_CONFIRM:
        return
    _, reply = forget_session(index, session_dir, target)
    console.print(reply)


def _picker_typed_loop(index: SessionIndex, session_dir: str | Path | None) -> str | None:
    """Numbered resume picker with a nested delete flow (no tty)."""
    console = DEFAULT_CODE_AGENT_CALLBACK_HANDLER.console
    while True:
        entries = _picker_entries(index, session_dir)
        if not entries:
            return None
        console.print("Recent sessions:")
        for pos, entry in enumerate(entries, 1):
            console.print(f"  {pos}. {entry.get('title', 'untitled')} [{entry['id'][:8]}]")
        delete_at = len(entries) + 1
        console.print(f"  {delete_at}. Delete a session…")
        console.print(f"  {delete_at + 1}. Start new session")
        try:
            choice = typer.prompt("Select session", type=int, default=delete_at + 1)
        except (typer.Abort, EOFError):
            return None
        if 1 <= choice <= len(entries):
            return entries[choice - 1]["id"]
        if choice == delete_at:
            _picker_typed_delete(index, session_dir, entries, console)
            continue
        if choice == delete_at + 1:
            return None
        console.print(f"Enter a number 1-{delete_at + 1}.")


def _picker_typed_delete(index, session_dir, entries, console) -> None:
    """Numbered delete picker + confirm; prints the forget reply."""
    console.print("Delete a session:")
    for pos, entry in enumerate(entries, 1):
        console.print(f"  {pos}. {entry.get('title', 'untitled')} [{entry['id'][:8]}]")
    console.print(f"  {len(entries) + 1}. Cancel")
    try:
        choice = typer.prompt("Delete which", type=int, default=len(entries) + 1)
    except (typer.Abort, EOFError):
        return
    if not 1 <= choice <= len(entries):
        return
    target = entries[choice - 1]
    console.print(f"Delete '{target.get('title', 'untitled')}' [{target['id'][:8]}]?")
    console.print("  1. Delete permanently")
    console.print("  2. Cancel")
    try:
        confirm = typer.prompt("Confirm", type=int, default=2)
    except (typer.Abort, EOFError):
        return
    if confirm != 1:
        return
    _, reply = forget_session(index, session_dir, target["id"])
    console.print(reply)


def _has_snapshot(session_dir: str | Path, session_id: str) -> bool:
    """True when a snapshot prefix exists for the id under the session dir."""
    try:
        return (Path(session_dir) / "session" / session_id).is_dir()
    except OSError:
        return False
