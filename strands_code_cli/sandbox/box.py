"""Strands Box Linux containment config, 8-provider egress, Dogwood policy & diagnostics (SANDBOX-01)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs
import typer

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    tomllib = None  # type: ignore[assignment]

from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.platform_io import (
    _REFUSED_ROOTS,
)
from strands_code_cli.platform_io import (
    atomic_write_text as _platform_atomic_write_text,
)
from strands_code_cli.platform_io import (
    ensure_private_dir as _platform_ensure_private_dir,
)
from strands_code_cli.platform_io import (
    refuse_symlink as _platform_refuse_symlink,
)
from strands_code_cli.routing.core import RoutingStrategy, load_strategy
from strands_code_cli.ui.console import console, stderr_console
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
    "decisions_api",
)
OPTIONAL_PROFILES: tuple[str, ...] = ("github_skills",)
_ALL_PROFILES = frozenset((*CORE_PROVIDERS, *OPTIONAL_PROFILES))
_BOX_BINARIES: tuple[str, ...] = (
    "box",
    "strands-box-contain-trampoline",
    "strands-box-sock-alias",
)
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
    if any(
        ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value
    ):
        raise ValueError(f"Invalid control or surrogate character in {label}")
    return value


def _toml_str(value: str, label: str = "value") -> str:
    _reject_control_chars(value, label)
    return json.dumps(value, ensure_ascii=False)


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


def _refuse_symlink(path: Path, label: str = "path", *, max_ancestors: int = 2) -> None:
    _platform_refuse_symlink(path, label, max_ancestors=max_ancestors)


def _is_refused_root(path: Path) -> bool:
    return Path(os.path.realpath(path)) in _REFUSED_ROOTS


def _ensure_dir(path: Path, label: str) -> Path:
    return _platform_ensure_private_dir(path, label, mode=0o700, max_ancestors=2)


def _shebang_interpreter(tool_path: Path) -> Path | None:
    try:
        with tool_path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return None
    if not head.startswith(b"#!"):
        return None
    first_line = head.splitlines()[0][2:].decode("utf-8", errors="ignore").strip()
    tokens = first_line.split()
    if not tokens:
        return None
    return Path(os.path.realpath(tokens[0]))


def _atomic_write_text(path: Path, content: str) -> Path:
    return _platform_atomic_write_text(
        path,
        content,
        mode=0o600,
        dir_mode=0o700,
        refuse_ancestors=2,
        label=path.name,
    )


def repo_config_id(repo_root: Path) -> str:
    """Return unique ``<slug>-<hash8>`` identifier for ``repo_root`` (D-02)."""
    resolved = Path(os.path.realpath(repo_root))
    slug = re.sub(r"[^a-z0-9]+", "-", resolved.name.lower()).strip("-") or "repo"
    slug = slug[:32].rstrip("-") or "repo"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def _box_name(repo_root: Path) -> str:
    """Return Strands Box ``name`` capped to 32 ASCII bytes (``sc-<slug>-<hash8>``)."""
    resolved = Path(os.path.realpath(repo_root))
    slug = re.sub(r"[^a-z0-9]+", "-", resolved.name.lower()).strip("-") or "repo"
    slug = slug[:20].rstrip("-") or "repo"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"sc-{slug}-{digest}"


def default_box_config_dir(repo_root: Path) -> Path:
    """Return host-only ``~/.config/strands-box/repos/<repo-id>`` directory."""
    base = Path(platformdirs.user_config_dir(_BOX_APP_NAME))
    return base / _REPOS_DIR / repo_config_id(repo_root)


def default_box_data_dir(repo_root: Path, *, home: Path | None = None) -> Path:
    """Return host-only ``~/.local/share/strands-box/repos/<repo-id>`` box_dir."""
    base = (
        home / ".local" / "share" / _BOX_APP_NAME
        if home is not None
        else Path(platformdirs.user_data_dir(_BOX_APP_NAME))
    )
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


def _strategy_engines(strategy: RoutingStrategy | None) -> list[str]:
    if strategy is None:
        return []
    raw = (
        strategy.engine.order
        if strategy.engine.order is not None
        else [strategy.engine.primary]
    )
    return [engine for engine in raw if engine != "off"]


def _providers_from_routing(strategy: RoutingStrategy | None) -> set[str]:
    engines = _strategy_engines(strategy)
    if strategy is None or not engines:
        return set()
    found: set[str] = set()
    if "native" in engines:
        found.add("typesafe")
    if "decisions_api" in engines:
        found.add("decisions_api")
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
    return found


def _providers_from_env(env: Mapping[str, str]) -> set[str]:
    checks = (
        ("bedrock", ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_PROFILE")),
        ("google", ("GOOGLE_API_KEY", "GEMINI_API_KEY")),
        ("anthropic", ("ANTHROPIC_API_KEY",)),
        ("openai", ("OPENAI_API_KEY",)),
        ("meta", ("MODEL_API_KEY", "META_API_KEY")),
        ("openrouter", ("OPENROUTER_API_KEY", "LITELLM_API_KEY")),
        ("typesafe", ("TYPESAFE_API_KEY",)),
        ("decisions_api", ("JEV_API_KEY",)),
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
    detected.update(_providers_from_routing(strategy))
    detected.update(_providers_from_env(env_map))
    if not detected:
        detected.add("bedrock")
    if allow_decisions_api:
        detected.add("decisions_api")

    ordered = [p for p in CORE_PROVIDERS if p in detected]
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


def _coalesce_dirs(paths: Sequence[Path]) -> list[Path]:
    """Collapse duplicate or nested directory grants to their minimal enclosing set."""
    unique: list[Path] = []
    for path in paths:
        _append_unique(unique, path)
    ordered = sorted(unique, key=lambda p: len(p.parts))
    kept: list[Path] = []
    for cand in ordered:
        if not any(cand == parent or parent in cand.parents for parent in kept):
            kept.append(cand)
    return [p for p in unique if p in kept]


def _valid_shebang(real: Path, write_paths: Sequence[Path]) -> bool:
    interp = _shebang_interpreter(real)
    if interp is None:
        return True
    return interp.is_file() and not _is_under_any(interp, write_paths)


def _first_non_writable_tool(
    name: str,
    venv_bin: Path | None,
    env_path: str,
    write_paths: Sequence[Path],
) -> Path | None:
    if venv_bin is not None:
        cand = venv_bin / name
        if cand.is_file():
            real = Path(os.path.realpath(cand))
            if _is_under_any(real, write_paths):
                return None
            if (
                os.access(cand, os.X_OK)
                and real.is_file()
                and _valid_shebang(real, write_paths)
            ):
                return real

    for raw_dir in env_path.split(os.pathsep):
        if not raw_dir:
            continue
        cand = Path(raw_dir) / name
        if not cand.is_file() or not os.access(cand, os.X_OK):
            continue
        real = Path(os.path.realpath(cand))
        if (
            real.is_file()
            and not _is_under_any(real, write_paths)
            and _valid_shebang(real, write_paths)
        ):
            return real
    return None


def _resolve_tool_commands(
    venv_bin: Path | None, env_path: str, write_paths: Sequence[Path]
) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name in ("git", "pytest", "rg", "ruff", "uv"):
        hit = _first_non_writable_tool(name, venv_bin, env_path, write_paths)
        if hit is not None:
            resolved[name] = hit
    return resolved


def _resolve_cli_command(
    venv_bin: Path | None,
    py_real: Path,
    env_path: str,
    exec_paths: list[Path],
) -> list[str]:
    """Resolve strands-code launcher command and record its canonical executable path."""
    cand = venv_bin / "strands-code" if venv_bin is not None else None
    cli_bin = (
        str(cand)
        if cand is not None and cand.is_file()
        else shutil.which("strands-code", path=env_path)
    )
    if cli_bin and Path(cli_bin).is_file():
        cli_real = Path(os.path.realpath(cli_bin))
        _append_unique(exec_paths, cli_real)
        return [str(cli_real)]
    return [
        str(py_real),
        "-c",
        "from strands_code_cli.entry.main import main; main()",
    ]


def _valid_nonroot_dir(cand: Path | None) -> Path | None:
    if cand is None:
        return None
    resolved = Path(os.path.realpath(cand))
    if not resolved.is_dir() or resolved in _REFUSED_ROOTS:
        return None
    return resolved


def _resolve_venv_dir(ws: Path, py_bin: Path) -> Path | None:
    if (ws / ".venv").exists():
        return _valid_nonroot_dir(ws / ".venv")
    if py_bin.parent.name == "bin":
        return _valid_nonroot_dir(py_bin.parent.parent)
    return None


def _resolve_code_dirs(
    home_dir: Path, explicit_home: Path | None
) -> tuple[Path, Path, Path]:
    cfg_raw = (
        home_dir / ".config" / _CODE_APP_NAME
        if explicit_home is not None
        else platformdirs.user_config_dir(_CODE_APP_NAME)
    )
    cache_raw = (
        home_dir / ".cache" / _CODE_APP_NAME
        if explicit_home is not None
        else platformdirs.user_cache_dir(_CODE_APP_NAME)
    )
    raw_cfg = Path(cfg_raw)
    raw_cache = Path(cache_raw)
    _refuse_symlink(raw_cfg, "strands-code config dir", max_ancestors=1)
    _refuse_symlink(raw_cache, "strands-code cache dir", max_ancestors=1)
    _refuse_symlink(raw_cache / "tmp", "strands-code tmp dir", max_ancestors=1)
    code_cfg = Path(os.path.realpath(raw_cfg))
    code_cache = Path(os.path.realpath(raw_cache))
    return code_cfg, code_cache, code_cache / "tmp"


def _system_arch_lib_dir() -> Path | None:
    for cand in (
        Path(f"/usr/lib/{platform.machine()}-linux-gnu"),
        Path("/usr/lib64"),
    ):
        valid = _valid_nonroot_dir(cand)
        if valid is not None:
            return valid
    return None


def _python_extension_exec_dirs(
    stdlib_dir: Path | None, venv_dir: Path | None
) -> list[Path]:
    cands: list[Path] = []
    if stdlib_dir is not None:
        dyn = _valid_nonroot_dir(stdlib_dir / "lib-dynload")
        if dyn is not None:
            cands.append(dyn)
    raw_platlib = sysconfig.get_paths().get("platlib")
    if raw_platlib:
        plat = _valid_nonroot_dir(Path(raw_platlib))
        if plat is not None:
            cands.append(plat)
    if venv_dir is not None:
        for sp in sorted(venv_dir.glob("lib/python*/site-packages")):
            valid = _valid_nonroot_dir(sp)
            if valid is not None:
                cands.append(valid)
    return _coalesce_dirs(cands)


def resolve_runtime_paths(
    repo_root: Path,
    *,
    python_executable: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve canonical repo, `.venv`, `uv` Python, and config/cache paths."""
    env_map = os.environ if env is None else env
    home_dir = Path(os.path.realpath(home if home is not None else Path.home()))
    env_path = env_map.get("PATH", os.defpath)
    ws = Path(os.path.realpath(repo_root))
    py_bin = (
        python_executable if python_executable is not None else Path(sys.executable)
    )
    py_real = Path(os.path.realpath(py_bin))

    venv_dir = _resolve_venv_dir(ws, py_bin)
    venv_bin = venv_dir / "bin" if venv_dir is not None else None
    code_cfg, code_cache, tmp_dir = _resolve_code_dirs(home_dir, home)

    raw_stdlib = sysconfig.get_paths().get("stdlib")
    stdlib_dir = _valid_nonroot_dir(Path(raw_stdlib)) if raw_stdlib else None
    package_root = _valid_nonroot_dir(Path(__file__).resolve().parents[2])
    py_root = _valid_nonroot_dir(py_real.parent.parent)
    uv_python_dir = _valid_nonroot_dir(home_dir / ".local" / "share" / "uv" / "python")
    arch_lib_dir = _system_arch_lib_dir()

    read_paths: list[Path] = []
    for cand in (
        ws,
        venv_dir,
        package_root,
        stdlib_dir,
        py_root,
        uv_python_dir,
        arch_lib_dir,
        code_cfg,
        code_cache,
    ):
        if cand is not None and not _is_refused_root(cand):
            _append_unique(read_paths, cand)
    read_paths = _coalesce_dirs(read_paths)

    write_paths: list[Path] = []
    for cand in (ws, code_cfg, code_cache):
        if not _is_refused_root(cand):
            _append_unique(write_paths, cand)
    write_paths = _coalesce_dirs(write_paths)

    tools = _resolve_tool_commands(venv_bin, env_path, write_paths)
    exec_paths: list[Path] = [py_real]
    agent_cmd = _resolve_cli_command(venv_bin, py_real, env_path, exec_paths)
    exec_paths.extend(_python_extension_exec_dirs(stdlib_dir, venv_dir))
    exec_paths = _coalesce_dirs(exec_paths)
    return {
        "home": home_dir,
        "workspace": ws,
        "venv_dir": venv_dir,
        "venv_bin": venv_bin,
        "package_root": package_root,
        "stdlib_dir": stdlib_dir,
        "py_root": py_root,
        "uv_python_dir": uv_python_dir,
        "arch_lib_dir": arch_lib_dir,
        "py_bin": py_bin,
        "py_real": py_real,
        "code_cfg": code_cfg,
        "code_cache": code_cache,
        "tmp_dir": tmp_dir,
        "agent_command": agent_cmd,
        "read": read_paths,
        "write": write_paths,
        "exec": exec_paths,
        "tools": tools,
    }


