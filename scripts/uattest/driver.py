#!/usr/bin/env python3
"""Scripted live-tmux UAT driver for strands-code Phase 7 + 8 confirmation.

Usage: driver.py {s1|s2|r1|r2|r3|r4}   (one scenario per process; tmux
session per scenario). s1/s2 cover Phase 7 (/btw); r1/r2/r3/r4 cover
the Phase 8 rows (guided setup, local engine, e2e routed turn, side
ask) against the Decision-API flow.
Transcripts land in /tmp/uatr4/<scenario>.log (s*) or /tmp/uatr8/<scenario>.log
(r*). Exit 0 = all asserts passed.

Key insight: a mid-turn Approve? dialog blocks the pump thread, so the driver
must answer dialogs to make progress (like a human would). S1 retries until the
idle case materializes (max 2 attempts).
"""
import os
import re
import subprocess
import sys
import time

LOGDIR = "/tmp/uatr4"
LOGDIR8 = "/tmp/uatr8"
CLI = "/home/csaba/.local/bin/uv run --project /home/csaba/repos/AWS/strands-code strands-code"
WORKDIR = "/tmp/uattest"
WORKDIR8 = "/tmp/uatr8"
COST_RE = re.compile(r"\(\d+%\) \$", re.MULTILINE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def wait_for_new(sess, pattern, timeout, label, poll=3):
    """wait_for that ignores matches already in the scrollback (r-scenarios).

    Multi-turn scenarios re-match earlier output (status lines, cost
    lines, Routed notes); snapshotting the baseline count makes the
    wait fire only on a fresh occurrence.
    """
    rx = re.compile(pattern, re.MULTILINE) if isinstance(pattern, str) else pattern
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


def start_cli(sess, workdir=WORKDIR):
    tmux("kill-session", "-t", sess)
    tmux("new-session", "-d", "-s", sess, "-x", "200", "-y", "60")
    send(sess, f"cd {workdir} && {CLI}", "Enter")
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


# ---------------------------------------------------------------- Phase 8

def ensure_workdir(name):
    """Fresh per-scenario workdir under /tmp/uatr8 (strategy files land here)."""
    path = os.path.join(WORKDIR8, name)
    os.makedirs(os.path.join(path, ".agent"), exist_ok=True)
    strat = os.path.join(path, ".agent", "routing.yaml")
    if os.path.exists(strat):
        os.remove(strat)
    return path


def write_strategy(workdir, text):
    path = os.path.join(workdir, ".agent", "routing.yaml")
    with open(path, "w") as f:
        f.write(text)
    return path


def strategy_text(workdir):
    with open(os.path.join(workdir, ".agent", "routing.yaml")) as f:
        return f.read()


def strategy_ids(workdir):
    ids = []
    for line in strategy_text(workdir).splitlines():
        line = line.strip()
        if line.startswith("- "):
            line = line[2:]
        if line.startswith("id:"):
            ids.append(line.split("id:", 1)[1].strip())
    return ids


def current_model_from_boot(text):
    """Default model id from the boot warning (no hardcoded ids)."""
    m = re.search(r"Model (\S+) has no native web search", text)
    assert m, "boot model line not found"
    return m.group(1)


def live_decision_id():
    """Cheapest decisions-catalog id, via the repo's own code."""
    code = (
        "from strands_code_cli.live_pricing import fetch_openrouter_decision_models;"
        "from strands_code_cli.router import _setup_decision_entries;"
        "entries = _setup_decision_entries(fetch_openrouter_decision_models());"
        "assert entries, 'empty decisions catalog';"
        "print(entries[0]['id'])"
    )
    r = subprocess.run(
        ["uv", "run", "--project", REPO, "python", "-c", code],
        capture_output=True, text=True, timeout=120,
        cwd="/tmp",
    )
    assert r.returncode == 0, f"catalog fetch failed: {r.stderr[-300:]}"
    return r.stdout.strip()


HOLD_NOTE_RE = re.compile(r"Routing held on \S+ \(.+; retrying next ask\)")
"""Hold-note shape: serving model + reason detail + retry promise."""


def routed_line_with_confidences(text, side=False):
    """Latest Routed line; asserts it carries both confidence cells (D-12)."""
    marker = "Routed (btw)" if side else "Routed \u2192"
    lines = [line for line in text.splitlines() if marker in line]
    assert lines, f"no {marker} line (held?)"
    assert re.search(r"model \d+%, effort \d+%", lines[-1]), (
        f"routed line lacks both confidences: {lines[-1]}"
    )
    return lines[-1]


def wait_routed(sess, timeout, label, after=0, side=False):
    """Wait for a fresh Routed/Held transcript line (baseline ``after``).

    Serves mid-turn Approve? dialogs like wait_main_end: a main-turn
    tool approval blocks the pump, starving the side spawn behind it.
    """
    marker = "Routed (btw)" if side else "Routed \u2192"
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
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


def scenario_r1():
    """R1: /route setup against the live split catalogs + /route validate.

    Repo scope keeps the user's global config untouched. Asserts the
    candidate radio carried live chat-catalog prices, the decision
    radio carried live decisions-catalog prices (split-catalog setup,
    not the typed fallback), the file round-trips the enumerated id
    with no key material, and validate reports VALID against the
    cached decisions catalog.
    """
    workdir = ensure_workdir("w1")
    sess = "uatr8r1"
    start_cli(sess, workdir)
    try:
        send(sess, "/route setup", "Enter")
        wait_for(sess, r"Where should the strategy live", 60, "scope-radio")
        send(sess, "Down", "Enter")  # repo scope
        wait_for(sess, r"Decision engine", 60, "engine-radio")
        send(sess, "Enter")  # openrouter (default)
        text = wait_for(sess, r"Pick a candidate model", 120, "candidate-radio")
        assert "per 1M" in text, "candidate radio lacks live prices (typed fallback?)"
        send(sess, "Enter")  # cheapest first
        for _ in range(3):  # Done radio (same title) until decision radio
            time.sleep(4)
            text = pane_text(sess)
            if "Pick the decision model" in text:
                break
            assert "Pick a candidate model" in text, "lost the setup flow"
            send(sess, "Enter")  # Done is the default once picks exist
        else:
            raise AssertionError("decision radio never arrived")
        time.sleep(4)  # let the decision options render past the title
        text = pane_text(sess)
        tail = text.split("Pick the decision model")[-1]
        assert "per 1M" in tail, "decision radio lacks live prices (typed fallback?)"
        send(sess, "Enter")  # cheapest decisions-catalog entry
        wait_for(sess, r"Enter one directive per line", 60, "directives")
        send(sess, "Trivial asks go cheap.", "Enter")
        time.sleep(2)
        send(sess, "Enter")  # blank line finishes
        text = wait_for(sess, r"Routing strategy saved \(repo\)", 60, "saved")
        assert "Live catalog unreachable" not in text, "catalog fetch failed"
        assert "Decisions catalog unreachable" not in text, "decisions fetch failed"
        assert "1 candidate, engine openrouter" in text, "summary mismatch"
        saved = strategy_text(workdir)
        assert "api_key" not in saved, "key material in strategy file"
        ids = strategy_ids(workdir)
        assert len(ids) == 1, f"expected 1 candidate, got {ids}"
        assert ids[0] in text, "saved id was not enumerated live"
        send(sess, "/cost refresh", "Enter")
        wait_for(sess, r"OpenRouter:", 120, "refresh-done")
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert ": ok" in text, "candidate not ok"
        assert "known in the cached decisions catalog" in text, "decision id cache miss"
        assert "SKIP" not in text and "INVALID" not in text, "validate flags set"
        print("R1 PASS", flush=True)
    finally:
        save(sess, "r1", LOGDIR8)
        stop_cli(sess)


def scenario_r2():
    """R2: System One path via a real Ollama daemon + routed turn.

    Strategy is hand-written (covers the manual-edit path) with a
    decision-capable pull; the ask must route through the daemon
    (Routed line, /cost 'via local') with a measured decision
    latency, never hold, and the local decision spend must read
    zero (cost-absent calls price nothing, never estimated).
    """
    workdir = ensure_workdir("w2")
    sess = "uatr8r2"
    start_cli(sess, workdir)
    try:
        current = current_model_from_boot(pane_text(sess))
        write_strategy(workdir, (
            "candidates:\n"
            "  - id: bedrock/amazon.nova-micro-v1:0\n"
            "    tier: tiny\n"
            "    levels: [auto, off]\n"
            f"  - id: {current}\n"
            "    tier: mid\n"
            "    levels: [auto, off]\n"
            "directives: >-\n"
            "  Always stay on the current model.\n"
            "engine:\n"
            "  primary: local\n"
            "  local_model: tev1:0.8b\n"
        ))
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert text.count(": ok") >= 2, "candidates not ok"
        send(sess, "/route on", "Enter")  # file landed after boot; enable explicitly
        wait_for(sess, r"Routing on", 60, "explicit-on")
        send(sess, "/route status", "Enter")
        text = wait_for_new(sess, r"Routing: ", 60, "status")
        assert "Routing: on" in text, "routing not on"
        assert "routing.yaml" in text, "status lacks strategy source"
        send(sess, "Reply with exactly these 3 words: alpha beta gamma", "Enter")
        t0 = time.time()
        text, _ = wait_routed(sess, 120, "routed-line")
        print(f"[r2] decision latency: {time.time() - t0:.1f}s", flush=True)
        assert "Routed \u2192" in text, "no Routed line (held?)"
        assert "Routing held" not in text, "local engine held current"
        text, _ = wait_main_end(sess)
        assert "alpha beta gamma" in text.lower(), "turn not served"
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 60, "cost-routing")
        assert "via local" in text, "decision engine not local"
        assert re.search(r"via local \$0\.0000", text), "local decision spend nonzero"
        assert "[held]" not in text, "held marker in cost report"
        print("R2 PASS", flush=True)
    finally:
        save(sess, "r2", LOGDIR8)
        stop_cli(sess)


