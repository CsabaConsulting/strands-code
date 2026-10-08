"""Idle multiplex (E) spike verdict plus plumbing and live tests (G-7-1-R2).

SPIKE VERDICT: GO (live pty, 2026-10-08, prompt_toolkit 3.0.53).

Shape spiked (sequential, never nested): idle prompt as prompt_async,
asyncio.wait FIRST_COMPLETED against a broker-poll stand-in; on
approval arrival cancel the prompt future, let the loop quiesce
(run_until_complete returns), serve sync on the main thread with the
real choice.radio_choice, then re-issue prompt_async with
default=<preserved buffer>. Spike scripts (uncommitted, 07-03
precedent): /tmp/spike_e_child.py + /tmp/spike_e_drive.py.

Evidence (real pty via stdlib pty.openpty — kernel line discipline,
termios, isatty True; NOT a headless fake):
- GO-1 buffer preserved: typed "hello par" (no Enter), approval fired,
  session.default_buffer.text captured "hello par" after cancel,
  re-issued prompt re-rendered it, Enter submitted it intact.
- GO-2 terminal restored: termios iflag/oflag/lflag identical
  before/after (ECHO+ICANON back), child rc=0, no traceback.
- GO-3a Ctrl-C in dialog cancels the dialog: re-issued prompt stayed
  alive, buffer intact, submit worked, rc=0.
- GO-3b Ctrl-C at prompt cancels the line: clean marker, rc=0.

Task 2 implements E in loop.py exactly as spiked. The headless tests
below prove the FIRST_COMPLETED plumbing with stand-ins (07-03 probe-2
shape); the pty tests re-prove GO-1/GO-2/GO-3 against real
prompt_toolkit and skip where no pty exists. No live model, no network.
"""

import asyncio
import os
import select
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _has_pty() -> bool:
    try:
        import pty

        master, slave = pty.openpty()
    except (ImportError, OSError):
        return False
    os.close(master)
    os.close(slave)
    return True


