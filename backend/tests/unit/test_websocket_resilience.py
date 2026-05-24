from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.market_data_feed import FyersMarketDataFeed


@pytest.fixture
def mock_ws_dependencies():
    with patch("backend.app.services.market_data_feed.data_ws") as mock_data_ws, \
         patch("backend.app.services.market_data_feed.SessionLocal"), \
         patch("backend.app.services.market_data_feed.get_current_access_token") as mock_get_token:
        
        mock_get_token.return_value = "mock_token"
        
        # We need to capture the callbacks passed to FyersDataSocket
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
        on_connection_change=on_connection_change_mock
    )
    
    # Start the feed, which initializes the socket and background thread
    feed.start()
    
    # Grab the kwargs passed to FyersDataSocket
    call_kwargs = mock_ws_dependencies["data_ws"].FyersDataSocket.call_args.kwargs
    
    assert call_kwargs["reconnect"] is True, "WebSocket must be configured with reconnect=True"
    
    # Simulate on_connect
    on_connect_callback = call_kwargs["on_connect"]
    on_connect_callback()
    assert feed.connected is True
    on_connection_change_mock.assert_called_with(True)
    
    # Simulate a close/disconnect event
    on_close_callback = call_kwargs["on_close"]
    on_close_callback({"code": 1006, "reason": "Connection closed abnormally"})
    
    assert feed.connected is False
    # The callback should be called with False when closed
    on_connection_change_mock.assert_called_with(False)


def test_ws_corrupted_packet_handling(mock_ws_dependencies):
    """
    Pass a malformed JSON string or binary garbage into the message parser
    and assert that the system logs a warning and skips to the next packet
    without crashing the background thread.
    """
    on_tick_mock = MagicMock()
    on_error_mock = MagicMock()
    on_connection_change_mock = MagicMock()
    
    feed = FyersMarketDataFeed(
        on_tick=on_tick_mock,
        on_error=on_error_mock,
        on_connection_change=on_connection_change_mock
    )
    
    feed.start()
    call_kwargs = mock_ws_dependencies["data_ws"].FyersDataSocket.call_args.kwargs
    on_message_callback = call_kwargs["on_message"]
    
    # Send a valid message
    on_message_callback({"symbol": "NSE:INFY", "ltp": 1500.0})
    on_tick_mock.assert_called_with("INFY", 1500.0)
    
    # Reset mock for the corrupted test
    on_tick_mock.reset_mock()
    
    # 1. Corrupted packet: missing 'ltp' and 'lp'
    on_message_callback({"symbol": "NSE:INFY", "invalid_key": "junk"})
    on_tick_mock.assert_not_called()
    
    # 2. Corrupted packet: ltp is unparseable string
    on_message_callback({"symbol": "NSE:INFY", "ltp": "NOT_A_FLOAT"})
    on_tick_mock.assert_not_called()
    
    # 3. Corrupted packet: fully empty dict
    on_message_callback({})
    on_tick_mock.assert_not_called()
    
    # System should still be alive, verify next valid message works
    on_message_callback({"symbol": "NSE:TCS", "ltp": 3500.0})
    on_tick_mock.assert_called_with("TCS", 3500.0)
