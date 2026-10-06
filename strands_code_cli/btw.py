"""Mid-turn /btw side channel: parallel side agent, fenced delivery (LOOP-03).

A ``/btw <question>`` line typed mid-turn carves out of steering (see
:mod:`strands_code_cli.steering`) and spawns a side agent that runs in
parallel with the main turn: same model, same tools, same approval
gate, forked main history, recall-only shared memory. Its answer
streams live as a fenced block while main output flows outside it, and
the Q&A appends to main history at the turn boundary.

Threading contract: the steering reader thread only enqueues the
question; the main-thread pump builds and submits the side agent, so
agent construction never happens off the main thread. Both callback
handlers serialize whole message blocks on :data:`RENDER_LOCK`, so
fenced side blocks never tear against main output. Workers never open
:func:`~strands_code_cli.output.output_context` — they print into the
turn's already-open proxy.
"""

from __future__ import annotations

import copy
import queue
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from strands_harness import create_harness
from strands_harness.memory import resolve_memory

from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_cli.memory_file import load_memory, register_memory_plugin
from strands_code_cli.output import print_plain

RENDER_LOCK = threading.Lock()
"""Serializes whole message blocks across the main and btw handlers.

Rich serializes single ``print`` calls internally, but a fenced side
block is a header+body+footer sequence — only this shared lock keeps
it contiguous against main output.
"""

console = Console()

BTW_QUESTION_CHARS = 60
"""Question prefix length carried in the fence header (single line)."""

BTW_USAGE = "Usage: /btw <side question>"
"""Idle usage text; also the mid-turn reply for a bare ``/btw`` line."""

BTW_NOTED = "Side question noted — answering in parallel."
"""Submit echo when no side answer runs (idle-side submit)."""

BTW_QUEUED_TEMPLATE = "Side question queued (#{depth} in line) — answering in parallel."
"""Submit echo when a side answer runs (``{depth}`` is the post-put depth)."""

BTW_FRAMING = (
    "Side task: answer the trailing btw question directly and concisely; "
    "the main task continues in parallel and your answer lands as a fenced side block."
)
"""One framing line appended to the side agent's instructions."""

BTW_FORK_PREAMBLE = (
    "The conversation so far is the main agent's. You are its side channel answering "
    "the btw question below while the main task continues."
)
"""Frames the forked history's trailing question (mirrors the harness fork preamble)."""


def _fence_title(question: str) -> str:
    """Single-line fence title: first 60 chars of the question."""
    return " ".join(question.split())[:BTW_QUESTION_CHARS]


