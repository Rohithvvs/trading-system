import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("--- 1. Place BUY Order ---")
    import uuid
    payload = {
        "symbol": "SBIN-EQ",
        "side": "BUY",
        "qty": 10,
        "order_type": "MARKET",
        "product_type": "MIS",
        "idempotency_key": str(uuid.uuid4())
    }
    r = requests.post(f"{BASE_URL}/paper-trading/orders", json=payload)
    print("Response:", r.status_code, r.text)
    if r.status_code != 200:
        return
    
    order_data = r.json()
    order_id = order_data["id"]
    
    print("--- 2. Get Pending Orders ---")
    r = requests.get(f"{BASE_URL}/paper-trading/orders/pending")
    print("Response:", r.status_code, r.text)
    
    print("--- 3. Get Positions ---")
    r = requests.get(f"{BASE_URL}/paper-trading/positions")
    print("Response:", r.status_code, r.text)
    
    print("--- 4. Get Account Summary ---")
    r = requests.get(f"{BASE_URL}/paper-trading/account")
    print("Response:", r.status_code, r.text)
    
    # We might not need to modify because market order should fill instantly (or stay pending if no engine)
    # Wait, the engine fills orders if LTP matches. Let's see if it filled.
    time.sleep(2)
    
    print("--- 5. Place SELL Order to close ---")
    payload = {
        "symbol": "SBIN-EQ",
        "side": "SELL",
        "qty": 10,
        "order_type": "MARKET",
        "product_type": "MIS",
        "idempotency_key": str(uuid.uuid4())
    }
    r = requests.post(f"{BASE_URL}/paper-trading/orders", json=payload)
    print("Response:", r.status_code, r.text)

if __name__ == "__main__":
    run_tests()
