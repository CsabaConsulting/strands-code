# Phase 2 UAT — File/Edit/Shell Surface + /diff

**Date:** 2026-09-25 (conversational, live CLI)
**Result: 5/5 passed, 0 blockers.**

| # | Test | Action | Observed | Verdict |
|---|------|--------|----------|---------|
| 1 | `/diff` empty state | `/diff show` | `Diff mode: on-demand (0 pending).` | PASS |
| 2 | Mode switch + persistence | `/diff approve-each`, restart, `/diff show` | `Diff mode set to approve-each.` then `Diff mode: approve-each (0 pending).` | PASS |
| 3 | `/search` | `/search builtin_tools` (repo cwd) | Many `path:line:match` hits across repo | PASS with observation |
| 4 | Agent live read | "Read router.py, list slash commands" | Agent chained `shell` + `read` builtins, correct command table | PASS |
| 5 | Diff gate approve-each | "Create /tmp/diffprobe.txt…" | Per-hunk unified diff + `Apply? [y/N]` prompt; approved, file written byte-exact (15 B, no trailing newline, agent self-verified) | PASS |

**Observations (non-blocking):**
- T3: first attempt from a non-repo cwd returned "No matches found" — correct scoping behavior, not a bug. `/search` also sweeps `.planning` and `.venv` (noisy but lexical-correct; consider default excludes in a later phase).
- T4: `python_repl` refused `import subprocess` per its allowlist; agent recovered via `shell`. Sandbox behaving as designed.
- T5: diff header shows `a//tmp/...` (doubled slash, cosmetic only).
