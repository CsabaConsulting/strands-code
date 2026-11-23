# Upstream Comment Draft (`#2489`) & `aws/bedrock-agentcore-sdk-python` Verification

> **HOLD BEFORE POSTING:** Review the comment below (and replace/adjust if desired) before running `gh issue comment 2489`. Also includes the verification record confirming why no issue or PR is needed for `aws/bedrock-agentcore-sdk-python`.

# Filed URL

https://github.com/strands-agents/harness-sdk/issues/2489#issuecomment-7104053907

---

## 1. Comment Draft for `strands-agents/harness-sdk#2489`

- **Target issue:** https://github.com/strands-agents/harness-sdk/issues/2489 (`[FEATURE] Resume agent loop from pending toolUse messages`)
- **Policy note:** Includes explicit AI-assistance disclosure and concise, constructive engineering context per `team/AI_USAGE_POLICY.md`.

```markdown
*(Disclosure: drafted with AI assistance and reviewed/edited by me; see `team/AI_USAGE_POLICY.md`.)*

Strong +1 for the **opt-in** option (e.g., an explicit flag on `InvokeOptions` / `AgentConfig`) rather than making implicit trailing-`ToolUseBlock` (`toolUseBlock`) auto-dispatch the default in `strands-ts`.

From Python experience, implicitly skipping the model whenever the trailing message happens to contain a tool-use block creates a subtle footgun (documented in #3467 "Trusted Message History" and CVE-2026-18830 advisories): any wrapper or HTTP handler that passes caller-influenced `Message[]` / `MessageData[]` or `ContentBlock[]` / `ContentBlockData[]` arrays into `invoke()` can accidentally trigger direct tool execution with no model turn, middleware, or `BeforeModelCallEvent` mediation in between.

In `strands-ts`, keeping explicit provenance / opt-in on resume preserves the Principle of Least Surprise:
- **Session restore & interrupts:** can opt in automatically inside trusted SDK state machines (`Checkpoint` / `CheckpointResumeContent`, `InterruptState` / `InterruptResponseContent`, or an explicit resume flag).
- **Return-of-Control:** callers intentionally continuing from a synthetic or pre-computed `ToolUseBlock` pass the opt-in explicitly.
- **Unvalidated inputs (fail closed by default):** cannot accidentally bypass model evaluation — and when a caller passes an un-opted-in trailing `ToolUseBlock` (or a `user`-role `ToolUseBlock`), failing closed with an explicit error pointing to the opt-in flag is clearer and safer than silently forwarding an unmatched `ToolUseBlock` to the model (where most providers reject it anyway).

Related downstream hardening for Python wrappers: aws-samples/sample-strands-code-agent#6 and aws-samples/sample-strands-code-agent#7.
```

### Held Publish Command

> **Important:** Extract **only** the fenced `markdown` comment block from Section 1 above into `/tmp/comment_2489.md` (do **not** pass this whole wrapper file, the top HOLD notice, or Section 2's `aws/bedrock-agentcore-sdk-python` verification summary to `--body-file`).

```bash
gh issue comment 2489 \
  --repo strands-agents/harness-sdk \
  --body-file /tmp/comment_2489.md
```

---

## 2. Verification Summary: `aws/bedrock-agentcore-sdk-python` (No Issue/PR Needed)

Audited `aws/bedrock-agentcore-sdk-python` (`main`) directly against the CVE-2026-18830 / CoreBreak pattern:

- **`README.md`:** Quickstart `@app.entrypoint` example already enforces strict string typing before calling Strands:
  ```python
  prompt = request.get("prompt")
  if not isinstance(prompt, str):
      raise ValueError("prompt must be a string")
  ```
  accompanied by the explicit warning: *"Validate agent input before forwarding it to an agent framework. Keep prompts typed as strings and pass only prompt text to the agent."*
- **`src/bedrock_agentcore/runtime/app.py` (`BedrockAgentCoreApp.entrypoint`):** Docstring already warns explicitly: *"Invocation payloads are passed to the registered function unchanged. Applications should validate input before forwarding it to an agent framework."*
- **`src/bedrock_agentcore/runtime/ag_ui.py` (`AGUIApp.entrypoint`):** Docstring already warns explicitly: *"Adapters should validate message content after protocol parsing before forwarding it to another agent framework."*
- **`src/bedrock_agentcore/runtime/a2a.py`:** Wraps caller-supplied `AgentExecutor` instances (such as `StrandsA2AExecutor`, whose A2A part converter in `strands/multiagent/a2a/executor.py` only emits `text`, media, or validated `interruptResponse` blocks and serializes `DataPart` to text).

**Conclusion:** `aws/bedrock-agentcore-sdk-python` has already incorporated input-validation warnings and safe quickstart typing, and AWS mitigated the managed AgentCore `InvokeHarness` API server-side for CVE-2026-18830 — so no upstream issue or PR is needed there.
