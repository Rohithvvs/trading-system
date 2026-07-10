import requests

url = "http://127.0.0.1:8000/analysis/screener/full"
payload = {
    "mode": "swing",
    "timeframe": "1d",
    "symbols": [],
    "top_n": 20
}
headers = {
    "Content-Type": "application/json",
    "Accept": "text/event-stream"
}

print(f"Sending request to {url}")
try:
    response = requests.post(url, json=payload, headers=headers, stream=True)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        for line in response.iter_lines():
            if line:
                print(line.decode('utf-8'))
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
