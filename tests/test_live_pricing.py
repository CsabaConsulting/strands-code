"""Live price/window layers: tier filtering, matching, cache, fallthrough."""

import json
import sys
import types

import pytest

from strands_code_cli import cost_context, live_pricing

# Real Price List records (us-west-2, pub 2026-10-03), trimmed to the
# fields the parser reads. Standard Mistral Large 3: $0.50 in / $1.50
# out per 1M; every other tier must be rejected.
_FIXTURES = (
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-input-tokens-priority", "0.0008800000"),
    ("USW2-Mistral-Large-3-675b-Instruct-output-tokens-batch", "0.0007500000"),
    ("USW2-Mistral-Large-3-675b-Instruct-output-tokens-flex", "0.0007500000"),
    ("USW2-Mistral-Large-3-675b-Instruct-input-tokens", "0.0005000000"),
    ("USW2-Mistral-Large-3-675b-Instruct-input-tokens-flex", "0.0002500000"),
    ("USW2-Mistral-Large-3-675b-Instruct-output-tokens", "0.0015000000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-output-tokens-flex", "0.0007500000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-output-tokens-standard", "0.0015000000"),
    ("USW2-Mistral-Large-3-675b-Instruct-input-tokens-priority", "0.0008800000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-output-tokens-batch", "0.0007500000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-input-tokens-standard", "0.0005000000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-input-tokens-flex", "0.0002500000"),
    ("USW2-Mistral-Large-3-675b-Instruct-output-tokens-priority", "0.0026300000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-output-tokens-priority", "0.0026300000"),
    ("USW2-mistral.mistral-large-3-675b-instruct-mantle-input-tokens-batch", "0.0002500000"),
    ("USW2-Mistral-Large-3-675b-Instruct-input-tokens-batch", "0.0002500000"),
    ("USW2-Claude3Sonnet-input-tokens", "0.0030000000"),
    ("USW2-Claude3Haiku-input-tokens", "0.0002500000"),
    ("USW2-Claude2.0-input-tokens", "0.0080000000"),
    ("USW2-Claude2.1-input-tokens", "0.0080000000"),
    ("USW2-ClaudeInstant-input-tokens", "0.0008000000"),
)


def _item(usagetype, usd, unit="1K tokens", pub="2026-10-03T00:11:38Z"):
    """Rebuild one full-shape Price List item from the slim table."""
    return {
        "product": {"attributes": {"usagetype": usagetype}},
        "terms": {
            "OnDemand": {
                "sku.term": {
                    "priceDimensions": {
                        "sku.term.dim": {
                            "unit": unit,
                            "pricePerUnit": {"USD": usd},
                        }
                    }
                }
            }
        },
        "publicationDate": pub,
    }


@pytest.fixture(autouse=True)
def _live_enabled(monkeypatch, tmp_path):
    """Opt out of the suite kill-switch with an isolated cache dir."""
    monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
    monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))
    live_pricing._reset_cooldowns()
    yield
    live_pricing._reset_cooldowns()


def _fake_fetch(monkeypatch, rows=_FIXTURES):
    """Serve fixture items for the Bedrock fetch; count refresh calls."""
    calls = []

    def _fetch(region):
        calls.append(region)
        return [_item(u, p) for u, p in rows]

    monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _fetch)
    return calls


# ----------------------------------------------------------------------
# usagetype parsing + model matching (pure, no network)
# ----------------------------------------------------------------------


