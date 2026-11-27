"""Pure-HTTPS marketplace catalog, safe unpack, and lockfile verification (SKILL-03)."""

from __future__ import annotations

import bz2
import errno
import hashlib
import io
import json
import lzma
import os
import re
import shutil
import stat
import tarfile
import tempfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import platformdirs
import yaml
from strands.vended_plugins.skills import Skill

from strands_code_cli.platform_io import (
    atomic_write_text as _platform_atomic_write_text,
)
from strands_code_cli.platform_io import (
    refuse_symlink as _platform_refuse_symlink,
)
from strands_code_cli.ui.console import sanitize_display

_APP_DIR_NAME = "strands-code"
MARKETPLACES_FILENAME = "marketplaces.yaml"
MARKETPLACES_SKILLS_REL = Path(".agent") / "skills-marketplaces"
SKILLS_LOCK_REL = Path(".agent") / "skills-lock.json"
LOCKFILE_VERSION = 1

MAX_TARBALL_BYTES = 25 * 1024 * 1024
MAX_TARBALL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_TARBALL_MEMBERS = 4096
MAX_CATALOG_SCAN_BYTES = 20 * 1024 * 1024
MAX_CATALOG_SCAN_FILES = 1024
MAX_API_JSON_BYTES = 2 * 1024 * 1024
MAX_SKILL_FILES = 256
MAX_SKILL_BYTES = 5 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 20.0

_ALLOWED_TARBALL_HOSTS = frozenset(
    {"codeload.github.com", "objects.githubusercontent.com"}
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALIAS_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SKILL_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_GITHUB_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_RESERVED_NAMESPACES = frozenset({"local", "all"})
_MANIFEST_CANDIDATES = (
    PurePosixPath(".agent-plugin/marketplace.json"),
    PurePosixPath(".claude-plugin/marketplace.json"),
)


@dataclass
class MarketplaceEntry:
    """Registered marketplace catalog source persisted in marketplaces.yaml."""

    name: str
    source: str
    kind: str  # "github" | "local"
    ref: str | None = None
    added_at: str = ""


@dataclass
class CatalogSkill:
    """One skill advertised by a marketplace catalog or repository."""

    name: str
    description: str
    marketplace: str
    source: str
    repo_url: str
    subdir: str
    ref: str | None = None
    commit_sha: str | None = None


@dataclass
class LockEntry:
    """Pinned marketplace skill record persisted in ./.agent/skills-lock.json."""

    namespace: str
    name: str
    source: str
    repo_url: str
    subdir: str
    ref: str
    commit_sha: str
    computed_hash: str
    has_scripts: bool = False
    script_files: list[str] = field(default_factory=list)
    installed_at: str = ""

    @property
    def namespaced(self) -> str:
        return f"{self.namespace}:{self.name}"


@dataclass
class VerifiedMarketplaceSkill:
    """Hash-verified installed skill ready to expose in SkillIndex & AgentSkills."""

    namespace: str
    name: str
    path: Path
    entry: LockEntry


@dataclass
class InstallOutcome:
    """Result returned by install_skill()."""

    installed: list[LockEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SkillUpdateRecord:
    """Per-skill update diff including commit transition and bundled scripts."""

    entry: LockEntry
    old_sha: str
    new_sha: str
    added_scripts: list[str] = field(default_factory=list)
    changed_scripts: list[str] = field(default_factory=list)


@dataclass
class UpdateOutcome:
    """Result returned by update_installed_skills()."""

    updated: list[SkillUpdateRecord] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SyncOutcome:
    """Result returned by sync_installed_skills()."""

    restored: list[LockEntry] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RemoveOutcome:
    """Result returned by remove_installed_skill()."""

    removed: bool
    message: str


def default_marketplaces_path() -> Path:
    """Return ~/.config/strands-code/marketplaces.yaml path."""
    return Path(platformdirs.user_config_dir(_APP_DIR_NAME)) / MARKETPLACES_FILENAME


def default_cache_dir() -> Path:
    """Return ~/.cache/strands-code/marketplaces directory path."""
    return Path(platformdirs.user_cache_dir(_APP_DIR_NAME)) / "marketplaces"


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _has_control_chars(text: str) -> bool:
    return any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in text)


def read_github_token() -> str | None:
    """Read optional GitHub API token from environment without persistence or logging."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        raw = os.environ.get(var)
        if not isinstance(raw, str):
            continue
        stripped = raw.strip()
        if not stripped or _has_control_chars(stripped):
            continue
        return stripped
    return None


def valid_namespace(name: str) -> bool:
    """Return True when name is a legal non-reserved marketplace namespace slug."""
    if not isinstance(name, str) or name in _RESERVED_NAMESPACES:
        return False
    return bool(_ALIAS_RE.match(name))


def validate_namespace(name: str) -> str:
    """Validate and return a marketplace alias/namespace or raise ValueError."""
    if not valid_namespace(name):
        raise ValueError(
            f"Invalid marketplace namespace {name!r}: expected 1-64 lowercase "
            "alphanumeric/hyphen chars, not 'local' or 'all'."
        )
    return name


def valid_skill_name(name: str) -> bool:
    """Return True when name satisfies the strict AgentSkills slug grammar."""
    return (
        isinstance(name, str) and "--" not in name and bool(_SKILL_SLUG_RE.match(name))
    )


def validate_skill_name(name: str) -> str:
    """Validate and return a strict skill directory/slug name or raise ValueError."""
    if not valid_skill_name(name):
        raise ValueError(
            f"Invalid skill name {name!r}: expected 1-64 lowercase alphanumeric/single-hyphen chars."
        )
    return name


def github_repo_slug(owner: str, repo: str) -> str:
    """Derive a flat, single-segment filesystem namespace ``owner--repo`` (D-02)."""
    o = re.sub(r"[^a-z0-9]+", "-", owner.lower()).strip("-") or "org"
    r = re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-") or "repo"
    combined = f"{o}--{r}"
    if len(combined) > 64:
        combined = combined[:64].rstrip("-")
    if not valid_namespace(combined):
        raise ValueError(f"Cannot derive safe namespace slug from {owner!r}/{repo!r}")
    return combined


def _validate_github_segment(segment: str, kind: str) -> str:
    if (
        not segment
        or segment in (".", "..")
        or ".." in segment
        or not _GITHUB_SEGMENT_RE.match(segment)
    ):
        raise ValueError(f"Invalid GitHub {kind}: {segment!r}")
    return segment


def _validate_git_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    if (
        not ref
        or _has_control_chars(ref)
        or any(ch.isspace() for ch in ref)
        or ".." in ref
        or any(ch in ref for ch in ("\\", "?", "#", "@{"))
    ):
        raise ValueError(f"Invalid git ref: {ref!r}")
    return ref


def _split_repo_and_ref(raw_repo: str) -> tuple[str, str | None]:
    if "@" in raw_repo:
        repo_part, _, ref_part = raw_repo.partition("@")
        ref = _validate_git_ref(ref_part)
    else:
        repo_part, ref = raw_repo, None
    if repo_part.endswith(".git"):
        repo_part = repo_part[:-4]
    return _validate_github_segment(repo_part, "repo"), ref


def _extract_https_github_rel(spec: str) -> str:
    parsed = urlsplit(spec)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "github.com"
    ):
        raise ValueError(f"Only https://github.com URLs are allowed: {spec!r}")
    if (
        parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Unsupported URL fields in GitHub spec: {spec!r}")
    return parsed.path.strip("/")


def parse_github_spec(spec: str) -> tuple[str, str, str | None]:
    """Parse ``owner/repo[@ref]`` or ``https://github.com/owner/repo[.git][@ref]``."""
    if not isinstance(spec, str) or not spec or spec != spec.strip():
        raise ValueError(f"Invalid GitHub spec: {spec!r}")
    if _has_control_chars(spec) or any(ch.isspace() for ch in spec) or "\\" in spec:
        raise ValueError(f"Invalid GitHub spec: {spec!r}")

    rel = _extract_https_github_rel(spec) if "://" in spec else spec.strip("/")
    parts = rel.split("/")
    if len(parts) != 2:
        raise ValueError(f"Expected owner/repo[@ref], got: {spec!r}")
    owner = _validate_github_segment(parts[0], "owner")
    repo, ref = _split_repo_and_ref(parts[1])
    return owner, repo, ref


def canonical_github_repo_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}"


def _refuse_symlink(path: Path, label: str = "path") -> None:
    _platform_refuse_symlink(path, label, max_ancestors=1)


def _refuse_symlink_chain(root: Path, *segments: str) -> None:
    curr = root
    if curr.is_symlink():
        raise ValueError(f"Refusing symlink directory: {curr}")
    for seg in segments:
        curr = curr / seg
        if curr.is_symlink():
            raise ValueError(f"Refusing symlink path: {curr}")


