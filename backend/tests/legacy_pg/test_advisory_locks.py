import pytest
import asyncio
from sqlalchemy import text
from backend.app.db.locks import acquire_singleton_lease, transaction_advisory_lock
from backend.app.db.session import AsyncSessionLocal

@pytest.mark.asyncio
async def test_singleton_lease_acquire_and_release():
    lease = await acquire_singleton_lease("test_singleton_lease_1")
    assert lease.acquired is True
    
    # Try to acquire it again while it's held
    lease2 = await acquire_singleton_lease("test_singleton_lease_1")
    assert lease2.acquired is False
    
    # Release the first lease
    await lease.release()
    
    # Should be able to acquire again
    lease3 = await acquire_singleton_lease("test_singleton_lease_1")
    assert lease3.acquired is True
    await lease3.release()


@pytest.mark.asyncio
async def test_singleton_lease_concurrent_contention():
    # Attempt to grab the same lease concurrently across multiple "workers"
    results = await asyncio.gather(
        acquire_singleton_lease("test_contention"),
        acquire_singleton_lease("test_contention"),
        acquire_singleton_lease("test_contention"),
        acquire_singleton_lease("test_contention")
    )
    
    acquired_count = sum(1 for r in results if r.acquired)
    assert acquired_count == 1
    
    # Release the winner
    for r in results:
        if r.acquired:
            await r.release()


@pytest.mark.asyncio
async def test_transaction_advisory_lock_commit():
    async with AsyncSessionLocal() as db:
        async with transaction_advisory_lock(db, "test_xact_lock_1") as acquired:
            assert acquired is True
            
            # Try to grab it in another session before commit
            async with AsyncSessionLocal() as db2:
                async with transaction_advisory_lock(db2, "test_xact_lock_1") as acquired2:
                    assert acquired2 is False
        
        # We must commit or rollback for the transaction lock to release
        await db.commit()
    
    # After commit, it should be available
    async with AsyncSessionLocal() as db3:
        async with transaction_advisory_lock(db3, "test_xact_lock_1") as acquired3:
            assert acquired3 is True
        await db3.rollback()


@pytest.mark.asyncio
async def test_transaction_advisory_lock_rollback_cleanup():
    async with AsyncSessionLocal() as db:
        async with transaction_advisory_lock(db, "test_xact_lock_rollback") as acquired:
            assert acquired is True
        # Rollback forces the release of pg_try_advisory_xact_lock
        await db.rollback()
    
    # Verify it is immediately available again
    async with AsyncSessionLocal() as db2:
        async with transaction_advisory_lock(db2, "test_xact_lock_rollback") as acquired2:
            assert acquired2 is True
        await db2.rollback()