def scenario_r3():
    """R3: end-to-end routed turn on Bedrock + toggle round-trip.

    Decision via the live decisions catalog cheapest id; the routed
    turn serves on Bedrock with both confidences on the Routed line;
    /cost shows the compact Routing entry with reported spend. Then
    /route off suppresses routing for a turn and /route on restores
    it; any hold note must match the held-on shape.
    """
    workdir = ensure_workdir("w3")
    decision = live_decision_id()
    print(f"[r3] decision model: {decision}", flush=True)
    sess = "uatr8r3"
    start_cli(sess, workdir)
    try:
        current = current_model_from_boot(pane_text(sess))
        send(sess, "/cost refresh", "Enter")
        wait_for(sess, r"OpenRouter:", 120, "refresh-done")
        write_strategy(workdir, (
            "candidates:\n"
            "  - id: bedrock/amazon.nova-micro-v1:0\n"
            "    tier: tiny\n"
            "    levels: [auto, off]\n"
            f"  - id: {current}\n"
            "    tier: mid\n"
            "    levels: [auto, off]\n"
            "directives: >-\n"
            "  Always stay on the current model.\n"
            "engine:\n"
            "  primary: openrouter\n"
            f"  decision_model: {decision}\n"
        ))
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert "not in the cached decisions catalog" not in text, "decision id cache miss"
        send(sess, "/route on", "Enter")  # file landed after boot; enable explicitly
        wait_for(sess, r"Routing on", 60, "explicit-on")
        send(sess, "Reply with exactly these 3 words: alpha beta gamma", "Enter")
        text, _ = wait_routed(sess, 120, "routed-line")
        routed_line_with_confidences(text)
        assert "Routing held" not in text, "openrouter engine held current"
        text, _ = wait_main_end(sess)
        assert "alpha beta gamma" in text.lower(), "turn not served"
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 60, "cost-routing")
        assert "via openrouter" in text, "decision engine not openrouter"
        assert re.search(r"\[model \d+%, effort \d+%]", text), "cost entry lacks confidences"
        assert re.search(r"via openrouter \$\d+\.\d{4}", text), "cost entry lacks spend"
        assert "[held]" not in text, "held marker in cost report"
        snap = pane_text(sess)
        routed_before = snap.count("Routed \u2192")
        send(sess, "/route off", "Enter")
        wait_for_new(sess, r"Routing off", 60, "off")
        send(sess, "Reply with exactly: offcheck", "Enter")
        after_cost = len(COST_RE.findall(pane_text(sess)))
        text, _ = wait_main_end(sess, after=after_cost)
        assert text.count("Routed \u2192") == routed_before, "routed while off"
        send(sess, "/route on", "Enter")
        wait_for_new(sess, r"Routing on", 60, "on")
        send(sess, "Reply with exactly: oncheck", "Enter")
        marked = text.count("Routed \u2192") + text.count("Routing held")
        text, _ = wait_routed(sess, 120, "routed-again", after=marked)
        if text.count("Routed \u2192") != routed_before + 1:
            # Transient decision-API failure holds (D-08); the product
            # retries next ask, so the rig gets one retry too.
            print("[r3] held once, retrying the ask", flush=True)
            assert HOLD_NOTE_RE.search(text), "hold note shape mismatch"
            wait_main_end(sess, after=len(COST_RE.findall(pane_text(sess))))
            send(sess, "Reply with exactly: oncheck again", "Enter")
            marked = text.count("Routed \u2192") + text.count("Routing held")
            text, _ = wait_routed(sess, 120, "routed-retry", after=marked)
            assert text.count("Routed \u2192") == routed_before + 1, "no route after on"
        routed_line_with_confidences(text)
        wait_main_end(sess, after=len(COST_RE.findall(pane_text(sess))))
        print("R3 PASS", flush=True)
    finally:
        save(sess, "r3", LOGDIR8)
        stop_cli(sess)


