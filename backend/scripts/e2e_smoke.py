import os
import sys
# Ensure test routes are enabled
os.environ.setdefault("APP_ENV", "test")

# Ensure the project root is on sys.path so `import backend` works
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

print("Resetting test diagnostics...")
res = client.post("/test-diagnostics/reset")
print(res.status_code, res.text)

print("Resetting paper account...")
res = client.post("/paper-trading/account/reset", json={"starting_balance": 1000000})
print(res.status_code)
try:
    print(res.json())
except Exception:
    print(res.text)

print("Placing order...")
order_payload = {
    "symbol": "INFY-EQ",
    "side": "BUY",
    "type": "MARKET",
    "qty": 10,
    "price": 100.0,
    "notes": "smoke test buy",
}
res = client.post("/paper-trading/orders", json=order_payload)
print("POST /paper-trading/orders ->", res.status_code)
try:
    print(res.json())
except Exception:
    print(res.text)

print("Fetching account summary...")
res = client.get("/paper-trading/account/summary")
print(res.status_code)
try:
    print(res.json())
except Exception:
    print(res.text)

print("Fetching positions...")
res = client.get("/paper-trading/positions")
print(res.status_code)
try:
    print(res.json())
except Exception:
    print(res.text)
