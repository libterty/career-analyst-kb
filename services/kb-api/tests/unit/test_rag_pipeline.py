"""Unit tests for RAGPipeline (src/rag/pipeline.py).

Infrastructure (Milvus, LLM, embedder) is fully mocked.
Only the pure logic — _build_context and _retrieve routing — is tested here.
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Extra stubs needed to import src.rag.pipeline in the host venv.
# conftest.py already registers: langchain.*, fastapi, sqlalchemy, rank_bm25,
# jieba, pymilvus.  We register the remaining infra modules here.
# ---------------------------------------------------------------------------
for _name in [
    "src.core.llm_factory",
    "src.ingestion.embedder",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

# Provide a passthrough build_llm so the module attribute is a callable mock
sys.modules["src.core.llm_factory"].build_llm = MagicMock(return_value=MagicMock())

from src.core.domain.search_result import SearchResult
from src.rag.pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(chunk_id: str, content: str, section: str = "sec") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section=section, score=0.8)


# ---------------------------------------------------------------------------
# _build_context — static method, no infrastructure needed
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_empty_results_returns_placeholder(self):
        result = RAGPipeline._build_context([])
        assert result == "（未找到相關段落）"

    def test_single_result_with_section(self):
        text = RAGPipeline._build_context([_sr("a", "內容A", section="面試技巧")])
        assert "[1]" in text
        assert "【面試技巧】" in text
        assert "內容A" in text

    def test_single_result_without_section(self):
        text = RAGPipeline._build_context([_sr("a", "內容A", section="")])
        assert "[1]" in text
        assert "【】" not in text
        assert "內容A" in text

    def test_multiple_results_numbered_sequentially(self):
        results = [_sr(str(i), f"doc{i}", section=f"S{i}") for i in range(3)]
        text = RAGPipeline._build_context(results)
        assert "[1]" in text
        assert "[2]" in text
        assert "[3]" in text
        assert "[4]" not in text

    def test_results_separated_by_double_newline(self):
        results = [_sr("a", "first"), _sr("b", "second")]
        text = RAGPipeline._build_context(results)
        assert "\n\n" in text

    def test_all_content_included(self):
        results = [_sr("a", "alpha", "S1"), _sr("b", "beta", "S2")]
        text = RAGPipeline._build_context(results)
        assert "alpha" in text
        assert "beta" in text
        assert "S1" in text
        assert "S2" in text


# ---------------------------------------------------------------------------
# _retrieve — routing between Langfuse-traced and plain paths
# ---------------------------------------------------------------------------

class TestRetrieve:
    def _make_pipeline(self):
        """Build a RAGPipeline with all infra mocked out."""
        with patch("src.rag.pipeline.MilvusRetriever"), \
             patch("src.rag.pipeline.EmbeddingService"), \
             patch("src.rag.pipeline.HybridSearchEngine"), \
             patch("src.rag.pipeline.build_llm", return_value=MagicMock()):
            p = RAGPipeline(milvus_host="localhost", milvus_port=19530)
        return p

    def _inject_search(self, pipeline, results: list[SearchResult]):
        pipeline._search = MagicMock()
        pipeline._search.search.return_value = results
        pipeline._embedder = MagicMock()
        pipeline._embedder.embed_query.return_value = [0.1, 0.2]
        pipeline._prompt_optimizer = MagicMock()
        pipeline._prompt_optimizer.enhance_query.side_effect = lambda q: q
        return pipeline

    def test_retrieve_returns_context_and_results(self):
        p = self._make_pipeline()
        sr = _sr("a", "some content")
        self._inject_search(p, [sr])

        context, results = p._retrieve("問題")

        assert results == [sr]
        assert "some content" in context

    def test_retrieve_empty_results_returns_placeholder_context(self):
        p = self._make_pipeline()
        self._inject_search(p, [])

        context, results = p._retrieve("問題")

        assert results == []
        assert context == "（未找到相關段落）"

    def test_retrieve_calls_enhance_query(self):
        p = self._make_pipeline()
        self._inject_search(p, [])
        p._prompt_optimizer.enhance_query.side_effect = lambda q: q.upper()

        p._retrieve("hello")

        p._prompt_optimizer.enhance_query.assert_called_once_with("hello")
        p._embedder.embed_query.assert_called_once_with("HELLO")

    def test_retrieve_skips_langfuse_when_no_client(self):
        p = self._make_pipeline()
        self._inject_search(p, [_sr("a", "c")])

        with patch("src.rag.pipeline.langfuse_client", return_value=None):
            context, results = p._retrieve("q")

        assert len(results) == 1

    def test_retrieve_uses_langfuse_span_when_available(self):
        p = self._make_pipeline()
        self._inject_search(p, [_sr("a", "c")])

        fake_obs = MagicMock()
        fake_obs.__enter__ = MagicMock(return_value=fake_obs)
        fake_obs.__exit__ = MagicMock(return_value=False)
        fake_lf = MagicMock()
        fake_lf.start_as_current_observation.return_value = fake_obs

        with patch("src.rag.pipeline.langfuse_client", return_value=fake_lf), \
             patch("src.rag.pipeline.langfuse_trace_id_var") as tv:
            tv.get.return_value = "trace-123"
            p._retrieve("q")

        fake_lf.start_as_current_observation.assert_called_once()
        fake_obs.update.assert_called_once()
