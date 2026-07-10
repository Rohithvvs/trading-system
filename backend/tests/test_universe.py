import pytest
import os
from sqlalchemy import select
from backend.app.models.stock import StockMaster
from backend.app.services.universe_service import UniverseService
from backend.scripts.import_stocks_master import import_csv
from backend.app.db.session import AsyncSessionLocal

@pytest.fixture
def sample_csv(tmp_path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "Symbol,Company Name,Industry,Series,ISIN Code\n"
        "RELIANCE,Reliance Industries,Energy,EQ,INE123456\n"
        "TCS,Tata Consultancy,IT,EQ,INE654321\n"
        "INFY,Infosys,IT,,INE987654\n"
        "DUP,Duplicate,IT,EQ,INE000\n"
        "DUP,Duplicate,IT,EQ,INE000\n"
    )
    return str(csv_file)

@pytest.mark.asyncio
async def test_table_creation_and_import(sample_csv):
    # Test CSV import
    await import_csv(sample_csv, "TEST_UNIVERSE")
    
    # Test retrieval
    symbols = await UniverseService.get_active_symbols("TEST_UNIVERSE")
    assert len(symbols) == 4
    
    assert "RELIANCE-EQ" in symbols
    assert "TCS-EQ" in symbols
    assert "INFY-EQ" in symbols
    assert "DUP-EQ" in symbols

@pytest.mark.asyncio
async def test_empty_universe():
    symbols = await UniverseService.get_active_symbols("EMPTY_UNIVERSE")
    assert symbols == []

@pytest.mark.asyncio
async def test_duplicate_handling(sample_csv):
    # DUP is in the CSV twice
    await import_csv(sample_csv, "DUP_UNIVERSE")
    
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(StockMaster).where(StockMaster.symbol == "DUP-EQ")
        )
        # Should only be one entry
        assert len(list(result.all())) == 1
