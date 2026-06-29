import time

print("Starting rest of imports timing...")
t0 = time.time()

modules = [
    "app.services.candle_store",
    "app.db.session",
    "app.services.paper_trading_service",
    "app.db.locks",
    "app.core.task_supervisor",
    "app.schemas",
    "app.observability.scan_diagnostics",
    "app.core.log_manager"
]

for mod in modules:
    t = time.time()
    try:
        __import__(mod)
        print(f"{mod}: {time.time() - t:.2f}s")
    except Exception as e:
        print(f"{mod} error: {e}")

print(f"Total time: {time.time() - t0:.2f}s")
