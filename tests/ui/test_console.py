"""Wave 0 tests for shared UI console, lock, and display sanitizers (`ui/console.py`)."""

from __future__ import annotations

from strands_code_cli.ui.console import (
    RENDER_LOCK,
    console,
    sanitize_display,
    sanitize_line,
    sanitize_multiline,
    stderr_console,
)


class TestUiConsole:
    def test_console_exports_and_reentrant_render_lock(self):
        assert console is not None
        assert stderr_console is not None
        assert stderr_console.stderr is True
        with RENDER_LOCK:
            with RENDER_LOCK:
                pass

    def test_sanitize_display_strips_ansi_osc_controls_keeps_brackets_and_truncates(
        self,
    ):
        raw = "\x1b[31mEvil\x1b[0m \x1b]0;WindowTitle\x07\x1b]8;;https://x\x1b\\link\x1b]8;;\x1b\\ \t[red]text\x00\x1f\x7f  über"
        cleaned = sanitize_display(raw)
        assert "\x1b" not in cleaned
        assert "\x00" not in cleaned
        assert "\x1f" not in cleaned
        assert "\x7f" not in cleaned
        assert "WindowTitle" not in cleaned
        assert "[red]text" in cleaned
        assert "über" in cleaned

        long_text = "word " * 100
        truncated = sanitize_display(long_text, max_len=30)
        assert len(truncated) <= 30
        assert truncated.endswith("...")

    def test_sanitize_line_preserves_indentation_and_strips_escapes(self):
        raw = "  \t\x1b[32mif ok:\x1b[0m # keep [tag]\x00\x07"
        cleaned = sanitize_line(raw)
        assert cleaned.startswith("  ")
        assert "\x1b" not in cleaned
        assert "\x00" not in cleaned
        assert "\x07" not in cleaned
        assert "\t" not in cleaned
        assert "if ok: # keep [tag]" in cleaned

    def test_sanitize_strips_ecma48_c1_dcs_apc_charset_and_bidi_controls(self):
        cases = (
            ("\x1b[>4;2mhello", "hello"),
            ("\x1b[38:2:255:0:0mhello\x1b[0m", "hello"),
            ("\x9b31mhello\x9b0m", "hello"),
            ("\x9d0;evil-title\x9chello", "hello"),
            ("\x1bP+q544e\x1b\\hello", "hello"),
            ("\x1b_Ga=T,f=32\x1b\\hello", "hello"),
            ("\x1b(0hello", "hello"),
            ("\x1b]52;c;cHdu", ""),
            ("safe\u202eevil\u2066x\u2069", "safeevilx"),
        )
        for poisoned, expected in cases:
            assert sanitize_display(poisoned) == expected
            assert sanitize_line(poisoned) == expected
            assert sanitize_multiline(poisoned) == expected
        assert sanitize_multiline("harmless\rSPOOFED") == "harmlessSPOOFED"
        assert sanitize_multiline("a\nb\tc") == "a\nb\tc"
