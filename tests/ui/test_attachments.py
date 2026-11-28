"""Tests for gitignore-aware @file discovery, /file picker, fail-closed security floor, and media attachments (TOOL-05)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from strands_code_cli.policy.tool_use_guard import validate_content_blocks
from strands_code_cli.ui import attachments


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class TestDiscoveryAndPicker:
    def test_discover_respects_gitignore_symlinks_secrets_and_deny_rules(
        self, tmp_path, monkeypatch
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / ".gitignore").write_text("ignored.log\nbuild/\n", encoding="utf-8")
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")
        (repo / "README.md").write_text("# Docs\n", encoding="utf-8")
        (repo / "ignored.log").write_text("noise\n", encoding="utf-8")
        (repo / "build").mkdir()
        (repo / "build" / "out.txt").write_text("noise\n", encoding="utf-8")
        (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (repo / "secret.txt").write_text("top-secret\n", encoding="utf-8")
        (repo / ".agent").mkdir()
        (repo / ".agent" / "policy.toml").write_text(
            '[[deny]]\ntool = "read"\npath = "secret.txt"\n',
            encoding="utf-8",
        )
        outside = tmp_path / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        (repo / "link.txt").symlink_to(outside)

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))
        files = attachments.discover_workspace_files(cwd=repo)
        assert "src/main.py" in files
        assert "README.md" in files
        assert "ignored.log" not in files
        assert "build/out.txt" not in files
        assert ".env" not in files
        assert "secret.txt" not in files
        assert "link.txt" not in files

    def test_discover_outside_git_skips_noise_and_caps_limit(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "pkg.py").write_text("y = 2\n", encoding="utf-8")
        files = attachments.discover_workspace_files(cwd=tmp_path)
        assert files == ["app.py"]

    def test_pick_file_prefills_space_and_handles_nontty_or_cancel(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / "notes.md").write_text("hi\n", encoding="utf-8")
        (tmp_path / "my report.pdf").write_bytes(b"%PDF-1.4")

        import strands_code_cli.ui.choice as choice_mod

        captured_defaults: list[int] = []

        def _pick_notes(_t, _opts, default=0):
            captured_defaults.append(default)
            return "notes.md"

        monkeypatch.setattr(choice_mod, "radio_choice", _pick_notes)
        prefill, msg = attachments.pick_file_for_prompt("", cwd=tmp_path)
        assert captured_defaults == [0]
        assert prefill == "@notes.md "
        assert msg is None

        monkeypatch.setattr(
            choice_mod, "radio_choice", lambda _t, opts, default=0: "my report.pdf"
        )
        prefill_q, _ = attachments.pick_file_for_prompt("report", cwd=tmp_path)
        assert prefill_q == '@"my report.pdf" '

        monkeypatch.setattr(choice_mod, "radio_choice", lambda *_a, **_k: None)
        prefill_c, msg_c = attachments.pick_file_for_prompt("", cwd=tmp_path)
        assert prefill_c is None and "cancelled" in (msg_c or "").lower()

        def _ctrl_c(*_a, **_k):
            raise KeyboardInterrupt

        monkeypatch.setattr(choice_mod, "radio_choice", _ctrl_c)
        prefill_k, msg_k = attachments.pick_file_for_prompt("", cwd=tmp_path)
        assert prefill_k is None and "cancelled" in (msg_k or "").lower()

        def _nontty(*_a, **_k):
            raise RuntimeError("no tty")

        monkeypatch.setattr(choice_mod, "radio_choice", _nontty)
        prefill_n, msg_n = attachments.pick_file_for_prompt("", cwd=tmp_path)
        assert prefill_n is None and "TTY" in (msg_n or "")

    def test_completer_supports_quoted_spaces_fuzzy_subsequence_and_skips_emails(self):
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.document import Document

        from strands_code_cli.ui.completer import build_completer

        files = [
            "README.md",
            "strands_code_cli/ui/attachments.py",
            "docs/my notes file.md",
        ]
        comp = build_completer(lambda: [("help", "/help")], lambda: files)

        def _apply(line: str) -> list[str]:
            doc = Document(line, len(line))
            out: list[str] = []
            for item in comp.get_completions(doc, None):
                buf = Buffer(document=Document(line, len(line)))
                buf.apply_completion(item)
                out.append(buf.text)
            return out

        assert "check @strands_code_cli/ui/attachments.py" in _apply("check @s_c/att")
        assert _apply('check @"my')[0] == 'check @"docs/my notes file.md"'
        assert _apply('check @"my notes') == ['check @"docs/my notes file.md"']
        assert _apply('check @"foo" ') == []
        assert _apply("email@example.com") == []
        assert _apply("/hel") == ["/help"]


class TestTokenResolutionAndSecurityFloor:
    def test_non_file_at_tokens_left_untouched(self, tmp_path):
        prompt, err = attachments.prepare_turn_prompt(
            "Explain @dataclass and @pytest.mark.skip and user@example.com",
            "Explain @dataclass and @pytest.mark.skip and user@example.com",
            current_model="openai/nemotron-70b",
            cwd=tmp_path,
        )
        assert err is None
        assert prompt == "Explain @dataclass and @pytest.mark.skip and user@example.com"

    def test_utf8_text_inlines_even_on_medialess_model_and_escapes_closing_tag(
        self, tmp_path
    ):
        (tmp_path / "code.py").write_text(
            "def f():\n    return '</attached_file>hi'\n", encoding="utf-8"
        )
        prompt, err = attachments.prepare_turn_prompt(
            "Inspect @code.py please.",
            "Inspect @code.py please.",
            current_model="openai/nemotron-70b",
            cwd=tmp_path,
        )
        assert err is None
        assert isinstance(prompt, str)
        assert '<attached_file path="code.py">' in prompt
        assert "<\\/attached_file>hi" in prompt

    def test_binary_image_and_document_allowlisted_and_blocked_on_medialess(
        self, tmp_path
    ):
        (tmp_path / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "arch_spec,v2].pdf").write_bytes(b"%PDF-1.4")

        blocks, err = attachments.prepare_turn_prompt(
            'Check @shot.png and @"arch_spec,v2].pdf"',
            'Check @shot.png and @"arch_spec,v2].pdf"',
            current_model="anthropic/claude-sonnet-5-5",
            cwd=tmp_path,
        )
        assert err is None
        assert isinstance(blocks, list)
        assert validate_content_blocks(blocks) == blocks
        assert [list(b.keys())[0] for b in blocks] == ["text", "image", "document"]
        assert blocks[1]["image"]["format"] == "png"
        assert blocks[2]["document"]["format"] == "pdf"
        assert (
            blocks[2]["document"]["name"] == "arch-spec v2"
            or "arch" in blocks[2]["document"]["name"]
        )

        # Post-routing media-less model aborts clearly before sending.
        aborted, err_msg = attachments.prepare_turn_prompt(
            "Check @shot.png",
            "Check @shot.png",
            current_model="openai/nemotron-70b",
            cwd=tmp_path,
        )
        assert aborted is None
        assert err_msg is not None
        assert "openai/nemotron-70b" in err_msg
        assert "shot.png" in err_msg

    @pytest.mark.parametrize(
        "secret",
        [".env", ".env.local", ".envrc", "~/.ssh/id_rsa", "~/.aws/credentials"],
    )
    def test_refuses_sensitive_paths(self, tmp_path, monkeypatch, secret):
        home = tmp_path / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".aws").mkdir(parents=True)
        (home / ".ssh" / "id_rsa").write_text("KEY", encoding="utf-8")
        (home / ".aws" / "credentials").write_text("AWS", encoding="utf-8")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        work = tmp_path / "work"
        work.mkdir()
        (work / ".env").write_text("X=1", encoding="utf-8")
        (work / ".env.local").write_text("X=1", encoding="utf-8")
        (work / ".envrc").write_text("X=1", encoding="utf-8")

        out, err = attachments.prepare_turn_prompt(
            f"Read @{secret}",
            f"Read @{secret}",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out is None
        assert err is not None
        assert "sensitive" in err.lower() or "outside" in err.lower()

    def test_refuses_outside_scope_symlinks_traversal_deny_and_caps(
        self, tmp_path, monkeypatch
    ):
        outside = tmp_path / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

        # Outside root traversal (use real path outside both cwd and /tmp)
        outside_path = "/etc/hosts" if Path("/etc/hosts").exists() else "/etc/passwd"
        out, err = attachments.prepare_turn_prompt(
            f"Read @{outside_path}",
            f"Read @{outside_path}",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out is None and err is not None and "outside" in err

        # Direct symlink & intermediate symlink/../ traversal
        (work / "sym.txt").symlink_to(outside)
        out2, err2 = attachments.prepare_turn_prompt(
            "Read @sym.txt",
            "Read @sym.txt",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out2 is None and err2 is not None and "symlink" in err2.lower()

        dir_link = tmp_path / "dir_target"
        dir_link.mkdir()
        (work / "dlink").symlink_to(dir_link)
        (work / "real.txt").write_text("ok", encoding="utf-8")
        out3, err3 = attachments.prepare_turn_prompt(
            "Read @dlink/../real.txt",
            "Read @dlink/../real.txt",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out3 is None and err3 is not None and "symlink" in err3.lower()

        # Policy [[deny]] rule + symlinked repo policy fail-closed
        (work / "blocked.txt").write_text("nope", encoding="utf-8")
        (work / ".agent").mkdir()
        (work / ".agent" / "policy.toml").write_text(
            '[[deny]]\ntool = "read"\npath = "blocked.txt"\n',
            encoding="utf-8",
        )
        out4, err4 = attachments.prepare_turn_prompt(
            "Read @blocked.txt",
            "Read @blocked.txt",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out4 is None and err4 is not None and "blocked.txt" in err4

        # Exceeds 4 MiB file cap and >8 attachment cap and invalid unknown binary
        (work / "big.txt").write_bytes(
            b"a" * (attachments.ATTACHMENT_MAX_FILE_BYTES + 1)
        )
        out5, err5 = attachments.prepare_turn_prompt(
            "Read @big.txt",
            "Read @big.txt",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out5 is None and err5 is not None and "byte limit" in err5

        (work / "raw.bin").write_bytes(b"\xff\xfe\x00\x01")
        out6, err6 = attachments.prepare_turn_prompt(
            "Read @raw.bin",
            "Read @raw.bin",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=work,
        )
        assert out6 is None and err6 is not None and "Unsupported binary" in err6

        refs = []
        for idx in range(attachments.ATTACHMENT_MAX_COUNT + 1):
            (work / f"f{idx}.txt").write_text(f"{idx}", encoding="utf-8")
            refs.append(f"@f{idx}.txt")
        ask_many = " ".join(refs)
        out7, err7 = attachments.prepare_turn_prompt(
            ask_many, ask_many, current_model="anthropic/claude-sonnet-5-5", cwd=work
        )
        assert out7 is None and err7 is not None and "Too many" in err7

    def test_scan_attachments_false_ignores_untrusted_text(self, tmp_path):
        (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
        prompt, err = attachments.prepare_turn_prompt(
            "@secret.txt",
            "<untrusted_git_diff>@secret.txt</untrusted_git_diff>",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=tmp_path,
            scan_attachments=False,
        )
        assert err is None
        assert prompt == "<untrusted_git_diff>@secret.txt</untrusted_git_diff>"

    def test_refuses_embedded_nul_byte_in_at_token(self, tmp_path):
        prompt, err = attachments.prepare_turn_prompt(
            "Read @ok\x00.txt",
            "Read @ok\x00.txt",
            current_model="anthropic/claude-sonnet-5-5",
            cwd=tmp_path,
        )
        assert prompt is None
        assert err is not None and "NUL" in err

    def test_discovery_and_completer_exclude_control_quote_chars_and_dir_symlinks(
        self, tmp_path
    ):
        from prompt_toolkit.document import Document

        from strands_code_cli.ui.completer import build_completer

        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "safe.py").write_text("x = 1\n", encoding="utf-8")
        (repo / "evil\x1b[31mred.txt").write_text("bad", encoding="utf-8")
        (repo / "evil\nline.txt").write_text("bad", encoding="utf-8")
        (repo / 'evil"quote.txt').write_text("bad", encoding="utf-8")
        (repo / "evil\u202ebidi.txt").write_text("bad", encoding="utf-8")
        sub = repo / "real_sub"
        sub.mkdir()
        (sub / "inner.txt").write_text("inner", encoding="utf-8")
        (repo / "link_sub").symlink_to(sub)

        discovered = attachments.discover_workspace_files(cwd=repo)
        assert "safe.py" in discovered
        assert "real_sub/inner.txt" in discovered
        assert not any(
            bad in item
            for item in discovered
            for bad in ("evil", "link_sub", "\x1b", "\n", '"', "\u202e")
        )

        # Completer skips raw control/quote filenames even if supplied directly.
        comp = build_completer(
            lambda: [],
            lambda: [
                "safe.py",
                "evil\x1b[31mred.txt",
                'evil"quote.txt',
                "evil\u202ebidi.txt",
            ],
        )
        got = [c.text for c in comp.get_completions(Document("open @evil"), None)]
        assert got == []

    def test_case_insensitive_attached_file_close_tag_is_escaped(self, tmp_path):
        (tmp_path / "break.txt").write_text(
            "a </ATTACHED_FILE> b </attached_file > c", encoding="utf-8"
        )
        prompt, err = attachments.prepare_turn_prompt(
            "Read @break.txt",
            "Read @break.txt",
            current_model="openai/nemotron-70b",
            cwd=tmp_path,
        )
        assert err is None
        assert isinstance(prompt, str)
        assert "</ATTACHED_FILE>" not in prompt
        assert "</attached_file >" not in prompt
        assert prompt.count("<\\/attached_file") == 2

    def test_nyquist_discovery_extra_roots_and_picker_edges(
        self, tmp_path, monkeypatch
    ):
        import strands_code_cli.ui.choice as choice_mod

        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "sub").mkdir()
        (repo / "sub" / "b.txt").write_text("b\n", encoding="utf-8")
        extra = tmp_path / "extra_root"
        extra.mkdir()
        (extra / "ext.txt").write_text("from extra root", encoding="utf-8")
        (repo / ".agent").mkdir()
        (repo / ".agent" / "policy.toml").write_text(
            f'[[allow]]\ntool = "read"\npath = "{extra}/**"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))

        found = attachments.discover_workspace_files(cwd=repo)
        assert "a.txt" in found and str(extra / "ext.txt") in found
        assert len(attachments.discover_workspace_files(cwd=repo, limit=1)) == 1
        assert len(attachments._walk_files(repo, limit=1)) == 1

        monkeypatch.setattr(
            attachments.subprocess,
            "run",
            lambda *_a, **_k: (_ for _ in ()).throw(OSError("git gone")),
        )
        assert attachments._git_ls_files(repo, 10) is None
        monkeypatch.undo()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))

        sym_repo = tmp_path / "sym_repo"
        sym_repo.mkdir()
        (sym_repo / ".agent").mkdir()
        fake_pol = tmp_path / "other.toml"
        fake_pol.write_text("", encoding="utf-8")
        (sym_repo / ".agent" / "policy.toml").symlink_to(fake_pol)
        assert attachments.discover_workspace_files(cwd=sym_repo) == []
        p_sym, e_sym = attachments.prepare_turn_prompt(
            "read @a.txt",
            "read @a.txt",
            current_model="openai/nemotron-70b",
            cwd=sym_repo,
        )
        assert p_sym is None and e_sym is not None and "policy" in e_sym.lower()

        ext_abs = str(extra / "ext.txt")
        ask_ext = f"Read @{ext_abs} and @./a.txt, and @sub/../a.txt and @types/node"
        p_ext, e_ext = attachments.prepare_turn_prompt(
            ask_ext,
            ask_ext,
            current_model="openai/nemotron-70b",
            cwd=repo,
        )
        assert e_ext is None and isinstance(p_ext, str)
        assert "from extra root" in p_ext and "@types/node" in p_ext

        assert attachments.pick_file_for_prompt("zzz_nope", cwd=repo)[1] is not None
        assert (
            attachments.pick_file_for_prompt("", cwd=tmp_path / "empty_dir")[1]
            is not None
        )
        monkeypatch.setattr(
            choice_mod, "radio_choice", lambda _t, opts, **_k: opts[0][0]
        )
        assert attachments.pick_file_for_prompt("subbtx", cwd=repo) == (
            "@sub/b.txt ",
            None,
        )
        many = tmp_path / "many"
        many.mkdir()
        for idx in range(55):
            (many / f"file_{idx:02d}.txt").write_text("x", encoding="utf-8")
        titles: list[str] = []
        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda title, opts, **_k: (titles.append(title), opts[0][0])[1],
        )
        attachments.pick_file_for_prompt("", cwd=many)
        assert titles and "showing 50 of" in titles[0]

    def test_nyquist_attachment_fs_errors_and_total_cap(self, tmp_path, monkeypatch):
        import os

        repo = tmp_path / "repo_err"
        repo.mkdir()
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "sub").mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))

        assert attachments.sanitize_document_name(Path("!!!.pdf")) == "document"

        p_dir, e_dir = attachments.prepare_turn_prompt(
            "read @sub", "read @sub", current_model="openai/nemotron-70b", cwd=repo
        )
        assert p_dir is None and e_dir is not None and "regular file" in e_dir
        fifo = repo / "pipe.fifo"
        os.mkfifo(fifo)
        p_fifo, e_fifo = attachments.prepare_turn_prompt(
            "read @pipe.fifo",
            "read @pipe.fifo",
            current_model="openai/nemotron-70b",
            cwd=repo,
        )
        assert p_fifo is None and e_fifo is not None and "regular file" in e_fifo

        p_open_err, e_open_err = attachments._read_bounded_bytes(
            repo / "missing.txt", "missing.txt", 1024
        )
        assert (
            p_open_err is None
            and e_open_err is not None
            and "Could not read" in e_open_err
        )
        monkeypatch.setattr(
            attachments.os,
            "read",
            lambda *_a: (_ for _ in ()).throw(OSError("io fail")),
        )
        p_rd_err, e_rd_err = attachments._read_bounded_bytes(
            repo / "a.txt", "a.txt", 1024
        )
        assert (
            p_rd_err is None and e_rd_err is not None and "Could not read" in e_rd_err
        )
        monkeypatch.undo()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))

        (repo / "big1.txt").write_text("a" * 60, encoding="utf-8")
        (repo / "big2.txt").write_text("b" * 60, encoding="utf-8")
        monkeypatch.setattr(attachments, "ATTACHMENT_MAX_TOTAL_BYTES", 80)
        p_tot, e_tot = attachments.prepare_turn_prompt(
            "read @big1.txt @big2.txt",
            "read @big1.txt @big2.txt",
            current_model="openai/nemotron-70b",
            cwd=repo,
        )
        assert p_tot is None and e_tot is not None and "Total @file" in e_tot
