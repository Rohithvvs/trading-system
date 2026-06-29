import sys
sys.path.insert(0, "F:/trading system01/trading system")

from backend.app.services.ohlcv_store import init_db, get_candle_count, save_candles, update_ltp, get_ltp
from backend.app.config import settings
from fyers_apiv3 import fyersModel
from datetime import date, timedelta, datetime
import time

# ── Build Fyers Client ────────────────────────
client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
token     = (settings.fyers_access_token or "").strip().strip('"').strip("'")
if client_id and token.startswith(f"{client_id}:"):
    token = token.split(":", 1)[1]

client = fyersModel.FyersModel(
    client_id=client_id,
    token=token,
    is_async=False,
    log_path=""
)

# ── Test 3 Symbols Only ───────────────────────
TEST_SYMBOLS = ["TCS", "HDFCBANK", "INFY"]

init_db()
print("\n" + "="*50)
print("  BACKFILL TEST — 3 STOCKS (FETCH + SAVE)")
print("="*50)

for sym in TEST_SYMBOLS:
    fyers_sym = f"NSE:{sym}-EQ"
    print(f"\n[{sym}] Starting...")

    try:
        today = date.today()

        # ── Fetch candles (2 calls) ───────────────
        call1 = client.history(data={
            "symbol"     : fyers_sym,
            "resolution" : "1D",
            "date_format": "1",
            "range_from" : str(today - timedelta(days=730)),
            "range_to"   : str(today - timedelta(days=365)),
            "cont_flag"  : "1"
        })
        call2 = client.history(data={
            "symbol"     : fyers_sym,
            "resolution" : "1D",
            "date_format": "1",
            "range_from" : str(today - timedelta(days=365)),
            "range_to"   : str(today),
            "cont_flag"  : "1"
        })

        rows1 = call1.get("candles", []) if call1.get("code") == 200 else []
        rows2 = call2.get("candles", []) if call2.get("code") == 200 else []

        print(f"  Call1 → code:{call1.get('code')} | candles:{len(rows1)}")
        print(f"  Call2 → code:{call2.get('code')} | candles:{len(rows2)}")

        # ── Convert + deduplicate ─────────────────
        all_rows = rows1 + rows2
        seen = {}
        for row in all_rows:
            d = datetime.utcfromtimestamp(row[0]).strftime("%Y-%m-%d")
            seen[d] = {
                "date"  : d,
                "open"  : row[1],
                "high"  : row[2],
                "low"   : row[3],
                "close" : row[4],
                "volume": row[5]
            }
        final_rows = sorted(seen.values(), key=lambda x: x["date"])

        # ── Save candles to DB ────────────────────
        save_candles(sym, final_rows)
        print(f"  ✅ Saved {len(final_rows)} candles to DB")

        # ── Fetch + Save LTP ──────────────────────
        ltp_resp = client.quotes(data={"symbols": fyers_sym})
        try:
            ltp = float(ltp_resp["d"][0]["v"]["lp"])
            update_ltp(sym, ltp)
            print(f"  ✅ LTP saved: ₹{ltp}")
        except:
            print(f"  ⚠️  LTP not available (market closed)")

        # ── Verify from DB ────────────────────────
        db_count = get_candle_count(sym)
        db_ltp   = get_ltp(sym)
        print(f"  ✅ DB verify → candles:{db_count} | ltp:{db_ltp}")

    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    time.sleep(0.3)

print("\n" + "="*50)
print("TEST COMPLETE")
print("If all 3 show ✅ Saved → run full backfill")
print("="*50)