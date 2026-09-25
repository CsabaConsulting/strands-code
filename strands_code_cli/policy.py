"""Deterministic TOML allow/deny policy store + match engine (TOOL-03, D-05..D-08).

Shape mirrors :class:`strands_code_cli.diff_config.DiffConfig` exactly
(dataclass, platformdirs home, repo layer, symlink refusal fail-loud,
atomic tmp+replace save, 0o700 home dir) but persists TOML via stdlib
``tomllib`` (read) plus a hand-rolled serialiser for the repo's own narrow
rule schema (no new dependency). No smart/NL-policy strings, no Cedar,
no Phase 4 mode vocabulary.

Lookup (resolved item 1): layered UNION, not replace. Home
``~/.config/strands-code/policy.toml`` provides defaults; repo
``./.agent/policy.toml`` layers over it. Matching rules are collected
across both files plus builtins; deny-wins across the union (D-07).
Repo rules are checked first only for explanation order.

Load posture (resolved item 7): missing files yield built-in defaults;
ANY parse/schema violation (bad TOML, unknown key, unknown tool name,
malformed rule) logs a warning and falls back to built-in defaults, i.e.
prompt-on-everything-mutating (fail-closed, never allow-all). A symlinked
policy path raises ``ValueError`` fail-loud (``DiffConfig.load`` mirror).

User-facing TOML contract (print exactly this)::

    [options]
    trust_delegated = false  # D-12: true skips prompts inside delegated turns

    [[allow]]                # proceed silently
    tool = "shell"           # required: known tool name or "*"
    command = "git status"   # shell/python_repl: prefix of normalised command/code

    [[allow]]
    tool = "write"           # file tools: write | edit (read/search need no rules)
    path = "docs/*.md"       # glob via fnmatch; repo-relative AND absolute realpath

    [[deny]]                 # hard-deny, no prompt, rule named in refusal
    tool = "shell"
    command = "curl"

Schema rules: ``tool`` required (known name or ``"*"``); exactly one of
``path`` (file tools) or ``command`` (shell, python_repl) per rule.

Accepted residuals (D-14, risk 5): ``VAR=curl; $VAR x`` indirection,
pipes into interpreters (``curl x | sh`` still contains the ``curl``
substring so it prompts as network, but intent is unreadable), exotic
binaries outside the pattern list, and ``python_repl`` interior
``open()``/``socket`` calls (approval is all-or-nothing per execution;
it does NOT imply file/network confinement inside the snippet).
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

logger = logging.getLogger(__name__)

_CONFIG_DIR_NAME = "strands-code"
_CONFIG_FILE_NAME = "policy.toml"
_REPO_POLICY_REL = Path(".agent") / "policy.toml"

_KNOWN_KEYS = {"options", "allow", "deny"}
_KNOWN_OPTION_KEYS = {"trust_delegated"}
_KNOWN_RULE_KEYS = {"tool", "path", "command"}

# Tool names the policy schema recognises ("*" = any tool).
KNOWN_TOOLS = frozenset(
    {
        "shell",
        "read",
        "write",
        "edit",
        "search",
        "python_repl",
        "web_fetch",
        "web_search",
        "subagent",
        "programmatic_tool_caller",
    }
)

FILE_TOOLS = frozenset({"write", "edit", "read"})
COMMAND_TOOLS = frozenset({"shell", "python_repl"})

# Read-only tools pre-allowed by built-in default (D-09).
BUILTIN_ALLOWED_TOOLS = frozenset({"read", "search"})

# Network binaries substring-scanned in normalised shell text (D-14).
NETWORK_BINARIES = ("curl", "wget", "aria2c", "ssh", "scp", "rsync", "ftp", "sftp")

# curl upload/mutation flags: presence means the fetch is NOT GET-shaped (D-15).
_CURL_UPLOAD_FLAGS = (
    "-d",
    "--data",
    "--data-binary",
    "--data-raw",
    "--data-urlencode",
    "--upload-file",
    "-T",
    "--form",
    "--form-string",
    "--head",
    "-I",
)
_CURL_MUTATING_METHODS = ("POST", "PUT", "DELETE", "PATCH")

# `sh -c "..."` / `bash -c '...'` / `sh -lc "..."` one-level unwrap (resolved item 3).
_SHELL_PATTERN = re.compile(r"^(sh|bash)\s+(.*)$", re.DOTALL)
_FLAG_PATTERN = re.compile(r"^(-[a-zA-Z]+)\s+(.*)$", re.DOTALL)


def default_policy_config_path() -> Path:
    """User policy file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


def default_repo_policy_path() -> Path:
    """Repo policy file path (cwd-anchored ``./.agent/policy.toml``)."""
    return Path(os.getcwd()) / _REPO_POLICY_REL


