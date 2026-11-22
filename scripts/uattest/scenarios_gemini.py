"""Phase 14 Google Gemini zero-AWS scenario for the live-tmux UAT rig.

Owns scenario_g1: launches strands-code with AWS credentials stripped and
isolated XDG_CONFIG_HOME, boots --model google/gemini-2.5-flash, checks
/context (1M), runs a read tool turn, checks /cost pricing, switches to
google/gemini-2.5-pro, and verifies session-scoped startup wrote no config.yaml.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios_upstream import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    USAGE_END_RE,
    _fresh_upstream_workdir,
    _stop_and_flush,
    _wait_turn_end,
)
from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    LOGDIR8,
    pane_text,
    save,
    send,
    start_cli,
    wait_for_new,
)

RIG_GEMINI_FLASH = "google/gemini-2.5-flash"
RIG_GEMINI_PRO = "google/gemini-2.5-pro"


def scenario_g1() -> None:
    """G1: Zero-AWS Gemini 2.5 Flash launch, tool turn, /context, /cost, and /model."""
    workdir, xdg = _fresh_upstream_workdir("g1")
    with open(os.path.join(workdir, "sentinel.txt"), "w", encoding="utf-8") as handle:
        handle.write("GEMINI_SENTINEL_14\n")

    cfg_path = os.path.join(xdg, "strands-code", "config.yaml")
    env_prefix = (
        "env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY "
        "-u AWS_SESSION_TOKEN -u AWS_PROFILE -u AWS_DEFAULT_PROFILE "
        f"UV_NO_SYNC=1 XDG_CONFIG_HOME={xdg} "
    )
    sess = "uatr8g1"
    start_cli(
        sess,
        workdir,
        env_prefix=env_prefix,
        cli_args=f"--model {RIG_GEMINI_FLASH}",
    )
    try:
        ctx_n = len(re.findall(r"Context — ", pane_text(sess)))
        send(sess, "/context", "Enter")
        ctx_text = wait_for_new(
            sess, r"Context — ", 30, "context", poll=1, before=ctx_n
        )
        assert "gemini-2.5-flash" in ctx_text, "/context missing active Gemini model"
        assert "of 1.05M" in ctx_text or "of 1.00M" in ctx_text, (
            "/context missing 1M Gemini window"
        )

        after = len(USAGE_END_RE.findall(pane_text(sess)))
        send(
            sess,
            "Use the read tool to read sentinel.txt in the current directory and reply with the exact token inside it.",
            "Enter",
        )
        turn_text = _wait_turn_end(sess, after=after, timeout=180)
        assert "GEMINI_SENTINEL_14" in turn_text, (
            "Gemini read turn did not return GEMINI_SENTINEL_14"
        )

        cost_n = pane_text(sess).count("Display only")
        send(sess, "/cost", "Enter")
        cost_text = wait_for_new(
            sess, r"Display only", 20, "cost", poll=1, before=cost_n
        )
        assert "$" in cost_text and "Display only" in cost_text, (
            "/cost missing USD spend display"
        )

        sw_n = pane_text(sess).count(f"Model: {RIG_GEMINI_PRO}")
        send(sess, f"/model {RIG_GEMINI_PRO}", "Enter")
        sw_text = wait_for_new(
            sess,
            re.escape(f"Model: {RIG_GEMINI_PRO}"),
            30,
            "switch",
            poll=1,
            before=sw_n,
        )
        assert f"Model: {RIG_GEMINI_PRO}" in sw_text

        save(sess, "g1", LOGDIR8)
    finally:
        _stop_and_flush(sess)
    assert not os.path.exists(cfg_path), (
        "--model must stay session-scoped without writing config.yaml"
    )
    print("G1 PASS", flush=True)
