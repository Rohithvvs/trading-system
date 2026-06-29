import time

print("Starting app.routes import timing...")
t0 = time.time()

modules = [
    "app.routes.fyers",
    "app.routes.paper_trading",
    "app.routes.screener",
    "app.routes.orchestrator",
    "app.routes.analysis"
]

for mod in modules:
    t = time.time()
    try:
        __import__(mod)
        print(f"{mod}: {time.time() - t:.2f}s")
    except Exception as e:
        print(f"{mod} error: {e}")

print(f"Total time: {time.time() - t0:.2f}s")
