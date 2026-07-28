import pytest
import pytest_asyncio
from datetime import datetime, timezone
from decimal import Decimal
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
async def test_single_final_write_upserts_latest(test_db):
    now = datetime.now(timezone.utc)
    c1 = ScanCandidateDTO(symbol="RELIANCE", strategy_name="S1", signal_type="BUY", score=85.0)
    c2 = ScanCandidateDTO(symbol="INFY", strategy_name="S1", signal_type="WATCH", score=72.0)

    aggregate = ScanAggregateResult(
        scan_id="scan-001",
        symbol_universe="NIFTY500",
        execution_timestamp=now,
        candidates=[c1, c2],
        total_scanned=500,
        total_candidates=2,
        save_history=False,
    )

    writer = ScannerSingleWriteService(test_db)
    res = await writer.persist_single_final_write(aggregate)

    assert res.success is True
    assert res.latest_rows_upserted == 2

    # Query DB to confirm atomic commit
    count = await test_db.scalar(select(func.count(LatestScanResult.id)))
    assert count == 2

    rows = (await test_db.execute(select(LatestScanResult))).scalars().all()
    symbols = {r.symbol for r in rows}
    assert symbols == {"RELIANCE", "INFY"}


@pytest.mark.asyncio
async def test_single_final_write_overwrites_existing(test_db):
    now = datetime.now(timezone.utc)
    # First write
    c1 = ScanCandidateDTO(symbol="RELIANCE", strategy_name="S1", signal_type="BUY", score=80.0)
    agg1 = ScanAggregateResult(scan_id="scan-001", candidates=[c1], execution_timestamp=now)
    writer = ScannerSingleWriteService(test_db)
    await writer.persist_single_final_write(agg1)

    # Second write with updated score
    c2 = ScanCandidateDTO(symbol="RELIANCE", strategy_name="S1", signal_type="BUY", score=95.0)
    agg2 = ScanAggregateResult(scan_id="scan-002", candidates=[c2], execution_timestamp=now)
    await writer.persist_single_final_write(agg2)

    count = await test_db.scalar(select(func.count(LatestScanResult.id)))
    assert count == 1

    row = (await test_db.execute(select(LatestScanResult).where(LatestScanResult.symbol == "RELIANCE"))).scalar_one()
    assert float(row.score) == 95.0
