import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("--- 3. Get Positions ---")
    r = requests.get(f"{BASE_URL}/paper-trading/positions")
    print("Response:", r.status_code, r.text)
    
    positions = r.json()
    pos_id = None
    if positions:
        pos_id = positions[0]["id"]
        
    if pos_id:
        print("--- 5. Place SELL Order to close ---")
        import uuid
        payload = {
            "symbol": "SBIN-EQ",
            "side": "SELL",
            "qty": 20,
            "order_type": "MARKET",
            "product_type": "MIS",
            "idempotency_key": str(uuid.uuid4())
        }
        r = requests.post(f"{BASE_URL}/paper-trading/orders", json=payload)
        print("Response:", r.status_code, r.text)
        
    print("--- 4. Get Account Summary ---")
    r = requests.get(f"{BASE_URL}/paper-trading/account")
    print("Response:", r.status_code, r.text)

if __name__ == "__main__":
    run_tests()
