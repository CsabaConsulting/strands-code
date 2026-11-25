# Sandbox Future: MXC / Strands Box / Dogwood evaluation

Evaluated 2026-10-10; updated 2026-11-21. **Update:** Strands Box (`strands-agents/box`, `v0.2.3+`) now supports Linux via 3 co-located Rust binaries using unprivileged namespaces (`CLONE_NEWUSER`, `CLONE_NEWNET`, mount/PID/IPC/UTS) and `seccomp-bpf` (no `bwrap` or Landlock required), plus Dogwood `policy.dw` + credential egress proxy — Linux blocker cleared; promoted into `v2.0` Phase 17 (`SANDBOX-01`, see `.planning/research/V2-ALIGNMENT.md`).

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

Supports both macOS Apple Silicon (Seatbelt) and Linux (`v0.2.3+`, 3 co-located Rust binaries `box`, `strands-box-contain-trampoline`, and `strands-box-sock-alias` using unprivileged `CLONE_NEWUSER` / `CLONE_NEWNET` / mount / PID / IPC / UTS namespaces and `seccomp-bpf`; no `bwrap` or Landlock required; `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64`).
Kernel-enforced sandbox funneling everything to an embedded Dogwood Local Engine;
Strands Shell, Monty-for-Python, egress gateway, and MCP broker share one policy
engine + event history; default-deny; out-of-band credential injection keeps secrets
outside the agent process. Harness-agnostic (wraps `box run --config ...` around `strands-code` unchanged).
Verdict: the endgame — Linux support has now landed (2026-11), clearing the blocker
to adopt Box (`box.toml` + `policy.dw`) as a non-overridable floor under our HITL
dialogs. Promoted into active `v2.0` Phase 17 (`SANDBOX-01`, see `.planning/research/V2-ALIGNMENT.md`).

### Dogwood (github.com/dogwood-policy/dogwood)

Temporal semantic policy ("push only if tests passed in 15m", spend caps) that our
stateless TOML allowlist + classifier fundamentally cannot express, in one language
instead of allowlist-plus-code. Wrinkle: locked decision D-05 says determinism,
"never Cedar" — Dogwood lowers to Cedar, so adoption revisits D-05 (justifiably:
Dogwood-deterministic is not NL-string policy, but the letter stands). Reference
interpreter is explicitly not for production; the Local Engine (embedded in Box, also
usable standalone) is the runtime. Verdict: prefer adoption via Box (shared engine +
event history); standalone Local Engine acceptable if Box Linux slips badly. D-05
revisit approved in principle 2026-10-10. Keep our dialogs as the product surface
either way.

## Selected direction (post-v1)

Defense in depth: HITL approval UX on top, Box + Dogwood as the deterministic floor
below. First step when Box supports Linux: spike `box run strands-code` with a
policy mirroring our allowlist and compare Box verdicts against gate decisions.
No MXC/Dogwood-standalone work scheduled.

## Monty Python VM (`pydantic-monty` / Strands Box Monty) — Phase 20 (`SANDBOX-02`)

Because `strands_code_cli` binds `python_repl` with `authorized_imports=set()` and
`CodeactStint` with `CODEACT_AUTHORIZED_IMPORTS = frozenset({"math"})` (funneling
file/shell capabilities exclusively through explicit host callbacks `read`, `write`,
`edit`, and `shell`), executing generated Python in Rust-backed **Monty**
(`pydantic-monty`, <1 ms cold start, worker-subprocess crash isolation, memory/timeout
caps, explicit `external_lookup` bridge) eliminates in-process `smolagents` memory
tampering (`sys.modules`, `PolicyClassifier`, `PendingStore`) even when running unboxed,
while Strands Box's embedded Monty tool informs optional unified Dogwood temporal
event alignment (`D-24` keeps `strands_code_agent/` untouched).
