import requests
import uuid
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("--- 1. Place BUY Order ---")
    payload = {
        "symbol": "SBIN-EQ",
        "side": "BUY",
        "qty": 5,
        "order_type": "MARKET",
        "product_type": "MIS",
        "idempotency_key": str(uuid.uuid4())
    }
    r = requests.post(f"{BASE_URL}/paper-trading/orders", json=payload)
    print("BUY Response:", r.status_code, r.text)

    print("--- 2. Get Positions ---")
    r = requests.get(f"{BASE_URL}/paper-trading/positions")
    print("Positions Response:", r.status_code, r.text)
    
    positions = r.json()
    open_qty = 0
    for p in positions:
        if p["symbol"] == "SBIN-EQ":
            open_qty += p["qty"]
            
    if open_qty > 0:
        print(f"--- 3. Place SELL Order to close {open_qty} shares ---")
        payload = {
            "symbol": "SBIN-EQ",
            "side": "SELL",
            "qty": open_qty,
            "order_type": "MARKET",
            "product_type": "MIS",
            "idempotency_key": str(uuid.uuid4())
        }
        r = requests.post(f"{BASE_URL}/paper-trading/orders", json=payload)
        print("SELL Response:", r.status_code, r.text)
        
    print("--- 4. Final Account Summary ---")
    r = requests.get(f"{BASE_URL}/paper-trading/account")
    print("Account Response:", r.status_code, r.text)

if __name__ == "__main__":
    run_tests()
