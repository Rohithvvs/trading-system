import sys
import os

sys.path.append(r"F:\trading system01\trading system\backend")
from backend.app.config import settings
from fyers_apiv3 import fyersModel
import json

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcUdsQk1pMHhiUGJUTUtVSUZVM0ZkWGk4SXpGNDNnV21MV3Q4NnZubTE4RHpkRkdXY0JhUFFkNWh0QWFTU3lITkplUTFzQzhQZ1lTSHBsckgzVU9aVExNdGJDdExiaC1md1Z0WkV2Vk5JNldicFVqZz0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiJlMWYxMTgxMjVlNjgzMDRlYzhkZDI4MDcxM2UyNjk4Y2EwZmE1YmQ5OWMyNjUwN2RjZDA1OTAyMyIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWUowODcxOCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzgwMTg3NDAwLCJpYXQiOjE3ODAxMDkzODgsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc4MDEwOTM4OCwic3ViIjoiYWNjZXNzX3Rva2VuIn0.22EqteAUOZxQf8tkFjXm1WVphN8bUuz4TLx6uwjxgxg"
client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")

client = fyersModel.FyersModel(
    is_async=False,
    client_id=client_id,
    token=token,
    log_path=""
)

try:
    print("--- Profile ---")
    print(client.get_profile())
    print("--- Funds ---")
    print(client.funds())
    print("--- Holdings ---")
    print(client.holdings())
    print("--- Positions ---")
    print(client.positions())
    print("--- Quotes ---")
    print(client.quotes({"symbols": "NSE:SBIN-EQ"}))
    print("--- History ---")
    print(client.history({
        "symbol": "NSE:SBIN-EQ",
        "resolution": "1",
        "date_format": "1",
        "range_from": "2024-05-01",
        "range_to": "2024-05-02",
        "cont_flag": "1"
    }))
except Exception as e:
    print("Error:", str(e))
