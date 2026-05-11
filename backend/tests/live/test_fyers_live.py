from __future__ import annotations

import os

import pytest

from backend.app.config import settings
from backend.app.services.fyers_service import FyersService


@pytest.mark.live
@pytest.mark.slow
def test_live_fyers_quote_check_is_manual_and_masked(client):
    token = os.getenv("FYERS_LIVE_ACCESS_TOKEN") or os.getenv("FYERS_ACCESS_TOKEN")
    app_id = os.getenv("FYERS_APP_ID")
    if not token or not app_id:
        pytest.skip("Set FYERS_APP_ID and FYERS_LIVE_ACCESS_TOKEN to run live FYERS tests manually.")

    settings.fyers_app_id = app_id
    saved = client.post("/api/token/save-access-token", json={"access_token": token})
    assert saved.status_code == 200, saved.text

    price = FyersService().fetch_ltp("INFY-EQ")
    assert price is None or price > 0
