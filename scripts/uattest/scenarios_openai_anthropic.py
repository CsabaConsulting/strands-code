"""Phase 15 OpenAI and Anthropic zero-AWS scenarios for the live-tmux UAT rig.

Owns scenario_o1 and scenario_an1: launches strands-code with AWS
credentials stripped and isolated XDG_CONFIG_HOME, boots native OpenAI
and Anthropic models, verifies --model writes no config.yaml, checks
/context (~1M), runs a read tool turn, checks /cost pricing, and performs
a same-provider /model switch.
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

RIG_OPENAI_PRIMARY = "openai/gpt-6.1-sol"
RIG_OPENAI_SECONDARY = "openai/gpt-6.1-terra"
RIG_ANTHROPIC_PRIMARY = "anthropic/claude-sonnet-5-5"
RIG_ANTHROPIC_SECONDARY = "anthropic/claude-haiku-5-5"


def _run_provider_rig(
    *,
    name: str,
    primary: str,
    secondary: str,
    sentinel: str,
    expected_window: str,
) -> None:
    """Execute a shared zero-AWS / isolated-XDG native provider UAT flow."""
    workdir, xdg = _fresh_upstream_workdir(name)
    sentinel_path = os.path.join(workdir, "sentinel.txt")
    with open(sentinel_path, "w", encoding="utf-8") as handle:
        handle.write(f"{sentinel}\n")

    cfg_path = os.path.join(xdg, "strands-code", "config.yaml")
    env_prefix = (
        "env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY "
        "-u AWS_SESSION_TOKEN -u AWS_PROFILE -u AWS_DEFAULT_PROFILE "
        f"UV_NO_SYNC=1 XDG_CONFIG_HOME={xdg} "
    )
    sess = f"uatr8{name}"
    start_cli(
        sess,
        workdir,
        env_prefix=env_prefix,
        cli_args=f"--model {primary}",
    )
    try:
        ctx_n = len(re.findall(r"Context — ", pane_text(sess)))
        send(sess, "/context", "Enter")
        ctx_text = wait_for_new(
            sess, r"Context — ", 30, "context", poll=1, before=ctx_n
        )
        assert f"Context — {primary}" in ctx_text, (
            f"/context missing active model {primary}"
        )
        assert expected_window in ctx_text, (
            f"/context missing expected window {expected_window}"
        )
        assert not os.path.exists(cfg_path), (
            "--model must stay session-scoped without writing config.yaml"
        )

        after = len(USAGE_END_RE.findall(pane_text(sess)))
        send(
            sess,
            f"Use the read tool to read {sentinel_path} and reply with the exact token inside it.",
            "Enter",
        )
        turn_text = _wait_turn_end(sess, after=after, timeout=180)
        assert sentinel in turn_text, f"{name} read turn did not return {sentinel}"

        cost_n = pane_text(sess).count("Display only")
        send(sess, "/cost", "Enter")
        cost_text = wait_for_new(
            sess, r"Display only", 20, "cost", poll=1, before=cost_n
        )
        assert f"Cost — {primary}" in cost_text, f"/cost missing active model {primary}"
        assert "$" in cost_text and "Display only" in cost_text, (
            "/cost missing USD spend display"
        )

        sw_n = pane_text(sess).count(f"Model: {secondary}")
        send(sess, f"/model {secondary}", "Enter")
        sw_text = wait_for_new(
            sess,
            re.escape(f"Model: {secondary}"),
            30,
            "switch",
            poll=1,
            before=sw_n,
        )
        assert f"Model: {secondary}" in sw_text
        assert "Dropping reasoningContent" not in sw_text, (
            f"Same-provider switch {primary} -> {secondary} dropped reasoningContent"
        )
    finally:
        save(sess, name, LOGDIR8)
        _stop_and_flush(sess)


def scenario_o1() -> None:
    """O1: Zero-AWS OpenAI GPT-6.1 Sol launch, tool turn, /context, /cost, /model."""
    _run_provider_rig(
        name="o1",
        primary=RIG_OPENAI_PRIMARY,
        secondary=RIG_OPENAI_SECONDARY,
        sentinel="OPENAI_SENTINEL_15",
        expected_window="of 1.05M",
    )
    print("O1 PASS", flush=True)


def scenario_an1() -> None:
    """AN1: Zero-AWS Anthropic Claude Sonnet 5.5 launch, tool turn, /context, /cost, /model."""
    _run_provider_rig(
        name="an1",
        primary=RIG_ANTHROPIC_PRIMARY,
        secondary=RIG_ANTHROPIC_SECONDARY,
        sentinel="ANTHROPIC_SENTINEL_15",
        expected_window="of 1.00M",
    )
    print("AN1 PASS", flush=True)
