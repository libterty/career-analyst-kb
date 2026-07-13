# Technical Concerns

**Analysis Date:** 2026-06-27

## Critical Issues

~~**Hardcoded default secret key in production config** — FIXED 2026-07-13~~
~~`lifespan` now raises RuntimeError if SECRET_KEY is still the placeholder and app_env != "development". Also logs a warning if ADMIN_PASSWORD is not set. (`src/api/main.py`)~~

~~**Hardcoded PostgreSQL credentials in default database URL** — FIXED 2026-07-13~~
~~`database_url` no longer has a default value; pydantic-settings raises `ValidationError` at startup if `DATABASE_URL` env var is not set. (`src/core/config.py`)~~

~~**In-memory session memory dict grows unbounded** — FIXED 2026-07-13~~
~~`_memories` is now an `OrderedDict` with LRU eviction at 10 000 sessions (`chat_service.py`).~~

## Technical Debt

~~**Synchronous embedding calls inside async paths** — FIXED 2026-07-13~~
~~All three sync `self._embed_query(...)` calls now use `await asyncio.get_running_loop().run_in_executor(None, self._embed_query, ...)` in both `chat_service.py` and `semantic_cache_service.py`.~~

~~**BM25 corpus cache never invalidated after re-ingestion** — FIXED 2026-07-13~~
~~`ChatService.invalidate_search_cache()` added; ingestion router calls it after subprocess returncode == 0 (`routers/ingestion.py`).~~

~~**Dual-path session repository construction per request with potential connection leak** — FIXED 2026-07-13~~
~~`stream_answer` now wraps the entire generator body in `try/finally`; `_db.close()` is guaranteed to run on both happy path and exception path (`chat_service.py:184-320`).~~

~~**Bare `except Exception: return []` silences Milvus errors** — FIXED 2026-07-13~~
~~`logger.warning(...)` now logs the exception before `return []` in `semantic_cache.py:get_sources()`.~~

~~**`print()` in config module docstring** — FIXED 2026-07-13~~
~~Removed `print(settings.llm_provider)` from the docstring; replaced with bare attribute access example.~~

## Performance Bottlenecks

~~**Full-corpus BM25 rebuild on first query (cold start)** — FIXED 2026-07-13~~
~~`lifespan` startup now calls `svc._search_engine._ensure_bm25_index()` via `run_in_executor` so the index is ready before the first request (`main.py`).~~

~~**Query embedded twice per request on cache miss** — FIXED 2026-07-13~~
~~`stream_answer` computes `query_embedding` once (before step 2.5), passes it to `SemanticCacheService.lookup(query_text, query_embedding)` and reuses it for `search_engine.search`. `lookup` now accepts an optional `query_embedding` parameter.~~

## Missing Functionality

~~**No unit tests for ChatService, RAG pipeline, or HybridSearchEngine** — FIXED 2026-07-13~~
~~Added `test_hybrid_search.py` (16 tests: tokenize, RRF fusion, BM25 path, fallback, invalidation) and `test_rag_pipeline.py` (11 tests: _build_context, _retrieve routing, Langfuse span). Combined with existing `test_chat_service.py`, core RAG logic now has 58 unit tests.~~

~~**No per-endpoint rate limiting on the chat streaming endpoint** — FIXED 2026-07-13~~
~~`src/api/limiter.py` extracts the shared `slowapi.Limiter` instance. `/api/chat/query` (streaming) now limits to 20 req/min/IP; `/api/chat/query/sync` to 10 req/min/IP. `main.py` imports from `limiter.py` to avoid circular deps.~~

~~**No startup warning when `ADMIN_PASSWORD` is unset** — FIXED 2026-07-13~~
~~`lifespan` logs `logger.warning` if `settings.admin_password` is None. (`src/api/main.py:56-57`)~~

## Security Concerns

~~**JWT secret key has a trivially guessable default** — FIXED 2026-07-13~~
~~`lifespan` raises `RuntimeError` if `SECRET_KEY` is still the placeholder and `app_env != "development"`. (`src/api/main.py`)~~

~~**Long access token expiry with no revocation mechanism** — FIXED 2026-07-13~~
~~Access token shortened to 60 min. New `refresh_tokens` table stores SHA-256(token); each token is revoked on use (rotation). `POST /api/auth/refresh` issues a new token pair; `POST /api/auth/logout` revokes all active refresh tokens. (`src/api/auth.py`, `src/api/routers/auth.py`, migration `20260713_1000`)~~

~~**`cors_origins` defaults to `http://localhost:3000` with no production enforcement check** — FIXED 2026-07-13~~
~~`lifespan` logs a warning when `app_env=production` and any `cors_origins` entry contains "localhost". (`src/api/main.py`)~~

## Observability Gaps

~~**No structured request tracing (correlation IDs)** — FIXED 2026-07-13~~
~~`src/api/middleware.py` adds `CorrelationIdMiddleware`: stamps every request with an 8-char UUID stored in `request_id_var` (contextvars), returned as `X-Request-ID` response header. Registered in `main.py` before CORS middleware.~~

~~**No health check for Milvus or Ollama connectivity** — FIXED 2026-07-13~~
~~`GET /health/ready` probes Milvus (`has_collection`) and Ollama (`/api/tags`) with a 3-second timeout each. Returns 200 `{status: "ready"}` when both are up, 503 with per-service error details otherwise. (`src/api/main.py`)~~

~~**Milvus flush failures emit a log but have no metric or alert** — FIXED 2026-07-13~~
~~`embedder.py` now wraps all `flush()` calls in `_flush()` helper: on failure logs a warning and increments the `milvus_flush_errors_total` Prometheus counter exposed at `/metrics`. (`src/ingestion/embedder.py`)~~

---

*Concerns audit: 2026-06-27*
