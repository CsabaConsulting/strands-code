"""Deterministic TOML allow/deny policy store + match engine (TOOL-03, D-05..D-08).

Shape mirrors :class:`strands_code_cli.policy.diff_config.DiffConfig` exactly
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
import json
import logging
import os
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs
import tomllib

from strands_code_cli.platform_io import atomic_write_text, refuse_symlink

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
        "skills",
        "search_memory",
        "retrieve_context",
        "strands_manage_background_task",
    }
)

FILE_TOOLS = frozenset({"write", "edit", "read"})
PATH_TOOLS = frozenset({"write", "edit", "read", "search"})
COMMAND_TOOLS = frozenset({"shell", "python_repl"})
TOOL_ONLY_TOOLS = frozenset(
    {
        "web_fetch",
        "web_search",
        "subagent",
        "programmatic_tool_caller",
        "skills",
        "search_memory",
        "retrieve_context",
        "strands_manage_background_task",
    }
)

# Read-only / internal harness tools pre-allowed by built-in default (D-03, D-05).
# Note: "read" itself evaluates scope & sensitive-path floors before allow fallback.
BUILTIN_ALLOWED_TOOLS = frozenset(
    {
        "read",
        "search",
        "skills",
        "search_memory",
        "retrieve_context",
        "strands_manage_background_task",
    }
)

# Network binaries substring-scanned in normalised shell text (D-14).
NETWORK_BINARIES = ("curl", "wget", "aria2c", "ssh", "scp", "rsync", "ftp", "sftp")

_CURL_UNSAFE_LONG_FLAGS = frozenset(
    {
        "--form",
        "--form-string",
        "--json",
        "--upload-file",
        "--output",
        "--output-dir",
        "--remote-name",
        "--remote-name-all",
        "--head",
        "--config",
        "--cookie-jar",
        "--dump-header",
        "--trace",
        "--trace-ascii",
        "--next",
    }
)
_CURL_UNSAFE_SHORT_CHARS = frozenset({"F", "T", "d", "o", "O", "I", "K", "c", "D", ":"})
_SHELL_RAW_META_CHARS = frozenset({";", "|", "&", "`", "\n", "\r", ">", "<"})
_FETCH_DISALLOWED_GIT_FLAGS = ("--upload-pack", "--exec")

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
    """One allow/deny rule: ``tool`` plus optional ``path`` or ``command``."""

    tool: str
    path: str | None = None
    command: str | None = None

    def describe(self) -> str:
        """Short human form used in prompts and refusal text."""
        if self.path is None and self.command is None:
            return self.tool
        selector = (
            f'path "{self.path}"'
            if self.path is not None
            else f'command "{self.command}"'
        )
        return f"{self.tool} {selector}"


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
        home = (
            Path(home_path) if home_path is not None else default_policy_config_path()
        )
        repo = Path(repo_path) if repo_path is not None else default_repo_policy_path()
        for label, candidate in (("home policy", home), ("repo policy", repo)):
            refuse_symlink(candidate, label, max_ancestors=1)
        try:
            home_cfg = _load_one(home)
            repo_cfg = _load_one(repo)
        except (PolicySchemaError, tomllib.TOMLDecodeError, OSError, ValueError) as exc:
            logger.warning(
                "Ignoring policy config, falling back to prompt-all defaults: %s", exc
            )
            return cls()
        merged = cls()
        for single in (home_cfg, repo_cfg):
            if single is None:
                continue
            merged.allow.extend(single.allow)
            merged.deny.extend(single.deny)
        # trust_delegated is strictly home-only (D-04): untrusted repos cannot opt in.
        if home_cfg is not None:
            merged.options.trust_delegated = home_cfg.options.trust_delegated
        if repo_cfg is not None and repo_cfg.options.trust_delegated:
            logger.warning(
                "Ignoring untrusted trust_delegated = true in repo policy %s; only home policy may enable it.",
                repo,
            )
        # Repo rules first for explanation order only (deny-wins is order-free).
        if repo_cfg is not None:
            merged.allow = list(repo_cfg.allow) + list(
                home_cfg.allow if home_cfg else []
            )
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
        narrow-rules-only). Symlinked targets/ancestors raise ``ValueError``.
        """
        if kind not in ("allow", "deny"):
            raise ValueError(f"Rule kind must be 'allow' or 'deny', got {kind!r}")
        _validate_rule(rule)
        if rule.tool == "*":
            raise ValueError("Derived rules must be narrow (tool '*' refused)")
        resolved = (
            Path(repo_path) if repo_path is not None else default_repo_policy_path()
        )
        refuse_symlink(resolved, "policy file", max_ancestors=1)
        existing = ""
        if resolved.exists():
            existing = resolved.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                existing += "\n"
        candidate_text = existing + _serialise_rule(kind, rule)
        tomllib.loads(candidate_text)
        atomic_write_text(
            resolved,
            candidate_text,
            mode=0o600,
            dir_mode=0o700,
            refuse_ancestors=1,
            label="policy file",
        )
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
        raise PolicySchemaError(
            f"Unknown policy option keys: {sorted(unknown_options)}"
        )
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
    """Enforce selector exclusivity and tool scoping."""
    has_path = rule.path is not None
    has_command = rule.command is not None
    if has_path and has_command:
        raise PolicySchemaError("Policy rule cannot set both 'path' and 'command'")
    if rule.tool != "*" and rule.tool not in KNOWN_TOOLS:
        raise PolicySchemaError(f"Unknown policy rule tool: {rule.tool!r}")
    if not has_path and not has_command:
        if rule.tool not in TOOL_ONLY_TOOLS:
            raise PolicySchemaError("Policy rule needs 'path' or 'command'")
        return
    if has_path and (
        not isinstance(rule.path, str)
        or not rule.path
        or (rule.tool not in PATH_TOOLS and rule.tool != "*")
    ):
        raise PolicySchemaError(f"'path' rules need a path tool, got {rule.tool!r}")
    if has_command and (not isinstance(rule.command, str) or not rule.command):
        raise PolicySchemaError("Policy command selector must be a non-empty string")
    if has_command and rule.tool not in COMMAND_TOOLS and rule.tool != "*":
        raise PolicySchemaError(
            f"'command' rules need shell/python_repl, got {rule.tool!r}"
        )


