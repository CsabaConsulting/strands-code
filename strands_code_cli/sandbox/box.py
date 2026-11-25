"""Strands Box Linux containment config, 7-provider egress, Dogwood policy & diagnostics (SANDBOX-01)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs
import typer
from rich.console import Console

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    tomllib = None  # type: ignore[assignment]

from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.routing.core import RoutingStrategy, load_strategy
from strands_code_cli.ui.output import print_plain

_BOX_APP_NAME = "strands-box"
_CODE_APP_NAME = "strands-code"
_REPOS_DIR = "repos"
_TRUTHY = frozenset({"1", "true", "yes"})

CORE_PROVIDERS: tuple[str, ...] = (
    "bedrock",
    "google",
    "anthropic",
    "openai",
    "meta",
    "openrouter",
    "typesafe",
)
OPTIONAL_PROFILES: tuple[str, ...] = ("decisions_api", "github_skills")
_ALL_PROFILES = frozenset((*CORE_PROVIDERS, *OPTIONAL_PROFILES))
_BOX_BINARIES: tuple[str, ...] = (
    "box",
    "strands-box-contain-trampoline",
    "strands-box-sock-alias",
)
_SYSTEM_READ_DIRS: tuple[str, ...] = (
    "/usr",
    "/bin",
    "/lib",
    "/lib64",
    "/etc/ssl",
    "/etc/resolv.conf",
)
_SYSTEM_READ_FILES: tuple[str, ...] = ("/etc/hosts", "/etc/nsswitch.conf")
_APPARMOR_SYSCTL = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
_APPARMOR_PROFILE = Path("/etc/apparmor.d/strands-box")
APPARMOR_PROFILE_SNIPPET = """abi <abi/4.0>,
include <tunables/global>