def _resolve_confined_no_symlinks(root: Path, rel: PurePosixPath | None = None) -> Path:
    """Resolve ``root / rel`` refusing symlinks at every segment & confining to root."""
    if root.is_symlink():
        raise ValueError(f"Refusing symlink directory: {root}")
    curr = root
    if rel is not None and rel != PurePosixPath("."):
        for seg in rel.parts:
            curr = curr / seg
            if curr.is_symlink():
                raise ValueError(f"Refusing symlink path: {curr}")
    real_root = Path(os.path.realpath(root))
    real_curr = Path(os.path.realpath(curr))
    if real_curr != real_root and real_root not in real_curr.parents:
        raise ValueError(f"Path escapes local root {root}: {curr}")
    return curr


def _atomic_write_text(
    path: Path,
    content: str,
    *,
    dir_mode: int | None = None,
    file_mode: int | None = None,
) -> Path:
    return _platform_atomic_write_text(
        path,
        content,
        mode=file_mode,
        dir_mode=dir_mode,
        refuse_ancestors=1,
        label=str(path),
    )


def load_marketplaces(path: Path | None = None) -> dict[str, MarketplaceEntry]:
    """Load registered marketplaces from YAML; ships empty by default (D-02)."""
    target = path if path is not None else default_marketplaces_path()
    _refuse_symlink(target, "marketplaces registry")
    if not target.exists():
        return {}
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed marketplaces registry: {target}") from exc
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Malformed marketplaces registry: {target}")
    items = raw.get("marketplaces", {})
    if not isinstance(items, dict):
        raise ValueError(f"Malformed 'marketplaces' mapping: {target}")
    out: dict[str, MarketplaceEntry] = {}
    for alias, entry in items.items():
        if not isinstance(entry, dict) or not valid_namespace(str(alias)):
            continue
        kind = str(entry.get("kind", "")).strip()
        source = str(entry.get("source", "")).strip()
        if kind not in ("github", "local") or not source:
            continue
        ref_val = entry.get("ref")
        out[str(alias)] = MarketplaceEntry(
            name=str(alias),
            source=source,
            kind=kind,
            ref=str(ref_val) if ref_val is not None else None,
            added_at=str(entry.get("added_at", "")),
        )
    return out


def save_marketplaces(
    entries: dict[str, MarketplaceEntry], path: Path | None = None
) -> Path:
    """Persist registered marketplaces atomically (0o700 dir / 0o600 file)."""
    target = path if path is not None else default_marketplaces_path()
    serialized = {
        "version": 1,
        "marketplaces": {
            key: {
                "source": val.source,
                "kind": val.kind,
                "ref": val.ref,
                "added_at": val.added_at,
            }
            for key, val in sorted(entries.items())
        },
    }
    return _atomic_write_text(
        target,
        yaml.safe_dump(serialized, sort_keys=True),
        dir_mode=0o700,
        file_mode=0o600,
    )


def _cache_file(name: str, cache_dir: Path | None = None) -> Path:
    validate_namespace(name)
    root = cache_dir if cache_dir is not None else default_cache_dir()
    return root / f"{name}.json"


def load_cached_catalog(name: str, cache_dir: Path | None = None) -> list[CatalogSkill]:
    """Load cached catalog JSON for one marketplace namespace cleanly."""
    path = _cache_file(name, cache_dir)
    _refuse_symlink(path, "marketplace cache")
    if not path.exists():
        return []
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except (OSError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []
    skills_raw = raw.get("skills", [])
    if not isinstance(skills_raw, list):
        return []
    out: list[CatalogSkill] = []
    for item in skills_raw:
        if not isinstance(item, dict):
            continue
        sname = item.get("name")
        mname = str(item.get("marketplace", name))
        if (
            not isinstance(sname, str)
            or not valid_skill_name(sname)
            or not valid_namespace(mname)
        ):
            continue
        out.append(
            CatalogSkill(
                name=sname,
                description=sanitize_display(item.get("description", "")),
                marketplace=mname,
                source=str(item.get("source", "")),
                repo_url=str(item.get("repo_url", "")),
                subdir=str(item.get("subdir", ".")),
                ref=str(item["ref"]) if item.get("ref") else None,
                commit_sha=str(item["commit_sha"]) if item.get("commit_sha") else None,
            )
        )
    return out


def save_cached_catalog(
    name: str, skills: list[CatalogSkill], cache_dir: Path | None = None
) -> Path:
    """Persist discovered catalog skills to ~/.cache/strands-code/marketplaces/<name>.json."""
    path = _cache_file(name, cache_dir)
    payload = {
        "marketplace": name,
        "updated_at": _utc_now_iso(),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "marketplace": s.marketplace,
                "source": s.source,
                "repo_url": s.repo_url,
                "subdir": s.subdir,
                "ref": s.ref,
                "commit_sha": s.commit_sha,
            }
            for s in skills
        ],
    }
    return _atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        dir_mode=0o700,
        file_mode=0o600,
    )


def make_marketplace_client(timeout: float = HTTP_TIMEOUT_SECONDS) -> httpx.Client:
    """Create the single HTTPS httpx seam with redirects explicitly disabled."""
    return httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False)


def _api_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "strands-code",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _reject_json_constant(token: str) -> Any:
    raise ValueError(f"Non-standard JSON constant rejected: {token}")


def _github_get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    try:
        with client.stream(
            "GET", url, headers=_api_headers(read_github_token())
        ) as resp:
            if 300 <= resp.status_code < 400:
                raise ValueError(f"Unexpected GitHub API redirect ({resp.status_code})")
            if resp.status_code >= 400:
                raise ValueError(
                    f"GitHub API request failed ({resp.status_code}) for {url}"
                )
            raw_bytes = _read_bounded_response(resp, MAX_API_JSON_BYTES)
    except httpx.HTTPError:
        raise ValueError("GitHub network error (offline or unreachable)") from None
    data = json.loads(raw_bytes.decode("utf-8"), parse_constant=_reject_json_constant)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON payload from GitHub API: {url}")
    return data


