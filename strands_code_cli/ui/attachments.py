"""Inline @file resolution, gitignore-aware discovery, /file picker, and media attachments (TOOL-05)."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

from strands_code_cli.model.model_switch import supports_media
from strands_code_cli.platform_io import refuse_symlink_under_roots
from strands_code_cli.policy.core import (
    Deny,
    PolicyConfig,
    _is_sensitive_read_path,
    decide,
)
from strands_code_cli.policy.scope import confine, effective_roots, resolve
from strands_code_cli.policy.tool_use_guard import validate_content_blocks
from strands_code_cli.ui.console import sanitize_display

ATTACHMENT_MAX_FILE_BYTES = 4 * 1024 * 1024
"""Maximum bytes read from a single @file attachment (4 MiB, CODEACT parity)."""

ATTACHMENT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
"""Maximum cumulative bytes across all @file attachments in one turn (16 MiB)."""

ATTACHMENT_MAX_COUNT = 8
"""Maximum distinct file attachments permitted in a single turn."""

IMAGE_EXT_FORMATS: dict[str, str] = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
}

BINARY_DOC_EXT_FORMATS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".doc": "doc",
    ".xls": "xls",
}

_SKIP_WALK_DIRS = frozenset(
    {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
)
_AT_TOKEN_RE = re.compile(r'(?<![\w/\\])@(?:(?:"([^"\r\n]+)")|([^\s"\'`]+))')
_DOC_NAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9 \-()\[\]]+")
_TRAILING_PUNCT = ",.;:!?)]}"


def _load_read_policy(real_base: Path) -> tuple[PolicyConfig | None, str | None]:
    """Load active home + repo PolicyConfig fail-closed."""
    try:
        return (PolicyConfig.load(repo_path=real_base / ".agent" / "policy.toml"), None)
    except ValueError as exc:
        return (None, f"Refused attachment read by policy: {exc}")


def _is_candidate_safe(
    candidate: Path,
    *,
    real_base: Path,
    extra_roots: tuple[Path, ...],
    policy: PolicyConfig,
) -> bool:
    """Return True if candidate is a non-symlink regular file allowed under policy."""
    if candidate.is_symlink():
        return False
    try:
        resolved = confine(candidate, real_base, extra_roots=extra_roots)
        refuse_symlink_under_roots(resolved, (real_base, *extra_roots), "attachment")
    except ValueError:
        return False
    if _is_sensitive_read_path(str(candidate), real_base) or _is_sensitive_read_path(
        str(resolved), real_base
    ):
        return False
    if isinstance(decide("read", {"path": str(resolved)}, policy, cwd=real_base), Deny):
        return False
    return candidate.is_file()


def _git_ls_files(root: Path, limit: int) -> list[Path] | None:
    """List gitignore-filtered workspace files via git ls-files when inside a repo."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            shell=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if top.returncode != 0:
            return None
        proc = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            shell=False,
            capture_output=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    items: list[Path] = []
    for raw_rel in proc.stdout.split(b"\x00"):
        if not raw_rel:
            continue
        rel = raw_rel.decode("utf-8", errors="surrogateescape")
        try:
            items.append(root / rel)
        except ValueError:
            continue
        if len(items) >= limit:
            break
    return items


def _walk_files(root: Path, limit: int) -> list[Path]:
    """Bounded os.walk fallback for directories outside a git repository."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in _SKIP_WALK_DIRS and not (Path(dirpath) / d).is_symlink()
        )
        for name in sorted(filenames):
            found.append(Path(dirpath) / name)
            if len(found) >= limit:
                return found
    return found


def discover_workspace_files(
    cwd: str | Path | None = None, *, limit: int = 5000
) -> list[str]:
    """Return sorted gitignore-filtered workspace files safe to reference via @file."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    real_base = Path(os.path.realpath(base))
    policy, err = _load_read_policy(real_base)
    if err is not None or policy is None:
        return []
    roots = effective_roots(real_base, policy, tool_name="read")
    real_tmp = Path(os.path.realpath("/tmp"))
    extra_roots = tuple(r for r in roots if r not in (real_base, real_tmp))

    candidates = _git_ls_files(real_base, limit)
    if candidates is None:
        candidates = _walk_files(real_base, limit)
    for extra in extra_roots:
        if extra.is_dir() and len(candidates) < limit:
            candidates.extend(_walk_files(extra, limit - len(candidates)))

    results: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        if not _is_candidate_safe(
            cand, real_base=real_base, extra_roots=extra_roots, policy=policy
        ):
            continue
        try:
            rel = cand.relative_to(real_base).as_posix()
        except ValueError:
            rel = cand.as_posix()
        if rel not in seen:
            seen.add(rel)
            results.append(rel)
        if len(results) >= limit:
            break
    return sorted(results)


