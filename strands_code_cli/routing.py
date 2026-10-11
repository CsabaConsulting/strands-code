"""Per-ask model routing via a cheap decision model (MODEL-03).

A routing strategy (candidate model set + freeform directives, global or
repo file with repo winning whole-file) arms routing; without one the
CLI behaves exactly as before (D-01). Each configured ask routes
pre-turn at idle through an ordered engine registry — OpenRouter chat
completions first, the local Ollama daemon second, hold-current
last — and the pick applies through the existing switch machinery.
No heuristic ever picks a model: every engine, parse, or resolve
failure holds the current model with history byte-identical (D-08).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import platformdirs
import yaml

from strands_code_cli.cost_context import (
    cost_for,
    estimate_messages_tokens,
    price_for,
    window_for,
)
from strands_code_cli.model_switch import supports_reasoning

logger = logging.getLogger(__name__)

_STRATEGY_DIR_NAME = "strands-code"
_STRATEGY_FILE_NAME = "routing.yaml"
_REPO_STRATEGY_REL = Path(".agent") / "routing.yaml"

ASK_TRUNCATE_CHARS = 2000
"""Decision prompts carry the current ask only, truncated to this width."""

DECISION_TIMEOUT_SECONDS = 10
"""Per-engine network ceiling; a slow decision call holds, never blocks."""

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
"""Default decision engine transport (D-06)."""

OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
"""Default local daemon address (the harness ``OLLAMA_HOST`` default)."""

OLLAMA_TIMEOUT_SECONDS = 30
"""Local engine ceiling; cold model loads need room, failures still hold."""

OLLAMA_KEEP_ALIVE = "5m"
"""Keep the decision model warm between asks (one daemon round trip)."""

_TOP_LEVEL_KEYS = {"candidates", "directives", "engine", "quiet"}
_CANDIDATE_KEYS = {"id", "tier", "note", "levels", "benchmarks"}
_BENCHMARK_KEYS = {"swe_verified", "lmarena_coding", "aa_index", "pulled"}
_ENGINE_KEYS = {"primary", "decision_model", "local_model", "local_base_url"}


@dataclass
class RoutingCandidate:
    """One routable model entry from the strategy file."""

    id: str
    tier: str | None = None
    note: str | None = None
    levels: list[str] | None = None
    benchmarks: dict[str, Any] | None = None


@dataclass
class RoutingEngine:
    """Decision engine selection from the strategy file."""

    primary: str = "openrouter"
    decision_model: str | None = None
    local_model: str | None = None
    local_base_url: str | None = None


@dataclass
class RoutingStrategy:
    """Parsed strategy: candidates + directives + engine + source path."""

    candidates: list[RoutingCandidate] = field(default_factory=list)
    directives: str = ""
    engine: RoutingEngine = field(default_factory=RoutingEngine)
    quiet: bool = False
    source: Path | None = None


@dataclass(frozen=True)
class RoutingPick:
    """One parsed decision: model id + thinking level + one-line why."""

    model: str
    effort: str
    why: str


def default_global_strategy_path() -> Path:
    """Global strategy file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_STRATEGY_DIR_NAME)) / _STRATEGY_FILE_NAME


def default_repo_strategy_path() -> Path:
    """Repo strategy file path (cwd-anchored ``./.agent/routing.yaml``)."""
    return Path(os.getcwd()) / _REPO_STRATEGY_REL