def scenario_r4():
    """R4: live /btw side ask routes side-flagged through the strategy.

    Mid-turn /btw spawn must print the side-headed ``Routed (btw)``
    line with both confidences, and the /cost Routing section must
    carry the side-flagged entry. Main ask also routes; both
    decisions go to OpenRouter.
    """
    workdir = ensure_workdir("w4")
    decision = live_decision_id()
    print(f"[r4] decision model: {decision}", flush=True)
    sess = "uatr8r4"
    start_cli(sess, workdir)
    try:
        current = current_model_from_boot(pane_text(sess))
        write_strategy(workdir, (
            "candidates:\n"
            "  - id: bedrock/amazon.nova-micro-v1:0\n"
            "    tier: tiny\n"
            "    levels: [auto, off]\n"
            f"  - id: {current}\n"
            "    tier: mid\n"
            "    levels: [auto, off]\n"
            "directives: >-\n"
            "  Always stay on the current model.\n"
            "engine:\n"
            "  primary: openrouter\n"
            f"  decision_model: {decision}\n"
        ))
        send(sess, "/route on", "Enter")
        wait_for(sess, r"Routing on", 60, "explicit-on")
        send(sess, "Write a pure-Python benchmark comparing JSON vs pickle across 5 payload sizes and PRINT the whole script plus predicted results — do not save or run anything, just output text, no tools", "Enter")
        time.sleep(6)  # stagger: let the main decision finish first
        send(sess, "/btw Reply with exactly: sidecheck", "Enter")
        wait_for(sess, r"Side question noted", 60, "side-spawn")
        try:
            text, _ = wait_routed(sess, 60, "routed-btw", side=True)
        except AssertionError:
            # Transient decision-API failure holds silently on the side
            # path; each spawn decides once, so a second /btw retries.
            print("[r4] first spawn unmarked, sending a second /btw", flush=True)
            send(sess, "/btw Reply with exactly: sidecheck two", "Enter")
            wait_for_new(sess, r"Side question noted", 60, "side-spawn-2")
            text, _ = wait_routed(sess, 120, "routed-btw-2", side=True)
        routed_line_with_confidences(text, side=True)
        text, _ = wait_main_end(sess, timeout=300)
        assert "sidecheck" in text.lower(), "side answer not served"
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 120, "cost-routing")
        assert "(btw)" in text, "no side-flagged cost entry"
        assert "via openrouter" in text, "side decision engine not openrouter"
        print("R4 PASS", flush=True)
    finally:
        save(sess, "r4", LOGDIR8)
        stop_cli(sess)


if __name__ == "__main__":
    os.makedirs(LOGDIR, exist_ok=True)
    os.makedirs(LOGDIR8, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "s1":
        scenario_s1()
    elif which == "s2":
        scenario_s2()
    elif which == "r1":
        scenario_r1()
    elif which == "r2":
        scenario_r2()
    elif which == "r3":
        scenario_r3()
    elif which == "r4":
        scenario_r4()
    else:
        sys.exit("usage: driver.py {s1|s2|r1|r2|r3|r4}")
