"""Phase 11 CodeAct scenarios for the live-tmux UAT rig (D-14).

Owns scenario_a1/a2 plus no area helpers; tmux/send/wait/save plumbing
comes from uattest_lib as absolute sibling imports (CF-07 option (a)).
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    CLI,
    COST_RE,
    LOGDIR8,
    ensure_workdir,
    pane_text,
    save,
    send,
    start_cli,
    stop_cli,
    tmux,
    wait_for_new,
    wait_main_end,
)


def scenario_a1():
    """A1: explicit ``--codeact code`` boots into code mode; bare ``--codeact`` is rejected."""
    workdir = ensure_workdir("w11")
    sess = "uatr8a1"
    tmux("kill-session", "-t", sess)
    tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "60")
    try:
        send(sess, f"cd {workdir} && {CLI} --codeact", "Enter")
        time.sleep(5)
        early = pane_text(sess)
        assert "requires an argument" in early, (
            "bare --codeact should require an explicit tool|code|both value"
        )
        tmux("kill-session", "-t", sess)
        start_cli(sess, workdir, cli_args="--codeact code")
        before = len(re.findall(r"Interface: code", pane_text(sess)))
        send(sess, "/codeact", "Enter")
        text = wait_for_new(sess, r"Interface: code", 30, "code-report", before=before)
        assert "code-first actions through python_repl" in text, (
            "bare /codeact did not report code mode"
        )
        print("A1 PASS", flush=True)
    finally:
        save(sess, "a1", LOGDIR8)
        stop_cli(sess)


def scenario_a2():
    """A2: code turn labels codeact; switch-back tool turn is unshaped.

    Boots with --codeact code, runs one minimal turn (asserts the
    ``interface: codeact`` label), switches to tool, runs another
    minimal turn (asserts a fresh ``interface: tool`` label and no
    python_repl shaping after the switch). Covers UAT tests 2+5.
    """
    workdir = ensure_workdir("w12")
    sess = "uatr8a2"
    start_cli(sess, workdir, cli_args="--codeact code")
    try:
        after = len(COST_RE.findall(pane_text(sess)))
        send(
            sess,
            "Reply with the single word: ok. Answer from general knowledge only; do not read, list, or run anything.",
            "Enter",
        )
        text, _ = wait_main_end(sess, after=after)
        assert re.search(r"^interface: codeact", text, re.MULTILINE), (
            "code turn lacks the codeact label"
        )
        before_switch = len(re.findall(r"Interface: tool", pane_text(sess)))
        send(sess, "/codeact tool", "Enter")
        wait_for_new(sess, r"Interface: tool", 30, "switched", before=before_switch)
        after = len(COST_RE.findall(pane_text(sess)))
        send(
            sess,
            "Reply with the single word: ok. Answer from general knowledge only; do not read, list, or run anything.",
            "Enter",
        )
        text, _ = wait_main_end(sess, after=after)
        assert re.search(r"^interface: tool", text, re.MULTILINE), (
            "tool turn lacks the tool label"
        )
        tail = text.split("Interface: tool")[-1]
        assert "[Tool] python_repl" not in tail, (
            "tool turn unexpectedly shaped code-first"
        )
        print("A2 PASS", flush=True)
    finally:
        save(sess, "a2", LOGDIR8)
        stop_cli(sess)
