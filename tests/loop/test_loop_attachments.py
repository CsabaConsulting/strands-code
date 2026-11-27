"""Integration tests for @file completion, /file prefill, post-routing media gate, and multimodal loop turns."""

from __future__ import annotations

from types import SimpleNamespace

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from strands_code_cli.dispatch.core import dispatch
from strands_code_cli.loop.core import run_loop
from strands_code_cli.routing.core import RoutingState
from strands_code_cli.session.session_index import SessionIndex
from strands_code_cli.ui.completer import (
    AtFileCompleter,
    SlashCompleter,
    build_completer,
)


class _ScriptedSession:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.seen_defaults: list[str] = []

    def prompt(self, _prompt_text: str, *, default: str = "") -> str:
        self.seen_defaults.append(default)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


class _DummyAgent:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.prompts: list = []

    def add_hook(self, *_args, **_kwargs) -> None:
        pass

    def __call__(self, prompt, **_kwargs):
        self.prompts.append(prompt)
        self.messages.append({"role": "assistant", "content": [{"text": "done"}]})
        return SimpleNamespace(
            stop_reason="end_turn",
            metrics=SimpleNamespace(accumulated_usage={}),
            message=self.messages[-1],
        )


class TestAtFileCompleterAndLoopIntegration:
    def test_composite_completer_preserves_slash_and_completes_midline_at_file(self):
        words = [("help", "/help"), ("deploy", "/local:deploy")]
        files = ["src/app.py", "docs/my spec.md"]
        slash_only = SlashCompleter(lambda: words)
        at_only = AtFileCompleter(lambda: files)
        assert [
            c.text for c in slash_only.get_completions(Document("/he"), CompleteEvent())
        ] == ["/help"]
        assert [
            c.text
            for c in at_only.get_completions(Document("check @app"), CompleteEvent())
        ] == ["@src/app.py"]
        assert [
            c.text
            for c in at_only.get_completions(Document("check @spec"), CompleteEvent())
        ] == ['@"docs/my spec.md"']
        assert list(at_only.get_completions(Document("/skills"), CompleteEvent())) == []

        comp = build_completer(lambda: words, lambda: files)
        got_slash = [
            c.text for c in comp.get_completions(Document("/he"), CompleteEvent())
        ]
        got_at = [
            c.text for c in comp.get_completions(Document("open @src"), CompleteEvent())
        ]
        assert "/help" in got_slash
        assert "@src/app.py" in got_at

    def test_file_dispatch_returns_prefill_and_loop_prefills_next_prompt(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")

        import strands_code_cli.ui.choice as choice_mod

        monkeypatch.setattr(
            choice_mod, "radio_choice", lambda _t, opts, default=1: "src/main.py"
        )
        index = SessionIndex(tmp_path / "sessions")
        action, msg = dispatch("/file main", session_id="s1", index=index, cwd=tmp_path)
        assert action == "prefill"
        assert msg == "@src/main.py "

        agent = _DummyAgent()
        prompts = iter(["/file main", "explain @src/main.py please", "/exit"])

        class _FakePromptSession:
            seen_defaults: list[str] = []

            def __init__(self, **_kwargs) -> None:
                pass

            def prompt(self, _p: str, *, default: str = "") -> str:
                self.seen_defaults.append(default)
                try:
                    return next(prompts)
                except StopIteration:
                    raise EOFError from None

        created: list[_FakePromptSession] = []

        def _make_session(**kwargs):
            s = _FakePromptSession(**kwargs)
            created.append(s)
            return s

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _make_session)
        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )
        assert created[0].seen_defaults == ["", "@src/main.py ", ""]
        assert len(agent.prompts) == 1
        assert '<attached_file path="src/main.py">' in agent.prompts[0]

    def test_post_routing_medialess_model_aborts_before_model_call_and_routing_sees_ask_only(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "notes.txt").write_text("CONFIDENTIAL_FILE_BODY", encoding="utf-8")
        index = SessionIndex(tmp_path / "sessions")
        agent = _DummyAgent()

        lines = iter(["Inspect @pic.png and @notes.txt", "/exit"])

        class _Sess:
            def __init__(self, **_kw):
                pass

            def prompt(self, _p: str, **_kw):
                return next(lines)

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _Sess)
        routing_asks: list[str] = []

        def _fake_route(
            _agent,
            *,
            current_model: str,
            ask_text: str,
            **_kw,
        ) -> str:
            routing_asks.append(ask_text)
            # Simulate /route switching onto a verified media-less model.
            return "openai/nemotron-70b"

        monkeypatch.setattr("strands_code_cli.loop.core._route_pre_turn", _fake_route)
        printed: list[str] = []
        monkeypatch.setattr(
            "strands_code_cli.loop.core.print_plain",
            lambda _c, text, **_kw: printed.append(str(text)),
        )
        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )

        # Routing saw only raw user text, never attached file body or PNG bytes.
        assert routing_asks == ["Inspect @pic.png and @notes.txt"]
        # Media-less model aborted BEFORE calling the agent!
        assert agent.prompts == []
        assert any(
            "openai/nemotron-70b" in line and "pic.png" in line for line in printed
        )
        assert isinstance(RoutingState(), RoutingState)

    def test_media_capable_routed_model_receives_allowlisted_content_blocks(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
        index = SessionIndex(tmp_path / "sessions")
        agent = _DummyAgent()
        lines = iter(["Review @pic.png and @doc.pdf", "/exit"])

        class _Sess:
            def __init__(self, **_kw):
                pass

            def prompt(self, _p: str, **_kw):
                return next(lines)

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _Sess)
        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )

        assert len(agent.prompts) == 1
        sent = agent.prompts[0]
        assert isinstance(sent, list)
        assert [list(b.keys())[0] for b in sent] == ["text", "image", "document"]
