import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .live_state_machine import LiveOrderStateMachine
from ..models.live_trading import LiveAccount

logger = logging.getLogger(__name__)

class MarginEngine:
    """
    Implements Area 1: Margin Reservation Governance from D2.4D.
    Guarantees mathematically consistent available and reserved cash management.
    """

    @classmethod
    async def reserve_margin(cls, db: AsyncSession, account_id: int, required_margin: Decimal) -> LiveAccount:
        """
        Locks the Account row and shifts cash from available to reserved.
        Raises ValueError if insufficient funds.
        """
        # Ensure row-level locking to prevent concurrent double spending
        stmt = select(LiveAccount).where(LiveAccount.id == account_id).with_for_update()
        account = await db.scalar(stmt)
        if not account:
            raise ValueError(f"LiveAccount {account_id} not found.")

        if account.available_cash < required_margin:
            raise ValueError(
                f"Insufficient funds. Required: {required_margin}, Available: {account.available_cash}"
            )

        account.available_cash -= required_margin
        account.reserved_cash += required_margin
        
        logger.info(f"Reserved margin {required_margin} for account {account_id}. Available: {account.available_cash}, Reserved: {account.reserved_cash}")
        return account

    @classmethod
    async def release_margin(cls, db: AsyncSession, account_id: int, released_margin: Decimal) -> LiveAccount:
        """
        Locks the Account row and shifts cash from reserved back to available.
        Typically used upon order FAILED, REJECTED, or CANCELLED.
        Raises ValueError if releasing more than is reserved.
        """
        stmt = select(LiveAccount).where(LiveAccount.id == account_id).with_for_update()
        account = await db.scalar(stmt)
        if not account:
            raise ValueError(f"LiveAccount {account_id} not found.")

        if released_margin > account.reserved_cash:
            raise ValueError(
                f"Cannot release {released_margin}. Only {account.reserved_cash} reserved."
            )
        
        account.reserved_cash -= released_margin
        account.available_cash += released_margin
        
        logger.info(f"Released margin {released_margin} for account {account_id}. Available: {account.available_cash}, Reserved: {account.reserved_cash}")
        return account

    @classmethod
    async def consume_margin(cls, db: AsyncSession, account_id: int, consumed_amount: Decimal) -> LiveAccount:
        """
        Converts reserved funds into permanently spent funds.
        Raises ValueError if consuming more than is reserved.
        """
        stmt = select(LiveAccount).where(LiveAccount.id == account_id).with_for_update()
        account = await db.scalar(stmt)
        if not account:
            raise ValueError(f"LiveAccount {account_id} not found.")

        if consumed_amount > account.reserved_cash:
            raise ValueError(
                f"Cannot consume {consumed_amount}. Only {account.reserved_cash} reserved."
            )
            
        # Deduct permanently from reserved cash. It does not return to available cash.
        account.reserved_cash -= consumed_amount
        
        logger.info(f"Consumed margin {consumed_amount} for account {account_id}. Available: {account.available_cash}, Reserved: {account.reserved_cash}")
        return account

    @classmethod
    async def adjust_reservation_for_modify(
        cls, db: AsyncSession, account_id: int, current_reserved: Decimal, new_required: Decimal
    ) -> LiveAccount:
        """
        Handles explicit risk-increasing and risk-decreasing modification rules.
        Risk-Increasing: Funds must exist and are reserved immediately.
        Risk-Decreasing: No funds are released yet (to prevent double spend on broker reject).
        Returns the updated account.
        """
        stmt = select(LiveAccount).where(LiveAccount.id == account_id).with_for_update()
        account = await db.scalar(stmt)
        if not account:
            raise ValueError(f"LiveAccount {account_id} not found.")

        delta = new_required - current_reserved

        if delta > 0:
            # Risk-Increasing Modification (Qty / Price Increase)
            if account.available_cash < delta:
                raise ValueError(
                    f"Insufficient funds for modification increase. Required additional: {delta}, Available: {account.available_cash}"
                )
            account.available_cash -= delta
            account.reserved_cash += delta
            logger.info(f"Increased reserved margin by {delta} for account {account_id} during MODIFY_PENDING.")
        elif delta <= 0:
            # Risk-Decreasing Modification (Qty / Price Decrease)
            # NEVER release funds until broker officially confirms.
            logger.info(f"Risk-decreasing modify detected (delta {delta}). Holding {account.reserved_cash} reserved margin safely during MODIFY_PENDING.")
            pass
            
        return account