def _fuzzy_filter_files(files: list[str], query: str) -> list[str]:
    """Filter workspace files by substring then fuzzy subsequence."""
    q = query.strip().lower()
    if not q:
        return files
    exact = [f for f in files if q in f.lower()]
    if exact:
        return exact
    fuzzy: list[str] = []
    for item in files:
        pos = 0
        lowered = item.lower()
        for ch in lowered:
            if pos < len(q) and ch == q[pos]:
                pos += 1
        if pos == len(q):
            fuzzy.append(item)
    return fuzzy


def format_at_reference(rel_or_abs: str) -> str:
    """Format a selected path as `@path` or `@"path with spaces"`."""
    if any(ch.isspace() for ch in rel_or_abs):
        return f'@"{rel_or_abs}" '
    return f"@{rel_or_abs} "


def pick_file_for_prompt(
    query: str = "", *, cwd: str | Path | None = None
) -> tuple[str | None, str | None]:
    """Open TTY picker over safe workspace files and return prompt-buffer pre-fill."""
    from strands_code_cli.ui.choice import radio_choice

    files = discover_workspace_files(cwd=cwd)
    matches = _fuzzy_filter_files(files, query)
    if not matches:
        safe_q = sanitize_display(query.strip())
        note = (
            f"No workspace files matching {safe_q!r}."
            if safe_q
            else "No workspace files found."
        )
        return (None, note)
    shown = matches[:50]
    options: list[tuple[str, str]] = [(item, sanitize_display(item)) for item in shown]
    title = "Attach workspace file (@file)"
    if len(matches) > len(shown):
        title = f"Attach workspace file (showing {len(shown)} of {len(matches)})"
    try:
        picked = radio_choice(title, options, default=1)
    except RuntimeError:
        return (
            None,
            "Interactive TTY required for /file picker; reference files inline with @<path>.",
        )
    if picked is None:
        return (None, "File picker cancelled.")
    return (format_at_reference(picked), None)


def extract_at_tokens(text: str) -> list[str]:
    """Extract raw `@path` / `@"path with spaces"` tokens from user-typed text."""
    tokens: list[str] = []
    for match in _AT_TOKEN_RE.finditer(text):
        quoted, bare = match.group(1), match.group(2)
        tok = quoted if quoted is not None else bare
        if tok:
            tokens.append(tok)
    return tokens


def sanitize_document_name(path: Path) -> str:
    """Sanitize filename to Bedrock/provider-safe `[A-Za-z0-9 -()[]]` label."""
    cleaned = _DOC_NAME_UNSAFE_RE.sub(" ", path.stem)
    collapsed = " ".join(cleaned.split()).strip()
    if not collapsed:
        return "document"
    return collapsed[:64]


def _refuse_token_symlinks(
    expanded: Path, real_base: Path, roots: tuple[Path, ...]
) -> None:
    """Walk un-collapsed segments of ``expanded`` and reject symlinks before confine."""
    if not expanded.is_absolute():
        cur, parts = real_base, expanded.parts
    else:
        cur, parts = Path(expanded.anchor), expanded.parts[1:]
        for root in roots:
            raw_root = Path(os.path.normpath(str(root)))
            if expanded == root or root in expanded.parents:
                cur, parts = root, expanded.parts[len(root.parts) :]
                break
            if expanded == raw_root or raw_root in expanded.parents:
                cur, parts = root, expanded.parts[len(raw_root.parts) :]
                break
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            cur = cur.parent
            continue
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"Refusing symlink in @file attachment: {cur}")


