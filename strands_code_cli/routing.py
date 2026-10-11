"""Per-ask model routing via a cheap decision model (MODEL-03).

A routing strategy (candidate model set + freeform directives, global or
repo file with repo winning whole-file) arms routing; without one the
CLI behaves exactly as before (D-01). Each configured ask routes
pre-turn at idle through an ordered engine registry — OpenRouter chat
completions first, hold-current last — and the pick applies through the
existing switch machinery. No heuristic ever picks a model: every
engine, parse, or resolve failure holds the current model with history
byte-identical (D-08).
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
        if not isinstance(value, str):
            logger.warning("Ignoring routing engine %r (not a string)", key)
            continue
        setattr(engine, key, value)
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

    Returns None when both files are missing or unparsable (routing off).

    Raises:
        ValueError: When either resolved path is a symlink (fail-loud,
            same policy as provider config and capability overrides).
    """
    repo = Path(repo_path) if repo_path is not None else default_repo_strategy_path()
    strategies = _load_one(repo)
    if strategies is not None:
        return strategies
    home = (
        Path(global_path) if global_path is not None else default_global_strategy_path()
    )
    return _load_one(home)


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


def decide_via_openrouter(
    *,
    decision_model: str,
    system: str,
    user: str,
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> str | None:
    """One routing decision via OpenRouter chat completions; None on failure.

    The ``OPENROUTER_API_KEY`` is read at call time inside this engine
    function only (runtime-supplied credential, never persisted, sent
    header-only, never logged — the harness ``OLLAMA_API_KEY``
    precedent). Any failure (no key, network, timeout, malformed
    payload) yields None and the chain tries the next engine.
    """
    import urllib.request

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not decision_model:
        return None
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
        return None
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message", {})
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) and content.strip() else None


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


EngineAttempt = Callable[[RoutingStrategy, str, str], str | None]
"""One engine try: (strategy, system, user) -> raw text or None."""

_ENGINE_REGISTRY: list[tuple[str, EngineAttempt]] = []
"""Ordered engine chain; each engine is tried once per ask."""


def register_engine(name: str, attempt: EngineAttempt) -> None:
    """Append one named engine to the chain (08-02 adds the local engine)."""
    _ENGINE_REGISTRY.append((name, attempt))


def _openrouter_attempt(strategy: RoutingStrategy, system: str, user: str) -> str | None:
    """OpenRouter chain link: None without a configured decision model."""
    decision_model = strategy.engine.decision_model
    if not decision_model:
        return None
    return decide_via_openrouter(decision_model=decision_model, system=system, user=user)


register_engine("openrouter", _openrouter_attempt)


def decide(
    strategy: RoutingStrategy,
    *,
    current_model: str,
    side: bool,
    ask: str,
) -> tuple[RoutingPick | None, str]:
    """Route one ask: prompt build, engine chain, strict parse.

    Returns ``(pick, engine)`` where engine names the producing engine
    on success and the last failed engine on hold. Total failure —
    every engine None or unparseable — yields ``(None, engine)`` and
    the caller holds current (D-08).
    """
    system, user = build_routing_prompt(
        directives=strategy.directives,
        candidates=strategy.candidates,
        current_model=current_model,
        side=side,
        ask=ask,
    )
    failed = "openrouter"
    for name, attempt in _ENGINE_REGISTRY:
        try:
            text = attempt(strategy, system, user)
        except Exception:
            text = None
        if text is None:
            failed = name
            continue
        pick = parse_pick(text, strategy.candidates)
        if pick is None:
            failed = name
            continue
        return (pick, name)
    return (None, failed)


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
    *, model: str, effort: str, why: str, prev_model: str, ask: str
) -> str:
    """One transcript line for a routed ask (model, why, cost impact)."""
    delta = route_cost_delta(model, prev_model, ask)
    return f"Routed \u2192 {model} ({effort}): {why} \u00b7 ~${delta}/ask vs {prev_model}"


def format_hold_line(*, current: str, engine: str) -> str:
    """Hold-current failure note naming the failed engine (D-08)."""
    return f"Routing held on {current} ({engine} failed; retrying next ask)"
