from fyers_apiv3 import fyersModel
from backend.app.config import settings


def _sanitize_token(token: str | None, client_id: str | None = None) -> str:
    t = (token or "").strip().strip('"').strip("'")
    if client_id:
        cid = (client_id or "").strip().strip('"').strip("'")
        if cid and t.startswith(f"{cid}:"):
            t = t.split(":", 1)[1]
    return t


client = fyersModel.FyersModel(
    is_async=False,
    client_id=(settings.fyers_app_id or "").strip().strip('"').strip("'"),
    token=_sanitize_token(settings.fyers_access_token, settings.fyers_app_id),
    log_path=""
)

payload = {
    "symbol": "NSE:RELIANCE-EQ",
    "resolution": "1D",
    "date_format": "1",
    "range_from": "2025-01-01",
    "range_to": "2026-05-02",
    "cont_flag": "1"
}

response = client.history(data=payload)
print("PAYLOAD =", payload)
print("RAW_RESPONSE =", response)
print("CANDLE_COUNT =", len(response.get("candles", [])) if isinstance(response, dict) else "not-dict")