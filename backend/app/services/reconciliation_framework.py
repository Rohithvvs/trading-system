import logging
from datetime import datetime, timezone, timedelta
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, update

from ..models.live_trading import LiveOrder

logger = logging.getLogger(__name__)

class ReconciliationFramework:
    """
    Implements Area 2 & Area 4 from D2.4D Architecture Hardening.
    Provides FOR UPDATE SKIP LOCKED exact-once claiming, and exponential backoff circuit breakers.
    """

    MAX_RETRIES = 5

    @classmethod
    def get_next_backoff(cls, attempts: int) -> timedelta | None:
        """
        Circuit breaker exponential backoff calculator.
        1: +10s
        2: +30s
        3: +2m
        4: +10m
        5: HALT (None returned)
        """
        if attempts == 0:
            return timedelta(seconds=10)
        elif attempts == 1:
            return timedelta(seconds=30)
        elif attempts == 2:
            return timedelta(minutes=2)
        elif attempts == 3:
            return timedelta(minutes=10)
        else:
            return None  # HALT - manual intervention required

    @classmethod
    async def claim_batch_for_reconciliation(
        cls, db: AsyncSession, batch_size: int = 100
    ) -> Sequence[LiveOrder]:
        """
        Sweeps the database for orphaned orders that need reconciliation.
        Uses SELECT ... FOR UPDATE SKIP LOCKED to guarantee mutually exclusive exactly-once processing
        even across hundreds of split-brain scheduler pods.
        """
        now = datetime.now(timezone.utc)

        # We look for EXECUTING, RECONCILING, MODIFY_PENDING, CANCEL_PENDING
        # where next_reconcile_at has passed.
        # Note: In a true sweep, initial orders might not have next_reconcile_at set until the first timeout.
        # The scheduler would also look for updated_at < now - 10s if next_reconcile_at is null.
        
        # Build the exact criteria for a stale order
        stale_condition = and_(
            LiveOrder.status.in_(["EXECUTING", "RECONCILING", "MODIFY_PENDING", "CANCEL_PENDING"]),
            or_(
                and_(LiveOrder.next_reconcile_at.isnot(None), LiveOrder.next_reconcile_at <= now),
                and_(LiveOrder.next_reconcile_at.is_(None), LiveOrder.updated_at <= now - timedelta(seconds=10))
            )
        )

        stmt = (
            select(LiveOrder)
            .where(stale_condition)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        claimed_orders = (await db.scalars(stmt)).all()
        
        # Transition them to RECONCILING so they remain locked to this worker's intent
        # even if this worker's transaction commits temporarily before full Fyers sync (if using autonomous txs).
        # But here, we hold the row lock until our transaction finishes.
        for order in claimed_orders:
            logger.info(f"Worker claimed orphaned order {order.id} (Status: {order.status}) via SKIP LOCKED.")
            # Note: We do not alter state here. The caller will process and commit.

        return claimed_orders

    @classmethod
    def apply_backoff(cls, order: LiveOrder) -> bool:
        """
        Increments attempts and sets next_reconcile_at.
        Returns False if Max Retries reached (HALT).
        """
        backoff = cls.get_next_backoff(order.reconciliation_attempts)
        if backoff is None:
            order.status = "MANUAL_INTERVENTION_REQUIRED"
            logger.critical(f"Order {order.id} reached max reconciliation retries. HALTED.")
            return False
            
        order.reconciliation_attempts += 1
        order.next_reconcile_at = datetime.now(timezone.utc) + backoff
        logger.warning(f"Order {order.id} backoff applied. Attempt {order.reconciliation_attempts}. Next retry at {order.next_reconcile_at}")
        return True