def _parse_candidate(entry: object, pos: int) -> RoutingCandidate | None:
    """Normalize one candidate entry; warn and return None when untrusted."""
    if not isinstance(entry, dict):
        logger.warning("Ignoring routing candidate #%d (not a mapping)", pos)
        return None
    unknown = set(entry) - _CANDIDATE_KEYS
    if unknown:
        logger.warning(
            "Ignoring routing candidate #%d (unknown keys: %s)", pos, sorted(unknown)
        )
        return None
    candidate_id = entry.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        logger.warning("Ignoring routing candidate #%d (missing id)", pos)
        return None
    tier = entry.get("tier")
    if tier is not None and not isinstance(tier, str):
        logger.warning("Ignoring routing candidate #%d ('tier' not a string)", pos)
        return None
    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        logger.warning("Ignoring routing candidate #%d ('note' not a string)", pos)
        return None
    levels = entry.get("levels")
    if levels is not None:
        if not isinstance(levels, list) or any(
            not isinstance(level, str) for level in levels
        ):
            logger.warning(
                "Ignoring routing candidate #%d ('levels' not a string list)", pos
            )
            return None
        levels = list(levels)
    benchmarks = entry.get("benchmarks")
    if benchmarks is not None:
        if not isinstance(benchmarks, dict):
            logger.warning(
                "Ignoring routing candidate #%d ('benchmarks' not a mapping)", pos
            )
            return None
        unknown_bench = set(benchmarks) - _BENCHMARK_KEYS
        if unknown_bench:
            logger.warning(
                "Ignoring routing candidate #%d (unknown benchmark keys: %s)",
                pos,
                sorted(unknown_bench),
            )
            return None
        benchmarks = dict(benchmarks)
    return RoutingCandidate(
        id=candidate_id, tier=tier, note=note, levels=levels, benchmarks=benchmarks
    )


