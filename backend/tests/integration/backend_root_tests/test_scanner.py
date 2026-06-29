import requests
import json

url = "http://127.0.0.1:8000/analysis/screener/full"
payload = {
    "mode": "swing",
    "top_n": 1,
    "timeframe": {
        "lookback_window": 180,
        "swing": "1d",
        "intraday": "15m"
    },
    "symbols": ["ABB"]
}
response = requests.post(url, json=payload, stream=True)
for line in response.iter_lines():
    if line:
        print(line.decode("utf-8"))