class TestParseUsagetype:
    def test_standard_forms_accepted(self):
        assert live_pricing.parse_usagetype(
            "USW2-Mistral-Large-3-675b-Instruct-input-tokens"
        ) == ("mistral-large-3-675b-instruct", "input")
        assert live_pricing.parse_usagetype(
            "USW2-mistral.mistral-large-3-675b-instruct-mantle-output-tokens-standard"
        ) == ("mistral.mistral-large-3-675b-instruct", "output")

    def test_tier_variants_rejected(self):
        for usage in (
            "USW2-Model-input-tokens-batch",
            "USW2-Model-output-tokens-priority",
            "USW2-Model-input-tokens-flex",
            "USW2-Model-cache-read-tokens",
            "USW2-Model-input-tokens-cross-region-global",
            "USW2-Model-input-video-token-count",
            "not-a-usagetype",
            "",
        ):
            assert live_pricing.parse_usagetype(usage) is None, usage


class TestModelCandidates:
    def test_forms_most_specific_first(self):
        forms = live_pricing.model_candidates("mistral.mistral-large-3-675b-instruct")
        assert forms[0] == live_pricing.normalize(
            "mistral.mistral-large-3-675b-instruct"
        )
        assert live_pricing.normalize("mistral-large-3-675b-instruct") in forms

    def test_version_suffixes_stripped(self):
        forms = live_pricing.model_candidates("anthropic.claude-3-haiku-20240307-v1:0")
        assert "claude3haiku" in forms

    def test_routed_ids_match_full_only(self):
        forms = live_pricing.model_candidates("us.anthropic.claude-haiku-4-5-x")
        assert forms == [live_pricing.normalize("us.anthropic.claude-haiku-4-5-x")]


class TestParsePriceRecord:
    def test_standard_record_scales_to_per_1m(self):
        core, direction, per_1m = live_pricing.parse_price_record(
            _item("USW2-Mistral-Large-3-675b-Instruct-input-tokens", "0.0005000000")
        )
        assert direction == "input"
        assert per_1m == pytest.approx(0.50)
        assert core == "mistral-large-3-675b-instruct"

    def test_batch_record_rejected_despite_input_tokens_shape(self):
        assert (
            live_pricing.parse_price_record(
                _item(
                    "USW2-Mistral-Large-3-675b-Instruct-output-tokens-batch",
                    "0.0007500000",
                )
            )
            is None
        )

    def test_malformed_items_rejected(self):
        assert live_pricing.parse_price_record({}) is None
        assert live_pricing.parse_price_record({"product": {"attributes": {}}}) is None
        broken = _item("USW2-Model-input-tokens", "0.0005")
        broken["terms"] = {}
        assert live_pricing.parse_price_record(broken) is None


# ----------------------------------------------------------------------
# Bedrock live layer over faked fetch
# ----------------------------------------------------------------------


class TestBedrockLivePrice:
    def test_fixture_prices_resolve(self, monkeypatch):
        _fake_fetch(monkeypatch)
        hit = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert hit is not None
        price_in, price_out, provenance = hit
        assert price_in == pytest.approx(0.50)
        assert price_out == pytest.approx(1.50)
        assert "us-west-2" in provenance and "2026-10-03" in provenance

    def test_legacy_claude_short_name_matches(self, monkeypatch):
        rows = list(_FIXTURES) + [("USW2-Claude3Haiku-output-tokens", "0.0012500000")]
        _fake_fetch(monkeypatch, rows)
        hit = live_pricing.bedrock_live_price(
            "anthropic.claude-3-haiku-20240307-v1:0", "us-west-2"
        )
        assert hit is not None
        assert hit[0] == pytest.approx(0.25)
        assert hit[1] == pytest.approx(1.25)

    def test_routed_id_never_matches_base_records(self, monkeypatch):
        _fake_fetch(monkeypatch)
        assert (
            live_pricing.bedrock_live_price(
                "us.mistral.mistral-large-3-675b-instruct", "us-west-2"
            )
            is None
        )

    def test_unknown_model_misses(self, monkeypatch):
        _fake_fetch(monkeypatch)
        assert (
            live_pricing.bedrock_live_price("mystery/acme-1", "us-west-2") is None
        )

    def test_no_region_skips_without_fetch(self, monkeypatch):
        def _boom(_region):
            raise AssertionError("must not fetch without a region")

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _boom)
        assert live_pricing.bedrock_live_price("anything", None) is None


