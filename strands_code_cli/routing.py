"""Per-ask model routing via a cheap decision model (MODEL-03).

A routing strategy (candidate model set + freeform directives, global or
repo file with repo winning whole-file) arms routing; without one the
CLI behaves exactly as before (D-01). Each configured ask routes
pre-turn at idle through an ordered engine registry — the OpenRouter
Decisions API first, the local Ollama System One daemon second,
hold-current last — and the pick applies through the existing switch
machinery. The model judges (typed probability tables); code gates
(threshold plus tie-margin) and computes. No heuristic ever picks a
model: every engine, validation, gate, or resolve failure holds the
current model with history byte-identical (D-08).
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

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
"""Default decision engine transport (D-06)."""

TYPESAFE_DECISIONS_URL = "https://api.typesafe.ai/v1/systemone"
"""Native TypeSafe decision engine transport (Phase 9 D-05)."""

TYPESAFE_INPUT_USD_PER_MTOK = 0.042
"""Native input price per million tokens (flat input-only rate)."""

DEFAULT_TIE_MARGIN = 0.04
"""Near-tie gap: top-two within this routes the cheaper one (D-14).

Probe-derived 2026-10-12 (``evals/routing-probe/baseline.json``):
max observed near-tie margin 0.03 (Jev 0.51-vs-0.48 split) plus one
0.01 grid step of headroom — the grid floor is Jev's 2-decimal
rounding granularity (Pitfall 2). Below every routed margin (0.34
min), so zero probe outcomes change; arms the tie-break for future
threshold-clearing near-ties.
"""

DEFAULT_CONFIDENCE_THRESHOLD = 0.62
"""Model gate: top-1 probability below this holds current (D-16).

Probe-derived 2026-10-12 (``evals/routing-probe/baseline.json``):
midpoint of the observed (0.51 wrong-catchable max, 0.73 correct
min) gap, with 0.11 margin each side. One shared value serves both
pinned engines — neither misfires in the dangerous direction.
Always compared against the pick's top-1 probability, never the
vendor confidence field (Pitfall 1).
"""

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 524, 529})
"""Decision-API codes worth one retry; every 4xx holds immediately."""

MAX_CANDIDATES = 26
"""Hard candidate cap: the binding ``choice`` option limit is 26."""

OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
"""Default local daemon address (the harness ``OLLAMA_HOST`` default)."""

OLLAMA_TIMEOUT_SECONDS = 30
"""Local engine ceiling; cold model loads need room, failures still hold."""

OLLAMA_KEEP_ALIVE = "5m"
"""Keep the decision model warm between asks (one daemon round trip)."""

OLLAMA_PREFLIGHT_TIMEOUT_SECONDS = 5
"""Per-GET ceiling for daemon preflight; the chain runs two per ask."""

DECISION_BODY_MAX_BYTES = 64 * 1024
"""Serialized decision-payload ceiling (the Ollama 64 KiB frame)."""

TRUNCATION_MARKER = "ask truncated to fit the decision cap"
"""Verdict-detail flag the hooks render as the truncation marker."""

_TOP_LEVEL_KEYS = {
    "candidates",
    "directives",
    "engine",
    "quiet",
    "tie_margin",
    "confidence_threshold",
}
_CANDIDATE_KEYS = {"id", "tier", "note", "levels", "benchmarks", "criteria"}
_BENCHMARK_KEYS = {"swe_verified", "lmarena_coding", "aa_index", "pulled"}
_ENGINE_KEYS = {
    "primary",
    "decision_model",
    "local_model",
    "local_base_url",
    "order",
    "native_model",
    "skip_notes",
}


@dataclass
class RoutingCandidate:
    """One routable model entry from the strategy file."""

    id: str
    tier: str | None = None
    note: str | None = None
    levels: list[str] | None = None
    benchmarks: dict[str, Any] | None = None
    criteria: str | None = None


@dataclass
class RoutingEngine:
    """Decision engine selection from the strategy file."""

    primary: str = "openrouter"
    decision_model: str | None = None
    local_model: str | None = None
    local_base_url: str | None = None
    order: list[str] | None = None
    native_model: str | None = None
    skip_notes: bool = True


@dataclass
class RoutingStrategy:
    """Parsed strategy: candidates + directives + engine + gate knobs."""

    candidates: list[RoutingCandidate] = field(default_factory=list)
    directives: str = ""
    engine: RoutingEngine = field(default_factory=RoutingEngine)
    quiet: bool = False
    tie_margin: float = DEFAULT_TIE_MARGIN
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    source: Path | None = None


@dataclass(frozen=True)
class RoutingPick:
    """One gated decision: model id + thinking level + confidences.

    ``model_confidence`` is the routed model's own table probability
    (the tie-break runner-up read when substituted, never the vendor
    confidence field); ``effort_confidence`` is the second call's
    top-1 level probability, None when no effort question ran (the
    lone level of a single-level pick rides through instead).
    """

    model: str
    effort: str
    model_confidence: float | None = None
    effort_confidence: float | None = None
    tie_break: bool = False


def default_global_strategy_path() -> Path:
    """Global strategy file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_STRATEGY_DIR_NAME)) / _STRATEGY_FILE_NAME


def default_repo_strategy_path() -> Path:
    """Repo strategy file path (cwd-anchored ``./.agent/routing.yaml``)."""
    return Path(os.getcwd()) / _REPO_STRATEGY_REL


def _candidate_skip_reason(entry: object, pos: int) -> str | None:
    """None when the entry parses; else the exact loader skip reason.

    Single source of truth for candidate validity: the loader warns
    with this reason and ``validate_strategy`` reports it, so the
    command shows exactly what the loader would do.
    """
    if not isinstance(entry, dict):
        return "not a mapping"
    unknown = set(entry) - _CANDIDATE_KEYS
    if unknown:
        return f"unknown keys: {sorted(unknown)}"
    candidate_id = entry.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return "missing id"
    tier = entry.get("tier")
    if tier is not None and not isinstance(tier, str):
        return "'tier' not a string"
    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        return "'note' not a string"
    levels = entry.get("levels")
    if levels is not None and (
        not isinstance(levels, list)
        or any(not isinstance(level, (str, bool)) for level in levels)
    ):
        return "'levels' not a string list"
    benchmarks = entry.get("benchmarks")
    if benchmarks is not None:
        if not isinstance(benchmarks, dict):
            return "'benchmarks' not a mapping"
        unknown_bench = set(benchmarks) - _BENCHMARK_KEYS
        if unknown_bench:
            return f"unknown benchmark keys: {sorted(unknown_bench)}"
    criteria = entry.get("criteria")
    if criteria is not None and not isinstance(criteria, str):
        return "'criteria' not a string"
    return None


