import requests
import time

endpoints = [
    "/workstation/api-health",
    "/workstation/market-overview",
    "/workstation/saved-scans",
    "/workstation/scan-history?limit=20",
    "/workstation/risk-settings",
    "/workstation/alerts",
    "/api/token/status",
]

# Note: The prompt says /token/status but the route is defined under prefix "/api/token" -> "/api/token/status"
# Also /paper-trading/engine/status 

endpoints.append("/paper-trading/engine/status")

print("Endpoint\tHTTP Status\tResponse Time\tSuccess/Failure")
for ep in endpoints:
    url = f"http://127.0.0.1:8000{ep}"
    start = time.time()
    try:
        r = requests.get(url, timeout=10)
        ms = int((time.time() - start) * 1000)
        status = r.status_code
        success = "Success" if status == 200 else "Failure"
        print(f"{ep}\t{status}\t{ms}ms\t{success}")
        if status != 200:
            print(f"  Error body: {r.text}")
    except Exception as e:
        ms = int((time.time() - start) * 1000)
        print(f"{ep}\tError\t{ms}ms\tFailure ({e})")