profile strands-box /usr/local/libexec/strands-box/{box,strands-box-contain-trampoline} flags=(unconfined) {
  userns,
  include if exists <local/strands-box>
}"""

_REGION_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
_AWS_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class EgressSpec:
    """One Strands Box TOML ``[egress.<name>]`` section and Dogwood targets."""

    section: str
    destinations: tuple[str, ...]
    secret_ref: str | None = None
    placement: str | None = None
    header: str | None = None
    prefix: str | None = None


@dataclass(frozen=True)
class BoxInitResult:
    """Result returned by :func:`init_box_config`."""

    config_dir: Path
    box_toml: Path
    policy_dw: Path
    providers: tuple[str, ...]
    warnings: tuple[str, ...]
    self_tamper_risk: bool


@dataclass(frozen=True)
class BoxDoctorCheck:
    """Single read-only Linux / Box / config check."""

    name: str
    ok: bool
    detail: str
    remediation: str | None = None


@dataclass(frozen=True)
class BoxDoctorReport:
    """Aggregate report produced by :func:`run_box_doctor`."""

    checks: tuple[BoxDoctorCheck, ...]
    ok: bool


def _nonempty(name: str, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    val = source.get(name)
    return isinstance(val, str) and bool(val.strip())


def is_in_strands_box(env: Mapping[str, str] | None = None) -> bool:
    """Return True when running inside Strands Box (``STRANDS_BOX`` truthy)."""
    source = os.environ if env is None else env
    raw = source.get("STRANDS_BOX", "")
    return isinstance(raw, str) and raw.strip().lower() in _TRUTHY


def _reject_control_chars(value: str, label: str) -> str:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"Invalid control character in {label}")
    return value


def _toml_str(value: str, label: str = "value") -> str:
    _reject_control_chars(value, label)
    return json.dumps(value)


def _toml_list(values: Sequence[str], label: str = "list") -> str:
    return "[" + ", ".join(_toml_str(v, label) for v in values) + "]"


def _validate_region(region: str) -> str:
    cleaned = _reject_control_chars(region.strip(), "AWS region")
    if not _REGION_RE.match(cleaned):
        raise ValueError(f"Invalid AWS region {region!r}")
    return cleaned


def _validate_aws_profile(profile: str) -> str:
    cleaned = _reject_control_chars(profile.strip(), "AWS profile")
    if (
        not cleaned
        or cleaned in (".", "..")
        or ".." in cleaned
        or not _AWS_PROFILE_RE.match(cleaned)
    ):
        raise ValueError(f"Invalid AWS profile {profile!r}")
    return cleaned


def _refuse_symlink(path: Path, label: str = "path") -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing symlink {label}: {path}")
    if path.parent.is_symlink():
        raise ValueError(f"Refusing symlink parent for {label}: {path.parent}")


def _atomic_write_text(path: Path, content: str) -> Path:
    _refuse_symlink(path, str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def repo_config_id(repo_root: Path) -> str:
    """Return unique ``<slug>-<hash8>`` identifier for ``repo_root`` (D-02)."""
    resolved = Path(os.path.realpath(repo_root))
    slug = re.sub(r"[^a-z0-9]+", "-", resolved.name.lower()).strip("-") or "repo"
    slug = slug[:32].rstrip("-") or "repo"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def default_box_config_dir(repo_root: Path) -> Path:
    """Return host-only ``~/.config/strands-box/repos/<repo-id>`` directory."""
    base = Path(platformdirs.user_config_dir(_BOX_APP_NAME))
    return base / _REPOS_DIR / repo_config_id(repo_root)


def default_box_data_dir(repo_root: Path) -> Path:
    """Return host-only ``~/.local/share/strands-box/repos/<repo-id>`` box_dir."""
    base = Path(platformdirs.user_data_dir(_BOX_APP_NAME))
    return base / _REPOS_DIR / repo_config_id(repo_root)


def _provider_from_model_id(model_id: str | None) -> str | None:
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    cleaned = model_id.strip()
    if cleaned.startswith("arn:") or "/" not in cleaned:
        return "bedrock"
    prefix, _, rest = cleaned.partition("/")
    low = prefix.lower()
    if low in ("bedrock", "google", "anthropic", "openai", "meta", "openrouter"):
        return low
    if low == "litellm":
        sub = rest.partition("/")[0].lower()
        if sub == "openrouter":
            return "openrouter"
    return None


def _providers_from_routing(
    strategy: RoutingStrategy | None,
) -> tuple[set[str], bool]:
    if strategy is None:
        return set(), False
    found: set[str] = set()
    engines = strategy.engine.order or [strategy.engine.primary]
    needs_decisions_api = "decisions_api" in engines
    if "native" in engines:
        found.add("typesafe")
    if "openrouter" in engines:
        found.add("openrouter")
    if "llm" in engines:
        prov = _provider_from_model_id(strategy.engine.llm_model)
        if prov:
            found.add(prov)
    for cand in strategy.candidates:
        prov = _provider_from_model_id(cand.id)
        if prov:
            found.add(prov)
    return found, needs_decisions_api


def _providers_from_env(env: Mapping[str, str]) -> set[str]:
    checks = (
        ("bedrock", ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_PROFILE")),
        ("google", ("GOOGLE_API_KEY", "GEMINI_API_KEY")),
        ("anthropic", ("ANTHROPIC_API_KEY",)),
        ("openai", ("OPENAI_API_KEY",)),
        ("meta", ("MODEL_API_KEY", "META_API_KEY")),
        ("openrouter", ("OPENROUTER_API_KEY",)),
        ("typesafe", ("TYPESAFE_API_KEY",)),
    )
    return {name for name, keys in checks if any(_nonempty(key, env) for key in keys)}


def _safe_load_provider_config() -> ProviderConfig:
    try:
        return ProviderConfig.load()
    except ValueError:
        return ProviderConfig()


def _safe_load_strategy(repo_root: Path) -> RoutingStrategy | None:
    try:
        return load_strategy(repo_path=repo_root / ".agent" / "routing.yaml")
    except ValueError:
        return None


def detect_active_providers(
    repo_root: Path,
    *,
    config: ProviderConfig | None = None,
    routing_strategy: RoutingStrategy | None = None,
    env: Mapping[str, str] | None = None,
    allow_decisions_api: bool = False,
    allow_github_skills: bool = False,
) -> list[str]:
    """Detect minimal active egress profiles from config, routing, and env presence."""
    env_map = os.environ if env is None else env
    cfg = config if config is not None else _safe_load_provider_config()
    strategy = (
        routing_strategy
        if routing_strategy is not None
        else _safe_load_strategy(repo_root)
    )
    detected: set[str] = set()
    cfg_prov = _provider_from_model_id(cfg.model)
    if cfg_prov:
        detected.add(cfg_prov)
    route_provs, _ = _providers_from_routing(strategy)
    detected.update(route_provs)
    detected.update(_providers_from_env(env_map))
    if not detected:
        detected.add("bedrock")

    ordered = [p for p in CORE_PROVIDERS if p in detected]
    if allow_decisions_api:
        ordered.append("decisions_api")
    if allow_github_skills:
        ordered.append("github_skills")
    return ordered


def _normalize_requested_providers(
    providers: Sequence[str],
    *,
    allow_decisions_api: bool,
    allow_github_skills: bool,
) -> list[str]:
    selected: set[str] = set()
    for item in providers:
        for part in item.split(","):
            cleaned = _reject_control_chars(part.strip().lower(), "provider")
            if not cleaned:
                continue
            if cleaned not in _ALL_PROFILES:
                raise ValueError(
                    f"Unknown provider {cleaned!r}: expected {', '.join(sorted(_ALL_PROFILES))}"
                )
            selected.add(cleaned)
    if allow_decisions_api:
        selected.add("decisions_api")
    if allow_github_skills:
        selected.add("github_skills")
    return [p for p in (*CORE_PROVIDERS, *OPTIONAL_PROFILES) if p in selected]


def _append_unique(bucket: list[Path], cand: Path) -> None:
    if cand not in bucket:
        bucket.append(cand)


def _resolve_tool_commands(venv_bin: Path | None, env_path: str) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    fallbacks = {
        "git": Path("/usr/bin/git"),
        "pytest": (venv_bin / "pytest") if venv_bin else Path("/usr/bin/pytest"),
        "rg": Path("/usr/bin/rg"),
        "ruff": (venv_bin / "ruff") if venv_bin else Path("/usr/bin/ruff"),
        "uv": Path("/usr/bin/uv"),
    }
    for name in ("git", "pytest", "rg", "ruff", "uv"):
        cand = venv_bin / name if venv_bin else None
        if cand is not None and cand.is_file():
            resolved[name] = cand
            continue
        hit = shutil.which(name, path=env_path)
        resolved[name] = Path(hit) if hit else fallbacks[name]
    return resolved


def resolve_runtime_paths(
    repo_root: Path,
    *,
    python_executable: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve canonical repo, `.venv`, `uv` Python, and config/cache paths."""
    env_map = os.environ if env is None else env
    home_dir = home if home is not None else Path.home()
    env_path = env_map.get("PATH", os.defpath)
    ws = Path(os.path.realpath(repo_root))
    py_bin = (
        python_executable if python_executable is not None else Path(sys.executable)
    )
    py_real = Path(os.path.realpath(py_bin))

    venv_dir: Path | None = None
    if (ws / ".venv").exists():
        venv_dir = Path(os.path.realpath(ws / ".venv"))
    elif py_bin.parent.name == "bin":
        venv_dir = Path(os.path.realpath(py_bin.parent.parent))
    venv_bin = venv_dir / "bin" if venv_dir is not None else None

    code_cfg = Path(os.path.realpath(platformdirs.user_config_dir(_CODE_APP_NAME)))
    code_cache = Path(os.path.realpath(platformdirs.user_cache_dir(_CODE_APP_NAME)))
    uv_python_dir = home_dir / ".local" / "share" / "uv" / "python"

    read_paths: list[Path] = [Path(p) for p in _SYSTEM_READ_DIRS]
    for cand in (
        ws,
        venv_dir,
        py_real.parent.parent,
        uv_python_dir.resolve() if uv_python_dir.exists() else None,
        code_cfg,
    ):
        if cand is not None:
            _append_unique(read_paths, cand)

    write_paths: list[Path] = []
    for cand in (ws, code_cfg, code_cache, Path("/tmp")):
        _append_unique(write_paths, cand)

    tools = _resolve_tool_commands(venv_bin, env_path)
    tools["python"] = py_bin

    exec_paths: list[Path] = []
    for cand in (*tools.values(), py_real):
        _append_unique(exec_paths, cand)

    cli_bin = shutil.which("strands-code", path=env_path)
    agent_cmd = [cli_bin] if cli_bin else [str(py_bin), "-m", "strands_code_cli"]
    return {
        "home": home_dir,
        "workspace": ws,
        "venv_bin": venv_bin,
        "py_bin": py_bin,
        "py_real": py_real,
        "agent_command": agent_cmd,
        "read": read_paths,
        "read_file": [Path(p) for p in _SYSTEM_READ_FILES],
        "write": write_paths,
        "list": [ws],
        "exec": exec_paths,
        "tools": tools,
    }


