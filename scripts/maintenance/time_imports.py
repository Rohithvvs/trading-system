import time

print("Starting import timing...")
t0 = time.time()

t1 = time.time()
try:
    from app.config import settings
    print(f"app.config: {time.time() - t1:.2f}s")
except Exception as e:
    print(f"config error: {e}")

t2 = time.time()
try:
    from app.db import init_db
    print(f"app.db: {time.time() - t2:.2f}s")
except Exception as e:
    print(f"db error: {e}")

t3 = time.time()
try:
    from app.routes import api_router
    print(f"app.routes: {time.time() - t3:.2f}s")
except Exception as e:
    print(f"routes error: {e}")

t4 = time.time()
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    print(f"apscheduler: {time.time() - t4:.2f}s")
except Exception as e:
    print(f"apscheduler error: {e}")

t5 = time.time()
try:
    from app.services.market_engine_service import market_engine
    print(f"market_engine_service: {time.time() - t5:.2f}s")
except Exception as e:
    print(f"market_engine_service error: {e}")

print(f"Total time: {time.time() - t0:.2f}s")
