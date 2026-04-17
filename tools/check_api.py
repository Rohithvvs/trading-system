import json
import urllib.request
import urllib.error
import sys

BASE = "http://127.0.0.1:8000"
OPENAPI = f"{BASE}/openapi.json"

try:
    data = urllib.request.urlopen(OPENAPI, timeout=5).read()
except Exception as e:
    print("openapi_error:", e)
    sys.exit(1)

spec = json.loads(data)
paths = list(spec.get("paths", {}).keys())
print("openapi_paths_count:", len(paths))

if "/analysis/screener/full" in paths:
    print("screener_path: FOUND")
else:
    print("screener_path: NOT FOUND")

# Try POST to screener
url = f"{BASE}/analysis/screener/full"
req_data = json.dumps({"mode": "paper", "timeframe": {}, "symbols": [], "top_n": 1}).encode("utf-8")
req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")

try:
    resp = urllib.request.urlopen(req, timeout=10)
    body = resp.read().decode("utf-8")
    print("POST_STATUS:", resp.getcode())
    print("POST_BODY:", body)
except urllib.error.HTTPError as e:
    try:
        body = e.read().decode("utf-8")
    except Exception:
        body = "<no body>"
    print("HTTPError:", e.code, body)
except Exception as e:
    print("POST_ERROR:", e)
