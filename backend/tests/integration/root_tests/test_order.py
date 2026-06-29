import httpx
import uuid
resp = httpx.post("http://127.0.0.1:8000/paper-trading/orders", json={
    "symbol": "RELIANCE-EQ",
    "side": "BUY",
    "qty": 1,
    "type": "MARKET",
    "idempotency_key": str(uuid.uuid4())
})
print(resp.status_code)
print(resp.text)
