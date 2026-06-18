import asyncio
import argparse
from pathlib import Path
import aiosqlite
from sqlalchemy import text
import sys
from datetime import datetime, timezone
import os

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.db.session import AsyncSessionLocal

def localize_utc(naive_dt_str: str | None) -> datetime | None:
    if naive_dt_str is None:
        return None
    try:
        dt = datetime.fromisoformat(naive_dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None

async def migrate_candles(sqlite_path: Path):
    print("Starting candle migration...")
    sqlite_uri = f"file:{sqlite_path}?mode=ro"
    async with aiosqlite.connect(sqlite_uri, uri=True) as sqlite_conn:
        sqlite_conn.row_factory = aiosqlite.Row
        async with AsyncSessionLocal() as pg_session:
            async with sqlite_conn.execute("SELECT * FROM candles") as cursor:
                rows = await cursor.fetchall()
                print(f"Found {len(rows)} candles to migrate.")
                
                # We do batched inserts for speed
                chunk_size = 1000
                for i in range(0, len(rows), chunk_size):
                    chunk = rows[i:i + chunk_size]
                    values = []
                    params = {}
                    
                    for j, row in enumerate(chunk):
                        params[f"symbol_{j}"] = row["symbol"]
                        params[f"resolution_{j}"] = row["resolution"]
                        params[f"date_{j}"] = localize_utc(row["date"])
                        params[f"open_{j}"] = row["open"]
                        params[f"high_{j}"] = row["high"]
                        params[f"low_{j}"] = row["low"]
                        params[f"close_{j}"] = row["close"]
                        params[f"volume_{j}"] = row["volume"]
                        params[f"fetched_at_{j}"] = localize_utc(row["fetched_at"])
                        
                        values.append(
                            f"(:symbol_{j}, :resolution_{j}, :date_{j}, :open_{j}, :high_{j}, :low_{j}, :close_{j}, :volume_{j}, :fetched_at_{j})"
                        )
                    
                    query = text(f"""
                        INSERT INTO market_data.candles (symbol, resolution, date, open, high, low, close, volume, fetched_at)
                        VALUES {", ".join(values)}
                        ON CONFLICT (symbol, resolution, date) DO NOTHING
                    """)
                    
                    await pg_session.execute(query, params)
                    await pg_session.commit()
                    
                    print(f"Migrated {i + len(chunk)} / {len(rows)} candles.")
                    
    print("Candle migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_candles("trading_system.db"))
