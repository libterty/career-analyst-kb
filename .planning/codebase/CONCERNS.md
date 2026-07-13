# Technical Concerns

**Analysis Date:** 2026-06-27

## Critical Issues

~~**Hardcoded default secret key in production config** — FIXED 2026-07-13~~
~~`lifespan` now raises RuntimeError if SECRET_KEY is still the placeholder and app_env != "development". Also logs a warning if ADMIN_PASSWORD is not set. (`src/api/main.py`)~~

**Hardcoded PostgreSQL credentials in default database URL:**
- Issue: Default `database_url` embeds `career:secret` as username/password.
- Files: `services/kb-api/src/core/config.py:75`
- Impact: Developers running without `.env` connect to a DB with well-known credentials; easy to forget to rotate.
- Fix approach: Remove the default entirely so startup fails fast if `DATABASE_URL` is not set.

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

**No per-endpoint rate limiting on the chat streaming endpoint:**
- Issue: The message count cap (`max_messages_per_session`) limits total messages but there is no per-minute or per-IP rate limit on the chat streaming route. A single client can flood LLM inference requests.
- Files: `services/kb-api/src/api/routers/` (no rate limit middleware observed)
- Impact: Denial-of-service on the Ollama/Grok backend; unexpected cost spikes for paid providers.
- Fix approach: Add `slowapi` or a Redis-backed rate limiter as FastAPI middleware.

**No startup warning when `ADMIN_PASSWORD` is unset:**
- Issue: If `ADMIN_PASSWORD` env var is not set, no admin account is created and there is no warning.
- Files: `services/kb-api/src/core/config.py:101`
- Impact: Fresh deployments have no admin access unless the operator knows to set this env var.
- Fix approach: Log a `logger.warning` at startup if `admin_password` is None.

## Security Concerns

**JWT secret key has a trivially guessable default (see Critical Issues).**

**Long access token expiry with no revocation mechanism:**
- Risk: Default access token lifetime is 480 minutes (8 hours). There is no refresh-token mechanism and no server-side token revocation list.
- Files: `services/kb-api/src/core/config.py:88`
- Recommendations: Implement short-lived access tokens (15-60 min) plus refresh tokens, or add a server-side revocation mechanism.

**`cors_origins` defaults to `http://localhost:3000` with no production enforcement check:**
- Issue: If `app_env=production` and the operator forgets to set `CORS_ORIGINS`, the API silently allows only localhost origins, breaking the frontend with no diagnostic message.
- Files: `services/kb-api/src/core/config.py:99`
- Fix approach: Log a warning when `app_env=production` and `cors_origins` still matches the development default.

## Observability Gaps

**No structured request tracing (correlation IDs):**
- Issue: Logs include `session_id` but no request-level trace ID is propagated across the RAG pipeline, security checks, and DB calls.
- Impact: Difficult to correlate logs from a single request across modules in production.
- Fix approach: Inject a `request_id` (UUID) at the router level via middleware and thread it through all service log statements.

**No health check for Milvus or Ollama connectivity:**
- Issue: The health endpoint (if present) likely only checks PostgreSQL. Milvus and Ollama failures would only surface as 500 errors on the first chat request.
- Impact: Load balancers or Kubernetes readiness probes cannot detect degraded state.
- Fix approach: Add `pymilvus.utility.has_collection()` and Ollama `/api/tags` probes to a `/health/ready` endpoint.

**Milvus flush failures emit a log but have no metric or alert:**
- Issue: The auto-flush added in commit `cee02a2` logs warnings on failure but there is no metric counter or alerting hook.
- Files: `services/kb-api/src/ingestion/embedder.py`
- Impact: Silent data loss on restart if repeated flush errors accumulate unnoticed.

---

*Concerns audit: 2026-06-27*
