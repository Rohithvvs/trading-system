import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func
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
async def test_single_write_empty_candidates_list(test_db):
    """Edge Case: Scanning yields 0 candidate matches; transaction completes cleanly with 0 writes."""
    now = datetime.now(timezone.utc)
    aggregate = ScanAggregateResult(
        scan_id="empty-scan-001",
        symbol_universe="NIFTY500",
        execution_timestamp=now,
        candidates=[],
        total_scanned=500,
        total_candidates=0,
        save_history=True,
    )

    writer = ScannerSingleWriteService(test_db)
    res = await writer.persist_single_final_write(aggregate)

    assert res.success is True
    assert res.latest_rows_upserted == 0
    assert res.history_rows_inserted == 0

    count = await test_db.scalar(select(func.count(LatestScanResult.id)))
    assert count == 0


@pytest.mark.asyncio
async def test_single_write_large_universe_batch_chunking(test_db):
    """Edge Case: Large universe scan with 550 candidates triggers parameterised 500-row batch chunking."""
    now = datetime.now(timezone.utc)
    candidates = [
        ScanCandidateDTO(symbol=f"STOCK_{i:04d}", strategy_name="S1", signal_type="BUY", score=80.0)
        for i in range(550)
    ]

    aggregate = ScanAggregateResult(
        scan_id="large-scan-001",
        symbol_universe="NIFTY500",
        execution_timestamp=now,
        candidates=candidates,
        total_scanned=550,
        total_candidates=550,
        save_history=True,
    )

    writer = ScannerSingleWriteService(test_db)
    res = await writer.persist_single_final_write(aggregate)

    assert res.success is True
    assert res.latest_rows_upserted == 550
    assert res.history_rows_inserted == 550

    count = await test_db.scalar(select(func.count(LatestScanResult.id)))
    assert count == 550
