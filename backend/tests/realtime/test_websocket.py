import pytest
from unittest.mock import Mock, patch
from threading import Event

from backend.app.services.market_data_feed import FyersMarketDataFeed

@pytest.fixture
def mock_callbacks():
    return {
        "on_tick": Mock(),
        "on_error": Mock(),
        "on_connection_change": Mock()
    }

@patch("app.services.market_data_feed.data_ws")
@patch("app.services.market_data_feed.get_current_access_token")
def test_websocket_connect_disconnect_cycle(mock_get_token, mock_data_ws, mock_callbacks):
    """Test standard connect and explicit stop lifecycle"""
    mock_get_token.return_value = "fake_token"
    mock_socket_instance = Mock()
    mock_data_ws.FyersDataSocket.return_value = mock_socket_instance
    
    feed = FyersMarketDataFeed(**mock_callbacks)
    feed.start()
    
    # Simulate internal thread logic firing the on_connect callback
    on_connect_callback = mock_data_ws.FyersDataSocket.call_args[1]["on_connect"]
    on_connect_callback()
    
    assert feed.connected is True
    mock_callbacks["on_connection_change"].assert_called_with(True)
    
    # Stop the feed
    feed.stop()
    assert feed.connected is False
    mock_socket_instance.close_connection.assert_called_once()
    mock_callbacks["on_connection_change"].assert_called_with(False)

@patch("app.services.market_data_feed.data_ws")
@patch("app.services.market_data_feed.get_current_access_token")
def test_websocket_duplicate_subscription_prevention(mock_get_token, mock_data_ws, mock_callbacks):
    """Test that syncing identical symbols doesn't trigger duplicate network calls"""
    mock_get_token.return_value = "fake_token"
    mock_socket_instance = Mock()
    mock_data_ws.FyersDataSocket.return_value = mock_socket_instance
    
    feed = FyersMarketDataFeed(**mock_callbacks)
    
    # Must manually set connected to simulate active socket
    feed.connected = True
    feed._socket = mock_socket_instance
    
    # Sync first time
    feed.sync_symbols({"NSE:RELIANCE-EQ", "NSE:TCS-EQ"})
    mock_socket_instance.subscribe.assert_called_once()
    
    # Sync exact same set again
    mock_socket_instance.subscribe.reset_mock()
    feed.sync_symbols({"NSE:RELIANCE-EQ", "NSE:TCS-EQ"})
    
    # Should not call subscribe again!
    mock_socket_instance.subscribe.assert_not_called()
    
    # Add one, remove one
    feed.sync_symbols({"NSE:RELIANCE-EQ", "NSE:INFY-EQ"})
    mock_socket_instance.subscribe.assert_called_with(symbols=["NSE:INFY-EQ"], data_type="SymbolUpdate")
    mock_socket_instance.unsubscribe.assert_called_with(symbols=["NSE:TCS-EQ"], data_type="SymbolUpdate")

@patch("app.services.market_data_feed.data_ws")
@patch("app.services.market_data_feed.get_current_access_token")
def test_websocket_message_parsing_and_dropping(mock_get_token, mock_data_ws, mock_callbacks):
    """Test that valid ticks route through and malformed ticks are dropped silently without crashing."""
    mock_get_token.return_value = "fake_token"
    mock_data_ws.FyersDataSocket.return_value = Mock()
    
    feed = FyersMarketDataFeed(**mock_callbacks)
    feed.start()
    
    on_message_callback = mock_data_ws.FyersDataSocket.call_args[1]["on_message"]
    
    # 1. Valid tick
    on_message_callback({"symbol": "NSE:RELIANCE-EQ", "ltp": 2500.5})
    mock_callbacks["on_tick"].assert_called_with("RELIANCE-EQ", 2500.5)
    
    # 2. Alternative valid tick format from FYERS
    on_message_callback({"s": "NSE:TCS-EQ", "lp": 3500.0})
    mock_callbacks["on_tick"].assert_called_with("TCS-EQ", 3500.0)
    
    # 3. Malformed tick (missing price) - should NOT crash, should drop
    mock_callbacks["on_tick"].reset_mock()
    on_message_callback({"symbol": "NSE:BAD-EQ"}) # missing ltp
    mock_callbacks["on_tick"].assert_not_called()

@patch("app.services.market_data_feed.data_ws")
@patch("app.services.market_data_feed.get_current_access_token")
def test_websocket_error_recovery(mock_get_token, mock_data_ws, mock_callbacks):
    """Test that errors toggle the connection state."""
    mock_get_token.return_value = "fake_token"
    
    feed = FyersMarketDataFeed(**mock_callbacks)
    feed.start()
    
    feed.connected = True
    on_error_callback = mock_data_ws.FyersDataSocket.call_args[1]["on_error"]
    
    # Simulate network drop
    on_error_callback("Connection reset by peer")
    
    # Verify internal state changed
    assert feed.connected is False
    mock_callbacks["on_connection_change"].assert_called_with(False)
    mock_callbacks["on_error"].assert_called_with("Connection reset by peer")
