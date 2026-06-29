import requests
import time

print("Testing api-health...")
try:
    res = requests.get("http://127.0.0.1:8000/workstation/api-health", timeout=3)
    print("API health:", res.status_code, res.text)
except Exception as e:
    print("API health failed:", e)

print("Testing scan/latest...")
try:
    res = requests.get("http://127.0.0.1:8000/analysis/scan/latest", timeout=3)
    print("Scan latest:", res.status_code, res.text)
except Exception as e:
    print("Scan latest failed:", e)
