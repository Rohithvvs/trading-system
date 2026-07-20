import uuid

from backend.app.models.paper_trading import PaperOrder, PaperPosition
from backend.app.services.paper_trading_service import PaperTradingService

_TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def test_gap_down_stop_loss_execution(db_session):
    """
    Mock an order with a stop-loss at 100. Feed it a new daily open candle
    that gaps down to 90. Assert that the matching engine executes the fill
    exactly at the gap price (90), not the ideal trigger price (100).
    """
    service = PaperTradingService(db_session, user_id=_TEST_USER_ID)
    
    # Setup initial account and position
    account = service._get_or_create_account()
    
    # Create an open position at 120
    position = PaperPosition(
        account_id=account.id,
        status="OPEN",
        lifecycle_state="OPEN_POSITION",
        symbol="GAP_TEST",
        qty=10,
        avg_entry_price=120.0,
        current_price=120.0,
        stop_loss=100.0,
    )
    db_session.add(position)
    
    # Create the pending STOP order to sell at 100
    stop_order = PaperOrder(
        account_id=account.id,
        symbol="GAP_TEST",
        side="SELL",
        order_type="STOP",
        product_type="CNC",
        qty=10,
        order_price=100.0,  # Limit price fallback
        stop_price=100.0,   # Trigger price
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    db_session.add(stop_order)
    db_session.commit()
    
    # Market opens and the price gaps down instantly to 90
    gap_price = 90.0
    
    # Process the fill
    filled_order, updated_position, trade, message = service._try_fill_order(
        account=account,
        order=stop_order,
        current_price=gap_price
    )
    
    # Assertions
    assert filled_order.status == "FILLED"
    # The crucial assertion: executed at gap price (90), not stop price (100)
    assert filled_order.filled_price == 90.0
    
    # The position should be fully closed
    assert updated_position is None
    
    # The trade history should reflect the gap down PnL
    assert trade is not None
    assert trade.exit_price == 90.0
    assert trade.pnl == (90.0 - 120.0) * 10  # -300.0


def test_partial_fill_scaling(db_session):
    """
    Mock an execution where only 50% of the target quantity is filled. Assert
    that the database updates the position size correctly without duplicating
    the initial invested capital tracking rows.
    """
    service = PaperTradingService(db_session, user_id=_TEST_USER_ID)
    account = service._get_or_create_account()
    
    # Create an open position for 100 shares
    position = PaperPosition(
        account_id=account.id,
        status="OPEN",
        lifecycle_state="OPEN_POSITION",
        symbol="PARTIAL_TEST",
        qty=100,
        avg_entry_price=50.0,
        current_price=50.0,
    )
    db_session.add(position)
    db_session.commit()
    
    # We want to sell 50 shares (50% partial fill)
    partial_sell_order = PaperOrder(
        account_id=account.id,
        symbol="PARTIAL_TEST",
        side="SELL",
        order_type="MARKET",
        product_type="CNC",
        qty=50,
        order_price=60.0,
        status="PENDING",
    )
    db_session.add(partial_sell_order)
    db_session.commit()
    
    filled_order, updated_position, trade, message = service._try_fill_order(
        account=account,
        order=partial_sell_order,
        current_price=60.0
    )
    
    assert filled_order.status == "FILLED"
    assert filled_order.qty == 50
    assert trade.qty == 50
    
    # Assert position was updated correctly
    assert updated_position is not None
    assert updated_position.qty == 50
    # Average entry price should remain untouched for the remaining shares
    assert updated_position.avg_entry_price == 50.0
    
    # Count the number of positions for this symbol
    position_count = db_session.query(PaperPosition).filter_by(symbol="PARTIAL_TEST").count()
    assert position_count == 1, "Should not duplicate capital tracking rows"
