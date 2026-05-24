from datetime import datetime
from backend.app.models.paper_trading import PaperTradingAccount, PaperPosition, PaperOrder
from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.services.market_engine_service import market_engine, IST

def test_capital_validation_gate(db):
    """
    Test Capital Validation Gate:
    Verify that when an order's estimated cost exceeds the account's available cash balance,
    _try_fill_order rejects it immediately with a 'REJECTED' status flag.
    """
    service = PaperTradingService(db)
    
    # Account with only 5000.0 INR cash
    account = PaperTradingAccount(
        id=1,
        name="Low Cash Account",
        base_currency="INR",
        starting_balance=10000.0,
        cash_balance=5000.0
    )
    db.add(account)
    db.commit()

    # Buy order that costs 6000.0 INR (exceeds 5000.0 cash)
    over_budget_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="LIMIT",
        order_price=1200.0,
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    filled_order, position, _, message = service._try_fill_order(account, over_budget_order, 1200.0)
    db.commit()

    assert filled_order.status == "REJECTED"
    assert "insufficient available cash" in message.lower()
    assert position is None
    # Cash balance should remain unchanged
    assert account.cash_balance == 5000.0


def test_naked_sell_protection(db):
    """
    Test Naked-Sell Protection:
    Verify that a manual or system exit request asking to SELL more shares than are currently held
    in an open PaperPosition triggers a fast rejection.
    """
    service = PaperTradingService(db)
    account = PaperTradingAccount(
        id=1,
        name="Trading Account",
        base_currency="INR",
        starting_balance=100000.0,
        cash_balance=100000.0
    )
    db.add(account)
    db.commit()

    # Case A: User has position, but sells more than they own
    pos = PaperPosition(
        account_id=account.id,
        symbol="INFY-EQ",
        status="OPEN",
        qty=10,
        avg_entry_price=1000.0,
        current_price=1000.0
    )
    db.add(pos)
    db.commit()

    # Attempt to sell 15 shares (owns only 10)
    oversell_order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="SELL",
        order_type="MARKET",
        qty=15,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    filled_order, position, _, message = service._try_fill_order(account, oversell_order, 1000.0)
    db.commit()

    assert filled_order.status == "REJECTED"
    assert "not enough position quantity to sell" in message.lower()
    assert pos.qty == 10  # Holdings remain unchanged

    # Case B: User has NO position at all for the symbol, attempts to sell
    naked_sell_order = PaperOrder(
        account_id=account.id,
        symbol="TCS-EQ",
        side="SELL",
        order_type="MARKET",
        qty=5,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY"
    )

    filled_naked, position_naked, _, message_naked = service._try_fill_order(account, naked_sell_order, 3000.0)
    db.commit()

    assert filled_naked.status == "REJECTED"
    assert "not enough position quantity to sell" in message_naked.lower()
    assert position_naked is None


def test_trading_clock_rules():
    """
    Test Trading Clock Rules:
    Verify is_market_hours returns False on weekends and blocks order flows
    outside the standard Indian market hours (09:00 to 16:00 IST).
    """
    # 1. Weekday (Monday) Standard Market Hours (10:00 AM IST) -> Should be True
    dt_monday_market = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    assert market_engine.is_market_hours(dt_monday_market) is True

    # 2. Weekday (Monday) Pre-Market Hour (08:59 AM IST) -> Should be False
    dt_monday_early = datetime(2026, 5, 25, 8, 59, tzinfo=IST)
    assert market_engine.is_market_hours(dt_monday_early) is False

    # 3. Weekday (Monday) Post-Market Hour (04:01 PM IST) -> Should be False
    dt_monday_late = datetime(2026, 5, 25, 16, 1, tzinfo=IST)
    assert market_engine.is_market_hours(dt_monday_late) is False

    # 4. Weekend (Saturday) Noon (12:00 PM IST) -> Should be False
    dt_saturday = datetime(2026, 5, 23, 12, 0, tzinfo=IST)
    assert market_engine.is_market_hours(dt_saturday) is False

    # 5. Weekend (Sunday) Noon (12:00 PM IST) -> Should be False
    dt_sunday = datetime(2026, 5, 24, 12, 0, tzinfo=IST)
    assert market_engine.is_market_hours(dt_sunday) is False
