"""Phase 8 decision-routing scenarios for the live-tmux UAT rig (D-14).

Owns scenario_r1/r2/r3/r4 plus the strategy-file, catalog, and routed-line
helpers; tmux/send/wait/save plumbing comes from uattest_lib as absolute
sibling imports (CF-07 option (a)).
"""

import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    COST_RE,
    LOGDIR8,
    REPO,
    RIG_NOVA_MICRO,
    ensure_workdir,
    pane_text,
    save,
    send,
    start_cli,
    stop_cli,
    wait_for,
    wait_for_new,
    wait_main_end,
    wait_routed,
)


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


def strategy_order(workdir):
    """Engine try-order from the saved file (block or flow style)."""
    text = strategy_text(workdir)
    for lineno, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped == "order:":
            order = []
            for rest in text.splitlines()[lineno + 1 :]:
                item = rest.strip()
                if not item.startswith("- "):
                    break
                order.append(item[2:].strip())
            return order
        if stripped.startswith("order:"):
            flow = stripped.split("order:", 1)[1].strip()
            assert flow.startswith("[") and flow.endswith("]"), text
            return [piece.strip() for piece in flow[1:-1].split(",")]
    raise AssertionError(f"no engine order in strategy file:\n{text}")


def current_model_from_boot(text):
    """Default model id from the boot warning (no hardcoded ids)."""
    m = re.search(r"Model (\S+) has no native web search", text)
    assert m, "boot model line not found"
    return m.group(1)