_STATIC_EGRESS_SPECS: dict[str, EgressSpec] = {
    "anthropic": EgressSpec(
        "anthropic",
        ("api.anthropic.com",),
        "env://ANTHROPIC_API_KEY",
        "header",
        "x-api-key",
        "",
    ),
    "openai": EgressSpec(
        "openai",
        ("api.openai.com",),
        "env://OPENAI_API_KEY",
        "header",
        "Authorization",
        "Bearer",
    ),
    "openrouter": EgressSpec(
        "openrouter",
        ("openrouter.ai/api/v1/chat/*", "openrouter.ai/api/alpha/decisions"),
        "env://OPENROUTER_API_KEY",
        "header",
        "Authorization",
        "Bearer",
    ),
    "typesafe": EgressSpec(
        "typesafe",
        ("api.typesafe.ai",),
        "env://TYPESAFE_API_KEY",
        "header",
        "Authorization",
        "Bearer",
    ),
    "decisions_api": EgressSpec(
        "decisions_api",
        ("decisionapi.net",),
        "env://JEV_API_KEY",
        "header",
        "Authorization",
        "Bearer",
    ),
}


def _bedrock_egress_spec(
    aws_region: str, aws_profile: str | None, env: Mapping[str, str]
) -> EgressSpec:
    dest = (f"bedrock-runtime.{aws_region}.amazonaws.com",)
    if aws_profile:
        return EgressSpec("bedrock", dest, secret_ref=f"aws://{aws_profile}")
    if _nonempty("AWS_BEARER_TOKEN_BEDROCK", env) and not _nonempty(
        "AWS_ACCESS_KEY_ID", env
    ):
        return EgressSpec(
            "bedrock",
            dest,
            secret_ref="env://AWS_BEARER_TOKEN_BEDROCK",
            placement="header",
            header="Authorization",
            prefix="Bearer",
        )
    return EgressSpec("bedrock", dest, secret_ref="aws://")


