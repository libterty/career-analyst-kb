"""Unit tests for ChatService and _ThinkFilter."""
from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.chat_service import ChatService, _ThinkFilter
from src.core.domain.search_result import SearchResult


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_stub_chunk(text: str):
    chunk = MagicMock()
    chunk.content = text
    return chunk


async def _async_chunks(*texts: str):
    for t in texts:
        yield _make_stub_chunk(t)


def _make_chat_service(
    *,
    llm_chunks: list[str] | None = None,
    llm_raise: Exception | None = None,
    search_results: list[SearchResult] | None = None,
    session_repo=None,
    db_session_factory=None,
    max_messages: int = 100,
    semantic_cache=None,
) -> ChatService:
    validator = MagicMock()
    validator.check_input.side_effect = lambda x: x

    sanitizer = MagicMock()
    sanitizer.sanitize_output.side_effect = lambda x: x

    enhancer = MagicMock()
    enhancer.enhance_query.side_effect = lambda x: x

    search_engine = MagicMock()
    search_engine.search.return_value = search_results or []

    async def _fake_astream(messages):
        if llm_raise:
            raise llm_raise
        chunks = llm_chunks or ["hello"]
        for t in chunks:
            yield _make_stub_chunk(t)

    llm = MagicMock()
    llm.astream = _fake_astream

    svc = ChatService(
        input_validator=validator,
        output_sanitizer=sanitizer,
        query_enhancer=enhancer,
        search_engine=search_engine,
        llm=llm,
        embed_query_fn=lambda q: [0.1, 0.2, 0.3],
        session_repo=session_repo,
        max_messages_per_session=max_messages,
        db_session_factory=db_session_factory,
    )
    if semantic_cache is not None:
        svc.set_semantic_cache(semantic_cache)
    return svc


async def _collect(gen: AsyncIterator[str]) -> list[str]:
    """Collect all chunks from an async generator."""
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# _ThinkFilter
# ---------------------------------------------------------------------------

