---
phase: 05-model-cost-context-commands
kind: api-coverage
status: sealed
source: 05-SUMMARY.md
updated: 2026-09-27
---

# Phase 05 API Coverage Matrix

External-API surface touched by Phase 05 (Model + Cost + Context Commands).
AWS-optional posture holds: every call is fail-soft and the CLI runs fully
offline without boto3 installed.

| Capability | Decision | Reason |
|---|---|---|
| `bedrock:ListFoundationModels` (ON_DEMAND filter) | INTEGRATE | Chat-capable `/model` discovery in `model_switch.py:discover_models` (TEXT in/out modalities, rerank/embed names dropped); falls back to configured/custom ids on any failure |
| `bedrock:ListInferenceProfiles` | INTEGRATE | App-profile ARNs displayed verbatim (prefixes intact) by `discover_models`; skipped silently on failure; listing never implies entitlement — `resolve_model` stays authoritative |
| `bedrock:InvokeModel` and `bedrock-runtime:*` | OPT-OUT | Invocation stays inside the Strands `BedrockModel` provider; Phase 05 adds no direct invoke path |
| `bedrock:ListPromptRouters` and other `List*` discovery calls | OPT-OUT | Discovery limited to foundation models + app profiles; routers/custom/imported/provisioned models are out of `/model` scope |
| Mutating Bedrock calls (e.g. `bedrock:CreateInferenceProfile`) | OPT-OUT | Display-only phase; cost is display-only forever, no provisioning |
| `sts:GetCallerIdentity` | OPT-OUT | Pre-existing first-run credential check (`first_run.py`), not Phase 05 scope; unchanged |

## Non-API note

Spend figures come from static `MODEL_PRICING`/`MODEL_LIMITS` tables in
`strands_code_cli/cost_context.py`, not from Cost Explorer or any metering
API — no billing API is integrated by design.
