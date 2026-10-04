"""Loader + merge tests for user capability overrides (aider-style)."""

import pytest

from strands_code_cli.model_capabilities import (
    CapabilityOverride,
    _reset_overrides_cache,
    active_overrides,
    load_capability_overrides,
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    _reset_overrides_cache()
    yield
    _reset_overrides_cache()


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


class TestLoader:
    def test_valid_file_parses(self, tmp_path):
        path = _write(
            tmp_path / "caps.yaml",
            "overrides:\n"
            "  - match: {provider: bedrock, vendor: amazon, family: nova}\n"
            "    reasoning: true\n"
            "  - match: {name_contains: gpt-oss}\n"
            "    media: true\n",
        )
        rules = load_capability_overrides(path)
        assert rules == [
            CapabilityOverride(provider="bedrock", vendor="amazon", family="nova", reasoning=True),
            CapabilityOverride(name_contains="gpt-oss", media=True),
        ]

    def test_missing_file_is_empty(self, tmp_path):
        assert load_capability_overrides(tmp_path / "nope.yaml") == []

    def test_malformed_yaml_is_empty(self, tmp_path):
        path = _write(tmp_path / "caps.yaml", "overrides: [unclosed\n")
        assert load_capability_overrides(path) == []

    def test_unknown_match_key_skips_entry(self, tmp_path):
        path = _write(
            tmp_path / "caps.yaml",
            "overrides:\n"
            "  - match: {vender: amazon}\n"  # typo must not widen the rule
            "    reasoning: true\n"
            "  - match: {vendor: amazon}\n"
            "    reasoning: false\n",
        )
        assert load_capability_overrides(path) == [
            CapabilityOverride(vendor="amazon", reasoning=False)
        ]

    def test_non_bool_effect_skips_entry(self, tmp_path):
        path = _write(
            tmp_path / "caps.yaml",
            "overrides:\n  - match: {vendor: amazon}\n    reasoning: sometimes\n",
        )
        assert load_capability_overrides(path) == []

    def test_symlink_refused(self, tmp_path):
        target = _write(tmp_path / "real.yaml", "overrides: []\n")
        link = tmp_path / "link.yaml"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlink"):
            load_capability_overrides(link)

    def test_cache_loads_once_until_reset(self, tmp_path, monkeypatch):
        import strands_code_cli.model_capabilities as caps

        path = _write(tmp_path / "caps.yaml", "overrides: []\n")
        monkeypatch.setattr(caps, "default_capabilities_path", lambda: path)
        assert active_overrides() == []
        _write(path, "overrides:\n  - match: {}\n    reasoning: true\n")
        assert active_overrides() == []  # stale until reset
        _reset_overrides_cache()
        assert active_overrides() == [CapabilityOverride(reasoning=True)]


class TestMerge:
    def test_override_beats_harness_both_directions(self, monkeypatch):
        import strands_code_cli.model_capabilities as caps
        from strands_code_cli.model_switch import supports_media, supports_reasoning

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [
                CapabilityOverride(vendor="google", reasoning=True),
                CapabilityOverride(vendor="anthropic", reasoning=False),
                CapabilityOverride(name_contains="gpt-oss", media=True),
            ],
        )
        assert supports_reasoning("google.gemma-3-27b-it") is True  # enabled by user
        assert supports_reasoning("bedrock/anthropic.claude-opus-5") is False  # disabled
        assert supports_media("bedrock/openai.gpt-oss-120b-1:0") is True  # enabled

    def test_first_match_wins_per_field(self, monkeypatch):
        import strands_code_cli.model_capabilities as caps
        from strands_code_cli.model_switch import supports_reasoning

        monkeypatch.setattr(
            caps,
            "active_overrides",
            lambda: [
                CapabilityOverride(media=False),  # matches all, but silent on reasoning
                CapabilityOverride(reasoning=True),
            ],
        )
        assert supports_reasoning("google.gemma-3-27b-it") is True

    def test_context_report_counts_overrides(self, monkeypatch):
        from types import SimpleNamespace

        import strands_code_cli.model_capabilities as caps
        from strands_code_cli.cost_context import context_report

        monkeypatch.setattr(caps, "active_overrides", lambda: [CapabilityOverride()])
        report = context_report(SimpleNamespace(messages=[]), "bedrock/x")
        assert "capability overrides: 1 active" in report
        monkeypatch.setattr(caps, "active_overrides", lambda: [])
        assert "capability overrides" not in context_report(
            SimpleNamespace(messages=[]), "bedrock/x"
        )