class TestBedrockCache:
    def test_fresh_cache_serves_without_fetch(self, monkeypatch, tmp_path):
        _fake_fetch(monkeypatch)
        live_pricing.bedrock_live_price("mistral.mistral-large-3", "us-west-2")

        def _boom(_region):
            raise AssertionError("fresh cache must not refetch")

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _boom)
        hit = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert hit is not None and hit[0] == pytest.approx(0.50)

    def test_failed_refresh_serves_stale_once(self, monkeypatch):
        calls = _fake_fetch(monkeypatch)
        live_pricing.bedrock_live_price("mistral.mistral-large-3", "us-west-2")
        assert len(calls) == 1
        path = live_pricing._cache_dir() / "bedrock-pricing-us-west-2.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["fetched_at"] = 0  # force expiry
        path.write_text(json.dumps(payload), encoding="utf-8")

        def _fail(_region):
            calls.append("retry")
            return None

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _fail)
        stale = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert stale is not None and stale[0] == pytest.approx(0.50)
        # Second call stays in cooldown: no further attempt, still stale.
        again = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert again is not None
        assert calls.count("retry") == 1

    def test_corrupt_cache_refetches(self, monkeypatch, tmp_path):
        path = tmp_path / "bedrock-pricing-us-west-2.json"
        path.write_text("not json", encoding="utf-8")
        calls = _fake_fetch(monkeypatch)
        hit = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert hit is not None and len(calls) == 1

    def test_no_cache_and_failed_fetch_misses(self, monkeypatch):
        monkeypatch.setattr(
            live_pricing, "fetch_bedrock_records", lambda _region: None
        )
        assert (
            live_pricing.bedrock_live_price(
                "mistral.mistral-large-3-675b-instruct", "us-west-2"
            )
            is None
        )


# ----------------------------------------------------------------------
# OpenRouter layer over faked fetch
# ----------------------------------------------------------------------

