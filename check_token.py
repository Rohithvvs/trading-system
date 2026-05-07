from fyers_apiv3 import fyersModel

# Paste your exact values here
APP_ID = "8BC5U9HYCQ-100"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcC1VeUplNldMdjdpZjhHT0x2WmdBb1E2ckNMeGlBTEFtOW1fTDZZWENQY1VjWkFHMXU4UW9OcFNGWFYwN1VCTnhxblhCVDQ1d3FhZi1BWG9oYVozVk50bmEtRDZwVEo3cnRMcnNkRXNkTnliT1IyMD0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI0NTljMjA5MmUyZTk4ZjM2NWE2NTRiMDk4NzlhM2IxOWMwOTg1ZjBkMTFiNTU0YjY5YzI2NjY1MyIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWUowODcxOCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzc4MDI3NDAwLCJpYXQiOjE3Nzc5NDU3MzcsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc3Nzk0NTczNywic3ViIjoiYWNjZXNzX3Rva2VuIn0.HERPH3pi_izr5Yk5DiSDEaSisryFEveRofQOaozXG2A"


fyers = fyersModel.FyersModel(
    client_id=APP_ID,
    token=ACCESS_TOKEN,
    is_async=False,
    log_path=""
)

# Request 1 - older data
r1 = fyers.history(data={
    "symbol": "NSE:RELIANCE-EQ",
    "resolution": "1D",
    "date_format": "1",
    "range_from": "2025-01-01",
    "range_to": "2025-12-31",
    "cont_flag": "1"
})

# Request 2 - recent data
r2 = fyers.history(data={
    "symbol": "NSE:RELIANCE-EQ",
    "resolution": "1D",
    "date_format": "1",
    "range_from": "2026-01-01",
    "range_to": "2026-05-03",
    "cont_flag": "1"
})

c1 = r1.get("candles", [])
c2 = r2.get("candles", [])
total = c1 + c2

print("Request 1 code    :", r1.get("code"), "| Candles:", len(c1))
print("Request 2 code    :", r2.get("code"), "| Candles:", len(c2))
print("Total candles     :", len(total))
print("Passes 220 check? :", len(total) >= 220)