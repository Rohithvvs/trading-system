import requests

url = "http://127.0.0.1:8000/workstation/market-overview"

print(f"Sending request to {url}")
try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
