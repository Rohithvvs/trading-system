from backend.app.models.paper_trading import PaperTradingAccount, PaperOrder
from backend.app.services.paper_trading_service import PaperTradingService

def test_market_order_immediate_fill(db):
    """
    Test Market Orders:
    Check that a MARKET order triggers an immediate 'FILLED' status switch inside _try_fill_order.
    """
    service = PaperTradingService(db)
    account = PaperTradingAccount(
        id=1,
        name="Test Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=100000.0
    )
    db.add(account)
    db.commit()

    # Buy Market Order
    order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="MARKET",
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    filled_order, position, _, _ = service._try_fill_order(account, order, 1200.0)
    db.commit()

    assert filled_order.status == "FILLED"
    assert filled_order.lifecycle_state == "ENTRY_FILLED"
    assert filled_order.filled_price == 1200.0
    assert position is not None
    assert position.qty == 5
    assert position.lifecycle_state == "OPEN_POSITION"


def test_limit_order_pending_and_fill_thresholds(db):
    """
    Test Pending States:
    Check that LIMIT orders remain 'PENDING' unless prices cross the precise execution thresholds:
    - Buy triggers when current_price <= order_price
    - Sell triggers when current_price >= order_price
    """
    service = PaperTradingService(db)
    account = PaperTradingAccount(
        id=1,
        name="Test Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=100000.0
    )
    db.add(account)
    db.commit()

    # 1. LIMIT BUY: Order Price = 1000.0
    buy_limit_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="LIMIT",
        order_price=1000.0,
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    # Price = 1010.0 (Above limit price -> Should remain PENDING)
    filled_buy, position_buy, _, _ = service._try_fill_order(account, buy_limit_order, 1010.0)
    db.commit()
    assert filled_buy.status == "PENDING"
    assert filled_buy.lifecycle_state == "PENDING_ENTRY"
    assert position_buy is None

    # Price = 1000.0 (Exactly at limit price -> Should FILL)
    filled_buy, position_buy, _, _ = service._try_fill_order(account, buy_limit_order, 1000.0)
    db.commit()
    assert filled_buy.status == "FILLED"
    assert filled_buy.lifecycle_state == "ENTRY_FILLED"
    assert position_buy is not None
    assert position_buy.avg_entry_price == 1000.0

    # 2. LIMIT SELL: Order Price = 1100.0 (requires holding)
    # The account currently holds 10 Qty INFY-EQ at average entry price 1000.0
    sell_limit_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="SELL",
        order_type="LIMIT",
        order_price=1100.0,
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    # Price = 1090.0 (Below limit price -> Should remain PENDING)
    filled_sell, position_sell, _, _ = service._try_fill_order(account, sell_limit_order, 1090.0)
    db.commit()
    assert filled_sell.status == "PENDING"
    assert filled_sell.lifecycle_state == "PENDING_ENTRY"

    # Price = 1100.0 (Exactly at limit price -> Should FILL)
    filled_sell, position_sell, trade, _ = service._try_fill_order(account, sell_limit_order, 1100.0)
    db.commit()
    assert filled_sell.status == "FILLED"
    assert filled_sell.lifecycle_state == "EXIT_FILLED"
    assert position_sell is None  # Position closed
    assert trade is not None
    assert trade.pnl == 1000.0  # (1100 - 1000) * 10


def test_stop_order_lifecycle(db):
    """
    Test STOP Order Triggers:
    - Stop Buy: triggers when current_price >= stop_price
    - Stop Sell: triggers when current_price <= stop_price
    """
    service = PaperTradingService(db)
    account = PaperTradingAccount(
        id=1,
        name="Test Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=100000.0
    )
    db.add(account)
    db.commit()

    # 1. STOP BUY Order: stop_price = 150.0
    stop_buy = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="STOP",
        order_price=150.0,  # fallback if stop_price is unset
        stop_price=150.0,
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    # Price = 145.0 (Below stop trigger -> Should remain PENDING)
    filled_buy, _, _, _ = service._try_fill_order(account, stop_buy, 145.0)
    db.commit()
    assert filled_buy.status == "PENDING"

    # Price = 150.0 (Stop triggered -> Should FILL)
    filled_buy, position, _, _ = service._try_fill_order(account, stop_buy, 150.0)
    db.commit()
    assert filled_buy.status == "FILLED"
    assert filled_buy.lifecycle_state == "ENTRY_FILLED"
    assert position is not None
    assert position.avg_entry_price == 150.0

    # 2. STOP SELL Order: stop_price = 130.0 (requires holding)
    stop_sell = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="SELL",
        order_type="STOP",
        order_price=130.0,
        stop_price=130.0,
        qty=10,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    # Price = 135.0 (Above stop trigger -> Should remain PENDING)
    filled_sell, _, _, _ = service._try_fill_order(account, stop_sell, 135.0)
    db.commit()
    assert filled_sell.status == "PENDING"

    # Price = 130.0 (Stop triggered -> Should FILL)
    filled_sell, position_sell, trade, _ = service._try_fill_order(account, stop_sell, 130.0)
    db.commit()
    assert filled_sell.status == "FILLED"
    assert filled_sell.lifecycle_state == "EXIT_FILLED"
    assert position_sell is None
    assert trade is not None
    assert trade.pnl == -200.0  # (130 - 150) * 10
