from __future__ import annotations

import pytest

from tests.utils.db_assertions import assert_token_stored, row_count, write_db_snapshot


@pytest.mark.integration
def test_save_access_token_writes_token_and_history(client, db_session, artifact_dir):
    token = "test-access-token-1234567890"

    response = client.post("/api/token/save-access-token", json={"access_token": token})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    token_row = assert_token_stored(db_session)
    assert token_row["status"] == "active"
    assert row_count(db_session, "fyers_token_history") == 1

    status = client.get("/api/token/status")
    assert status.status_code == 200
    assert status.json()["access_token_active"] is True

    diagnostic = client.get("/test-diagnostics/token")
    assert diagnostic.status_code == 200
    assert diagnostic.json()["stored_in_sqlite"] is True
    assert token not in diagnostic.text

    write_db_snapshot(db_session, artifact_dir, "token-persistence", ["fyers_tokens", "fyers_token_history"])
