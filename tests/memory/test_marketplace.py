"""Hermetic tests for marketplaces, safe archive unpack, and lockfile verification (SKILL-03)."""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
from pathlib import PurePosixPath

import httpx
import pytest

from strands_code_cli.memory import marketplace as mp
from strands_code_cli.memory.marketplace import (
    MAX_SKILL_BYTES,
    MAX_SKILL_FILES,
    MAX_TARBALL_BYTES,
    add_marketplace,
    browse_marketplaces,
    compute_skill_dir_hash,
    github_repo_slug,
    install_skill,
    list_marketplaces,
    load_lockfile,
    load_marketplaces,
    parse_github_spec,
    read_github_token,
    remove_installed_skill,
    remove_marketplace,
    sanitize_display,
    sync_installed_skills,
    update_installed_skills,
    update_marketplace,
    valid_namespace,
    verify_installed_marketplace_skills,
)

_SHA_V1 = "1" * 40
_SHA_V2 = "2" * 40


def _build_tar_gz(entries: list[tuple[str, bytes | str]], *, prefix: str = "") -> bytes:
    """Create an in-memory gzipped tarball from (rel_path, content) items."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        if prefix:
            root_info = tarfile.TarInfo(name=prefix.rstrip("/"))
            root_info.type = tarfile.DIRTYPE
            root_info.mode = 0o755
            tf.addfile(root_info)
        for rel, body in entries:
            data = body.encode("utf-8") if isinstance(body, str) else body
            full = f"{prefix.rstrip('/')}/{rel}" if prefix else rel
            info = tarfile.TarInfo(name=full)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _skill_md(name: str, description: str, *, allowed_tools: str = "") -> str:
    extra = f"allowed-tools: {allowed_tools}\n" if allowed_tools else ""
    return (
        f"---\nname: {name}\ndescription: {description}\n{extra}---\n"
        f"# {name}\nUse carefully.\n"
    )


def _github_mock_transport(
    commits: dict[tuple[str, str, str], str],
    tarballs: dict[tuple[str, str, str], bytes],
    *,
    default_branch: str = "main",
    seen_headers: list[tuple[str, dict[str, str]]] | None = None,
    redirect_host: str = "codeload.github.com",
) -> httpx.MockTransport:
    """Hermetic mock transport emulating GitHub repo/commit/tarball + redirect."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen_headers is not None:
            seen_headers.append((str(request.url), dict(request.headers)))
        host = request.url.host
        path = request.url.path
        if host == redirect_host:
            parts = path.strip("/").split("/")
            owner, repo, sha = parts[0], parts[1], parts[-1]
            data = tarballs[(owner, repo, sha)]
            return httpx.Response(
                200,
                content=data,
                headers={"Content-Length": str(len(data))},
            )
        if host != "api.github.com":
            return httpx.Response(404, json={"message": "unexpected host"})
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "repos":
            return httpx.Response(200, json={"default_branch": default_branch})
        if len(parts) == 5 and parts[0] == "repos" and parts[3] == "commits":
            owner, repo, ref = parts[1], parts[2], parts[4]
            sha = commits.get((owner, repo, ref))
            if sha is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"sha": sha})
        if len(parts) == 5 and parts[0] == "repos" and parts[3] == "tarball":
            owner, repo, sha = parts[1], parts[2], parts[4]
            if (owner, repo, sha) not in tarballs:
                return httpx.Response(404, json={"message": "Not Found"})
            location = f"https://{redirect_host}/{owner}/{repo}/legacy.tar.gz/{sha}"
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(404, json={"message": f"unhandled {path}"})

    return httpx.MockTransport(handler)


class TestConftestAndValidation:
    def test_conftest_scrubs_github_tokens(self):
        from tests.conftest import _PROVIDER_ENV_VARS

        assert "GITHUB_TOKEN" in _PROVIDER_ENV_VARS
        assert "GH_TOKEN" in _PROVIDER_ENV_VARS
        assert "GITHUB_TOKEN" not in os.environ
        assert "GH_TOKEN" not in os.environ

    def test_namespace_alias_and_slug_validation(self):
        assert valid_namespace("anthropic-skills") is True
        assert valid_namespace("team1") is True
        assert valid_namespace("local") is False
        assert valid_namespace("all") is False
        assert valid_namespace("Bad_Upper") is False
        assert valid_namespace("../escape") is False
        assert valid_namespace("-leading") is False
        assert github_repo_slug("Anthropic", "skills.sh") == "anthropic--skills-sh"
        assert len(github_repo_slug("org-" * 20, "repo-" * 20)) <= 64

    def test_parse_github_spec_valid_and_rejected(self):
        assert parse_github_spec("owner/repo") == ("owner", "repo", None)
        assert parse_github_spec("owner/repo@v1.2") == ("owner", "repo", "v1.2")
        assert parse_github_spec("https://github.com/owner/repo.git@abc") == (
            "owner",
            "repo",
            "abc",
        )
        bad_specs = (
            "http://github.com/owner/repo",
            "https://evil.example/owner/repo",
            "https://user:pass@github.com/owner/repo",
            "https://github.com/owner/repo?foo=1",
            "owner/../repo",
            "owner/repo@bad\nref",
        )
        for bad in bad_specs:
            with pytest.raises(ValueError):
                parse_github_spec(bad)