_STATIC_EGRESS_SPECS: dict[str, EgressSpec] = {
    "anthropic": EgressSpec(
        "anthropic",
        ("api.anthropic.com",),
        "env://ANTHROPIC_API_KEY",
        "header",
        "Authorization",
        "Bearer",
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
            if name == "openrouter":
                specs.append(
                    EgressSpec("openrouter_models", ("openrouter.ai/api/v1/models*",))
                )
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
        "PATH": ":".join(path_parts),
        "TERM": term,
        "TMPDIR": str(runtime["tmp_dir"]),
        "STRANDS_BOX": "1",
    }
    raw_ct = env.get("COLORTERM")
    if isinstance(raw_ct, str) and raw_ct.strip():
        out["COLORTERM"] = _reject_control_chars(raw_ct.strip(), "COLORTERM")
    xdg_defaults = {
        "XDG_CONFIG_HOME": runtime["code_cfg"].parent,
        "XDG_CACHE_HOME": runtime["code_cache"].parent,
    }
    for key, default_dir in xdg_defaults.items():
        val = env.get(key)
        if not isinstance(val, str) or not val.strip():
            cand = default_dir
            cleaned = _reject_control_chars(str(cand), key)
        else:
            cleaned = _reject_control_chars(val.strip(), key)
            cand = Path(cleaned)
        if (
            cand.is_absolute()
            and cand not in _REFUSED_ROOTS
            and not _is_refused_root(cand)
        ):
            out[key] = cleaned
    if "bedrock" in providers:
        out["AWS_REGION"] = aws_region
    return out


def _is_under_any(target: Path, dirs: Sequence[Path]) -> bool:
    return any(target == d or d in target.parents for d in dirs)


def _render_tool_section(
    tool_name: str, tool_path: Path, runtime: Mapping[str, Any]
) -> list[str]:
    ws: Path = runtime["workspace"]
    code_cache: Path = runtime["code_cache"]
    tool_read: list[Path] = [ws]
    if tool_name in ("pytest", "ruff", "uv"):
        cands: list[Path | None] = [runtime.get("venv_dir")]
        if tool_name == "pytest":
            cands.extend(
                [
                    runtime.get("package_root"),
                    runtime.get("stdlib_dir"),
                    runtime.get("py_root"),
                    runtime.get("uv_python_dir"),
                    runtime.get("arch_lib_dir"),
                ]
            )
        cands.append(code_cache)
        for cand in cands:
            if cand is not None and not _is_refused_root(cand):
                _append_unique(tool_read, cand)
    tool_read = _coalesce_dirs(tool_read)

    section = [
        "",
        f"[tool.{tool_name}]",
        f"command = {_toml_list([str(tool_path)])}",
        f"[tool.{tool_name}.filesystem]",
        f"read = {_toml_list([str(p) for p in tool_read], f'tool.{tool_name}.read')}",
    ]
    interp = _shebang_interpreter(tool_path)
    if interp is not None and interp.is_file() and not _is_under_any(interp, tool_read):
        section.append(
            f"read_file = {_toml_list([str(interp)], f'tool.{tool_name}.read_file')}"
        )
    if tool_name == "git":
        section.append(f"write = {_toml_list([str(ws)], f'tool.{tool_name}.write')}")
    elif tool_name in ("pytest", "ruff", "uv"):
        tool_write = _coalesce_dirs([ws, code_cache])
        section.append(
            f"write = {_toml_list([str(p) for p in tool_write], f'tool.{tool_name}.write')}"
        )
    return section


def render_box_toml(
    *,
    repo_root: Path,
    box_dir: Path,
    runtime: dict[str, Any],
    egress_specs: Sequence[EgressSpec],
    agent_env: Mapping[str, str],
) -> str:
    """Render validated ``box.toml`` string (no host secrets embedded)."""
    lines = [
        "# Strands Box configuration generated by strands-code (SANDBOX-01)",
        f"name = {_toml_str(_box_name(repo_root), 'name')}",
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
            f"write = {_toml_list([str(p) for p in fs['write']], 'filesystem.write')}",
            f"exec = {_toml_list([str(p) for p in fs['exec']], 'filesystem.exec')}",
        ]
    )
    for tool_name, tool_path in runtime["tools"].items():
        lines.extend(_render_tool_section(tool_name, tool_path, runtime))

    for spec in egress_specs:
        if spec.secret_ref is None:
            continue
        lines.extend(
            [
                "",
                f"[egress.{spec.section}]",
                f"destinations = {_toml_list(spec.destinations, f'egress.{spec.section}')}",
                f"[egress.{spec.section}.secret]",
                f"ref = {_toml_str(spec.secret_ref, 'secret.ref')}",
            ]
        )
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
        '    || context.input.path like "*/.envrc"',
        '    || context.input.path like "*/.ssh/*"',
        '    || context.input.path like "*/.aws/*"',
        '    || context.input.path like "*/.git/config"',
        '    || context.input.path like "*/.netrc"',
        '    || context.input.path like "*/.npmrc"',
        '    || context.input.path like "*/.pypirc"',
        "};",
        "",
        '@id("allow_fs_read")',
        'permit (principal, action == Box::Action::"fs:read", resource);',
        "",
        '@id("allow_fs_write")',
        'permit (principal, action == Box::Action::"fs:write", resource);',
        "",
        '@id("allow_fs_delete")',
        'permit (principal, action == Box::Action::"fs:delete", resource);',
        "",
        '@id("allow_fs_move")',
        'permit (principal, action == Box::Action::"fs:move", resource);',
        "",
        '@id("allow_shell_exec")',
        'permit (principal, action == Box::Action::"shell:exec", resource);',
        "",
        '@id("forbid_box_config_write")',
        'forbid (principal, action == Box::Action::"fs:write", resource)',
        "when {",
        '    context.input.path like "*/.config/strands-box/*"',
        '    || context.input.path like "*/.local/share/strands-box/*"',
        "};",
        "",
        '@id("forbid_box_config_delete")',
        'forbid (principal, action == Box::Action::"fs:delete", resource)',
        "when {",
        '    context.input.path like "*/.config/strands-box/*"',
        '    || context.input.path like "*/.local/share/strands-box/*"',
        "};",
        "",
        '@id("forbid_box_config_move")',
        'forbid (principal, action == Box::Action::"fs:move", resource)',
        "when {",
        '    context.input.path like "*/.config/strands-box/*"',
        '    || context.input.path like "*/.local/share/strands-box/*"',
        "};",
        "",
        '@id("allow_dev_tools")',
        'permit (principal, action == Box::Action::"shell:spawn", resource)',
        "when {",
        '    ["pytest", "rg", "ruff", "uv", "git"].contains(context.input.program)',
        "};",
        "",
        '@id("forbid_uv_git_push")',
        'forbid (principal, action == Box::Action::"shell:spawn", resource)',
        "when {",
        '    context.input.program == "uv"',
        "    && (",
        '        context.input.command like "*git *push*"',
        '        || context.input.command like "*git -c *"',
        "    )",
        "};",
        "",
        '@id("push_requires_recent_tests")',
        'forbid (principal, action == Box::Action::"shell:spawn", resource)',
        "when {",
        '    context.input.program == "git"',
        "    && (",
        '        (context.input has arg1 && context.input.arg1 == "push")',
        '        || (context.input has arg2 && context.input.arg2 == "push")',
        '        || (context.input has arg1 && context.input.arg1 == "-c" && context.input.command like "*push*")',
        "        || (",
        "            context.input has arg1",
        '            && !(["commit", "log", "grep", "show", "diff"].contains(context.input.arg1))',
        '            && (context.input.command like "* push" || context.input.command like "* push *")',
        "        )",
        "    )",
        "}",
        "unless temporal {",
        "    formerly within 900s (",
        '        Box::Action::"shell:spawn"::response {',
        '            input.program: "pytest",',
        "            output.status: 0",
        "        }",
        '        && !Box::Action::"shell:spawn"::response {',
        '            input.program: "pytest",',
        '            input.arg1: "--version"',
        "        }",
        '        && !Box::Action::"shell:spawn"::response {',
        '            input.program: "pytest",',
        '            input.arg1: "--help"',
        "        }",
        "    )",
        "}",
        "unless temporal {",
        "    formerly within 900s (",
        '        Box::Action::"shell:spawn"::response {',
        '            input.program: "uv",',
        '            input.arg1: "run",',
        '            input.arg2: "pytest",',
        "            output.status: 0",
        "        }",
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


