"""First-run credential preflight: Bedrock-or-stop (D-05)."""

from __future__ import annotations

import logging
from collections.abc import Callable

import typer

logger = logging.getLogger(__name__)

BEDROCK_SETUP_POINTER = (
    "No AWS credentials found. strands-code runs its model on Amazon Bedrock.\n"
    "Set credentials via the ambient boto3 chain (env vars, ~/.aws/config, or an "
    "IAM role), then relaunch."
)


def _default_probe() -> None:
    """Cheap STS call over the ambient chain; never reads credentials directly."""
    import boto3
    from botocore.config import Config

    sts = boto3.client(
        "sts",
        config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 0}),
    )
    sts.get_caller_identity()


def preflight_credentials(probe: Callable[[], None] | None = None) -> None:
    """Stop with the Bedrock pointer when the credential chain is empty.

    Runs before any session or config side effect; a failing probe prints
    the pointer and exits non-zero. D-05 is costly to reverse: an
    offline-first entry later reworks launch and session defaults.

    Args:
        probe: Injectable credential check for offline tests; the ambient
            STS probe is used when omitted.
    """
    check = probe if probe is not None else _default_probe
    try:
        check()
    except typer.Exit:
        raise
    except Exception as exc:
        logger.warning("Credential preflight failed: %s", type(exc).__name__)
        typer.secho(BEDROCK_SETUP_POINTER, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
