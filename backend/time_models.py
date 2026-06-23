import time

print("Starting app.models import timing...")
t0 = time.time()
try:
    from app.models import FyersToken
    print(f"app.models: {time.time() - t0:.2f}s")
except Exception as e:
    print(f"error: {e}")