def live_decision_id():
    """Cheapest decisions-catalog id, via the repo's own code."""
    code = (
        "from strands_code_cli.cost.live_pricing import fetch_openrouter_decision_models;"
        "from strands_code_cli.dispatch.core import _setup_decision_entries;"
        "entries = _setup_decision_entries(fetch_openrouter_decision_models());"
        "assert entries, 'empty decisions catalog';"
        "print(entries[0]['id'])"
    )
    r = subprocess.run(
        ["uv", "run", "--project", REPO, "python", "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
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


def scenario_r1():
    """R1: /route setup against the live split catalogs + /route validate.

    Repo scope keeps the user's global config untouched. Asserts the
    order proposal is accepted, the candidate radio carried live
    chat-catalog prices, the decision radio carried live
    decisions-catalog prices (split-catalog setup, not the typed
    fallback), the file round-trips the enumerated id with no key
    material, and validate reports VALID against the cached
    decisions catalog.
    """
    workdir = ensure_workdir("w1")
    sess = "uatr8r1"
    start_cli(sess, workdir)
    try:
        send(sess, "/route setup", "Enter")
        wait_for(sess, r"Where should the strategy live", 60, "scope-radio")
        send(sess, "Down", "Enter")  # repo scope
        text = wait_for(sess, r"Proposed engine order:", 60, "order-proposal")
        assert "openrouter" in text, "proposal lacks openrouter"
        send(sess, "Enter")  # empty accepts the proposed order
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
        wait_for(sess, r"Local decision model tag", 60, "local-tag")
        send(sess, "Enter")  # empty takes nimble
        # Native pick appears only with a key in the environment.
        text = wait_for(
            sess,
            r"Pick the native Jev model|Print a one-line note",
            60,
            "native-or-skip",
        )
        if "Pick the native Jev model" in text.split("Local decision model tag")[-1]:
            time.sleep(3)  # let the radio options render past the title
            tail = pane_text(sess).split("Pick the native Jev model")[-1]
            assert "jev-1.13.0" in tail, "native radio lacks the pin"
            send(sess, "Enter")  # pin (default)
            wait_for(sess, r"Print a one-line note", 60, "skip-notes")
        send(sess, "Enter")  # skip notes stay on (default)
        wait_for(sess, r"Enter one directive per line", 60, "directives")
        send(sess, "Trivial asks go cheap.", "Enter")
        time.sleep(2)
        send(sess, "Enter")  # blank line finishes
        text = wait_for(sess, r"Routing strategy saved \(repo\)", 60, "saved")
        assert "Live catalog unreachable" not in text, "catalog fetch failed"
        assert "Decisions catalog unreachable" not in text, "decisions fetch failed"
        assert re.search(r"1 candidate, engine order ", text), "summary mismatch"
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
        write_strategy(
            workdir,
            (
                "candidates:\n"
                f"  - id: {RIG_NOVA_MICRO}\n"
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
            ),
        )
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert text.count(": ok") >= 2, "candidates not ok"
        send(sess, "/route on", "Enter")  # file landed after boot; enable explicitly
        wait_for(sess, r"Routing on", 60, "explicit-on")
        status_before = len(re.findall(r"Routing: ", pane_text(sess)))
        send(sess, "/route status", "Enter")
        text = wait_for_new(sess, r"Routing: ", 60, "status", before=status_before)
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
        cost_before = len(re.findall(r"Routing:", pane_text(sess)))
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 60, "cost-routing", before=cost_before)
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
        write_strategy(
            workdir,
            (
                "candidates:\n"
                f"  - id: {RIG_NOVA_MICRO}\n"
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
            ),
        )
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert "not in the cached decisions catalog" not in text, (
            "decision id cache miss"
        )
        send(sess, "/route on", "Enter")  # file landed after boot; enable explicitly
        wait_for(sess, r"Routing on", 60, "explicit-on")
        send(sess, "Reply with exactly these 3 words: alpha beta gamma", "Enter")
        text, _ = wait_routed(sess, 120, "routed-line")
        routed_line_with_confidences(text)
        assert "Routing held" not in text, "openrouter engine held current"
        text, _ = wait_main_end(sess)
        assert "alpha beta gamma" in text.lower(), "turn not served"
        cost_before = len(re.findall(r"Routing:", pane_text(sess)))
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 60, "cost-routing", before=cost_before)
        assert "via openrouter" in text, "decision engine not openrouter"
        assert re.search(r"\[model \d+%, effort \d+%]", text), (
            "cost entry lacks confidences"
        )
        assert re.search(r"via openrouter \$\d+\.\d{4}", text), "cost entry lacks spend"
        assert "[held]" not in text, "held marker in cost report"
        snap = pane_text(sess)
        routed_before = snap.count("Routed \u2192")
        off_before = len(re.findall(r"Routing off", pane_text(sess)))
        send(sess, "/route off", "Enter")
        wait_for_new(sess, r"Routing off", 60, "off", before=off_before)
        after_cost = len(COST_RE.findall(pane_text(sess)))
        send(sess, "Reply with exactly: offcheck", "Enter")
        text, _ = wait_main_end(sess, after=after_cost)
        assert text.count("Routed \u2192") == routed_before, "routed while off"
        on_before = len(re.findall(r"Routing on", pane_text(sess)))
        send(sess, "/route on", "Enter")
        wait_for_new(sess, r"Routing on", 60, "on", before=on_before)
        oncheck_cost_before = len(COST_RE.findall(pane_text(sess)))
        send(sess, "Reply with exactly: oncheck", "Enter")
        marked = text.count("Routed \u2192") + text.count("Routing held")
        text, _ = wait_routed(sess, 120, "routed-again", after=marked)
        final_cost_before = oncheck_cost_before
        if text.count("Routed \u2192") != routed_before + 1:
            # Transient decision-API failure holds (D-08); the product
            # retries next ask, so the rig gets one retry too.
            print("[r3] held once, retrying the ask", flush=True)
            assert HOLD_NOTE_RE.search(text), "hold note shape mismatch"
            held_text, _ = wait_main_end(sess, after=oncheck_cost_before)
            final_cost_before = len(COST_RE.findall(held_text))
            send(sess, "Reply with exactly: oncheck again", "Enter")
            marked = text.count("Routed \u2192") + text.count("Routing held")
            text, _ = wait_routed(sess, 120, "routed-retry", after=marked)
            assert text.count("Routed \u2192") == routed_before + 1, "no route after on"
        routed_line_with_confidences(text)
        wait_main_end(sess, after=final_cost_before)
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
        write_strategy(
            workdir,
            (
                "candidates:\n"
                f"  - id: {RIG_NOVA_MICRO}\n"
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
            ),
        )
        send(sess, "/route on", "Enter")
        wait_for(sess, r"Routing on", 60, "explicit-on")
        send(
            sess,
            "Write a pure-Python benchmark comparing JSON vs pickle across 5 payload sizes and PRINT the whole script plus predicted results — do not save or run anything, just output text, no tools",
            "Enter",
        )
        time.sleep(6)  # stagger: let the main decision finish first
        send(sess, "/btw Reply with exactly: sidecheck", "Enter")
        wait_for(sess, r"Side question noted", 60, "side-spawn")
        try:
            text, _ = wait_routed(sess, 60, "routed-btw", side=True)
        except AssertionError:
            # Transient decision-API failure holds silently on the side
            # path; each spawn decides once, so a second /btw retries.
            print("[r4] first spawn unmarked, sending a second /btw", flush=True)
            spawn_before = len(re.findall(r"Side question noted", pane_text(sess)))
            send(sess, "/btw Reply with exactly: sidecheck two", "Enter")
            wait_for_new(
                sess, r"Side question noted", 60, "side-spawn-2", before=spawn_before
            )
            text, _ = wait_routed(sess, 120, "routed-btw-2", side=True)
        routed_line_with_confidences(text, side=True)
        text, _ = wait_main_end(sess, timeout=300)
        assert "sidecheck" in text.lower(), "side answer not served"
        cost_before = len(re.findall(r"Routing:", pane_text(sess)))
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 120, "cost-routing", before=cost_before)
        assert "(btw)" in text, "no side-flagged cost entry"
        assert "via openrouter" in text, "side decision engine not openrouter"
        print("R4 PASS", flush=True)
    finally:
        save(sess, "r4", LOGDIR8)
        stop_cli(sess)
