"""Phase 10 reported-spend scenarios for the live-tmux UAT rig (D-14).

Owns scenario_c1/c2 plus the shared OpenRouter id, the actual-marker
regexes, and the model-switch helper; tmux/send/wait/save plumbing
comes from uattest_lib as absolute sibling imports (CF-07 option (a)).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    COST_RE,
    LOGDIR8,
    ensure_workdir,
    pane_text,
    save,
    send,
    start_cli,
    stop_cli,
    wait_for,
    wait_for_new,
    wait_main_end,
)

# CLI-accepted aggregator form (bare ``openrouter/`` ids are rejected by
# /model validation; the wrap gate accepts both prefix forms).
CHEAP_OPENROUTER_ID = "litellm/openrouter/openai/gpt-4o-mini"
# Post-turn usage line with a marked actual: ``1.50K (1%) $0.00 actual``.
ACTUAL_USAGE_RE = re.compile(r"\(\d+%\) \$\d+\.\d{2} actual", re.MULTILINE)
# /cost row with a marked actual: ``turn 1 ... $0.0024 actual``.
ACTUAL_ROW_RE = re.compile(r"\$\d+\.\d{4} actual", re.MULTILINE)
# Blended-total split line: ``(actual $0.0024 + estimated $0.0100)``.
SPLIT_RE = re.compile(
    r"\(actual \$\d+\.\d{4} \+ estimated \$\d+\.\d{4}\)", re.MULTILINE
)


def _require_openrouter_key():
    """Fail fast without the ambient key (never print key material)."""
    assert os.environ.get("OPENROUTER_API_KEY"), (
        "OPENROUTER_API_KEY not set in the ambient environment; "
        "c-scenarios need a keyed run"
    )


def _switch_model(sess, model_id):
    """Explicit-id /model switch; the loop replies ``Model: <id> — ...``."""
    send(sess, f"/model {model_id}", "Enter")
    text = wait_for(sess, rf"Model: {re.escape(model_id)}", 90, "switched")
    assert "Model switch failed" not in text, "switch failed"
    return text


def scenario_c1():
    """C1: an OpenRouter main turn shows the marked actual (UAT test 3).

    Switch to the pinned cheap id, run one minimal turn, and assert
    the usage line plus the /cost row carry the ``actual`` marker.
    Pure-actual session: plain total, no split line (D-11).
    """
    _require_openrouter_key()
    workdir = ensure_workdir("w9")
    sess = "uatr8c1"
    start_cli(sess, workdir)
    try:
        _switch_model(sess, CHEAP_OPENROUTER_ID)
        after = len(COST_RE.findall(pane_text(sess)))
        send(
            sess,
            "Reply with the single word: ok. Answer from general knowledge only; do not read, list, or run anything.",
            "Enter",
        )
        text, _ = wait_main_end(sess, after=after)
        assert ACTUAL_USAGE_RE.search(text), (
            f"usage line lacks the actual marker: {text[-300:]}"
        )
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"turn 1", 60, "cost-rows")
        assert ACTUAL_ROW_RE.search(text), "cost row lacks the actual marker"
        assert not SPLIT_RE.search(text), "split line on a pure-actual session"
        print("C1 PASS", flush=True)
    finally:
        save(sess, "c1", LOGDIR8)
        stop_cli(sess)


def scenario_c2():
    """C2: a mixed session shows the blended total plus the split.

    One turn on the default (estimate) model, then switch to the
    OpenRouter id for a second turn; /cost must show the blended
    headline with the ``(actual $X + estimated $Y)`` split beneath.
    """
    _require_openrouter_key()
    workdir = ensure_workdir("w10")
    sess = "uatr8c2"
    start_cli(sess, workdir)
    try:
        send(
            sess,
            "Reply with the single word: ok. Answer from general knowledge only; do not read, list, or run anything.",
            "Enter",
        )
        text, _ = wait_main_end(sess)
        assert "actual" not in text.splitlines()[-1], (
            "estimate turn unexpectedly marked actual"
        )
        _switch_model(sess, CHEAP_OPENROUTER_ID)
        after = len(COST_RE.findall(pane_text(sess)))
        send(
            sess,
            "Reply with the single word: ok. Answer from general knowledge only; do not read, list, or run anything.",
            "Enter",
        )
        text, _ = wait_main_end(sess, after=after)
        assert ACTUAL_USAGE_RE.search(text), (
            f"usage line lacks the actual marker: {text[-300:]}"
        )
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"turn 2", 60, "cost-rows")
        assert SPLIT_RE.search(text), "blended split line missing"
        print("C2 PASS", flush=True)
    finally:
        save(sess, "c2", LOGDIR8)
        stop_cli(sess)
