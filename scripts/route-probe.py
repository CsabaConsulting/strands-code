#!/usr/bin/env python3
"""Calibration probe runner over the production decision stack.

Runs the labeled probe set (``evals/routing-probe/probes.jsonl``) through
one pinned decision engine and writes one JSONL verdict record per probe
(top-1 probabilities, top1-minus-top2 margins, serving snapshots). The
runner imports the production state builders, transports, and gate from
``strands_code_cli.routing`` — no duplicated decision logic.

Modes::

    route-probe.py --dry-run            # list probe ids, no network
    route-probe.py --run openrouter     # 20 live verdicts via OpenRouter
    route-probe.py --run local          # 20 live verdicts via Ollama
    route-probe.py --run native         # 20 live verdicts via TypeSafe
    route-probe.py --compare            # diff runs against baseline.json

Regression path (compare-mode fallback): promptfoo is not installed on
this machine, so question regression runs through ``--compare`` instead
of ``promptfoo eval``. ``--compare`` diffs fresh ``--run`` output
against the recorded ``evals/routing-probe/baseline.json`` and exits
nonzero on any gated model-verdict drift (pick change or route/hold
flip), which is the same signal a promptfoo verdict-diff gate would
give. Effort-read flips warn instead of failing (D-16 routes weak
effort reads ungated, so near-tie flips are expected jitter), as do
top-1 moves over 0.05 and serving-snapshot changes. If promptfoo is
installed later, wrap ``probes.jsonl`` in
``evals/routing-probe/promptfooconfig.yaml`` per the pinned decision
model and run ``promptfoo eval`` alongside ``--compare``.

Security: the cloud key is read from the environment at call time by
the production transport (header-only, never logged); fault probes use
a bogus key value, never the real one. Verdict records and the
baseline carry asks, tables, and snapshots — never secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROBE_FILE = REPO_ROOT / "evals" / "routing-probe" / "probes.jsonl"
BASELINE_FILE = REPO_ROOT / "evals" / "routing-probe" / "baseline.json"

# Pinned engines. The cloud id is re-verified against the live
# decisions catalog at calibration time (2026-10-12: 19 entries, Jev
# still listed); re-pin on drift and note it. The local tag prefers
# nimble (RESEARCH default) and falls back to the pulled tev1 tag.
DECISION_MODEL_PIN = "typesafe/jev-1.13"
LOCAL_MODEL_PIN = "nimble"
LOCAL_MODEL_FALLBACK = "tev1:0.8b"
NATIVE_MODEL_PIN = "jev-1.13.0"

RUN_ENGINES = ("openrouter", "local", "native")
"""Engines the runner addresses (--run choices plus dry-run list)."""

CALIBRATION_DIRECTIVES = "trivial asks go cheap, deep refactors go big"

# tier -> (candidate id, criteria prose). Ids resolve in the almanac so
# the production tie-break can price near-tie pairs (D-14).
CALIBRATION_CANDIDATES = (
    (
        "cheap",
        "anthropic/claude-haiku-4-5",
        "Cheapest small model for trivial lookups and one-line edits",
    ),
    (
        "mid",
        "anthropic/claude-sonnet-4-5",
        "Mid-size model for everyday implementation and debugging",
    ),
    (
        "premium",
        "anthropic/claude-opus-4-5",
        "Premium large model for deep refactors and multi-file changes",
    ),
)

CALIBRATION_LEVELS = ["auto", "off", "low", "medium", "high"]
"""Advertised levels for the single-candidate effort probe (D-15)."""

TOP1_WARN_DELTA = 0.05
"""Top-1 drift above this prints a warning (gated drift fails)."""


def _ensure_production_imports() -> None:
    """Re-exec under the project venv when the direct import fails.

    ``strands_code_cli/__init__.py`` pulls the harness CLI, which only
    exists inside the ``uv`` venv. A bare ``python3`` therefore
    re-execs through ``uv run`` so the documented invocations work
    from any interpreter. The ``_ROUTE_PROBE_REEXEC`` guard keeps a
    genuinely broken venv from looping.
    """
    try:
        import strands_code_cli.routing  # noqa: F401
    except ModuleNotFoundError:
        if os.environ.get("_ROUTE_PROBE_REEXEC"):
            raise
        env = dict(os.environ, _ROUTE_PROBE_REEXEC="1")
        argv = [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            "python",
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ]
        os.execvpe("uv", argv, env)


_ensure_production_imports()

from strands_code_cli.routing import (  # noqa: E402
    RoutingCandidate,
    RoutingEngine,
    RoutingStrategy,
    build_decision_state,
    build_effort_question,
    build_model_question,
    decide_via_ollama,
    decide_via_openrouter,
    decide_via_typesafe,
    gate_model,
    local_engine_ready,
    validate_choice_answer,
)


def load_probes(path: Path = PROBE_FILE) -> list[dict]:
    """Load the labeled probe set (one JSON object per line)."""
    probes = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                probes.append(json.loads(line))
            except ValueError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}")
    return probes


def expand_ask(probe: dict) -> str:
    """Render the probe ask, padding deterministically when specified.

    ``ask_pad`` carries ``target_chars`` plus a ``filler`` line that is
    repeated to reach the target exactly, so oversized-ask probes stay
    reviewable in one JSONL line instead of embedding kilobytes.
    """
    ask = probe.get("ask", "")
    pad = probe.get("ask_pad")
    if not pad:
        return ask
    target = int(pad["target_chars"])
    filler = pad["filler"]
    if len(ask) >= target:
        return ask
    need = target - len(ask)
    repeats = (need + len(filler) - 1) // len(filler)
    return ask + (filler * repeats)[:need]


def calibration_strategy(
    *,
    single: bool,
    decision_model: str | None,
    local_model: str | None,
    native_model: str | None = None,
) -> tuple[RoutingStrategy, dict[str, str]]:
    """Build the fixed calibration strategy plus id->tier map."""
    entries = CALIBRATION_CANDIDATES[1:2] if single else CALIBRATION_CANDIDATES
    candidates = [
        RoutingCandidate(
            id=model_id,
            tier=tier,
            criteria=criteria,
            levels=list(CALIBRATION_LEVELS),
        )
        for tier, model_id, criteria in entries
    ]
    strategy = RoutingStrategy(
        candidates=candidates,
        directives=CALIBRATION_DIRECTIVES,
        engine=RoutingEngine(
            primary="openrouter",
            decision_model=decision_model,
            local_model=local_model,
            native_model=native_model,
        ),
    )
    return strategy, {model_id: tier for tier, model_id, _ in entries}


def resolve_local_model(base_url: str | None = None) -> str:
    """Pick the local tag: nimble when ready, else the tev1 fallback."""
    base = base_url or os.environ.get("OLLAMA_HOST") or None
    root = base or "http://127.0.0.1:11434"
    if local_engine_ready(root, LOCAL_MODEL_PIN):
        return LOCAL_MODEL_PIN
    if local_engine_ready(root, LOCAL_MODEL_FALLBACK):
        print(
            f"note: {LOCAL_MODEL_PIN} not pulled; "
            f"falling back to {LOCAL_MODEL_FALLBACK}",
            flush=True,
        )
        return LOCAL_MODEL_FALLBACK
    raise SystemExit(
        f"no decision model pulled (neither {LOCAL_MODEL_PIN} "
        f"nor {LOCAL_MODEL_FALLBACK} ready at {root})"
    )


def _fault_for(probe: dict, engine: str) -> str | None:
    """Resolve the probe fault for one engine (str or per-engine map)."""
    fault = probe.get("fault")
    if fault is None:
        return None
    if isinstance(fault, dict):
        return fault.get(engine)
    return fault


class _FaultContext:
    """Apply one fault around a single engine call (restores after)."""

    def __init__(self, fault: str | None, engine: str):
        self._fault = fault
        self._engine = engine
        self._saved = {}
        self.timeout: float | None = None
        self.model_override: str | None = None
        self.base_override: str | None = None

    def __enter__(self):
        fault = self._fault
        if fault == "timeout":
            self.timeout = 0.001
        elif fault == "unknown-model":
            self.model_override = "probe-no-such-model-xyz"
        elif fault == "bad-key" and self._engine == "openrouter":
            self._saved["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
            os.environ["OPENROUTER_API_KEY"] = "probe-bogus-key"
        elif fault == "no-key" and self._engine == "openrouter":
            self._saved["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
            os.environ.pop("OPENROUTER_API_KEY", None)
        elif fault == "bad-key" and self._engine == "native":
            self._saved["TYPESAFE_API_KEY"] = os.environ.get("TYPESAFE_API_KEY")
            os.environ["TYPESAFE_API_KEY"] = "probe-bogus-key"
        elif fault == "no-key" and self._engine == "native":
            self._saved["TYPESAFE_API_KEY"] = os.environ.get("TYPESAFE_API_KEY")
            os.environ.pop("TYPESAFE_API_KEY", None)
        elif fault == "dead-port" and self._engine == "local":
            self.base_override = "http://127.0.0.1:1"
        elif fault is not None:
            raise SystemExit(f"unknown fault {fault!r} for {self._engine}")
        return self

    def __exit__(self, *exc_info):
        for key, saved in self._saved.items():
            if saved is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved
        return False


def _ranked(probs: dict[str, float]) -> list[tuple[str, float]]:
    """Options sorted by probability desc, id asc (the gate order)."""
    return sorted(probs.items(), key=lambda item: (-item[1], item[0]))


def run_probe(
    probe: dict,
    *,
    engine: str,
    decision_model: str,
    local_model: str,
    native_model: str | None = None,
) -> dict:
    """Execute one probe through one engine; return the verdict record."""
    ask = expand_ask(probe)
    single = probe.get("candidates") == "single"
    native_tag = native_model or NATIVE_MODEL_PIN
    strategy, tiers = calibration_strategy(
        single=single,
        decision_model=decision_model,
        local_model=local_model,
        native_model=native_tag,
    )
    state = build_decision_state(
        ask=ask,
        directives=strategy.directives,
        side=bool(probe.get("side")),
    )
    if single:
        question_key = "pick_effort"
        question = build_effort_question(
            candidate=strategy.candidates[0],
            directives=strategy.directives,
        )
        membership = [RoutingCandidate(id=level) for level in CALIBRATION_LEVELS]
    else:
        question_key = "pick_model"
        question = build_model_question(
            candidates=strategy.candidates,
            directives=strategy.directives,
        )
        membership = strategy.candidates
    questions = {question_key: question}
    fault = _fault_for(probe, engine)
    with _FaultContext(fault, engine) as applied:
        if engine == "openrouter":
            kwargs: dict = {}
            if applied.timeout is not None:
                kwargs["timeout"] = applied.timeout
            result = decide_via_openrouter(
                decision_model=applied.model_override or decision_model,
                state=state,
                questions=questions,
                **kwargs,
            )
        elif engine == "local":
            kwargs = {}
            if applied.timeout is not None:
                kwargs["timeout"] = applied.timeout
            if applied.base_override is not None:
                kwargs["local_base_url"] = applied.base_override
            result = decide_via_ollama(
                local_model=applied.model_override or local_model,
                state=state,
                questions=questions,
                **kwargs,
            )
        elif engine == "native":
            kwargs = {}
            if applied.timeout is not None:
                kwargs["timeout"] = applied.timeout
            result = decide_via_typesafe(
                native_model=applied.model_override or native_tag,
                state=state,
                questions=questions,
                **kwargs,
            )
        else:
            raise SystemExit(f"unknown engine {engine!r}")
    if engine == "openrouter":
        pin = decision_model
    elif engine == "local":
        pin = local_model
    else:
        pin = native_tag
    record: dict = {
        "probe": probe["id"],
        "category": probe.get("category"),
        "engine": engine,
        "pin": pin,
        "snapshot": result.model,
        "question": question_key,
        "fault": fault,
        "ask_chars": len(ask),
        "sent_chars": len(state["ask"]),
        "error": result.error,
        "truncated": result.truncated,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost": result.cost,
        "expected": probe.get("expected"),
        "acceptable": probe.get("acceptable", []),
        "knobs": {
            "confidence_threshold": strategy.confidence_threshold,
            "tie_margin": strategy.tie_margin,
        },
    }
    answer = None
    raw_answer = None
    if result.answers is not None:
        raw_answer = result.answers.get(question_key)
        answer = validate_choice_answer(raw_answer, membership)
    record["had_answers"] = result.answers is not None
    if answer is None:
        if raw_answer is not None:
            record["raw_answer"] = repr(raw_answer)[:500]
        record.update(
            {
                "table": None,
                "top1": None,
                "top1_prob": None,
                "top2_prob": None,
                "margin": None,
                "gated": None,
                "tie_break": False,
                "detail": result.error or "invalid table",
            }
        )
    else:
        probs = answer["probabilities"]
        ranked = _ranked(probs)
        top1, top1_prob = ranked[0]
        top2_prob = ranked[1][1] if len(ranked) > 1 else None
        record.update(
            {
                "table": probs,
                "top1": top1,
                "top1_prob": top1_prob,
                "top2_prob": top2_prob,
                "margin": (top1_prob - top2_prob if top2_prob is not None else None),
            }
        )
        if single:
            record.update(
                {
                    "gated": top1,
                    "tie_break": False,
                    "detail": "",
                }
            )
        else:
            gated, tie_break, detail = gate_model(answer, strategy)
            record.update(
                {
                    "gated": gated,
                    "tie_break": tie_break,
                    "detail": detail,
                }
            )
    record["match"] = _matches(record, probe, tiers)
    return record


def _matches(record: dict, probe: dict, tiers: dict[str, str]) -> bool:
    """True when the verdict meets the probe's labeled expectation."""
    expected = probe.get("expected")
    if expected == "hold":
        return record["gated"] is None
    if expected == "route":
        gated = record["gated"]
        return gated is not None and tiers.get(gated) in (probe.get("acceptable") or [])
    if expected == "effort-route":
        return record["gated"] in CALIBRATION_LEVELS and record["table"] is not None
    return True  # route-or-hold: informational, always matches


