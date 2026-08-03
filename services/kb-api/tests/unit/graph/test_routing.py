"""Router tests — route_after_relevance_check (src/rag/graph/routing.py).

Covers every branch of the deterministic router described in
docs/graph-design/target-graph-design.md (R2 decision point).
"""
from __future__ import annotations

from src.rag.graph.routing import route_after_relevance_check
from src.rag.graph.state import RetrievalGraphState


def _state(*, sufficient: bool, retry_count: int) -> RetrievalGraphState:
    state = RetrievalGraphState.new("問題")
    object.__setattr__(state, "relevance_sufficient", sufficient)
    object.__setattr__(state, "retry_count", retry_count)
    return state


def test_route_sufficient_goes_to_build_context():
    state = _state(sufficient=True, retry_count=0)
    assert route_after_relevance_check(state) == "build_context"


def test_route_insufficient_with_retry_budget_goes_to_rewrite():
    # MAX_ITERATIONS = 2 → retry_count=0 still has budget for one more attempt
    state = _state(sufficient=False, retry_count=0)
    assert route_after_relevance_check(state) == "rewrite"


def test_route_insufficient_retry_exhausted_falls_back_to_build_context():
    state = _state(sufficient=False, retry_count=1)
    assert route_after_relevance_check(state) == "build_context"


def test_route_sufficient_overrides_retry_count():
    # even mid-retry, a sufficient verdict should short-circuit to build_context
    state = _state(sufficient=True, retry_count=1)
    assert route_after_relevance_check(state) == "build_context"
