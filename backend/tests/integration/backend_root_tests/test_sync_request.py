import requests

url = "http://127.0.0.1:8000/analysis/screener/full"
payload = {
    "mode": "swing",
    "top_n": 20,
    "lookback_days": 180,
    "swing_resolution": "1d",
    "custom_symbols": []
}

print(f"Sending request to {url}")
try:
    response = requests.post(url, json=payload, stream=True)
    print(f"Status Code: {response.status_code}")
    for line in response.iter_lines():
        if line:
            print(f"Received chunk: {line.decode('utf-8')}")
            break # just need to see that it started streaming successfully!
except Exception as e:
    print(f"Error: {e}")
