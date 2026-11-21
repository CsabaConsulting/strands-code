# Upstream PR Draft: Reject Caller-Supplied `toolUse` Blocks & Document Wrapper Input Validation

- **Target repo:** `aws-samples/sample-strands-code-agent` (`main`, based on `3832c5b` / `v0.5.0`)
- **Prepared local branch:** `upstream-pr/reject-caller-tool-use` (commit `239395d`)

---

## PR Title

```text
Add RejectCallerToolUseHook and wrapper input-validation security note
```

## PR Description Body

### Summary

Adds defense-in-depth hardening against unmediated tool execution from unvalidated caller payloads (the publicly disclosed "CoreBreak" / CVE-2026-18830 pattern) when `CodeAgent` is embedded behind API or service handlers:

- Adds `RejectCallerToolUseHook` (exported in `strands_code_agent`) registered on `BeforeInvocationEvent` by default (`reject_caller_tool_use: bool = True` on `CodeAgent.__init__`).
  - Rejects invocations (`ValueError`) if any incoming `"user"`-role message or the trailing incoming message in `event.messages` contains a `"toolUse"` block.
  - Preserves normal `str` prompts, allowlisted `ContentBlock` lists (`text`, `image`, `document`), paired historical `[user(text), assistant(toolUse), user(toolResult), user(text)]` transcripts, and multi-turn model-driven `python_repl` loops.
  - Copies any caller-supplied `hooks` list before appending `RejectCallerToolUseHook` and supports `reject_caller_tool_use=False` to opt out for trusted replay flows.
  - Uses a defensive import for `strands.hooks` (`BeforeInvocationEvent`, `HookProvider`, `HookRegistry`) so compatibility with `strands-agents>=0.1.0` stays intact.
- Updates `README.md`:
  - Documents `reject_caller_tool_use` in the `CodeAgent` parameter table.
  - Adds a concise **Input Validation for Service / API Wrappers** section under `## Security`.
- Adds offline unit and `Agent` integration tests in `tests/test_code_agent.py` (`TestCallerToolUseGuard`).

### Files Modified

- `strands_code_agent/code_agent.py`
- `strands_code_agent/__init__.py`
- `README.md`
- `tests/test_code_agent.py`

### Testing

Executed the full non-integration suite on commit `239395d` against `strands-agents==1.65.0`:

```bash
pytest tests/ -q
# 219 passed, 5 deselected (integration marker deselected by pyproject.toml), exit code 0
```

Verified offline scenarios in `TestCallerToolUseGuard`:
1. `RejectCallerToolUseHook` is appended cleanly to a copied `hooks` list by default, and omitted when `reject_caller_tool_use=False`.
2. Raw `[{"toolUse": ...}]`, `[{"role": "user", "content": [{"toolUse": ...}]}]`, and trailing `[{"role": "assistant", "content": [{"toolUse": ...}]}]` inputs raise `ValueError` before model or `python_repl` execution.
3. Opting out via `reject_caller_tool_use=False` preserves the native SDK execution path.
4. Plain `str` prompts, allowlisted `[{"text": ...}]` lists, paired historical `toolUse`/`toolResult` transcripts, and live model-initiated `python_repl` loops all succeed normally.

### Checklist

- [x] Rebased cleanly onto latest `upstream/main` (`3832c5b`, `v0.5.0`)
- [x] Focused diff with no unrelated formatting changes
- [x] Local test suite passes (`219 passed, 5 deselected`)
- [x] License confirmed: MIT-0

---

## Commands to Publish Branch & Open Issue / PR

Note: `gh` is not currently authenticated in this environment (`gh auth status`). Once signed in (`gh auth login`), run:

```bash
# 1. File the companion issue first (per CONTRIBUTING.md)
gh issue create \
  --repo aws-samples/sample-strands-code-agent \
  --title "Defense-in-depth: warn against unvalidated ContentBlock/Message forwarding & guard caller-supplied toolUse blocks" \
  --body-file docs/upstream/sample_code_agent_cve_2026_18830_issue.md

# 2. Push the tested PR branch to your fork (origin) and open the PR
git push -u origin upstream-pr/reject-caller-tool-use
gh pr create \
  --repo aws-samples/sample-strands-code-agent \
  --base main \
  --head CsabaConsulting:upstream-pr/reject-caller-tool-use \
  --title "Add RejectCallerToolUseHook and wrapper input-validation security note" \
  --body-file docs/upstream/sample_code_agent_cve_2026_18830_pr.md
```
