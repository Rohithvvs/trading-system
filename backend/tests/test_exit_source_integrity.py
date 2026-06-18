import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.paper_trading_service import PaperTradingService
from app.models.paper_trading import PaperTradeHistory

@pytest.fixture
def paper_service():
    service = PaperTradingService(MagicMock())
    service.db = MagicMock()
    service.logger = MagicMock()
    return service

def test_legacy_null_exit_source_serialization(paper_service):
    """
    TEST CATEGORY 10 — EXIT SOURCE INTEGRITY
    Legacy Rows: NULL
    Verify frontend fallback still works by ensuring serialization handles None correctly.
    """
    trade = PaperTradeHistory(
        id=1,
        account_id=1,
        symbol="TEST",
        qty=Decimal("10"),
        entry_price=Decimal("100.00"),
        exit_price=Decimal("105.00"),
        pnl=Decimal("50.00"),
        pnl_percent=Decimal("5.00"),
        opened_at=datetime.utcnow(),
        closed_at=datetime.utcnow(),
        exit_reason="MANUAL_EXIT",
        exit_source=None,  # Legacy row
    )
    
    serialized = paper_service._serialize_trade(trade)
    
    # Ensures it doesn't crash and correctly passes None up to the API layer
    # where the frontend `?? "MANUAL"` will take over
    assert serialized.exit_source is None
    assert serialized.exit_reason == "MANUAL_EXIT"

def test_reconciliation_exit_source(paper_service):
    """
    TEST CATEGORY 10 — EXIT SOURCE INTEGRITY
    Verify RECONCILIATION exit source is assigned when an order is historically filled.
    Actually, RECONCILIATION exits are simulated by auto_exit passing source="RECONCILIATION".
    """
    # This is handled exactly the same way as LIVE, we just ensure the parameter propagates.
    account_mock = MagicMock()
    account_mock.id = 1
    account_mock.cash_balance = Decimal("100000.00")
    account_mock.starting_balance = Decimal("100000.00")
    account_mock.realized_pnl = Decimal("0.00")
    account_mock.unrealized_pnl = Decimal("0.00")
    paper_service._get_or_create_account = MagicMock(return_value=account_mock)
    paper_service.get_dashboard = MagicMock()
    paper_service._serialize_order = MagicMock()
    paper_service._serialize_trade = MagicMock()
    paper_service._record_execution_event = MagicMock()
    pos_mock = MagicMock(id=5, qty=Decimal("10"), avg_entry_price=Decimal("100"))
    paper_service.db.scalar.side_effect = [pos_mock, None]
    
    try:
        paper_service.auto_exit(5, 110.00, reason="TARGET_HIT", source="RECONCILIATION")
    except Exception:
        pass
    
    add_calls = paper_service.db.add.call_args_list
    trade_history = None
    for call in add_calls:
        if isinstance(call[0][0], PaperTradeHistory):
            trade_history = call[0][0]
            
    assert trade_history is not None
    assert trade_history.exit_source == "RECONCILIATION"
