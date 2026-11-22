---
phase: 14-first-class-google-gemini-provider-aware-startup
plan: 01
subsystem: entry, dispatch, packaging
tags: [gemini, preflight, cli, strands-box, optional-extras]
dependency_graph:
  requires: []
  provides:
    - gemini optional extra in pyproject.toml and uv.lock
    - provider-aware startup preflight and ambient model auto-pick (entry/first_run.py)
    - session-scoped --model CLI flag (entry/main.py)
    - has_google_credentials() helper for downstream model discovery
  affects:
    - pyproject.toml
    - uv.lock
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/entry/first_run.py
    - strands_code_cli/entry/main.py
    - tests/conftest.py
    - tests/dispatch/test_cli_entry.py
    - tests/entry/test_first_run.py
    - tests/entry/test_session_resume.py
tech_stack:
  added: ["strands-agents[gemini] optional extra (google-genai)"]
  patterns: ["Provider-aware credential preflight isolated in entry/first_run.py", "Session-scoped --model override after read-only ProviderConfig.load()"]
key_files:
  modified:
    - pyproject.toml
    - uv.lock
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/entry/first_run.py
    - strands_code_cli/entry/main.py
    - tests/conftest.py
    - tests/dispatch/test_cli_entry.py
    - tests/entry/test_first_run.py
    - tests/entry/test_session_resume.py
decisions:
  - "All os.environ credential checks stay isolated inside strands_code_cli/entry/first_run.py so test_no_credential_persistence_sinks holds."
  - "Preflight checks non-empty env presence only (never key prefixes) and skips sts.get_caller_identity() for non-AWS providers and STRANDS_BOX=1."
  - "GOOGLE_GENAI_USE_VERTEXAI=true is mutually exclusive with GOOGLE_API_KEY/GEMINI_API_KEY and requires GOOGLE_CLOUD_PROJECT."
metrics:
  completed: "2026-11-21"
---

# Phase 14 Plan 01: Gemini Packaging & Provider-Aware Startup Preflight Summary

## What Was Built

1. **Packaging & Dispatch Hint (`D-01`):**
   - Added `gemini = ["strands-agents[gemini]"]` to `[project.optional-dependencies]` in `pyproject.toml` and regenerated `uv.lock` (147 resolved packages, `uv lock --check` clean).
   - Registered `"google": "gemini"` in `strands_code_cli/dispatch/core.py` `_SDK_EXTRA_HINTS` so missing `google-genai` surfaces `pip install strands-code-agent[gemini]`.

2. **Provider-Aware Startup Preflight & `--model` Flag (`D-02`, `D-03`):**
   - Rewrote `strands_code_cli/entry/first_run.py` to support Amazon Bedrock, Google Gemini (`GOOGLE_API_KEY` / `GEMINI_API_KEY` or Vertex ADC via `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT`), Anthropic, OpenAI, OpenRouter, LiteLLM proxies, and local Ollama without calling AWS STS unnecessarily.
   - Enforced fast-fail validation on mutually exclusive Google auth (`GOOGLE_GENAI_USE_VERTEXAI` with `GOOGLE_API_KEY`/`GEMINI_API_KEY`) and missing `GOOGLE_CLOUD_PROJECT`, plus Strands Box (`STRANDS_BOX=1`) STS bypass and phantom-token acceptance (non-empty check only).
   - Added ambient model auto-selection (`google/gemini-2.5-flash`, `anthropic/claude-sonnet-4-6`, `openai/gpt-5.4`, or actionable `--model litellm/openrouter/...` guidance when `OPENROUTER_API_KEY` is set).
   - Exposed session-scoped `--model` on the root CLI callback in `strands_code_cli/entry/main.py` with `ProviderConfig.load()` running before `_preflight_credentials(model=..., base_url=...)` and zero `config.yaml` writes.
   - Added `_hermetic_provider_env` (`autouse=True`) in `tests/conftest.py` and full unit/CLI coverage including secret canary non-leakage.

## Verification

- `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/cost/test_cost_context.py -q`: **137 passed**
- `/home/csaba/.local/bin/uv lock --check`: **exit 0**
- `.venv/bin/ruff check strands_code_cli tests scripts` & `ruff format --check`: **All checks passed (113 files)**
- `.venv/bin/xenon --max-absolute C strands_code_cli/entry/ strands_code_cli/dispatch/`: **exit 0**
