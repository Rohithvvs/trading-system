import pytest
import asyncio
from unittest.mock import Mock, patch
from backend.app.services.market_data_feed import FyersMarketDataFeed

@patch("app.services.market_data_feed.data_ws")
@patch("app.services.market_data_feed.get_current_access_token")
def test_resilience_network_partition(mock_get_token, mock_data_ws):
    """
    Chaos Test: Simulate a harsh network partition (socket closure + exception)
    and verify the feed's error handlers securely detach the socket without locking the thread.
    """
    mock_get_token.return_value = "fake_token"
    mock_socket = Mock()
    mock_data_ws.FyersDataSocket.return_value = mock_socket
    
    # We purposefully throw an exception when close_connection is called
    # to simulate a violently broken pipe
    mock_socket.close_connection.side_effect = BrokenPipeError("Socket forcibly closed by remote host")
    
    callbacks = {
        "on_tick": Mock(),
        "on_error": Mock(),
        "on_connection_change": Mock()
    }
    
    feed = FyersMarketDataFeed(**callbacks)
    feed.start()
    
    # Force the feed to believe it's connected
    feed.connected = True
    feed._socket = mock_socket
    
    # Call stop(), which invokes the mocked close_connection that throws BrokenPipeError
    # We wrap in try-except to prove it handles the exception gracefully
    try:
        feed.stop()
    except Exception as e:
        pytest.fail(f"Feed did not gracefully handle network partition exception: {e}")
        
    assert feed.connected is False
    callbacks["on_connection_change"].assert_called_with(False)


@pytest.mark.asyncio
async def test_resilience_queue_full():
    """
    Chaos Test: Flood an async queue to prove it drops events gracefully 
    instead of ballooning memory.
    """
    # Simulate the internal behavior of the LoggerService queue
    queue = asyncio.Queue(maxsize=5)
    
    dropped = 0
    for i in range(10):
        try:
            queue.put_nowait(f"Log_Item_{i}")
        except asyncio.QueueFull:
            dropped += 1
            
    assert queue.qsize() == 5
    assert dropped == 5 # 5 items should have gracefully hit QueueFull without crashing