def _valid_base_url(value: str) -> bool:
    """True when the daemon address is an http(s) URL with a host (T-08-06)."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


def _parse_engine(raw: object) -> RoutingEngine:
    """Normalize the engine mapping; unknown keys warn and fall to defaults."""
    engine = RoutingEngine()
    if raw is None:
        return engine
    if not isinstance(raw, dict):
        logger.warning("Ignoring routing 'engine' (not a mapping); using defaults")
        return engine
    unknown = set(raw) - _ENGINE_KEYS
    if unknown:
        logger.warning("Ignoring unknown routing engine keys: %s", sorted(unknown))
    for key in ("primary", "decision_model", "local_model", "local_base_url"):
        value = raw.get(key)
        if value is None:
            continue
        if key == "primary" and isinstance(value, bool):
            # YAML 1.1 folds unquoted on/off (yes/no) to bools: honor
            # the intent instead of warn-and-defaulting an explicit off.
            setattr(engine, key, "openrouter" if value else "off")
            continue
        if not isinstance(value, str):
            logger.warning("Ignoring routing engine %r (not a string)", key)
            continue
        setattr(engine, key, value)
    base_url = engine.local_base_url
    if base_url is not None:
        if not base_url.strip():
            engine.local_base_url = None
        elif not _valid_base_url(base_url):
            logger.warning(
                "Ignoring routing local_base_url %r (http/https only); using %s",
                base_url,
                OLLAMA_DEFAULT_HOST,
            )
            engine.local_base_url = OLLAMA_DEFAULT_HOST
    return engine


def _parse_strategy(data: dict[str, Any], source: Path) -> RoutingStrategy:
    """Normalize one parsed YAML mapping (unknown top-level keys default)."""
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        logger.warning("Ignoring unknown routing keys: %s", sorted(unknown))
    raw_candidates = data.get("candidates", [])
    candidates: list[RoutingCandidate] = []
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        logger.warning("Ignoring routing 'candidates' (not a list)")
    else:
        for pos, entry in enumerate(raw_candidates):
            candidate = _parse_candidate(entry, pos)
            if candidate is not None:
                candidates.append(candidate)
    directives = data.get("directives", "")
    if directives is None:
        directives = ""
    if not isinstance(directives, str):
        logger.warning("Ignoring routing 'directives' (not a string)")
        directives = ""
    quiet = data.get("quiet", False)
    if not isinstance(quiet, bool):
        logger.warning("Ignoring routing 'quiet' (not true/false)")
        quiet = False
    return RoutingStrategy(
        candidates=candidates,
        directives=directives,
        engine=_parse_engine(data.get("engine")),
        quiet=quiet,
        source=source,
    )


def _load_one(path: Path) -> RoutingStrategy | None:
    """Parse one strategy file: None when missing or unparsable (warned)."""
    if path.is_symlink():
        raise ValueError(f"Routing strategy must not be a symlink: {path}")
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        logger.warning("Ignoring unreadable routing strategy %s: %s", path, exc)
        return None
    if data is None:
        return None
    if not isinstance(data, dict):
        logger.warning("Ignoring malformed routing strategy %s (not a mapping)", path)
        return None
    return _parse_strategy(data, path)


def load_strategy(
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> RoutingStrategy | None:
    """Load the routing strategy: repo wins whole-file, else global.

    Returns None when both files are missing or unparsable (routing off)
    and when the winning strategy sets ``engine.primary: off`` — the
    off switch lives at the load layer, so the hook takes its existing
    skip-silently branch with zero engine calls and no hold note.

    Raises:
        ValueError: When either resolved path is a symlink (fail-loud,
            same policy as provider config and capability overrides).
    """
    repo = Path(repo_path) if repo_path is not None else default_repo_strategy_path()
    strategies = _load_one(repo)
    if strategies is not None:
        return None if strategies.engine.primary == "off" else strategies
    home = (
        Path(global_path) if global_path is not None else default_global_strategy_path()
    )
    strategies = _load_one(home)
    if strategies is not None and strategies.engine.primary == "off":
        return None
    return strategies


_SYSTEM_PROMPT = """You route coding asks to exactly one candidate model. Reply with JSON only: {"model": "<candidate id>", "effort": "<level>", "why": "<=12 words>"}.
Rules:
- "model" MUST be one id from the candidate table verbatim.
- "effort" MUST be one of the candidate's advertised levels.
- Prefer STAYING on the current model unless another is clearly better."""


def _candidate_row(candidate: RoutingCandidate) -> str:
    """One candidate table line with live price and window values."""
    prices = price_for(candidate.id)
    if prices is None:
        price_cell = "n/a per 1M"
    else:
        price_cell = f"${prices[0]:g}/${prices[1]:g} per 1M"
    window = window_for(candidate.id)
    window_cell = str(window) if window is not None else "n/a"
    tier_cell = candidate.tier if candidate.tier else "-"
    levels_cell = ",".join(candidate.levels) if candidate.levels else "-"
    return f"{candidate.id} | {price_cell} | {window_cell} | {tier_cell} | {levels_cell}"


def build_routing_prompt(
    *,
    directives: str,
    candidates: list[RoutingCandidate],
    current_model: str,
    side: bool,
    ask: str,
) -> tuple[str, str]:
    """Build the (system, user) decision prompt for one ask.

    The user message carries directives, one candidate table line per
    model, the current model plus the side flag, then the ask text
    truncated to 2000 chars. No history, tool results, file contents,
    or catalog descriptions ever enter the prompt (T-08-02).
    """
    lines = ["User directives:", directives or "(none)", ""]
    lines.append("Candidate table (id | $in/$out per 1M | window | tier | levels):")
    lines.extend(_candidate_row(candidate) for candidate in candidates)
    lines.append("")
    lines.append(f"Current model: {current_model}. Side ask: {str(side).lower()}.")
    lines.append("")
    lines.append(ask[:ASK_TRUNCATE_CHARS])
    return (_SYSTEM_PROMPT, "\n".join(lines))


@dataclass(frozen=True)
class EngineResult:
    """One engine try: raw assistant text plus decision-call token usage.

    ``text`` is None on any failure (no key, network, timeout,
    malformed payload); the token counts come from the engine
    response usage fields and default to zeros when absent, feeding
    the /cost routing section (T-08-08).
    """

    text: str | None
    input_tokens: int = 0
    output_tokens: int = 0


def _count(value: object) -> int:
    """Best-effort non-negative int for a usage field (bool-safe)."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def decide_via_openrouter(
    *,
    decision_model: str,
    system: str,
    user: str,
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via OpenRouter chat completions.

    The ``OPENROUTER_API_KEY`` is read at call time inside this engine
    function only (runtime-supplied credential, never persisted, sent
    header-only, never logged — the harness ``OLLAMA_API_KEY``
    precedent). Any failure (no key, network, timeout, malformed
    payload) yields a text-None result and the chain tries the next
    engine.
    """
    import urllib.request

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not decision_model:
        return EngineResult(text=None)
    body = json.dumps(
        {
            "model": decision_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 300,
            "temperature": 0,
            "stream": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return EngineResult(text=None)
    if not isinstance(payload, dict):
        return EngineResult(text=None)
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return EngineResult(text=None)
    first = choices[0]
    if not isinstance(first, dict):
        return EngineResult(text=None)
    message = first.get("message", {})
    if not isinstance(message, dict):
        return EngineResult(text=None)
    content = message.get("content")
    text = content if isinstance(content, str) and content.strip() else None
    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return EngineResult(
        text=text,
        input_tokens=_count(usage.get("prompt_tokens")),
        output_tokens=_count(usage.get("completion_tokens")),
    )


_OLLAMA_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
"""Hosts that never carry key material (T-08-06)."""


def _ollama_headers(base: str) -> dict[str, str]:
    """Local daemon headers; the auth header only for proxied hosts."""
    from urllib.parse import urlsplit

    headers = {"Content-Type": "application/json", "User-Agent": "strands-code"}
    try:
        loopback = urlsplit(base).hostname in _OLLAMA_LOOPBACK_HOSTS
    except ValueError:
        loopback = False
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key and not loopback:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def decide_via_ollama(
    *,
    local_model: str,
    local_base_url: str | None = None,
    system: str,
    user: str,
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via the local Ollama daemon (``/api/chat``).

    The base URL resolves strategy-first, then the harness
    ``OLLAMA_HOST`` default; only http/https addresses with a host are
    called. The request is non-streaming with a JSON object format
    over model/effort/why and a 5m keep-alive; the usage pair comes
    from the response eval counts. Any failure yields a text-None
    result — offline with no daemon simply holds current (D-09).
    """
    import urllib.request

    if not local_model:
        return EngineResult(text=None)
    base = local_base_url or os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST
    if not _valid_base_url(base):
        return EngineResult(text=None)
    body = json.dumps(
        {
            "model": local_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "effort": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["model", "effort", "why"],
            },
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base.rstrip('/')}/api/chat", data=body, headers=_ollama_headers(base)
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return EngineResult(text=None)
    if not isinstance(payload, dict):
        return EngineResult(text=None)
    message = payload.get("message", {})
    if not isinstance(message, dict):
        return EngineResult(text=None)
    content = message.get("content")
    return EngineResult(
        text=content if isinstance(content, str) and content.strip() else None,
        input_tokens=_count(payload.get("prompt_eval_count")),
        output_tokens=_count(payload.get("eval_count")),
    )