@dataclass
class PolicyOptions:
    """Gate options (D-12)."""

    trust_delegated: bool = False


@dataclass
class Rule:
    """One allow/deny rule: ``tool`` plus exactly one of ``path``/``command``."""

    tool: str
    path: str | None = None
    command: str | None = None

    def describe(self) -> str:
        """Short human form used in prompts and refusal text."""
        selector = f'path "{self.path}"' if self.path is not None else f'command "{self.command}"'
        return f'{self.tool} {selector}'


@dataclass
class PolicyConfig:
    """Layered TOML policy: options + allow/deny rule lists."""

    options: PolicyOptions = field(default_factory=PolicyOptions)
    allow: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)

    @classmethod
    def load(
        cls,
        home_path: str | Path | None = None,
        repo_path: str | Path | None = None,
    ) -> PolicyConfig:
        """Load the layered union (home defaults + repo overlay), fail-closed.

        Missing files yield built-in defaults. Any parse/schema violation
        in either file warns and returns built-in defaults
        (prompt-all-mutating, never allow-all). Symlinked paths raise
        ``ValueError`` fail-loud.
        """
        home = Path(home_path) if home_path is not None else default_policy_config_path()
        repo = Path(repo_path) if repo_path is not None else default_repo_policy_path()
        for candidate in (home, repo):
            if candidate.is_symlink():
                raise ValueError(f"Policy file must not be a symlink: {candidate}")
        try:
            home_cfg = _load_one(home)
            repo_cfg = _load_one(repo)
        except (PolicySchemaError, tomllib.TOMLDecodeError, OSError, ValueError) as exc:
            logger.warning("Ignoring policy config, falling back to prompt-all defaults: %s", exc)
            return cls()
        merged = cls()
        for single in (home_cfg, repo_cfg):
            if single is None:
                continue
            merged.allow.extend(single.allow)
            merged.deny.extend(single.deny)
            if single.options.trust_delegated:
                merged.options.trust_delegated = True
        # Repo rules first for explanation order only (deny-wins is order-free).
        if repo_cfg is not None:
            merged.allow = list(repo_cfg.allow) + list(home_cfg.allow if home_cfg else [])
            merged.deny = list(repo_cfg.deny) + list(home_cfg.deny if home_cfg else [])
        return merged

    def append_rule(
        self,
        kind: str,
        rule: Rule,
        repo_path: str | Path | None = None,
    ) -> Path:
        """Append one narrow derived rule to the REPO policy file, atomically.

        Only ``allow``/``deny`` kinds; ``tool = "*"`` is refused (D-03
        narrow-rules-only). Symlinked targets raise ``ValueError``.
        """
        if kind not in ("allow", "deny"):
            raise ValueError(f"Rule kind must be 'allow' or 'deny', got {kind!r}")
        _validate_rule(rule)
        if rule.tool == "*":
            raise ValueError("Derived rules must be narrow (tool '*' refused)")
        resolved = Path(repo_path) if repo_path is not None else default_repo_policy_path()
        if resolved.is_symlink():
            raise ValueError(f"Policy file must not be a symlink: {resolved}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(resolved.parent, 0o700)
        existing = ""
        if resolved.exists():
            existing = resolved.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                existing += "\n"
        existing += _serialise_rule(kind, rule)
        tmp = resolved.with_suffix(".toml.tmp")
        tmp.write_text(existing, encoding="utf-8")
        os.replace(tmp, resolved)
        target = self.allow if kind == "allow" else self.deny
        target.append(rule)
        return resolved


class PolicySchemaError(ValueError):
    """Raised for any policy TOML shape violation (fail-closed upstream)."""


def _load_one(path: Path) -> PolicyConfig | None:
    """Load a single policy file; None when missing. Raises on violation."""
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        raise
    if data is None:
        return None
    if not isinstance(data, dict):
        raise PolicySchemaError(f"Policy file {path} must be a TOML mapping")
    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        raise PolicySchemaError(f"Unknown policy keys: {sorted(unknown)}")
    options = PolicyOptions()
    raw_options = data.get("options", {})
    if not isinstance(raw_options, dict):
        raise PolicySchemaError("Policy [options] must be a mapping")
    unknown_options = set(raw_options) - _KNOWN_OPTION_KEYS
    if unknown_options:
        raise PolicySchemaError(f"Unknown policy option keys: {sorted(unknown_options)}")
    if "trust_delegated" in raw_options:
        value = raw_options["trust_delegated"]
        if not isinstance(value, bool):
            raise PolicySchemaError("Policy trust_delegated must be a boolean")
        options.trust_delegated = value
    cfg = PolicyConfig(options=options)
    for kind in ("allow", "deny"):
        raw_rules = data.get(kind, [])
        if not isinstance(raw_rules, list):
            raise PolicySchemaError(f"Policy [[{kind}]] must be a list")
        for raw in raw_rules:
            rule = _parse_rule(raw)
            (cfg.allow if kind == "allow" else cfg.deny).append(rule)
    return cfg


def _parse_rule(raw: Any) -> Rule:
    """Validate one rule mapping; raises :class:`PolicySchemaError`."""
    if not isinstance(raw, dict):
        raise PolicySchemaError("Policy rule must be a mapping")
    unknown = set(raw) - _KNOWN_RULE_KEYS
    if unknown:
        raise PolicySchemaError(f"Unknown policy rule keys: {sorted(unknown)}")
    tool = raw.get("tool")
    if not isinstance(tool, str) or not tool:
        raise PolicySchemaError("Policy rule needs a 'tool' string")
    if tool != "*" and tool not in KNOWN_TOOLS:
        raise PolicySchemaError(f"Unknown policy rule tool: {tool!r}")
    rule = Rule(
        tool=tool,
        path=raw.get("path"),
        command=raw.get("command"),
    )
    _validate_rule(rule)
    return rule


def _validate_rule(rule: Rule) -> None:
    """Enforce exactly-one-of path/command and tool scoping."""
    has_path = rule.path is not None
    has_command = rule.command is not None
    if has_path == has_command:
        raise PolicySchemaError("Policy rule needs exactly one of 'path' or 'command'")
    if rule.tool != "*" and rule.tool not in KNOWN_TOOLS:
        raise PolicySchemaError(f"Unknown policy rule tool: {rule.tool!r}")
    if has_path and rule.tool not in FILE_TOOLS and rule.tool != "*":
        raise PolicySchemaError(f"'path' rules need a file tool, got {rule.tool!r}")
    if has_command and rule.tool not in COMMAND_TOOLS and rule.tool != "*":
        raise PolicySchemaError(f"'command' rules need shell/python_repl, got {rule.tool!r}")


def _serialise_rule(kind: str, rule: Rule) -> str:
    """Render one rule in the repo's own narrow schema (no TOML writer dep)."""
    lines = [f"[[{kind}]]", f'tool = "{rule.tool}"']
    if rule.path is not None:
        lines.append(f'path = "{rule.path}"')
    else:
        lines.append(f'command = "{rule.command}"')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Match engine (pure functions; no HITL imports here)
# ---------------------------------------------------------------------------


def normalise_command(cmd: str) -> str:
    """Strip, then unwrap ONE ``sh -c``/``bash -c``/``sh -lc`` quote level.

    Unwrapping is single-shot, not recursive (resolved item 3): allow
    rules match on PREFIX of the result, network detection scans the
    result for SUBSTRING binary names.
    """
    text = cmd.strip()
    shell = _SHELL_PATTERN.match(text)
    if not shell:
        return text
    rest = shell.group(2).strip()
    while True:
        flag = _FLAG_PATTERN.match(rest)
        if not flag:
            return text
        if "c" in flag.group(1)[1:]:
            inner = flag.group(2).strip()
            if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in ("'", '"'):
                return inner[1:-1]
            return inner
        rest = flag.group(2).strip()


def _tool_input_text(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Command/code text for command tools (shell/python_repl)."""
    if tool_name == "shell":
        value = tool_input.get("command", "")
    elif tool_name == "python_repl":
        value = tool_input.get("code", "")
    else:
        value = ""
    if not isinstance(value, str):
        return ""
    return value


def match_rule(rule: Rule, tool_name: str, tool_input: dict[str, Any], cwd: str | Path | None = None) -> bool:
    """True when ``rule`` covers this (tool, input) pair.

    Path rules fnmatch against the raw input path, the absolute path, the
    realpath, and the repo-relative path (when under ``cwd``). Command
    rules prefix-match the normalised command/code.
    """
    if rule.tool != "*" and rule.tool != tool_name:
        return False
    if rule.path is not None:
        raw = tool_input.get("path", "")
        if not isinstance(raw, str) or not raw:
            return False
        candidates = [raw]
        base = Path(cwd) if cwd is not None else Path(os.getcwd())
        absolute = raw if Path(raw).is_absolute() else str(base / raw)
        candidates.append(absolute)
        try:
            candidates.append(os.path.realpath(absolute))
        except OSError:
            pass
        try:
            rel = os.path.relpath(os.path.realpath(absolute), os.path.realpath(base))
            if not rel.startswith(".."):
                candidates.append(rel)
        except (OSError, ValueError):
            pass
        return any(fnmatch.fnmatch(c, rule.path) for c in candidates)
    if rule.command is not None:
        return normalise_command(_tool_input_text(tool_name, tool_input)).startswith(rule.command)
    return False


def is_fetch_get(command: str) -> bool:
    """True for GET-shaped read-only fetches (D-15): curl without upload or
    mutating-method flags, or ``git fetch``."""
    text = normalise_command(command)
    lowered = text.lower()
    if "git fetch" in lowered:
        return True
    if "curl" not in lowered:
        return False
    tokens = text.split()
    for pos, token in enumerate(tokens):
        low = token.lower()
        if low in _CURL_UPLOAD_FLAGS or any(
            low == flag or low.startswith(flag + "=") for flag in _CURL_UPLOAD_FLAGS if flag.startswith("--")
        ):
            return False
        if low in ("-X", "--request") and pos + 1 < len(tokens):
            if tokens[pos + 1].upper() in _CURL_MUTATING_METHODS:
                return False
        if low.startswith("-x") and len(low) > 2 and low[2:].upper() in _CURL_MUTATING_METHODS:
            return False
    if re.search(r"(?i)-X\s*(POST|PUT|DELETE|PATCH)", text):
        return False
    return True


def is_network_command(command: str) -> bool:
    """True when shell text needs at least a Prompt (D-14): network binary
    substrings, ``git push``/``git pull``, or the ``gh`` CLI."""
    text = normalise_command(command)
    lowered = text.lower()
    for binary in NETWORK_BINARIES:
        if binary in lowered:
            return True
    if "git push" in lowered or "git pull" in lowered:
        return True
    tokens = re.split(r"\s|[;|&()<>]", lowered)
    if "gh" in tokens:
        return True
    return False


# ---------------------------------------------------------------------------
# Verdicts + decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Allow:
    """Proceed silently."""


@dataclass(frozen=True)
class Prompt:
    """Prompt with full detail; ``reason`` is the one-line risk line (D-01)."""

    reason: str


@dataclass(frozen=True)
class Deny:
    """Hard-deny, no prompt; ``rule`` is named in the refusal (resolved item 2)."""

    rule: Rule | None = None
    reason: str = ""


def _allowed_roots_text(cwd: str | Path, policy: PolicyConfig) -> str:
    """Allowed-roots rendering for outside-scope denials (scope error shape)."""
    from strands_code_cli.scope import effective_roots

    roots = effective_roots(cwd, policy)
    return ", ".join(str(r) for r in roots)


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    policy: PolicyConfig,
    cwd: str | Path | None = None,
) -> Allow | Prompt | Deny:
    """Deny-first verdict across the rule union (D-06/D-07/D-13/D-15).

    Order: deny match (hard-deny) → allow match → built-in
    read/search/fetch allows → Prompt. Outside-scope file paths with no
    covering allow rule deny naming the allowed roots. Policy match runs
    BEFORE scope confinement (risk 6): an allow rule for an outside path
    grants roots the confiner then admits.
    """
    base = Path(cwd) if cwd is not None else Path(os.getcwd())
    if not isinstance(tool_input, dict):
        tool_input = {}
    for rule in policy.deny:
        if match_rule(rule, tool_name, tool_input, base):
            return Deny(rule=rule, reason=f"Denied by policy rule [deny {rule.describe()}]")
    for rule in policy.allow:
        if match_rule(rule, tool_name, tool_input, base):
            return Allow()
    if tool_name in BUILTIN_ALLOWED_TOOLS:
        return Allow()
    if tool_name in ("web_fetch", "web_search"):
        return Allow()  # D-16: pre-allowed fetches may hit any host
    if tool_name == "shell":
        command = _tool_input_text("shell", tool_input)
        if is_fetch_get(command):
            return Allow()
        if is_network_command(command):
            return Prompt(reason=f"Network action: {normalise_command(command)[:200]}")
        return Prompt(reason=f"Shell command: {normalise_command(command)[:200]}")
    if tool_name == "python_repl":
        code = _tool_input_text("python_repl", tool_input)
        return Prompt(reason=f"Python execution: {code[:200]}")
    if tool_name in FILE_TOOLS:
        raw = tool_input.get("path", "")
        from strands_code_cli.scope import effective_roots

        roots = effective_roots(base, policy)
        if isinstance(raw, str) and raw:
            from strands_code_cli.scope import resolve

            canonical = Path(os.path.realpath(resolve(raw, base)))
            if not any(canonical == r or r in canonical.parents for r in roots):
                allowed = ", ".join(str(r) for r in roots)
                return Deny(reason=f"Path {canonical} is outside the allowed roots: {allowed}")
        return Prompt(reason=f"File {tool_name}: {raw}")
    if tool_name == "subagent":
        return Prompt(reason="Delegated subtask inherits the gate (D-12)")
    return Prompt(reason=f"Tool {tool_name} is not pre-allowed")
