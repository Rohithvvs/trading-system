from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.market_data_feed import FyersMarketDataFeed


@pytest.fixture
def mock_ws_dependencies():
    with patch("backend.app.services.market_data_feed.data_ws") as mock_data_ws:
        mock_socket_instance = MagicMock()
        mock_data_ws.FyersDataSocket.return_value = mock_socket_instance
        yield {
            "data_ws": mock_data_ws,
            "socket_instance": mock_socket_instance,
        }


def test_ws_auto_reconnect(mock_ws_dependencies):
    """
    Mock a ConnectionClosed exception and verify the WebSocket manager
    triggers the auto-reconnect loop instead of exiting.
    """
    on_tick_mock = MagicMock()
    on_error_mock = MagicMock()
    on_connection_change_mock = MagicMock()

    feed = FyersMarketDataFeed(
        on_tick=on_tick_mock,
        on_error=on_error_mock,
        on_connection_change=on_connection_change_mock,
    )

    # start() requires an access token string
    feed.start("mock_token")

    call_kwargs = mock_ws_dependencies["data_ws"].FyersDataSocket.call_args.kwargs

    assert call_kwargs["reconnect"] is True, "WebSocket must be configured with reconnect=True"

    on_connect_callback = call_kwargs["on_connect"]
    on_connect_callback()
    assert feed.connected is True
    on_connection_change_mock.assert_called_with(True)

    on_close_callback = call_kwargs["on_close"]
    on_close_callback({"code": 1006, "reason": "Connection closed abnormally"})

    assert feed.connected is False
    on_connection_change_mock.assert_called_with(False)


def test_ws_corrupted_packet_handling(mock_ws_dependencies):
    """
    Pass malformed payloads into the message parser and assert ticks are skipped
    without crashing the feed.
    """
    on_tick_mock = MagicMock()
    on_error_mock = MagicMock()
    on_connection_change_mock = MagicMock()

    feed = FyersMarketDataFeed(
        on_tick=on_tick_mock,
        on_error=on_error_mock,
        on_connection_change=on_connection_change_mock,
    )

    feed.start("mock_token")
    call_kwargs = mock_ws_dependencies["data_ws"].FyersDataSocket.call_args.kwargs
    on_message_callback = call_kwargs["on_message"]

    # Valid message (symbol may be normalized by payload model)
    on_message_callback({"symbol": "NSE:INFY-EQ", "ltp": 1500.0})
    assert on_tick_mock.called
    on_tick_mock.reset_mock()

    # Corrupted packets must not raise or emit ticks
    on_message_callback({"symbol": "NSE:INFY-EQ", "invalid_key": "junk"})
    on_tick_mock.assert_not_called()

    on_message_callback({"symbol": "NSE:INFY-EQ", "ltp": "NOT_A_FLOAT"})
    on_tick_mock.assert_not_called()

    on_message_callback({})
    on_tick_mock.assert_not_called()

    on_message_callback({"symbol": "NSE:TCS-EQ", "ltp": 3500.0})
    assert on_tick_mock.called