class LockedHandler:
    """Render-lock proxy around a callback handler (behavior-preserving).

    Forwards every ``__call__`` kwarg bundle to the inner handler with
    the whole message block held under :data:`RENDER_LOCK`, so main
    output and fenced side blocks interleave only at block granularity.
    Exposes the wrapped handler as :attr:`inner`.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def __call__(self, **kwargs: Any) -> Any:
        with RENDER_LOCK:
            return self.inner(**kwargs)


class FencedBtwHandler:
    """Fenced side-block wrapper around the shared callback handler.

    Prints the ``--- btw: <question> ---`` header, delegates the
    message to the inner (shared, locked) handler, then prints the
    ``--- end btw ---`` footer — all three under :data:`RENDER_LOCK`
    so the block lands contiguously. Messages without content return
    None with no fence (no empty blocks for metadata-only events).
    """

    def __init__(self, inner: Any, question: str) -> None:
        self.inner = inner
        self.question = question
        owned = getattr(inner, "console", None)
        self.console = owned if isinstance(owned, Console) else Console()

    def __call__(self, **kwargs: Any) -> None:
        message = kwargs.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not content:
            return None
        with RENDER_LOCK:
            print_plain(self.console, f"--- btw: {_fence_title(self.question)} ---")
            try:
                self.inner(**kwargs)
            finally:
                print_plain(self.console, "--- end btw ---")
        return None


def render_btw_error(question: str, exc: BaseException) -> None:
    """Render a side failure as a fenced error block (never silent).

    Same fence shape as answers; the body names the exception so a
    failed side run stays visible in the transcript.
    """
    with RENDER_LOCK:
        print_plain(console, f"--- btw: {_fence_title(question)} ---")
        print_plain(console, f"btw failed ({type(exc).__name__}): {exc}")
        print_plain(console, "--- end btw ---")


def fork_btw_history(messages: list | None, question: str) -> list:
    """Fork parent history for the side agent (replicated harness "all").

    Replicates the ``strands-harness`` 0.1.2 ``_fork_messages`` "all"
    algorithm (never import harness privates across the package
    boundary): deep-copy, drop ``toolUse`` blocks with no matching
    ``toolResult``, strip all ``reasoningContent`` blocks, drop
    messages left empty. The framed btw question becomes the trailing
    user turn — absorbed into the trailing message when it is already
    user-role, so emitted roles strictly alternate (per the harness
    ``_with_history`` rule).
    """
    forked: list = []
    answered = {
        block["toolResult"]["toolUseId"]
        for message in (messages or [])
        for block in message.get("content", [])
        if "toolResult" in block
    }
    for message in messages or []:
        content = [
            block
            for block in message.get("content", [])
            if "reasoningContent" not in block
            and ("toolUse" not in block or block["toolUse"].get("toolUseId") in answered)
        ]
        if content:
            forked.append({"role": message["role"], "content": copy.deepcopy(content)})
    framed = {"text": f"{BTW_FORK_PREAMBLE}\n\n{question}"}
    if forked and forked[-1]["role"] == "user":
        forked[-1]["content"].append(framed)
    else:
        forked.append({"role": "user", "content": [framed]})
    return forked


def append_btw_turn(messages: list, question: str, answer: str) -> None:
    """Append one completed side Q&A to main history (boundary flush).

    Main-thread only, at the main-turn boundary: the user turn carries
    the ``/btw`` escape verbatim and the assistant turn the verbatim
    side answer, so the main agent can reference the exchange.
    """
    messages.extend(
        [
            {"role": "user", "content": [{"text": f"/btw {question}"}]},
            {"role": "assistant", "content": [{"text": answer}]},
        ]
    )


def register_btw_cancel(broker: Any, btw: BtwContext) -> None:
    """Bind the side channel's cancel event under ``"btw"`` (spawn time).

    The broker rides a parameter so this module never imports the gate
    layer — the policy_gate → btw ``RENDER_LOCK`` import stays acyclic.
    """
    if broker is not None:
        broker.register_cancel("btw", btw.cancel_event)


def unregister_btw_cancel(broker: Any) -> None:
    """Drop the ``"btw"`` cancel binding (side completion)."""
    if broker is not None:
        broker.unregister_cancel("btw")


class BtwQueue:
    """Unbounded FIFO of side questions with depth-returning submit (D-10).

    Backed by :class:`queue.Queue`: no cap, no eviction, no silent
    loss — the pump spawns one side agent at a time in submit order
    and the depth echo is the attention control. Only stripped
    non-empty question strings are held; blank submits raise rather
    than enqueue a no-op side run.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()

    def put(self, question: str) -> int:
        """Enqueue one question; return the post-put depth (1-based).

        Raises:
            ValueError: When the question is blank after stripping.
        """
        cleaned = question.strip()
        if not cleaned:
            raise ValueError("btw question must not be blank")
        self._queue.put(cleaned)
        return self._queue.qsize()

    def get_nowait(self) -> str:
        """Next queued question (FIFO); raises ``queue.Empty`` when idle."""
        return self._queue.get_nowait()

    def empty(self) -> bool:
        """True when no question waits."""
        return self._queue.empty()

    def qsize(self) -> int:
        """Current queued depth (approximate under concurrency)."""
        return self._queue.qsize()

    @property
    def depth(self) -> int:
        """Alias for :meth:`qsize` (readable submit-site spelling)."""
        return self._queue.qsize()


