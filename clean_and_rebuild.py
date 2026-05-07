import sys
import os
sys.path.insert(0, "F:/trading system01/trading system")

import sqlite3
import pandas as pd
from datetime import date, timedelta, datetime
import time

from backend.app.services.ohlcv_store import init_db, save_candles, update_ltp
from backend.app.config import settings
from fyers_apiv3 import fyersModel

DB_PATH  = "backend/data/ohlcv_cache.db"
CSV_PATH = "F:/trading system01/trading system/ind_nifty500list.csv"

# ── Step 1: Wipe DB ───────────────────────────
def clean_db():
    print("\n🗑️  Cleaning existing DB...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM ohlcv_daily")
    conn.execute("DELETE FROM ltp_cache")
    conn.commit()
    conn.close()
    print("✅ DB cleaned — all old data removed")

# ── Step 2: Build Fyers Client ────────────────
def build_client():
    client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
    token     = (settings.fyers_access_token or "").strip().strip('"').strip("'")
    if client_id and token.startswith(f"{client_id}:"):
        token = token.split(":", 1)[1]
    return fyersModel.FyersModel(
        client_id=client_id,
        token=token,
        is_async=False,
        log_path=""
    )

# ── Step 3: Fetch Candles for One Stock ───────
def fetch_candles(client, fyers_symbol):
    today = date.today()
    rows  = []
    for range_from, range_to in [
        (today - timedelta(days=730), today - timedelta(days=365)),
        (today - timedelta(days=365), today),
    ]:
        resp = client.history(data={
            "symbol"     : fyers_symbol,
            "resolution" : "1D",
            "date_format": "1",
            "range_from" : str(range_from),
            "range_to"   : str(range_to),
            "cont_flag"  : "1"
        })
        if resp.get("code") == 200:
            rows += resp.get("candles", [])
    
    # Convert + deduplicate
    seen = {}
    for row in rows:
        d = datetime.utcfromtimestamp(row[0]).strftime("%Y-%m-%d")
        seen[d] = {
            "date"  : d,
            "open"  : row[1],
            "high"  : row[2],
            "low"   : row[3],
            "close" : row[4],
            "volume": row[5]
        }
    return sorted(seen.values(), key=lambda x: x["date"])

# ── Step 4: Fetch LTP ─────────────────────────
def fetch_ltp(client, fyers_symbol):
    try:
        resp = client.quotes(data={"symbols": fyers_symbol})
        return float(resp["d"][0]["v"]["lp"])
    except:
        return None

# ── Main ──────────────────────────────────────
def main():
    # Confirm before wiping
    print("\n⚠️  WARNING: This will DELETE all existing candle data")
    print(f"   and refetch fresh data for all stocks in CSV")
    confirm = input("\n   Type 'YES' to continue: ").strip()
    if confirm != "YES":
        print("❌ Cancelled.")
        return

    # Clean DB
    clean_db()

    # Read CSV
    df_csv  = pd.read_csv(CSV_PATH)
    symbols = df_csv["Symbol"].dropna().str.strip().str.upper().tolist()
    total   = len(symbols)
    print(f"\n📋 Found {total} stocks in CSV")

    # Build client
    init_db()
    client  = build_client()

    # Verify token works
    test = client.quotes(data={"symbols": "NSE:RELIANCE-EQ"})
    if test.get("code") != 200:
        print(f"\n❌ Token check FAILED: {test.get('message')}")
        print("   Update FYERS_ACCESS_TOKEN in .env and retry")
        return
    print("✅ Token verified — starting rebuild...\n")

    fetched = failed = 0

    for i, sym in enumerate(symbols, 1):
        clean_sym  = sym.replace("-EQ", "")
        fyers_sym  = f"NSE:{clean_sym}-EQ"

        print(f"[{i:>4}/{total}] {clean_sym:<20}", end=" ")

        try:
            rows = fetch_candles(client, fyers_sym)
            if rows:
                save_candles(clean_sym, rows)
                ltp = fetch_ltp(client, fyers_sym)
                if ltp:
                    update_ltp(clean_sym, ltp)
                print(f"✅ {len(rows)} candles | LTP: ₹{ltp or 'N/A'}")
                fetched += 1
            else:
                print("⚠️  No candles returned")
                failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1

        time.sleep(0.3)

    print(f"""
{'='*50}
  CLEAN + REBUILD COMPLETE
{'='*50}
  Total   : {total}
  Fetched : {fetched}
  Failed  : {failed}
  DB Path : {DB_PATH}
{'='*50}
""")

if __name__ == "__main__":
    main()