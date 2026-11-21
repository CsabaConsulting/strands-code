# Phase 3 UAT — Permissions Gate (TOOL-03)

**Date:** 2026-09-25 (conversational, live CLI, repo cwd)
**Result: 5/5 passed, 0 blockers.**

| # | Test | Action | Observed | Verdict |
|---|------|--------|----------|---------|
| 1 | `/policy show` | `/policy show` | `Effective policy (deny-wins across home + repo union): Builtins: allow read, search; allow GET-shaped fetch, git fetch.` | PASS |
| 2 | Shell mutation prompts | `mkdir -p /tmp/gatetest && echo probe > …` via shell, approve | Full-detail prompt (exact command + `Risk:` line, `[y/n/always/never]`); approved → exit 0. Agent's own follow-up `ls`/`cat` verification prompted again (deny-first per call). | PASS |
| 3 | Deny skips + continues | `printf … > denied.txt` via shell, answer `n` | `CONFIRMATION_FAILED` tool error; agent verified `denied.txt` absent via `read` (FileNotFoundError), explained, offered alternatives, no retry loop. | PASS |
| 4 | Write prompts once | `write` tool create `single.txt`, approve | Exactly ONE prompt (gate subsumed per-hunk diff prompt — D-10 holds); diff rendered inline; applied. `/diff show` → `approve-each (0 pending)`. | PASS |
| 5 | `python_repl` gated | `print(6*7)` via python, approve | Prompt showed the code + `Risk: Python execution: …`; approved → `42`. | PASS |

**Observations (non-blocking):**
- T3–T4: the agent's closing narration repeatedly claimed actions went through "without a prompt"/"ungated" when the transcript shows approval prompts were rendered and answered. Model confabulation about conversation history, not a gate defect — the gate evidence (rendered prompts, user answers, enforcement) is unambiguous in-transcript. Possible follow-up: prompt steering so the agent describes gating accurately (Phase 4+ polish, not this phase).
- T2: `Risk:` line echoes the full command verbatim (redundant with `Detail:` for shell). Cosmetic; risk-reason quality is planner discretion for a later pass.
- Probe files under `/tmp/gatetest/` cleaned after UAT.
