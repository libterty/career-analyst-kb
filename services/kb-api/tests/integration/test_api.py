"""Integration tests for FastAPI endpoints — Phase 5.
Requires a running PostgreSQL instance (or SQLite for CI).
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.api.models.database import create_tables


@pytest_asyncio.fixture(scope="module")
async def client():
    await create_tables()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_and_login(client):
    # Register
    resp = await client.post(
        "/api/auth/register",
        json={"username": "test_user", "password": "Test1234!", "role": "editor"},
    )
    assert resp.status_code in (201, 409)  # 409 if already exists

    # Login
    resp = await client.post(
        "/api/auth/token",
        data={"username": "test_user", "password": "Test1234!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_chat_requires_auth(client):
    resp = await client.post(
        "/api/chat/query/sync",
        json={"question": "什麼是三寶？"},
    )
    assert resp.status_code == 401
