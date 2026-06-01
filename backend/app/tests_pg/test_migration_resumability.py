import pytest
import uuid
import asyncio
from sqlalchemy import text
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

# Import from scripts correctly by resolving path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.migrate_sqlite_to_pg import get_checkpoint, update_checkpoint

@pytest.fixture(autouse=True)
async def cleanup_checkpoints(db: AsyncSession):
    # Ensure a clean slate before each test
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.commit()

@pytest.mark.asyncio
async def test_migration_checkpoint_atomicity(db: AsyncSession):
    """
    Test 1 & 2: Prove that if a transaction fails before commit,
    neither data nor checkpoint is persisted (Atomic failure).
    If it succeeds, both are persisted (Atomic success).
    """
    run_id = str(uuid.uuid4())
    table_name = "paper_trading_accounts"

    # 1. Start Migration Chunk Simulation (Will Crash)
    try:
        # Simulate inserting an account
        await db.execute(
            text("""
                INSERT INTO paper_trading_accounts 
                (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
                VALUES (1, 'Test Account', 'USD', 10000.00, 10000.00, 0.02, :now, :now)
            """),
            {"now": datetime.now(timezone.utc)}
        )
        
        # Advance checkpoint
        await update_checkpoint(db, table_name, last_pk=1, last_chunk=1, rows_in_chunk=1, run_id=run_id)

        # Simulate Crash before commit!
        raise RuntimeError("Simulated Crash during migration chunk!")

    except RuntimeError:
        await db.rollback()

    # 2. Verify Atomic Rollback
    ckpt = await get_checkpoint(db, table_name)
    assert ckpt["last_pk"] == 0
    assert ckpt["last_chunk"] == 0

    res = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts"))
    assert res.scalar() == 0

    # 3. Resume and Succeed
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts 
            (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (1, 'Test Account', 'USD', 10000.00, 10000.00, 0.02, :now, :now)
        """),
        {"now": datetime.now(timezone.utc)}
    )
    
    await update_checkpoint(db, table_name, last_pk=1, last_chunk=1, rows_in_chunk=1, run_id=run_id)
    await db.commit()

    # 4. Verify Atomic Commit
    ckpt2 = await get_checkpoint(db, table_name)
    assert ckpt2["last_pk"] == 1
    assert ckpt2["last_chunk"] == 1

    res2 = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts"))
    assert res2.scalar() == 1

@pytest.mark.asyncio
async def test_migration_checkpoint_resume_no_drift(db: AsyncSession):
    """
    Test 3: Verify that resuming from a checkpoint cleanly prevents drift.
    """
    run_id = str(uuid.uuid4())
    table_name = "paper_trading_accounts"

    # Emulate Chunk 1 Success
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts 
            (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (1, 'Test Account', 'USD', 10000.00, 10000.00, 0.02, :now, :now)
        """),
        {"now": datetime.now(timezone.utc)}
    )
    await update_checkpoint(db, table_name, last_pk=1, last_chunk=1, rows_in_chunk=1, run_id=run_id)
    await db.commit()

    # Emulate Resume
    ckpt = await get_checkpoint(db, table_name)
    assert ckpt["last_pk"] == 1

    # Chunk 2 runs based on id > last_pk
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts 
            (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (2, 'Test Account 2', 'USD', 10000.00, 10000.00, 0.02, :now, :now)
        """),
        {"now": datetime.now(timezone.utc)}
    )
    await update_checkpoint(db, table_name, last_pk=2, last_chunk=2, rows_in_chunk=1, run_id=run_id)
    await db.commit()

    # Verify state
    ckpt_final = await get_checkpoint(db, table_name)
    assert ckpt_final["last_pk"] == 2
    assert ckpt_final["last_chunk"] == 2

    # Check rows_migrated tracks sum correctly via ON CONFLICT DO UPDATE
    res = await db.execute(text("SELECT rows_migrated FROM migration_checkpoints WHERE table_name = :t"), {"t": table_name})
    assert res.scalar() == 2

    res_count = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts"))
    assert res_count.scalar() == 2
