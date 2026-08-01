import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func, text
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
async def test_single_write_with_save_history_true(test_db):
    now = datetime.now(timezone.utc)
    candidates = [
        ScanCandidateDTO(symbol=f"SYM_{i}", strategy_name="S1", signal_type="BUY", score=80.0 + i)
        for i in range(10)
    ]

    aggregate = ScanAggregateResult(
        scan_id="hist-scan-001",
        symbol_universe="NIFTY500",
        execution_timestamp=now,
        candidates=candidates,
        total_scanned=500,
        total_candidates=10,
        save_history=True,
    )

    writer = ScannerSingleWriteService(test_db)
    res = await writer.persist_single_final_write(aggregate)

    assert res.success is True
    assert res.latest_rows_upserted == 10
    assert res.history_rows_inserted == 10


@pytest.mark.asyncio
async def test_single_write_with_save_history_false(test_db):
    now = datetime.now(timezone.utc)
    candidates = [
        ScanCandidateDTO(symbol="RELIANCE", strategy_name="S1", signal_type="BUY", score=90.0)
    ]

    aggregate = ScanAggregateResult(
        scan_id="hist-scan-002",
        candidates=candidates,
        save_history=False,
    )

    writer = ScannerSingleWriteService(test_db)
    res = await writer.persist_single_final_write(aggregate)

    assert res.success is True
    assert res.latest_rows_upserted == 1
    assert res.history_rows_inserted == 0
