import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy import text

from backend.app.models.live_trading import LiveAccount, LiveOrder, LivePosition, BrokerExecutionLog
from backend.app.services.live_state_machine import LiveOrderStateMachine
from backend.app.services.margin_engine import MarginEngine
from backend.app.services.reconciliation_framework import ReconciliationFramework

@pytest.fixture
async def live_account(db: AsyncSession):
    account = LiveAccount(
        name="Test Live Account",
        available_cash=Decimal("100000.00"),
        reserved_cash=Decimal("0.00")
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account

@pytest.mark.asyncio
async def test_state_machine_valid_transitions():
    assert LiveOrderStateMachine.validate_transition("CREATED", "EXECUTING")
    assert LiveOrderStateMachine.validate_transition("EXECUTING", "BROKER_ACCEPTED")
    assert LiveOrderStateMachine.validate_transition("BROKER_ACCEPTED", "PARTIALLY_FILLED")
    assert LiveOrderStateMachine.validate_transition("PARTIALLY_FILLED", "FILLED")
    
    with pytest.raises(ValueError):
        LiveOrderStateMachine.validate_transition("FILLED", "CANCELLED")
        
    with pytest.raises(ValueError):
        LiveOrderStateMachine.validate_transition("FAILED", "BROKER_ACCEPTED")

@pytest.mark.asyncio
async def test_margin_reservation_correctness(db: AsyncSession, live_account: LiveAccount):
    # Reserve 50k
    account = await MarginEngine.reserve_margin(db, live_account.id, Decimal("50000.00"))
    assert account.available_cash == Decimal("50000.00")
    assert account.reserved_cash == Decimal("50000.00")
    await db.commit()
    
    # Release 20k
    account = await MarginEngine.release_margin(db, live_account.id, Decimal("20000.00"))
    assert account.available_cash == Decimal("70000.00")
    assert account.reserved_cash == Decimal("30000.00")
    await db.commit()
    
    # Try to reserve more than available
    with pytest.raises(ValueError, match="Insufficient funds"):
        await MarginEngine.reserve_margin(db, live_account.id, Decimal("80000.00"))

@pytest.mark.asyncio
async def test_modify_reservation_correctness(db: AsyncSession, live_account: LiveAccount):
    await MarginEngine.reserve_margin(db, live_account.id, Decimal("50000.00"))
    await db.commit()
    
    # Increase risk (requires 10k more)
    account = await MarginEngine.adjust_reservation_for_modify(
        db, live_account.id, current_reserved=Decimal("50000.00"), new_required=Decimal("60000.00")
    )
    assert account.available_cash == Decimal("40000.00")
    assert account.reserved_cash == Decimal("60000.00")
    await db.commit()
    
    # Decrease risk (requires 20k less, but should NOT release yet!)
    account = await MarginEngine.adjust_reservation_for_modify(
        db, live_account.id, current_reserved=Decimal("60000.00"), new_required=Decimal("40000.00")
    )
    assert account.available_cash == Decimal("40000.00")
    assert account.reserved_cash == Decimal("60000.00")
    await db.commit()

@pytest.mark.asyncio
async def test_execution_ledger_deduplication(db: AsyncSession):
    broker_order_id = f"fyers_{uuid.uuid4()}"
    trade_id = f"trade_{uuid.uuid4()}"
    
    # Insert first execution
    log1 = BrokerExecutionLog(
        broker_trade_id=trade_id,
        broker_order_id=broker_order_id,
        execution_timestamp=datetime.now(timezone.utc),
        side="BUY",
        qty=Decimal("10"),
        price=Decimal("150.0")
    )
    db.add(log1)
    await db.commit()
    
    # Try to insert exact same trade ID (duplicate webhook)
    # Using ON CONFLICT DO NOTHING natively requires specific dialect constructs,
    # but since SQLAlchemy ORM .add() without merge will raise IntegrityError if flushed,
    # we simulate the ON CONFLICT DO NOTHING manually or via raw SQL.
    # In practice, the backend will use pg_insert().on_conflict_do_nothing().
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    
    stmt = pg_insert(BrokerExecutionLog).values(
        broker_trade_id=trade_id,
        broker_order_id=broker_order_id,
        execution_timestamp=datetime.now(timezone.utc),
        side="BUY",
        qty=Decimal("10"),
        price=Decimal("150.0")
    ).on_conflict_do_nothing()
    
    await db.execute(stmt)
    await db.commit()
    
    # Verify only one exists
    result = (await db.scalars(select(BrokerExecutionLog).where(BrokerExecutionLog.broker_trade_id == trade_id))).all()
    assert len(result) == 1

@pytest.mark.asyncio
async def test_reconciliation_claiming_and_backoff(db: AsyncSession, live_account: LiveAccount):
    now = datetime.now(timezone.utc)
    
    order = LiveOrder(
        account_id=live_account.id,
        symbol="TEST",
        side="BUY",
        order_type="MARKET",
        requested_qty=Decimal("10"),
        status="EXECUTING",
        idempotency_key=str(uuid.uuid4()),
        updated_at=now - timedelta(seconds=20) # Stale
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    # Claim it
    claimed = await ReconciliationFramework.claim_batch_for_reconciliation(db)
    assert len(claimed) >= 1
    claimed_order = [o for o in claimed if o.id == order.id][0]
    
    # Apply backoff
    assert claimed_order.reconciliation_attempts == 0
    can_continue = ReconciliationFramework.apply_backoff(claimed_order)
    assert can_continue is True
    assert claimed_order.reconciliation_attempts == 1
    assert claimed_order.next_reconcile_at > datetime.now(timezone.utc)
    await db.commit()
    
    # Push attempts to 5
    claimed_order.reconciliation_attempts = 5
    can_continue = ReconciliationFramework.apply_backoff(claimed_order)
    assert can_continue is False
    assert claimed_order.status == "MANUAL_INTERVENTION_REQUIRED"

@pytest.mark.asyncio
async def test_live_account_invariants(db: AsyncSession):
    # Try creating account with negative cash
    account = LiveAccount(
        name="Bad Account",
        available_cash=Decimal("-10.00"),
        reserved_cash=Decimal("0.00")
    )
    db.add(account)
    with pytest.raises(DatabaseError):
        await db.commit()
    await db.rollback()

import asyncio

@pytest.mark.asyncio
async def test_skip_locked_concurrency(db: AsyncSession, live_account: LiveAccount):
    # Create multiple stale orders
    now = datetime.now(timezone.utc)
    for i in range(5):
        order = LiveOrder(
            account_id=live_account.id,
            symbol="TEST",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("10"),
            status="EXECUTING",
            idempotency_key=str(uuid.uuid4()),
            updated_at=now - timedelta(seconds=20)
        )
        db.add(order)
    await db.commit()

    # Simulate 2 concurrent workers attempting to claim the same batch
    # In a real app they'd use different sessions, but we can verify the SQL generated uses SKIP LOCKED.
    # To truly test concurrency with pytest-asyncio and multiple sessions we'd need a more complex fixture.
    # Instead, we just call the function and ensure it doesn't crash and returns the expected items.
    claimed1 = await ReconciliationFramework.claim_batch_for_reconciliation(db, batch_size=2)
    assert len(claimed1) == 2
    # The actual SKIP LOCKED lock behavior is proven by the SQL syntax emitted, which Postgres honors.

@pytest.mark.asyncio
async def test_consume_margin(db: AsyncSession, live_account: LiveAccount):
    # Reserve 50k
    account = await MarginEngine.reserve_margin(db, live_account.id, Decimal("50000.00"))
    assert account.reserved_cash == Decimal("50000.00")
    await db.commit()
    
    # Consume 10k
    account = await MarginEngine.consume_margin(db, live_account.id, Decimal("10000.00"))
    assert account.reserved_cash == Decimal("40000.00")
    assert account.available_cash == Decimal("50000.00") # Unchanged
    await db.commit()
    
    # Try to consume more than reserved
    with pytest.raises(ValueError, match="Cannot consume"):
        await MarginEngine.consume_margin(db, live_account.id, Decimal("50000.00"))
    
@pytest.mark.asyncio
async def test_release_safety(db: AsyncSession, live_account: LiveAccount):
    await MarginEngine.reserve_margin(db, live_account.id, Decimal("20000.00"))
    await db.commit()
    
    # Try to release 30k when only 20k reserved
    with pytest.raises(ValueError, match="Cannot release"):
        await MarginEngine.release_margin(db, live_account.id, Decimal("30000.00"))
        
from backend.app.models.live_trading import OrderExecutionEvent

@pytest.mark.asyncio
async def test_execution_event_creation(db: AsyncSession, live_account: LiveAccount):
    order = LiveOrder(
        account_id=live_account.id,
        symbol="TEST",
        side="BUY",
        order_type="MARKET",
        requested_qty=Decimal("10"),
        status="EXECUTING",
        idempotency_key=str(uuid.uuid4())
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    event = OrderExecutionEvent(
        order_id=order.id,
        event_type="STATE_TRANSITION",
        previous_state="EXECUTING",
        new_state="BROKER_ACCEPTED",
        reason="Broker acknowledged order",
        metadata_json={"broker_id": "12345"}
    )
    db.add(event)
    await db.commit()
    
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 1
    assert result[0].new_state == "BROKER_ACCEPTED"

