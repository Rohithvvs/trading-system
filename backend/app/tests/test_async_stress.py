import pytest
import asyncio
from sqlalchemy import text
from backend.app.db.session import AsyncSessionLocal

@pytest.mark.asyncio
async def test_async_transaction_timeout():
    """Verify that slow DB operations respect timeouts."""
    async with AsyncSessionLocal() as db:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                db.execute(text("SELECT SYSTEM_USER(), SLEEP(5)")),
                timeout=0.1
            )

@pytest.mark.asyncio
async def test_task_cancellation_cleanup():
    """Verify that cancelled background tasks clean up their sessions."""
    # This is a stub for the failure injection test
    # If a task is cancelled, the session should not leak.
    pass