def _token_looks_explicit_path_or_secret(raw_token: str, real_base: Path) -> bool:
    """True if token attempts path traversal, home/abs path, or secret names."""
    if raw_token.startswith(("~", "/", "./", "../")) or ".." in Path(raw_token).parts:
        return True
    if "/" in raw_token or os.sep in raw_token:
        return True
    return _is_sensitive_read_path(raw_token, real_base)


def _trim_sentence_punct(raw_token: str, real_base: Path) -> str:
    """Trim trailing sentence punctuation only if literal doesn't exist and trimmed does."""
    if raw_token.startswith("~") or (real_base / raw_token).exists():
        return raw_token
    trimmed = raw_token.rstrip(_TRAILING_PUNCT)
    if trimmed and trimmed != raw_token and (real_base / trimmed).exists():
        return trimmed
    return raw_token


def _resolve_attachment_target(
    raw_token: str,
    *,
    real_base: Path,
    roots: tuple[Path, ...],
    extra_roots: tuple[Path, ...],
    policy: PolicyConfig,
) -> tuple[Path | None, str | None]:
    """Resolve one `@token` to `(target_path, None)` or `(None, error)`.

    Returns `(None, None)` when the token is clearly a non-file code/mention token
    (e.g. `@dataclass`, `@pytest.mark`) that does not exist anywhere on disk.
    """
    token = _trim_sentence_punct(raw_token, real_base)
    expanded = Path(os.path.expanduser(token))
    un_symlinked_cand = expanded if expanded.is_absolute() else (real_base / expanded)
    exists_or_symlink = os.path.lexists(un_symlinked_cand)
    explicit_path = _token_looks_explicit_path_or_secret(token, real_base)
    if not exists_or_symlink and not explicit_path:
        return (None, None)

    try:
        _refuse_token_symlinks(expanded, real_base, roots)
        target = confine(
            resolve(expanded, real_base), real_base, extra_roots=extra_roots
        )
        refuse_symlink_under_roots(target, roots, "attachment")
    except ValueError as exc:
        return (None, str(exc))

    if _is_sensitive_read_path(token, real_base) or _is_sensitive_read_path(
        str(target), real_base
    ):
        return (None, f"Refused @file attachment: sensitive path {token!r}")

    verdict = decide("read", {"path": str(target)}, policy, cwd=real_base)
    if isinstance(verdict, Deny):
        return (None, verdict.reason)

    if not target.exists():
        return (None, None)
    return (target, None)


def _read_bounded_bytes(
    target: Path, label: str, max_bytes: int
) -> tuple[bytes | None, str | None]:
    """Read regular file bytes safely via O_NOFOLLOW | O_NONBLOCK with byte cap."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        return (None, f"Could not read @{label}: {exc}")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return (None, f"Refused @{label}: not a regular file")
        if st.st_size > max_bytes:
            return (None, f"Refused @{label}: exceeds {max_bytes} byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                return (None, f"Refused @{label}: exceeds {max_bytes} byte limit")
            chunks.append(chunk)
        return (b"".join(chunks), None)
    except OSError as exc:
        return (None, f"Could not read @{label}: {exc}")
    finally:
        os.close(fd)


def _classify_attachment(
    target: Path,
    raw_bytes: bytes,
    label: str,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Return `(inline_text_block, binary_block, error)` for one attachment."""
    suffix = target.suffix.lower()
    if suffix in IMAGE_EXT_FORMATS:
        return (
            None,
            {
                "image": {
                    "format": IMAGE_EXT_FORMATS[suffix],
                    "source": {"bytes": raw_bytes},
                }
            },
            None,
        )
    if suffix in BINARY_DOC_EXT_FORMATS:
        return (
            None,
            {
                "document": {
                    "format": BINARY_DOC_EXT_FORMATS[suffix],
                    "name": sanitize_document_name(target),
                    "source": {"bytes": raw_bytes},
                }
            },
            None,
        )
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return (
            None,
            None,
            f"Unsupported binary file @{label}; supported binary attachments are images ({', '.join(sorted(IMAGE_EXT_FORMATS))}) and docs ({', '.join(sorted(BINARY_DOC_EXT_FORMATS))}).",
        )
    safe_path = sanitize_display(label).replace('"', "'")
    safe_body = text.replace("</attached_file>", "<\\/attached_file>")
    return (
        f'<attached_file path="{safe_path}">\n{safe_body}\n</attached_file>',
        None,
        None,
    )


