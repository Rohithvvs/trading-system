import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from backend.app.models.paper_trading import PaperPosition, PaperTradeHistory, PaperOrder
from backend.app.services.paper_trading_service import PaperTradingService

@pytest.fixture
def paper_service():
    service = PaperTradingService(MagicMock())
    service.db = MagicMock()
    service.logger = MagicMock()
    return service

def test_try_fill_order_manual_exit(paper_service):
    account = MagicMock()
    account.id = 1
    account.cash_balance = Decimal("100000.00")
    account.starting_balance = Decimal("100000.00")
    account.realized_pnl = Decimal("0.00")
    account.unrealized_pnl = Decimal("0.00")
    
    order = PaperOrder(
        id=10,
        account_id=1,
        symbol="RELIANCE",
        side="SELL",
        order_type="MARKET",
        qty=Decimal("10"),
        order_price=None,
        status="PENDING"
    )
    
    position = PaperPosition(
        id=5,
        account_id=1,
        symbol="RELIANCE",
        qty=Decimal("10"),
        avg_entry_price=Decimal("2500.00"),
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    # Mock finding the position
    paper_service.db.scalar.return_value = position
    
    current_price = 2600.00
    filled_order, updated_position, trade_info, message = paper_service._try_fill_order(account, order, current_price)
    
    # Check that a PaperTradeHistory record was added
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_reason == "MANUAL"
    assert trade_history.exit_source == "MANUAL"

def test_auto_exit_sets_source(paper_service):
    account = MagicMock()
    account.id = 1
    account.cash_balance = Decimal("100000.00")
    account.starting_balance = Decimal("100000.00")
    account.realized_pnl = Decimal("0.00")
    account.unrealized_pnl = Decimal("0.00")
    
    position = PaperPosition(
        id=5,
        account_id=1,
        symbol="RELIANCE",
        qty=Decimal("10"),
        avg_entry_price=Decimal("2500.00"),
        status="OPEN",
        created_at=datetime.utcnow()
    )
    
    # Mock _get_or_create_account and get_dashboard
    paper_service._get_or_create_account = MagicMock(return_value=account)
    mock_dashboard = MagicMock()
    mock_dashboard.account = account
    paper_service.get_dashboard = MagicMock(return_value=mock_dashboard)
    paper_service._serialize_order = MagicMock()
    paper_service._serialize_trade = MagicMock()
    # Return position on first query, then None for ExecutionEvent dedupe check
    paper_service.db.scalar.side_effect = [position, None]
    paper_service._record_execution_event = MagicMock()
    
    paper_service.auto_exit(position.id, 2400.00, reason="STOPLOSS_HIT", source="LIVE")
    
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_reason == "STOPLOSS_HIT"
    assert trade_history.exit_source == "LIVE"