class TestFirstCompletedPlumbing:
    """Headless FIRST_COMPLETED shape with stand-ins (07-03 probe-2)."""

    @staticmethod
    def _race(prompt_result=None, prompt_delay=10.0, poll_delay=0.0):
        """Mirror of the spiked episode: prompt vs broker-poll race.

        Returns ("line", text) or ("approval", None); the loser is
        cancelled and the loop quiesces before returning.
        """

        async def _fake_prompt():
            await asyncio.sleep(prompt_delay)
            return prompt_result

        async def _fake_poll():
            await asyncio.sleep(poll_delay)
            return "APPROVAL"

        async def _main():
            loop = asyncio.get_running_loop()
            prompt_task = loop.create_task(_fake_prompt())
            poll_task = loop.create_task(_fake_poll())
            done, pending = await asyncio.wait(
                {prompt_task, poll_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except BaseException:
                    pass
            if prompt_task in done:
                return ("line", prompt_task.result())
            return ("approval", None)

        return asyncio.run(_main())

    def test_approval_wins_cancels_prompt(self):
        kind, text = self._race(prompt_result="typed", prompt_delay=10.0, poll_delay=0.0)
        assert (kind, text) == ("approval", None)

    def test_line_wins_cancels_poll(self):
        kind, text = self._race(prompt_result="typed", prompt_delay=0.0, poll_delay=10.0)
        assert (kind, text) == ("line", "typed")

    def test_loser_task_settles(self):
        """After the race no task is left pending (quiesce, no leak)."""
        seen: list = []

        async def _fake_prompt():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                seen.append("prompt-cancelled")
                raise
            return "typed"

        async def _fake_poll():
            await asyncio.sleep(0.0)
            return "APPROVAL"

        async def _main():
            loop = asyncio.get_running_loop()
            prompt_task = loop.create_task(_fake_prompt())
            poll_task = loop.create_task(_fake_poll())
            done, pending = await asyncio.wait(
                {prompt_task, poll_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except BaseException:
                    pass
            return prompt_task, poll_task

        prompt_task, poll_task = asyncio.run(_main())
        assert prompt_task.cancelled()
        assert poll_task.done() and not poll_task.cancelled()
        assert seen == ["prompt-cancelled"]


class _PtyFail(Exception):
    pass


class _PtyDriver:
    """Minimal expect-driver over a real pty (stdlib only)."""

    def __init__(self, scenario: str):
        import pty

        self.master, self.slave = pty.openpty()
        self.before = termios.tcgetattr(self.slave)
        env = dict(os.environ, TERM="xterm-256color")
        self.proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "child", scenario],
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            cwd=str(REPO_ROOT),
            env=env,
            close_fds=True,
        )
        self.buf = b""
        self.deadline = time.time() + 60.0

    def expect(self, needle: bytes, what: str) -> None:
        while needle not in self.buf:
            remaining = self.deadline - time.time()
            if remaining <= 0:
                raise _PtyFail(f"timeout waiting for {what}; saw: {self.buf[-600:]!r}")
            ready, _, _ = select.select([self.master], [], [], min(5.0, remaining))
            if not ready:
                continue
            try:
                chunk = os.read(self.master, 4096)
            except OSError as exc:
                raise _PtyFail(f"pty read failed waiting for {what}: {exc}")
            if not chunk:
                if self.proc.poll() is not None:
                    raise _PtyFail(
                        f"child exited rc={self.proc.returncode} waiting for "
                        f"{what}; saw: {self.buf[-600:]!r}"
                    )
                continue
            self.buf += chunk

    def send(self, data: bytes) -> None:
        time.sleep(0.2)
        os.write(self.master, data)

    def finish(self) -> None:
        try:
            rc = self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise _PtyFail(f"child hung; saw: {self.buf[-600:]!r}")
        assert rc == 0, f"child rc={rc}; saw: {self.buf[-600:]!r}"
        assert b"Traceback" not in self.buf, f"traceback; saw: {self.buf[-1200:]!r}"
        after = termios.tcgetattr(self.slave)
        for idx, name in ((0, "iflag"), (1, "oflag"), (3, "lflag")):
            assert self.before[idx] == after[idx], f"termios {name} not restored"

    def close(self) -> None:
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.mark.skipif(not _has_pty(), reason="no pty available")
class TestLiveIdleMultiplex:
    """GO-1/GO-2/GO-3 re-proven in-suite against real prompt_toolkit."""

    def _drive(self, scenario: str) -> _PtyDriver:
        return _PtyDriver(scenario)

    def test_buffer_preserved_across_reissue(self):
        driver = self._drive("serve")
        try:
            driver.expect(b"SPIKE:ready", "ready")
            time.sleep(0.5)
            driver.send(b"hello par")
            driver.expect(b"SPIKE:dialog-open", "dialog-open marker")
            driver.expect(b"Approve?", "dialog frame")
            driver.send(b"\x1b[B")
            driver.send(b"\r")
            driver.expect(b"SPIKE:served=n", "serve marker")
            driver.expect(b"SPIKE:buffer=hello par", "buffer capture")
            driver.expect(b"hello par", "re-issued buffer render")
            driver.send(b"\r")
            driver.expect(b"SPIKE:submitted=hello par", "submit after re-issue")
            driver.expect(b"SPIKE:done rc=0", "clean exit")
            driver.finish()
        finally:
            driver.close()

    def test_terminal_state_restored_after_serve(self):
        driver = self._drive("serve")
        try:
            driver.expect(b"SPIKE:ready", "ready")
            time.sleep(0.5)
            driver.send(b"hello par")
            driver.expect(b"SPIKE:dialog-open", "dialog-open marker")
            driver.expect(b"Approve?", "dialog frame")
            driver.send(b"\r")
            driver.expect(b"SPIKE:served=", "serve marker")
            driver.send(b"\r")
            driver.expect(b"SPIKE:done rc=0", "clean exit")
            driver.finish()  # asserts rc 0, no traceback, termios restored
            assert driver.before[3] & termios.ECHO
            assert driver.before[3] & termios.ICANON
        finally:
            driver.close()

    def test_ctrl_c_in_dialog_cancels_dialog(self):
        driver = self._drive("ctrlc_dialog")
        try:
            driver.expect(b"SPIKE:ready", "ready")
            time.sleep(0.5)
            driver.send(b"hello par")
            driver.expect(b"SPIKE:dialog-open", "dialog-open marker")
            driver.expect(b"Approve?", "dialog frame")
            driver.send(b"\x03")
            driver.expect(b"SPIKE:cancelled=dialog", "dialog cancel")
            driver.expect(b"hello par", "re-issued buffer render after Ctrl-C")
            driver.send(b"\r")
            driver.expect(b"SPIKE:submitted=hello par", "submit after dialog Ctrl-C")
            driver.expect(b"SPIKE:done rc=0", "clean exit")
            driver.finish()
        finally:
            driver.close()

    def test_ctrl_c_at_prompt_cancels_line(self):
        driver = self._drive("ctrlc_prompt")
        try:
            driver.expect(b"SPIKE:ready", "ready")
            time.sleep(0.5)
            driver.send(b"hello")
            driver.send(b"\x03")
            driver.expect(b"SPIKE:cancelled=prompt", "prompt cancel")
            driver.expect(b"SPIKE:done rc=0", "clean exit")
            driver.finish()
        finally:
            driver.close()


class _FakeBuffer:
    def __init__(self, text: str = ""):
        self.text = text


class _FakeSession:
    """PromptSession double: scripted prompt_async results, default capture."""

    def __init__(self, script, buffer_text: str = ""):
        self._script = list(script)
        self.defaults: list = []
        self.default_buffer = _FakeBuffer(buffer_text)
        self.sync_calls: list = []

    async def prompt_async(self, message: str, default: str = ""):
        self.defaults.append(default)
        result = self._script.pop(0)
        if isinstance(result, BaseException):
            raise result
        if result == "HANG":
            await asyncio.sleep(30)
            return "never"
        return result

    def prompt(self, message: str):
        self.sync_calls.append(message)
        return "sync-line"


class _FakeRequest:
    def __init__(self, cancel=None, on_prompt=None):
        self.cancel = cancel
        self._on_prompt = on_prompt
        self.served = 0
        self.aborted = 0

    def run_prompt(self):
        self.served += 1
        if self._on_prompt is not None:
            self._on_prompt()

    def abort(self):
        self.aborted += 1


class _FakeBroker:
    """ApprovalBroker double: scripted pending flag plus request queue."""

    def __init__(self, requests=()):
        self._requests = list(requests)

    @property
    def has_pending(self) -> bool:
        return bool(self._requests)

    def poll(self, timeout: float = 0.05):
        if self._requests:
            return self._requests.pop(0)
        return None


def _fake_btw():
    import threading
    from types import SimpleNamespace

    return SimpleNamespace(cancel_event=threading.Event(), approval_announced=False)


class TestIdleMultiplexBranch:
    """GO branch: canned broker events serve at idle (hermetic, no tty)."""

    def test_serves_canned_approval_at_idle(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        req = _FakeRequest()
        broker = _FakeBroker([req])
        session = _FakeSession(["HANG", "typed line"], buffer_text="half typed")
        btw = _fake_btw()
        assert _idle_prompt_multiplexed(session, broker, btw) == "typed line"
        assert req.served == 1  # served without a submitted turn
        assert btw.approval_announced is False  # latch bypassed: immediate

    def test_prompt_reissued_with_preserved_buffer(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        req = _FakeRequest()
        broker = _FakeBroker([req])
        session = _FakeSession(["HANG", "typed line"], buffer_text="half typed")
        assert _idle_prompt_multiplexed(session, broker, _fake_btw()) == "typed line"
        assert session.defaults == ["", "half typed"]

    def test_line_wins_without_approval(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        broker = _FakeBroker()  # nothing pending, nothing queued
        session = _FakeSession(["just a line"])
        assert _idle_prompt_multiplexed(session, broker, _fake_btw()) == "just a line"
        assert session.defaults == [""]  # single episode, no serve, no re-issue

    def test_dialog_ctrl_c_cancels_side_and_reissues(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        def _interrupt():
            raise KeyboardInterrupt

        req = _FakeRequest(on_prompt=_interrupt)
        broker = _FakeBroker([req])
        session = _FakeSession(["HANG", "after cancel"], buffer_text="kept")
        btw = _fake_btw()
        assert _idle_prompt_multiplexed(session, broker, btw) == "after cancel"
        assert req.aborted == 1  # waiter unblocked, never wedged
        assert btw.cancel_event.is_set()  # side run cancelled, not orphaned
        assert session.defaults == ["", "kept"]  # line survives the cancel

    def test_prompt_ctrl_c_cancels_line(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        session = _FakeSession([KeyboardInterrupt()])
        with pytest.raises(KeyboardInterrupt):
            _idle_prompt_multiplexed(session, _FakeBroker(), _fake_btw())

    def test_prompt_eof_propagates(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        session = _FakeSession([EOFError()])
        with pytest.raises(EOFError):
            _idle_prompt_multiplexed(session, _FakeBroker(), _fake_btw())

    def test_no_broker_falls_back_to_sync_prompt(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        session = _FakeSession(["unused"])
        assert _idle_prompt_multiplexed(session, None, _fake_btw()) == "sync-line"
        assert session.sync_calls == ["> "]
        assert session.defaults == []

    def test_prompt_only_session_falls_back_to_sync_prompt(self):
        from strands_code_cli.loop import _idle_prompt_multiplexed

        class _SyncOnly:
            def prompt(self, message):
                return "sync-line"

        req = _FakeRequest()
        broker = _FakeBroker([req])  # pending, but the session can't race
        assert _idle_prompt_multiplexed(_SyncOnly(), broker, _fake_btw()) == "sync-line"
        assert req.served == 0  # legacy blocking prompt, never multiplexed

    def test_dead_request_skipped_without_dialog(self):
        import threading

        from strands_code_cli.loop import _idle_prompt_multiplexed

        dead = threading.Event()
        dead.set()
        req = _FakeRequest(cancel=dead)
        broker = _FakeBroker([req])
        session = _FakeSession(["HANG", "typed line"])
        assert _idle_prompt_multiplexed(session, broker, _fake_btw()) == "typed line"
        assert req.served == 0  # dead-tag drain ate it: no phantom dialog
        assert req.aborted == 1


def _child_main(scenario: str) -> int:
    """Spiked episode shape, self-contained for the pty tests.

    Real PromptSession.prompt_async raced against a broker-poll
    stand-in; on approval cancel + quiesce, serve sync with the real
    radio_choice, re-issue with the preserved buffer.
    """
    sys.path.insert(0, str(REPO_ROOT))
    import asyncio as _asyncio
    import threading as _threading
    import time as _time

    from prompt_toolkit import PromptSession as _PromptSession

    from strands_code_cli.choice import radio_choice as _radio_choice

    approval = _threading.Event()

    def _timer() -> None:
        _time.sleep(1.2)
        approval.set()

    async def _poll_broker() -> str:
        while True:
            await _asyncio.sleep(0.05)
            if approval.is_set():
                return "APPROVAL"

    def _race(session, buf: str):
        loop = _asyncio.new_event_loop()
        try:
            _asyncio.set_event_loop(loop)

            async def _main():
                prompt_task = loop.create_task(session.prompt_async("> ", default=buf))
                poll_task = loop.create_task(_poll_broker())
                done, pending = await _asyncio.wait(
                    {prompt_task, poll_task}, return_when=_asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    try:
                        await task
                    except BaseException:
                        pass
                if prompt_task in done:
                    return ("line", prompt_task.result())
                return ("approval", session.default_buffer.text)

            return loop.run_until_complete(_main())
        finally:
            try:
                loop.close()
            finally:
                _asyncio.set_event_loop(None)

    session = _PromptSession("> ")
    buf = ""
    if scenario != "ctrlc_prompt":
        _threading.Thread(target=_timer, daemon=True).start()
    print("SPIKE:ready", flush=True)
    try:
        while True:
            try:
                kind, text = _race(session, buf)
            except KeyboardInterrupt:
                print("SPIKE:cancelled=prompt", flush=True)
                print("SPIKE:done rc=0", flush=True)
                return 0
            if kind == "line":
                print(f"SPIKE:submitted={text}", flush=True)
                print("SPIKE:done rc=0", flush=True)
                return 0
            print(f"SPIKE:buffer={text}", flush=True)
            buf = text
            print("SPIKE:dialog-open", flush=True)
            try:
                answer = _radio_choice(
                    "[btw] Approve?", (("y", "Yes"), ("n", "No")), default=1
                )
            except KeyboardInterrupt:
                print("SPIKE:cancelled=dialog", flush=True)
                approval.clear()
                continue
            print(f"SPIKE:served={answer}", flush=True)
            approval.clear()
    except Exception as exc:  # noqa: BLE001 — child must report, not hang
        print(f"SPIKE:exception={type(exc).__name__}:{exc}", flush=True)
        return 1


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "child":
    sys.exit(_child_main(sys.argv[2]))
