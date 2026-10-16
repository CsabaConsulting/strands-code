"""Phase 9 native-engine scenarios for the live-tmux UAT rig (D-14).

Owns scenario_n1/n2/n3/n4 plus the native pin/snapshot constants and
setup helpers; tmux/send/wait/save plumbing comes from uattest_lib and
the routing helpers from scenarios_routing, all as absolute sibling
imports (CF-07 option (a)).
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios_routing import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    current_model_from_boot,
    routed_line_with_confidences,
    strategy_order,
    strategy_text,
    wait_routed,
    write_strategy,
)
from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    LOGDIR8,
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
)

NATIVE_PIN = "jev-1.13.0"
"""Pinned Jev build the native rig rows expect (09 pin)."""

NATIVE_SNAPSHOT = "jev-1.13.0"
"""Serving snapshot the validate ping must name (drift fails loudly)."""

BOGUS_TYPESAFE_KEY = "probe-bogus-key"
"""Bogus key value for the bad-key row — never real key material."""


def _setup_single_cheapest_candidate(sess):
    """Cheapest chat-catalog pick plus Done; asserts live prices."""
    text = wait_for(sess, r"Pick a candidate model", 120, "candidate-radio")
    assert "per 1M" in text, "candidate radio lacks live prices (typed fallback?)"
    send(sess, "Enter")  # cheapest first
    for _ in range(3):  # Done radio (same title) until the next prompt
        time.sleep(4)
        text = pane_text(sess)
        if "Pick the decision model" in text:
            return
        assert "Pick a candidate model" in text, "lost the setup flow"
        send(sess, "Enter")  # Done is the default once picks exist
    raise AssertionError("decision radio never arrived")


def _setup_finish_directives(sess, line="Trivial asks go cheap."):
    """One directive line plus the blank-line finish."""
    wait_for(sess, r"Enter one directive per line", 60, "directives")
    send(sess, line, "Enter")
    time.sleep(2)
    send(sess, "Enter")  # blank line finishes


def scenario_n1():
    """N1: setup with a key proposes the native-first order.

    Accepts the proposal and completes setup; the saved file must
    carry order [native, openrouter, local] with the pinned Jev id
    and no key material, and validate must report VALID with the
    native ping naming the serving snapshot.
    """
    workdir = ensure_workdir("w5")
    sess = "uatr8n1"
    start_cli(sess, workdir)
    try:
        send(sess, "/route setup", "Enter")
        wait_for(sess, r"Where should the strategy live", 60, "scope-radio")
        send(sess, "Down", "Enter")  # repo scope
        text = wait_for(sess, r"Proposed engine order:", 60, "order-proposal")
        assert "native, openrouter, local" in text, (
            f"key-present proposal not native-first: {text[-300:]}"
        )
        assert "native first" in text, "proposal lacks the key-found note"
        send(sess, "Enter")  # empty accepts the proposed order
        _setup_single_cheapest_candidate(sess)
        time.sleep(4)  # let the decision options render past the title
        text = pane_text(sess)
        tail = text.split("Pick the decision model")[-1]
        assert "per 1M" in tail, "decision radio lacks live prices (typed fallback?)"
        send(sess, "Enter")  # cheapest decisions-catalog entry
        wait_for(sess, r"Local decision model tag", 60, "local-tag")
        send(sess, "Enter")  # empty takes nimble
        text = wait_for(sess, r"Pick the native Jev model", 60, "native-radio")
        time.sleep(3)  # let the radio options render past the title
        tail = pane_text(sess).split("Pick the native Jev model")[-1]
        assert NATIVE_PIN in tail, "native radio lacks the pin"
        send(sess, "Enter")  # pin (default)
        wait_for(sess, r"Print a one-line note", 60, "skip-notes")
        send(sess, "Enter")  # skip notes stay on (default)
        _setup_finish_directives(sess)
        text = wait_for(sess, r"Routing strategy saved \(repo\)", 60, "saved")
        assert "1 candidate, engine order native, openrouter, local" in text, (
            "summary mismatch"
        )
        saved = strategy_text(workdir)
        assert "api_key" not in saved, "key material in strategy file"
        assert strategy_order(workdir) == ["native", "openrouter", "local"]
        assert f"native_model: {NATIVE_PIN}" in saved, "pin not saved"
        send(sess, "/cost refresh", "Enter")
        wait_for(sess, r"OpenRouter:", 120, "refresh-done")
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert f"native: engine ok (snapshot {NATIVE_SNAPSHOT})" in text, (
            "ping did not name the snapshot"
        )
        assert "SKIP" not in text and "INVALID" not in text, "validate flags set"
        print("N1 PASS", flush=True)
    finally:
        save(sess, "n1", LOGDIR8)
        stop_cli(sess)


def scenario_n2():
    """N2: setup without a key hides native everywhere.

    Boots keyless; the proposal must exclude native with the hidden
    note, the declined-proposal builder must offer no native option,
    and the saved file must carry no native keys.
    """
    workdir = ensure_workdir("w6")
    sess = "uatr8n2"
    start_cli(sess, workdir, env_prefix="env -u TYPESAFE_API_KEY ")
    try:
        send(sess, "/route setup", "Enter")
        wait_for(sess, r"Where should the strategy live", 60, "scope-radio")
        send(sess, "Down", "Enter")  # repo scope
        text = wait_for(sess, r"Proposed engine order:", 60, "order-proposal")
        assert "Proposed engine order: openrouter, local" in text, (
            f"keyless proposal wrong: {text[-300:]}"
        )
        assert "native hidden" in text, "proposal lacks the hidden note"
        send(sess, "no", "Enter")  # decline into the order builder
        wait_for(sess, r"Primary decision engine", 60, "primary-radio")
        time.sleep(3)  # let the radio options render past the title
        tail = pane_text(sess).split("Primary decision engine")[-1]
        assert "native" not in tail.lower(), "builder offers native without a key"
        send(sess, "Enter")  # openrouter primary
        wait_for(sess, r"Add a fallback engine", 60, "fallback-radio")
        send(sess, "Enter")  # Done is the default: order [openrouter]
        _setup_single_cheapest_candidate(sess)
        time.sleep(4)
        send(sess, "Enter")  # cheapest decisions-catalog entry
        # Order [openrouter]: no local tag, no native pick follow.
        wait_for(sess, r"Print a one-line note", 60, "skip-notes")
        send(sess, "Enter")  # skip notes stay on (default)
        _setup_finish_directives(sess)
        text = wait_for(sess, r"Routing strategy saved \(repo\)", 60, "saved")
        assert "1 candidate, engine order openrouter" in text, "summary mismatch"
        saved = strategy_text(workdir)
        assert "api_key" not in saved, "key material in strategy file"
        assert strategy_order(workdir) == ["openrouter"]
        assert "native_model" not in saved, "native leaked into the file"
        print("N2 PASS", flush=True)
    finally:
        save(sess, "n2", LOGDIR8)
        stop_cli(sess)


def _native_strategy(current):
    """Hand-written native-first strategy (manual-edit path, like r2)."""
    return (
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
        "  order: [native]\n"
        f"  native_model: {NATIVE_PIN}\n"
    )


def scenario_n3():
    """N3: validate pings native ok, and fails a bad key loudly.

    Hand-written native strategy: with the real ambient key the
    ping must name the serving snapshot under a VALID head; rebooted
    with a bogus key the same file must flip to INVALID with the
    key fix line.
    """
    workdir = ensure_workdir("w7")
    sess = "uatr8n3"
    start_cli(sess, workdir)
    try:
        current = current_model_from_boot(pane_text(sess))
        write_strategy(workdir, _native_strategy(current))
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy VALID", 60, "valid")
        assert f"native: engine ok (snapshot {NATIVE_SNAPSHOT})" in text, (
            "ping did not name the snapshot"
        )
        assert "SKIP" not in text and "INVALID" not in text, "validate flags set"
        save(sess, "n3-ok", LOGDIR8)
        stop_cli(sess)
        start_cli(
            sess,
            workdir,
            env_prefix=f"TYPESAFE_API_KEY={BOGUS_TYPESAFE_KEY} ",
        )
        send(sess, "/route validate", "Enter")
        text = wait_for(sess, r"Routing strategy INVALID", 60, "invalid")
        assert "TypeSafe key rejected (HTTP 401)" in text, "bad key not loud"
        assert "fix: set TYPESAFE_API_KEY to a valid key" in text, (
            "key fix line missing"
        )
        print("N3 PASS", flush=True)
    finally:
        save(sess, "n3", LOGDIR8)
        stop_cli(sess)


def scenario_n4():
    """N4: a native-first ask routes with the routed transcript line.

    The ask must print ``Routed`` with both confidences, and /cost
    must show the decision ``via native`` with a spend cell — never
    held, never spend-silent. (The computed-rate Prices marker is a
    unit-pinned single-source line; live turns fold it into mixed.)
    """
    workdir = ensure_workdir("w8")
    sess = "uatr8n4"
    start_cli(sess, workdir)
    try:
        current = current_model_from_boot(pane_text(sess))
        write_strategy(workdir, _native_strategy(current))
        send(sess, "/route on", "Enter")  # file landed after boot; enable explicitly
        wait_for(sess, r"Routing on", 60, "explicit-on")
        # A mid ask, not the r2 trivial ask: Jev reads the trivial
        # ask 50/50 (trivial -> tiny vs directives -> current) and
        # holds 2/2, while the debug ask routes current at 0.95.
        send(
            sess,
            "Debug the intermittent timeout failure in the API client test suite and propose a fix. Answer from general knowledge only; do not read, list, or run anything. End your reply with exactly: debugdone",
            "Enter",
        )
        text, _ = wait_routed(sess, 120, "routed-line")
        routed_line_with_confidences(text)
        assert "Routing held" not in text, "native engine held current"
        text, _ = wait_main_end(sess)
        assert "debugdone" in text.lower(), "turn not served"
        cost_before = len(re.findall(r"Routing:", pane_text(sess)))
        send(sess, "/cost", "Enter")
        text = wait_for_new(sess, r"Routing:", 60, "cost-routing", before=cost_before)
        assert "via native" in text, "decision engine not native"
        assert re.search(r"via native \$\d+\.\d{4}", text), "cost entry lacks spend"
        assert "[held]" not in text, "held marker in cost report"
        print("N4 PASS", flush=True)
    finally:
        save(sess, "n4", LOGDIR8)
        stop_cli(sess)
