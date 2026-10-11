#!/usr/bin/env python3
"""Scripted live-tmux UAT driver for strands-code Phase 7 confirmation round.

Usage: driver.py {s1|s2}   (one scenario per process; tmux session per scenario)
Transcripts land in /tmp/uatr4/<scenario>.log. Exit 0 = all asserts passed.

Key insight: a mid-turn Approve? dialog blocks the pump thread, so the driver
must answer dialogs to make progress (like a human would). S1 retries until the
idle case materializes (max 2 attempts).
"""
import re
import subprocess
import sys
import time

LOGDIR = "/tmp/uatr4"
CLI = "/home/csaba/.local/bin/uv run --project /home/csaba/repos/AWS/strands-code strands-code"
WORKDIR = "/tmp/uattest"
COST_RE = re.compile(r"\(\d+%\) \$", re.MULTILINE)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=30)


def pane_text(sess):
    r = tmux("capture-pane", "-p", "-t", sess, "-S", "-1000")
    return r.stdout


def wait_for(sess, pattern, timeout, label, poll=3):
    rx = re.compile(pattern, re.MULTILINE) if isinstance(pattern, str) else pattern
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        if rx.search(text):
            print(f"[{label}] seen", flush=True)
            return text
        time.sleep(poll)
    raise AssertionError(f"TIMEOUT waiting for {label}: {pattern!r}")


def send(sess, *keys):
    tmux("send-keys", "-t", sess, *keys)


def start_cli(sess):
    tmux("kill-session", "-t", sess)
    tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "60")
    send(sess, f"cd {WORKDIR} && {CLI}", "Enter")
    time.sleep(6)
    if "Recent sessions" in pane_text(sess):
        print("[picker] Enter for new session", flush=True)
        send(sess, "Enter")
    wait_for(sess, r"Ctrl-D to exit", 90, "boot")
    wait_for(sess, r"^> ?$", 30, "prompt", poll=2)


def stop_cli(sess):
    try:
        send(sess, "C-d")
        time.sleep(3)
    finally:
        tmux("kill-session", "-t", sess)


def save(sess, name):
    path = f"{LOGDIR}/{name}.log"
    with open(path, "w") as f:
        f.write(pane_text(sess))
    print(f"[saved] {path}", flush=True)


def wait_main_end(sess, timeout=240):
    """Wait for main-end cost line, answering mid-turn dialogs like a human.

    Returns (pane_text, midturn_dialog_served).
    """
    served = False
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        if COST_RE.search(text):
            return text, served
        if re.search(r"Approve\?", text):
            print("[assist] answering mid-turn dialog with Yes", flush=True)
            served = True
            send(sess, "Enter")
            time.sleep(5)
            continue
        time.sleep(3)
    raise AssertionError("TIMEOUT waiting for main-end")


def scenario_s1():
    """Test 1: idle side approval pops live via multiplex, no typing."""
    for attempt in (1, 2):
        sess = f"uatr4s1a{attempt}"
        start_cli(sess)
        try:
            send(sess, "Reply with exactly these 3 words: alpha beta gamma", "Enter")
            time.sleep(2)
            send(sess, "/btw list the files in /tmp and delete nothing, but check with me first", "Enter")
            time.sleep(4)
            if "Side question noted" not in pane_text(sess):
                print(f"[attempt {attempt}] /btw landed at idle (normal turn), retrying", flush=True)
                save(sess, f"s1a{attempt}-nodispatch")
                continue
            text, served = wait_main_end(sess)
            if served:
                print(f"[attempt {attempt}] mid-turn serve (not the idle case), retrying", flush=True)
                save(sess, f"s1a{attempt}-midturn")
                continue
            print("[idle] hands off — expecting live dialog, sending nothing", flush=True)
            text = wait_for(sess, r"Approve\? \[btw\]", 180, "live-dialog")
            before = text.split("Approve? [btw]")[0][-500:]
            assert "will prompt when the next turn starts" not in before, \
                "bounded-wait announce instead of multiplex"
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
        send(sess, "Write a pure-Python benchmark comparing JSON vs pickle across 5 payload sizes and PRINT the whole script plus predicted results", "Enter")
        time.sleep(2)
        send(sess, "/btw explain in detail how rainbows form, at least 300 words, plain text, no tools", "Enter")
        wait_for(sess, r"Side question noted", 60, "side-spawn")
        time.sleep(1)  # C-c during side startup latency; side needs no approval
        assert "--- end btw ---" not in pane_text(sess), "side finished before C-c (void run)"
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


if __name__ == "__main__":
    import os
    os.makedirs(LOGDIR, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "s1":
        scenario_s1()
    elif which == "s2":
        scenario_s2()
    else:
        sys.exit("usage: driver.py {s1|s2}")
