import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.append(str(root))

import os
import time
from backend.app.db import scan_store

db_path = scan_store.DB_PATH
if db_path.exists():
    try:
        os.remove(db_path)
        print("Removed old DB file")
    except Exception as e:
        print(f"Error removing old DB: {e}")

# Create dummy payload of ~10MB
dummy_payload = {
    "timestamp": "2023-10-27T10:00:00Z",
    "items": [
        {
            "symbol": f"SYM_{i}",
            "close": 150.5 + i,
            "ema_20": 149.0 + i,
            "volume": 100000 + i,
            "matched": i % 2 == 0,
            "signal": "bullish" if i % 2 == 0 else "neutral",
            # add a lot of text to inflate size
            "history": [{"date": f"2023-10-{d}", "c": 100+d} for d in range(1, 30)] * 10
        }
        for i in range(5000)
    ]
}

# Measure write time
import asyncio
start_write = time.time()
asyncio.run(scan_store.save_latest_scan(dummy_payload))
write_time = time.time() - start_write

# Measure DB size
db_size_kb = db_path.stat().st_size / 1024

# Measure read time
start_read = time.time()
loaded = asyncio.run(scan_store.load_latest_scan())
read_time = time.time() - start_read

assert loaded is not None, "Failed to load scan"
assert len(loaded["items"]) == 5000, "Item count mismatch"

print("="*40)
print(f"Write Time: {write_time:.4f}s")
print(f"Read Time:  {read_time:.4f}s")
print(f"DB Size:    {db_size_kb:.2f} KB")
print("="*40)
print("TEST SUCCESSFUL")