def _toml_rule_str(value: str, field_name: str) -> str:
    if any((ord(ch) < 32 and ch not in ("\t", "\n")) or ord(ch) == 127 for ch in value):
        raise ValueError(f"Disallowed control character in policy rule {field_name}")
    return json.dumps(value)


def _serialise_rule(kind: str, rule: Rule) -> str:
    """Render one rule with safe JSON/TOML string escaping."""
    _validate_rule(rule)
    lines = [f"[[{kind}]]", f"tool = {_toml_rule_str(rule.tool, 'tool')}"]
    if rule.path is not None:
        lines.append(f"path = {_toml_rule_str(rule.path, 'path')}")
    elif rule.command is not None:
        lines.append(f"command = {_toml_rule_str(rule.command, 'command')}")
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


def _has_unquoted_shell_metachars(text: str) -> bool:
    """True on backticks/subshell expansions anywhere or unquoted shell metacharacters."""
    quote: str | None = None
    escaped = False
    for idx, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            continue
        if ch in ("'", '"') and quote in (None, ch):
            quote = None if quote == ch else ch
            continue
        if quote != "'" and (ch == "`" or text[idx : idx + 2] == "$("):
            return True
        if quote is None and ch in _SHELL_RAW_META_CHARS:
            return True
    return quote is not None


def _has_shell_metachars(text: str, *, allow_quoted: bool = False) -> bool:
    """Detect shell metacharacters, subshells, and multiline control tokens."""
    if not allow_quoted:
        return "$(" in text or any(ch in _SHELL_RAW_META_CHARS for ch in text)
    return _has_unquoted_shell_metachars(text)


def _canonical_allow_pattern(pattern: str) -> str:
    """Canonicalize fixed base of an absolute allow glob without altering glob tokens."""
    if not Path(pattern).is_absolute():
        return pattern
    cut = len(pattern)
    for ch in ("*", "?", "["):
        pos = pattern.find(ch)
        if pos != -1:
            cut = min(cut, pos)
    prefix, tail = pattern[:cut], pattern[cut:]
    if "/" not in prefix:
        return pattern
    sep = prefix.rfind("/")
    dir_part = os.path.realpath(prefix[:sep] or "/")
    rem = prefix[sep:]
    if dir_part == "/":
        return rem + tail if rem.startswith("/") else "/" + rem + tail
    return dir_part + rem + tail