def _github_egress_specs(env: Mapping[str, str]) -> list[EgressSpec]:
    gh_var = (
        "GITHUB_TOKEN"
        if _nonempty("GITHUB_TOKEN", env)
        else ("GH_TOKEN" if _nonempty("GH_TOKEN", env) else None)
    )
    return [
        EgressSpec(
            "github_api",
            ("api.github.com",),
            f"env://{gh_var}" if gh_var else None,
            "header" if gh_var else None,
            "Authorization" if gh_var else None,
            "Bearer" if gh_var else None,
        ),
        EgressSpec(
            "github_downloads",
            ("codeload.github.com", "objects.githubusercontent.com"),
        ),
    ]


def _egress_specs_for_providers(
    providers: Sequence[str],
    *,
    aws_region: str,
    aws_profile: str | None,
    env: Mapping[str, str],
) -> list[EgressSpec]:
    specs: list[EgressSpec] = []
    for name in providers:
        if name in _STATIC_EGRESS_SPECS:
            specs.append(_STATIC_EGRESS_SPECS[name])
        elif name == "bedrock":
            specs.append(_bedrock_egress_spec(aws_region, aws_profile, env))
        elif name == "google":
            g_var = (
                "GEMINI_API_KEY"
                if _nonempty("GEMINI_API_KEY", env)
                and not _nonempty("GOOGLE_API_KEY", env)
                else "GOOGLE_API_KEY"
            )
            specs.append(
                EgressSpec(
                    "google",
                    ("generativelanguage.googleapis.com",),
                    f"env://{g_var}",
                    "header",
                    "x-goog-api-key",
                    "",
                )
            )
        elif name == "meta":
            m_var = (
                "META_API_KEY"
                if _nonempty("META_API_KEY", env)
                and not _nonempty("MODEL_API_KEY", env)
                else "MODEL_API_KEY"
            )
            specs.append(
                EgressSpec(
                    "meta",
                    ("api.meta.ai",),
                    f"env://{m_var}",
                    "header",
                    "Authorization",
                    "Bearer",
                )
            )
        elif name == "github_skills":
            specs.extend(_github_egress_specs(env))
    return specs


def _render_agent_env(
    *,
    runtime: dict[str, Any],
    providers: Sequence[str],
    aws_region: str,
    env: Mapping[str, str],
) -> dict[str, str]:
    venv_bin = runtime["venv_bin"]
    base_path = env.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    _reject_control_chars(base_path, "PATH")
    path_parts = [str(venv_bin)] if venv_bin is not None else []
    for segment in base_path.split(":"):
        if segment and segment not in path_parts:
            path_parts.append(segment)

    term = _reject_control_chars(
        (env.get("TERM") or "xterm-256color").strip() or "xterm-256color", "TERM"
    )
    out: dict[str, str] = {
        "HOME": str(runtime["home"]),
        "PATH": ":".join(path_parts),
        "TERM": term,
        "STRANDS_BOX": "1",
    }
    colorterm = env.get("COLORTERM")
    if isinstance(colorterm, str) and colorterm.strip():
        out["COLORTERM"] = _reject_control_chars(colorterm.strip(), "COLORTERM")
    if "bedrock" in providers:
        out["AWS_REGION"] = aws_region
    return out


def render_box_toml(
    *,
    repo_root: Path,
    box_dir: Path,
    runtime: dict[str, Any],
    egress_specs: Sequence[EgressSpec],
    agent_env: Mapping[str, str],
) -> str:
    """Render validated ``box.toml`` string (no host secrets embedded)."""
    repo_name = repo_config_id(repo_root)
    lines = [
        "# Strands Box configuration generated by strands-code (SANDBOX-01)",
        f"name = {_toml_str(f'strands-code-{repo_name}', 'name')}",
        f"box_dir = {_toml_str(str(box_dir), 'box_dir')}",
        'policy = "policy.dw"',
        "",
        "[agent]",
        f"command = {_toml_list(runtime['agent_command'], 'command')}",
        f"workspace = {_toml_str(str(runtime['workspace']), 'workspace')}",
        "",
        "[agent.env]",
    ]
    for key, val in agent_env.items():
        lines.append(f"{key} = {_toml_str(val, key)}")

    fs = runtime
    lines.extend(
        [
            "",
            "[agent.filesystem]",
            f"read = {_toml_list([str(p) for p in fs['read']], 'filesystem.read')}",
            f"read_file = {_toml_list([str(p) for p in fs['read_file']], 'filesystem.read_file')}",
            f"write = {_toml_list([str(p) for p in fs['write']], 'filesystem.write')}",
            f"list = {_toml_list([str(p) for p in fs['list']], 'filesystem.list')}",
            f"exec = {_toml_list([str(p) for p in fs['exec']], 'filesystem.exec')}",
        ]
    )
    for tool_name, tool_path in runtime["tools"].items():
        lines.extend(
            ["", f"[tool.{tool_name}]", f"command = {_toml_list([str(tool_path)])}"]
        )

    for spec in egress_specs:
        lines.extend(
            [
                "",
                f"[egress.{spec.section}]",
                f"destinations = {_toml_list(spec.destinations, f'egress.{spec.section}')}",
            ]
        )
        if spec.secret_ref is not None:
            lines.append(f"[egress.{spec.section}.secret]")
            lines.append(f"ref = {_toml_str(spec.secret_ref, 'secret.ref')}")
            if spec.placement is not None:
                lines.append(f"placement = {_toml_str(spec.placement, 'placement')}")
            if spec.header is not None:
                lines.append(f"header = {_toml_str(spec.header, 'header')}")
            if spec.prefix is not None:
                lines.append(f"prefix = {_toml_str(spec.prefix, 'prefix')}")

    return "\n".join(lines) + "\n"


