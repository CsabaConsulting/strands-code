"""Phase 16 Meta Model API zero-AWS scenario for the live-tmux UAT rig.

Owns scenario_m1: launches strands-code with AWS credentials stripped and
isolated XDG_CONFIG_HOME on meta/muse-spark-1.3-contributor, verifies
--model writes no config.yaml, checks /context (~1.05M), runs a read tool
turn, checks /cost pricing, and performs a same-provider /model switch to
meta/muse-ember-1.0.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios_openai_anthropic import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    _run_provider_rig,
)

RIG_META_PRIMARY = "meta/muse-spark-1.3-contributor"
RIG_META_SECONDARY = "meta/muse-ember-1.0"


def scenario_m1() -> None:
    """M1: Zero-AWS Meta Muse Spark launch, tool turn, /context, /cost, /model."""
    _run_provider_rig(
        name="m1",
        primary=RIG_META_PRIMARY,
        secondary=RIG_META_SECONDARY,
        sentinel="META_SENTINEL_16",
        expected_window="of 1.05M",
    )
    print("M1 PASS", flush=True)
