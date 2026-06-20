import requests

print("Testing /scanner/latest")
try:
    response = requests.get("http://127.0.0.1:8000/workstation/market-overview", timeout=30)
    print(f"Status: {response.status_code}")
    print(response.text[:200])
except Exception as e:
    print(f"Error: {e}")