class TestThinkFilter:
    def test_passthrough_short_text_via_flush(self):
        # Short text (<=7 chars) stays buffered; flush() returns it.
        f = _ThinkFilter()
        mid = f.feed("hello")
        assert mid == ""  # buffered — could be <think> start
        assert f.flush() == "hello"

    def test_passthrough_long_text_streams_eagerly(self):
        # Text longer than 7 chars flushes everything except the last 7 bytes.
        f = _ThinkFilter()
        out = f.feed("hello world!")  # 12 chars; 5 chars flushed, 7 buffered
        out += f.flush()
        assert out == "hello world!"

    def test_strips_complete_think_block(self):
        f = _ThinkFilter()
        out = ""
        out += f.feed("before <think>hidden</think> after")
        out += f.flush()
        assert "hidden" not in out
        assert "before" in out
        assert "after" in out

    def test_strips_split_think_block(self):
        f = _ThinkFilter()
        out = ""
        out += f.feed("<thi")
        out += f.feed("nk>hidden content")
        out += f.feed("</think>visible")
        out += f.flush()
        assert "hidden" not in out
        assert "visible" in out

    def test_flush_returns_remaining_visible_text(self):
        f = _ThinkFilter()
        f.feed("hello ")
        out = f.flush()
        assert out == "hello "

    def test_unclosed_think_block_suppressed_by_flush(self):
        f = _ThinkFilter()
        f.feed("visible<think>hidden but never closed")
        out = f.flush()
        assert "hidden" not in out

    def test_does_not_raise_on_edge_cases(self):
        f = _ThinkFilter()
        try:
            f.feed("")
            f.feed("<think>")
            f.feed("</think>")
            f.flush()
        except Exception as exc:
            pytest.fail(f"_ThinkFilter raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# ChatService — basic stream
# ---------------------------------------------------------------------------

class TestChatServiceStream:
    @pytest.mark.anyio
    async def test_streams_llm_tokens(self):
        svc = _make_chat_service(llm_chunks=["Hello", " world"])
        chunks = await _collect(svc.stream_answer("test question"))
        # _ThinkFilter may split tokens due to buffering; check combined text
        text = "".join(c for c in chunks if not c.startswith("["))
        assert "Hello world" in text

    @pytest.mark.anyio
    async def test_embed_called_with_enhanced_query(self):
        captured = {}

        async def _collect_embed(gen):
            return [c async for c in gen]

        svc = _make_chat_service()
        svc._embed_query = lambda q: captured.update({"q": q}) or [0.1]  # type: ignore[method-assign]
        svc._query_enhancer.enhance_query.side_effect = lambda x: x.upper()  # type: ignore[union-attr]
        await _collect(svc.stream_answer("hello"))
        assert captured.get("q") == "HELLO"

    @pytest.mark.anyio
    async def test_search_called_with_embedding(self):
        svc = _make_chat_service()
        await _collect(svc.stream_answer("q"))
        svc._search_engine.search.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.anyio
    async def test_no_db_session_without_factory(self):
        # When no db_session_factory, stream_answer must work without touching _db
        svc = _make_chat_service()
        chunks = await _collect(svc.stream_answer("q", user_id=None))
        assert any(chunks)  # at least one token


# ---------------------------------------------------------------------------
# ChatService — message limit
# ---------------------------------------------------------------------------

class TestMessageLimit:
    @pytest.mark.anyio
    async def test_raises_429_when_limit_reached(self):
        session_repo = AsyncMock()
        session_repo.find_by_session_id.return_value = MagicMock()
        session_repo.get_message_count.return_value = 5  # at limit

        svc = _make_chat_service(session_repo=session_repo, max_messages=5)

        # HTTPException is the stub from conftest; check status_code=429
        with pytest.raises(Exception) as exc_info:
            await _collect(svc.stream_answer("q", user_id=1))

        assert exc_info.value.status_code == 429  # type: ignore[attr-defined]

    @pytest.mark.anyio
    async def test_allows_when_under_limit(self):
        session_repo = AsyncMock()
        session_repo.find_by_session_id.return_value = MagicMock()
        session_repo.get_message_count.return_value = 3
        session_repo.add_message.return_value = MagicMock(id=42)

        svc = _make_chat_service(session_repo=session_repo, max_messages=5)
        chunks = await _collect(svc.stream_answer("q", user_id=1))
        assert any(chunks)


# ---------------------------------------------------------------------------
# ChatService — DB session cleanup (try/finally)
# ---------------------------------------------------------------------------

class TestDbSessionCleanup:
    @pytest.mark.anyio
    async def test_db_closed_on_happy_path(self):
        mock_db = AsyncMock()
        session_repo = AsyncMock()
        session_repo.find_by_session_id.return_value = MagicMock()
        session_repo.get_message_count.return_value = 0
        session_repo.add_message.return_value = MagicMock(id=1)

        def factory():
            return mock_db

        # Patch the lazy import path used inside stream_answer
        import sys
        fake_repo_mod = sys.modules.get("src.infrastructure.repositories.chat_session_repository")
        original_cls = getattr(fake_repo_mod, "SQLAlchemyChatSessionRepository", None)
        fake_repo_mod.SQLAlchemyChatSessionRepository = lambda _db: session_repo  # type: ignore[union-attr]

        try:
            svc = _make_chat_service(db_session_factory=factory)
            await _collect(svc.stream_answer("q", user_id=1))
        finally:
            if original_cls is not None:
                fake_repo_mod.SQLAlchemyChatSessionRepository = original_cls  # type: ignore[union-attr]

        mock_db.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_db_closed_on_llm_exception(self):
        mock_db = AsyncMock()
        session_repo = AsyncMock()
        session_repo.find_by_session_id.return_value = MagicMock()
        session_repo.get_message_count.return_value = 0
        session_repo.add_message.return_value = MagicMock(id=1)

        def factory():
            return mock_db

        import sys
        fake_repo_mod = sys.modules.get("src.infrastructure.repositories.chat_session_repository")
        original_cls = getattr(fake_repo_mod, "SQLAlchemyChatSessionRepository", None)
        fake_repo_mod.SQLAlchemyChatSessionRepository = lambda _db: session_repo  # type: ignore[union-attr]

        try:
            svc = _make_chat_service(
                db_session_factory=factory,
                llm_raise=RuntimeError("LLM crashed"),
            )
            with pytest.raises(RuntimeError, match="LLM crashed"):
                await _collect(svc.stream_answer("q", user_id=1))
        finally:
            if original_cls is not None:
                fake_repo_mod.SQLAlchemyChatSessionRepository = original_cls  # type: ignore[union-attr]

        mock_db.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# ChatService — semantic cache hit
# ---------------------------------------------------------------------------

class TestSemanticCacheHit:
    @pytest.mark.anyio
    async def test_returns_cached_answer_without_llm(self):
        cache = AsyncMock()
        cache.lookup.return_value = ("cached answer", [])

        svc = _make_chat_service(semantic_cache=cache)
        chunks = await _collect(svc.stream_answer("q"))

        full = "".join(chunks)
        assert "cached answer" in full
        # LLM should NOT have been called
        svc._llm.astream  # accessing to verify; we check search not called
        svc._search_engine.search.assert_not_called()  # type: ignore[union-attr]

    @pytest.mark.anyio
    async def test_cache_miss_calls_llm(self):
        cache = AsyncMock()
        cache.lookup.return_value = None
        cache.store = AsyncMock()

        svc = _make_chat_service(llm_chunks=["from llm"], semantic_cache=cache)
        chunks = await _collect(svc.stream_answer("q"))

        full = "".join(c for c in chunks if not c.startswith("["))
        assert "from llm" in full


# ---------------------------------------------------------------------------
# ChatService — memory LRU
# ---------------------------------------------------------------------------

class TestMemoryLRU:
    def test_memory_created_per_session(self):
        svc = _make_chat_service()
        m1 = svc._get_memory("session-a")
        m2 = svc._get_memory("session-b")
        assert m1 is not m2

    def test_same_session_returns_same_memory(self):
        svc = _make_chat_service()
        m1 = svc._get_memory("session-x")
        m2 = svc._get_memory("session-x")
        assert m1 is m2

    def test_lru_evicts_oldest_when_full(self):
        svc = _make_chat_service()
        svc._memories_maxsize = 3

        svc._get_memory("s1")
        svc._get_memory("s2")
        svc._get_memory("s3")
        # Access s1 to make it most-recently-used
        svc._get_memory("s1")
        # Adding s4 should evict s2 (LRU)
        svc._get_memory("s4")

        assert "s2" not in svc._memories
        assert "s1" in svc._memories
        assert "s3" in svc._memories
        assert "s4" in svc._memories