class TestMarketplaceRegistryAndCatalogs:
    def test_ships_empty_and_persists_with_restricted_perms(self, tmp_path):
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        assert load_marketplaces(mpath) == {}
        assert list_marketplaces(marketplaces_path=mpath) == []

        catalog_dir = tmp_path / "local-cat"
        (catalog_dir / "skills" / "alpha").mkdir(parents=True)
        (catalog_dir / "skills" / "alpha" / "SKILL.md").write_text(
            _skill_md("alpha", "Alpha helper"), encoding="utf-8"
        )
        cache_dir = tmp_path / "cache"
        entry, discovered = add_marketplace(
            str(catalog_dir),
            name="team",
            marketplaces_path=mpath,
            cache_dir=cache_dir,
        )
        assert entry.name == "team"
        assert entry.kind == "local"
        assert [s.name for s in discovered] == ["alpha"]
        assert (mpath.stat().st_mode & 0o777) == 0o600
        assert (mpath.parent.stat().st_mode & 0o777) == 0o700
        assert [e.name for e in list_marketplaces(marketplaces_path=mpath)] == ["team"]

        assert remove_marketplace("team", marketplaces_path=mpath, cache_dir=cache_dir)
        assert list_marketplaces(marketplaces_path=mpath) == []

    def test_claude_plugin_and_agent_plugin_manifest_discovery(self, tmp_path):
        claude_root = tmp_path / "claude-cat"
        (claude_root / ".claude-plugin").mkdir(parents=True)
        (claude_root / "packages" / "doc" / "pdf").mkdir(parents=True)
        (claude_root / "packages" / "doc" / "pdf" / "SKILL.md").write_text(
            _skill_md("pdf", "PDF parser [beta]"), encoding="utf-8"
        )
        manifest = {
            "name": "official",
            "plugins": [
                {
                    "name": "doc-suite",
                    "source": "./packages/doc",
                    "skills": ["./pdf"],
                },
                {
                    "name": "remote-pack",
                    "source": {
                        "source": "github",
                        "repo": "other/tools",
                        "path": "skills/lint",
                        "ref": "v2",
                    },
                },
            ],
        }
        (claude_root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        skills = mp.discover_catalog_from_tree(
            claude_root,
            marketplace="official",
            source=str(claude_root),
            repo_url=str(claude_root),
        )
        by_name = {s.name: s for s in skills}
        assert by_name["pdf"].subdir == "packages/doc/pdf"
        assert by_name["lint"].repo_url == "https://github.com/other/tools"
        assert by_name["lint"].ref == "v2"

        agent_root = tmp_path / "agent-cat"
        (agent_root / ".agent-plugin").mkdir(parents=True)
        (agent_root / "skills" / "fmt").mkdir(parents=True)
        (agent_root / "skills" / "fmt" / "SKILL.md").write_text(
            _skill_md("fmt", "Formatter"), encoding="utf-8"
        )
        (agent_root / ".agent-plugin" / "marketplace.json").write_text(
            json.dumps({"skills": [{"name": "fmt", "path": "skills/fmt"}]}),
            encoding="utf-8",
        )
        agent_skills = mp.discover_catalog_from_tree(
            agent_root,
            marketplace="team",
            source=str(agent_root),
            repo_url=str(agent_root),
        )
        assert [s.name for s in agent_skills] == ["fmt"]

    def test_root_skill_repo_direct_discovery(self, tmp_path):
        root = tmp_path / "single-skill"
        root.mkdir()
        (root / "SKILL.md").write_text(
            _skill_md("solo", "Root skill"), encoding="utf-8"
        )
        skills = mp.discover_catalog_from_tree(
            root,
            marketplace="org--solo",
            source="org/solo",
            repo_url="https://github.com/org/solo",
        )
        assert len(skills) == 1
        assert skills[0].name == "solo"
        assert skills[0].subdir == "."


class TestRedirectAndLifecycle:
    def test_redirect_strips_authorization_and_blocks_evil_host(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_token_value")
        headers_log: list[tuple[str, dict[str, str]]] = []
        tar = _build_tar_gz(
            [("SKILL.md", _skill_md("solo", "Solo skill"))],
            prefix=f"acme-solo-{_SHA_V1[:7]}",
        )
        transport = _github_mock_transport(
            {("acme", "solo", "main"): _SHA_V1},
            {("acme", "solo", _SHA_V1): tar},
            seen_headers=headers_log,
        )
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            sha, ref = mp.resolve_github_commit("acme", "solo", None, client=client)
            assert sha == _SHA_V1 and ref == "main"
            blob = mp.download_github_tarball("acme", "solo", sha, client=client)
            assert blob == tar

        api_calls = [h for url, h in headers_log if "api.github.com" in url]
        codeload_calls = [h for url, h in headers_log if "codeload.github.com" in url]
        assert all(
            h.get("authorization") == "Bearer ghp_secret_token_value" for h in api_calls
        )
        assert codeload_calls and all("authorization" not in h for h in codeload_calls)

        evil_transport = _github_mock_transport(
            {("acme", "solo", "main"): _SHA_V1},
            {("acme", "solo", _SHA_V1): tar},
            redirect_host="evil.example",
        )
        with httpx.Client(transport=evil_transport, follow_redirects=False) as bad:
            with pytest.raises(ValueError, match="redirect host"):
                mp.download_github_tarball("acme", "solo", _SHA_V1, client=bad)

    def test_end_to_end_install_and_update_scripts_diff(self, tmp_path):
        manifest = {
            "name": "acme-cat",
            "plugins": [{"name": "pack", "source": "./skills", "skills": ["./audit"]}],
        }
        tar_v1 = _build_tar_gz(
            [
                (".claude-plugin/marketplace.json", json.dumps(manifest)),
                (
                    "skills/audit/SKILL.md",
                    _skill_md("audit", "Audit code", allowed_tools="bash"),
                ),
                ("skills/audit/scripts/check.py", "print('v1')\n"),
            ],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        tar_v2 = _build_tar_gz(
            [
                (".claude-plugin/marketplace.json", json.dumps(manifest)),
                ("skills/audit/SKILL.md", _skill_md("audit", "Audit code v2")),
                ("skills/audit/scripts/check.py", "print('v2')\n"),
                ("skills/audit/scripts/extra.sh", "echo hi\n"),
            ],
            prefix=f"acme-skills-{_SHA_V2[:7]}",
        )
        commits = {("acme", "skills", "main"): _SHA_V1}
        tarballs = {("acme", "skills", _SHA_V1): tar_v1}
        transport = _github_mock_transport(commits, tarballs)
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        workdir = tmp_path / "repo"
        workdir.mkdir()

        with httpx.Client(transport=transport, follow_redirects=False) as client:
            add_marketplace(
                "acme/skills",
                name="acme",
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            listed = browse_marketplaces(
                "acme", refresh=False, marketplaces_path=mpath, cache_dir=cdir
            )
            assert [s.name for s in listed] == ["audit"]

            inst = install_skill(
                "acme:audit",
                cwd=workdir,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            lock_v1 = inst.installed[0]
            assert lock_v1.commit_sha == _SHA_V1
            assert lock_v1.script_files == ["scripts/check.py"]
            assert any("scripts/check.py" in w for w in inst.warnings)

            commits[("acme", "skills", "main")] = _SHA_V2
            tarballs[("acme", "skills", _SHA_V2)] = tar_v2
            update_marketplace(
                "acme", marketplaces_path=mpath, cache_dir=cdir, client=client
            )
            upd = update_installed_skills(
                "acme:audit",
                cwd=workdir,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            rec = upd.updated[0]
            assert rec.old_sha == _SHA_V1 and rec.new_sha == _SHA_V2
            assert rec.added_scripts == ["scripts/extra.sh"]
            assert rec.changed_scripts == ["scripts/check.py"]

    def test_tamper_drift_sync_restore_and_remove(self, tmp_path):
        tar = _build_tar_gz(
            [("skills/audit/SKILL.md", _skill_md("audit", "Pinned skill"))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        transport = _github_mock_transport(
            {("acme", "skills", "main"): _SHA_V1},
            {("acme", "skills", _SHA_V1): tar},
        )
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        workdir = tmp_path / "repo"
        workdir.mkdir()

        with httpx.Client(transport=transport, follow_redirects=False) as client:
            install_skill(
                "acme/skills",
                cwd=workdir,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            installed_dir = (
                workdir / mp.MARKETPLACES_SKILLS_REL / "acme--skills" / "audit"
            )
            (installed_dir / "SKILL.md").write_text(
                _skill_md("audit", "Tampered!"), encoding="utf-8"
            )
            verified, warnings = verify_installed_marketplace_skills(
                workdir / mp.MARKETPLACES_SKILLS_REL, workdir / mp.SKILLS_LOCK_REL
            )
            assert verified == []
            assert any("sync" in w for w in warnings)

            synced = sync_installed_skills(cwd=workdir, client=client)
            assert [e.name for e in synced.restored] == ["audit"]
            verified_after, warnings_after = verify_installed_marketplace_skills(
                workdir / mp.MARKETPLACES_SKILLS_REL, workdir / mp.SKILLS_LOCK_REL
            )
            assert [v.name for v in verified_after] == ["audit"]
            assert warnings_after == []

            rem = remove_installed_skill(
                "acme--skills:audit",
                marketplaces_dir=workdir / mp.MARKETPLACES_SKILLS_REL,
                lockfile_path=workdir / mp.SKILLS_LOCK_REL,
            )
            assert rem.removed is True
            assert not installed_dir.exists()
            assert load_lockfile(workdir / mp.SKILLS_LOCK_REL) == {}

    def test_adhoc_owner_repo_install_derives_flat_slug(self, tmp_path):
        tar = _build_tar_gz(
            [("skills/helper/SKILL.md", _skill_md("helper", "Direct helper"))],
            prefix=f"Org-My_Tools-{_SHA_V1[:7]}",
        )
        transport = _github_mock_transport(
            {("Org", "My_Tools", "v1"): _SHA_V1},
            {("Org", "My_Tools", _SHA_V1): tar},
        )
        workdir = tmp_path / "repo"
        workdir.mkdir()
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            outcome = install_skill(
                "Org/My_Tools@v1",
                cwd=workdir,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
        assert [e.namespace for e in outcome.installed] == ["org--my-tools"]
        assert (
            workdir
            / mp.MARKETPLACES_SKILLS_REL
            / "org--my-tools"
            / "helper"
            / "SKILL.md"
        ).is_file()


class TestMarketplaceSecurityGuards:
    def test_tarball_rejects_symlink_hardlink_device_zipslip_gitmodules(self, tmp_path):
        staging = tmp_path / "stage"

        def _make_special_tar(modifier) -> bytes:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tf:
                skill_data = _skill_md("evil", "Bad").encode("utf-8")
                ok = tarfile.TarInfo(name="evil/SKILL.md")
                ok.size = len(skill_data)
                tf.addfile(ok, io.BytesIO(skill_data))
                modifier(tf)
            return buf.getvalue()

        def add_sym(tf):
            info = tarfile.TarInfo(name="evil/references/leak.md")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)

        def add_hard(tf):
            info = tarfile.TarInfo(name="evil/hard.md")
            info.type = tarfile.LNKTYPE
            info.linkname = "evil/SKILL.md"
            tf.addfile(info)

        def add_fifo(tf):
            info = tarfile.TarInfo(name="evil/pipe")
            info.type = tarfile.FIFOTYPE
            tf.addfile(info)

        def add_zipslip(tf):
            data = b"pwned"
            info = tarfile.TarInfo(name="../../outside.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        def add_abs(tf):
            data = b"pwned"
            info = tarfile.TarInfo(name="/etc/evil")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        def add_gitmodules(tf):
            data = b"[submodule]"
            info = tarfile.TarInfo(name="evil/.gitmodules")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        for mod in (
            add_sym,
            add_hard,
            add_fifo,
            add_zipslip,
            add_abs,
            add_gitmodules,
        ):
            stage_case = staging / mod.__name__
            stage_case.mkdir(parents=True)
            with pytest.raises(ValueError):
                mp.extract_tarball_subdir_safe(
                    _make_special_tar(mod),
                    subdir="evil",
                    skill_name="evil",
                    staging_dir=stage_case,
                )

    def test_tarball_download_and_unpack_caps_enforced(self, tmp_path):
        huge_hdr = httpx.MockTransport(
            lambda _r: httpx.Response(
                200,
                content=b"ok",
                headers={"Content-Length": str(MAX_TARBALL_BYTES + 1)},
            )
        )
        with httpx.Client(transport=huge_hdr, follow_redirects=False) as client:
            with pytest.raises(ValueError, match="size limit"):
                mp.download_github_tarball("acme", "repo", _SHA_V1, client=client)

        too_many_entries = [("big/SKILL.md", _skill_md("big", "Too many files"))] + [
            (f"big/references/f{i}.txt", "x") for i in range(MAX_SKILL_FILES)
        ]
        tar_many = _build_tar_gz(too_many_entries)
        with pytest.raises(ValueError, match="file count"):
            mp.extract_tarball_subdir_safe(
                tar_many,
                subdir="big",
                skill_name="big",
                staging_dir=tmp_path / "many",
            )

        tar_big_bytes = _build_tar_gz(
            [
                ("big/SKILL.md", _skill_md("big", "Huge blob")),
                ("big/assets/blob.bin", b"a" * (MAX_SKILL_BYTES + 10)),
            ]
        )
        with pytest.raises(ValueError, match="size limit"):
            mp.extract_tarball_subdir_safe(
                tar_big_bytes,
                subdir="big",
                skill_name="big",
                staging_dir=tmp_path / "bytes",
            )

    def test_strict_skill_validation_and_rollback_on_failed_update(self, tmp_path):
        bad_tar = _build_tar_gz(
            [("other/SKILL.md", _skill_md("mismatch", "Name mismatch"))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        with pytest.raises(ValueError):
            mp.extract_tarball_subdir_safe(
                bad_tar,
                subdir="other",
                skill_name="other",
                staging_dir=tmp_path / "strict",
            )

        # Rollback preserves prior installed version on bad v2 archive
        good_v1 = _build_tar_gz(
            [("skills/alpha/SKILL.md", _skill_md("alpha", "Safe v1"))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        bad_v2 = _build_tar_gz(
            [
                ("skills/alpha/SKILL.md", _skill_md("mismatch", "Corrupt v2")),
            ],
            prefix=f"acme-skills-{_SHA_V2[:7]}",
        )
        commits = {("acme", "skills", "main"): _SHA_V1}
        tarballs = {("acme", "skills", _SHA_V1): good_v1}
        transport = _github_mock_transport(commits, tarballs)
        workdir = tmp_path / "ws"
        workdir.mkdir()
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            add_marketplace(
                "acme/skills",
                name="acme",
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            install_skill(
                "acme:alpha",
                cwd=workdir,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            commits[("acme", "skills", "main")] = _SHA_V2
            tarballs[("acme", "skills", _SHA_V2)] = bad_v2
            update_marketplace(
                "acme", marketplaces_path=mpath, cache_dir=cdir, client=client
            )
            with pytest.raises(ValueError):
                update_installed_skills(
                    "acme:alpha",
                    cwd=workdir,
                    marketplaces_path=mpath,
                    cache_dir=cdir,
                    client=client,
                )
        installed_dir = workdir / mp.MARKETPLACES_SKILLS_REL / "acme" / "alpha"
        assert "Safe v1" in (installed_dir / "SKILL.md").read_text(encoding="utf-8")

    def test_symlinked_local_catalog_config_lockfile_and_installed_fail_closed(
        self, tmp_path
    ):
        real_skill = tmp_path / "cat" / "skills" / "alpha"
        real_skill.mkdir(parents=True)
        (real_skill / "SKILL.md").write_text(_skill_md("alpha", "Ok"), encoding="utf-8")
        (real_skill / "leak.txt").symlink_to(tmp_path / "outside.secret")
        with pytest.raises(ValueError, match="symlink"):
            mp.copy_local_dir_safe(
                real_skill, skill_name="alpha", staging_dir=tmp_path / "st"
            )

        sym_yaml = tmp_path / "sym.yaml"
        sym_yaml.symlink_to(tmp_path / "target.yaml")
        with pytest.raises(ValueError, match="symlink"):
            load_marketplaces(sym_yaml)

        sym_lock = tmp_path / "sym-lock.json"
        sym_lock.symlink_to(tmp_path / "target.json")
        with pytest.raises(ValueError, match="symlink"):
            load_lockfile(sym_lock)

        ws = tmp_path / "ws"
        sym_skill = ws / mp.MARKETPLACES_SKILLS_REL / "acme" / "linked"
        sym_skill.parent.mkdir(parents=True)
        target = tmp_path / "outside-skill"
        target.mkdir()
        (target / "SKILL.md").write_text(_skill_md("linked", "Sym"), encoding="utf-8")
        sym_skill.symlink_to(target)
        verified, warnings = verify_installed_marketplace_skills(
            ws / mp.MARKETPLACES_SKILLS_REL, ws / mp.SKILLS_LOCK_REL
        )
        assert verified == []
        assert any("symlink" in w.lower() for w in warnings)

    def test_token_and_display_sanitization(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", "   \n  ")
        assert read_github_token() is None
        monkeypatch.setenv("GITHUB_TOKEN", "bad\x1b[31m\r\ntoken")
        assert read_github_token() is None
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", " ghp_valid123 ")
        assert read_github_token() == "ghp_valid123"

        cleaned = sanitize_display("\x1b[31mEvil\x1b[0m [red]note[/red]\r\n\tline2")
        assert "\x1b" not in cleaned
        assert "\r" not in cleaned and "\n" not in cleaned
        assert "[red]note[/red]" in cleaned

        # Deterministic hash refuses symlink
        d = tmp_path / "s"
        d.mkdir()
        (d / "SKILL.md").write_text(_skill_md("s", "Ok"), encoding="utf-8")
        (d / "bad").symlink_to(d / "SKILL.md")
        with pytest.raises(ValueError, match="symlink"):
            compute_skill_dir_hash(d)


class TestPhase18SecurityAuditHardening:
    def test_lockfile_rejects_traversal_mismatch_bad_sha_and_hash(self, tmp_path):
        base_valid = {
            "namespace": "acme",
            "name": "audit",
            "source": "acme/skills",
            "repo_url": "https://github.com/acme/skills",
            "subdir": "skills/audit",
            "ref": "main",
            "commit_sha": _SHA_V1,
            "computed_hash": f"sha256:{'a' * 64}",
        }
        cases = (
            {"namespace": "../../tmp/pwn"},
            {"name": "../evil"},
            {"name": "bad--slug"},
            {"commit_sha": "not-a-sha"},
            {"computed_hash": "md5:1234"},
            {"subdir": "../../etc"},
        )
        for pos, patch_fields in enumerate(cases):
            entry = {**base_valid, **patch_fields}
            lp = tmp_path / f"lock-{pos}.json"
            lp.write_text(
                json.dumps({"version": 1, "skills": {"acme:audit": entry}}),
                encoding="utf-8",
            )
            with pytest.raises(ValueError):
                load_lockfile(lp)

        mismatch = tmp_path / "lock-mismatch.json"
        mismatch.write_text(
            json.dumps({"version": 1, "skills": {"other:audit": base_valid}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="mismatch"):
            load_lockfile(mismatch)

    def test_sync_refuses_unregistered_local_repo_url_and_mismatched_hash_before_write(
        self, tmp_path
    ):
        ws = tmp_path / "ws"
        host_secret = tmp_path / "host-secret"
        host_secret.mkdir(parents=True)
        (host_secret / "SKILL.md").write_text(
            _skill_md("steal", "Exfil"), encoding="utf-8"
        )
        secret_hash = compute_skill_dir_hash(host_secret)
        lock_path = ws / mp.SKILLS_LOCK_REL
        mp.save_lockfile(
            lock_path,
            {
                "evil:steal": mp.LockEntry(
                    namespace="evil",
                    name="steal",
                    source=str(host_secret),
                    repo_url=str(host_secret),
                    subdir=".",
                    ref="local",
                    commit_sha=_SHA_V1,
                    computed_hash=secret_hash,
                )
            },
        )
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        with pytest.raises(ValueError, match="unregistered local path"):
            sync_installed_skills(cwd=ws, marketplaces_path=mpath)
        assert not (ws / mp.MARKETPLACES_SKILLS_REL / "evil" / "steal").exists()

        # Registered local catalog syncs when unchanged, and hash-mismatched GitHub sync leaves dest untouched
        ws2 = tmp_path / "ws2"
        tar_good = _build_tar_gz(
            [("skills/audit/SKILL.md", _skill_md("audit", "Pinned"))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        tar_evil = _build_tar_gz(
            [("skills/audit/SKILL.md", _skill_md("audit", "Upstream swapped!"))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        tarballs = {("acme", "skills", _SHA_V1): tar_good}
        transport = _github_mock_transport(
            {("acme", "skills", "main"): _SHA_V1}, tarballs
        )
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            install_skill(
                "acme/skills", cwd=ws2, marketplaces_path=mpath, client=client
            )
            installed_md = (
                ws2 / mp.MARKETPLACES_SKILLS_REL / "acme--skills" / "audit" / "SKILL.md"
            )
            installed_md.write_text(
                _skill_md("audit", "Local tamper"), encoding="utf-8"
            )
            tarballs[("acme", "skills", _SHA_V1)] = tar_evil
            with pytest.raises(ValueError, match="Hash mismatch"):
                sync_installed_skills(cwd=ws2, marketplaces_path=mpath, client=client)
            assert "Local tamper" in installed_md.read_text(encoding="utf-8")

    def test_redirect_port_json_nan_network_error_and_update_errors(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_CanaryDoNotLeak999999999999")

        port_transport = httpx.MockTransport(
            lambda _r: httpx.Response(
                302,
                headers={
                    "Location": f"https://codeload.github.com:8443/a/b/tar/{_SHA_V1}"
                },
            )
        )
        with httpx.Client(transport=port_transport, follow_redirects=False) as client:
            with pytest.raises(ValueError, match="redirect host"):
                mp.download_github_tarball("a", "b", _SHA_V1, client=client)

        nan_transport = httpx.MockTransport(
            lambda _r: httpx.Response(200, content=b'{"sha": NaN}')
        )
        with httpx.Client(transport=nan_transport, follow_redirects=False) as client:
            with pytest.raises(ValueError, match="Non-standard JSON"):
                mp.resolve_github_commit("a", "b", "main", client=client)

        def _offline(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        with httpx.Client(
            transport=httpx.MockTransport(_offline), follow_redirects=False
        ) as client:
            with pytest.raises(ValueError, match="offline or unreachable") as exc_info:
                mp.resolve_github_commit("a", "b", "main", client=client)
            assert "ghp_Canary" not in str(exc_info.value)

        with pytest.raises(ValueError, match="Invalid GitHub"):
            mp.resolve_github_commit("../bad", "repo", "main")
        with pytest.raises(ValueError, match="Unknown marketplace"):
            update_marketplace(
                "nonexistent", marketplaces_path=tmp_path / "missing.yaml"
            )

    def test_symlinked_agent_parent_and_cwd_dotenv_blocked(self, tmp_path, monkeypatch):
        real_agent = tmp_path / "real_agent"
        (real_agent / "skills-marketplaces" / "acme" / "demo").mkdir(parents=True)
        sym_agent = tmp_path / "ws" / ".agent"
        sym_agent.parent.mkdir(parents=True)
        sym_agent.symlink_to(real_agent)

        verified, warnings = verify_installed_marketplace_skills(
            sym_agent / "skills-marketplaces", sym_agent / "skills-lock.json"
        )
        assert verified == []
        assert any("symlink" in w.lower() for w in warnings)

        dotenv_dir = tmp_path / "untrusted_cwd"
        dotenv_dir.mkdir()
        (dotenv_dir / ".env").write_text(
            "GITHUB_TOKEN=ghp_PoisonDotEnv0000000000\n", encoding="utf-8"
        )
        from strands_code_cli.entry.first_run import disable_cwd_dotenv

        monkeypatch.chdir(dotenv_dir)
        disable_cwd_dotenv()
        import dotenv

        assert dotenv.load_dotenv() is False
        assert read_github_token() is None


class TestPhase18NyquistMarketplaceBranches:
    def test_defaults_sanitization_validation_and_atomic_write_cleanup(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "platformdirs.user_config_dir", lambda _app: str(tmp_path / "cfg")
        )
        monkeypatch.setattr(
            "platformdirs.user_cache_dir", lambda _app: str(tmp_path / "cache")
        )
        assert mp.default_marketplaces_path() == tmp_path / "cfg" / "marketplaces.yaml"
        assert mp.default_cache_dir() == tmp_path / "cache" / "marketplaces"

        truncated = sanitize_display("a" * 50, max_len=20)
        assert len(truncated) <= 20 and truncated.endswith("...")

        for bad_ref in ("", "a..b", "bad ref", "a?b", "a@{0}", "\x01"):
            with pytest.raises(ValueError):
                mp._validate_git_ref(bad_ref)
        for bad_spec in ("", " acme/repo "):
            with pytest.raises(ValueError):
                parse_github_spec(bad_spec)

        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        sym_parent = tmp_path / "sym_parent"
        sym_parent.symlink_to(real_dir)
        with pytest.raises(ValueError, match="symlink parent"):
            mp._refuse_symlink(sym_parent / "file.txt", "cfg")
        with pytest.raises(ValueError, match="symlink directory"):
            mp._refuse_symlink_chain(sym_parent, "a")
        seg = real_dir / "seg"
        seg.symlink_to(tmp_path)
        with pytest.raises(ValueError, match="symlink path"):
            mp._refuse_symlink_chain(real_dir, "seg")

        def _boom(_src, _dst):
            raise OSError("boom")

        monkeypatch.setattr(os, "replace", _boom)
        with pytest.raises(OSError, match="boom"):
            mp._atomic_write_text(tmp_path / "x.txt", "hi")
        assert list(tmp_path.glob(".x.txt.*.tmp")) == []

    def test_registry_and_cache_malformed_inputs(self, tmp_path):
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("", encoding="utf-8")
        assert load_marketplaces(empty_yaml) == {}

        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed marketplaces registry"):
            load_marketplaces(list_yaml)

        bad_map = tmp_path / "bad_map.yaml"
        bad_map.write_text("marketplaces: []\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed 'marketplaces' mapping"):
            load_marketplaces(bad_map)

        mixed_yaml = tmp_path / "mixed.yaml"
        mixed_yaml.write_text(
            "marketplaces:\n"
            "  local: {kind: github, source: a/b}\n"
            "  badtype: not-a-dict\n"
            "  badkind: {kind: svn, source: a/b}\n"
            "  emptysrc: {kind: github, source: ''}\n"
            "  ok: {kind: github, source: acme/skills}\n",
            encoding="utf-8",
        )
        assert list(load_marketplaces(mixed_yaml)) == ["ok"]

        cdir = tmp_path / "cache"
        assert mp.load_cached_catalog("acme", cdir) == []
        cdir.mkdir()
        (cdir / "acme.json").write_text("[]", encoding="utf-8")
        assert mp.load_cached_catalog("acme", cdir) == []
        (cdir / "acme.json").write_text(
            json.dumps(
                {
                    "skills": [
                        "not-a-dict",
                        {"name": "../bad", "marketplace": "acme"},
                        {"name": "ok", "marketplace": "local"},
                        {"name": "good", "marketplace": "acme", "description": "Valid"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert [s.name for s in mp.load_cached_catalog("acme", cdir)] == ["good"]

    def test_transport_redirects_caps_errors_and_client_factory(self, monkeypatch):
        client = mp.make_marketplace_client()
        assert client.follow_redirects is False
        client.close()

        for bad_loc in (
            "",
            "https://codeload.github.com/a b",
            "https://codeload.github.com/\x07",
        ):
            with pytest.raises(ValueError, match="Invalid redirect Location"):
                mp._validate_tarball_redirect_url(bad_loc)

        monkeypatch.setattr(mp, "MAX_API_JSON_BYTES", 32)
        api_responses = {
            "/r302": httpx.Response(
                302, headers={"Location": "https://api.github.com/x"}
            ),
            "/r404": httpx.Response(404),
            "/rbig": httpx.Response(200, content=b'{"payload": "' + b"x" * 30 + b'"}'),
            "/rlist": httpx.Response(200, content=b"[]"),
            "/repos/missing-branch/repo": httpx.Response(200, json={}),
            "/repos/badsha/repo": httpx.Response(200, json={"default_branch": "main"}),
            "/repos/badsha/repo/commits/main": httpx.Response(
                200, json={"sha": "short"}
            ),
        }
        api_client = httpx.Client(
            transport=httpx.MockTransport(lambda req: api_responses[req.url.path]),
            follow_redirects=False,
        )
        for path in ("/r302", "/r404", "/rbig", "/rlist"):
            with pytest.raises(ValueError):
                mp._github_get_json(api_client, f"https://api.github.com{path}")
        with pytest.raises(ValueError, match="default_branch"):
            mp.resolve_github_commit("missing-branch", "repo", None, client=api_client)
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            mp.resolve_github_commit("badsha", "repo", None, client=api_client)
        api_client.close()

        with pytest.raises(ValueError, match="Invalid commit SHA"):
            mp.download_github_tarball("acme", "skills", "not-a-sha")

        def _tar_handler(req: httpx.Request) -> httpx.Response:
            if (
                req.url.path.endswith(f"/{_SHA_V2}")
                and req.url.host == "api.github.com"
            ):
                return httpx.Response(404)
            if req.url.host == "api.github.com":
                return httpx.Response(
                    302,
                    headers={
                        "Location": f"https://codeload.github.com/acme/skills/{_SHA_V1}"
                    },
                )
            if req.url.host == "codeload.github.com":
                return httpx.Response(
                    302, headers={"Location": "https://codeload.github.com/loop"}
                )
            return httpx.Response(404)

        dl_client = httpx.Client(
            transport=httpx.MockTransport(_tar_handler), follow_redirects=False
        )
        with pytest.raises(ValueError, match="failed"):
            mp.download_github_tarball("acme", "skills", _SHA_V2, client=dl_client)
        with pytest.raises(ValueError, match="Nested redirects"):
            mp.download_github_tarball("acme", "skills", _SHA_V1, client=dl_client)
        dl_client.close()

        class _ChunkStream(httpx.SyncByteStream):
            def __iter__(self):
                yield b"a" * 10
                yield b"b" * 10

        stream_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _req: httpx.Response(200, stream=_ChunkStream())
            ),
            follow_redirects=False,
        )
        with pytest.raises(ValueError, match="exceeds size limit"):
            mp.download_github_tarball(
                "acme", "skills", _SHA_V1, client=stream_client, max_bytes=12
            )
        stream_client.close()

        def _err_handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        err_client = httpx.Client(
            transport=httpx.MockTransport(_err_handler), follow_redirects=False
        )
        with pytest.raises(ValueError, match="offline or unreachable"):
            mp.download_github_tarball("acme", "skills", _SHA_V1, client=err_client)
        err_client.close()

    def test_tarball_safe_unpack_edge_branches(self, tmp_path):
        for bad in ("", "a\x00b", "a\\b"):
            with pytest.raises(ValueError):
                mp._normalize_rel_posix(bad)

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pax = tarfile.TarInfo("pax_global_header")
            pax.type = tarfile.XGLTYPE
            tf.addfile(pax, io.BytesIO(b""))
            dot = tarfile.TarInfo("skills/demo")
            dot.type = tarfile.DIRTYPE
            tf.addfile(dot)
            md = _skill_md("demo", "Demo.").encode("utf-8")
            info = tarfile.TarInfo("skills/demo/SKILL.md")
            info.size = len(md)
            tf.addfile(info, io.BytesIO(md))
            readme = b"# Readme\n"
            r_info = tarfile.TarInfo("README.md")
            r_info.size = len(readme)
            tf.addfile(r_info, io.BytesIO(readme))

        staged, scripts = mp.extract_tarball_subdir_safe(
            buf.getvalue(),
            subdir="skills/demo",
            skill_name="demo",
            staging_dir=tmp_path / "st1",
        )
        assert (staged / "SKILL.md").is_file() and scripts == []

        skills_top_tar = _build_tar_gz(
            [("skills/solo/SKILL.md", _skill_md("solo", "Solo."))]
        )
        staged2, _ = mp.extract_tarball_subdir_safe(
            skills_top_tar,
            subdir="skills/solo",
            skill_name="solo",
            staging_dir=tmp_path / "st2",
        )
        assert (staged2 / "SKILL.md").is_file()

        with pytest.raises(ValueError, match="not found in archive"):
            mp.extract_tarball_subdir_safe(
                skills_top_tar,
                subdir="missing",
                skill_name="solo",
                staging_dir=tmp_path / "st3",
            )

        weird = tarfile.TarInfo("weird")
        weird.type = tarfile.XHDTYPE
        with pytest.raises(ValueError, match="Unsupported archive entry"):
            mp._validate_tar_member(weird)

        sym_skill = tmp_path / "sym_skill"
        (sym_skill / "scripts").mkdir(parents=True)
        sym_target = tmp_path / "evil_target.py"
        sym_target.write_text("print('hi')\n", encoding="utf-8")
        (sym_skill / "scripts" / "evil.py").symlink_to(sym_target)
        with pytest.raises(ValueError, match="Symlink inside scripts"):
            mp._collect_script_files(sym_skill)

        with pytest.raises(ValueError, match="file count limit"):
            mp._write_staged_files(
                [(PurePosixPath("a.txt"), b"1"), (PurePosixPath("b.txt"), b"2")],
                skill_name="demo",
                staging_dir=tmp_path / "st4",
                max_files=1,
                max_bytes=100,
            )
        with pytest.raises(ValueError, match="unpacked size limit"):
            mp._write_staged_files(
                [(PurePosixPath("a.txt"), b"12345")],
                skill_name="demo",
                staging_dir=tmp_path / "st5",
                max_files=10,
                max_bytes=3,
            )
        with pytest.raises(ValueError, match="Illegal skill relative file path"):
            mp._write_staged_files(
                [(PurePosixPath("."), b"x")],
                skill_name="demo",
                staging_dir=tmp_path / "st6",
                max_files=10,
                max_bytes=100,
            )

    def test_local_dir_safe_copy_and_hash_edge_branches(self, tmp_path):
        with pytest.raises(ValueError, match="invalid or a symlink"):
            mp.copy_local_dir_safe(
                tmp_path / "missing", skill_name="demo", staging_dir=tmp_path / "st"
            )

        empty_dir = tmp_path / "empty_local"
        empty_dir.mkdir()
        with pytest.raises(ValueError, match="empty"):
            mp.copy_local_dir_safe(
                empty_dir, skill_name="demo", staging_dir=tmp_path / "st"
            )

        sym_sub_dir = tmp_path / "sym_sub"
        sym_sub_dir.mkdir()
        (sym_sub_dir / "inner").symlink_to(tmp_path)
        with pytest.raises(ValueError, match="symlink in local"):
            mp.copy_local_dir_safe(
                sym_sub_dir, skill_name="demo", staging_dir=tmp_path / "st"
            )

        fifo_dir = tmp_path / "fifo_dir"
        fifo_dir.mkdir()
        os.mkfifo(fifo_dir / "pipe")
        with pytest.raises(ValueError, match="non-regular"):
            mp.copy_local_dir_safe(
                fifo_dir, skill_name="demo", staging_dir=tmp_path / "st"
            )
        with pytest.raises(ValueError, match="non-regular"):
            compute_skill_dir_hash(fifo_dir)

        gm_dir = tmp_path / "gm_dir"
        gm_dir.mkdir()
        (gm_dir / ".gitmodules").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="submodules"):
            mp.copy_local_dir_safe(
                gm_dir, skill_name="demo", staging_dir=tmp_path / "st"
            )

        capped = tmp_path / "capped"
        capped.mkdir()
        (capped / "SKILL.md").write_text(_skill_md("demo", "Demo."), encoding="utf-8")
        (capped / "extra.txt").write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="file count limit"):
            mp.copy_local_dir_safe(
                capped, skill_name="demo", staging_dir=tmp_path / "st", max_files=1
            )
        with pytest.raises(ValueError, match="unpacked size limit"):
            mp.copy_local_dir_safe(
                capped, skill_name="demo", staging_dir=tmp_path / "st", max_bytes=4
            )

        with pytest.raises(ValueError, match="missing skill dir"):
            compute_skill_dir_hash(tmp_path / "nonexistent")
        with pytest.raises(ValueError, match="symlink dir"):
            compute_skill_dir_hash(sym_sub_dir)

    def test_lockfile_and_manifest_discovery_variants(self, tmp_path, monkeypatch):
        ver_lock = tmp_path / "ver.json"
        ver_lock.write_text('{"version": 99, "skills": {}}', encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported lockfile"):
            load_lockfile(ver_lock)

        bad_map_lock = tmp_path / "badmap.json"
        bad_map_lock.write_text('{"version": 1, "skills": []}', encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed 'skills' map"):
            load_lockfile(bad_map_lock)

        bad_entry_lock = tmp_path / "badentry.json"
        bad_entry_lock.write_text(
            '{"version": 1, "skills": {"acme:x": "bad"}}', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Malformed lockfile entry"):
            load_lockfile(bad_entry_lock)

        assert mp._join_rel_posix("skills", ".") == "skills"
        assert mp._skill_meta_from_dir(
            tmp_path / "no_md", fallback_name="fb", fallback_desc="fd"
        ) == (
            "fb",
            "fd",
        )
        root_md_dir = tmp_path / "root_md"
        root_md_dir.mkdir()
        (root_md_dir / "SKILL.md").write_text(
            _skill_md("demo", "Root"), encoding="utf-8"
        )
        assert mp._skill_meta_from_dir(
            root_md_dir, fallback_name="fb", fallback_desc="fd", allow_root_name=True
        ) == ("demo", "Root")

        assert (
            mp._resolve_external_source_dict(
                {"source": "gitlab", "repo": "a/b"},
                fallback_name="x",
                fallback_desc="",
                marketplace="m",
                default_ref=None,
            )
            is None
        )
        assert (
            mp._resolve_external_source_dict(
                {"source": "github"},
                fallback_name="x",
                fallback_desc="",
                marketplace="m",
                default_ref=None,
            )
            is None
        )

        with pytest.raises(ValueError, match="Catalog root"):
            mp.discover_catalog_from_tree(
                tmp_path / "missing_tree", marketplace="m", source="s", repo_url="r"
            )

        bad_manifest = tmp_path / "bad_manifest"
        (bad_manifest / ".claude-plugin").mkdir(parents=True)
        (bad_manifest / ".claude-plugin" / "marketplace.json").write_text(
            "[]", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Malformed marketplace manifest"):
            mp.discover_catalog_from_tree(
                bad_manifest, marketplace="m", source="s", repo_url="r"
            )

        root_plug = tmp_path / "root_plug"
        (root_plug / ".claude-plugin").mkdir(parents=True)
        (root_plug / "SKILL.md").write_text(
            _skill_md("root-skill", "Root plug"), encoding="utf-8"
        )
        (root_plug / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "plugins": [
                        "bad",
                        {"name": "rootpkg", "source": ".", "description": "Root"},
                        {"name": "miss", "source": "./nope"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        root_found = mp.discover_catalog_from_tree(
            root_plug,
            marketplace="rootcat",
            source="s",
            repo_url="https://github.com/a/b",
        )
        assert [s.name for s in root_found] == ["root-skill"]

        sub_plug = tmp_path / "sub_plug"
        (sub_plug / ".claude-plugin").mkdir(parents=True)
        (sub_plug / "pack" / "skills" / "sub").mkdir(parents=True)
        (sub_plug / "pack" / "skills" / "sub" / "SKILL.md").write_text(
            _skill_md("sub", "Sub"), encoding="utf-8"
        )
        (sub_plug / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "pack", "source": "./pack"}]}),
            encoding="utf-8",
        )
        assert [
            s.name
            for s in mp.discover_catalog_from_tree(
                sub_plug,
                marketplace="subcat",
                source="s",
                repo_url="https://github.com/a/b",
            )
        ] == ["sub"]

        flat_tree = tmp_path / "flat_tree"
        (flat_tree / ".agent-plugin").mkdir(parents=True)
        (flat_tree / "skills" / "one").mkdir(parents=True)
        (flat_tree / "skills" / "one" / "SKILL.md").write_text(
            _skill_md("one", "One"), encoding="utf-8"
        )
        (flat_tree / ".agent-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "skills": [
                        "skills/one",
                        {
                            "name": "ext",
                            "description": "Ext",
                            "source": {
                                "source": "github",
                                "repo": "acme/ext",
                                "path": "skills/ext",
                            },
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        flat_found = mp.discover_catalog_from_tree(
            flat_tree, marketplace="flat", source="s", repo_url="https://github.com/a/b"
        )
        assert [s.name for s in flat_found] == ["one", "ext"]

        monkeypatch.setattr(mp, "MAX_SKILL_BYTES", 10)
        oversized_tar = _build_tar_gz(
            [("skills/big/SKILL.md", _skill_md("big", "Too big for tiny limit"))]
        )
        with pytest.raises(ValueError, match="Catalog metadata file exceeds limit"):
            mp.discover_catalog_from_tarball(
                oversized_tar,
                marketplace="m",
                source="s",
                repo_url="https://github.com/a/b",
            )

    def test_local_catalog_install_sync_and_atomic_swap_rollback(
        self, tmp_path, monkeypatch
    ):
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        not_dir = tmp_path / "file.txt"
        not_dir.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="non-symlink dir"):
            add_marketplace(str(not_dir), marketplaces_path=mpath, cache_dir=cdir)

        local_cat = tmp_path / "local_cat"
        (local_cat / ".agent-plugin").mkdir(parents=True)
        (local_cat / "skills" / "alpha").mkdir(parents=True)
        (local_cat / "skills" / "alpha" / "SKILL.md").write_text(
            _skill_md("alpha", "Alpha."), encoding="utf-8"
        )
        (local_cat / ".agent-plugin" / "marketplace.json").write_text(
            json.dumps({"skills": ["skills/alpha"]}), encoding="utf-8"
        )
        add_marketplace(
            str(local_cat), name="localcat", marketplaces_path=mpath, cache_dir=cdir
        )
        assert "localcat" in update_marketplace(
            None, marketplaces_path=mpath, cache_dir=cdir
        )
        with pytest.raises(ValueError, match="Unknown marketplace"):
            browse_marketplaces("unknown", marketplaces_path=mpath, cache_dir=cdir)
        assert [
            s.name
            for s in browse_marketplaces(
                "localcat", refresh=True, marketplaces_path=mpath, cache_dir=cdir
            )
        ] == ["alpha"]
        assert [
            s.name
            for s in browse_marketplaces(
                None, refresh=True, marketplaces_path=mpath, cache_dir=cdir
            )
        ] == ["alpha"]
        assert (
            remove_marketplace("nope", marketplaces_path=mpath, cache_dir=cdir) is False
        )

        ws = tmp_path / "ws"
        ws.mkdir()
        with pytest.raises(ValueError, match="not found in marketplace"):
            install_skill(
                "localcat:missing", cwd=ws, marketplaces_path=mpath, cache_dir=cdir
            )
        with pytest.raises(ValueError, match="non-symlink dir"):
            install_skill(str(not_dir), cwd=ws, marketplaces_path=mpath, cache_dir=cdir)
        with pytest.raises(ValueError, match="No matching installable"):
            install_skill(
                str(local_cat),
                skill_filter="nope",
                cwd=ws,
                marketplaces_path=mpath,
                cache_dir=cdir,
            )

        ws2 = tmp_path / "ws2"
        ws2.mkdir()
        direct = install_skill(
            str(local_cat),
            skill_filter="alpha",
            cwd=ws2,
            marketplaces_path=mpath,
            cache_dir=cdir,
        )
        assert direct.installed[0].name == "alpha"

        outcome = install_skill(
            "localcat:alpha", cwd=ws, marketplaces_path=mpath, cache_dir=cdir
        )
        assert outcome.installed[0].namespaced == "localcat:alpha"
        installed_md = (
            ws / mp.MARKETPLACES_SKILLS_REL / "localcat" / "alpha" / "SKILL.md"
        )
        installed_md.write_text(_skill_md("alpha", "Tampered."), encoding="utf-8")
        sync1 = sync_installed_skills(cwd=ws, marketplaces_path=mpath)
        assert [e.namespaced for e in sync1.restored] == ["localcat:alpha"]
        sync2 = sync_installed_skills(cwd=ws, marketplaces_path=mpath)
        assert sync2.verified == ["localcat:alpha"]

        dest = ws / ".agent" / "skills-marketplaces" / "localcat" / "swap"
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text("orig", encoding="utf-8")
        stale_bak = dest.with_name(f".swap.bak-{os.getpid()}")
        stale_bak.mkdir()
        (stale_bak / "old.txt").write_text("old", encoding="utf-8")
        staged = tmp_path / "staged"
        staged.mkdir()
        (staged / "SKILL.md").write_text("new", encoding="utf-8")

        def _move_fail(_src, _dst):
            raise OSError("disk full")

        monkeypatch.setattr(shutil, "move", _move_fail)
        with pytest.raises(OSError, match="disk full"):
            mp._atomic_swap_skill_dir(staged, dest)
        assert (dest / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "orig" and not stale_bak.exists()

    def test_update_sync_remove_and_verify_edge_branches(self, tmp_path):
        mpath = tmp_path / "cfg" / "marketplaces.yaml"
        cdir = tmp_path / "cache"
        ws = tmp_path / "ws"
        ws.mkdir()

        tar_v1 = _build_tar_gz(
            [("skills/demo/SKILL.md", _skill_md("demo", "Demo."))],
            prefix=f"acme-skills-{_SHA_V1[:7]}",
        )
        transport = _github_mock_transport(
            {("acme", "skills", "main"): _SHA_V1},
            {("acme", "skills", _SHA_V1): tar_v1},
        )
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            install_skill(
                "acme/skills",
                skill_filter="demo",
                cwd=ws,
                marketplaces_path=mpath,
                cache_dir=cdir,
                client=client,
            )
            up_all = update_installed_skills(
                None, cwd=ws, marketplaces_path=mpath, cache_dir=cdir, client=client
            )
            assert up_all.unchanged == ["acme--skills:demo"]
            up_bare = update_installed_skills(
                "demo", cwd=ws, marketplaces_path=mpath, cache_dir=cdir, client=client
            )
            assert up_bare.unchanged == ["acme--skills:demo"]
            with pytest.raises(ValueError, match="not found"):
                update_installed_skills(
                    "missing",
                    cwd=ws,
                    marketplaces_path=mpath,
                    cache_dir=cdir,
                    client=client,
                )

            (
                ws / mp.MARKETPLACES_SKILLS_REL / "acme--skills" / "demo" / "extra_link"
            ).symlink_to(ws)
            restored = sync_installed_skills(
                cwd=ws, marketplaces_path=mpath, client=client
            )
            assert [e.namespaced for e in restored.restored] == ["acme--skills:demo"]

        mp_dir = ws / mp.MARKETPLACES_SKILLS_REL
        lk_path = ws / mp.SKILLS_LOCK_REL
        assert (
            remove_installed_skill(
                "demo", marketplaces_dir=mp_dir, lockfile_path=lk_path
            ).removed
            is False
        )
        assert (
            remove_installed_skill(
                "acme:../bad", marketplaces_dir=mp_dir, lockfile_path=lk_path
            ).removed
            is False
        )
        assert (
            remove_installed_skill(
                "acme:ghost", marketplaces_dir=mp_dir, lockfile_path=lk_path
            ).removed
            is False
        )
        sym_target = tmp_path / "outside_skill"
        sym_target.mkdir()
        (mp_dir / "acme").mkdir(parents=True)
        (mp_dir / "acme" / "symsk").symlink_to(sym_target)
        assert (
            remove_installed_skill(
                "acme:symsk", marketplaces_dir=mp_dir, lockfile_path=lk_path
            ).removed
            is False
        )

        bad_lock = tmp_path / "bad_lock.json"
        bad_lock.write_text("{corrupt", encoding="utf-8")
        _, bad_lock_w = verify_installed_marketplace_skills(mp_dir, bad_lock)
        assert any("Unreadable skills lockfile" in w for w in bad_lock_w)

        sym_mp = tmp_path / "sym_mp"
        sym_mp.symlink_to(mp_dir)
        _, sym_mp_w = verify_installed_marketplace_skills(sym_mp, lk_path)
        assert any("is a symlink" in w for w in sym_mp_w)

        verify_ws = tmp_path / "verify_ws"
        v_mp = verify_ws / ".agent" / "skills-marketplaces"
        v_lk = verify_ws / ".agent" / "skills-lock.json"
        (v_mp / "sym-ns").mkdir(parents=True)
        (v_mp / "local").mkdir(parents=True)
        (v_mp / "stray.txt").write_text("x", encoding="utf-8")
        (v_mp / "sym-ns").rmdir()
        (v_mp / "sym-ns").symlink_to(tmp_path)
        (v_mp / "acme").mkdir(parents=True)
        (v_mp / "acme" / "note.txt").write_text("x", encoding="utf-8")
        (v_mp / "acme" / "unlocked").mkdir()
        bad_skill = v_mp / "acme" / "badskill"
        bad_skill.mkdir()
        (bad_skill / "SKILL.md").write_text(
            "---\nname: badskill\n---\nNo desc\n", encoding="utf-8"
        )
        bad_hash = compute_skill_dir_hash(bad_skill)
        mp.save_lockfile(
            v_lk,
            {
                "acme:badskill": mp.LockEntry(
                    namespace="acme",
                    name="badskill",
                    source="acme/skills",
                    repo_url="https://github.com/acme/skills",
                    subdir="skills/badskill",
                    ref="main",
                    commit_sha=_SHA_V1,
                    computed_hash=bad_hash,
                )
            },
        )
        ver_list, ver_w = verify_installed_marketplace_skills(v_mp, v_lk)
        assert ver_list == []
        assert any("symlinked marketplace namespace" in w for w in ver_w)
        assert any("unlocked marketplace skill" in w for w in ver_w)
        assert any("invalid marketplace skill" in w for w in ver_w)


@pytest.mark.integration
def test_live_github_marketplace_browse_install_and_verify(tmp_path):
    """Live GitHub probe: resolve anthropics/skills, install one skill, verify SHA-256."""
    from strands_code_cli.memory.skills import SkillIndex

    mpath = tmp_path / "cfg" / "marketplaces.yaml"
    cdir = tmp_path / "cache"
    workdir = tmp_path / "repo"
    workdir.mkdir()

    try:
        entry, catalog = add_marketplace(
            "anthropics/skills",
            name="anthropic-skills",
            marketplaces_path=mpath,
            cache_dir=cdir,
        )
    except (httpx.HTTPError, ValueError) as exc:
        msg = str(exc)
        if isinstance(exc, httpx.HTTPError) or any(
            code in msg
            for code in ("403", "429", "502", "503", "offline", "unreachable")
        ):
            pytest.skip(f"Live GitHub probe skipped (offline or rate-limited): {msg}")
        raise

    assert entry.name == "anthropic-skills"
    assert catalog, "Expected anthropics/skills catalog to yield at least one skill"

    chosen = catalog[0]
    try:
        outcome = install_skill(
            f"anthropic-skills:{chosen.name}",
            cwd=workdir,
            marketplaces_path=mpath,
            cache_dir=cdir,
        )
    except (httpx.HTTPError, ValueError) as exc:
        msg = str(exc)
        if isinstance(exc, httpx.HTTPError) or any(
            code in msg
            for code in ("403", "429", "502", "503", "offline", "unreachable")
        ):
            pytest.skip(f"Live GitHub install skipped (offline or rate-limited): {msg}")
        raise

    assert len(outcome.installed) == 1
    locked = outcome.installed[0]
    assert len(locked.commit_sha) == 40
    assert locked.computed_hash.startswith("sha256:")

    index = SkillIndex(skills_dir=workdir / ".agent" / "skills")
    resolved = index.resolve(f"anthropic-skills:{chosen.name}")
    assert resolved is not None and resolved.commit_sha == locked.commit_sha

    installed_md = (
        workdir
        / mp.MARKETPLACES_SKILLS_REL
        / "anthropic-skills"
        / chosen.name
        / "SKILL.md"
    )
    installed_md.write_text(
        installed_md.read_text(encoding="utf-8") + "\n<!-- drift -->\n",
        encoding="utf-8",
    )
    verified, warnings = verify_installed_marketplace_skills(
        workdir / mp.MARKETPLACES_SKILLS_REL, workdir / mp.SKILLS_LOCK_REL
    )
    assert all(v.name != chosen.name for v in verified)
    assert any("hash-drifted" in w for w in warnings)
