"""Phase 7 /btw side-channel scenarios for the live-tmux UAT rig (D-14).

Owns scenario_s1/s2 plus no area helpers; tmux/send/wait/save plumbing
comes from uattest_lib as absolute sibling imports (CF-07 option (a)).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    pane_text,
    save,
    send,
    start_cli,
    stop_cli,
    wait_for,
    wait_main_end,
)


def scenario_s1():
    """Test 1: idle side approval pops live via multiplex, no typing."""
    for attempt in (1, 2):
        sess = f"uatr4s1a{attempt}"
        start_cli(sess)
        try:
            send(sess, "Reply with exactly these 3 words: alpha beta gamma", "Enter")
            time.sleep(2)
            send(
                sess,
                "/btw list the files in /tmp and delete nothing, but check with me first",
                "Enter",
            )
            time.sleep(4)
            if "Side question noted" not in pane_text(sess):
                print(
                    f"[attempt {attempt}] /btw landed at idle (normal turn), retrying",
                    flush=True,
                )
                save(sess, f"s1a{attempt}-nodispatch")
                continue
            text, served = wait_main_end(sess)
            if served:
                print(
                    f"[attempt {attempt}] mid-turn serve (not the idle case), retrying",
                    flush=True,
                )
                save(sess, f"s1a{attempt}-midturn")
                continue
            print(
                "[idle] hands off — expecting live dialog, sending nothing", flush=True
            )
            text = wait_for(sess, r"Approve\? \[btw\]", 180, "live-dialog")
            before = text.split("Approve? [btw]")[0][-500:]
            assert "will prompt when the next turn starts" not in before, (
                "bounded-wait announce instead of multiplex"
            )
            send(sess, "Enter")
            wait_for(sess, r"end btw", 180, "fenced-result")
            text = pane_text(sess)
            assert "CONFIRMATION_FAILED" not in text, "side approval self-denied"
            assert "--- end btw ---" in text, "missing fence"
            print("S1 PASS", flush=True)
            save(sess, "s1")
            return
        finally:
            save(sess, f"s1a{attempt}-timeout")
            stop_cli(sess)
    raise AssertionError("S1: idle case did not materialize in 2 attempts")


def scenario_s2():
    """Test 2 (chooser path on final code): cancel-side, no approval pending.

    Deterministic: side streams text only, so Ctrl-C always finds the chooser
    with no dialog competition. Exercises the 07-05 stdin guard + chooser.
    (The approval-race F-1 path is unchanged since the R2 human pass.)
    """
    sess = "uatr4s2"
    start_cli(sess)
    try:
        send(
            sess,
            "Write a pure-Python benchmark comparing JSON vs pickle across 5 payload sizes and PRINT the whole script plus predicted results",
            "Enter",
        )
        time.sleep(2)
        send(
            sess,
            "/btw explain in detail how rainbows form, at least 300 words, plain text, no tools",
            "Enter",
        )
        wait_for(sess, r"Side question noted", 60, "side-spawn")
        time.sleep(1)  # C-c during side startup latency; side needs no approval
        assert "--- end btw ---" not in pane_text(sess), (
            "side finished before C-c (void run)"
        )
        send(sess, "C-c")
        wait_for(sess, r"Cancel which\?", 60, "chooser")
        time.sleep(2)
        send(sess, "Down", "Enter")  # default=Main -> Down = Side
        wait_for(sess, r"Cancelled by user", 60, "side-cancelled")
        text = pane_text(sess)
        tail = text.split("Cancel which?")[-1]
        assert "Approve? [btw]" not in tail, "orphan btw dialog after cancel"
        assert "btw failed" not in text, "EventLoopException fence leaked"
        assert "--- btw:" in text and "--- end btw ---" in text, "cancel not fenced"
        wait_main_end(sess, timeout=300)
        print("S2 PASS", flush=True)
    finally:
        save(sess, "s2")
        stop_cli(sess)
