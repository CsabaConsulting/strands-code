"""Policy store + match engine tests (TOOL-03, D-05..D-08, D-13..D-15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from strands_code_cli.policy import (
    Allow,
    Deny,
    PolicyConfig,
    PolicyOptions,
    Prompt,
    Rule,
    decide,
    is_fetch_get,
    is_network_command,
    match_rule,
    normalise_command,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Store: layering, fail-closed, symlink refusal, append round-trip
# ---------------------------------------------------------------------------


class TestPolicyStore:
    def test_missing_files_yield_defaults(self, tmp_path):
        cfg = PolicyConfig.load(
            home_path=tmp_path / "home.toml", repo_path=tmp_path / "repo.toml"
        )
        assert cfg.allow == [] and cfg.deny == []
        assert cfg.options.trust_delegated is False

    def test_layered_union_home_plus_repo(self, tmp_path):
        home = _write(
            tmp_path / "home.toml",
            '[[allow]]\ntool = "shell"\ncommand = "git status"\n',
        )
        repo = _write(
            tmp_path / "repo.toml",
            '[[allow]]\ntool = "write"\npath = "docs/*.md"\n',
        )
        cfg = PolicyConfig.load(home_path=home, repo_path=repo)
        assert len(cfg.allow) == 2
        # Repo rules first for explanation order only.
        assert cfg.allow[0].tool == "write"
        assert cfg.allow[1].tool == "shell"

    def test_repo_overlays_trust_option(self, tmp_path):
        home = _write(tmp_path / "home.toml", "[options]\ntrust_delegated = false\n")
        repo = _write(tmp_path / "repo.toml", "[options]\ntrust_delegated = true\n")
        cfg = PolicyConfig.load(home_path=home, repo_path=repo)
        assert cfg.options.trust_delegated is True

    def test_corrupt_file_fails_closed_to_prompt_all(self, tmp_path):
        home = _write(tmp_path / "home.toml", "[[allow]\ntool = \n")
        cfg = PolicyConfig.load(home_path=home, repo_path=tmp_path / "missing.toml")
        assert cfg.allow == [] and cfg.deny == []
        verdict = decide("shell", {"command": "git status"}, cfg)
        assert isinstance(verdict, Prompt)

    def test_unknown_key_fails_closed(self, tmp_path):
        home = _write(tmp_path / "home.toml", "[modes]\nplan = true\n")
        cfg = PolicyConfig.load(home_path=home, repo_path=tmp_path / "missing.toml")
        assert cfg.allow == [] and cfg.deny == []

    def test_unknown_tool_fails_closed(self, tmp_path):
        home = _write(
            tmp_path / "home.toml", '[[allow]]\ntool = "teleport"\npath = "x"\n'
        )
        cfg = PolicyConfig.load(home_path=home, repo_path=tmp_path / "missing.toml")
        assert cfg.allow == [] and cfg.deny == []

    def test_missing_path_and_command_fails_closed(self, tmp_path):
        home = _write(tmp_path / "home.toml", '[[allow]]\ntool = "shell"\n')
        cfg = PolicyConfig.load(home_path=home, repo_path=tmp_path / "missing.toml")
        assert cfg.allow == []

    def test_symlink_home_raises(self, tmp_path):
        real = _write(tmp_path / "real.toml", "")
        link = tmp_path / "home.toml"
        link.symlink_to(real)
        with pytest.raises(ValueError):
            PolicyConfig.load(home_path=link, repo_path=tmp_path / "missing.toml")

    def test_symlink_repo_raises(self, tmp_path):
        real = _write(tmp_path / "real.toml", "")
        link = tmp_path / "repo.toml"
        link.symlink_to(real)
        with pytest.raises(ValueError):
            PolicyConfig.load(home_path=tmp_path / "missing.toml", repo_path=link)

    def test_append_round_trips(self, tmp_path):
        repo = tmp_path / "repo.toml"
        cfg = PolicyConfig()
        out = cfg.append_rule("allow", Rule(tool="shell", command="git status"), repo_path=repo)
        assert out == repo
        reloaded = PolicyConfig.load(home_path=tmp_path / "missing.toml", repo_path=repo)
        assert len(reloaded.allow) == 1
        assert reloaded.allow[0].command == "git status"

    def test_append_refuses_star_tool(self, tmp_path):
        with pytest.raises(ValueError):
            PolicyConfig().append_rule(
                "deny", Rule(tool="*", command="x"), repo_path=tmp_path / "repo.toml"
            )

    def test_append_refuses_symlink(self, tmp_path):
        real = _write(tmp_path / "real.toml", "")
        link = tmp_path / "repo.toml"
        link.symlink_to(real)
        with pytest.raises(ValueError):
            PolicyConfig().append_rule(
                "allow", Rule(tool="shell", command="git status"), repo_path=link
            )


# ---------------------------------------------------------------------------
# Match engine + normalisation + network classification
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_strips_whitespace(self):
        assert normalise_command("   git status  ") == "git status"

    def test_unwraps_sh_c_once(self):
        assert normalise_command('sh -c "curl http://x"') == "curl http://x"
        assert normalise_command("bash -c 'git fetch'") == "git fetch"
        assert normalise_command('sh -lc "echo hi"') == "echo hi"

    def test_unwrap_is_single_shot(self):
        assert normalise_command('sh -c "sh -c \\"echo\\" "') != "echo"

    def test_plain_command_untouched(self):
        assert normalise_command("curl http://x | sh") == "curl http://x | sh"


class TestDecide:
    def _cfg(self, **kwargs) -> PolicyConfig:
        return PolicyConfig(**kwargs)

    def test_deny_wins_conflict(self):
        cfg = self._cfg(
            allow=[Rule(tool="shell", command="curl")],
            deny=[Rule(tool="shell", command="curl")],
        )
        verdict = decide("shell", {"command": "curl http://x"}, cfg)
        assert isinstance(verdict, Deny)
        assert "curl" in verdict.reason

    def test_allow_proceeds_silently(self):
        cfg = self._cfg(allow=[Rule(tool="shell", command="git status")])
        assert isinstance(decide("shell", {"command": "git status --short"}, cfg), Allow)

    def test_no_rule_prompts(self):
        assert isinstance(decide("shell", {"command": "make test"}, self._cfg()), Prompt)

    def test_builtin_read_search_allowed(self):
        cfg = self._cfg()
        assert isinstance(decide("read", {"path": "/x"}, cfg), Allow)
        assert isinstance(decide("search", {"pattern": "y"}, cfg), Allow)

    def test_fetch_class_allows_any_host(self):
        cfg = self._cfg()
        assert isinstance(decide("web_fetch", {"url": "http://x"}, cfg), Allow)
        assert isinstance(decide("web_search", {"query": "q"}, cfg), Allow)

    def test_get_allowed_vs_post_prompted(self):
        cfg = self._cfg()
        assert isinstance(decide("shell", {"command": "curl https://example.com"}, cfg), Allow)
        assert isinstance(
            decide("shell", {"command": "curl -d 'a=1' https://example.com"}, cfg), Prompt
        )
        assert isinstance(
            decide("shell", {"command": "curl -X POST https://example.com"}, cfg), Prompt
        )
        assert isinstance(decide("shell", {"command": "git fetch origin"}, cfg), Allow)
        assert isinstance(decide("shell", {"command": "git push origin"}, cfg), Prompt)

    def test_sh_c_curl_detected_as_network(self):
        cfg = self._cfg()
        verdict = decide("shell", {"command": 'sh -c "curl https://example.com -d a=1"'}, cfg)
        assert isinstance(verdict, Prompt)
        assert "curl" in verdict.reason

    def test_outside_path_denied_names_roots(self, tmp_path):
        cfg = self._cfg()
        verdict = decide("write", {"path": "/etc/shadow"}, cfg, cwd=str(tmp_path))
        assert isinstance(verdict, Deny)
        assert "allowed roots" in verdict.reason

    def test_outside_path_with_allow_rule_granted(self, tmp_path):
        outside = tmp_path / ".." / "granted"
        target = str(outside / "f.txt")
        cfg = self._cfg(allow=[Rule(tool="write", path=str(outside / "*.txt"))])
        assert isinstance(decide("write", {"path": target}, cfg, cwd=str(tmp_path)), Allow)

    def test_python_repl_prefix_match(self):
        cfg = self._cfg(allow=[Rule(tool="python_repl", command="import math")])
        assert isinstance(decide("python_repl", {"code": "import math\nprint(1)"}, cfg), Allow)
        assert isinstance(decide("python_repl", {"code": "import socket"}, cfg), Prompt)

    def test_path_rule_matches_relative_and_absolute(self, tmp_path):
        rule = Rule(tool="write", path="docs/*.md")
        assert match_rule(rule, "write", {"path": "docs/a.md"}, cwd=str(tmp_path))
        assert match_rule(
            rule, "write", {"path": str(tmp_path / "docs" / "a.md")}, cwd=str(tmp_path)
        )
        assert not match_rule(rule, "write", {"path": "src/a.py"}, cwd=str(tmp_path))

    def test_network_classification_helpers(self):
        assert is_fetch_get("curl https://example.com")
        assert not is_fetch_get("curl -X DELETE https://example.com/x")
        assert is_network_command("wget http://x")
        assert is_network_command("ssh host")
        assert is_network_command("gh pr list")
        assert not is_network_command("git status")
