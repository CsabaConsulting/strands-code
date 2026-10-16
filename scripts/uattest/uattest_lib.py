#!/usr/bin/env python3
"""Shared tmux/send/wait/save plumbing for the scripted live-tmux UAT rig (D-13).

Owns the session lifecycle (start/stop), tmux I/O (tmux/pane_text/send),
all waits (wait_for/wait_for_new/wait_main_end/wait_routed), transcript
saving (save), per-scenario workdirs (ensure_workdir), and the module
constants plus compiled regexes the scenarios share. Scenario files and
driver.py import these as absolute siblings (CF-07 option (a)); the rig
contract tests load this module via importlib and patch pane_text here.
"""

import os
import re
import subprocess
import time

LOGDIR = "/tmp/uatr4"
LOGDIR8 = "/tmp/uatr8"
CLI = "/home/csaba/.local/bin/uv run --project /home/csaba/repos/AWS/strands-code strands-code"
WORKDIR = "/tmp/uattest"
WORKDIR8 = "/tmp/uatr8"
# Matches the post-turn usage line in both shapes: ``451.27K (45%) $0.01``
# and the unknown-window fallback ``4.49K (n/a) $0.00`` (G-08-1: nova
# turns print the fallback, which the old %-only pattern never saw).
COST_RE = re.compile(r"\((?:\d+%|n/a)\) \$", re.MULTILINE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ACTIVE SYSTEM_DEFINED inference-profile form in us-west-2; the bare
# base id supports only INFERENCE_PROFILE throughput and is rejected
# at ConverseStream (G-08-1). All rig strategies build from this one
# constant so the sites cannot drift again.
RIG_NOVA_MICRO = "bedrock/us.amazon.nova-micro-v1:0"
# Literal "Turn failed ..." line the loop prints on provider errors;
# failed turns never print a cost line, so waits matching only success
# markers would hang to timeout without this fail-fast check (G-08-1).
FAIL_RE = re.compile(r"Turn failed[^\n]*")


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


def wait_for_new(sess, pattern, timeout, label, poll=3, before=None):
    """wait_for that ignores matches already in the scrollback (r-scenarios).

    Multi-turn scenarios re-match earlier output (status lines, cost
    lines, Routed notes); snapshotting the baseline count makes the
    wait fire only on a fresh occurrence. Pass a pre-send ``before``
    count when the reply is an instant local command: snapshotting
    after send races the reply and hangs on a match already present.
    """
    rx = re.compile(pattern, re.MULTILINE) if isinstance(pattern, str) else pattern
    if before is None:
        before = len(rx.findall(pane_text(sess)))
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        if len(rx.findall(text)) > before:
            print(f"[{label}] seen", flush=True)
            return text
        time.sleep(poll)
    raise AssertionError(f"TIMEOUT waiting for {label}: {pattern!r}")


def send(sess, *keys):
    tmux("send-keys", "-t", sess, *keys)


def start_cli(sess, workdir=WORKDIR, env_prefix="", cli_args=""):
    """Boot the CLI; env_prefix overrides the ambient env for one session.

    Native scenarios use it to hide the key (``env -u
    TYPESAFE_API_KEY``) or to boot with a bogus key
    (``TYPESAFE_API_KEY=probe-bogus-key``) — bogus values only,
    never real key material. ``cli_args`` appends CLI arguments
    (CodeAct scenarios boot with ``--codeact`` forms).
    """
    tmux("kill-session", "-t", sess)
    tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "60")
    extra = f" {cli_args}" if cli_args else ""
    send(sess, f"cd {workdir} && {env_prefix}{CLI}{extra}", "Enter")
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


def save(sess, name, logdir=LOGDIR):
    path = f"{logdir}/{name}.log"
    with open(path, "w") as f:
        f.write(pane_text(sess))
    print(f"[saved] {path}", flush=True)


def wait_main_end(sess, timeout=240, after=0):
    """Wait for main-end cost line, answering mid-turn dialogs like a human.

    Returns (pane_text, midturn_dialog_served). ``after`` is a baseline
    COST_RE count to exceed (multi-turn scenarios pass the current
    count so an earlier turn's cost line cannot satisfy the wait).
    """
    served = False
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        failed = FAIL_RE.search(text)
        if failed:
            raise AssertionError(
                f"Turn failed during main-end: {failed.group(0)[:200]}"
            )
        if len(COST_RE.findall(text)) > after:
            return text, served
        if re.search(r"Approve\?", text):
            print("[assist] answering mid-turn dialog with Yes", flush=True)
            served = True
            send(sess, "Enter")
            time.sleep(5)
            continue
        time.sleep(3)
    raise AssertionError("TIMEOUT waiting for main-end")


def ensure_workdir(name):
    """Fresh per-scenario workdir under /tmp/uatr8 (strategy files land here)."""
    path = os.path.join(WORKDIR8, name)
    os.makedirs(os.path.join(path, ".agent"), exist_ok=True)
    strat = os.path.join(path, ".agent", "routing.yaml")
    if os.path.exists(strat):
        os.remove(strat)
    return path


def wait_routed(sess, timeout, label, after=0, side=False):
    """Wait for a fresh Routed/Held transcript line (baseline ``after``).

    Serves mid-turn Approve? dialogs like wait_main_end: a main-turn
    tool approval blocks the pump, starving the side spawn behind it.
    """
    marker = "Routed (btw)" if side else "Routed \u2192"
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        failed = FAIL_RE.search(text)
        if failed:
            raise AssertionError(f"Turn failed during {label}: {failed.group(0)[:200]}")
        fresh = text.count(marker) + text.count("Routing held") > after
        if fresh:
            return text, None
        if re.search(r"Approve\?", text):
            print("[assist] answering mid-turn dialog with Yes", flush=True)
            send(sess, "Enter")
            time.sleep(5)
            continue
        time.sleep(2)
    raise AssertionError(f"TIMEOUT waiting for {label}")
