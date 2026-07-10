import csv
import sys
import asyncio
from sqlalchemy import select, func
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db.session import AsyncSessionLocal
from app.models.stock import StockMaster

async def main():
    csv_path = r"F:\trading system01\trading system\ind_nifty500list.csv"
    expected = 0
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Symbol") or row.get("symbol"):
                expected += 1
                
    async with AsyncSessionLocal() as db:
        result = await db.scalar(select(func.count(StockMaster.id)))
        present = result or 0
        
    print(f"CSV Rows Expected: {expected}")
    print(f"DB Rows Present: {present}")
    print(f"Rows to Insert: {expected - present}")

if __name__ == "__main__":
    asyncio.run(main())