def _configured_model_refs(
    config: ProviderConfig, strategy: RoutingStrategy | None
) -> list[str]:
    refs = [config.model] if config.model else []
    if strategy is not None:
        if strategy.engine.llm_model:
            refs.append(strategy.engine.llm_model)
        refs.extend(c.id for c in strategy.candidates if c.id)
    return refs


def _collect_box_warnings(
    cfg_dir: Path,
    out_dir: Path | None,
    runtime: dict[str, Any],
    config: ProviderConfig,
    strategy: RoutingStrategy | None,
    env_map: Mapping[str, str],
) -> tuple[list[str], bool]:
    warnings: list[str] = []
    self_tamper_risk = False
    if out_dir is not None and _is_writable_target(cfg_dir, runtime):
        self_tamper_risk = True
        warnings.append(
            f"Warning: '{cfg_dir}' lies inside writable sandbox paths — "
            "an in-session write could tamper with next-launch containment. "
            "Prefer default host-only ~/.config/strands-box/ storage."
        )
    if env_map.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in _TRUTHY:
        warnings.append(
            "Note: GOOGLE_GENAI_USE_VERTEXAI is set — Vertex AI ADC/endpoints are not "
            "pre-configured in Strands Box; use GOOGLE_API_KEY / GEMINI_API_KEY or add "
            "custom Vertex egress."
        )
    base_env_vars = (
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "META_BASE_URL",
        "LITELLM_BASE_URL",
    )
    if config.base_url or any(_nonempty(k, env_map) for k in base_env_vars):
        warnings.append(
            "Note: custom base_url detected — generated box.toml permits only standard "
            "vendor endpoints; add your proxy host to box.toml and policy.dw if needed."
        )
    refs = _configured_model_refs(config, strategy)
    if any(
        r.lower().startswith(("ollama/", "litellm/ollama")) for r in refs
    ) or "local" in _strategy_engines(strategy):
        warnings.append(
            "Note: local Ollama model/engine detected — loopback 127.0.0.1:11434 is "
            "unreachable inside Strands Box's isolated network namespace."
        )
    if any(r.lower().startswith("bedrock-mantle/") for r in refs):
        warnings.append(
            "Note: bedrock-mantle model detected — default bedrock profile permits "
            "bedrock-runtime.<region>.amazonaws.com only, not bedrock-mantle endpoints."
        )
    return warnings, self_tamper_risk


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
    raw_profile = aws_profile if aws_profile else env_map.get("AWS_PROFILE")
    profile = (
        _validate_aws_profile(raw_profile)
        if raw_profile and raw_profile.strip()
        else None
    )

    cfg = config if config is not None else _safe_load_provider_config()
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
            config=cfg,
            routing_strategy=strategy,
            env=env_map,
            allow_decisions_api=allow_decisions_api,
            allow_github_skills=allow_github_skills,
        )

    cfg_dir = out_dir if out_dir is not None else default_box_config_dir(root)
    _refuse_symlink(cfg_dir, "box config dir")
    data_dir = default_box_data_dir(root, home=home)
    _ensure_dir(data_dir.parent, "box data parent")
    runtime = resolve_runtime_paths(
        root, python_executable=python_executable, home=home, env=env_map
    )
    _ensure_dir(runtime["code_cfg"], "strands-code config dir")
    _ensure_dir(runtime["code_cache"], "strands-code cache dir")
    _ensure_dir(runtime["tmp_dir"], "strands-code tmp dir")
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

    warnings, self_tamper_risk = _collect_box_warnings(
        cfg_dir, out_dir, runtime, cfg, strategy, env_map
    )

    return BoxInitResult(
        config_dir=cfg_dir,
        box_toml=box_toml,
        policy_dw=policy_dw,
        providers=tuple(selected),
        warnings=tuple(warnings),
        self_tamper_risk=self_tamper_risk,
    )


