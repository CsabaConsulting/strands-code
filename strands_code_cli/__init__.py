"""strands-code conversational CLI (Phase 1 tracer slice)."""

from strands_code_cli.entry.first_run import disable_cwd_dotenv

disable_cwd_dotenv()

from strands_code_cli.entry.main import main  # noqa: E402 - disable implicit CWD .env auto-load before smolagents/litellm import (T-14-02)

__all__ = ["main"]