def parse_pick(
    text: str | None, candidates: list[RoutingCandidate]
) -> RoutingPick | None:
    """Parse one engine response strictly; None holds the current model.

    ``model`` must equal a candidate id verbatim (no normalization, no
    fuzzy match — fuzzy matching is heuristic picking), ``effort`` must
    be a string inside that candidate's advertised levels when levels
    are advertised, and ``why`` truncates to one line. Anything else —
    malformed JSON, unknown ids, wrong levels — holds current (T-08-01).
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    model = data.get("model")
    if not isinstance(model, str):
        return None
    candidate = next((entry for entry in candidates if entry.id == model), None)
    if candidate is None:
        return None
    effort = data.get("effort")
    if not isinstance(effort, str) or not effort:
        return None
    if candidate.levels is not None and effort not in candidate.levels:
        return None
    why = data.get("why", "")
    if not isinstance(why, str):
        why = ""
    return RoutingPick(model=model, effort=effort, why=why.splitlines()[0][:200] if why else "")


EngineAttempt = Callable[[RoutingStrategy, str, str], EngineResult | None]
"""One engine try: (strategy, system, user) -> result or None when skipped."""

_ENGINE_REGISTRY: list[tuple[str, EngineAttempt]] = []
"""Ordered engine chain; each engine is tried once per ask."""


def register_engine(name: str, attempt: EngineAttempt) -> None:
    """Append one named engine to the chain (openrouter first, local second)."""
    _ENGINE_REGISTRY.append((name, attempt))


def _openrouter_attempt(
    strategy: RoutingStrategy, system: str, user: str
) -> EngineResult | None:
    """OpenRouter chain link: None without a configured decision model."""
    decision_model = strategy.engine.decision_model
    if not decision_model:
        return None
    return decide_via_openrouter(decision_model=decision_model, system=system, user=user)


def _ollama_attempt(
    strategy: RoutingStrategy, system: str, user: str
) -> EngineResult | None:
    """Local chain link: None without a configured local model (skipped)."""
    local_model = strategy.engine.local_model
    if not local_model:
        return None
    return decide_via_ollama(
        local_model=local_model,
        local_base_url=strategy.engine.local_base_url,
        system=system,
        user=user,
    )


register_engine("openrouter", _openrouter_attempt)
register_engine("local", _ollama_attempt)


def _chain_for(strategy: RoutingStrategy) -> list[tuple[str, EngineAttempt]]:
    """Engine links for one strategy: primary selects, unconfigured skips.

    ``openrouter`` tries the API then the daemon; ``local`` tries the
    daemon only (fully offline local-or-hold, D-09); ``off`` tries
    nothing — the load layer already yields None for it, and a
    directly built off strategy degrades the same way here. The local
    link is skipped, not failed, when no local model configures.
    """
    primary = strategy.engine.primary or "openrouter"
    if primary == "off":
        return []
    names = ["local"] if primary == "local" else ["openrouter", "local"]
    by_name = dict(_ENGINE_REGISTRY)
    chain: list[tuple[str, EngineAttempt]] = []
    for name in names:
        if name == "local" and not strategy.engine.local_model:
            continue
        attempt = by_name.get(name)
        if attempt is not None:
            chain.append((name, attempt))
    return chain


def decide(
    strategy: RoutingStrategy,
    *,
    current_model: str,
    side: bool = False,
    ask: str,
) -> tuple[RoutingPick | None, str, tuple[int, int]]:
    """Route one ask: prompt build, engine chain, strict parse.

    Returns ``(pick, engine, usage)`` where engine names the producing
    engine on success and the last attempted engine on hold, and usage
    is the decision-call ``(input, output)`` token pair (zeros on
    hold). Total failure — every engine empty or unparseable — yields
    ``(None, engine, (0, 0))`` and the caller holds current (D-08).
    One attempt per engine per ask; never any in-ask retry.
    """
    system, user = build_routing_prompt(
        directives=strategy.directives,
        candidates=strategy.candidates,
        current_model=current_model,
        side=side,
        ask=ask,
    )
    chain = _chain_for(strategy)
    if not chain:
        return (None, strategy.engine.primary or "openrouter", (0, 0))
    failed = chain[0][0]
    for name, attempt in chain:
        try:
            result = attempt(strategy, system, user)
        except Exception:
            result = None
        if result is None or result.text is None:
            failed = name
            continue
        pick = parse_pick(result.text, strategy.candidates)
        if pick is None:
            failed = name
            continue
        return (pick, name, (result.input_tokens, result.output_tokens))
    return (None, failed, (0, 0))


_EFFORT_NO_THINKING = ("auto", "off")
"""Effort values that need no thinking support (harness default / disabled)."""


def validate_routed_effort(
    pick: RoutingPick, candidates: list[RoutingCandidate]
) -> bool:
    """True when the pick effort may apply; False holds current (D-05).

    Pre-mutation gate, run before ``apply_switch``: the effort must sit
    inside the candidate's advertised levels when levels are
    advertised, and any thinking level needs a reasoning-capable
    candidate (``supports_reasoning`` family). Mismatches hold current
    and never coerce the level down to a supported one (D-08).
    """
    candidate = next((entry for entry in candidates if entry.id == pick.model), None)
    if candidate is None:
        return False
    if candidate.levels is not None and pick.effort not in candidate.levels:
        return False
    if pick.effort not in _EFFORT_NO_THINKING and not supports_reasoning(pick.model):
        return False
    return True


def decision_model_for(strategy: RoutingStrategy, engine: str) -> str | None:
    """Decision model id behind one engine name, for /cost accounting.

    ``openrouter`` prices at the API decision model, ``local`` at the
    daemon model; anything else (``resolve`` holds, unknown engines)
    has no decision model and prices nothing (T-08-08).
    """
    if engine == "openrouter":
        return strategy.engine.decision_model
    if engine == "local":
        return strategy.engine.local_model
    return None


def route_cost_delta(new_model: str, prev_model: str, ask: str) -> str:
    """``+0.0123``-style per-ask delta of new vs prev, or ``n/a``.

    Both sides price the same ask estimate (chars/4, symmetric
    in/out proxy); ``n/a`` when either side lacks prices.
    """
    estimate = estimate_messages_tokens([{"role": "user", "content": [{"text": ask}]}])
    new_cost = cost_for(estimate, estimate, new_model)
    prev_cost = cost_for(estimate, estimate, prev_model)
    if new_cost is None or prev_cost is None:
        return "n/a"
    return f"{new_cost - prev_cost:+.4f}"


def format_routed_line(
    *, model: str, effort: str, why: str, prev_model: str, ask: str, side: bool = False
) -> str:
    """One transcript line for a routed ask (model, why, cost impact).

    Side asks print the ``Routed (btw)`` head so the transcript tells
    spawn-time side picks apart from main-turn picks.
    """
    delta = route_cost_delta(model, prev_model, ask)
    head = "Routed (btw)" if side else "Routed"
    return f"{head} \u2192 {model} ({effort}): {why} \u00b7 ~${delta}/ask vs {prev_model}"


def format_hold_line(*, current: str, engine: str) -> str:
    """Hold-current failure note naming the failed engine (D-08)."""
    return f"Routing held on {current} ({engine} failed; retrying next ask)"


ROUTING_ON_REPLY = "Routing on — asks route pre-turn through the decision model."
ROUTING_OFF_REPLY = "Routing off — the current model serves every ask."
ROUTE_USAGE = "Usage: /route [on|off|status]"
MODEL_ROUTING_KEEP_REPLY = "Model unchanged — routing stays on."
ROUTING_MANUAL_OFF_NOTE = "Routing off — manual /model wins; /route on to re-enable."


class RoutingState:
    """Session-sticky routing toggle (D-10; mirrors :class:`ModeState`).

    ``state`` is ``"on"`` or ``"off"`` (anything else raises
    ``ValueError``). The loop owns one instance, defaulting to on when
    a strategy configures; ``/route`` flips it and a confirmed manual
    ``/model`` switch turns it off.
    """

    VALID = ("on", "off")

    def __init__(self, initial: str = "on") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown routing state {initial!r}: expected on|off")
        self._state = initial

    @property
    def state(self) -> str:
        """Current toggle state (``"on"`` or ``"off"``)."""
        return self._state

    def is_on(self) -> bool:
        """True when the pre-turn hook may route."""
        return self._state == "on"

    def set(self, state: str) -> str:
        """Flip the toggle; returns the transcript announcement.

        Raises:
            ValueError: For anything outside ``on|off``.
        """
        if state not in self.VALID:
            raise ValueError(f"unknown routing state {state!r}: expected on|off")
        self._state = state
        return ROUTING_ON_REPLY if state == "on" else ROUTING_OFF_REPLY

    def announce(self, strategy: RoutingStrategy | None = None) -> str:
        """Bare-status report for ``/route`` (toggle plus strategy detail)."""
        return route_status_text(self, strategy)


def route_status_text(
    routing: RoutingState, strategy: RoutingStrategy | None
) -> str:
    """Full ``/route status`` report: toggle, source, engine, count."""
    lines = [f"Routing: {routing.state}"]
    if strategy is None:
        lines.append("Strategy: none configured")
        return "\n".join(lines)
    source = str(strategy.source) if strategy.source is not None else "(unsaved)"
    count = len(strategy.candidates)
    noun = "candidate" if count == 1 else "candidates"
    lines.append(f"Strategy: {source} ({count} {noun})")
    decision = strategy.engine.decision_model or "(no decision model)"
    lines.append(f"Engine: {strategy.engine.primary} ({decision})")
    return "\n".join(lines)


def warn_applies(routing: RoutingState | None) -> bool:
    """True when ``/model`` must warn: toggle on AND a strategy configures."""
    if routing is None or not routing.is_on():
        return False
    try:
        strategy = load_strategy()
    except ValueError:
        return False
    return strategy is not None and bool(strategy.candidates)