_OR_MODELS = [
    {
        "id": "qwen/qwen3-32b",
        "context_length": 131072,
        "pricing": {"prompt": "0.00000008", "completion": "0.00000028"},
    },
    {
        "id": "qwen/qwen3-32b:free",
        "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {"id": "broken/entry", "pricing": {"prompt": "n/a"}},
]


class TestOpenRouterEntry:
    def test_price_and_window_resolve(self, monkeypatch):
        monkeypatch.setattr(
            live_pricing, "fetch_openrouter_models", lambda: list(_OR_MODELS)
        )
        entry = live_pricing.openrouter_entry("litellm/openrouter/qwen/qwen3-32b")
        assert entry is not None
        assert entry["in"] == pytest.approx(0.08)
        assert entry["out"] == pytest.approx(0.28)
        assert entry["window"] == 131072

    def test_prefix_forms_and_free_tier(self, monkeypatch):
        monkeypatch.setattr(
            live_pricing, "fetch_openrouter_models", lambda: list(_OR_MODELS)
        )
        assert (
            live_pricing.openrouter_entry("openrouter/qwen/qwen3-32b") is not None
        )
        free = live_pricing.openrouter_entry("openrouter/qwen/qwen3-32b:free")
        assert free is not None and free["in"] == 0.0 and free["out"] == 0.0

    def test_bedrock_id_skips_without_fetch(self, monkeypatch):
        def _boom():
            raise AssertionError("bedrock ids must not fetch openrouter")

        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", _boom)
        assert live_pricing.openrouter_entry("qwen.qwen3-32b-v1:0") is None
        assert live_pricing.is_openrouter_id("qwen.qwen3-32b-v1:0") is False
        assert live_pricing.is_openrouter_id("openrouter/qwen/qwen3-32b") is True


# ----------------------------------------------------------------------
# LiteLLM layer over a faked module
# ----------------------------------------------------------------------


def _fake_litellm(monkeypatch, table):
    fake = types.ModuleType("litellm")
    fake.model_cost = dict(table)
    monkeypatch.setitem(sys.modules, "litellm", fake)


class TestLiteLLMEntry:
    def test_key_variants(self, monkeypatch):
        _fake_litellm(
            monkeypatch,
            {
                "bedrock/us.anthropic.claude-haiku-4-5-x": {
                    "input_cost_per_token": 1.1e-6,
                    "output_cost_per_token": 5.5e-6,
                    "max_input_tokens": 200000,
                }
            },
        )
        entry = live_pricing.litellm_entry("us.anthropic.claude-haiku-4-5-x")
        assert entry is not None
        assert entry["in"] == pytest.approx(1.10)
        assert entry["out"] == pytest.approx(5.50)
        assert entry["window"] == 200000

    def test_missing_module_misses(self, monkeypatch):
        # None in sys.modules makes `import litellm` raise ImportError.
        monkeypatch.setitem(sys.modules, "litellm", None)
        assert live_pricing.litellm_entry("anything") is None

    def test_bedrock_mantle_variant(self, monkeypatch):
        _fake_litellm(
            monkeypatch,
            {
                "bedrock_mantle/openai.gpt-5.4": {
                    "input_cost_per_token": 2.75e-6,
                    "output_cost_per_token": 1.65e-5,
                    "max_input_tokens": 1050000,
                }
            },
        )
        entry = live_pricing.litellm_entry("openai.gpt-5.4")
        assert entry is not None
        assert entry["in"] == pytest.approx(2.75)
        assert entry["out"] == pytest.approx(16.50)
        assert entry["window"] == 1050000


# ----------------------------------------------------------------------
# Resolution order through cost_context
# ----------------------------------------------------------------------


class TestResolutionOrder:
    def test_live_beats_static(self, monkeypatch):
        _fake_fetch(
            monkeypatch,
            [
                ("USW2-Claude3Haiku-input-tokens", "0.0009990000"),
                ("USW2-Claude3Haiku-output-tokens", "0.0099990000"),
            ],
        )
        price = cost_context.price_for(
            "anthropic.claude-3-haiku-20240307-v1:0", region="us-west-2"
        )
        assert price is not None
        assert price[0] == pytest.approx(0.999)
        assert cost_context.price_provenance(
            "anthropic.claude-3-haiku-20240307-v1:0", region="us-west-2"
        ).startswith("Bedrock live")

    def test_fallthrough_to_static(self, monkeypatch):
        _fake_fetch(monkeypatch, rows=[])
        price = cost_context.price_for(
            "anthropic.claude-3-haiku-20240307-v1:0", region="us-west-2"
        )
        assert price == (0.25, 1.25)
        assert (
            cost_context.price_provenance(
                "anthropic.claude-3-haiku-20240307-v1:0", region="us-west-2"
            )
            == "static table"
        )

    def test_routed_id_reaches_litellm_not_live(self, monkeypatch):
        _fake_fetch(monkeypatch)
        _fake_litellm(
            monkeypatch,
            {
                "bedrock/us.anthropic.claude-haiku-4-5-x": {
                    "input_cost_per_token": 1.1e-6,
                    "output_cost_per_token": 5.5e-6,
                    "max_input_tokens": 200000,
                }
            },
        )
        price = cost_context.price_for(
            "us.anthropic.claude-haiku-4-5-x", region="us-west-2"
        )
        assert price is not None and price[0] == pytest.approx(1.10)
        assert (
            cost_context.price_provenance(
                "us.anthropic.claude-haiku-4-5-x", region="us-west-2"
            )
            == "LiteLLM bundled"
        )
        assert (
            cost_context.window_for("us.anthropic.claude-haiku-4-5-x") == 200000
        )

    def test_openrouter_window_flows_to_window_for(self, monkeypatch):
        monkeypatch.setattr(
            live_pricing, "fetch_openrouter_models", lambda: list(_OR_MODELS)
        )
        assert (
            cost_context.window_for("litellm/openrouter/qwen/qwen3-32b") == 131072
        )
        price = cost_context.price_for("litellm/openrouter/qwen/qwen3-32b")
        assert price is not None and price[0] == pytest.approx(0.08)

    def test_unknown_model_provenance(self, monkeypatch):
        _fake_fetch(monkeypatch, rows=[])
        assert (
            cost_context.price_provenance("mystery/acme-1", region="us-west-2")
            == "unknown"
        )
        assert cost_context.price_for("mystery/acme-1", region="us-west-2") is None

    def test_gpt_on_bedrock_falls_to_mantle_litellm(self, monkeypatch):
        _fake_fetch(monkeypatch, rows=[])  # Price List has no GPT records
        _fake_litellm(
            monkeypatch,
            {
                "bedrock_mantle/openai.gpt-5.4": {
                    "input_cost_per_token": 2.75e-6,
                    "output_cost_per_token": 1.65e-5,
                    "max_input_tokens": 1050000,
                }
            },
        )
        price = cost_context.price_for("openai.gpt-5.4", region="us-west-2")
        assert price is not None and price[0] == pytest.approx(2.75)
        assert (
            cost_context.price_provenance("openai.gpt-5.4", region="us-west-2")
            == "LiteLLM bundled"
        )
        assert cost_context.window_for("openai.gpt-5.4") == 1050000

    def test_kill_switch_restores_static_only(self, monkeypatch):
        monkeypatch.setenv("STRANDS_CODE_NO_LIVE_PRICING", "1")

        def _boom(*_a, **_k):
            raise AssertionError("live layers must stay off")

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _boom)
        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", _boom)
        # Even with LiteLLM installed and hitting, resolution stays static.
        _fake_litellm(
            monkeypatch,
            {
                "anthropic.claude-3-haiku-20240307-v1:0": {
                    "input_cost_per_token": 9.99e-6,
                    "output_cost_per_token": 9.99e-6,
                }
            },
        )
        assert cost_context.price_for(
            "anthropic.claude-3-haiku-20240307-v1:0", region="us-west-2"
        ) == (0.25, 1.25)

    def test_cost_report_names_price_source(self, monkeypatch):
        _fake_fetch(monkeypatch, rows=[])
        report = cost_context.cost_report(
            [{"turn": 1, "input_tokens": 10, "output_tokens": 5}],
            "anthropic.claude-3-haiku-20240307-v1:0",
        )
        assert "Prices: static table." in report

    def test_cost_report_mixed_provenance(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        _fake_fetch(
            monkeypatch,
            [
                ("USW2-Claude3Haiku-input-tokens", "0.0009990000"),
                ("USW2-Claude3Haiku-output-tokens", "0.0099990000"),
            ],
        )
        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 1000,
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
            },
            {
                "turn": 2,
                "input_tokens": 1000,
                "output_tokens": 1000,
                "model": "amazon.nova-micro-v1:0",
            },
        ]
        report = cost_context.cost_report(
            turns, "anthropic.claude-3-haiku-20240307-v1:0"
        )
        assert "turn 1: in 1.00K, out 1.00K, $0.0110" in report
        assert "turn 2: in 1.00K, out 1.00K, $0.0002" in report
        assert "Prices: mixed (per-turn model)." in report


