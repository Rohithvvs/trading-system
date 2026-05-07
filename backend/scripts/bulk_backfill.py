from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas
from fyers_apiv3 import fyersModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings
from backend.app.services.ohlcv_store import get_candle_count, init_db, save_candles, update_ltp


CSV_PATH = Path(r"F:\trading system01\trading system\ind_nifty500list.csv")


def read_symbols() -> list[tuple[str, str]]:
    frame = pandas.read_csv(CSV_PATH)
    symbols: list[tuple[str, str]] = []
    for raw_symbol in frame["Symbol"].dropna().tolist():
        symbol = str(raw_symbol).strip().upper()
        if not symbol:
            continue
        if not symbol.endswith("-EQ"):
            symbol = f"{symbol}-EQ"
        clean_symbol = symbol.removeprefix("NSE:")
        if clean_symbol.endswith("-EQ"):
            clean_symbol = clean_symbol[:-3]
        fyers_symbol = f"NSE:{clean_symbol}-EQ"
        symbols.append((clean_symbol, fyers_symbol))
    return symbols


def build_client():
    client_id = settings.fyers_app_id.strip().strip('"').strip("'")
    token = settings.fyers_access_token.strip().strip('"').strip("'")
    if client_id and token.startswith(f"{client_id}:"):
        token = token.split(":", 1)[1]
    return fyersModel.FyersModel(
        client_id=client_id,
        token=token,
        is_async=False,
        log_path="",
    )


def fetch_candles(client, fyers_symbol: str) -> list[dict]:
    today = date.today()
    ranges = [
        ((today - timedelta(days=730)).isoformat(), (today - timedelta(days=365)).isoformat()),
        ((today - timedelta(days=365)).isoformat(), today.isoformat()),
    ]
    merged_rows: dict[str, dict] = {}

    for range_from, range_to in ranges:
        payload = {
            "symbol": fyers_symbol,
            "resolution": "1D",
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1",
        }
        response = client.history(data=payload)
        if not isinstance(response, dict):
            print(f"  WARNING - invalid history response for {fyers_symbol} {range_from} to {range_to}")
            continue
        if response.get("code") != 200:
            print(
                f"  WARNING - history call failed for {fyers_symbol} {range_from} to {range_to} "
                f"(code={response.get('code')})"
            )
            continue

        for row in response.get("candles", []):
            if len(row) < 6:
                continue
            candle_date = datetime.utcfromtimestamp(row[0]).strftime("%Y-%m-%d")
            merged_rows[candle_date] = {
                "date": candle_date,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": int(row[5]),
            }

    return [merged_rows[key] for key in sorted(merged_rows)]


def fetch_ltp(client, fyers_symbol: str) -> float | None:
    try:
        response = client.quotes(data={"symbols": fyers_symbol})
    except Exception:
        return None

    if not isinstance(response, dict):
        return None

    try:
        value = response["d"][0]["v"]["lp"]
        return float(value)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def main() -> None:
    init_db()
    os.makedirs(PROJECT_ROOT / "backend" / "data", exist_ok=True)
    _ = sqlite3.connect(PROJECT_ROOT / "backend" / "data" / "ohlcv_cache.db").close()

    symbols = read_symbols()
    client = build_client()

    skipped = 0
    fetched = 0
    failed = 0
    total = len(symbols)

    for index, (clean_symbol, fyers_symbol) in enumerate(symbols, start=1):
        print(f"[{index:>3}/{total}] Processing {clean_symbol}...")
        try:
            count = get_candle_count(clean_symbol)
            if count >= 260:
                skipped += 1
                print(f"  SKIP - already has {count} candles")
            else:
                rows = fetch_candles(client, fyers_symbol)
                if rows:
                    save_candles(clean_symbol, rows)
                    fetched += 1
                    print(f"  DONE - saved {len(rows)} candles")
                else:
                    failed += 1
                    print("  FAILED - no data returned")

            ltp = fetch_ltp(client, fyers_symbol)
            if ltp is not None:
                update_ltp(clean_symbol, ltp)
                print(f"  LTP: {ltp}")

            time.sleep(0.3)
        except Exception as exc:
            failed += 1
            print(f"  ERROR: {str(exc)}")
            continue

    print("===============================")
    print("BULK BACKFILL COMPLETE")
    print(f"Total   : {total}")
    print(f"Fetched : {fetched}")
    print(f"Skipped : {skipped}")
    print(f"Failed  : {failed}")
    print("===============================")


if __name__ == "__main__":
    main()
