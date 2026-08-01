import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.market_engine_service import MarketEngineService


@pytest.fixture
def test_engine():
    with patch("backend.app.services.market_engine_service.FyersService"):
        engine = MarketEngineService()
        engine._feed = MagicMock()
        engine._feed.connected = False
        engine._feed.start = MagicMock()
        engine._feed.restart = MagicMock()
        engine._feed.sync_symbols = MagicMock()
        engine._feed.stop = MagicMock()
        yield engine


@pytest.mark.asyncio
async def test_sqlite_operational_error_graceful_handling(test_engine, caplog):
    """
    Simulate an active trading sequence. Mid-trade, inject an artificial DB error.
    Assert the backend catches exceptions safely, logs it, and doesn't crash.
    """
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock(side_effect=Exception("database is locked"))
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "backend.app.services.market_engine_service.AsyncSessionLocal",
        return_value=mock_db,
    ):
        with patch.object(
            test_engine, "_process_symbol", new_callable=AsyncMock
        ), patch.object(
            test_engine, "_get_or_create_session", new_callable=AsyncMock
        ) as mock_session_factory:
            mock_session_factory.return_value = MagicMock()
            # Trigger tick (async handler)
            await test_engine._on_tick("RELIANCE", 2500.0)

    # Assert no crash, LTP still recorded, and error logged
    assert test_engine.latest_ltp["RELIANCE"] == 2500.0
    assert any(
        "Tick processing error" in record.message and "RELIANCE" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_websocket_connection_reset_retry(test_engine, caplog):
    """
    Force a dirty WebSocket drop (ConnectionResetError).
    Assert it logs it and triggers automated connection retry logic instead of crashing.
    """
    test_engine.is_market_hours = MagicMock(return_value=True)
    test_engine._desired_symbols = AsyncMock(return_value={"RELIANCE"})
    test_engine._feed.connected = False
    test_engine._poll_missing_prices = AsyncMock()

    # scalars().all() used when started_at is None
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db = AsyncMock()
    mock_db.scalars = AsyncMock(return_value=mock_result)

    from datetime import datetime, timezone

    mock_session = MagicMock()
    mock_session.status = "ERROR_RETRYING"
    # Non-None started_at skips MARKET_ENGINE_STARTED logging branch
    mock_session.started_at = datetime.now(timezone.utc)
    mock_session.id = 1

    with patch(
        "backend.app.services.market_engine_service.get_current_access_token",
        new_callable=AsyncMock,
        return_value="test-token",
    ):
        await test_engine._on_feed_error(ConnectionResetError("Connection reset by peer"))
        assert not test_engine._feed.connected

        await test_engine._reconcile_session(mock_db, mock_session)

        # Feed restart path: disconnected → restart(token)
        test_engine._feed.restart.assert_called()
        assert mock_session.status == "RUNNING"