def _parse_candidate(entry: object, pos: int) -> RoutingCandidate | None:
    """Normalize one candidate entry; warn and return None when untrusted."""
    reason = _candidate_skip_reason(entry, pos)
    if reason is not None:
        logger.warning("Ignoring routing candidate #%d (%s)", pos, reason)
        return None
    if not isinstance(entry, dict):  # unreachable: a None reason proves a dict
        return None
    levels = entry.get("levels")
    if levels is not None:
        # YAML 1.1 folds unquoted on/off to bools: honor the intent as level
        # strings so hand-edited strategies load as usable candidates
        # (mirrors the _parse_engine primary fold).
        levels = [
            "on" if level is True else "off" if level is False else level
            for level in levels
        ]
    benchmarks = entry.get("benchmarks")
    return RoutingCandidate(
        id=entry["id"],
        tier=entry.get("tier"),
        note=entry.get("note"),
        levels=list(levels) if levels is not None else None,
        benchmarks=dict(benchmarks) if benchmarks is not None else None,
        criteria=entry.get("criteria"),
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
    if engine.primary not in ("openrouter", "local", "off"):
        logger.warning(
            "Ignoring routing engine primary %r "
            "(expected openrouter|local|off); using openrouter",
            engine.primary,
        )
        engine.primary = "openrouter"
    order = raw.get("order")
    if order is not None:
        if not isinstance(order, list):
            logger.warning("Ignoring routing engine 'order' (not a list)")
        else:
            names: list[str] = []
            for entry in order:
                if entry not in ("native", "openrouter", "local"):
                    logger.warning(
                        "Ignoring unknown routing engine %r in 'order'", entry
                    )
                    continue
                if entry not in names:
                    names.append(entry)
            engine.order = names
    native_model = raw.get("native_model")
    if native_model is not None:
        if not isinstance(native_model, str):
            logger.warning("Ignoring routing engine 'native_model' (not a string)")
        else:
            engine.native_model = native_model
    skip_notes = raw.get("skip_notes", True)
    if not isinstance(skip_notes, bool):
        logger.warning("Ignoring routing engine 'skip_notes' (not true/false)")
    else:
        engine.skip_notes = skip_notes
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


def _parse_knob(value: object, name: str, default: float) -> float:
    """One gate knob: missing defaults silently, wrong warns and defaults.

    The loader stays fail-soft (routing keeps running on the default);
    ``validate_strategy`` is the strict judge that fails out-of-range
    knobs with a fix line.
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        logger.warning("Ignoring routing %r (not a number); using %s", name, default)
        return default
    number = float(value)
    if not 0.0 <= number <= 1.0:
        logger.warning(
            "Ignoring routing %r (%s outside 0..1); using %s", name, value, default
        )
        return default
    return number


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
        tie_margin=_parse_knob(data.get("tie_margin"), "tie_margin", DEFAULT_TIE_MARGIN),
        confidence_threshold=_parse_knob(
            data.get("confidence_threshold"),
            "confidence_threshold",
            DEFAULT_CONFIDENCE_THRESHOLD,
        ),
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


def _is_secret_shaped_key(key: object) -> bool:
    """True when a mapping key looks like a credential slot (T-08-10).

    Matches ``api_key`` in any case/separator spelling (``API_KEY``,
    ``api-key``, ``apikey``, ``apiKey``); anything matching is dropped
    on save so guided setup can never persist a key next to the
    strategy — keys stay runtime env per 08-01.
    """
    if not isinstance(key, str):
        return False
    folded = key.lower().replace("_", "").replace("-", "")
    return "apikey" in folded


def save_strategy(
    data: dict[str, Any],
    scope: str,
    *,
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> Path:
    """Write one guided-setup strategy atomically (D-13).

    ``scope`` selects the global file or the repo file (explicit path
    overrides exist for tests). The write is tmp-write plus
    ``os.replace`` with the parent dir at 0700 (the provider-config
    precedent); api_key-shaped keys are dropped with a warning at both
    the top level and inside ``engine`` (T-08-10).

    Raises:
        ValueError: On an unknown scope, a symlinked target, a
            pre-existing temp file, a non-mapping payload, or zero
            usable candidates (the setup flow guarantees at least
            one; this is the fail-loud backstop).
    """
    if not isinstance(data, dict):
        raise ValueError("Routing strategy must be a mapping")
    if scope == "global":
        resolved = (
            Path(global_path)
            if global_path is not None
            else default_global_strategy_path()
        )
    elif scope == "repo":
        resolved = (
            Path(repo_path) if repo_path is not None else default_repo_strategy_path()
        )
    else:
        raise ValueError(f"Unknown strategy scope {scope!r}: expected global|repo")
    if resolved.is_symlink():
        raise ValueError(f"Routing strategy must not be a symlink: {resolved}")
    payload: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_shaped_key(key):
            logger.warning(
                "Dropping secret-shaped routing key %r (keys stay runtime env)", key
            )
            continue
        if key == "engine" and isinstance(value, dict):
            cleaned = {
                entry_key: entry_value
                for entry_key, entry_value in value.items()
                if not _is_secret_shaped_key(entry_key)
            }
            for dropped in set(value) - set(cleaned):
                logger.warning(
                    "Dropping secret-shaped routing engine key %r"
                    " (keys stay runtime env)",
                    dropped,
                )
            payload[key] = cleaned
        else:
            payload[key] = value
    usable = 0
    raw_candidates = payload.get("candidates", [])
    if isinstance(raw_candidates, list):
        for pos, entry in enumerate(raw_candidates):
            if _parse_candidate(entry, pos) is not None:
                usable += 1
    if usable == 0:
        raise ValueError(
            "Refusing to write a routing strategy with zero usable candidates"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved.parent, 0o700)
    tmp = resolved.with_suffix(".yaml.tmp")
    if tmp.is_symlink() or tmp.exists():
        raise ValueError(f"Refusing to write through existing temp file: {tmp}")
    tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
    os.replace(tmp, resolved)
    return resolved


@dataclass
class ValidationReport:
    """One strategy validity judgment for ``/route validate``."""

    valid: bool
    source: Path | None
    lines: list[str] = field(default_factory=list)
    """Detail lines in display order: candidates, knobs, engine, directives."""

    def format(self) -> str:
        """Render the full report as the ``/route validate`` reply."""
        head = "Routing strategy VALID" if self.valid else "Routing strategy INVALID"
        source = str(self.source) if self.source is not None else "(no file)"
        return "\n".join([f"{head} — {source}"] + self.lines)


def _read_strategy_data(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Raw YAML mapping plus failure reason (None reason when absent-or-ok).

    Missing and empty files read as absent (None, None) — the loader
    falls through them; corrupt and non-mapping files read as broken
    with the loader's reason.
    """
    if not path.exists():
        return (None, None)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return (None, f"unreadable: {exc}")
    if data is None:
        return (None, None)
    if not isinstance(data, dict):
        return (None, "not a mapping")
    return (data, None)


def _candidate_fix(reason: str, pos: int) -> str:
    """Manual-edit fix line for one loader skip reason."""
    if reason == "not a mapping":
        return f"make candidates[{pos}] a mapping like {{id: provider/model}}"
    if reason.startswith("unknown keys:"):
        return (
            f"remove the unknown keys from candidates[{pos}] "
            "(allowed: id, tier, note, levels, benchmarks, criteria)"
        )
    if reason == "missing id":
        return f"add id: <provider/model> to candidates[{pos}]"
    if reason == "'tier' not a string":
        return f"make candidates[{pos}].tier a string"
    if reason == "'note' not a string":
        return f"make candidates[{pos}].note a string"
    if reason == "'levels' not a string list":
        return f"make candidates[{pos}].levels a list like [low, high]"
    if reason == "'benchmarks' not a mapping":
        return f"make candidates[{pos}].benchmarks a mapping"
    if reason.startswith("unknown benchmark keys:"):
        return (
            f"remove the unknown keys from candidates[{pos}].benchmarks "
            "(allowed: swe_verified, lmarena_coding, aa_index, pulled)"
        )
    if reason == "'criteria' not a string":
        return f"make candidates[{pos}].criteria a string"
    return f"repair candidates[{pos}] ({reason})"


def _cached_decision_ids() -> set[str] | None:
    """Decisions-catalog ids from the disk cache only (None when absent).

    Never fetches: validate judges the real file against cached entries
    only and must report without network (D-13).
    """
    from strands_code_cli.live_pricing import cached_tables

    try:
        tables = cached_tables()
    except Exception:
        return None
    decisions = tables.get("decisions")
    if not isinstance(decisions, dict):
        return None
    models = decisions.get("models")
    if not isinstance(models, dict):
        return None
    return {key for key in models if isinstance(key, str)}


def _bare_catalog_id(model_id: str) -> str:
    """Strip an aggregator prefix for the cached-catalog membership check."""
    lowered = model_id.lower()
    for prefix in ("litellm/openrouter/", "openrouter/"):
        if lowered.startswith(prefix):
            return model_id[len(prefix) :]
    return model_id


def _catalog_known(model_id: str, catalog: set[str]) -> bool:
    """True when the id is catalog-known verbatim or prefix-stripped.

    Verbatim wins: genuine catalog ids can start with ``openrouter/``
    (e.g. ``openrouter/auto``), so stripping first would mangle them
    (UAT R1). The stripped form stays as a fallback for aggregator
    routes like ``litellm/openrouter/<id>``.
    """
    return model_id in catalog or _bare_catalog_id(model_id) in catalog


def validate_strategy(
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> ValidationReport:
    """Judge the winning strategy file without network, writes, or engines.

    Mirrors ``load_strategy`` precedence (repo wins whole-file, broken
    files fall back with a note) and reports the winning source, one
    line per candidate (ok or the exact loader skip reason), the
    26-candidate cap, the effective gate knobs (explicit or default),
    engine checks with the decision model looked up in the cached
    decisions catalog only (unchecked when the cache is unreachable),
    and the directives presence note. Every failure class carries a
    manual-edit fix.
    """
    repo = Path(repo_path) if repo_path is not None else default_repo_strategy_path()
    home = (
        Path(global_path) if global_path is not None else default_global_strategy_path()
    )
    for path in (repo, home):
        if path.is_symlink():
            return ValidationReport(
                valid=False,
                source=None,
                lines=[
                    f"strategy path is a symlink: {path}",
                    "fix: replace the symlink with a real file",
                ],
            )
    repo_data, repo_reason = _read_strategy_data(repo)
    home_data, home_reason = _read_strategy_data(home)
    if repo_data is not None:
        data, source = repo_data, repo
        fallback: str | None = None
    elif home_data is not None:
        data, source = home_data, home
        fallback = (
            f"note: repo strategy {repo} is {repo_reason} "
            "(using the global file instead) — fix the repo file or delete it"
            if repo_reason is not None
            else None
        )
    else:
        lines = []
        if repo_reason is not None:
            lines.append(f"repo strategy {repo} is {repo_reason}")
            lines.append(
                "fix: repair the YAML or delete the file and re-run /route setup"
            )
        if home_reason is not None:
            lines.append(f"global strategy {home} is {home_reason}")
            lines.append(
                "fix: repair the YAML or delete the file and re-run /route setup"
            )
        if not lines:
            lines.append("no strategy file found")
            lines.append("fix: run /route setup to create one")
        return ValidationReport(valid=False, source=None, lines=lines)
    lines = [fallback] if fallback is not None else []
    valid = True
    unknown_top = set(data) - _TOP_LEVEL_KEYS
    if unknown_top:
        lines.append(
            f"note: unknown top-level keys ignored: {sorted(unknown_top)} "
            "(the loader warns and continues)"
        )
    raw_candidates: object = data.get("candidates", [])
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        valid = False
        lines.append("candidates: INVALID — not a list (the loader ignores it)")
        lines.append("fix: make candidates: a list of {id: ...} entries")
    else:
        usable = 0
        for pos, entry in enumerate(raw_candidates):
            reason = _candidate_skip_reason(entry, pos)
            if reason is None:
                usable += 1
                lines.append(f"candidate #{pos} {entry['id']}: ok")
            else:
                valid = False
                lines.append(f"candidate #{pos}: SKIP — {reason}")
                lines.append(f"fix: {_candidate_fix(reason, pos)}")
        if len(raw_candidates) > MAX_CANDIDATES:
            valid = False
            lines.append(
                f"candidates: INVALID — {len(raw_candidates)} entries "
                f"exceeds the {MAX_CANDIDATES}-candidate cap"
            )
            lines.append(
                f"fix: keep at most {MAX_CANDIDATES} candidates "
                "(the choice call caps at 26 options)"
            )
        if usable == 0:
            valid = False
            lines.append("no usable candidates — routing stays off")
            lines.append(
                "fix: add at least one candidates entry with a model id, "
                "or re-run /route setup"
            )
    for knob, default in (
        ("tie_margin", DEFAULT_TIE_MARGIN),
        ("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD),
    ):
        raw_knob = data.get(knob)
        if raw_knob is None:
            lines.append(f"{knob}: {default} (default)")
        elif isinstance(raw_knob, bool) or not isinstance(raw_knob, (int, float)):
            valid = False
            lines.append(f"{knob}: INVALID — {raw_knob!r} is not a number")
            lines.append(f"fix: set {knob} to a number between 0 and 1")
        elif not 0.0 <= float(raw_knob) <= 1.0:
            valid = False
            lines.append(f"{knob}: INVALID — {raw_knob} is outside 0..1")
            lines.append(f"fix: set {knob} to a number between 0 and 1")
        else:
            lines.append(f"{knob}: {float(raw_knob)}")
    engine = _parse_engine(data.get("engine"))
    raw_engine = data.get("engine")
    raw_primary = raw_engine.get("primary") if isinstance(raw_engine, dict) else None
    if isinstance(raw_primary, str) and raw_primary not in (
        "openrouter",
        "local",
        "off",
    ):
        valid = False
        lines.append(f"engine: INVALID — unknown primary {raw_primary!r}")
        lines.append("fix: set engine.primary to openrouter|local|off")
    raw_base_url = (
        raw_engine.get("local_base_url") if isinstance(raw_engine, dict) else None
    )
    if (
        isinstance(raw_base_url, str)
        and raw_base_url.strip()
        and not _valid_base_url(raw_base_url)
    ):
        valid = False
        lines.append(
            f"engine: INVALID — local_base_url {raw_base_url!r} "
            "is not an http/https URL"
        )
        lines.append("fix: set engine.local_base_url to an http(s) URL or remove it")
    if engine.primary == "off":
        lines.append("engine: primary off — routing disabled by config")
    elif engine.primary == "local":
        if not engine.local_model:
            valid = False
            lines.append("engine: INVALID — primary is local with no local_model")
            lines.append(
                "fix: set engine.local_model to your Ollama tag, "
                "or switch primary to openrouter"
            )
        else:
            lines.append(f"engine: primary local, model {engine.local_model} — ok")
        if engine.decision_model:
            lines.append(
                f"engine: decision model {engine.decision_model} "
                "(unused while primary is local)"
            )
        else:
            lines.append("engine: no decision model (unused while primary is local)")
    else:
        if not engine.decision_model:
            valid = False
            lines.append(
                f"engine: INVALID — primary is {engine.primary} "
                "with no decision_model"
            )
            lines.append(
                "fix: set engine.decision_model to a decisions-catalog id, "
                "or re-run /route setup"
            )
        else:
            catalog = _cached_decision_ids()
            if catalog is None:
                lines.append(
                    f"engine: decision model {engine.decision_model} — unchecked "
                    "(no cached decisions catalog; run /cost refresh, then re-validate)"
                )
            elif _catalog_known(engine.decision_model, catalog):
                lines.append(
                    f"engine: decision model {engine.decision_model} — "
                    "known in the cached decisions catalog"
                )
            else:
                valid = False
                lines.append(
                    f"engine: INVALID — decision model {engine.decision_model} "
                    "not in the cached decisions catalog"
                )
                lines.append(
                    "fix: pick a live id from the decisions listing "
                    "(re-run /route setup), then /cost refresh and re-validate"
                )
    directives = data.get("directives", "")
    if directives is None:
        directives = ""
    if not isinstance(directives, str):
        lines.append("note: directives is not a string (the loader ignores it)")
    elif directives.strip():
        lines.append(f"directives: present ({len(directives)} chars)")
        if len(directives) > 4096:
            lines.append(
                "warning: directives exceed ~4K chars — they ride every "
                "decision call twice, so trim for cost and accuracy"
            )
    else:
        lines.append("note: no directives — the decider picks without guidance")
    return ValidationReport(valid=valid, source=source, lines=lines)


_MODEL_INSTRUCTIONS_BASE = (
    "Which candidate model should serve the ask in `ask`? "
    "Judge the ask, not its length. "
)


def build_decision_state(*, ask: str, directives: str, side: bool) -> dict[str, Any]:
    """Build the Decision-API state for one ask (T-08-23).

    Ask plus directives plus the side flag only — no history, tool
    results, file contents, or candidate stats. Ask and directives are
    each truncated to ASK_TRUNCATE_CHARS so a malicious repo strategy
    file cannot inject unbounded text into the paid decision call.
    """
    return {
        "ask": ask[:ASK_TRUNCATE_CHARS],
        "directives": directives[:ASK_TRUNCATE_CHARS] if directives else "",
        "side": side,
    }


def _criteria_text(candidate: RoutingCandidate) -> str:
    """One criteria prose line: criteria, else note, tier, or the id.

    The option name describing itself is the last resort (the Clef
    ``criteria: null`` precedent); blank strings count as missing.
    """
    for field in (candidate.criteria, candidate.note, candidate.tier):
        if isinstance(field, str) and field.strip():
            return field
    return candidate.id


def build_model_question(
    *, candidates: list[RoutingCandidate], directives: str
) -> dict[str, Any]:
    """Build the pick_model choice question (D-02, D-07).

    Criteria map each candidate id to its criteria prose; directives
    append to the instructions so they shape the judgment directly.
    Prices, windows, and benchmarks never enter the call — decision
    models do no quantities, so they stay code-side (the tie-break
    reads the almanac instead). No ``none`` criterion: below-threshold
    tables hold code-side (D-16).
    """
    shaped = directives[:ASK_TRUNCATE_CHARS] if directives else ""
    return {
        "type": "choice",
        "instructions": _MODEL_INSTRUCTIONS_BASE + shaped,
        "criteria": {
            candidate.id: _criteria_text(candidate) for candidate in candidates
        },
    }


_EFFORT_CRITERIA = {
    "auto": "Let the model decide how much thinking this ask needs",
    "off": "Answer directly with no thinking budget",
    "minimal": "Minimal thinking for trivial asks answerable at a glance",
    "low": "Light thinking for simple asks with a clear answer",
    "medium": "Moderate thinking for everyday implementation and debugging",
    "high": "Deep thinking for complex refactors and multi-step work",
    "xhigh": "Extended thinking for the hardest asks needing careful reasoning",
    "max": "Maximum thinking budget for the most demanding asks",
}
"""Fixed code-side prose per known effort level (the harness Effort set).

Unknown levels fall back to the bare level name, never operator
prose — the map is code, not strategy text (T-08-26).
"""


def build_effort_question(
    *, candidate: RoutingCandidate, directives: str
) -> dict[str, Any]:
    """Build the pick_effort choice question over one candidate (D-05, D-15).

    Criteria cover exactly the picked candidate's advertised levels —
    the second call judges only levels the pick can serve. Directives
    append to the instructions so they shape the effort judgment like
    the model one (D-07).
    """
    shaped = directives[:ASK_TRUNCATE_CHARS] if directives else ""
    return {
        "type": "choice",
        "instructions": (
            f"How much thinking budget does the ask in `ask` need "
            f"on {candidate.id}? "
            "Judge the ask, not its length. " + shaped
        ),
        "criteria": {
            level: _EFFORT_CRITERIA.get(level, level)
            for level in candidate.levels or []
        },
    }


@dataclass(frozen=True)
class EngineResult:
    """One engine try: typed answers plus usage triple plus snapshot.

    ``answers`` is None on any failure (no key, network, timeout,
    malformed payload); the token counts come from the engine
    response usage fields and default to zeros when absent, ``cost``
    carries the reported USD spend (None when the shape omits it, as
    local calls do), and ``model`` names the dated snapshot that
    served the request for drift tracing. ``error`` names the short
    failure class (``unready`` for a skipped local link, HTTP and
    transport classes otherwise); None means no information, which
    the verdict renders as the legacy ``<engine> failed`` detail.
    ``truncated`` reports that the transport shrank the ask to fit
    the body cap; the verdict carries the marker on its detail.
    """

    answers: dict[str, Any] | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None
    model: str | None = None
    error: str | None = None
    truncated: bool = False


def _count(value: object) -> int:
    """Best-effort non-negative int for a usage field (bool-safe)."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _cost(value: object) -> float | None:
    """Reported USD spend verbatim (None when absent or non-numeric)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _retryable_error(exc: BaseException) -> bool:
    """True for the one-retry class: retryable codes plus timeouts.

    4xx, refused connections, and malformed bodies hold immediately —
    retrying the same call cannot help (T-08-24).
    """
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRYABLE_STATUS
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, TimeoutError)
    return False


_CONNECTION_ERRORS = frozenset({"refused", "unreachable"})
"""Failure classes that pause routing when they take every link (D-09)."""


def _refused_reason(reason: object) -> bool:
    """True when a transport reason is a refused connection (errno 111)."""
    import errno

    if isinstance(reason, TimeoutError):
        return False
    if isinstance(reason, ConnectionRefusedError):
        return True
    return (
        isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
    )


def _failure_reason(exc: BaseException) -> str:
    """Short failure class for one transport exception (never secrets).

    ``HTTP <code>`` for HTTP errors, ``timeout`` for timeouts,
    ``refused``/``unreachable`` for connection-level failures,
    ``invalid body`` for undecodable 200s — ``json`` and ``utf-8``
    decode errors are both ``ValueError``.
    """
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            return "timeout"
        if _refused_reason(reason):
            return "refused"
        return "unreachable"
    if isinstance(exc, (ConnectionError, OSError)):
        if _refused_reason(exc):
            return "refused"
        return "unreachable"
    if isinstance(exc, ValueError):
        return "invalid body"
    return "error"


def _fit_decision_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Shrink state.ask until the serialized body fits the 64 KiB cap.

    Returns the (possibly copied) payload plus whether the ask
    shrank. Only the ask tightens — directives and criteria ride as
    built; when the ask alone cannot absorb the overshoot the
    shrunken body still ships and the server judges (an Ollama 413
    holds with the engine-plus-code detail).
    """
    body = json.dumps(payload).encode("utf-8")
    if len(body) <= DECISION_BODY_MAX_BYTES:
        return payload, False
    state = payload.get("state")
    if not isinstance(state, dict):
        return payload, False
    ask = state.get("ask")
    if not isinstance(ask, str) or not ask:
        return payload, False
    over = len(body) - DECISION_BODY_MAX_BYTES
    ask = ask[: max(0, len(ask) - over - 16)]
    shrunk = dict(payload)
    shrunk["state"] = {**state, "ask": ask}
    while ask and len(json.dumps(shrunk).encode("utf-8")) > DECISION_BODY_MAX_BYTES:
        ask = ask[: len(ask) // 2]
        shrunk["state"] = {**state, "ask": ask}
    return shrunk, True


def _with_truncation(detail: str, truncated: bool) -> str:
    """Append the truncation marker once when the payload shrank."""
    if not truncated or TRUNCATION_MARKER in detail:
        return detail
    return f"{detail}; {TRUNCATION_MARKER}" if detail else TRUNCATION_MARKER


def _post_decision(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> tuple[dict[str, Any] | None, str | None]:
    """POST one Decision-API request; (parsed mapping, failure class).

    Returns ``(data, None)`` on a well-shaped 200 and ``(None,
    reason)`` otherwise. Retries at most once on retryable codes and
    timeouts, never on 4xx or schema failures — a wrong-shaped 200 is
    its own outcome, never a reason to re-ask. Shared by both
    engines (T-08-24).
    """
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    for attempt_no in range(2):
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — every failure class holds
            if attempt_no == 0 and _retryable_error(exc):
                continue
            return None, _failure_reason(exc)
        if not isinstance(data, dict):
            return None, "invalid body"
        return data, None
    return None, "unreachable"  # unreachable: the loop always returns first


def decide_via_openrouter(
    *,
    decision_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via the OpenRouter Decisions API (T-08-22).

    The ``OPENROUTER_API_KEY`` is read at call time inside this engine
    function only (runtime-supplied credential, never persisted, sent
    header-only, never logged — the harness ``OLLAMA_API_KEY``
    precedent). Any failure (no key, network, timeout, malformed
    payload) yields an answers-None result and the chain tries the
    next engine. Usage carries the reported input/output tokens plus
    the reported USD cost (input-tokens-only billing, free outputs).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not decision_model:
        return EngineResult(answers=None)
    payload, truncated = _fit_decision_payload(
        {"model": decision_model, "state": state, "questions": questions}
    )
    data, error = _post_decision(
        OPENROUTER_DECISIONS_URL,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
        timeout,
    )
    if data is None:
        return EngineResult(answers=None, error=error, truncated=truncated)
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return EngineResult(
            answers=None, error="invalid body", truncated=truncated
        )
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    model = data.get("model")
    return EngineResult(
        answers=answers,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cost=_cost(usage.get("cost")),
        model=model if isinstance(model, str) else None,
        truncated=truncated,
    )


def decide_via_typesafe(
    *,
    native_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via the native TypeSafe Decisions API.

    The ``TYPESAFE_API_KEY`` is read at call time inside this engine
    function only (runtime-supplied credential, never persisted, sent
    header-only, never logged — the ``OPENROUTER_API_KEY``
    precedent). Any failure (no key, network, timeout, malformed
    payload) yields an answers-None result and the chain tries the
    next engine. Usage carries the reported input/output tokens;
    native usage never reports spend, so cost is computed code-side
    from the reported input tokens at the published flat input-only
    rate (output tokens are free).
    """
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key or not native_model:
        return EngineResult(answers=None)
    payload, truncated = _fit_decision_payload(
        {"model": native_model, "state": state, "questions": questions}
    )
    data, error = _post_decision(
        TYPESAFE_DECISIONS_URL,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        },
        timeout,
    )
    if data is None:
        return EngineResult(answers=None, error=error, truncated=truncated)
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return EngineResult(
            answers=None, error="invalid body", truncated=truncated
        )
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    model = data.get("model")
    in_tok = _count(usage.get("input_tokens"))
    return EngineResult(
        answers=answers,
        input_tokens=in_tok,
        output_tokens=_count(usage.get("output_tokens")),
        cost=in_tok * TYPESAFE_INPUT_USD_PER_MTOK / 1_000_000,
        model=model if isinstance(model, str) else None,
        truncated=truncated,
    )


_OLLAMA_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
"""Hosts that never carry key material (T-08-06)."""


def _ollama_base(local_base_url: str | None) -> str:
    """Daemon root: strategy URL, else the harness host, else loopback."""
    return local_base_url or os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST


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


def _preflight_get(url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """One daemon preflight GET: parsed mapping or None on any failure."""
    import urllib.request

    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(
            request, timeout=OLLAMA_PREFLIGHT_TIMEOUT_SECONDS
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — every preflight failure reads unready
        return None
    return data if isinstance(data, dict) else None


def _version_tuple(text: object) -> tuple[int, ...] | None:
    """Dotted version to ints; None when unparseable (fail closed)."""
    if not isinstance(text, str) or not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def local_engine_ready(base: str, tag: str) -> bool:
    """True when the Ollama daemon meets the floor and has the tag pulled.

    Probes GET ``<base>/api/version`` for the 0.35 floor (0.35.1 for
    tags starting with ``clef``) and GET ``<base>/api/tags`` for the
    tag (exact or ``:latest``-suffixed daemon names match). Any
    transport or parse failure returns False without raising — the
    chain treats unready as skip, never as ready (T-08-30).
    """
    if not base or not tag:
        return False
    root = base.rstrip("/")
    version = _preflight_get(f"{root}/api/version", _ollama_headers(base))
    if version is None:
        return False
    parsed = _version_tuple(version.get("version"))
    if parsed is None:
        return False
    floor = (0, 35, 1) if tag.startswith("clef") else (0, 35)
    if parsed < floor:
        return False
    tags = _preflight_get(f"{root}/api/tags", _ollama_headers(base))
    if tags is None:
        return False
    models = tags.get("models")
    if not isinstance(models, list):
        return False
    names = {
        model["name"]
        for model in models
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    if tag in names:
        return True
    bare = {
        name[: -len(":latest")] if name.endswith(":latest") else name
        for name in names
    }
    return tag in bare


def decide_via_ollama(
    *,
    local_model: str,
    local_base_url: str | None = None,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via Ollama System One (``/v1/systemone``).

    The base URL resolves strategy-first, then the harness
    ``OLLAMA_HOST`` default; only http/https addresses with a host are
    called (T-08-25). Decision models must never run through
    ``/api/chat`` (filler-token runaway). The local usage shape
    carries no cost, so spend records as None (rendered as zero, never
    estimated). Any failure yields an answers-None result — offline
    with no daemon simply holds current (D-09).
    """
    if not local_model:
        return EngineResult(answers=None)
    base = _ollama_base(local_base_url)
    if not _valid_base_url(base):
        return EngineResult(answers=None)
    payload, truncated = _fit_decision_payload(
        {
            "model": local_model,
            "state": state,
            "questions": questions,
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
    )
    data, error = _post_decision(
        f"{base.rstrip('/')}/v1/systemone",
        payload,
        _ollama_headers(base),
        timeout,
    )
    if data is None:
        return EngineResult(answers=None, error=error, truncated=truncated)
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return EngineResult(
            answers=None, error="invalid body", truncated=truncated
        )
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    model = data.get("model")
    return EngineResult(
        answers=answers,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cost=None,
        model=model if isinstance(model, str) else None,
        truncated=truncated,
    )


def _validate_choice_shape(answer: object) -> dict[str, Any] | None:
    """Typed shape check shared by both decision calls; None holds.

    The answer must be a dict with ``type`` exactly ``choice``, a
    non-empty ``probabilities`` mapping of 0..1 numbers summing to 1
    within 1e-6, and a ``choice`` sitting in the table. Membership in
    the live option set is judged separately per call (candidates for
    call 1, advertised levels via ``validate_routed_effort`` for
    call 2).
    """
    if not isinstance(answer, dict):
        return None
    if answer.get("type") != "choice":
        return None
    probs = answer.get("probabilities")
    if not isinstance(probs, dict) or not probs:
        return None
    for prob in probs.values():
        if isinstance(prob, bool) or not isinstance(prob, (int, float)):
            return None
        if not 0.0 <= prob <= 1.0:
            return None
    if abs(sum(probs.values()) - 1.0) > 1e-6:
        return None
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in probs:
        return None
    return answer


def validate_choice_answer(
    answer: object, candidates: list[RoutingCandidate]
) -> dict[str, Any] | None:
    """Validate one typed choice answer; None holds the current model.

    The answer must pass the shape check plus name a ``choice`` that
    sits in the live candidate ids (a stale pick after a strategy
    edit must never route — no normalization, no fuzzy match). The
    vendor ``confidence`` field may be absent; it is logged, never
    gated on (T-08-21).
    """
    answer = _validate_choice_shape(answer)
    if answer is None:
        return None
    live = {candidate.id for candidate in candidates}
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in live:
        return None
    return answer


def _validate_effort_answer(answer: object) -> dict[str, float] | None:
    """Validate one effort table; the probability mapping or None.

    Shape only — level membership is judged downstream by
    ``validate_routed_effort`` so an outside-level read holds with
    its unsupported-effort detail instead of a bare engine failure.
    """
    answer = _validate_choice_shape(answer)
    if answer is None:
        return None
    return answer["probabilities"]


def _price_total(model_id: str) -> float | None:
    """Almanac in+out price for one id (None when unpriced — D-14)."""
    try:
        prices = price_for(model_id)
    except Exception:
        return None
    if prices is None:
        return None
    return prices[0] + prices[1]


def gate_model(
    answer: dict[str, Any], strategy: RoutingStrategy
) -> tuple[str | None, bool, str]:
    """Gate one validated model table: (model|None, tie_break, detail).

    Below-threshold top-1 probabilities hold (D-16); near-tie top-two
    gaps route the cheaper candidate per almanac prices with a detail
    note (D-14). The gate reads the probability table only — never
    the vendor confidence field (Pitfall 1) and never the ``choice``
    field (the argmax is the source of truth). Unpriced or
    equal-priced pairs keep the argmax with no tie marker.
    """
    ranked = sorted(
        answer["probabilities"].items(), key=lambda item: (-item[1], item[0])
    )
    top, top_prob = ranked[0]
    if top_prob < strategy.confidence_threshold:
        return (
            None,
            False,
            f"confidence {top_prob:.0%} < {strategy.confidence_threshold:.0%}",
        )
    if len(ranked) == 1:
        return (top, False, "")
    second, second_prob = ranked[1]
    if top_prob - second_prob > strategy.tie_margin:
        return (top, False, "")
    top_price = _price_total(top)
    second_price = _price_total(second)
    if (
        top_price is None
        or second_price is None
        or second_price >= top_price
    ):
        return (top, False, "")
    return (
        second,
        True,
        f"tie {top_prob:.0%} vs {second_prob:.0%} → {second} (cheaper)",
    )


EngineAttempt = Callable[
    [RoutingStrategy, dict[str, Any], dict[str, Any]], EngineResult | None
]
"""One engine try: (strategy, state, questions) -> result or None when skipped."""

_ENGINE_REGISTRY: list[tuple[str, EngineAttempt]] = []
"""Ordered engine chain; each engine is tried once per ask."""


def register_engine(name: str, attempt: EngineAttempt) -> None:
    """Append one named engine to the chain (openrouter, local, native)."""
    _ENGINE_REGISTRY.append((name, attempt))


def _openrouter_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """OpenRouter chain link: None without a configured decision model."""
    decision_model = strategy.engine.decision_model
    if not decision_model:
        return None
    return decide_via_openrouter(
        decision_model=decision_model, state=state, questions=questions
    )


def _ollama_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """Local chain link: None without a configured local model (skipped)."""
    local_model = strategy.engine.local_model
    if not local_model:
        return None
    return decide_via_ollama(
        local_model=local_model,
        local_base_url=strategy.engine.local_base_url,
        state=state,
        questions=questions,
    )


def _typesafe_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """Native chain link: None without a configured native model."""
    native_model = strategy.engine.native_model
    if not native_model:
        return None
    return decide_via_typesafe(
        native_model=native_model, state=state, questions=questions
    )


def _local_unready_attempt(
    _strategy: RoutingStrategy, _state: dict[str, Any], _questions: dict[str, Any]
) -> EngineResult:
    """Inert local link: an unready daemon skips with zero POSTs.

    Offered by :func:`_chain_for` when :func:`local_engine_ready`
    fails — version below the floor, tag not pulled, or preflight
    unreachable — so the verdict carries the distinct unready detail
    instead of a transport failure.
    """
    return EngineResult(answers=None, error="unready")


register_engine("openrouter", _openrouter_attempt)
register_engine("local", _ollama_attempt)
register_engine("native", _typesafe_attempt)


def _link_detail(name: str, error: str | None) -> str:
    """Verdict detail for one failed link: engine plus cause.

    Unready skips name the preflight cause; HTTP failures name engine
    plus code; timeouts, refusals, and unreachable hosts name engine
    plus class; schema misses name the validation failure. Links
    without failure information keep the legacy ``<engine> failed``
    shape (byte-identical for missing-key and decide-level holds).
    """
    if error == "unready":
        return f"{name} unready (daemon version or tag not ready)"
    if error is not None and error.startswith("HTTP "):
        return f"{name} {error[len('HTTP '):]}"
    if error in ("timeout", "refused", "unreachable"):
        return f"{name} {error}"
    if error in ("invalid body", "invalid table"):
        return f"{name} {error}"
    return f"{name} failed"


def _pause_detail(down: list[str]) -> str:
    """Distinct pause detail naming every unreachable link (D-09)."""
    return f"paused: all engines unreachable ({', '.join(down)})"


def is_pause_detail(detail: str) -> bool:
    """True when a verdict detail pauses routing for the ask (D-09)."""
    return detail.startswith("paused:")


_LEGACY_PRIMARY_ORDER = {
    "openrouter": ["openrouter", "local"],
    "local": ["local"],
    "off": [],
}
"""Legacy primary values mapped to their equivalent engine order (D-01)."""


def _effective_order(engine: RoutingEngine) -> list[str]:
    """Engine order for one strategy: explicit order or legacy mapping.

    An explicit ``order`` drives the chain as listed; None means a
    legacy file, so ``primary`` maps to its equivalent order
    (openrouter-then-local, local-only, or empty for off).
    """
    if engine.order is not None:
        return list(engine.order)
    return list(
        _LEGACY_PRIMARY_ORDER.get(
            engine.primary or "openrouter", ["openrouter", "local"]
        )
    )


def _chain_for(strategy: RoutingStrategy) -> list[tuple[str, EngineAttempt]]:
    """Engine links for one strategy: order drives, unconfigured skips.

    The effective order lists the links in try order; an empty order
    tries nothing — the load layer already yields None for legacy
    off, and a directly built off strategy (or an explicit empty
    order) degrades the same way here. The local link is skipped,
    not failed, when no local model configures, and consults
    :func:`local_engine_ready` before it is offered: an unready
    daemon yields the inert unready link (zero POSTs, distinct
    detail) instead of a doomed decision call.
    """
    names = _effective_order(strategy.engine)
    by_name = dict(_ENGINE_REGISTRY)
    chain: list[tuple[str, EngineAttempt]] = []
    for name in names:
        if name == "local":
            if not strategy.engine.local_model:
                continue
            base = _ollama_base(strategy.engine.local_base_url)
            if not local_engine_ready(base, strategy.engine.local_model):
                chain.append((name, _local_unready_attempt))
                continue
        attempt = by_name.get(name)
        if attempt is not None:
            chain.append((name, attempt))
    return chain


def _merge_cost(first: float | None, second: float | None) -> float | None:
    """Summed reported spend; None only when both calls omit cost."""
    if first is None and second is None:
        return None
    return (first if first is not None else 0.0) + (
        second if second is not None else 0.0
    )


def _decide_effort(
    strategy: RoutingStrategy,
    candidate: RoutingCandidate,
    state: dict[str, Any],
    chain: list[tuple[str, EngineAttempt]],
) -> tuple[str | None, float | None, tuple[int, int, float | None], str, str, bool]:
    """Second sequential choice over the picked levels (D-15).

    Runs the pick_effort question through the same engine chain on
    the same state — never parallel with call 1, whose answer scopes
    the criteria. Returns ``(effort, confidence, usage, engine,
    detail, truncated)`` with the top choice taken ungated (a weak
    effort read still routes, D-16); a None effort holds the ask,
    since a failed or unparseable effort read carries no level to
    route. The detail mirrors call 1 (engine plus cause, pause when
    every link went down at connection level); ``truncated`` ORs
    every attempted call so the verdict flags a shrunken payload.
    """
    questions = {
        "pick_effort": build_effort_question(
            candidate=candidate, directives=strategy.directives
        )
    }
    order = _effective_order(strategy.engine)
    failed = chain[0][0] if chain else (order[0] if order else "off")
    detail = f"{failed} failed"
    down: list[str] = []
    informative = False
    truncated = False
    for name, attempt in chain:
        try:
            result = attempt(strategy, state, questions)
        except Exception:
            result = None
        if result is None:
            continue  # skipped link: unconfigured, never attempted
        truncated = truncated or result.truncated
        if result.answers is None:
            failed, detail = name, _link_detail(name, result.error)
            if result.error in _CONNECTION_ERRORS:
                down.append(name)
            elif result.error not in (None, "unready"):
                # Skipped and unready links are pause-neutral: never
                # attempted, so only attempted failures judge the pause.
                informative = True
            continue
        if result.model:
            logger.debug(
                "Routing effort decision via %s served by %s", name, result.model
            )
        table = _validate_effort_answer(result.answers.get("pick_effort"))
        if table is None:
            failed, detail = name, _link_detail(name, "invalid table")
            informative = True
            continue
        ranked = sorted(table.items(), key=lambda item: (-item[1], item[0]))
        top, top_prob = ranked[0]
        return (
            top,
            float(top_prob),
            (result.input_tokens, result.output_tokens, result.cost),
            name,
            "",
            truncated,
        )
    if down and not informative:
        return (None, None, (0, 0, None), down[-1], _pause_detail(down), truncated)
    return (None, None, (0, 0, None), failed, detail, truncated)


def decide(
    strategy: RoutingStrategy,
    *,
    current_model: str,
    side: bool = False,
    ask: str,
) -> tuple[RoutingPick | None, str, tuple[int, int, float | None], str]:
    """Route one ask: state build, engine chain, validate, gate.

    Returns ``(pick, engine, usage, detail)`` where engine names the
    model-decision engine on success and the last attempted engine on
    hold, usage sums both decision calls into one ``(input, output,
    reported cost)`` triple (zeros plus None on hold), and detail
    feeds the hold/route notes (empty on a clean route). Total
    failure — every engine down or schema-invalid — yields a None
    pick and the caller holds current (D-08). One chain pass per
    call; each engine retries at most once on retryable failures
    only. Connection-level failure on every attempted link pauses
    routing for the ask with a distinct pause detail (D-09); other
    holds name engine plus cause. When either call shrank the ask to
    fit the body cap, the detail carries the truncation marker.

    A below-threshold table holds immediately without trying the next
    engine: the ask itself is ambiguous, so the retry happens next
    ask (D-16). Past the gate, a second sequential call chooses the
    thinking level over only the picked candidate's levels, and the
    top choice routes ungated with its probability recorded as
    effort_confidence; the level then passes ``validate_routed_effort``
    on the switch path. Same-model picks skip that validation (the
    no-op fast path wins: the hook applies no switch and no effort,
    so there is nothing to judge). A single-level pick skips the
    second call — nothing to choose, and a one-option question
    violates the 2-26 floor — so the lone level rides through with
    effort_confidence None.

    A single candidate skips the model call but still asks the
    effort question over the lone candidate's levels (D-15): the
    verdict carries the decided level with model_confidence None, no
    tie marker, and call-2-only usage. A lone single-level candidate
    is fully degenerate — nothing to choose at either stage — so the
    lone level rides through with no decision call. A lone candidate
    with no levels holds with no engine call: a one-option choice is
    invalid (2-26) and there is no effort to pass through.
    """
    if _effective_order(strategy.engine) and len(strategy.candidates) == 1:
        only = strategy.candidates[0]
        if not only.levels:
            return (
                None,
                "none",
                (0, 0, None),
                "only candidate advertises no levels",
            )
        if len(only.levels) == 1:
            # Fully degenerate: no model choice and no effort choice —
            # the lone level rides through with no decision call.
            fast = RoutingPick(
                model=only.id,
                effort=only.levels[0],
                model_confidence=None,
                effort_confidence=None,
                tie_break=False,
            )
            if only.id != current_model and not validate_routed_effort(
                fast, strategy.candidates
            ):
                return (
                    None,
                    "none",
                    (0, 0, None),
                    f"effort {only.levels[0]!r} unsupported by {only.id}",
                )
            return (fast, "none", (0, 0, None), "")
        state = build_decision_state(
            ask=ask, directives=strategy.directives, side=side
        )
        chain = _chain_for(strategy)
        if not chain:
            order = _effective_order(strategy.engine)
            head = order[0] if order else "off"
            return (None, head, (0, 0, None), f"{head} failed")
        (
            effort,
            effort_confidence,
            usage,
            name,
            effort_detail,
            effort_truncated,
        ) = _decide_effort(strategy, only, state, chain)
        if effort is None:
            return (
                None,
                name,
                (0, 0, None),
                _with_truncation(effort_detail, effort_truncated),
            )
        fast = RoutingPick(
            model=only.id,
            effort=effort,
            model_confidence=None,
            effort_confidence=effort_confidence,
            tie_break=False,
        )
        if only.id != current_model and not validate_routed_effort(
            fast, strategy.candidates
        ):
            return (
                None,
                name,
                (0, 0, None),
                _with_truncation(
                    f"effort {effort!r} unsupported by {only.id}",
                    effort_truncated,
                ),
            )
        return (
            fast,
            name,
            usage,
            _with_truncation("", effort_truncated),
        )
    state = build_decision_state(
        ask=ask, directives=strategy.directives, side=side
    )
    questions = {
        "pick_model": build_model_question(
            candidates=strategy.candidates, directives=strategy.directives
        )
    }
    chain = _chain_for(strategy)
    if not chain:
        order = _effective_order(strategy.engine)
        head = order[0] if order else "off"
        return (None, head, (0, 0, None), f"{head} failed")
    failed = chain[0][0]
    detail = f"{failed} failed"
    down: list[str] = []
    informative = False
    truncated_any = False
    for name, attempt in chain:
        try:
            result = attempt(strategy, state, questions)
        except Exception:
            result = None
        if result is None:
            continue  # skipped link: unconfigured, never attempted
        truncated_any = truncated_any or result.truncated
        if result.answers is None:
            failed, detail = name, _link_detail(name, result.error)
            if result.error in _CONNECTION_ERRORS:
                down.append(name)
            elif result.error not in (None, "unready"):
                # Skipped and unready links are pause-neutral: never
                # attempted, so only attempted failures judge the pause.
                informative = True
            continue
        if result.model:
            logger.debug("Routing decision via %s served by %s", name, result.model)
        answer = validate_choice_answer(
            result.answers.get("pick_model"), strategy.candidates
        )
        if answer is None:
            failed, detail = name, _link_detail(name, "invalid table")
            informative = True
            continue
        model_id, tie_break, gate_detail = gate_model(answer, strategy)
        if model_id is None:
            return (
                None,
                name,
                (0, 0, None),
                _with_truncation(gate_detail, truncated_any),
            )
        candidate = next(
            entry for entry in strategy.candidates if entry.id == model_id
        )
        if not candidate.levels:
            return (
                None,
                name,
                (0, 0, None),
                f"picked candidate {model_id} advertises no levels",
            )
        effort_truncated = False
        if len(candidate.levels) == 1:
            # Degenerate choice: nothing to judge, and a one-option
            # question violates the 2-26 floor — the lone level rides
            # through with no effort read.
            effort, effort_confidence = candidate.levels[0], None
            total = (result.input_tokens, result.output_tokens, result.cost)
        else:
            (
                effort,
                effort_confidence,
                effort_usage,
                effort_engine,
                effort_detail,
                effort_truncated,
            ) = _decide_effort(strategy, candidate, state, chain)
            if effort is None:
                return (
                    None,
                    effort_engine,
                    (0, 0, None),
                    _with_truncation(
                        effort_detail, truncated_any or effort_truncated
                    ),
                )
            total = (
                result.input_tokens + effort_usage[0],
                result.output_tokens + effort_usage[1],
                _merge_cost(result.cost, effort_usage[2]),
            )
        pick = RoutingPick(
            model=model_id,
            effort=effort,
            model_confidence=float(answer["probabilities"][model_id]),
            effort_confidence=effort_confidence,
            tie_break=tie_break,
        )
        shrunk = truncated_any or effort_truncated
        if model_id != current_model and not validate_routed_effort(
            pick, strategy.candidates
        ):
            return (
                None,
                name,
                (0, 0, None),
                _with_truncation(
                    f"effort {pick.effort!r} unsupported by {model_id}", shrunk
                ),
            )
        return (
            pick,
            name,
            total,
            _with_truncation(gate_detail, shrunk),
        )
    if down and not informative:
        return (
            None,
            down[-1],
            (0, 0, None),
            _with_truncation(_pause_detail(down), truncated_any),
        )
    return (None, failed, (0, 0, None), _with_truncation(detail, truncated_any))


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
    try:
        estimate = estimate_messages_tokens(
            [{"role": "user", "content": [{"text": ask}]}]
        )
        new_cost = cost_for(estimate, estimate, new_model)
        prev_cost = cost_for(estimate, estimate, prev_model)
    except Exception:
        return "n/a"
    if new_cost is None or prev_cost is None:
        return "n/a"
    return f"{new_cost - prev_cost:+.4f}"


def _confidence_cell(value: float | None) -> str:
    """Percent cell for one confidence (n/a when no read exists)."""
    return f"{value:.0%}" if value is not None else "n/a"


def format_routed_line(
    *,
    model: str,
    effort: str,
    model_confidence: float | None,
    effort_confidence: float | None = None,
    tie_break: bool = False,
    truncated: bool = False,
    prev_model: str,
    ask: str,
    side: bool = False,
) -> str:
    """One transcript line for a routed ask (D-12).

    Choice plus both confidences plus the code-computed ``~$/ask``
    delta, with the tie-break substitution noted on the line. Side
    asks print the ``Routed (btw)`` head so the transcript tells
    spawn-time side picks apart from main-turn picks. A shrunken
    payload appends the truncation marker.
    """
    delta = route_cost_delta(model, prev_model, ask)
    head = "Routed (btw)" if side else "Routed"
    line = (
        f"{head} \u2192 {model} ({effort}): "
        f"model {_confidence_cell(model_confidence)}, "
        f"effort {_confidence_cell(effort_confidence)} "
        f"\u00b7 ~${delta}/ask vs {prev_model}"
    )
    if tie_break:
        line += " \u00b7 tie-break (cheaper of near-tie)"
    if truncated:
        line += f" \u00b7 {TRUNCATION_MARKER}"
    return line


def format_hold_line(*, current: str, detail: str) -> str:
    """Hold-current note with the reason detail (D-08, D-16).

    Engine failures pass ``"<engine> failed"`` (the long-standing
    shape); the threshold gate passes its ``confidence <read> <
    <threshold>`` read so the note names both numbers.
    """
    return f"Routing held on {current} ({detail}; retrying next ask)"


ROUTING_ON_REPLY = "Routing on — asks route pre-turn through the decision model."
ROUTING_OFF_REPLY = "Routing off — the current model serves every ask."
ROUTE_USAGE = "Usage: /route [on|off|status|setup|validate]"
MODEL_ROUTING_KEEP_REPLY = "Model unchanged — routing stays on."
ROUTING_MANUAL_OFF_NOTE = "Routing off — manual /model wins; /route on to re-enable."


class RoutingState:
    """Session-sticky routing toggle (D-10; mirrors :class:`ModeState`).

    ``state`` is ``"on"`` or ``"off"`` (anything else raises
    ``ValueError``). The loop owns one instance, defaulting to on when
    a strategy configures; ``/route`` flips it and a confirmed manual
    ``/model`` switch turns it off. The pause flag is separate and
    turn-scoped: an all-refused ask pauses same-turn decisions with
    zero new POSTs, and the next pre-turn hook resumes.
    """

    VALID = ("on", "off")

    def __init__(self, initial: str = "on") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown routing state {initial!r}: expected on|off")
        self._state = initial
        self._paused = False

    @property
    def state(self) -> str:
        """Current toggle state (``"on"`` or ``"off"``)."""
        return self._state

    def is_on(self) -> bool:
        """True when the pre-turn hook may route."""
        return self._state == "on"

    def is_paused(self) -> bool:
        """True when an all-refused ask paused this turn's decisions."""
        return self._paused

    def pause(self) -> None:
        """Pause routing for the ask: later same-turn decisions skip."""
        self._paused = True

    def resume(self) -> None:
        """Clear the pause: the next ask attempts its decision calls."""
        self._paused = False

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
