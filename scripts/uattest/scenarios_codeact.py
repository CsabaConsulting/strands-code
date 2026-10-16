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
    wait_for,
    wait_for_new,
    wait_main_end,
)


def scenario_a1():
    """A1: bare --codeact boots the session into code mode (G-11-1).

    RED before the gap fix (typer rejects the bare flag with
    "requires an argument"); GREEN after (boots, /codeact reports
    code). The early-pane check fails fast instead of hanging on
    the boot wait.
    """
    workdir = ensure_workdir("w11")
    sess = "uatr8a1"
    tmux("kill-session", "-t", sess)
    tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "60")
    try:
        send(sess, f"cd {workdir} && {CLI} --codeact", "Enter")
        time.sleep(8)
        early = pane_text(sess)
        if "requires an argument" in early:
            raise AssertionError(
                "G-11-1 reproduced: bare --codeact rejected, want boot into code mode"
            )
        if "Recent sessions" in early:
            print("[picker] Enter for new session", flush=True)
            send(sess, "Enter")
        wait_for(sess, r"Ctrl-D to exit", 90, "boot")
        wait_for(sess, r"^> ?$", 30, "prompt", poll=2)
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