def _egress_dw_rules(spec: EgressSpec) -> list[str]:
    host_paths: dict[str, list[str]] = {}
    for dest in spec.destinations:
        host, sep, path = dest.partition("/")
        host_paths.setdefault(host, []).append(f"/{path}" if sep else "")
    rules: list[str] = []
    for idx, (host, paths) in enumerate(host_paths.items()):
        rid = f"{spec.section}_{idx}"
        rules.extend(
            [
                f'@id("egress_{rid}_connect")',
                'permit (principal, action == Box::Action::"net:connect", resource)',
                f"when {{ context.input.host == {_toml_str(host)} && context.input.port == 443 }};",
                "",
            ]
        )
        clean_paths = [p for p in paths if p]
        if clean_paths:
            clauses = " || ".join(
                f"context.input.path like {_toml_str(p)}"
                if "*" in p
                else f"context.input.path == {_toml_str(p)}"
                for p in clean_paths
            )
            cond = (
                f"context.input.host == {_toml_str(host)} "
                f"&& context.input.port == 443 && ({clauses})"
            )
        else:
            cond = (
                f"context.input.host == {_toml_str(host)} && context.input.port == 443"
            )
        rules.extend(
            [
                f'@id("egress_{rid}_http")',
                'permit (principal, action == Box::Action::"http:request", resource)',
                f"when {{ {cond} }};",
                "",
            ]
        )
    return rules


def render_policy_dw(egress_specs: Sequence[EgressSpec]) -> str:
    """Render default-deny Dogwood ``policy.dw`` with `.env` forbid & MFOTL rule."""
    lines = [
        "// Dogwood policy generated by strands-code (SANDBOX-01)",
        "// Default-deny semantics: `forbid` always overrides `permit`.",
        "// Formal scoped revisit of v1.0 D-05: deterministic host-side `.dw` rules",
        "// run externally inside Strands Box; in-process Python interventions",
        "// remain deterministic TOML + Python only (never Cedar).",
        "",
        '@id("forbid_sensitive_files_read")',
        'forbid (principal, action == Box::Action::"fs:read", resource)',
        "when {",
        '    context.input.path like "*/.env"',
        '    || context.input.path like "*/.env.*"',
        '    || context.input.path like "*/.ssh/*"',
        '    || context.input.path like "*/.aws/*"',
        "};",
        "",
        '@id("allow_dev_tools")',
        'permit (principal, action == Box::Action::"shell:spawn", resource)',
        "when {",
        '    context.input.command in ["pytest", "rg", "ruff", "uv", "python"]',
        '    || (context.input.command == "git" && !(context.input.args like "push*"))',
        "};",
        "",
        '@id("push_requires_recent_tests")',
        'permit (principal, action == Box::Action::"shell:spawn", resource)',
        'when { context.input.command == "git" && context.input.args like "push*" }',
        "when temporal {",
        "    formerly within 900s (",
        '        action == Box::Action::"shell:spawn" && context.input.command == "pytest"',
        "    )",
        "};",
        "",
    ]
    for spec in egress_specs:
        lines.extend(_egress_dw_rules(spec))
    return "\n".join(lines).rstrip() + "\n"


def _is_writable_target(target_dir: Path, runtime: dict[str, Any]) -> bool:
    real_target = Path(os.path.realpath(target_dir))
    for w_path in runtime["write"]:
        real_w = Path(os.path.realpath(w_path))
        if real_target == real_w or real_w in real_target.parents:
            return True
    return False


