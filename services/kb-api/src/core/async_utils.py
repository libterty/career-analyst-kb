"""Helpers for offloading blocking, synchronous calls from the event loop.

FastAPI/uvicorn run a single event loop per worker process. Any synchronous
call left un-awaited inside an ``async def`` (e.g. a Milvus search or an
LLM ``.invoke()``) blocks that entire loop — not just the request that
triggered it, but every other concurrent request on the same worker,
including unrelated ones like ``/health``. Wrap such calls with
``run_blocking`` instead of calling them directly.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar("T")


async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking, synchronous callable in the default thread pool executor.

    Two things `loop.run_in_executor()` alone doesn't give you:

    * Keyword arguments — ``run_in_executor`` only accepts positional args,
      so this wraps the call to accept both.
    * A `StopIteration` guard — if the callable raises `StopIteration`
      (e.g. a `Mock(side_effect=[...])` running out of values), it surfaces
      inside the worker thread, not inside this coroutine's frame, so PEP 479's
      automatic StopIteration→RuntimeError conversion does not apply.
      `asyncio.Future.set_exception()` then refuses to carry a raw
      `StopIteration`, which leaves the awaiting coroutine stuck forever
      instead of raising. This re-raises it as `RuntimeError` before it
      reaches the Future, matching what PEP 479 would have done anyway.

    Note: this does NOT propagate ``contextvars`` into the worker thread
    (`loop.run_in_executor` never does). If the callable reads a contextvar
    (e.g. a Langfuse trace id), use `asyncio.to_thread` at the call site
    instead, which copies the current context automatically.
    """
    loop = asyncio.get_running_loop()

    def _call() -> T:
        try:
            return func(*args, **kwargs)
        except StopIteration as exc:
            raise RuntimeError(f"StopIteration raised from blocking call {func!r}") from exc

    return await loop.run_in_executor(None, _call)
