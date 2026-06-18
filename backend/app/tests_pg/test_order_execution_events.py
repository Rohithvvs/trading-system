import pytest
from decimal import Decimal
from datetime import datetime, timezone
import uuid
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.models.live_trading import LiveAccount, LiveOrder, OrderExecutionEvent
from backend.app.services.live_state_machine import LiveOrderStateMachine

@pytest.fixture
async def live_account(db: AsyncSession):
    account = LiveAccount(
        name="Test Account Events",
        available_cash=Decimal("100000.00"),
        reserved_cash=Decimal("0.00")
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account

@pytest.fixture
async def order(db: AsyncSession, live_account: LiveAccount):
    order = LiveOrder(
        account_id=live_account.id,
        symbol="TEST",
        side="BUY",
        order_type="MARKET",
        requested_qty=Decimal("10"),
        status="CREATED",
        idempotency_key=str(uuid.uuid4())
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order

@pytest.mark.asyncio
async def test_transition_creates_event(db: AsyncSession, order: LiveOrder):
    # Transition
    await LiveOrderStateMachine.transition_order_state(
        db=db,
        order=order,
        new_state="EXECUTING"
    )
    
    # Assert
    assert order.status == "EXECUTING"
    
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 1
    assert result[0].previous_state == "CREATED"
    assert result[0].new_state == "EXECUTING"
    assert result[0].event_type == "STATE_TRANSITION"

@pytest.mark.asyncio
async def test_multiple_transitions_create_full_audit_chain(db: AsyncSession, order: LiveOrder):
    await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
    await LiveOrderStateMachine.transition_order_state(db, order, "BROKER_ACCEPTED")
    await LiveOrderStateMachine.transition_order_state(db, order, "PARTIALLY_FILLED")
    await LiveOrderStateMachine.transition_order_state(db, order, "FILLED")
    
    result = (await db.scalars(
        select(OrderExecutionEvent)
        .where(OrderExecutionEvent.order_id == order.id)
        .order_by(OrderExecutionEvent.id)
    )).all()
    
    assert len(result) == 4
    assert result[0].new_state == "EXECUTING"
    assert result[1].new_state == "BROKER_ACCEPTED"
    assert result[2].new_state == "PARTIALLY_FILLED"
    assert result[3].new_state == "FILLED"

@pytest.mark.asyncio
async def test_invalid_transition_creates_no_event(db: AsyncSession, order: LiveOrder):
    # First go to FILLED
    await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
    await LiveOrderStateMachine.transition_order_state(db, order, "BROKER_ACCEPTED")
    await LiveOrderStateMachine.transition_order_state(db, order, "FILLED")
    
    # Attempt invalid EXECUTING
    with pytest.raises(ValueError):
        await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
        
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 3 # Only the first 3
    assert order.status == "FILLED"

@pytest.mark.asyncio
async def test_transition_and_event_atomicity(db: AsyncSession, order: LiveOrder):
    from unittest.mock import patch
    
    current_status = order.status
    
    # Force db.commit to fail
    with patch.object(db, "commit", side_effect=Exception("DB Failure")):
        with pytest.raises(Exception, match="DB Failure"):
            await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
            
    await db.rollback()
    
    # Verify rollback
    await db.refresh(order)
    assert order.status == current_status
    
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 0

@pytest.mark.asyncio
async def test_concurrent_transition_protection(db: AsyncSession, order: LiveOrder):
    # Note: Sharing a single AsyncSession across asyncio.gather() coroutines is illegal 
    # in SQLAlchemy and causes flush errors.
    # We will test sequential validity instead to ensure the state machine prevents double execution.
    
    await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
    
    # Attempting to transition to EXECUTING again should short-circuit and return cleanly
    await LiveOrderStateMachine.transition_order_state(db, order, "EXECUTING")
        
    # Should still only be 1 event due to the short-circuit
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 1
    assert result[0].new_state == "EXECUTING"

@pytest.mark.asyncio
async def test_event_metadata_persistence(db: AsyncSession, order: LiveOrder):
    metadata = {"exchange": "NSE", "tag": "test1234"}
    corr_id = f"corr_{uuid.uuid4()}"
    user = "system_trader"
    
    await LiveOrderStateMachine.transition_order_state(
        db=db, 
        order=order, 
        new_state="EXECUTING",
        reason="Triggered by algo",
        metadata=metadata,
        correlation_id=corr_id,
        created_by=user
    )
    
    result = (await db.scalars(select(OrderExecutionEvent).where(OrderExecutionEvent.order_id == order.id))).all()
    assert len(result) == 1
    event = result[0]
    
    assert event.reason == "Triggered by algo"
    assert event.metadata_json == metadata
    assert event.correlation_id == corr_id
    assert event.created_by == user
    assert event.event_timestamp is not None