def init_box_config(
    repo_root: Path | None = None,
    *,
    out_dir: Path | None = None,
    providers: Sequence[str] | None = None,
    aws_region: str | None = None,
    aws_profile: str | None = None,
    allow_decisions_api: bool = False,
    allow_github_skills: bool = False,
    config: ProviderConfig | None = None,
    routing_strategy: RoutingStrategy | None = None,
    python_executable: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> BoxInitResult:
    """Generate and persist ``box.toml`` + ``policy.dw`` safely for a repository."""
    env_map = os.environ if env is None else env
    root = Path(os.path.realpath(repo_root if repo_root is not None else Path.cwd()))
    region = _validate_region(
        aws_region
        or env_map.get("AWS_REGION")
        or env_map.get("AWS_DEFAULT_REGION")
        or "us-west-2"
    )
    profile = _validate_aws_profile(aws_profile) if aws_profile else None

    strategy = (
        routing_strategy if routing_strategy is not None else _safe_load_strategy(root)
    )
    if providers:
        selected = _normalize_requested_providers(
            providers,
            allow_decisions_api=allow_decisions_api,
            allow_github_skills=allow_github_skills,
        )
    else:
        selected = detect_active_providers(
            root,
            config=config,
            routing_strategy=strategy,
            env=env_map,
            allow_decisions_api=allow_decisions_api,
            allow_github_skills=allow_github_skills,
        )

    cfg_dir = out_dir if out_dir is not None else default_box_config_dir(root)
    _refuse_symlink(cfg_dir, "box config dir")
    data_dir = default_box_data_dir(root)
    runtime = resolve_runtime_paths(
        root, python_executable=python_executable, home=home, env=env_map
    )
    egress_specs = _egress_specs_for_providers(
        selected, aws_region=region, aws_profile=profile, env=env_map
    )
    agent_env = _render_agent_env(
        runtime=runtime, providers=selected, aws_region=region, env=env_map
    )

    toml_text = render_box_toml(
        repo_root=root,
        box_dir=data_dir,
        runtime=runtime,
        egress_specs=egress_specs,
        agent_env=agent_env,
    )
    if tomllib is not None:
        tomllib.loads(toml_text)
    dw_text = render_policy_dw(egress_specs)

    box_toml = _atomic_write_text(cfg_dir / "box.toml", toml_text)
    policy_dw = _atomic_write_text(cfg_dir / "policy.dw", dw_text)

    warnings: list[str] = []
    self_tamper_risk = False
    if out_dir is not None and _is_writable_target(cfg_dir, runtime):
        self_tamper_risk = True
        warnings.append(
            f"Warning: '{cfg_dir}' lies inside writable sandbox paths — "
            "an in-session write could tamper with next-launch containment. "
            "Prefer default host-only ~/.config/strands-box/ storage."
        )
    _, route_decisions_api = _providers_from_routing(strategy)
    if route_decisions_api and "decisions_api" not in selected:
        warnings.append(
            "Note: routing.yaml enables 'decisions_api' — re-run with "
            "--allow-decisions-api to include decisionapi.net egress."
        )

    return BoxInitResult(
        config_dir=cfg_dir,
        box_toml=box_toml,
        policy_dw=policy_dw,
        providers=tuple(selected),
        warnings=tuple(warnings),
        self_tamper_risk=self_tamper_risk,
    )


def discover_box_binaries(
    box_bin: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[Path | None, list[str]]:
    """Locate ``box`` and verify all 3 co-located Linux helpers exist."""
    env_map = os.environ if env is None else env
    raw = (
        str(box_bin)
        if box_bin is not None
        else env_map.get("STRANDS_BOX_BIN")
        or shutil.which("box", path=env_map.get("PATH"))
    )
    if not raw:
        return None, list(_BOX_BINARIES)
    cand = Path(raw).expanduser()
    if cand.is_dir():
        cand = cand / "box"
    if not cand.is_file():
        return None, list(_BOX_BINARIES)
    missing = [name for name in _BOX_BINARIES if not (cand.parent / name).is_file()]
    return (cand if not missing else None), missing


def _check_linux_arch(
    system_name: str, machine: str, env_map: Mapping[str, str]
) -> BoxDoctorCheck:
    low_sys = system_name.lower()
    low_arch = machine.lower()
    if low_sys != "linux":
        return BoxDoctorCheck(
            "linux_arch",
            False,
            f"Unsupported host OS '{system_name}' (Linux required for this workflow).",
            "Run Strands Box Linux binaries on Linux aarch64 or x86_64.",
        )
    if low_arch in ("x86_64", "amd64"):
        has_flag = env_map.get("EXPERIMENTAL_X86_SUPPORT") == "TRUE"
        return BoxDoctorCheck(
            "linux_arch",
            has_flag,
            "Linux x86_64 (`EXPERIMENTAL_X86_SUPPORT=TRUE` is "
            + ("set)." if has_flag else "NOT set)."),
            None
            if has_flag
            else "Set `export EXPERIMENTAL_X86_SUPPORT=TRUE` (or use `strands-code box run`).",
        )
    return BoxDoctorCheck("linux_arch", True, f"Linux {machine} (GA supported).")


def _check_apparmor(sysctl_path: Path, profile_path: Path) -> BoxDoctorCheck:
    if not sysctl_path.exists():
        return BoxDoctorCheck(
            "apparmor_userns",
            True,
            "No Ubuntu AppArmor userns sysctl restriction detected.",
        )
    val = sysctl_path.read_text(encoding="utf-8").strip()
    if val != "1":
        return BoxDoctorCheck(
            "apparmor_userns",
            True,
            f"AppArmor userns restriction disabled ({sysctl_path.name}={val}).",
        )
    if profile_path.is_file():
        return BoxDoctorCheck(
            "apparmor_userns",
            True,
            f"AppArmor userns=1 with profile present ({profile_path}).",
        )
    return BoxDoctorCheck(
        "apparmor_userns",
        False,
        f"Ubuntu AppArmor blocks CLONE_NEWUSER ({sysctl_path.name}=1) and {profile_path} is missing.",
        f"Install AppArmor profile at {profile_path}:\n{APPARMOR_PROFILE_SNIPPET}",
    )


def _check_box_config(cfg_toml: Path, cfg_dw: Path) -> BoxDoctorCheck:
    if cfg_toml.is_symlink() or cfg_dw.is_symlink() or cfg_toml.parent.is_symlink():
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Symlink refused in Box config path: {cfg_toml.parent}",
            "Remove symlinks and re-run `strands-code box init`.",
        )
    if not cfg_toml.is_file() or not cfg_dw.is_file():
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Config not found in {cfg_toml.parent}",
            "Run `strands-code box init` to generate box.toml and policy.dw.",
        )
    try:
        content = cfg_toml.read_text(encoding="utf-8")
        if tomllib is not None:
            tomllib.loads(content)
    except Exception as exc:
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Invalid {cfg_toml.name}: {exc}",
            "Re-run `strands-code box init` to regenerate box.toml.",
        )
    return BoxDoctorCheck("box_config", True, f"Valid config at {cfg_toml}")


