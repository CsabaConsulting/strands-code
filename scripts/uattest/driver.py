#!/usr/bin/env python3
"""Scripted live-tmux UAT driver for strands-code Phase 7-13 confirmation.

Usage: driver.py {s1|s2|r1|r2|r3|r4|n1|n2|n3|n4|c1|c2|a1|a2|u1|u2|u3}   (one scenario
per process; tmux session per scenario). s1/s2 cover Phase 7 (/btw);
r1/r2/r3/r4 cover the Phase 8 rows (guided setup, local engine, e2e
routed turn, side ask) against the Decision-API flow; n1/n2/n3/n4
cover the Phase 9 native rows (setup proposal, hidden-until-key,
validate ping, native-routed turn) against the TypeSafe native API;
c1/c2 cover the Phase 10 reported-spend rows (marked actual on an
OpenRouter main turn, blended total + split on a mixed session);
a1/a2 cover the Phase 11 CodeAct rows (bare --codeact boots code
mode, code turn labels codeact plus switch-back tool turn unshaped);
u1/u2/u3 cover Phase 13 upstream resync (Bedrock unary tool mode on Mistral 24.02,
Sonnet -> Nova 2 Lite --session-id resume + /context, 1.65 HITL/Plan).
Transcripts land in /tmp/uatr4/<scenario>.log (s*) or /tmp/uatr8/<scenario>.log
(r*/n*/c*/a*/u*). Exit 0 = all asserts passed.

Key insight: a mid-turn Approve? dialog blocks the pump thread, so the driver
must answer dialogs to make progress (like a human would). S1 retries until the
idle case materializes (max 2 attempts).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios_codeact import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    scenario_a1,
    scenario_a2,
)
from scenarios_cost import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    scenario_c1,
    scenario_c2,
)
from scenarios_native import (  # noqa: E402, F401 - BOGUS_TYPESAFE_KEY + _native_strategy re-exported for the loader-based calibration contract
    BOGUS_TYPESAFE_KEY,
    _native_strategy,
    scenario_n1,
    scenario_n2,
    scenario_n3,
    scenario_n4,
)
from scenarios_routing import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    scenario_r1,
    scenario_r2,
    scenario_r3,
    scenario_r4,
)
from scenarios_side import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    scenario_s1,
    scenario_s2,
)
from scenarios_upstream import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    scenario_u1,
    scenario_u2,
    scenario_u3,
)
from uattest_lib import (  # noqa: E402 - sibling import needs the sys.path insert above (CF-07a)
    LOGDIR,
    LOGDIR8,
)

SCENARIOS = {
    "s1": scenario_s1,
    "s2": scenario_s2,
    "r1": scenario_r1,
    "r2": scenario_r2,
    "r3": scenario_r3,
    "r4": scenario_r4,
    "n1": scenario_n1,
    "n2": scenario_n2,
    "n3": scenario_n3,
    "n4": scenario_n4,
    "c1": scenario_c1,
    "c2": scenario_c2,
    "a1": scenario_a1,
    "a2": scenario_a2,
    "u1": scenario_u1,
    "u2": scenario_u2,
    "u3": scenario_u3,
}

if __name__ == "__main__":
    os.makedirs(LOGDIR, exist_ok=True)
    os.makedirs(LOGDIR8, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = SCENARIOS.get(which)
    if fn is None:
        sys.exit(f"usage: driver.py {{{'|'.join(SCENARIOS)}}}")
    fn()
