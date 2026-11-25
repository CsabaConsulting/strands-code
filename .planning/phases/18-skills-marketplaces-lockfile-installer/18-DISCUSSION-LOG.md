# Phase 18: Skills Marketplaces & Lockfile Installer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `18-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-24
**Phase:** `18-skills-marketplaces-lockfile-installer`
**Areas discussed:** Remote fetch transport (`D-01`), Default marketplace & ad-hoc namespace policy (`D-02`), `scripts/*` warning & hash-drift strictness (`D-04`), Protected-path policy downgrade & live probe scope (`D-05`, `D-07`)

*(Pre-decided anchors from Roadmap, Requirement `SKILL-03`, and `v2.0` constraints not re-asked: support `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, and GitHub `owner/repo[@ref]` into `./.agent/skills-marketplaces/<ns>/<skill>/` with `./.agent/skills-lock.json` 40-char `commit_sha` + SHA-256 `computed_hash`, preserve `./.agent/skills/` for `local:` precedence and `BUILTIN_SLASH_HEADS` win rules, dynamic `/<ns>:` tab completion in `SlashCompleter`, reject symlinks/submodules/zip-slip with size/file caps, keep `allowed-tools` informational-only, render untrusted metadata via `print_plain`, frame third-party provenance explicitly on invocation, stay within `xenon C <= 20` and `lint-imports` boundaries, and keep `strands_code_agent/` pristine under `D-24`.)*

---

## Round 1: Transport, Default Catalogs, Lockfile Drift & Policy Protection

### Q1: Remote fetch transport (`D-01`)

How should remote marketplace catalogs and skill repos be fetched?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Pure HTTPS via `httpx` + stdlib `tarfile` | Resolve via GitHub API (`/commits/<ref>` -> `/tarball/<sha>`), honor optional `GITHUB_TOKEN`/`GH_TOKEN` header-only, plus local-path catalogs — zero `git` subprocess attack surface. | ✓ |
| Pure HTTPS for GitHub + guarded `git` subprocess fallback | Add guarded `git` (`core.hooksPath=/dev/null`, no submodules) for non-GitHub HTTPS Git hosts. | |
| Guarded `git` CLI subprocess for all remote repos | Use `git ls-remote` + shallow archive across all remote repos plus local-path catalogs. | |

**User's choice:** Pure HTTPS via `httpx` + stdlib `tarfile` (GitHub API `/commits/<ref>` -> `/tarball/<sha>`, optional `GITHUB_TOKEN`/`GH_TOKEN` header-only) plus local-path catalogs — zero `git` subprocess attack surface.

---

### Q2: Pre-registered marketplaces & ad-hoc `owner/repo` namespacing (`D-02`)

Should Phase 18 ship any pre-registered marketplaces, and how should ad-hoc `owner/repo` installs be namespaced?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Zero pre-registered marketplaces + flat `owner--repo` slug | Strict opt-in (example commands in help text); ad-hoc `owner/repo` installs use a flat sanitized slug `owner--repo` under `./.agent/skills-marketplaces/`. | ✓ |
| Curated opt-in presets + flat `owner--repo` slug | List curated preset hints in `/skills marketplace add` without auto-fetching until added; flat `owner--repo` slug for ad-hoc installs. | |
| Pre-register a default official catalog on first use | Auto-fetch a bundled official catalog on first `/skills browse`. | |

**User's choice:** Zero pre-registered marketplaces (strict opt-in; show example commands in help text); ad-hoc `owner/repo` installs use a flat sanitized slug like `owner--repo` under `./.agent/skills-marketplaces/`.

---

### Q3: `scripts/*` warnings & `skills-lock.json` hash-drift enforcement (`D-04`)

How strict should `scripts/*` warnings and `skills-lock.json` hash-drift checks be?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Warn prominently on `scripts/*` + warn-and-skip tampered skills on hash drift | Warn clearly on bundled `scripts/*` at install/update (still gated by `shell`/`python_repl` HITL), and warn-and-skip marketplace skills whose on-disk SHA-256 drifts from `skills-lock.json` until `/skills sync`. | ✓ |
| Require `--allow-scripts` flag + warn-and-skip on hash drift | Refuse script-bundling skills unless `--allow-scripts` is passed, plus warn-and-skip hash-drifted skills. | |
| Warn on `scripts/*` + load hash-drifted skills marked `[modified]` | Warn but keep loading locally edited marketplace skills with `[modified]`. | |

**User's choice:** Warn prominently on bundled `scripts/*` at install/update (never auto-executed; still gated by `shell`/`python_repl` HITL), and warn-and-skip tampered marketplace skills whose on-disk SHA-256 drifts from `skills-lock.json` until `/skills sync`.

---

### Q4: Protected-path `policy.core` defense & live GitHub probe (`D-05`, `D-07`)

How should `policy.core` protect skill/marketplace paths from broad repo `[[allow]]` rules, and should we include a live GitHub integration probe?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Downgrade broad `[[allow]]` globs to `Prompt` + offline suite + `@pytest.mark.integration` probe | Downgrade `write`/`edit` `Allow()` matching `.agent/skills*`, `.agent/skills-lock.json`, or `~/.config/strands-code/**` to `Prompt`, plus offline hermetic tests and `@pytest.mark.integration` live GitHub probe. | ✓ |
| Hard-Deny agent edits to marketplace/lockfile/config + Prompt on `.agent/skills/**` | Deny agent edits to `.agent/skills-marketplaces/**`, `.agent/skills-lock.json`, and `~/.config/strands-code/**` completely. | |
| Downgrade all protected paths to `Prompt` (offline tests only) | Downgrade to `Prompt` with offline hermetic tests only. | |

**User's choice:** Downgrade broad repo `[[allow]]` globs on `.agent/skills*`, `.agent/skills-lock.json`, and `~/.config/strands-code/**` to `Prompt` (blocks silent auto-approval while still letting the user approve intentional edits), plus offline hermetic tests + `@pytest.mark.integration` live GitHub probe.
