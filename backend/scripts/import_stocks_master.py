import csv
import sys
import asyncio
from sqlalchemy.dialects.postgresql import insert
import os
from pathlib import Path

# Robust path setup so the script works whether run directly,
# via python -m, or from repo root / Render environment.
_here = Path(__file__).resolve()
# Try common layouts: repo_root/backend/scripts/...
candidates = [
    _here.parents[1],   # backend/
    _here.parents[2],   # repo root/
    Path.cwd(),
]
for cand in candidates:
    if (cand / "app" / "db" / "session.py").exists():
        sys.path.insert(0, str(cand))
        break
else:
    # Fallback
    sys.path.append(str(_here.parents[1]))

from app.db.session import AsyncSessionLocal
from app.models.stock import StockMaster

async def import_csv(csv_path: str, universe: str):
    print(f"Importing {csv_path} into universe {universe}...")
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return

    records = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_symbol = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
            if not raw_symbol:
                continue
                
            series = (row.get("Series") or row.get("series") or "").strip().upper()
            
            # Normalization: ABC -> ABC-EQ
            if series == "EQ" and not raw_symbol.endswith("-EQ"):
                symbol = f"{raw_symbol}-EQ"
            elif not series and not raw_symbol.endswith("-EQ"):
                symbol = f"{raw_symbol}-EQ"
            else:
                symbol = raw_symbol

            company_name = (row.get("Company Name") or row.get("company_name") or "").strip()
            sector = (row.get("Industry") or row.get("industry") or row.get("sector") or "").strip()
            isin = (row.get("ISIN Code") or row.get("isin") or "").strip()

            records.append({
                "symbol": symbol,
                "company_name": company_name,
                "sector": sector,
                "series": series,
                "isin": isin,
                "universe": universe,
                "is_active": True,
            })

    if not records:
        print("No valid records found.")
        return

    async with AsyncSessionLocal() as db:
        stmt = insert(StockMaster).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "company_name": stmt.excluded.company_name,
                "sector": stmt.excluded.sector,
                "series": stmt.excluded.series,
                "isin": stmt.excluded.isin,
                "universe": stmt.excluded.universe,
                "is_active": True,
            }
        )
        await db.execute(stmt)
        await db.commit()
    print(f"Successfully upserted {len(records)} records for universe {universe}.")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "ind_nifty500list.csv"
    universe = sys.argv[2] if len(sys.argv) > 2 else "NIFTY500"
    asyncio.run(import_csv(csv_path, universe))
