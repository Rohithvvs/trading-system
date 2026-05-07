from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def normalize_database_url(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return "sqlite:///./trading_system.db"
    if "://" in value:
        return value
    if value.endswith(".db") or value.endswith(".sqlite") or value.endswith(".sqlite3"):
        return f"sqlite:///./{value}"
    return value


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Trading System")
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_url: str = normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite:///./trading_system.db")
    )
    cors_origins_raw: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
    )
    fyers_app_id: str = os.getenv("FYERS_APP_ID", "")
    fyers_access_token: str = os.getenv("FYERS_ACCESS_TOKEN", "")
    fyers_secret_id: str = os.getenv("FYERS_SECRET_ID", "")
    fyers_pin: str = os.getenv("FYERS_PIN", "")
    fyers_redirect_uri: str = os.getenv("FYERS_REDIRECT_URI", "")
    mongo_url: str = os.getenv("MONGO_URL", "")
    mongo_db_name: str = os.getenv("MONGO_DB_NAME", "")
    nifty500_csv_path: str = os.getenv("NIFTY500_CSV_PATH", "ind_nifty500list.csv")
    nifty500_symbols_raw: str = os.getenv("NIFTY500_SYMBOLS", "")
    nifty_next_500_symbols_raw: str = os.getenv("NIFTY_NEXT_500_SYMBOLS", "")
    universe_symbols_raw: str = os.getenv("UNIVERSE_SYMBOLS", os.getenv("NIFTY1000_SYMBOLS", ""))
    bse500_symbols_raw: str = os.getenv("BSE500_SYMBOLS", "")
    bse1000_symbols_raw: str = os.getenv("BSE1000_SYMBOLS", "")
    fyers_screener_symbols_raw: str = os.getenv(
        "FYERS_SCREENER_SYMBOLS",
        (
            "RELIANCE-EQ,INFY-EQ,TCS-EQ,HDFCBANK-EQ,ICICIBANK-EQ,SBIN-EQ,LT-EQ,ITC-EQ,"
            "AXISBANK-EQ,BAJFINANCE-EQ,HINDUNILVR-EQ,KOTAKBANK-EQ,ASIANPAINT-EQ,"
            "MARUTI-EQ,TITAN-EQ,ADANIPORTS-EQ,POWERGRID-EQ,ULTRACEMCO-EQ,NTPC-EQ,"
            "TATAMOTORS-EQ,TATASTEEL-EQ,M&M-EQ,SUNPHARMA-EQ,HCLTECH-EQ,WIPRO-EQ"
        ),
    )
    news_provider: str = os.getenv("NEWS_PROVIDER", "marketaux")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    news_base_url: str = os.getenv("NEWS_BASE_URL", "https://api.marketaux.com/v1/news/all")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    llm_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    advisory_disclaimer: str = os.getenv(
        "ADVISORY_DISCLAIMER",
        "Advisory only. This system does not place live trades and is not financial advice.",
    )
    cors_origins: list[str] = field(init=False)
    fyers_screener_symbols: list[str] = field(init=False)
    nifty500_symbols: list[str] = field(init=False)
    nifty_next_500_symbols: list[str] = field(init=False)
    bse500_symbols: list[str] = field(init=False)
    bse1000_symbols: list[str] = field(init=False)
    universe_symbols: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.cors_origins = [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]
        self.fyers_screener_symbols = [
            symbol.strip().upper() for symbol in self.fyers_screener_symbols_raw.split(",") if symbol.strip()
        ]
        self.nifty500_symbols = self._load_nifty500_symbols()
        nifty_next_source = self.nifty_next_500_symbols_raw or self._difference(
            self.universe_symbols_raw,
            ",".join(self.nifty500_symbols),
        )
        self.nifty_next_500_symbols = [
            symbol.strip().upper() for symbol in nifty_next_source.split(",") if symbol.strip()
        ]
        self.bse500_symbols = [
            symbol.strip().upper() for symbol in self.bse500_symbols_raw.split(",") if symbol.strip()
        ]
        self.bse1000_symbols = [
            symbol.strip().upper() for symbol in self.bse1000_symbols_raw.split(",") if symbol.strip()
        ]
        if self.universe_symbols_raw:
            self.universe_symbols = [
                symbol.strip().upper() for symbol in self.universe_symbols_raw.split(",") if symbol.strip()
            ]
        else:
            self.universe_symbols = list(self.nifty500_symbols)

    def _difference(self, larger: str, smaller: str) -> str:
        larger_symbols = [symbol.strip().upper() for symbol in larger.split(",") if symbol.strip()]
        smaller_keys = {
            symbol.strip().upper() for symbol in smaller.split(",") if symbol.strip()
        }
        return ",".join(symbol for symbol in larger_symbols if symbol not in smaller_keys)

    def _load_nifty500_symbols(self) -> list[str]:
        csv_symbols = self._load_nifty500_symbols_from_csv()
        if csv_symbols:
            return csv_symbols
        if self.nifty500_symbols_raw:
            return [
                symbol.strip().upper() for symbol in self.nifty500_symbols_raw.split(",") if symbol.strip()
            ]
        return list(self.fyers_screener_symbols)

    def _load_nifty500_symbols_from_csv(self) -> list[str]:
        csv_path = Path(self.nifty500_csv_path)
        if not csv_path.is_absolute():
            csv_path = ROOT_DIR / csv_path
        if not csv_path.exists():
            return []

        symbols: list[str] = []
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = (row.get("Symbol") or "").strip().upper()
                series = (row.get("Series") or "").strip().upper()
                if not symbol:
                    continue
                combined = f"{symbol}-{series}" if series else symbol
                symbols.append(combined)
        return list(dict.fromkeys(symbols))


settings = Settings()
