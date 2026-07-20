from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.session import get_db
from backend.app.main import app
from backend.tests.conftest import TEST_DB_PATH
from tests.utils.db_assertions import assert_token_stored, row_count, write_db_snapshot


@pytest.fixture()
def client(db_session) -> Generator[TestClient, None, None]:
    """Async get_db override on the same SQLite file as db_session."""
    db_path = Path(TEST_DB_PATH).resolve()
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(async_engine.dispose())
    except Exception:
        pass


@pytest.mark.integration
def test_save_access_token_writes_token_and_history(client, db_session, artifact_dir):
    token = "test-access-token-1234567890"

    response = client.post("/api/token/save-access-token", json={"access_token": token})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    # Sync session may hold a stale snapshot; expire so we see the async commit.
    db_session.expire_all()
    token_row = assert_token_stored(db_session)
    assert token_row["status"] == "active"
    assert row_count(db_session, "fyers_token_history") == 1

    status = client.get("/api/token/status")
    assert status.status_code == 200
    assert status.json()["access_token_active"] is True

    diagnostic = client.get("/test-diagnostics/token")
    assert diagnostic.status_code == 200
    # Diagnostics expose stored_in_db (works for sqlite + postgres test DBs)
    assert diagnostic.json().get("stored_in_db") is True
    assert token not in diagnostic.text

    write_db_snapshot(db_session, artifact_dir, "token-persistence", ["fyers_tokens", "fyers_token_history"])