def cmd_dry_run() -> int:
    """List probe ids without touching the network; exit 0."""
    probes = load_probes()
    print(f"engines: {', '.join(RUN_ENGINES)}")
    print(f"probes: {len(probes)}")
    for probe in probes:
        print(f"  {probe['id']} [{probe.get('category')}]")
    return 0


def _warm_local(local_model: str) -> None:
    """One throwaway local call so model load never flakes probe one."""
    strategy, _ = calibration_strategy(
        single=False, decision_model=None, local_model=local_model
    )
    state = build_decision_state(
        ask="warm-up", directives=strategy.directives, side=False
    )
    questions = {
        "pick_model": build_model_question(
            candidates=strategy.candidates,
            directives=strategy.directives,
        )
    }
    result = decide_via_ollama(
        local_model=local_model,
        state=state,
        questions=questions,
        timeout=300,
    )
    if result.answers is None:
        raise SystemExit(f"local warm-up failed: {result.error}")
    print(f"warmed {local_model} (snapshot {result.model})", flush=True)


def cmd_run(
    engine: str,
    *,
    out: Path | None,
    decision_model: str,
    local_model: str | None,
    native_model: str | None = None,
) -> int:
    """Execute the probe set through one engine; write JSONL verdicts."""
    probes = load_probes()
    # Cloud runs never touch the daemon: the OpenRouter and native
    # transports ignore the local tag, so resolve lazily on the
    # local path only and keep the pin populated from the constant
    # otherwise (D-06).
    if engine == "local":
        tag = local_model or resolve_local_model()
    else:
        tag = local_model or LOCAL_MODEL_PIN
    native_tag = native_model or NATIVE_MODEL_PIN
    if engine == "local":
        _warm_local(tag)
    out_path = out or Path(f"/tmp/route-probe-{engine}.jsonl")
    failures = 0
    with open(out_path, "w", encoding="utf-8") as handle:
        for probe in probes:
            record = run_probe(
                probe,
                engine=engine,
                decision_model=decision_model,
                local_model=tag,
                native_model=native_tag,
            )
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            status = "HOLD" if record["gated"] is None else "route"
            extra = record["detail"] or record["top1"]
            print(f"[{status}] {record['probe']}: {extra}", flush=True)
            # Transport health only: an invalid table with answers
            # present is a legitimate hold verdict (production holds
            # and serves), not a runner failure — behavior drift is
            # compare's job. Missing answers mean the engine itself
            # failed (or the key/daemon is absent) and fail loudly.
            if record["fault"] is None and not record["had_answers"]:
                failures += 1
                print(
                    f"error: non-fault probe {record['probe']} got no "
                    f"answers ({record['detail']})",
                    file=sys.stderr,
                )
    print(f"wrote {len(probes)} verdicts to {out_path}", flush=True)
    return 1 if failures else 0


