import pytest
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

@pytest.mark.asyncio
async def test_postgres_advisory_lock_acquisition_and_release():
    """
    Verify basic pg_try_advisory_lock acquisition and explicit release.
    """
    lock_id = 123456789
    async with AsyncSessionLocal() as db:
        # Acquire
        res1 = await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
        assert res1.scalar() is True

        # Release
        res2 = await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
        assert res2.scalar() is True

@pytest.mark.asyncio
async def test_postgres_advisory_lock_duplicate_rejection():
    """
    Verify that an acquired advisory lock prevents other connections from acquiring it.
    """
    lock_id = 987654321
    
    async with AsyncSessionLocal() as db1:
        # Session 1 acquires lock
        res1 = await db1.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
        assert res1.scalar() is True
        
        async with AsyncSessionLocal() as db2:
            # Session 2 tries to acquire the same lock and fails immediately
            res2 = await db2.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
            assert res2.scalar() is False

        # Session 1 releases lock
        res3 = await db1.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
        assert res3.scalar() is True

@pytest.mark.asyncio
async def test_postgres_advisory_lock_concurrent_contention():
    """
    Verify concurrent worker contention behavior.
    """
    lock_id = 555555555
    success_count = 0
    failure_count = 0

    async def worker():
        nonlocal success_count, failure_count
        async with AsyncSessionLocal() as db:
            res = await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
            if res.scalar():
                success_count += 1
                # Hold the lock until the whole test finishes
                await asyncio.sleep(1)
                await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
            else:
                failure_count += 1

    # Spin up 10 concurrent workers trying to grab the exact same lock instantly
    workers = [asyncio.create_task(worker()) for _ in range(10)]
    await asyncio.gather(*workers)

    # Some should succeed, some should fail due to lock contention in the pool
    assert success_count >= 1
    assert failure_count > 0