# ----------------------------------------------------------------------
# /cost refresh + table
# ----------------------------------------------------------------------


def _fake_openrouter(monkeypatch, models=_OR_MODELS):
    """Serve a /models payload for the OpenRouter fetch; count calls."""
    calls = []

    def _fetch():
        calls.append(True)
        return [dict(model) for model in models]

    monkeypatch.setattr(live_pricing, "fetch_openrouter_models", _fetch)
    return calls


class TestRefreshCaches:
    def test_refresh_stores_and_reports(self, monkeypatch):
        _fake_fetch(monkeypatch)
        _fake_openrouter(monkeypatch)
        summary = live_pricing.refresh_caches(region="us-west-2")
        assert summary["bedrock"]["models"] == 7
        assert summary["bedrock"]["publication"] == "2026-10-03T00:11:38Z"
        assert summary["openrouter"]["models"] == 2
        report = cost_context.refresh_report(summary)
        assert "us-west-2" in report and "7 models" in report
        assert "OpenRouter: 2 models." in report

    def test_refresh_bypasses_cooldown(self, monkeypatch):
        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", lambda _r: None)
        assert live_pricing.bedrock_live_price("x", "us-west-2") is None
        calls = _fake_fetch(monkeypatch)
        _fake_openrouter(monkeypatch)
        summary = live_pricing.refresh_caches(region="us-west-2")
        assert calls == ["us-west-2"]
        assert summary["bedrock"]["models"] == 7

    def test_refresh_failure_reports_and_keeps_stale(self, monkeypatch):
        _fake_fetch(monkeypatch)
        live_pricing.bedrock_live_price("mistral.mistral-large-3", "us-west-2")
        path = live_pricing._cache_dir() / "bedrock-pricing-us-west-2.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["fetched_at"] = 0
        path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", lambda _r: None)
        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", lambda: None)
        summary = live_pricing.refresh_caches(region="us-west-2")
        assert "error" in summary["bedrock"]
        assert "error" in summary["openrouter"]
        assert "fetch failed" in cost_context.refresh_report(summary)
        stale = live_pricing.bedrock_live_price(
            "mistral.mistral-large-3-675b-instruct", "us-west-2"
        )
        assert stale is not None and stale[0] == pytest.approx(0.50)

    def test_refresh_disabled(self, monkeypatch):
        monkeypatch.setenv("STRANDS_CODE_NO_LIVE_PRICING", "1")
        assert live_pricing.refresh_caches(region="us-west-2") == {"disabled": True}
        assert "disabled" in cost_context.refresh_report({"disabled": True})