def _load_run(path: Path) -> dict[str, dict]:
    """Load one run file into probe-id -> verdict."""
    verdicts = {}
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if line:
                record = json.loads(line)
                verdicts[record["probe"]] = record
    return verdicts


def _compare_engine(engine: str, run_path: Path, baseline: dict) -> tuple[int, int]:
    """Diff one engine run against the baseline; (drifts, warnings)."""
    try:
        run = _load_run(run_path)
    except FileNotFoundError:
        print(f"drift: {engine}: missing run file {run_path}")
        return 1, 0
    expected = baseline.get("verdicts", {}).get(engine, {})
    drifts = warnings = 0
    for probe_id, want in sorted(expected.items()):
        got = run.get(probe_id)
        if got is None:
            print(f"drift: {engine}/{probe_id}: missing from run")
            drifts += 1
            continue
        if got.get("gated") != want.get("gated"):
            # Effort reads are ungated by design (D-16 routes weak
            # reads), so near-tie effort flips are expected jitter,
            # not regressions — warn. Model verdicts are gated and
            # stable: any flip fails.
            if got.get("question") == "pick_effort":
                print(
                    f"warn: {engine}/{probe_id}: effort "
                    f"{want.get('gated')} -> {got.get('gated')} "
                    "(ungated read)"
                )
                warnings += 1
            else:
                print(
                    f"drift: {engine}/{probe_id}: gated "
                    f"{want.get('gated')} -> {got.get('gated')}"
                )
                drifts += 1
        for key in ("top1_prob",):
            old, new = want.get(key), got.get(key)
            if (
                isinstance(old, (int, float))
                and isinstance(new, (int, float))
                and abs(new - old) > TOP1_WARN_DELTA
            ):
                print(f"warn: {engine}/{probe_id}: {key} {old:.2f} -> {new:.2f}")
                warnings += 1
        if got.get("snapshot") != want.get("snapshot"):
            print(
                f"warn: {engine}/{probe_id}: snapshot "
                f"{want.get('snapshot')} -> {got.get('snapshot')} "
                "(re-pin and re-probe on drift)"
            )
            warnings += 1
    for probe_id in sorted(run):
        if probe_id not in expected:
            print(f"drift: {engine}/{probe_id}: not in baseline")
            drifts += 1
    return drifts, warnings


