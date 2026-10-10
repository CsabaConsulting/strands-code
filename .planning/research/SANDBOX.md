# Sandbox Future: MXC / Strands Box / Dogwood evaluation

Evaluated 2026-10-10. Decision: wait for Strands Box Linux; watch MXC; no code changes until then.

## Current posture (no containment)

- The harness `shell` tool runs commands directly on the host. Our entire security
  model is the interactive approval gate (deny-first allowlist, diff-gated
  write/edit) plus `chmod 700` on the session dir. A misclicked "Always" bypasses
  everything — there is no enforcement floor below the human click.
- `python_repl` is smolagents' import-allowlist interpreter (language-level only,
  plain subprocess). No bubblewrap/docker/namespaces anywhere in the repo.

## Options considered

### Microsoft MXC (github.com/microsoft/mxc)

Policy-driven layered isolation, JSON-schema policies (filesystem/network/UI),
bubblewrap default on Linux with LXC/microVM/Hyperlight escalation, one-shot and
session lifecycles. Natural mapping: generate a per-approval policy from gate
context (cwd read-write, repo read-only, network off/proxied) and exec through it.
Blockers: early preview — README states no MXC profile is a security boundary yet
and generated policies are overly permissive; Rust binaries + TypeScript SDK mean a
subprocess/JSON integration rather than a pip import. Verdict: watch, prototype
later; not a boundary we can rely on today.

### Strands Box (github.com/strands-agents/box)

Dev preview, macOS Apple-silicon only, Linux planned and actively developed.
Kernel-enforced sandbox funneling everything to an embedded Dogwood Local Engine;
Strands Shell, Monty-for-Python, egress gateway, and MCP broker share one policy
engine + event history; default-deny; credential injection keeps secrets out of the
agent. Harness-agnostic (runs any binary), so our CLI could sit inside it unchanged.
Verdict: the endgame — adopt as a non-overridable floor under our HITL dialogs
when Linux lands. Tracking via repo watch (same as harness-sdk).

### Dogwood (github.com/dogwood-policy/dogwood)

Temporal semantic policy ("push only if tests passed in 15m", spend caps) that our
stateless TOML allowlist + classifier fundamentally cannot express, in one language
instead of allowlist-plus-code. Wrinkle: locked decision D-05 says determinism,
"never Cedar" — Dogwood lowers to Cedar, so adoption revisits D-05 (justifiably:
Dogwood-deterministic is not NL-string policy, but the letter stands). Reference
interpreter is explicitly not for production; the Local Engine (embedded in Box) is
the runtime. Verdict: adopt via Box, not standalone; keep our dialogs as the product
surface.

## Selected direction (post-v1)

Defense in depth: HITL approval UX on top, Box + Dogwood as the deterministic floor
below. First step when Box supports Linux: spike `box run strands-code` with a
policy mirroring our allowlist and compare Box verdicts against gate decisions.
No MXC/Dogwood-standalone work scheduled.