class TestPriceTable:
    def _prime(self, monkeypatch):
        _fake_fetch(monkeypatch)
        _fake_openrouter(monkeypatch)
        live_pricing.refresh_caches(region="us-west-2")

    def test_rows_from_caches_plus_static(self, monkeypatch):
        self._prime(monkeypatch)
        table = cost_context.price_table(region="us-west-2")
        assert "mistral-large-3-675b-instruct" in table
        assert "in $0.5/1M, out $1.5/1M" in table
        assert "qwen/qwen3-32b" in table
        assert "Static fallback:" in table
        assert "claude-haiku-" in table

    def test_filter_narrows(self, monkeypatch):
        self._prime(monkeypatch)
        table = cost_context.price_table("mistral", region="us-west-2")
        assert "mistral-large-3" in table
        assert "qwen/qwen3-32b" not in table
        assert "claude3haiku" not in table

    def test_missing_caches_hint_without_fetch(self, monkeypatch):
        def _boom(*_a, **_k):
            raise AssertionError("table must not fetch")

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _boom)
        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", _boom)
        table = cost_context.price_table(region="us-west-2")
        assert "/cost refresh to fetch" in table
        assert "Static fallback:" in table

    def test_row_cap(self, monkeypatch):
        rows = [(f"USW2-Model{i:02d}-input-tokens", "0.0010000000") for i in range(45)]
        rows += [(f"USW2-Model{i:02d}-output-tokens", "0.0020000000") for i in range(45)]
        _fake_fetch(monkeypatch, rows)
        _fake_openrouter(monkeypatch, models=[])
        live_pricing.refresh_caches(region="us-west-2")
        table = cost_context.price_table(region="us-west-2")
        assert "…and 5 more" in table