def cmd_compare(
    *,
    baseline_path: Path,
    run_paths: dict[str, Path],
) -> int:
    """Diff run files against the recorded baseline (nonzero on drift)."""
    try:
        with open(baseline_path, encoding="utf-8") as handle:
            baseline = json.load(handle)
    except FileNotFoundError:
        print(f"error: baseline not found: {baseline_path}", file=sys.stderr)
        return 2
    drifts = warnings = 0
    for engine, run_path in run_paths.items():
        engine_drifts, engine_warnings = _compare_engine(engine, run_path, baseline)
        drifts += engine_drifts
        warnings += engine_warnings
    if drifts:
        print(f"compare: {drifts} drift(s), {warnings} warning(s)")
        return 1
    print(f"compare: clean ({warnings} warning(s))")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: dry-run, run, or compare."""
    parser = argparse.ArgumentParser(
        description="Calibration probe runner (see module docstring)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="list probe ids, no network"
    )
    group.add_argument(
        "--run",
        choices=RUN_ENGINES,
        metavar="ENGINE",
        help="execute the probe set through one engine",
    )
    group.add_argument(
        "--compare",
        action="store_true",
        help="diff run files against the baseline",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="run output path (default /tmp/route-probe-<engine>.jsonl)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_FILE,
        help="baseline path for --compare",
    )
    parser.add_argument(
        "--decision-model",
        default=DECISION_MODEL_PIN,
        help="OpenRouter decision id (default pinned)",
    )
    parser.add_argument(
        "--local-model",
        default=None,
        help="local tag (default nimble-or-tev1 auto-resolve)",
    )
    parser.add_argument(
        "--native-model",
        default=None,
        help="native Jev id (default pinned full semver)",
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        return cmd_dry_run()
    if args.run:
        return cmd_run(
            args.run,
            out=args.out,
            decision_model=args.decision_model,
            local_model=args.local_model,
            native_model=args.native_model,
        )
    return cmd_compare(
        baseline_path=args.baseline,
        run_paths={
            "openrouter": Path("/tmp/route-probe-openrouter.jsonl"),
            "local": Path("/tmp/route-probe-local.jsonl"),
            "native": Path("/tmp/route-probe-native.jsonl"),
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