def run_box_doctor(
    repo_root: Path | None = None,
    *,
    config_path: Path | None = None,
    box_bin: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    system_name: str | None = None,
    machine: str | None = None,
    apparmor_sysctl_path: Path | None = None,
    apparmor_profile_path: Path | None = None,
) -> BoxDoctorReport:
    """Run read-only diagnostics covering Linux arch, 3-binary layout, AppArmor & config."""
    env_map = os.environ if env is None else env
    root = Path(os.path.realpath(repo_root if repo_root is not None else Path.cwd()))
    cfg_toml = (
        config_path
        if config_path is not None
        else default_box_config_dir(root) / "box.toml"
    )
    cfg_dw = cfg_toml.parent / "policy.dw"

    checks: list[BoxDoctorCheck] = [
        _check_linux_arch(
            system_name or platform.system(),
            machine or platform.machine(),
            env_map,
        )
    ]

    found_box, missing_bins = discover_box_binaries(box_bin, env=env_map)
    checks.append(
        BoxDoctorCheck(
            "box_binaries",
            found_box is not None,
            (
                f"Found co-located 3-binary layout at {found_box.parent}"
                if found_box is not None
                else f"Missing co-located Strands Box binaries: {', '.join(missing_bins)}"
            ),
            None
            if found_box is not None
            else "Install `box`, `strands-box-contain-trampoline`, and `strands-box-sock-alias` into the same directory (or pass `--box-bin` / `STRANDS_BOX_BIN`).",
        )
    )
    checks.append(
        _check_apparmor(
            apparmor_sysctl_path or _APPARMOR_SYSCTL,
            apparmor_profile_path or _APPARMOR_PROFILE,
        )
    )
    dw_bin = shutil.which("dogwood", path=env_map.get("PATH"))
    checks.append(
        BoxDoctorCheck(
            "dogwood_cli",
            True,
            (
                f"Optional dogwood CLI installed at {dw_bin}"
                if dw_bin
                else "Optional dogwood CLI not on PATH (Dogwood engine is embedded in `box`)."
            ),
        )
    )
    checks.append(_check_box_config(cfg_toml, cfg_dw))
    py_real = Path(os.path.realpath(sys.executable))
    checks.append(
        BoxDoctorCheck(
            "uv_python_realpath",
            True,
            f"Python realpath resolved to {py_real}",
        )
    )
    return BoxDoctorReport(checks=tuple(checks), ok=all(c.ok for c in checks))


def format_doctor_report(report: BoxDoctorReport) -> str:
    """Render plain-text diagnostic summary (no secrets)."""
    lines = ["Strands Box Linux Diagnostics:"]
    for chk in report.checks:
        tag = "[OK]" if chk.ok else "[FAIL]"
        lines.append(f"  {tag} {chk.name}: {chk.detail}")
        if chk.remediation:
            lines.append(f"       fix: {chk.remediation}")
    lines.append(
        "Status: READY" if report.ok else "Status: ACTION REQUIRED (see [FAIL] items)"
    )
    return "\n".join(lines)


