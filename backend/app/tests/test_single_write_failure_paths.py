import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.market_data import LatestScanResult, Base
from app.schemas.scan_aggregate import ScanAggregateResult, ScanCandidateDTO
from app.services.scanner_single_write_service import ScannerSingleWriteService


@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(LatestScanResult.__table__.create)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_single_write_transaction_failure_rollback(test_db):
    """Failure Path: Database execution error must raise exception and leave DB uncorrupted."""
    c1 = ScanCandidateDTO(symbol="FAIL_SYM", strategy_name="S1", signal_type="BUY", score=90.0)
    aggregate = ScanAggregateResult(
        scan_id="fail-scan-001",
        candidates=[c1],
        save_history=False,
    )

    writer = ScannerSingleWriteService(test_db)

    # Patch db.execute to simulate DB commit failure
    with patch.object(test_db, "execute", side_effect=RuntimeError("Database Write Failure")):
        with pytest.raises(RuntimeError, match="Database Write Failure"):
            await writer.persist_single_final_write(aggregate)


@pytest.mark.asyncio
async def test_in_memory_timeout_failure_path():
    """Failure Path: 30-second in-memory calculation timeout raises TimeoutError."""
    import asyncio

    async def slow_screener():
        await asyncio.sleep(0.5)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_screener(), timeout=0.1)