def _match_path_rule(
    pattern: str,
    tool_name: str,
    tool_input: dict[str, Any],
    base: Path,
    *,
    is_allow: bool,
) -> bool:
    raw = tool_input.get("path", "")
    if tool_name == "search" and (not isinstance(raw, str) or not raw):
        raw = "."
    if not isinstance(raw, str) or not raw:
        return False
    absolute = raw if Path(raw).is_absolute() else str(base / raw)
    candidates: list[str] = []
    if not is_allow:
        candidates.extend((raw, os.path.normpath(absolute)))
    try:
        real_abs = os.path.realpath(absolute)
        candidates.append(real_abs)
    except OSError:
        real_abs = os.path.normpath(absolute)
    try:
        rel = os.path.relpath(real_abs, os.path.realpath(base))
        if (
            rel != ".."
            and not rel.startswith(f"..{os.sep}")
            and not rel.startswith("../")
        ):
            candidates.append(rel)
    except (OSError, ValueError):
        pass
    target_pattern = _canonical_allow_pattern(pattern) if is_allow else pattern
    return any(fnmatch.fnmatch(cand, target_pattern) for cand in candidates)


def _match_command_rule(
    prefix: str, tool_name: str, tool_input: dict[str, Any], *, is_allow: bool
) -> bool:
    norm = normalise_command(_tool_input_text(tool_name, tool_input))
    if not is_allow or tool_name != "shell":
        return norm.startswith(prefix)
    if _has_shell_metachars(norm, allow_quoted=True):
        return False
    return norm == prefix or (
        norm.startswith(prefix)
        and len(norm) > len(prefix)
        and norm[len(prefix)].isspace()
    )


def match_rule(
    rule: Rule,
    tool_name: str,
    tool_input: dict[str, Any],
    cwd: str | Path | None = None,
    *,
    is_allow: bool = False,
) -> bool:
    """True when ``rule`` covers this (tool, input) pair.

    ``[[allow]]`` path rules match canonical realpath candidates ONLY;
    ``[[deny]]`` keeps raw and canonical candidates. ``[[allow]]`` shell rules
    reject unquoted metacharacters and require whitespace word boundaries.
    """
    if rule.tool != "*" and rule.tool != tool_name:
        return False
    if rule.path is not None:
        base = Path(cwd) if cwd is not None else Path(os.getcwd())
        return _match_path_rule(
            rule.path, tool_name, tool_input, base, is_allow=is_allow
        )
    if rule.command is not None:
        return _match_command_rule(
            rule.command, tool_name, tool_input, is_allow=is_allow
        )
    return rule.tool == tool_name


def _curl_long_flag_unsafe(low: str) -> bool:
    if low.startswith("--data"):
        return True
    return any(
        low == flag or low.startswith(flag + "=") for flag in _CURL_UNSAFE_LONG_FLAGS
    )


def _curl_short_flags_unsafe(tok: str) -> bool:
    if not tok.startswith("-") or tok.startswith("--") or len(tok) <= 1:
        return False
    body = tok[1:].split("=", 1)[0]
    return "X" in body or any(ch in _CURL_UNSAFE_SHORT_CHARS for ch in body)


def _is_safe_curl_args(args: Sequence[str]) -> bool:
    idx = 0
    while idx < len(args):
        tok = args[idx]
        if tok == "--":
            break
        if tok in ("-X", "--request"):
            if idx + 1 >= len(args) or args[idx + 1].upper() not in ("GET", "HEAD"):
                return False
            idx += 2
            continue
        if tok.startswith("--request=") or (tok.startswith("-X") and len(tok) > 2):
            method = (
                tok.split("=", 1)[1] if tok.startswith("--") else tok[2:].lstrip("=")
            )
            if method.upper() not in ("GET", "HEAD"):
                return False
            idx += 1
            continue
        if _curl_long_flag_unsafe(tok.lower()) or _curl_short_flags_unsafe(tok):
            return False
        idx += 1
    return True


def is_fetch_get(command: str) -> bool:
    """True for isolated GET-shaped fetches (D-02): ``curl`` without upload,
    write, or mutating flags, or exact ``git fetch``."""
    text = normalise_command(command)
    if _has_shell_metachars(text, allow_quoted=False):
        return False
    try:
        tokens = shlex.split(text)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] == "git" and len(tokens) >= 2 and tokens[1] == "fetch":
        return not any(
            t.lower() == f or t.lower().startswith(f + "=")
            for t in tokens[2:]
            for f in _FETCH_DISALLOWED_GIT_FLAGS
        )
    if tokens[0] == "curl":
        return _is_safe_curl_args(tokens[1:])
    return False


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
    from strands_code_cli.policy.scope import effective_roots

    roots = effective_roots(cwd, policy)
    return ", ".join(str(r) for r in roots)


