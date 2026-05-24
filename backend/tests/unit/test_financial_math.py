from datetime import datetime, timezone
from backend.app.models.paper_trading import PaperTradingAccount, PaperPosition, PaperOrder
from backend.app.services.paper_trading_service import PaperTradingService, PriceSnapshot

def test_rolling_average_entry_price_and_pnl(db):
    """
    Test P&L Calculations:
    1. Check that buy inputs compute rolling average entry prices correctly.
    2. Check that sell actions compute absolute P&L and P&L percentages accurately.
    3. Check that zero-division bugs are prevented when average entry price is zero.
    """
    service = PaperTradingService(db)
    
    # 1. Create a Paper Trading Account
    account = PaperTradingAccount(
        id=1,
        name="Test Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=100000.0
    )
    db.add(account)
    db.commit()

    # 2. Place first BUY order: 10 Qty @ 1000.0
    order1 = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="MARKET",
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    
    # Execute buy
    filled_order1, position, trade1, _ = service._try_fill_order(account, order1, 1000.0)
    db.commit()

    assert filled_order1.status == "FILLED"
    assert filled_order1.filled_price == 1000.0
    assert position is not None
    assert position.qty == 10
    assert position.avg_entry_price == 1000.0
    assert account.cash_balance == 90000.0  # 100000 - (1000 * 10)

    # 3. Place second BUY order: 10 Qty @ 1200.0
    order2 = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="MARKET",
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    
    # Execute second buy
    filled_order2, position2, trade2, _ = service._try_fill_order(account, order2, 1200.0)
    db.commit()

    assert filled_order2.status == "FILLED"
    assert filled_order2.filled_price == 1200.0
    assert position2.qty == 20
    # Average price = (1000 * 10 + 1200 * 10) / 20 = 1100.0
    assert position2.avg_entry_price == 1100.0
    assert account.cash_balance == 78000.0  # 90000 - (1200 * 10)

    # 4. Place a SELL order: 10 Qty @ 1300.0
    sell_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="SELL",
        order_type="LIMIT",
        order_price=1300.0,
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    
    # Execute partial sell
    filled_sell, updated_pos, sell_trade, _ = service._try_fill_order(account, sell_order, 1300.0)
    db.commit()

    assert filled_sell.status == "FILLED"
    assert filled_sell.filled_price == 1300.0
    assert updated_pos is not None
    assert updated_pos.qty == 10
    assert updated_pos.avg_entry_price == 1100.0  # Avg entry remains unchanged
    assert account.cash_balance == 91000.0  # 78000 + (1300 * 10)
    
    # P&L calculations
    # P&L = (1300 - 1100) * 10 = 2000.0
    # P&L% = ((1300 - 1100) / 1100) * 100 = 18.1818...
    assert sell_trade is not None
    assert sell_trade.pnl == 2000.0
    assert round(sell_trade.pnl_percent, 2) == 18.18

    # 5. Place a final SELL order to close the position at a loss: 10 Qty @ 900.0
    close_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="SELL",
        order_type="MARKET",
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    
    # Execute final sell
    filled_close, final_pos, close_trade, _ = service._try_fill_order(account, close_order, 900.0)
    db.commit()

    assert filled_close.status == "FILLED"
    assert final_pos is None  # Position closed (deleted from DB)
    assert account.cash_balance == 100000.0  # 91000 + (900 * 10)
    
    # Loss P&L = (900 - 1100) * 10 = -2000.0
    # Loss P&L% = ((900 - 1100) / 1100) * 100 = -18.1818...
    assert close_trade is not None
    assert close_trade.pnl == -2000.0
    assert round(close_trade.pnl_percent, 2) == -18.18

    # 6. Test Division by Zero Prevention when avg_entry_price is zero
    zero_pos = PaperPosition(
        account_id=account.id,
        symbol="ZERO-EQ",
        status="OPEN",
        qty=5,
        avg_entry_price=0.0,
        current_price=0.0
    )
    db.add(zero_pos)
    db.commit()

    sell_zero = PaperOrder(
        account_id=account.id,
        symbol="ZERO-EQ",
        side="SELL",
        order_type="MARKET",
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    filled_zero_sell, _, zero_trade, _ = service._try_fill_order(account, sell_zero, 150.0)
    db.commit()

    assert filled_zero_sell.status == "FILLED"
    assert zero_trade is not None
    assert zero_trade.pnl == 150.0 * 5  # (150 - 0) * 5
    assert zero_trade.pnl_percent == 0.0  # Guarded from division by zero, returns 0.0


def test_build_account_summary(db):
    """
    Test Account Summary Math:
    - Equity = Cash Balance + Sum(Current Price * Qty)
    - Available Cash = Cash Balance - Reserved Cash
    - Reserved Cash = Sum(Order Price * Qty) for PENDING BUY LIMIT/GTT orders
    """
    service = PaperTradingService(db)

    # 1. Create a Paper Trading Account
    account = PaperTradingAccount(
        id=1,
        name="Summary Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=50000.0
    )
    db.add(account)
    db.commit()

    # 2. Add two active open positions
    pos1 = PaperPosition(
        account_id=account.id,
        symbol="TCS-EQ",
        status="OPEN",
        qty=5,
        avg_entry_price=3000.0,
        current_price=3000.0
    )
    pos2 = PaperPosition(
        account_id=account.id,
        symbol="RELIANCE-EQ",
        status="OPEN",
        qty=10,
        avg_entry_price=2000.0,
        current_price=2000.0
    )
    db.add_all([pos1, pos2])
    db.commit()

    # 3. Add orders of different types to verify cash reservation logic
    # - Pending BUY LIMIT order (should reserve cash)
    order_buy_limit = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="LIMIT",
        order_price=1000.0,
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    # - Pending BUY MARKET order (should not reserve cash)
    order_buy_market = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="MARKET",
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    # - Pending SELL LIMIT order (should not reserve cash)
    order_sell_limit = PaperOrder(
        account_id=account.id,
        symbol="TCS-EQ",
        side="SELL",
        order_type="LIMIT",
        order_price=3300.0,
        qty=2,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )
    db.add_all([order_buy_limit, order_buy_market, order_sell_limit])
    db.commit()

    # Mock Price Cache (Current Prices for positions and pending orders)
    price_cache = {
        "TCS-EQ": PriceSnapshot(
            symbol="TCS-EQ", current_price=3200.0, candles=[], ema_20=None, supertrend=None, source="test", fetched_at=datetime.now(timezone.utc)
        ),
        "RELIANCE-EQ": PriceSnapshot(
            symbol="RELIANCE-EQ", current_price=1900.0, candles=[], ema_20=None, supertrend=None, source="test", fetched_at=datetime.now(timezone.utc)
        ),
        "INFY-EQ": PriceSnapshot(
            symbol="INFY-EQ", current_price=1050.0, candles=[], ema_20=None, supertrend=None, source="test", fetched_at=datetime.now(timezone.utc)
        ),
    }

    # Execute build summary
    summary = service._build_account_summary(
        account=account,
        positions=[pos1, pos2],
        orders=[order_buy_limit, order_buy_market, order_sell_limit],
        trades=[],
        price_cache=price_cache
    )

    # Assert calculations
    # Invested = (3000 * 5) + (2000 * 10) = 15000 + 20000 = 35000.0
    assert summary.total_invested == 35000.0
    
    # Unrealized P&L = (3200 - 3000)*5 + (1900 - 2000)*10 = 1000 - 1000 = 0.0
    assert summary.unrealized_pnl == 0.0

    # Reserved Cash: order_buy_limit reserves (1000 * 5) = 5000.0
    assert summary.reserved_cash == 5000.0

    # Available Cash = cash_balance (50000) - reserved_cash (5000) = 45000.0
    assert summary.available_cash == 45000.0

    # Equity = cash_balance (50000) + Sum(current_price * qty)
    # Sum(current_price * qty) = (3200 * 5) + (1900 * 10) = 16000 + 19000 = 35000.0
    # Equity = 50000 + 35000 = 85000.0
    assert summary.equity == 85000.0
