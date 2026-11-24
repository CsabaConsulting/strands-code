"""Phase 13 upstream resync scenarios for the live-tmux UAT rig.

Owns scenario_u1 (Bedrock unary tool mode on Mistral Large 24.02 + Pixtral
Large 25.02 /model toggle), scenario_u2 (cross-family Sonnet -> Nova 2 Lite
--session-id resume + SDK model_info /context + InjectedBlock), and
scenario_u3 (1.65.0 PolicyHumanInTheLoop approval, policy [deny], and Plan-mode
deny). Uses XDG_CONFIG_HOME inside per-run /tmp workdirs so
~/.config/strands-code/config.yaml stays untouched while HOME keeps ~/.aws
credentials accessible.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    FAIL_RE,
    LOGDIR8,
    ensure_workdir,
    pane_text,
    save,
    send,
    start_cli,
    tmux,
    wait_for,
    wait_for_new,
)

RIG_MISTRAL_2402 = "mistral.mistral-large-2402-v1:0"
RIG_PIXTRAL_2502 = "us.mistral.pixtral-large-2502-v1:0"
RIG_SONNET_46 = "bedrock/us.anthropic.claude-sonnet-4-6"
RIG_NOVA_2_LITE = "bedrock/us.amazon.nova-2-lite-v1:0"
RIG_HAIKU_45 = "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"

SESSION_ID_RE = re.compile(r"Session ([0-9a-f-]{36})")
# Post-turn usage lines render either ``1.00K (1%) $0.00`` or unpriced
# ``1.00K (0%)`` (Nova 2 Lite has a 1M SDK window and no price table row).
USAGE_END_RE = re.compile(
    r"^\s*\d+(?:\.\d+)?[KM]?\s+\((?:\d+%|n/a)(?:,\s*\d+%\s+(?:cached|cache write))?\)(?:\s+\$\d+\.\d{2}(?:\s+actual)?)?\s*$",
    re.MULTILINE,
)


def _fresh_upstream_workdir(name: str) -> tuple[str, str]:
    """Reset one clean workdir + isolated XDG config dir under /tmp/uatr8."""
    path = ensure_workdir(name)
    for rel in (".agent/sessions", ".agent/session_index", ".xdg"):
        shutil.rmtree(os.path.join(path, rel), ignore_errors=True)
    for rel in (
        ".agent/MEMORY.md",
        ".agent/policy.toml",
        "sentinel.txt",
        "plan_blocked.txt",
    ):
        target = os.path.join(path, rel)
        if os.path.exists(target):
            os.remove(target)
    xdg = os.path.join(path, ".xdg")
    os.makedirs(os.path.join(xdg, "strands-code"), exist_ok=True)
    return path, xdg


def _write_xdg_model(xdg: str, model_id: str) -> None:
    """Point isolated XDG config.yaml at ``model_id`` without touching ~."""
    cfg = os.path.join(xdg, "strands-code", "config.yaml")
    with open(cfg, "w", encoding="utf-8") as handle:
        handle.write(f"model: {model_id}\n")


def _wait_idle_prompt(sess: str, timeout: int = 30) -> str:
    """Wait until the trailing prompt is idle, dismissing any Memory proposal."""
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if "Memory proposal" in "\n".join(lines[-12:]):
            send(sess, "Enter")
            time.sleep(2)
            continue
        if lines and lines[-1] == ">":
            time.sleep(2)
            refreshed = pane_text(sess)
            post_lines = [ln.rstrip() for ln in refreshed.splitlines() if ln.strip()]
            if (
                post_lines
                and post_lines[-1] == ">"
                and "Memory proposal" not in "\n".join(post_lines[-12:])
            ):
                return refreshed
        time.sleep(1)
    raise AssertionError("TIMEOUT waiting for idle prompt")


def _wait_turn_end(
    sess: str,
    *,
    after: int,
    timeout: int = 180,
    forbid_dialog_after: int | None = None,
) -> str:
    """Wait for a fresh trailing usage line; fail fast on errors or dialogs."""
    end = time.time() + timeout
    while time.time() < end:
        text = pane_text(sess)
        failed = FAIL_RE.search(text)
        if failed:
            raise AssertionError(
                f"Turn failed during upstream UAT: {failed.group(0)[:200]}"
            )
        if (
            forbid_dialog_after is not None
            and len(re.findall(r"Approve\?", text)) > forbid_dialog_after
        ):
            raise AssertionError("Unexpected approval dialog popped")
        if len(USAGE_END_RE.findall(text)) > after:
            return text
        time.sleep(2)
    raise AssertionError("TIMEOUT waiting for turn end")


def _stop_and_flush(sess: str) -> None:
    """Exit the CLI via Ctrl-D, wait briefly for session flush, and kill tmux."""
    try:
        send(sess, "C-d")
        end = time.time() + 20
        while time.time() < end:
            if "Session saved." in pane_text(sess):
                break
            time.sleep(1)
    finally:
        tmux("kill-session", "-t", sess)


def scenario_u1() -> None:
    """U1: Built-in Bedrock unary Converse tool mode on Mistral 24.02 + /model toggle."""
    workdir, xdg = _fresh_upstream_workdir("u1")
    with open(os.path.join(workdir, "sentinel.txt"), "w", encoding="utf-8") as handle:
        handle.write("UNARY_TOOL_SENTINEL_13\n")

    _write_xdg_model(xdg, RIG_MISTRAL_2402)
    sess = "uatr8u1"
    start_cli(sess, workdir, env_prefix=f"XDG_CONFIG_HOME={xdg} ")
    try:
        boot = " ".join(pane_text(sess).split())
        assert f"Note: streaming disabled for {RIG_MISTRAL_2402}" in boot, (
            "launch missing unary note"
        )
        assert "(Bedrock unary tool mode)." in boot, "launch note missing mode tag"
        assert "rejects tool use in streaming" not in boot, "obsolete warning printed"

        after = len(USAGE_END_RE.findall(pane_text(sess)))
        send(
            sess,
            "Use the read tool to read sentinel.txt in the current directory and reply with the exact token inside it.",
            "Enter",
        )
        text = _wait_turn_end(sess, after=after, timeout=180, forbid_dialog_after=0)
        assert "UNARY_TOOL_SENTINEL_13" in text, (
            f"Bedrock unary Converse tool turn missing sentinel: {text[-400:]}"
        )

        _wait_idle_prompt(sess)
        before_nova = len(re.findall(r"Model: ", pane_text(sess)))
        send(sess, f"/model {RIG_NOVA_2_LITE}", "Enter")
        switched_nova = wait_for_new(
            sess, r"Model: ", 30, "switch-nova", poll=1, before=before_nova
        )
        nova_tail = " ".join(switched_nova.split("Model:")[-1].split())
        assert "streaming disabled for" not in nova_tail, (
            f"Nova 2 Lite switch unexpectedly printed unary note: {nova_tail}"
        )

        before_pixtral = len(re.findall(r"Model: ", pane_text(sess)))
        send(sess, f"/model {RIG_PIXTRAL_2502}", "Enter")
        switched_pixtral = wait_for_new(
            sess, r"Model: ", 30, "switch-pixtral", poll=1, before=before_pixtral
        )
        pixtral_tail = " ".join(switched_pixtral.split("Model:")[-1].split())
        assert f"Note: streaming disabled for {RIG_PIXTRAL_2502}" in pixtral_tail
        assert "(Bedrock unary tool mode)." in pixtral_tail
        print("U1 PASS", flush=True)
    finally:
        save(sess, "u1", LOGDIR8)
        _stop_and_flush(sess)


def scenario_u2() -> None:
    """U2: Cross-family Sonnet -> Nova 2 Lite --session-id resume + /context."""
    workdir, xdg = _fresh_upstream_workdir("u2")
    with open(
        os.path.join(workdir, ".agent", "MEMORY.md"), "w", encoding="utf-8"
    ) as handle:
        handle.write("# Notes\n- Project codename: UAT_MEM_ALPHA_13\n")

    _write_xdg_model(xdg, RIG_SONNET_46)
    sess1 = "uatr8u2a"
    start_cli(sess1, workdir, env_prefix=f"XDG_CONFIG_HOME={xdg} ")
    try:
        match = SESSION_ID_RE.search(pane_text(sess1))
        assert match, "missing session UUID on boot"
        sid = match.group(1)

        before_ctx = len(re.findall(r"Context — ", pane_text(sess1)))
        send(sess1, "/context", "Enter")
        ctx1 = wait_for_new(sess1, r"Context — ", 30, "ctx1", poll=1, before=before_ctx)
        assert "of 1.00M" in ctx1, (
            f"expected 1.00M SDK window in /context: {ctx1[-300:]}"
        )

        after = len(USAGE_END_RE.findall(pane_text(sess1)))
        send(
            sess1,
            "Think step by step: what is 17 * 23? Reply with the number only, without using any tools.",
            "Enter",
        )
        text1 = _wait_turn_end(sess1, after=after, timeout=180, forbid_dialog_after=0)
        assert "391" in text1, f"expected 391 from Sonnet: {text1[-300:]}"
        save(sess1, "u2-s1", LOGDIR8)
    finally:
        _stop_and_flush(sess1)

    _write_xdg_model(xdg, RIG_NOVA_2_LITE)
    sess2 = "uatr8u2b"
    start_cli(
        sess2,
        workdir,
        env_prefix=f"XDG_CONFIG_HOME={xdg} ",
        cli_args=f"--session-id {sid}",
    )
    try:
        assert sid in pane_text(sess2), f"resumed session id {sid} missing from banner"
        after = len(USAGE_END_RE.findall(pane_text(sess2)))
        send(
            sess2,
            "What number did you calculate in our previous turn? Reply with the number only, no tools.",
            "Enter",
        )
        text2 = _wait_turn_end(sess2, after=after, timeout=180, forbid_dialog_after=0)
        assert "391" in text2, f"Nova 2 Lite missed resumed calculation: {text2[-300:]}"

        _wait_idle_prompt(sess2)
        before_ctx2 = len(re.findall(r"Context — ", pane_text(sess2)))
        send(sess2, "/context", "Enter")
        ctx2 = wait_for_new(
            sess2, r"Context — ", 30, "ctx2", poll=1, before=before_ctx2
        )
        tail = ctx2.split("Context — ")[-1]
        assert RIG_NOVA_2_LITE in tail and "of 1.00M" in tail, (
            f"expected {RIG_NOVA_2_LITE} 1.00M window in /context: {tail}"
        )
        print("U2 PASS", flush=True)
    finally:
        save(sess2, "u2", LOGDIR8)
        _stop_and_flush(sess2)


def scenario_u3() -> None:
    """U3: Live 1.65.0 PolicyHumanInTheLoop approval, [deny] rule, and Plan mode."""
    workdir, xdg = _fresh_upstream_workdir("u3")
    with open(
        os.path.join(workdir, ".agent", "policy.toml"), "w", encoding="utf-8"
    ) as handle:
        handle.write('[[deny]]\ntool = "shell"\ncommand = "uname"\n')
    _write_xdg_model(xdg, RIG_HAIKU_45)
    sess = "uatr8u3"
    start_cli(sess, workdir, env_prefix=f"XDG_CONFIG_HOME={xdg} ")
    try:
        # Part A: interactive HITL approval -> Proceed -> shell executes
        after = len(USAGE_END_RE.findall(pane_text(sess)))
        send(sess, "Run the shell command: echo HITL_OK_13", "Enter")
        wait_for(
            sess,
            r"Approve\? \[main\] shell — echo HITL_OK_13",
            90,
            "hitl-dialog",
            poll=1,
        )
        send(sess, "Up")
        time.sleep(0.5)
        send(sess, "Enter")
        text_a = _wait_turn_end(sess, after=after, timeout=180)
        assert "HITL_OK_13" in text_a, f"approved shell output missing: {text_a[-400:]}"

        # Part B: explicit [deny] rule short-circuits without prompting
        after_b = len(USAGE_END_RE.findall(pane_text(sess)))
        dialogs_before_b = len(re.findall(r"Approve\?", pane_text(sess)))
        send(sess, "Use the shell tool right now to run: uname -a", "Enter")
        text_b = _wait_turn_end(
            sess, after=after_b, timeout=180, forbid_dialog_after=dialogs_before_b
        )
        assert "Denied by policy rule" in text_b and "uname" in text_b, (
            f"policy deny refusal missing: {text_b[-400:]}"
        )

        # Part C: Plan mode blocks mutations without prompting or writing files
        before_mode = len(re.findall(r"Mode: plan", pane_text(sess)))
        send(sess, "/mode plan", "Enter")
        wait_for_new(sess, r"Mode: plan", 30, "plan-mode", poll=1, before=before_mode)
        after_c = len(USAGE_END_RE.findall(pane_text(sess)))
        dialogs_before_c = len(re.findall(r"Approve\?", pane_text(sess)))
        send(
            sess,
            "Attempt to use the write tool to create plan_blocked.txt with content hello.",
            "Enter",
        )
        _wait_turn_end(
            sess, after=after_c, timeout=180, forbid_dialog_after=dialogs_before_c
        )
        assert not os.path.exists(os.path.join(workdir, "plan_blocked.txt")), (
            "plan mode allowed file write!"
        )
        print("U3 PASS", flush=True)
    finally:
        save(sess, "u3", LOGDIR8)
        _stop_and_flush(sess)
