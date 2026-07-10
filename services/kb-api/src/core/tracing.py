"""Langfuse tracing — lazy initialisation for FastAPI side.

ContextVar pattern:
  Set `langfuse_trace_id_var` before entering async work so that
  `@observe`-decorated methods can link to the parent VoltAgent trace.
  The chat router sets it; the pipeline reads it.

Exports:
  langfuse_client()   — returns a Langfuse client or None when unconfigured
  observe             — re-export of langfuse.observe for convenience

Usage:
  from src.core.tracing import observe

  @observe(name="rag-retrieve")
  def my_fn(...): ...

When LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set the client is
never initialised and @observe is effectively a no-op pass-through.
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from typing import TYPE_CHECKING

langfuse_trace_id_var: ContextVar[str | None] = ContextVar("langfuse_trace_id", default=None)

if TYPE_CHECKING:
    from langfuse import Langfuse

try:
    from langfuse import observe as _observe_real
    from langfuse import Langfuse as _Langfuse

    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False


def _noop_observe(*args, **kwargs):
    """Identity decorator used when langfuse is not installed."""
    def decorator(fn):
        return fn
    if len(args) == 1 and callable(args[0]):
        return args[0]
    return decorator


observe = _observe_real if _LANGFUSE_AVAILABLE else _noop_observe  # type: ignore[assignment]


@lru_cache(maxsize=1)
def langfuse_client() -> "Langfuse | None":
    """Return a Langfuse client if keys are configured, else None."""
    if not _LANGFUSE_AVAILABLE:
        return None
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = os.environ.get("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        return None
    return _Langfuse(
        public_key=pk,
        secret_key=sk,
        host=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
