from __future__ import annotations

import pytest

import backend.app.services.paper_trading_service as paper_service
from tests.utils.db_assertions import assert_paper_order_stored, row_count, write_db_snapshot
from tests.utils.fakes import FakeFyersService


@pytest.mark.integration
def test_market_order_creates_paper_trading_rows(client, db_session, monkeypatch, artifact_dir):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)

    reset = client.post("/paper-trading/account/reset", json={"starting_balance": 1000000})
    assert reset.status_code == 200, reset.text

    response = client.post(
        "/paper-trading/orders",
        json={
            "symbol": "INFY-EQ",
            "side": "BUY",
            "type": "MARKET",
            "qty": 2,
            "stop_loss": 95,
            "target": 115,
            "notes": "integration test",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["order"]["status"] == "FILLED"
    assert payload["position"]["symbol"] == "INFY-EQ"

    order_row = assert_paper_order_stored(db_session, "INFY-EQ")
    assert order_row["status"] == "FILLED"
    assert row_count(db_session, "paper_trading_positions") == 1
    assert row_count(db_session, "paper_trading_transactions") == 1

    dashboard = client.get("/paper-trading/dashboard?selected_symbol=INFY-EQ")
    assert dashboard.status_code == 200
    assert dashboard.json()["positions"][0]["symbol"] == "INFY-EQ"

    write_db_snapshot(
        db_session,
        artifact_dir,
        "paper-trading-persistence",
        ["paper_trading_accounts", "paper_trading_orders", "paper_trading_positions", "paper_trading_transactions"],
    )