def _display_label(target: Path, real_base: Path) -> str:
    try:
        return target.relative_to(real_base).as_posix()
    except ValueError:
        return target.as_posix()


def _collect_attachments(
    tokens: list[str], real_base: Path, policy: PolicyConfig
) -> tuple[list[str], list[dict[str, Any]], list[str], str | None]:
    """Resolve, validate, read, and classify all attachment tokens for one turn."""
    roots = tuple(effective_roots(real_base, policy, tool_name="read"))
    extra_roots = tuple(r for r in roots if r != real_base)

    seen_targets: set[Path] = set()
    text_blocks: list[str] = []
    binary_blocks: list[dict[str, Any]] = []
    binary_names: list[str] = []
    total_bytes = 0

    for tok in tokens:
        target, err = _resolve_attachment_target(
            tok,
            real_base=real_base,
            roots=roots,
            extra_roots=extra_roots,
            policy=policy,
        )
        if err is not None:
            return ([], [], [], err)
        if target is None or target in seen_targets:
            continue
        seen_targets.add(target)
        if len(seen_targets) > ATTACHMENT_MAX_COUNT:
            return (
                [],
                [],
                [],
                f"Too many @file attachments (maximum {ATTACHMENT_MAX_COUNT} per turn).",
            )
        label = _display_label(target, real_base)
        raw_bytes, read_err = _read_bounded_bytes(
            target, label, ATTACHMENT_MAX_FILE_BYTES
        )
        if read_err is not None or raw_bytes is None:
            return ([], [], [], read_err or f"Could not read @{label}")
        total_bytes += len(raw_bytes)
        if total_bytes > ATTACHMENT_MAX_TOTAL_BYTES:
            return (
                [],
                [],
                [],
                f"Total @file attachment size exceeds {ATTACHMENT_MAX_TOTAL_BYTES} byte limit.",
            )
        inline, binary, cls_err = _classify_attachment(target, raw_bytes, label)
        if cls_err is not None:
            return ([], [], [], cls_err)
        if inline is not None:
            text_blocks.append(inline)
        elif binary is not None:
            binary_blocks.append(binary)
            binary_names.append(label)
    return (text_blocks, binary_blocks, binary_names, None)


def prepare_turn_prompt(
    raw_ask: str,
    agent_text: str,
    *,
    current_model: str,
    cwd: str | Path | None = None,
    scan_attachments: bool = True,
) -> tuple[str | list[dict[str, Any]] | None, str | None]:
    """Resolve real `@file` tokens in ``raw_ask`` after routing; return `(prompt, abort_msg)`."""
    if not scan_attachments:
        return (agent_text, None)
    tokens = extract_at_tokens(raw_ask)
    if not tokens:
        return (agent_text, None)

    base = Path(cwd) if cwd is not None else Path.cwd()
    real_base = Path(os.path.realpath(base))
    policy, pol_err = _load_read_policy(real_base)
    if pol_err is not None or policy is None:
        return (None, pol_err or "Refused by policy")

    text_blocks, binary_blocks, binary_names, col_err = _collect_attachments(
        tokens, real_base, policy
    )
    if col_err is not None:
        return (None, col_err)

    if binary_blocks and not supports_media(current_model):
        model_label = sanitize_display(current_model)
        files_label = ", ".join(sanitize_display(n) for n in binary_names)
        return (
            None,
            f"Model '{model_label}' does not support binary image/document attachments ({files_label}). Switch models with /model or remove the binary attachment.",
        )

    combined_text = (
        f"{agent_text}\n\n" + "\n\n".join(text_blocks) if text_blocks else agent_text
    )
    if not binary_blocks:
        return (combined_text, None)
    return (validate_content_blocks([{"text": combined_text}, *binary_blocks]), None)
