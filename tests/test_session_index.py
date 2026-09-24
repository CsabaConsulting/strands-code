"""Session index round-trips: mint, recency, rename, auto-title (D-03/D-04)."""

from __future__ import annotations

import json
import uuid

import pytest

from strands_code_cli.session_index import SessionIndex


def _fresh_index(tmp_path):
    return SessionIndex(tmp_path / "index")


# ---------------------------------------------------------------------------
# Mint + recency ordering
# ---------------------------------------------------------------------------


class TestMintAndRecency:
    def test_mint_returns_uuid_with_untitled_entry(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        uuid.UUID(sid)
        (entry,) = index.list_recent()
        assert entry["id"] == sid
        assert entry["title"] == "untitled"

    def test_recent_order_follows_updated_at(self, tmp_path):
        index = _fresh_index(tmp_path)
        first = index.mint()
        second = index.mint()
        assert [e["id"] for e in index.list_recent()] == [second, first]
        index.ensure(first)  # bump first to most recent
        assert [e["id"] for e in index.list_recent()] == [first, second]

    def test_ensure_registers_unknown_id(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = str(uuid.uuid4())
        entry = index.ensure(sid)
        assert entry["id"] == sid
        assert entry["title"] == "untitled"


# ---------------------------------------------------------------------------
# Rename (D-03, T-02-01)
# ---------------------------------------------------------------------------


class TestRename:
    def test_rename_persists(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        entry = index.rename(sid, "Atlas Project")
        assert entry["title"] == "Atlas Project"
        assert SessionIndex(tmp_path / "index").list_recent()[0]["title"] == "Atlas Project"

    def test_rename_unknown_id_raises_key_error(self, tmp_path):
        with pytest.raises(KeyError):
            _fresh_index(tmp_path).rename(str(uuid.uuid4()), "Nope")

    @pytest.mark.parametrize("bad", ["", "   ", "a/b", "a\\b", "nul\x00byte"])
    def test_rename_rejects_bad_titles(self, tmp_path, bad):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        with pytest.raises(ValueError):
            index.rename(sid, bad)
        assert index.list_recent()[0]["title"] == "untitled"

    def test_rename_caps_length(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        entry = index.rename(sid, "x" * 200)
        assert len(entry["title"]) <= 120

    def test_titles_live_only_in_sidecar_json(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        index.rename(sid, "Sidecar Only")
        root = tmp_path / "index"
        raw = (root / "index.json").read_text(encoding="utf-8")
        assert "Sidecar Only" in json.loads(raw)[sid]["title"]
        assert not (root / "Sidecar Only").exists()

    def test_dispatch_rename_separator_rejected_without_agent_turn(self, tmp_path):
        from strands_code_cli.router import dispatch

        index = _fresh_index(tmp_path)
        sid = index.mint()
        action, message = dispatch("/rename a/b", session_id=sid, index=index)
        assert action == "reply"
        assert "Cannot rename" in message
        assert index.list_recent()[0]["title"] == "untitled"


# ---------------------------------------------------------------------------
# Auto-title lifecycle (D-04)
# ---------------------------------------------------------------------------


class TestAutoTitle:
    def test_update_title_fills_untitled_once(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        entry = index.update_title(sid, "generated words here")
        assert entry["title"] == "generated words here"

    def test_update_title_never_overwrites_manual_rename(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        index.rename(sid, "My Title")
        entry = index.update_title(sid, "model generated words")
        assert entry["title"] == "My Title"

    def test_update_title_unknown_id_raises_key_error(self, tmp_path):
        with pytest.raises(KeyError):
            _fresh_index(tmp_path).update_title(str(uuid.uuid4()), "Nope")

    def test_loop_auto_title_respects_manual_rename(self, tmp_path):
        from types import SimpleNamespace

        from strands_code_cli.loop import _maybe_auto_title

        class _Model:
            def generate(self, prompt: str) -> str:
                assert prompt
                return "model generated words"

        index = _fresh_index(tmp_path)
        sid = index.mint()
        index.rename(sid, "My Title")
        _maybe_auto_title(SimpleNamespace(model=_Model()), sid, index, "first question")
        assert index.list_recent()[0]["title"] == "My Title"


# ---------------------------------------------------------------------------
# Fail-soft reads (T-02-02)
# ---------------------------------------------------------------------------


class TestFailSoftReads:
    def test_missing_index_reads_as_empty(self, tmp_path):
        assert _fresh_index(tmp_path).list_recent() == []

    def test_corrupt_index_reads_as_empty_without_raising(self, tmp_path):
        root = tmp_path / "index"
        root.mkdir()
        (root / "index.json").write_text("{not valid json", encoding="utf-8")
        assert SessionIndex(root).list_recent() == []

    def test_non_dict_payload_reads_as_empty(self, tmp_path):
        root = tmp_path / "index"
        root.mkdir()
        (root / "index.json").write_text("[1, 2]", encoding="utf-8")
        assert SessionIndex(root).list_recent() == []

    def test_pre_flag_entries_default_to_auto_titlable(self, tmp_path):
        root = tmp_path / "index"
        root.mkdir()
        sid = str(uuid.uuid4())
        (root / "index.json").write_text(
            json.dumps({sid: {"title": "old", "created_at": "t", "updated_at": "t"}}),
            encoding="utf-8",
        )
        index = SessionIndex(root)
        assert index.update_title(sid, "new words")["title"] == "new words"