def _is_exec_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def discover_box_binaries(
    box_bin: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[Path | None, list[str]]:
    """Locate ``box`` and verify all 3 co-located Linux helpers exist and execute."""
    env_map = os.environ if env is None else env
    raw = (
        str(box_bin)
        if box_bin is not None
        else env_map.get("STRANDS_BOX_BIN")
        or shutil.which("box", path=env_map.get("PATH"))
    )
    if not raw or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None, list(_BOX_BINARIES)
    cand = Path(raw).expanduser()
    if cand.is_dir():
        cand = cand / "box"
    if not _is_exec_file(cand):
        return None, list(_BOX_BINARIES)
    missing = [name for name in _BOX_BINARIES if not _is_exec_file(cand.parent / name)]
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


def _apparmor_has_userns(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if re.search(r"(?<![A-Za-z0-9_])userns(?![A-Za-z0-9_])", stripped):
            return True
    return False


def _check_apparmor(sysctl_path: Path, profile_path: Path) -> BoxDoctorCheck:
    if not sysctl_path.exists():
        return BoxDoctorCheck(
            "apparmor_userns",
            True,
            "No Ubuntu AppArmor userns sysctl restriction detected.",
        )
    try:
        val = sysctl_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return BoxDoctorCheck(
            "apparmor_userns",
            False,
            f"Cannot read {sysctl_path}: {exc}",
            f"Inspect {sysctl_path} permissions or install {profile_path}.",
        )
    if val != "1":
        return BoxDoctorCheck(
            "apparmor_userns",
            True,
            f"AppArmor userns restriction disabled ({sysctl_path.name}={val}).",
        )
    if profile_path.is_file():
        try:
            profile_text = profile_path.read_text(encoding="utf-8")
        except OSError as exc:
            return BoxDoctorCheck(
                "apparmor_userns",
                False,
                f"Cannot read AppArmor profile {profile_path}: {exc}",
                f"Ensure {profile_path} is readable and allows `userns,`.",
            )
        if not _apparmor_has_userns(profile_text):
            return BoxDoctorCheck(
                "apparmor_userns",
                False,
                f"AppArmor profile {profile_path} is missing `userns,` rule.",
                f"Update {profile_path} with:\n{APPARMOR_PROFILE_SNIPPET}",
            )
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


def _resolve_custom_policy_path(
    cfg_toml: Path, parsed_cfg: dict[str, Any]
) -> Path | None:
    pol_val = parsed_cfg.get("policy")
    if isinstance(pol_val, str) and pol_val.strip():
        cleaned_pol = _reject_control_chars(pol_val.strip(), "policy")
        return (
            Path(cleaned_pol)
            if Path(cleaned_pol).is_absolute()
            else cfg_toml.parent / cleaned_pol
        )
    return None


def _check_box_config(cfg_toml: Path, cfg_dw: Path) -> BoxDoctorCheck:
    try:
        _refuse_symlink(cfg_toml, "box.toml", max_ancestors=3)
        _refuse_symlink(cfg_dw, "policy.dw", max_ancestors=3)
    except ValueError as exc:
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Symlink refused in Box config path: {exc}",
            "Remove symlinks and re-run `strands-code box init`.",
        )
    if not cfg_toml.is_file():
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Config not found in {cfg_toml.parent}",
            "Run `strands-code box init` to generate box.toml and policy.dw.",
        )
    try:
        content = cfg_toml.read_text(encoding="utf-8")
        parsed_cfg = tomllib.loads(content) if tomllib is not None else {}
        custom_pol = _resolve_custom_policy_path(cfg_toml, parsed_cfg)
        active_pol = custom_pol if custom_pol is not None else cfg_dw
        _refuse_symlink(active_pol, "policy", max_ancestors=3)
    except Exception as exc:
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Invalid {cfg_toml.name}: {exc}",
            "Re-run `strands-code box init` to regenerate box.toml.",
        )
    if not active_pol.is_file():
        return BoxDoctorCheck(
            "box_config",
            False,
            f"Policy not found: {active_pol}",
            "Run `strands-code box init` to generate box.toml and policy.dw.",
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


def _validate_launch_box_dir(raw_box_dir: str) -> None:
    cleaned = _reject_control_chars(raw_box_dir, "box_dir")
    box_dir = Path(cleaned)
    if not box_dir.is_absolute():
        raise ValueError("Invalid box_dir: must be an absolute path")
    _refuse_symlink(box_dir, "box_dir", max_ancestors=2)
    parent = box_dir.parent
    real_parent = Path(os.path.realpath(parent))
    home_real = Path(os.path.realpath(Path.home()))
    if (
        parent in _REFUSED_ROOTS
        or real_parent in _REFUSED_ROOTS
        or real_parent == home_real
    ):
        raise ValueError(f"Refusing unsafe box_dir parent: {parent}")
    _ensure_dir(parent, "box data parent")


def _validate_launch_config(cfg_toml: Path) -> None:
    _refuse_symlink(cfg_toml, "box.toml", max_ancestors=3)
    _refuse_symlink(cfg_toml.parent / "policy.dw", "policy.dw", max_ancestors=3)
    if not cfg_toml.is_file():
        raise ValueError(
            f"Box config not found: {cfg_toml}. Run `strands-code box init` first."
        )
    if tomllib is None:
        return
    try:
        parsed_cfg = tomllib.loads(cfg_toml.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid {cfg_toml.name}: {exc}") from exc
    pol_path = _resolve_custom_policy_path(cfg_toml, parsed_cfg)
    if pol_path is not None:
        _refuse_symlink(pol_path, "policy", max_ancestors=3)
    box_dir_val = parsed_cfg.get("box_dir")
    if isinstance(box_dir_val, str) and box_dir_val.strip():
        _validate_launch_box_dir(box_dir_val)


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
    _validate_launch_config(cfg_toml)
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
    target = stderr_console if err else console
    for line in lines:
        print_plain(target, line)


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
        help="Force-enable decisionapi.net egress (auto-detected from routing.yaml or JEV_API_KEY).",
    ),
    allow_github_skills: bool = typer.Option(
        False,
        "--allow-github-skills",
        help="Allow GitHub skills marketplace egress (api.github.com + codeload/objects).",
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
    lines.extend(
        warn if warn.startswith(("Warning:", "Note:")) else f"Warning: {warn}"
        for warn in res.warnings
    )
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
