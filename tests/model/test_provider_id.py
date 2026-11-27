"""Wave 0 unit tests for canonical provider_of() identification (PARITY-01, D-06)."""

from __future__ import annotations

import pytest


class TestProviderId:
    @pytest.mark.parametrize(
        ("model_id", "unwrap", "expected"),
        [
            (None, False, "bedrock"),
            ("", False, "bedrock"),
            ("   ", True, "bedrock"),
            ("us.anthropic.claude-sonnet-4-6", False, "bedrock"),
            ("arn:aws:bedrock:us-west-2:123:inference-profile/x", False, "bedrock"),
            ("bedrock/anthropic.claude-sonnet-4-6", False, "bedrock"),
            ("bedrock-mantle/openai.gpt-6.2-sol", False, "bedrock-mantle"),
            ("bedrock-mantle/openai.gpt-6.2-sol", True, "bedrock-mantle"),
            ("Google/gemini-3.8-flash", False, "google"),
            ("openai/gpt-6.2-sol", False, "openai"),
            ("anthropic/claude-sonnet-5-5", False, "anthropic"),
            ("meta/muse-spark-1.3-contributor", False, "meta"),
            ("ollama/qwen3:8b", False, "ollama"),
            ("litellm/openrouter/anthropic/claude-sonnet-4.6", False, "litellm"),
            ("litellm/openrouter/anthropic/claude-sonnet-4.6", True, "openrouter"),
            ("litellm/ollama/qwen3:8b", False, "litellm"),
            ("litellm/ollama/qwen3:8b", True, "ollama"),
            ("litellm/ollama_chat/llama3.2", False, "litellm"),
            ("litellm/ollama_chat/llama3.2", True, "ollama"),
            ("litellm/anthropic/claude-sonnet-4-6", False, "litellm"),
            ("litellm/anthropic/claude-sonnet-4-6", True, "litellm"),
        ],
    )
    def test_provider_of_canonical_cases(self, model_id, unwrap, expected):
        from strands_code_cli.model.provider_id import provider_of

        assert provider_of(model_id, unwrap_litellm=unwrap) == expected

    def test_scoped_base_url_blocks_litellm_cross_provider_leak(self):
        from strands_code_cli.model.model_switch import scoped_base_url

        url = "http://127.0.0.1:4000/v1"
        assert scoped_base_url(url, "litellm", "litellm/custom/foo") == url
        assert (
            scoped_base_url(url, "litellm", "litellm/anthropic/claude-sonnet-4-6")
            == url
        )
        assert (
            scoped_base_url(url, "litellm", "litellm/openrouter/openai/gpt-4o") is None
        )
        assert scoped_base_url(url, "litellm", "litellm/ollama/qwen3:8b") is None
        assert scoped_base_url(url, "openrouter", "litellm/openrouter/a/b") == url
        assert scoped_base_url(url, "openrouter", "litellm/anthropic/c") is None