def launch_box_run(
    extra_args: Sequence[str] = (),
    *,
    repo_root: Path | None = None,
    config_path: Path | None = None,
    box_bin: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    machine: str | None = None,
    runner: Callable[..., Any] | None = None,
) -> tuple[int, list[str]]:
    """Invoke ``box run --config <box.toml> -- <args>`` fail-closed on symlinks/missing bins."""
    env_map = os.environ if env is None else env
    root = Path(os.path.realpath(repo_root if repo_root is not None else Path.cwd()))
    cfg_toml = (
        config_path
        if config_path is not None
        else default_box_config_dir(root) / "box.toml"
    )
    _refuse_symlink(cfg_toml, "box.toml")
    _refuse_symlink(cfg_toml.parent / "policy.dw", "policy.dw")
    if not cfg_toml.is_file():
        raise ValueError(
            f"Box config not found: {cfg_toml}. Run `strands-code box init` first."
        )
    resolved_box, missing = discover_box_binaries(box_bin, env=env_map)
    if resolved_box is None:
        raise ValueError(
            f"Strands Box binary layout incomplete (missing: {', '.join(missing)}). "
            "Run `strands-code box doctor` for setup steps."
        )

    child_env = dict(env_map)
    notices: list[str] = []
    arch = (machine or platform.machine()).lower()
    if (
        arch in ("x86_64", "amd64")
        and child_env.get("EXPERIMENTAL_X86_SUPPORT") != "TRUE"
    ):
        child_env["EXPERIMENTAL_X86_SUPPORT"] = "TRUE"
        notices.append(
            "Enabled EXPERIMENTAL_X86_SUPPORT=TRUE for Linux x86_64 Strands Box runtime."
        )

    cmd = [str(resolved_box), "run", "--config", str(cfg_toml)]
    if extra_args:
        cmd.append("--")
        cmd.extend(extra_args)
    exec_fn = runner if runner is not None else subprocess.run
    proc = exec_fn(cmd, env=child_env, check=False)
    return int(proc.returncode), notices


def _emit_lines(lines: Sequence[str], *, err: bool = False) -> None:
    """Print plain text lines without Rich markup interpretation."""
    console = Console(stderr=err)
    for line in lines:
        print_plain(console, line)


def _cmd_box_init(
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write box.toml and policy.dw here (defaults to ~/.config/strands-box/repos/<id>/).",
    ),
    provider: list[str] | None = typer.Option(
        None,
        "--provider",
        help="Enable an egress profile for this provider (repeatable).",
    ),
    region: str | None = typer.Option(
        None, "--region", help="AWS region for Bedrock egress host."
    ),
    aws_profile: str | None = typer.Option(
        None, "--aws-profile", help="AWS profile passed into Strands Box."
    ),
    allow_decisions_api: bool = typer.Option(
        False,
        "--allow-decisions-api",
        help="Allow OpenRouter /api/alpha/decisions egress.",
    ),
    allow_github_skills: bool = typer.Option(
        False,
        "--allow-github-skills",
        help="Allow api.github.com skill lookup egress.",
    ),
) -> None:
    """Generate box.toml and policy.dw for the current repository."""
    try:
        res = init_box_config(
            out_dir=out,
            providers=provider,
            aws_region=region,
            aws_profile=aws_profile,
            allow_decisions_api=allow_decisions_api,
            allow_github_skills=allow_github_skills,
        )
    except ValueError as exc:
        _emit_lines([f"Error: {exc}"], err=True)
        raise typer.Exit(code=1) from exc
    lines = [
        f"Wrote Strands Box config: {res.box_toml}",
        f"Wrote Dogwood policy:     {res.policy_dw}",
        f"Providers ({len(res.providers)}):        {', '.join(res.providers) or 'none'}",
    ]
    lines.extend(f"Warning: {warn}" for warn in res.warnings)
    _emit_lines(lines)


def _cmd_box_doctor(
    config: Path | None = typer.Option(
        None, "--config", help="Path to box.toml (defaults to repo config)."
    ),
    box_bin: str | None = typer.Option(
        None, "--box-bin", help="Explicit path to the `box` binary."
    ),
) -> None:
    """Check Linux host requirements for Strands Box (x86_64, AppArmor, binaries)."""
    report = run_box_doctor(config_path=config, box_bin=box_bin)
    _emit_lines([format_doctor_report(report)])
    if not report.ok:
        raise typer.Exit(code=1)


def _cmd_box_run(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None, "--config", help="Path to box.toml (defaults to repo config)."
    ),
    box_bin: str | None = typer.Option(
        None, "--box-bin", help="Explicit path to the `box` binary."
    ),
) -> None:
    """Launch ``strands-code`` inside Strands Box containment."""
    extra = list(ctx.args)
    if extra and extra[0] == "--":
        extra = extra[1:]
    try:
        rc, notices = launch_box_run(extra, config_path=config, box_bin=box_bin)
    except ValueError as exc:
        _emit_lines([f"Error: {exc}"], err=True)
        raise typer.Exit(code=1) from exc
    if notices:
        _emit_lines(notices, err=True)
    if rc != 0:
        raise typer.Exit(code=rc)


def build_box_app() -> typer.Typer:
    """Construct the ``strands-code box`` Typer subcommand group."""
    sub_app = typer.Typer(
        no_args_is_help=True,
        help="Manage Strands Box Linux containment configs, diagnostics, and runs.",
    )
    sub_app.command("init")(_cmd_box_init)
    sub_app.command("doctor")(_cmd_box_doctor)
    sub_app.command(
        "run",
        context_settings={
            "allow_extra_args": True,
            "ignore_unknown_options": True,
        },
    )(_cmd_box_run)
    return sub_app


box_app = build_box_app()