def resolve_github_commit(
    owner: str,
    repo: str,
    ref: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Resolve ref (or repo default branch) to immutable 40-char lowercase hex SHA."""
    _validate_github_segment(owner, "owner")
    _validate_github_segment(repo, "repo")
    own_client = client is None
    active = client if client is not None else make_marketplace_client()
    try:
        resolved_ref = _validate_git_ref(ref)
        if resolved_ref is None:
            repo_meta = _github_get_json(
                active, f"https://api.github.com/repos/{owner}/{repo}"
            )
            default_branch = repo_meta.get("default_branch")
            if not isinstance(default_branch, str) or not default_branch:
                raise ValueError(f"Missing default_branch for {owner}/{repo}")
            resolved_ref = _validate_git_ref(default_branch)
        assert resolved_ref is not None
        encoded_ref = quote(resolved_ref, safe="/._-")
        commit_meta = _github_get_json(
            active,
            f"https://api.github.com/repos/{owner}/{repo}/commits/{encoded_ref}",
        )
        sha = commit_meta.get("sha")
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            raise ValueError(
                f"Invalid commit SHA resolved for {owner}/{repo}@{resolved_ref}"
            )
        return sha, resolved_ref
    finally:
        if own_client:
            active.close()


def _validate_tarball_redirect_url(location: str) -> str:
    if (
        not location
        or _has_control_chars(location)
        or any(ch.isspace() for ch in location)
    ):
        raise ValueError("Invalid redirect Location header")
    parsed = urlsplit(location)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or parsed.port is not None
        or host not in _ALLOWED_TARBALL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"Disallowed tarball redirect host: {host or location!r}")
    return location


def _read_bounded_response(resp: httpx.Response, max_bytes: int) -> bytes:
    if resp.status_code >= 400:
        raise ValueError(f"Tarball download failed ({resp.status_code})")
    raw_len = resp.headers.get("content-length")
    if raw_len and raw_len.isdigit() and int(raw_len) > max_bytes:
        raise ValueError(f"Tarball exceeds size limit ({max_bytes} bytes)")
    buf = bytearray()
    for chunk in resp.iter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise ValueError(f"Tarball exceeds size limit ({max_bytes} bytes)")
    return bytes(buf)


def download_github_tarball(
    owner: str,
    repo: str,
    commit_sha: str,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_TARBALL_BYTES,
) -> bytes:
    """Download pinned tarball with single-hop redirect guard & no auth forwarding."""
    _validate_github_segment(owner, "owner")
    _validate_github_segment(repo, "repo")
    if not _SHA_RE.match(commit_sha):
        raise ValueError(f"Invalid commit SHA: {commit_sha!r}")
    url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{commit_sha}"
    own_client = client is None
    active = client if client is not None else make_marketplace_client()
    try:
        with active.stream(
            "GET", url, headers=_api_headers(read_github_token())
        ) as resp:
            if 300 <= resp.status_code < 400:
                redirect_url = _validate_tarball_redirect_url(
                    resp.headers.get("location", "")
                )
            else:
                return _read_bounded_response(resp, max_bytes)
        with active.stream(
            "GET", redirect_url, headers={"User-Agent": "strands-code"}
        ) as r2:
            if 300 <= r2.status_code < 400:
                raise ValueError("Nested redirects are rejected on tarball download")
            return _read_bounded_response(r2, max_bytes)
    except httpx.HTTPError:
        raise ValueError("GitHub network error (offline or unreachable)") from None
    finally:
        if own_client:
            active.close()


def _normalize_rel_posix(raw_name: str) -> PurePosixPath:
    if not raw_name or _has_control_chars(raw_name) or "\\" in raw_name:
        raise ValueError(f"Illegal archive member path: {raw_name!r}")
    cleaned = raw_name
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("/"):
        raise ValueError(f"Absolute archive member path rejected: {raw_name!r}")
    pure = PurePosixPath(cleaned)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Path traversal member rejected: {raw_name!r}")
    return pure


def _validate_tar_member(member: tarfile.TarInfo) -> PurePosixPath | None:
    if (
        member.type in (tarfile.XGLTYPE, tarfile.XHDTYPE)
        and member.name == "pax_global_header"
    ):
        return None
    pure = _normalize_rel_posix(member.name)
    if pure.name.lower() == ".gitmodules":
        raise ValueError("Git submodules (.gitmodules) are rejected")
    if member.issym() or member.islnk() or member.linkname:
        raise ValueError(f"Symlink/hardlink rejected in archive: {member.name!r}")
    if member.isfifo() or member.ischr() or member.isblk() or member.isdev():
        raise ValueError(f"Special device/FIFO rejected in archive: {member.name!r}")
    if not (member.isreg() or member.isdir()):
        raise ValueError(f"Unsupported archive entry type for {member.name!r}")
    return pure


def _matches_subdir(rel: PurePosixPath, subdir: PurePosixPath) -> PurePosixPath | None:
    if subdir == PurePosixPath("."):
        return rel
    if rel == subdir:
        return PurePosixPath(".")
    try:
        return rel.relative_to(subdir)
    except ValueError:
        return None


def _pref_matches_archive(
    parsed: list[tuple[tarfile.TarInfo, PurePosixPath]], top: str, preferred_subdir: str
) -> str | None:
    pref = _normalize_rel_posix(preferred_subdir)
    matches_unstripped = any(_matches_subdir(p, pref) is not None for _m, p in parsed)
    matches_stripped = any(
        len(p.parts) > 1
        and p.parts[0] == top
        and _matches_subdir(PurePosixPath(*p.parts[1:]), pref) is not None
        for _m, p in parsed
    )
    if matches_unstripped and not matches_stripped:
        return None
    return top


def _select_strip_prefix(
    parsed: list[tuple[tarfile.TarInfo, PurePosixPath]], preferred_subdir: str | None
) -> str | None:
    top_segments = {p.parts[0] for _m, p in parsed if p.parts and str(p) != "."}
    if len(top_segments) != 1:
        return None
    top = next(iter(top_segments))
    if top == "skills" or not any(len(p.parts) > 1 for _m, p in parsed):
        return None
    if preferred_subdir and preferred_subdir != ".":
        return _pref_matches_archive(parsed, top, preferred_subdir)
    return top


def _drain_decompressor(
    decomp: Any, chunk: bytes, out: bytearray, max_bytes: int
) -> None:
    """Feed ``chunk`` and drain any unconsumed buffer without exceeding ``max_bytes``."""
    pending = chunk
    while True:
        limit = max(1, max_bytes - len(out) + 1)
        piece = decomp.decompress(pending, limit)
        out.extend(piece)
        if len(out) > max_bytes:
            raise ValueError(
                f"Tarball decompressed size exceeds limit ({max_bytes} bytes)"
            )
        if decomp.eof:
            break
        if hasattr(decomp, "unconsumed_tail"):
            pending = decomp.unconsumed_tail
            if not pending:
                break
        elif hasattr(decomp, "needs_input"):
            if decomp.needs_input:
                break
            pending = b""
        else:
            break


def _decompress_bounded(data: bytes, make_decomp: Any, max_bytes: int) -> bytes:
    """Stream-decompress ``data`` with an additive uncompressed-byte cap."""
    out = bytearray()
    rem = data
    while rem:
        decomp = make_decomp()
        pos = 0
        while pos < len(rem) and not decomp.eof:
            chunk = rem[pos : pos + 65536]
            pos += len(chunk)
            _drain_decompressor(decomp, chunk, out, max_bytes)
        if not decomp.eof:
            flush_fn = getattr(decomp, "flush", None)
            if callable(flush_fn):
                tail = flush_fn()
                out.extend(tail)
                if len(out) > max_bytes:
                    raise ValueError(
                        f"Tarball decompressed size exceeds limit ({max_bytes} bytes)"
                    )
            break
        nxt = decomp.unused_data + rem[pos:]
        if not nxt or len(nxt) >= len(rem):
            break
        rem = nxt
    return bytes(out)


def _open_bounded_tar(tar_bytes: bytes) -> tarfile.TarFile:
    """Bound uncompressed payload before constructing the TarFile reader."""
    if tar_bytes[:2] == b"\x1f\x8b":
        raw_tar = _decompress_bounded(
            tar_bytes,
            lambda: zlib.decompressobj(16 + zlib.MAX_WBITS),
            MAX_TARBALL_UNCOMPRESSED_BYTES,
        )
    elif tar_bytes[:3] == b"BZh":
        raw_tar = _decompress_bounded(
            tar_bytes, bz2.BZ2Decompressor, MAX_TARBALL_UNCOMPRESSED_BYTES
        )
    elif tar_bytes[:6] == b"\xfd7zXZ\x00":
        raw_tar = _decompress_bounded(
            tar_bytes, lzma.LZMADecompressor, MAX_TARBALL_UNCOMPRESSED_BYTES
        )
    else:
        if len(tar_bytes) > MAX_TARBALL_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"Tarball decompressed size exceeds limit ({MAX_TARBALL_UNCOMPRESSED_BYTES} bytes)"
            )
        raw_tar = tar_bytes
    return tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:")


def _validate_tarball_stream(
    tar_bytes: bytes, preferred_subdir: str | None = None
) -> tuple[tarfile.TarFile, list[tuple[tarfile.TarInfo, PurePosixPath]]]:
    tf = _open_bounded_tar(tar_bytes)
    try:
        raw_members: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
        count = 0
        while (member := tf.next()) is not None:
            count += 1
            if count > MAX_TARBALL_MEMBERS:
                raise ValueError(
                    f"Tarball exceeds maximum member count ({MAX_TARBALL_MEMBERS})"
                )
            pure = _validate_tar_member(member)
            if pure is not None:
                raw_members.append((member, pure))
        strip_prefix = _select_strip_prefix(raw_members, preferred_subdir)
        normalized: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
        for member, pure in raw_members:
            if strip_prefix and pure.parts and pure.parts[0] == strip_prefix:
                rest = pure.parts[1:]
                rel = PurePosixPath(*rest) if rest else PurePosixPath(".")
            else:
                rel = pure
            normalized.append((member, rel))
        return tf, normalized
    except Exception:
        tf.close()
        raise


def _collect_script_files(skill_dir: Path) -> list[str]:
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return []
    found: list[str] = []
    for root, dirs, files in os.walk(scripts_dir, followlinks=False):
        dirs.sort()
        files.sort()
        root_path = Path(root)
        for fname in files:
            fpath = root_path / fname
            if fpath.is_symlink():
                raise ValueError(f"Symlink inside scripts dir: {fpath}")
            found.append(fpath.relative_to(skill_dir).as_posix())
    return sorted(found)


def _write_staged_files(
    items: list[tuple[PurePosixPath, bytes]],
    *,
    skill_name: str,
    staging_dir: Path,
    max_files: int,
    max_bytes: int,
) -> tuple[Path, list[str]]:
    validate_skill_name(skill_name)
    if len(items) > max_files:
        raise ValueError(f"Skill exceeds file count limit ({max_files})")
    total_bytes = sum(len(data) for _p, data in items)
    if total_bytes > max_bytes:
        raise ValueError(f"Skill exceeds unpacked size limit ({max_bytes} bytes)")

    target_dir = staging_dir / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    for rel, data in items:
        if (
            rel == PurePosixPath(".")
            or ".." in rel.parts
            or rel.name.lower() == ".gitmodules"
        ):
            raise ValueError(f"Illegal skill relative file path: {rel}")
        dest = target_dir / Path(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    Skill.from_file(target_dir, strict=True)
    scripts = _collect_script_files(target_dir)
    return target_dir, scripts


def extract_tarball_subdir_safe(
    tar_bytes: bytes,
    *,
    subdir: str,
    skill_name: str,
    staging_dir: Path,
    max_files: int = MAX_SKILL_FILES,
    max_bytes: int = MAX_SKILL_BYTES,
) -> tuple[Path, list[str]]:
    """Deny-first extraction of one skill subdir from tarball bytes into staging_dir."""
    norm_sub = (
        PurePosixPath(".")
        if subdir in ("", ".", "./")
        else _normalize_rel_posix(subdir)
    )
    tf, members = _validate_tarball_stream(tar_bytes, preferred_subdir=str(norm_sub))
    try:
        collected: list[tuple[PurePosixPath, bytes]] = []
        running_bytes = 0
        for member, rel in members:
            inner = _matches_subdir(rel, norm_sub)
            if inner is None or inner == PurePosixPath(".") or not member.isreg():
                continue
            if len(collected) >= max_files:
                raise ValueError(f"Skill exceeds file count limit ({max_files})")
            handle = tf.extractfile(member)
            if handle is None:
                continue
            data = handle.read(max_bytes + 1)
            running_bytes += len(data)
            if running_bytes > max_bytes:
                raise ValueError(
                    f"Skill exceeds unpacked size limit ({max_bytes} bytes)"
                )
            collected.append((inner, data))
    finally:
        tf.close()
    if not collected:
        raise ValueError(f"Skill directory {subdir!r} not found in archive")
    return _write_staged_files(
        collected,
        skill_name=skill_name,
        staging_dir=staging_dir,
        max_files=max_files,
        max_bytes=max_bytes,
    )


def copy_local_dir_safe(
    src_dir: Path,
    *,
    skill_name: str,
    staging_dir: Path,
    max_files: int = MAX_SKILL_FILES,
    max_bytes: int = MAX_SKILL_BYTES,
    source_root: Path | None = None,
    subdir_rel: PurePosixPath | None = None,
) -> tuple[Path, list[str]]:
    """Copy a local skill directory into staging_dir refusing symlinks, special files & bloat."""
    if source_root is not None:
        _resolve_confined_no_symlinks(source_root, subdir_rel)
    if src_dir.is_symlink() or not src_dir.is_dir():
        raise ValueError(f"Local skill source is invalid or a symlink: {src_dir}")
    collected: list[tuple[PurePosixPath, bytes]] = []
    running_bytes = 0
    for root, dirs, files in os.walk(src_dir, followlinks=False):
        dirs.sort()
        files.sort()
        root_path = Path(root)
        for dname in dirs:
            if (root_path / dname).is_symlink():
                raise ValueError(
                    f"Refusing symlink in local skill dir: {root_path / dname}"
                )
        for fname in files:
            fpath = root_path / fname
            if fpath.is_symlink():
                raise ValueError(f"Refusing symlink in local skill dir: {fpath}")
            st = fpath.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise ValueError(f"Refusing non-regular file in local skill: {fpath}")
            if fname.lower() == ".gitmodules":
                raise ValueError("Git submodules (.gitmodules) are rejected")
            if len(collected) >= max_files:
                raise ValueError(f"Skill exceeds file count limit ({max_files})")
            data = fpath.read_bytes()
            running_bytes += len(data)
            if running_bytes > max_bytes:
                raise ValueError(
                    f"Skill exceeds unpacked size limit ({max_bytes} bytes)"
                )
            rel = PurePosixPath(fpath.relative_to(src_dir).as_posix())
            collected.append((rel, data))
    if not collected:
        raise ValueError(f"Local skill directory is empty: {src_dir}")
    return _write_staged_files(
        collected,
        skill_name=skill_name,
        staging_dir=staging_dir,
        max_files=max_files,
        max_bytes=max_bytes,
    )


def compute_skill_dir_hash(skill_dir: Path) -> str:
    """Compute deterministic SHA-256 hash over sorted relative POSIX paths + bytes."""
    if skill_dir.is_symlink() or not skill_dir.is_dir():
        raise ValueError(f"Refusing symlink or missing skill dir: {skill_dir}")
    files_list: list[tuple[str, Path]] = []
    for root, dirs, files in os.walk(skill_dir, followlinks=False):
        dirs.sort()
        files.sort()
        root_path = Path(root)
        for dname in dirs:
            if (root_path / dname).is_symlink():
                raise ValueError(
                    f"Refusing symlink dir inside skill: {root_path / dname}"
                )
        for fname in files:
            fpath = root_path / fname
            if fpath.is_symlink():
                raise ValueError(f"Refusing symlink file inside skill: {fpath}")
            st = fpath.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise ValueError(f"Refusing non-regular file inside skill: {fpath}")
            files_list.append((fpath.relative_to(skill_dir).as_posix(), fpath))
    hasher = hashlib.sha256()
    for rel, fpath in sorted(files_list, key=lambda item: item[0]):
        data = fpath.read_bytes()
        hasher.update(f"{rel}\x00{len(data)}\x00".encode("utf-8"))
        hasher.update(data)
    return f"sha256:{hasher.hexdigest()}"


def _parse_lock_entry(key: Any, val: Any) -> LockEntry:
    if not isinstance(val, dict):
        raise ValueError(f"Malformed lockfile entry for {key!r}")
    ns = validate_namespace(str(val.get("namespace", "")))
    name = validate_skill_name(str(val.get("name", "")))
    if str(key) != f"{ns}:{name}":
        raise ValueError(f"Lockfile key mismatch: {key!r} != '{ns}:{name}'")
    commit_sha = str(val.get("commit_sha", ""))
    if not _SHA_RE.match(commit_sha):
        raise ValueError(f"Invalid lockfile commit_sha for '{key}'")
    computed_hash = str(val.get("computed_hash", ""))
    if not _HASH_RE.match(computed_hash):
        raise ValueError(f"Invalid lockfile computed_hash for '{key}'")
    subdir_raw = str(val.get("subdir", "."))
    subdir = (
        "." if subdir_raw in ("", ".", "./") else str(_normalize_rel_posix(subdir_raw))
    )
    raw_scripts = val.get("script_files", [])
    if not isinstance(raw_scripts, list):
        raise ValueError(f"Invalid lockfile script_files for '{key}'")
    return LockEntry(
        namespace=ns,
        name=name,
        source=str(val.get("source", "")),
        repo_url=str(val.get("repo_url", "")),
        subdir=subdir,
        ref=str(val.get("ref", "")),
        commit_sha=commit_sha,
        computed_hash=computed_hash,
        has_scripts=bool(val.get("has_scripts", False)),
        script_files=[str(p) for p in raw_scripts],
        installed_at=str(val.get("installed_at", "")),
    )


def load_lockfile(lockfile_path: Path) -> dict[str, LockEntry]:
    """Load ./.agent/skills-lock.json keyed by ``<namespace>:<name>`` fail-closed."""
    _refuse_symlink(lockfile_path, "skills lockfile")
    if not lockfile_path.exists():
        return {}
    raw = json.loads(
        lockfile_path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
    )
    if not isinstance(raw, dict) or raw.get("version") != LOCKFILE_VERSION:
        raise ValueError(f"Unsupported lockfile schema in {lockfile_path}")
    skills_raw = raw.get("skills", {})
    if not isinstance(skills_raw, dict):
        raise ValueError(f"Malformed 'skills' map in {lockfile_path}")
    return {str(key): _parse_lock_entry(key, val) for key, val in skills_raw.items()}


def save_lockfile(lockfile_path: Path, entries: dict[str, LockEntry]) -> Path:
    """Persist ./.agent/skills-lock.json atomically with symlink refusal."""
    _refuse_symlink(lockfile_path, "skills lockfile")
    payload = {
        "version": LOCKFILE_VERSION,
        "skills": {
            key: {
                "namespace": val.namespace,
                "name": val.name,
                "source": val.source,
                "repo_url": val.repo_url,
                "subdir": val.subdir,
                "ref": val.ref,
                "commit_sha": val.commit_sha,
                "computed_hash": val.computed_hash,
                "has_scripts": val.has_scripts,
                "script_files": list(val.script_files),
                "installed_at": val.installed_at,
            }
            for key, val in sorted(entries.items())
        },
    }
    return _atomic_write_text(
        lockfile_path, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def _join_rel_posix(base: str, child: str) -> str:
    norm_base = "" if base in ("", ".", "./") else str(_normalize_rel_posix(base))
    norm_child = "" if child in ("", ".", "./") else str(_normalize_rel_posix(child))
    joined = (
        PurePosixPath(norm_base) / norm_child
        if norm_child
        else PurePosixPath(norm_base or ".")
    )
    norm = _normalize_rel_posix(str(joined))
    return "." if str(norm) in ("", ".") else str(norm)


def _find_skill_md_in_dir(root: Path) -> Path | None:
    for fname in ("SKILL.md", "skill.md"):
        cand = root / fname
        if not cand.is_symlink() and cand.is_file():
            return cand
    return None


def _skill_meta_from_dir(
    skill_dir: Path,
    *,
    fallback_name: str,
    fallback_desc: str,
    allow_root_name: bool = False,
) -> tuple[str, str]:
    md = _find_skill_md_in_dir(skill_dir)
    if md is None:
        return fallback_name, sanitize_display(fallback_desc)
    try:
        if allow_root_name:
            loaded = Skill.from_content(md.read_text(encoding="utf-8"), strict=True)
        else:
            loaded = Skill.from_file(skill_dir, strict=True)
        return loaded.name, sanitize_display(loaded.description)
    except Exception:
        return fallback_name, sanitize_display(fallback_desc)


def _resolve_external_source_dict(
    src_obj: dict[str, Any],
    *,
    fallback_name: str,
    fallback_desc: str,
    marketplace: str,
    default_ref: str | None,
) -> CatalogSkill | None:
    kind = str(src_obj.get("source", "")).strip()
    if kind not in ("github", "git-subdir"):
        return None
    repo_raw = src_obj.get("repo") or src_obj.get("url")
    if not isinstance(repo_raw, str) or not repo_raw:
        return None
    owner, repo, url_ref = parse_github_spec(repo_raw)
    path_raw = str(src_obj.get("path", ".")).strip() or "."
    subdir = _join_rel_posix(".", path_raw)
    ref = _validate_git_ref(src_obj.get("ref") or url_ref or default_ref)
    sha = src_obj.get("sha")
    commit_sha = sha if isinstance(sha, str) and _SHA_RE.match(sha) else None
    sname = validate_skill_name(
        PurePosixPath(subdir).name if subdir != "." else fallback_name
    )
    return CatalogSkill(
        name=sname,
        description=sanitize_display(fallback_desc),
        marketplace=marketplace,
        source=f"{owner}/{repo}",
        repo_url=canonical_github_repo_url(owner, repo),
        subdir=subdir,
        ref=ref,
        commit_sha=commit_sha,
    )


def _expand_plugin_subpath(
    root: Path,
    rel_subdir: str,
    *,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None,
    commit_sha: str | None,
    fallback_desc: str,
) -> list[CatalogSkill]:
    rel_norm = (
        PurePosixPath(".") if rel_subdir == "." else _normalize_rel_posix(rel_subdir)
    )
    try:
        target = _resolve_confined_no_symlinks(root, rel_norm)
    except ValueError:
        return []
    if not target.is_dir():
        return []
    if _find_skill_md_in_dir(target) is not None:
        fallback = target.name if rel_subdir != "." else marketplace
        sname, sdesc = _skill_meta_from_dir(
            target,
            fallback_name=fallback,
            fallback_desc=fallback_desc,
            allow_root_name=(rel_subdir == "."),
        )
        return [
            CatalogSkill(
                name=sname,
                description=sdesc,
                marketplace=marketplace,
                source=source,
                repo_url=repo_url,
                subdir=rel_subdir,
                ref=ref,
                commit_sha=commit_sha,
            )
        ]
    return _scan_skill_dirs(
        target,
        base_rel=rel_subdir,
        marketplace=marketplace,
        source=source,
        repo_url=repo_url,
        ref=ref,
        commit_sha=commit_sha,
    )


def _discover_from_plugins_list(
    root: Path,
    plugins: list[Any],
    *,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None,
    commit_sha: str | None,
) -> list[CatalogSkill]:
    found: list[CatalogSkill] = []
    for entry in plugins:
        if not isinstance(entry, dict):
            continue
        p_name = str(entry.get("name", ""))
        p_desc = str(entry.get("description", ""))
        raw_src = entry.get("source", ".")
        if isinstance(raw_src, dict):
            ext = _resolve_external_source_dict(
                raw_src,
                fallback_name=p_name,
                fallback_desc=p_desc,
                marketplace=marketplace,
                default_ref=ref,
            )
            if ext is not None:
                found.append(ext)
            continue
        base_sub = _join_rel_posix(".", str(raw_src or "."))
        raw_skills = entry.get("skills")
        if isinstance(raw_skills, list) and raw_skills:
            for item in raw_skills:
                sub_rel = item.get("path", ".") if isinstance(item, dict) else str(item)
                joined = _join_rel_posix(base_sub, str(sub_rel))
                found.extend(
                    _expand_plugin_subpath(
                        root,
                        joined,
                        marketplace=marketplace,
                        source=source,
                        repo_url=repo_url,
                        ref=ref,
                        commit_sha=commit_sha,
                        fallback_desc=p_desc,
                    )
                )
        else:
            found.extend(
                _expand_plugin_subpath(
                    root,
                    base_sub,
                    marketplace=marketplace,
                    source=source,
                    repo_url=repo_url,
                    ref=ref,
                    commit_sha=commit_sha,
                    fallback_desc=p_desc,
                )
            )
    return found


def _discover_from_flat_skills(
    root: Path,
    items: list[Any],
    *,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None,
    commit_sha: str | None,
) -> list[CatalogSkill]:
    found: list[CatalogSkill] = []
    for item in items:
        if isinstance(item, str):
            joined = _join_rel_posix(".", item)
            found.extend(
                _expand_plugin_subpath(
                    root,
                    joined,
                    marketplace=marketplace,
                    source=source,
                    repo_url=repo_url,
                    ref=ref,
                    commit_sha=commit_sha,
                    fallback_desc="",
                )
            )
        elif isinstance(item, dict):
            path_val = item.get("path") or item.get("subdir") or item.get("source")
            if isinstance(path_val, dict):
                ext = _resolve_external_source_dict(
                    path_val,
                    fallback_name=str(item.get("name", "")),
                    fallback_desc=str(item.get("description", "")),
                    marketplace=marketplace,
                    default_ref=ref,
                )
                if ext is not None:
                    found.append(ext)
            elif isinstance(path_val, str) and path_val:
                joined = _join_rel_posix(".", path_val)
                found.extend(
                    _expand_plugin_subpath(
                        root,
                        joined,
                        marketplace=marketplace,
                        source=source,
                        repo_url=repo_url,
                        ref=ref,
                        commit_sha=commit_sha,
                        fallback_desc=str(item.get("description", "")),
                    )
                )
    return found


def _scan_skill_dirs(
    base_dir: Path,
    *,
    base_rel: str,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None,
    commit_sha: str | None,
) -> list[CatalogSkill]:
    found: list[CatalogSkill] = []
    candidate_roots = [base_dir / "skills", base_dir]
    seen_subdirs: set[str] = set()
    for search_root, prefix in (
        (candidate_roots[0], _join_rel_posix(base_rel, "skills")),
        (candidate_roots[1], base_rel),
    ):
        if search_root.is_symlink() or not search_root.is_dir():
            continue
        for child in sorted(search_root.iterdir(), key=lambda p: p.name):
            if child.is_symlink() or not child.is_dir():
                continue
            if _find_skill_md_in_dir(child) is None:
                continue
            sub_rel = _join_rel_posix(prefix, child.name)
            if sub_rel in seen_subdirs:
                continue
            seen_subdirs.add(sub_rel)
            sname, sdesc = _skill_meta_from_dir(
                child, fallback_name=child.name, fallback_desc=""
            )
            found.append(
                CatalogSkill(
                    name=sname,
                    description=sdesc,
                    marketplace=marketplace,
                    source=source,
                    repo_url=repo_url,
                    subdir=sub_rel,
                    ref=ref,
                    commit_sha=commit_sha,
                )
            )
    if not found and (root_md := _find_skill_md_in_dir(base_dir)) is not None:
        loaded = Skill.from_content(root_md.read_text(encoding="utf-8"), strict=True)
        found.append(
            CatalogSkill(
                name=loaded.name,
                description=sanitize_display(loaded.description),
                marketplace=marketplace,
                source=source,
                repo_url=repo_url,
                subdir=base_rel,
                ref=ref,
                commit_sha=commit_sha,
            )
        )
    return found


def discover_catalog_from_tree(
    root: Path,
    *,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None = None,
    commit_sha: str | None = None,
) -> list[CatalogSkill]:
    """Discover installable skills from manifest or SKILL.md directory tree."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Catalog root is missing or a symlink: {root}")
    for rel_manifest in _MANIFEST_CANDIDATES:
        try:
            mpath = _resolve_confined_no_symlinks(root, rel_manifest)
        except ValueError:
            continue
        if not mpath.is_file():
            continue
        data = json.loads(
            mpath.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(data, dict):
            raise ValueError(f"Malformed marketplace manifest: {mpath}")
        if isinstance(data.get("plugins"), list):
            return _discover_from_plugins_list(
                root,
                data["plugins"],
                marketplace=marketplace,
                source=source,
                repo_url=repo_url,
                ref=ref,
                commit_sha=commit_sha,
            )
        if isinstance(data.get("skills"), list):
            return _discover_from_flat_skills(
                root,
                data["skills"],
                marketplace=marketplace,
                source=source,
                repo_url=repo_url,
                ref=ref,
                commit_sha=commit_sha,
            )
    return _scan_skill_dirs(
        root,
        base_rel=".",
        marketplace=marketplace,
        source=source,
        repo_url=repo_url,
        ref=ref,
        commit_sha=commit_sha,
    )


def discover_catalog_from_tarball(
    tar_bytes: bytes,
    *,
    marketplace: str,
    source: str,
    repo_url: str,
    ref: str | None = None,
    commit_sha: str | None = None,
) -> list[CatalogSkill]:
    """Inspect manifests and SKILL.md metadata inside tar_bytes safely without symlinks."""
    tf, members = _validate_tarball_stream(tar_bytes)
    try:
        with tempfile.TemporaryDirectory(prefix="sc_cat_") as tmp:
            root = Path(tmp)
            scan_files = 0
            scan_bytes = 0
            for member, rel in members:
                if not member.isreg() or rel == PurePosixPath("."):
                    continue
                if rel.name not in ("marketplace.json", "SKILL.md", "skill.md"):
                    continue
                scan_files += 1
                if scan_files > MAX_CATALOG_SCAN_FILES:
                    raise ValueError(
                        f"Catalog archive exceeds metadata file limit ({MAX_CATALOG_SCAN_FILES})"
                    )
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                dest = root / Path(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = handle.read(MAX_SKILL_BYTES + 1)
                if len(data) > MAX_SKILL_BYTES:
                    raise ValueError(f"Catalog metadata file exceeds limit: {rel}")
                scan_bytes += len(data)
                if scan_bytes > MAX_CATALOG_SCAN_BYTES:
                    raise ValueError(
                        f"Catalog archive exceeds metadata byte limit ({MAX_CATALOG_SCAN_BYTES} bytes)"
                    )
                dest.write_bytes(data)
            return discover_catalog_from_tree(
                root,
                marketplace=marketplace,
                source=source,
                repo_url=repo_url,
                ref=ref,
                commit_sha=commit_sha,
            )
    finally:
        tf.close()


def _fetch_marketplace_catalog(
    entry: MarketplaceEntry, *, client: httpx.Client | None = None
) -> list[CatalogSkill]:
    if entry.kind == "local":
        root = Path(entry.source)
        return discover_catalog_from_tree(
            root,
            marketplace=entry.name,
            source=entry.source,
            repo_url=str(root.resolve()),
            ref=entry.ref or "local",
        )
    owner, repo, spec_ref = parse_github_spec(entry.source)
    sha, resolved_ref = resolve_github_commit(
        owner, repo, entry.ref or spec_ref, client=client
    )
    tar_bytes = download_github_tarball(owner, repo, sha, client=client)
    return discover_catalog_from_tarball(
        tar_bytes,
        marketplace=entry.name,
        source=f"{owner}/{repo}",
        repo_url=canonical_github_repo_url(owner, repo),
        ref=resolved_ref,
        commit_sha=sha,
    )


def add_marketplace(
    source: str,
    *,
    name: str | None = None,
    ref: str | None = None,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> tuple[MarketplaceEntry, list[CatalogSkill]]:
    """Register a GitHub or local-path marketplace and cache its catalog."""
    existing = load_marketplaces(marketplaces_path)
    local_cand = Path(source).expanduser()
    if local_cand.exists() and "://" not in source:
        if local_cand.is_symlink() or not local_cand.is_dir():
            raise ValueError(
                f"Local catalog path must be a non-symlink dir: {source!r}"
            )
        resolved_dir = local_cand.resolve()
        alias = validate_namespace(
            name or github_repo_slug("localcat", resolved_dir.name)
        )
        entry = MarketplaceEntry(
            name=alias,
            source=str(resolved_dir),
            kind="local",
            ref=_validate_git_ref(ref),
            added_at=_utc_now_iso(),
        )
    else:
        owner, repo, spec_ref = parse_github_spec(source)
        alias = validate_namespace(name or github_repo_slug(owner, repo))
        entry = MarketplaceEntry(
            name=alias,
            source=f"{owner}/{repo}",
            kind="github",
            ref=_validate_git_ref(ref or spec_ref),
            added_at=_utc_now_iso(),
        )
    skills = _fetch_marketplace_catalog(entry, client=client)
    existing[alias] = entry
    save_marketplaces(existing, marketplaces_path)
    save_cached_catalog(alias, skills, cache_dir)
    return entry, skills


def list_marketplaces(
    *, marketplaces_path: Path | None = None
) -> list[MarketplaceEntry]:
    """List registered marketplaces sorted by alias (zero network calls)."""
    entries = load_marketplaces(marketplaces_path)
    return [entries[k] for k in sorted(entries)]


def update_marketplace(
    name: str | None = None,
    *,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> dict[str, list[CatalogSkill]]:
    """Refresh one or all registered marketplace catalogs into cache."""
    entries = load_marketplaces(marketplaces_path)
    if name is not None:
        alias = validate_namespace(name)
        if alias not in entries:
            raise ValueError(f"Unknown marketplace: {name!r}")
        targets = [entries[alias]]
    else:
        targets = list(entries.values())
    refreshed: dict[str, list[CatalogSkill]] = {}
    for entry in targets:
        skills = _fetch_marketplace_catalog(entry, client=client)
        save_cached_catalog(entry.name, skills, cache_dir)
        refreshed[entry.name] = skills
    return refreshed


def remove_marketplace(
    name: str,
    *,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
) -> bool:
    """Remove a registered marketplace alias and its cached catalog."""
    alias = validate_namespace(name)
    entries = load_marketplaces(marketplaces_path)
    if alias not in entries:
        return False
    entries.pop(alias)
    save_marketplaces(entries, marketplaces_path)
    cpath = _cache_file(alias, cache_dir)
    if not cpath.parent.is_symlink() and not cpath.is_symlink():
        cpath.unlink(missing_ok=True)
    return True


def browse_marketplaces(
    marketplace_name: str | None = None,
    *,
    refresh: bool = False,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> list[CatalogSkill]:
    """List cached catalog skills locally (zero auto-network unless refresh=True)."""
    entries = load_marketplaces(marketplaces_path)
    if marketplace_name is not None:
        alias = validate_namespace(marketplace_name)
        if alias not in entries:
            raise ValueError(f"Unknown marketplace: {marketplace_name!r}")
        if refresh:
            return update_marketplace(
                alias,
                marketplaces_path=marketplaces_path,
                cache_dir=cache_dir,
                client=client,
            )[alias]
        return load_cached_catalog(alias, cache_dir)
    if refresh and entries:
        refreshed = update_marketplace(
            None,
            marketplaces_path=marketplaces_path,
            cache_dir=cache_dir,
            client=client,
        )
        return [s for ns in sorted(refreshed) for s in refreshed[ns]]
    out: list[CatalogSkill] = []
    for alias in sorted(entries):
        out.extend(load_cached_catalog(alias, cache_dir))
    return out


def _replace_dir(src: Path, dst: Path) -> None:
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.move(str(src), str(dst))


@contextmanager
def _staged_swap_transaction(
    staged_dir: Path, dest_dir: Path, *, cwd: Path
) -> Iterator[None]:
    """Swap staged_dir into dest_dir, rolling back if post-swap commit fails."""
    _refuse_symlink_chain(
        cwd,
        ".agent",
        "skills-marketplaces",
        dest_dir.parent.name,
        dest_dir.name,
    )
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_root: Path | None = None
    backup: Path | None = None
    if dest_dir.exists():
        backup_root = Path(
            tempfile.mkdtemp(prefix=f".{dest_dir.name}.bak-", dir=dest_dir.parent)
        )
        backup = backup_root / dest_dir.name
        os.replace(dest_dir, backup)
    try:
        _replace_dir(staged_dir, dest_dir)
        yield
    except Exception:
        if dest_dir.exists() and not dest_dir.is_symlink():
            shutil.rmtree(dest_dir, ignore_errors=True)
        if backup is not None and backup.exists() and not dest_dir.exists():
            os.replace(backup, dest_dir)
        raise
    finally:
        if backup_root is not None:
            shutil.rmtree(backup_root, ignore_errors=True)


def _atomic_swap_skill_dir(
    staged_dir: Path, dest_dir: Path, *, cwd: Path | None = None
) -> None:
    root = (
        cwd if cwd is not None else dest_dir.parent.parent.parent.parent
    )  # cwd when dest is <cwd>/.agent/skills-marketplaces/<ns>/<skill>
    with _staged_swap_transaction(staged_dir, dest_dir, cwd=root):
        pass


def _script_file_digests(skill_dir: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir() or scripts_dir.is_symlink():
        return digests
    for rel in _collect_script_files(skill_dir):
        data = (skill_dir / rel).read_bytes()
        digests[rel] = hashlib.sha256(data).hexdigest()
    return digests


def _install_catalog_skill(
    cat_skill: CatalogSkill,
    *,
    cwd: Path,
    client: httpx.Client | None,
    expected_hash: str | None = None,
) -> tuple[LockEntry, dict[str, str], dict[str, str], str | None]:
    ns = validate_namespace(cat_skill.marketplace)
    sname = validate_skill_name(cat_skill.name)
    _refuse_symlink_chain(cwd, ".agent", "skills-marketplaces")
    stage_parent = cwd / MARKETPLACES_SKILLS_REL
    stage_parent.mkdir(parents=True, exist_ok=True)
    dest_dir = stage_parent / ns / sname
    old_scripts = _script_file_digests(dest_dir) if dest_dir.is_dir() else {}
    lockfile_path = cwd / SKILLS_LOCK_REL
    existing_lock = load_lockfile(lockfile_path)
    key = f"{ns}:{sname}"
    old_sha = existing_lock[key].commit_sha if key in existing_lock else None

    with tempfile.TemporaryDirectory(prefix=".sc_stage_", dir=stage_parent) as tmp:
        staging_dir = Path(tmp)
        repo_path = Path(cat_skill.repo_url)
        if not cat_skill.repo_url.startswith("https://"):
            rel_sub = (
                PurePosixPath(".")
                if cat_skill.subdir == "."
                else _normalize_rel_posix(cat_skill.subdir)
            )
            src_dir = _resolve_confined_no_symlinks(repo_path, rel_sub)
            staged_dir, script_files = copy_local_dir_safe(
                src_dir,
                skill_name=sname,
                staging_dir=staging_dir,
                source_root=repo_path,
                subdir_rel=rel_sub,
            )
            computed_hash = compute_skill_dir_hash(staged_dir)
            commit_sha = computed_hash.removeprefix("sha256:")[:40]
            ref_val = cat_skill.ref or "local"
        else:
            owner, repo, url_ref = parse_github_spec(cat_skill.repo_url)
            if cat_skill.commit_sha and _SHA_RE.match(cat_skill.commit_sha):
                commit_sha = cat_skill.commit_sha
                ref_val = cat_skill.ref or url_ref or commit_sha
            else:
                commit_sha, ref_val = resolve_github_commit(
                    owner, repo, cat_skill.ref or url_ref, client=client
                )
            tar_bytes = download_github_tarball(owner, repo, commit_sha, client=client)
            staged_dir, script_files = extract_tarball_subdir_safe(
                tar_bytes,
                subdir=cat_skill.subdir,
                skill_name=sname,
                staging_dir=staging_dir,
            )
            computed_hash = compute_skill_dir_hash(staged_dir)

        if expected_hash is not None and computed_hash != expected_hash:
            raise ValueError(f"Hash mismatch restoring pinned {key} at {commit_sha}")
        new_scripts = _script_file_digests(staged_dir)
        lock_entry = LockEntry(
            namespace=cat_skill.marketplace,
            name=cat_skill.name,
            source=cat_skill.source,
            repo_url=cat_skill.repo_url,
            subdir=cat_skill.subdir,
            ref=ref_val,
            commit_sha=commit_sha,
            computed_hash=computed_hash,
            has_scripts=bool(script_files),
            script_files=script_files,
            installed_at=_utc_now_iso(),
        )
        existing_lock[key] = lock_entry
        with _staged_swap_transaction(staged_dir, dest_dir, cwd=cwd):
            save_lockfile(lockfile_path, existing_lock)
    return lock_entry, old_scripts, new_scripts, old_sha


def _scripts_warning(entry: LockEntry) -> str:
    joined = ", ".join(sanitize_display(p) for p in entry.script_files)
    return (
        f"Warning: '{entry.namespaced}' bundles scripts ({joined}). "
        "Scripts never auto-execute and remain gated by shell/python_repl HITL approval."
    )


def _lookup_catalog_entry(
    alias_raw: str,
    skill_name: str,
    *,
    marketplaces_path: Path | None,
    cache_dir: Path | None,
) -> list[CatalogSkill]:
    alias = validate_namespace(alias_raw)
    catalog = browse_marketplaces(
        alias, refresh=False, marketplaces_path=marketplaces_path, cache_dir=cache_dir
    )
    matches = [s for s in catalog if s.name == skill_name]
    if not matches:
        raise ValueError(f"Skill {skill_name!r} not found in marketplace {alias!r}")
    return matches


def _resolve_install_targets(
    target: str,
    *,
    skill_filter: str | None,
    marketplaces_path: Path | None,
    cache_dir: Path | None,
    client: httpx.Client | None,
) -> list[CatalogSkill]:
    if ":" in target and "://" not in target:
        ns, _, sname = target.partition(":")
        return _lookup_catalog_entry(
            ns, sname, marketplaces_path=marketplaces_path, cache_dir=cache_dir
        )
    if "@" in target and "/" not in target:
        sname, _, ns = target.partition("@")
        return _lookup_catalog_entry(
            ns, sname, marketplaces_path=marketplaces_path, cache_dir=cache_dir
        )

    local_cand = Path(target).expanduser()
    if local_cand.exists() and "://" not in target:
        if local_cand.is_symlink() or not local_cand.is_dir():
            raise ValueError(f"Local skill path must be a non-symlink dir: {target!r}")
        resolved = local_cand.resolve()
        slug = github_repo_slug("localcat", resolved.name)
        found = discover_catalog_from_tree(
            resolved,
            marketplace=slug,
            source=str(resolved),
            repo_url=str(resolved),
            ref="local",
        )
    else:
        owner, repo, ref = parse_github_spec(target)
        slug = github_repo_slug(owner, repo)
        sha, resolved_ref = resolve_github_commit(owner, repo, ref, client=client)
        tar_bytes = download_github_tarball(owner, repo, sha, client=client)
        found = discover_catalog_from_tarball(
            tar_bytes,
            marketplace=slug,
            source=f"{owner}/{repo}",
            repo_url=canonical_github_repo_url(owner, repo),
            ref=resolved_ref,
            commit_sha=sha,
        )
    if skill_filter:
        found = [s for s in found if s.name == skill_filter]
    if not found:
        raise ValueError(f"No matching installable skills found for {target!r}")
    return found


def install_skill(
    target: str,
    *,
    skill_filter: str | None = None,
    cwd: Path | None = None,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> InstallOutcome:
    """Install one or more marketplace/repository skills and update skills-lock.json."""
    root = cwd if cwd is not None else Path.cwd()
    targets = _resolve_install_targets(
        target,
        skill_filter=skill_filter,
        marketplaces_path=marketplaces_path,
        cache_dir=cache_dir,
        client=client,
    )
    installed: list[LockEntry] = []
    warnings: list[str] = []
    for cat_skill in targets:
        entry, _old, _new, _old_sha = _install_catalog_skill(
            cat_skill, cwd=root, client=client
        )
        installed.append(entry)
        if entry.has_scripts:
            warnings.append(_scripts_warning(entry))
    return InstallOutcome(installed=installed, warnings=warnings)


def _refresh_entry_from_sources(
    lock_entry: LockEntry,
    *,
    marketplaces_path: Path | None,
    cache_dir: Path | None,
    client: httpx.Client | None,
) -> CatalogSkill:
    entries = load_marketplaces(marketplaces_path)
    if lock_entry.namespace in entries:
        catalog = update_marketplace(
            lock_entry.namespace,
            marketplaces_path=marketplaces_path,
            cache_dir=cache_dir,
            client=client,
        )[lock_entry.namespace]
        for cand in catalog:
            if cand.name == lock_entry.name:
                return cand
    _validate_sync_source(lock_entry, marketplaces_path)
    return CatalogSkill(
        name=lock_entry.name,
        description="",
        marketplace=lock_entry.namespace,
        source=lock_entry.source,
        repo_url=lock_entry.repo_url,
        subdir=lock_entry.subdir,
        ref=lock_entry.ref,
        commit_sha=None,
    )


def _select_lock_keys(lock_map: dict[str, LockEntry], target: str | None) -> list[str]:
    if target is None:
        return sorted(lock_map)
    if target in lock_map:
        return [target]
    keys = [k for k, v in sorted(lock_map.items()) if v.name == target]
    if not keys:
        raise ValueError(f"Installed marketplace skill not found: {target!r}")
    return keys


def _update_single_skill(
    cur: LockEntry,
    *,
    root: Path,
    marketplaces_path: Path | None,
    cache_dir: Path | None,
    client: httpx.Client | None,
) -> SkillUpdateRecord | None:
    cat = _refresh_entry_from_sources(
        cur, marketplaces_path=marketplaces_path, cache_dir=cache_dir, client=client
    )
    new_entry, old_scripts, new_scripts, old_sha = _install_catalog_skill(
        cat, cwd=root, client=client
    )
    if (
        new_entry.commit_sha == cur.commit_sha
        and new_entry.computed_hash == cur.computed_hash
    ):
        return None
    added = sorted(p for p in new_scripts if p not in old_scripts)
    changed = sorted(
        p for p in new_scripts if p in old_scripts and new_scripts[p] != old_scripts[p]
    )
    return SkillUpdateRecord(
        entry=new_entry,
        old_sha=old_sha or cur.commit_sha,
        new_sha=new_entry.commit_sha,
        added_scripts=added,
        changed_scripts=changed,
    )


def update_installed_skills(
    target: str | None = None,
    *,
    cwd: Path | None = None,
    marketplaces_path: Path | None = None,
    cache_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> UpdateOutcome:
    """Update pinned marketplace skills to latest ref commit and diff bundled scripts."""
    root = cwd if cwd is not None else Path.cwd()
    lock_map = load_lockfile(root / SKILLS_LOCK_REL)
    keys = _select_lock_keys(lock_map, target)

    updated: list[SkillUpdateRecord] = []
    unchanged: list[str] = []
    warnings: list[str] = []
    for key in keys:
        rec = _update_single_skill(
            lock_map[key],
            root=root,
            marketplaces_path=marketplaces_path,
            cache_dir=cache_dir,
            client=client,
        )
        if rec is None:
            unchanged.append(key)
            continue
        updated.append(rec)
        if rec.added_scripts or rec.changed_scripts or rec.entry.has_scripts:
            warnings.append(_scripts_warning(rec.entry))
    return UpdateOutcome(updated=updated, unchanged=unchanged, warnings=warnings)


def _validate_sync_source(
    lock_entry: LockEntry, marketplaces_path: Path | None
) -> None:
    if lock_entry.repo_url.startswith("https://"):
        parse_github_spec(lock_entry.repo_url)
        return
    entries = load_marketplaces(marketplaces_path)
    reg = entries.get(lock_entry.namespace)
    if (
        reg is None
        or reg.kind != "local"
        or Path(reg.source).resolve() != Path(lock_entry.repo_url).resolve()
    ):
        raise ValueError(
            f"Refusing to sync unregistered local path for '{lock_entry.namespaced}' from skills-lock.json."
        )


def sync_installed_skills(
    *,
    cwd: Path | None = None,
    marketplaces_path: Path | None = None,
    client: httpx.Client | None = None,
) -> SyncOutcome:
    """Verify and restore pinned skills from ./.agent/skills-lock.json."""
    root = cwd if cwd is not None else Path.cwd()
    lockfile_path = root / SKILLS_LOCK_REL
    lock_map = load_lockfile(lockfile_path)
    restored: list[LockEntry] = []
    verified: list[str] = []
    warnings: list[str] = []

    for key, lock_entry in sorted(lock_map.items()):
        dest_dir = (
            root / MARKETPLACES_SKILLS_REL / lock_entry.namespace / lock_entry.name
        )
        needs_restore = True
        try:
            _refuse_symlink_chain(
                root,
                ".agent",
                "skills-marketplaces",
                lock_entry.namespace,
                lock_entry.name,
            )
            dest_safe = True
        except ValueError:
            dest_safe = False
        if dest_safe and dest_dir.exists() and not dest_dir.is_symlink():
            try:
                if compute_skill_dir_hash(dest_dir) == lock_entry.computed_hash:
                    verified.append(key)
                    needs_restore = False
            except ValueError:
                needs_restore = True
        if not needs_restore:
            continue
        _validate_sync_source(lock_entry, marketplaces_path)
        cat = CatalogSkill(
            name=lock_entry.name,
            description="",
            marketplace=lock_entry.namespace,
            source=lock_entry.source,
            repo_url=lock_entry.repo_url,
            subdir=lock_entry.subdir,
            ref=lock_entry.ref,
            commit_sha=lock_entry.commit_sha,
        )
        restored_entry, _old, _new, _old_sha = _install_catalog_skill(
            cat,
            cwd=root,
            client=client,
            expected_hash=lock_entry.computed_hash,
        )
        restored.append(restored_entry)
        if restored_entry.has_scripts:
            warnings.append(_scripts_warning(restored_entry))
    return SyncOutcome(restored=restored, verified=verified, warnings=warnings)


def _prune_namespace_dir(ns_dir: Path) -> None:
    try:
        if ns_dir.is_dir() and not ns_dir.is_symlink() and not any(ns_dir.iterdir()):
            ns_dir.rmdir()
    except OSError:
        pass


def _has_symlink_in_install_tree(
    marketplaces_dir: Path, ns: str, skill_dir: Path
) -> bool:
    return (
        marketplaces_dir.parent.is_symlink()
        or marketplaces_dir.is_symlink()
        or (marketplaces_dir / ns).is_symlink()
        or skill_dir.is_symlink()
    )


def remove_installed_skill(
    target: str, *, marketplaces_dir: Path, lockfile_path: Path
) -> RemoveOutcome:
    """Remove an installed marketplace skill directory and evict its lockfile entry."""
    if ":" not in target:
        return RemoveOutcome(False, f"Refused to remove skill {target!r}.")
    ns, _, sname = target.partition(":")
    if (
        not valid_namespace(ns)
        or not sname
        or "/" in sname
        or "\\" in sname
        or ".." in sname
    ):
        return RemoveOutcome(False, f"Refused to remove skill {target!r}.")
    skill_dir = marketplaces_dir / ns / sname
    if _has_symlink_in_install_tree(marketplaces_dir, ns, skill_dir):
        return RemoveOutcome(False, f"Refused to remove symlinked skill '{target}'.")
    lock_map = load_lockfile(lockfile_path) if not lockfile_path.is_symlink() else {}
    removed_fs = False
    if skill_dir.is_dir():
        resolved = skill_dir.resolve()
        ns_resolved = (marketplaces_dir / ns).resolve()
        if resolved.parent == ns_resolved and resolved.name == sname:
            shutil.rmtree(resolved)
            _prune_namespace_dir(marketplaces_dir / ns)
            removed_fs = True
    removed_lock = lock_map.pop(target, None) is not None
    if removed_lock:
        save_lockfile(lockfile_path, lock_map)
    if removed_fs or removed_lock:
        return RemoveOutcome(True, f"Removed skill '{target}'.")
    return RemoveOutcome(False, f"No marketplace skill named '{target}'.")


def verify_installed_marketplace_skills(
    marketplaces_dir: Path, lockfile_path: Path
) -> tuple[list[VerifiedMarketplaceSkill], list[str]]:
    """Verify ./.agent/skills-marketplaces against skills-lock.json; warn-and-skip on drift."""
    warnings: list[str] = []
    if lockfile_path.parent.is_symlink() or lockfile_path.is_symlink():
        return [], [
            f"Skills lockfile {lockfile_path} is a symlink — skipping all marketplace skills."
        ]
    try:
        lock_map = load_lockfile(lockfile_path)
    except Exception as exc:
        return [], [
            f"Unreadable skills lockfile {lockfile_path}: {sanitize_display(exc)}"
        ]

    if marketplaces_dir.parent.is_symlink() or marketplaces_dir.is_symlink():
        return [], [
            f"Marketplace skills dir {marketplaces_dir} is a symlink — skipping all marketplace skills."
        ]
    if not marketplaces_dir.exists():
        return [], warnings

    verified: list[VerifiedMarketplaceSkill] = []
    for ns_dir in sorted(marketplaces_dir.iterdir(), key=lambda p: p.name):
        if ns_dir.is_symlink():
            warnings.append(
                f"Skipped symlinked marketplace namespace {ns_dir.name!r} — remove symlink to recover."
            )
            continue
        if not ns_dir.is_dir() or not valid_namespace(ns_dir.name):
            continue
        for skill_dir in sorted(ns_dir.iterdir(), key=lambda p: p.name):
            key = f"{ns_dir.name}:{skill_dir.name}"
            if skill_dir.is_symlink():
                warnings.append(
                    f"Skipped symlinked marketplace skill '{key}' — run '/skills remove {key}'."
                )
                continue
            if not skill_dir.is_dir():
                continue
            lock_entry = lock_map.get(key)
            if lock_entry is None:
                warnings.append(
                    f"Skipped unlocked marketplace skill '{key}' — run '/skills remove {key}' or reinstall."
                )
                continue
            try:
                actual_hash = compute_skill_dir_hash(skill_dir)
                if actual_hash != lock_entry.computed_hash:
                    warnings.append(
                        f"Skipped hash-drifted skill '{key}' — run '/skills sync' or '/skills remove {key}'."
                    )
                    continue
                Skill.from_file(skill_dir, strict=True)
            except Exception as exc:
                warnings.append(
                    f"Skipped invalid marketplace skill '{key}' ({sanitize_display(exc)}) — run '/skills sync'."
                )
                continue
            verified.append(
                VerifiedMarketplaceSkill(
                    namespace=ns_dir.name,
                    name=skill_dir.name,
                    path=skill_dir,
                    entry=lock_entry,
                )
            )
    return verified, warnings
