import asyncio
import sys
import os

# Ensure the project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.app.db.session import init_db
from backend.app.main import automated_screening_job

async def run_dry_run():
    print("Initializing Database and Schema (creating HistoricalCandle)...")
    init_db()
    
    print("Running Automated Screening Job...")
    await automated_screening_job()
    print("Screener Run Complete!")

if __name__ == "__main__":
    asyncio.run(run_dry_run())
