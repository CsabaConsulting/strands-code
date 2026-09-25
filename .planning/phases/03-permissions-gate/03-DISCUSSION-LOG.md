# Phase 3: Permissions Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-25
**Phase:** 3-Permissions Gate
**Areas discussed:** Approval prompt UX, Policy file design, Defaults & double-prompting, Scope expansion & network

---

## Approval prompt UX

| Option | Description | Selected |
|--------|-------------|----------|
| Full detail | Every prompt shows the exact command or diff plus a one-line risk reason | ✓ |
| Compact one-liner | Short summary with detail on demand | |

| Option | Description | Selected |
|--------|-------------|----------|
| Skip and continue | Denied action skipped; agent explains and continues the turn | ✓ |
| Abort the turn | Any deny stops the whole turn immediately | |

| Option | Description | Selected |
|--------|-------------|----------|
| Offer to remember | After a deny, offer 'always deny this' to append a policy rule | ✓ |
| One-shot only | Denies apply once; standing rules edited by hand | |

| Option | Description | Selected |
|--------|-------------|----------|
| Approve the batch | Repeated similar actions collapse into one prompt | ✓ |
| Prompt every time | Each action prompts individually | |

**User's choice:** Full detail, skip-and-continue, offer-to-remember, batch approval.
**Notes:** No follow-up clarification needed; all first-round picks.

---

## Policy file design

| Option | Description | Selected |
|--------|-------------|----------|
| TOML allow/deny lists | Simple allow/deny rule lists, human-editable | ✓ |
| Natural-language policy | Plain-English policy, LLM-classified per action | |

| Option | Description | Selected |
|--------|-------------|----------|
| Tool + path/command | Rules match tool name plus path globs or command prefixes | ✓ |
| Tool names only | Rules allow/deny whole tools | |

| Option | Description | Selected |
|--------|-------------|----------|
| Deny wins | Allow+deny match → deny wins | ✓ |
| Most specific wins | Longest match wins either way | |

| Option | Description | Selected |
|--------|-------------|----------|
| Repo-local + home default | `./.agent/policy.toml` overrides home default | ✓ |
| Home only | Single user-wide file | |

**User's choice:** TOML, tool+path/command dimensions, deny-wins, repo-over-home layering.
**Notes:** No follow-up clarification needed.

---

## Defaults & double-prompting

| Option | Description | Selected |
|--------|-------------|----------|
| Reads pre-allowed | read/search never prompt; mutations prompt until policy says otherwise | ✓ |
| Literally everything prompts | Even reads prompt on day one | |

| Option | Description | Selected |
|--------|-------------|----------|
| One prompt total | Gate approval covers the write; /diff never re-prompts | ✓ |
| Keep both prompts | Gate + /diff each prompt per write | |

| Option | Description | Selected |
|--------|-------------|----------|
| Prompt like shell | python_repl prompts with code shown; closes the bypass | ✓ |
| Leave ungated for now | python_repl keeps sandbox-only protection | |

| Option | Description | Selected |
|--------|-------------|----------|
| Inherit and prompt | Delegated turns prompt too | ✓ |
| Trust parent approval | Delegate runs under launch approval | |

**User's choice:** Reads pre-allowed, one prompt total, python_repl gated, inherit-and-prompt default.
**Notes:** User added nuance on the last question: trust-parent approval should also be available as a policy config option.

---

## Scope expansion & network

| Option | Description | Selected |
|--------|-------------|----------|
| Policy file owns it | Out-of-scope paths denied unless an allow rule names them | ✓ |
| Separate prompt each time | Out-of-scope access always prompts, never encodable | |

| Option | Description | Selected |
|--------|-------------|----------|
| Pattern-match commands | curl/wget/ssh/git-fetch patterns classified as network | ✓ |
| Prompt all shell | Every shell command prompts regardless | |

| Option | Description | Selected |
|--------|-------------|----------|
| Deny by default | Network actions prompt unless explicitly allowed | |
| Allow common fetches | Read-only fetches pre-allowed; uploads/mutations prompt | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Any host allowed | Pre-allowed fetches may hit any destination | ✓ |
| Host allowlist in policy | Restrict fetches to named hosts | |

**User's choice:** Policy owns expansion, pattern-match network detection, pre-allowed read-only fetches to any host.
**Notes:** User picked convenience over strictness on network defaults against the recommendation; exfiltration-via-URL-params tradeoff explicitly accepted and recorded in CONTEXT.md D-15.

---

## the agent's Discretion

TOML schema details, prompt rendering shape, network pattern list contents, deny-skip agent messaging.

## Deferred Ideas

- Host allowlist for pre-allowed fetches (later tightening of D-16).
- Natural-language policy classification (rejected for now; revisit if TOML proves rigid).
