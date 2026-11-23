# Upstream Feature Proposal: Built-in `RejectCallerToolUseHook` and Explicit Resume-Provenance Gating (`strands-py`)

> **HOLD BEFORE PUBLISHING:** Complete `## Human Overview` in your own words per `team/AI_USAGE_POLICY.md`. Per `CONTRIBUTING.md`, this architectural proposal intentionally has **no PR branch yet** — file the issue first to align with maintainers on the public API and resume-provenance design.

- **Target repo:** `strands-agents/harness-sdk` (`main` at `d6c5fae7c`, tag `python/v1.65.0`)
- **Disclosure note:** Direct tool dispatch on trailing `toolUse` blocks is already publicly documented in #3467 ("Trusted Message History") and related CVE-2026-18830 advisories; this proposes SDK ergonomics for `strands-py` beyond the targeted `user`-role bug fix.

# Filed URL

https://github.com/strands-agents/harness-sdk/issues/6482

---

## 1. Issue Title

```text
[FEATURE] Python SDK: Ship built-in caller toolUse guard hook and gate direct tool dispatch on explicit resume provenance
```

## 2. Issue Body

```markdown
## Human Overview

Today #3467 requires every Python Strands wrapper accepting external messages to hand-roll a trailing-`toolUse` guard, even though `strands-py` already tracks explicit provenance for interrupts and checkpoints. I am proposing two steps: ship a canonical built-in guard hook now, and align on gating direct trailing-`assistant` `toolUse` dispatch behind explicit resume provenance or opt-in (#2489).

## SDK Language

Python

## Problem Statement

Per #3467 ("Trusted Message History"), calling `agent(messages)` when the trailing incoming message is an `assistant` turn carrying a `toolUse` block causes `event_loop_cycle()` (`_has_tool_use_in_latest_message`) to skip `_handle_model_execution()` and dispatch tools directly without invoking the model or `BeforeModelCallEvent` / `InvokeModelStage` middleware.

Meanwhile, `strands-py` **already uses explicit resume provenance** for its own first-party resume mechanisms in `event_loop_cycle()`:
- Tool interrupts: `agent._interrupt_state.activated and pending_tool_execution is not None`
- Checkpointing: `{"checkpointResume": {"checkpoint": ...}}` (`agent._checkpoint`)

Because trailing unmediated `toolUse` dispatch activates implicitly on raw message shapes without explicit opt-in or provenance checks, every downstream wrapper (as seen in aws-samples/sample-strands-code-agent#6 and aws-samples/sample-strands-code-agent#7) must re-implement the same `BeforeInvocationEvent` guard independently.

## Proposed Solution

Two complementary, incremental improvements in `strands-py`:

1. **Ship a canonical built-in guard (`RejectCallerToolUseHook` or `trusted_message_history` hook in `strands.hooks`):**
   Provide an off-the-shelf `HookProvider` on `BeforeInvocationEvent` that rejects incoming `"user"` `toolUse` blocks and trailing incoming `toolUse` blocks while preserving empty resume inputs (`interruptResponse`, `checkpointResume`), paired historical transcripts, and multi-turn model tool loops — replacing ad-hoc helper snippets in docs.

2. **Discuss gating direct trailing-`assistant` `toolUse` dispatch on explicit resume provenance (for a future minor/major checkpoint):**
   Require explicit opt-in or provenance (for example `checkpointResume`, interrupt state, session-restore provenance, or an explicit opt-in flag matching the discussion in #2489) rather than unconditionally trusting arbitrary caller-supplied `assistant` `toolUse` blocks passed to `agent(messages)` — and fail closed with an explicit error pointing callers to the opt-in flag when an un-opted-in trailing `toolUse` is supplied, rather than silently forwarding an unmatched `toolUse` to the model (where providers typically reject it anyway).

## Use Case

- Service/API developers exposing Strands `Agent`s behind FastAPI, Lambda, AG-UI, or AgentCore endpoints get a single audited SDK hook instead of duplicating custom `BeforeInvocationEvent` validators (aws-samples/sample-strands-code-agent#6 is one example already shipped downstream).
- Aligns Python and TypeScript semantics (see #2489's open discussion on opt-in vs. default `toolUse` resumption).

## Alternatives Solutions

- **Status quo (docs-only sanitization snippet per #3467):** Works when every consumer reads the guide and writes a hook, but duplicates security boilerplate across downstream packages and remains fail-open for callers that forget.
- **Hard break removing raw trailing-`assistant` `toolUse` auto-resume immediately:** Cleanest long-term boundary, but would break callers intentionally using `Agent` return-of-control or raw snapshot replay unless introduced behind an explicit opt-in / migration window first. Shipping the SDK hook immediately and gating implicit dispatch via opt-in or provenance avoids breaking existing users silently.

## Additional Context

<details>
<summary>References and prior art</summary>

- Public docs baseline: #3467 ("Trusted Message History").
- TypeScript counterpart debating opt-in vs. default: #2489.
- Downstream wrapper hardening reference: aws-samples/sample-strands-code-agent#6 and aws-samples/sample-strands-code-agent#7 (`RejectCallerToolUseHook`).
- Related bug report covering `user`-role messages and `list[ContentBlock]` prompts (filed separately so it can land immediately without waiting on provenance design decisions).

</details>
```

---

## 3. Held Publish Command (Run Only After Human Review)

```bash
# Edit ## Human Overview in your own words first, then copy ONLY the fenced markdown block from Section 2 (excluding the top HOLD notice and Section 3) to /tmp/strands_py_resume_provenance_issue.md (never pass this whole wrapper file directly to --body-file)
gh issue create \
  --repo strands-agents/harness-sdk \
  --title "[FEATURE] Python SDK: Ship built-in caller toolUse guard hook and gate direct tool dispatch on explicit resume provenance" \
  --body-file /tmp/strands_py_resume_provenance_issue.md
```