def _decide_shell(tool_input: dict[str, Any]) -> Allow | Prompt:
    """Verdict for shell: GET-shaped fetch allows, else prompt the command."""
    command = _tool_input_text("shell", tool_input)
    if is_fetch_get(command):
        return Allow()
    if is_network_command(command):
        return Prompt(reason=f"Network action: {normalise_command(command)[:200]}")
    return Prompt(reason=f"Shell command: {normalise_command(command)[:200]}")


def _decide_file_tool(
    tool_name: str, tool_input: dict[str, Any], base: Path, policy: PolicyConfig
) -> Prompt | Deny:
    """Verdict for write/edit file tools: outside-scope paths deny, else prompt."""
    raw = tool_input.get("path", "")
    from strands_code_cli.policy.scope import effective_roots, resolve

    roots = effective_roots(base, policy, tool_name=tool_name)
    if isinstance(raw, str) and raw:
        canonical = Path(os.path.realpath(resolve(raw, base)))
        if not any(canonical == r or r in canonical.parents for r in roots):
            allowed = ", ".join(str(r) for r in roots)
            return Deny(
                reason=f"Path {canonical} is outside the allowed roots: {allowed}"
            )
    return Prompt(reason=f"File {tool_name}: {raw}")


def _decide_read_or_search_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    base: Path,
    policy: PolicyConfig,
) -> Allow | Prompt:
    """Unboxed read/search check: sensitive secret paths & outside-scope targets prompt (D-03)."""
    raw = tool_input.get("path", "")
    if tool_name == "read" and _is_sensitive_read_path(raw, base):
        return Prompt(reason=f"Sensitive path ({raw}): approve explicit read")
    if tool_name == "search" and _is_sensitive_search_input(tool_input, base):
        detail = raw or str(tool_input.get("file_glob", ""))
        return Prompt(reason=f"Sensitive path ({detail}): approve explicit search")
    if isinstance(raw, str) and raw:
        from strands_code_cli.policy.scope import effective_roots, resolve

        roots = effective_roots(base, policy, tool_name=tool_name)
        canonical = Path(os.path.realpath(resolve(raw, base)))
        if not any(canonical == r or r in canonical.parents for r in roots):
            allowed = ", ".join(str(r) for r in roots)
            return Prompt(
                reason=f"Path {canonical} is outside the allowed roots: {allowed}"
            )
    return Allow()


def _path_matches_protected(
    candidate: Path, dirs: tuple[Path, ...], files: tuple[Path, ...]
) -> bool:
    return any(candidate == f for f in files) or any(
        candidate == d or d in candidate.parents for d in dirs
    )


def _is_env_filename(cand: Path) -> bool:
    return cand.name == ".env" or cand.name.startswith(".env.")


def _candidate_path_variants(raw: object, base: Path) -> tuple[list[Path], list[Path]]:
    if not isinstance(raw, str) or not raw:
        return [], []
    from strands_code_cli.policy.scope import resolve

    target = resolve(raw, base)
    candidates = [Path(os.path.normpath(str(target)))]
    try:
        candidates.append(Path(os.path.realpath(target)))
    except OSError:
        pass

    base_variants = [base]
    try:
        real_base = Path(os.path.realpath(base))
        if real_base != base:
            base_variants.append(real_base)
    except OSError:
        pass
    return candidates, base_variants


def _add_resolved_dir(bucket: list[Path], raw_dir: str | Path | None) -> None:
    if not raw_dir:
        return
    p = Path(str(raw_dir))
    bucket.append(Path(os.path.normpath(str(p))))
    try:
        bucket.append(Path(os.path.realpath(p)))
    except OSError:
        pass


def _is_sensitive_read_path(raw: object, base: Path) -> bool:
    """True when ``read`` targets ``.env*``, ``~/.ssh/*``, or ``~/.aws/*``."""
    candidates, _ = _candidate_path_variants(raw, base)
    if not candidates:
        return False
    home = Path.home()
    secret_dirs: list[Path] = []
    _add_resolved_dir(secret_dirs, home / ".ssh")
    _add_resolved_dir(secret_dirs, home / ".aws")
    dirs_tuple = tuple(secret_dirs)
    return any(
        _is_env_filename(cand)
        or _path_matches_protected(cand, dirs_tuple, ())
        or ".ssh" in cand.parts
        or ".aws" in cand.parts
        for cand in candidates
    )