@dataclass
class BtwContext:
    """Per-turn side-channel state (loop-owned, main-thread driven).

    The reader thread only submits questions into :attr:`spawn_queue`
    via :meth:`submit` (never spawns inline); the pump builds,
    submits, and reaps side agents. Completed turns wait in
    :attr:`pending` as ``(question, answer, result)`` tuples for the
    boundary flush; :attr:`done` flips once a side answer lands.
    :attr:`running` mirrors the side worker's lifetime for the submit
    echo (set while a side agent runs, cleared once drained).
    :attr:`cancel_targets` records the chooser answer (D-08) when a
    turn unwinds through the cancel path, so the loop can run the
    two-press machine per named target.
    """

    spawn_queue: BtwQueue
    build: Callable[[str], tuple[Any, list]]
    cancel_event: threading.Event
    pending: list = field(default_factory=list)
    done: bool = False
    cancel_targets: tuple = ()
    running: threading.Event = field(default_factory=threading.Event)

    def submit(self, question: str) -> int:
        """Enqueue one side question with its visible echo (D-10).

        Reader-thread entry: enqueues, then prints the ``> /btw``
        receipt plus the noted/queued status line — both under
        :data:`RENDER_LOCK` so the echo lands atomically against
        streaming output. A submit while a side answer runs reports
        its queue depth; an idle-side submit reports noted.

        Returns:
            The post-put queue depth (1-based).
        """
        depth = self.spawn_queue.put(question)
        cleaned = question.strip()
        with RENDER_LOCK:
            print_plain(console, f"> /btw {cleaned}")
            if self.running.is_set():
                print_plain(console, BTW_QUEUED_TEMPLATE.format(depth=depth))
            else:
                print_plain(console, BTW_NOTED)
        return depth


def build_btw_agent(
    parent_kwargs: dict[str, Any], history: list, question: str
) -> tuple[Any, list]:
    """Build the side agent via a ``create_harness`` factory rebuild.

    Replays the parent's ``create_harness`` kwargs with the delegate
    overrides: the SAME model/tools/interventions objects (never
    rebuilt), ``session`` forced off, recall-only shared memory, the
    parent hooks minus the steering hook object (dropped by identity
    via the ``steering_hook`` marker key, which is never forwarded),
    instructions plus one btw framing line, and the shared callback
    handler wrapped in :class:`FencedBtwHandler`. The shared memory
    conventions inject via :func:`register_memory_plugin`.

    Args:
        parent_kwargs: The parent's ``create_harness`` keyword
            arguments (never mutated); may carry ``hooks`` plus a
            ``steering_hook`` marker naming the hook object to drop.
        history: Parent ``agent.messages`` snapshot to fork (D-13).
        question: The btw question tail (verbatim, unstripped framing).

    Returns:
        ``(agent, prompt)`` where ``prompt`` is the forked history
        with the framed question as its trailing user turn — the
        side invocation prompt, passed as the agent's message list.
    """
    prompt = fork_btw_history(history, question)
    kwargs = dict(parent_kwargs)
    steering_hook = kwargs.pop("steering_hook", None)
    if "hooks" in kwargs:
        hooks = list(kwargs["hooks"] or [])
        if steering_hook is not None:
            hooks = [hook for hook in hooks if hook is not steering_hook]
        kwargs["hooks"] = hooks
    kwargs["session"] = False
    parent_memory = kwargs.get("memory")
    if parent_memory is None or parent_memory is False:
        kwargs["memory"] = False
    elif isinstance(parent_memory, Mapping):
        kwargs["memory"] = resolve_memory(
            stores=parent_memory.get("stores"),
            memory_dir=parent_memory.get("dir"),
            writable=False,
        )
    else:
        kwargs["memory"] = resolve_memory(writable=False)
    kwargs["instructions"] = f"{CODE_AGENT_INSTRUCTIONS}\n{BTW_FRAMING}"
    kwargs["callback_handler"] = FencedBtwHandler(kwargs["callback_handler"], question)
    agent = create_harness(**kwargs)
    register_memory_plugin(agent, load_memory)
    return agent, prompt