def _is_sensitive_search_input(tool_input: dict[str, Any], base: Path) -> bool:
    """True when ``search`` targets sensitive secret paths or secret globs (D-03)."""
    if _is_sensitive_read_path(tool_input.get("path", ""), base):
        return True
    raw_glob = tool_input.get("file_glob", "")
    if isinstance(raw_glob, str):
        lowered = raw_glob.lower()
        return any(token in lowered for token in (".env", ".ssh", ".aws"))
    return False


def _is_protected_skills_or_config_path(raw: object, base: Path) -> bool:
    """True when a write/edit target resolves into protected repo/host trees (D-03)."""
    candidates, base_variants = _candidate_path_variants(raw, base)
    if not candidates:
        return False

    protected_dirs: list[Path] = []
    for raw_dir in (
        platformdirs.user_config_dir("strands-code"),
        platformdirs.user_cache_dir("strands-code"),
        os.environ.get("STRANDS_CODE_CACHE_DIR", "").strip(),
        platformdirs.user_config_dir("strands-box"),
        platformdirs.user_data_dir("strands-box"),
    ):
        _add_resolved_dir(protected_dirs, raw_dir)

    protected_files: list[Path] = []
    for root in base_variants:
        protected_dirs.append(root / ".agent")
        protected_dirs.append(root / ".git")
        protected_files.append(root / "STRANDS.md")

    dirs_tuple = tuple(protected_dirs)
    files_tuple = tuple(protected_files)
    return any(
        _is_env_filename(cand) or _path_matches_protected(cand, dirs_tuple, files_tuple)
        for cand in candidates
    )


def _check_allow_rules(
    tool_name: str, tool_input: dict[str, Any], base: Path, policy: PolicyConfig
) -> Allow | Prompt | None:
    for rule in policy.allow:
        if not match_rule(rule, tool_name, tool_input, base, is_allow=True):
            continue
        raw_path = tool_input.get("path", "")
        if tool_name in ("write", "edit") and _is_protected_skills_or_config_path(
            raw_path, base
        ):
            return Prompt(
                reason=f"Protected path ({raw_path}): approve explicit {tool_name}"
            )
        if tool_name == "read" and _is_sensitive_read_path(raw_path, base):
            return Prompt(reason=f"Sensitive path ({raw_path}): approve explicit read")
        if tool_name == "search" and _is_sensitive_search_input(tool_input, base):
            detail = raw_path or str(tool_input.get("file_glob", ""))
            return Prompt(reason=f"Sensitive path ({detail}): approve explicit search")
        return Allow()
    return None


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    policy: PolicyConfig,
    cwd: str | Path | None = None,
) -> Allow | Prompt | Deny:
    """Deny-first verdict across the rule union (D-02..D-05).

    Order: deny match (hard-deny) -> allow match (downgraded to Prompt for
    protected write/edit or sensitive read/search) -> read/search scope & secret check ->
    built-in read-only/internal allows -> Prompt / outside-scope write Deny.
    """
    base = Path(cwd) if cwd is not None else Path(os.getcwd())
    if not isinstance(tool_input, dict):
        tool_input = {}
    for rule in policy.deny:
        if match_rule(rule, tool_name, tool_input, base, is_allow=False):
            return Deny(
                rule=rule, reason=f"Denied by policy rule [deny {rule.describe()}]"
            )
    allow_verdict = _check_allow_rules(tool_name, tool_input, base, policy)
    if allow_verdict is not None:
        return allow_verdict
    if tool_name in ("read", "search"):
        return _decide_read_or_search_tool(tool_name, tool_input, base, policy)
    if tool_name in BUILTIN_ALLOWED_TOOLS:
        return Allow()
    if tool_name in ("web_fetch", "web_search"):
        return Allow()  # D-16: pre-allowed fetches may hit any host
    if tool_name == "shell":
        return _decide_shell(tool_input)
    if tool_name == "python_repl":
        code = _tool_input_text("python_repl", tool_input)
        return Prompt(reason=f"Python execution: {code[:200]}")
    if tool_name in FILE_TOOLS:
        return _decide_file_tool(tool_name, tool_input, base, policy)
    if tool_name == "subagent":
        return Prompt(reason="Delegated subtask inherits the gate (D-12)")
    return Prompt(reason=f"Tool {tool_name} is not pre-allowed")
