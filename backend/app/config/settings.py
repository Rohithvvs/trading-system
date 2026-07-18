from __future__ import annotations

import csv
import logging
from pathlib import Path
from functools import cached_property
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

_logger = logging.getLogger("app.config")

ROOT_DIR = Path(__file__).resolve().parents[3]


def normalize_postgres_ssl_query(raw_value: str) -> str:
    parsed = urlsplit(raw_value)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2"}:
        return raw_value

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_pairs: list[tuple[str, str]] = []
    ssl_value: str | None = None
    has_sslmode = False

    for key, value in query_pairs:
        if key == "sslmode":
            has_sslmode = True
            normalized_pairs.append((key, value))
            continue
        if key == "ssl":
            ssl_value = value.lower()
            continue
        normalized_pairs.append((key, value))

    if ssl_value is not None and not has_sslmode:
        sslmode = "require" if ssl_value in {"1", "true", "yes", "require"} else "disable"
        normalized_pairs.append(("sslmode", sslmode))

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(normalized_pairs, doseq=True),
            parsed.fragment,
        )
    )


def normalize_database_url(raw_value: str) -> str:
    value = normalize_postgres_ssl_query(raw_value.strip())
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://") and not value.startswith("postgresql+asyncpg://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value

class Settings(BaseSettings):
    app_name: str = "Trading System"
    app_env: str = "development"
    google_client_id: str = ""
    quarantine_mode: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins_raw: str = Field(default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000", alias="CORS_ORIGINS")
    
    fyers_app_id: str = ""
    fyers_access_token: str = ""
    fyers_secret_id: str = ""
    fyers_pin: str = ""
    fyers_redirect_uri: str = ""
    mongo_url: str = ""
    mongo_db_name: str = ""
    nifty500_csv_path: str = "ind_nifty500list.csv"
    nifty500_symbols_raw: str = Field(default="", alias="NIFTY500_SYMBOLS")
    nifty_next_500_symbols_raw: str = Field(default="", alias="NIFTY_NEXT_500_SYMBOLS")
    nifty1000_symbols_raw: str = Field(default="", alias="NIFTY1000_SYMBOLS")
    universe_symbols_raw: str = Field(default="", alias="UNIVERSE_SYMBOLS")
    bse500_symbols_raw: str = Field(default="", alias="BSE500_SYMBOLS")
    bse1000_symbols_raw: str = Field(default="", alias="BSE1000_SYMBOLS")
    fyers_screener_symbols_raw: str = Field(
        default=(
            "RELIANCE-EQ,INFY-EQ,TCS-EQ,HDFCBANK-EQ,ICICIBANK-EQ,SBIN-EQ,LT-EQ,ITC-EQ,"
            "AXISBANK-EQ,BAJFINANCE-EQ,HINDUNILVR-EQ,KOTAKBANK-EQ,ASIANPAINT-EQ,"
            "MARUTI-EQ,TITAN-EQ,ADANIPORTS-EQ,POWERGRID-EQ,ULTRACEMCO-EQ,NTPC-EQ,"
            "TATAMOTORS-EQ,TATASTEEL-EQ,M&M-EQ,SUNPHARMA-EQ,HCLTECH-EQ,WIPRO-EQ"
        ),
        alias="FYERS_SCREENER_SYMBOLS"
    )

    # Allow the app to start with empty stocks_master (useful for initial deploys / data seeding)
    require_universe_data: bool = Field(default=True, alias="REQUIRE_UNIVERSE_DATA")
    news_provider: str = "marketaux"
    news_api_key: str = ""
    news_base_url: str = "https://api.marketaux.com/v1/news/all"
    llm_provider: str = "groq"
    llm_api_key: str = Field(default="", alias="GROQ_API_KEY")
    llm_model: str = "LLAMA_3_70B"
    admin_email: str = Field(default="", alias="ADMIN_EMAIL")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    advisory_disclaimer: str = "Advisory only. This system does not place live trades and is not financial advice."

    # FEAT-008 realistic trade execution control plane
    # Master switch; when False, orchestrator forces LEGACY path.
    feat008_enabled: bool = Field(default=True, alias="FEAT008_ENABLED")
    # REALISTIC | LEGACY — fill model for primary metrics
    feat008_execution_model: str = Field(default="REALISTIC", alias="FEAT008_EXECUTION_MODEL")
    # Whether composite score uses realistic (True) or legacy (False) metrics
    feat008_composite_uses_realistic: bool = Field(
        default=True, alias="FEAT008_COMPOSITE_USES_REALISTIC"
    )
    # Skip trades that lack a next bar for realistic entry (default True)
    feat008_skip_on_missing_next_bar: bool = Field(
        default=True, alias="FEAT008_SKIP_ON_MISSING_NEXT_BAR"
    )

    # FEAT-004: Market regime overlay (disabled by default)
    feat004_enabled: bool = False
    feat004_stage: str = "SHADOW"
    feat004_score_delta_fav: float = 2.0
    feat004_score_delta_neu: float = 0.0
    feat004_score_delta_cau: float = -3.0
    feat004_score_delta_def: float = -5.0
    feat004_score_delta_abs: float = 0.0
    feat004_buy_downgrade_threshold_cau: float = 74.0
    feat004_buy_downgrade_threshold_def: float = 77.0
    feat004_buy_threshold: float = 72.0
    feat004_favorable_cap_below_buy: bool = True
    feat004_sector_mapping_enabled: bool = True
    feat004_sector_min_candles: int = 50
    feat004_benchmark_symbols: str = "NIFTY500"
    feat004_min_benchmark_candles: int = 220
    feat004_staleness_limit_days: int = 1

    # FEAT-007: Sector relative strength overlay (disabled by default)
    feat007_enabled: bool = False
    feat007_stage: str = "SHADOW"
    feat007_score_delta_strength: float = 1.5
    feat007_score_delta_weak: float = -3.0
    feat007_buy_downgrade_threshold: float = 74.0
    feat007_buy_threshold: float = 72.0
    feat007_strength_cap_enabled: bool = True

    # FEAT-008: Execution model
    feat008_enabled: bool = True
    feat008_execution_model: str = "REALISTIC"
    feat008_composite_uses_realistic: bool = True
    feat008_skip_on_missing_next_bar: bool = True

    # Convention (config-contract Specs): use Field(...) for defaults/constraints; env names
    # are UPPER_SNAKE via alias (same pattern as FEAT-008). Values are NON-BINDING until a
    # later spec wires consumers — do not treat flags as proof of runtime behavior.
    #
    # FEAT-024A Spec 1 (004-execution-costs-config): configuration contract only.
    # Loaded from env but NON-BINDING until later FEAT-024A specs wire consumers.
    # Separate from FEAT-008 / backtest_service cost profiles (slippage_rate, brokerage_rate).
    costs_enabled: bool = Field(default=True, alias="COSTS_ENABLED")
    slippage_bps: float = Field(default=5.0, alias="SLIPPAGE_BPS")
    commission_fixed: float = Field(default=0.50, alias="COMMISSION_FIXED")
    commission_percent: float = Field(default=0.001, alias="COMMISSION_PERCENT")

    # FEAT-024B Spec 1 (005-portfolio-config): configuration contract only.
    # Loaded from env (PORTFOLIO_*) but NON-BINDING until later FEAT-024B specs wire consumers.
    # Do not treat portfolio_simulation_enabled=True as evidence that multi-asset portfolio
    # simulation, sizing, or cash accounting runs.
    # Dual source of truth (intentional Spec 1): BacktestService hardcoded equity 100000.0
    # and run(position_sizing_pct=...) remain authoritative for single-asset backtests.
    portfolio_simulation_enabled: bool = Field(default=False, alias="PORTFOLIO_SIMULATION_ENABLED")
    portfolio_max_concurrent_positions: int = Field(default=5, ge=1, alias="PORTFOLIO_MAX_CONCURRENT_POSITIONS")
    portfolio_max_position_pct: float = Field(default=20.0, gt=0.0, le=100.0, alias="PORTFOLIO_MAX_POSITION_PCT")
    portfolio_minimum_trade_value: float = Field(default=1000.0, ge=0.0, alias="PORTFOLIO_MINIMUM_TRADE_VALUE")
    # Effectively a constant in Spec 1: default False and validator rejects True (NSE/BSE).
    portfolio_allow_fractional_shares: bool = Field(
        default=False,
        alias="PORTFOLIO_ALLOW_FRACTIONAL_SHARES",
        description="Must remain False for Indian Cash Equity whole-share delivery (Spec 1).",
    )
    portfolio_reserve_cash_enabled: bool = Field(default=False, alias="PORTFOLIO_RESERVE_CASH_ENABLED")
    portfolio_starting_capital: float = Field(default=100000.0, ge=1000.0, alias="PORTFOLIO_STARTING_CAPITAL")

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding='utf-8',
        extra="ignore",
        populate_by_name=True
    )

    @field_validator("database_url", mode="before")
    def _validate_db_url(cls, v, info):
        if v:
            return normalize_database_url(v)
        return "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"

    @field_validator("feat008_execution_model", mode="before")
    @classmethod
    def _normalize_exec_model(cls, v: str | None) -> str:
        if v is None or not str(v).strip():
            return "REALISTIC"
        cleaned = str(v).strip().upper()
        if cleaned in {"REALISTIC", "LEGACY"}:
            return cleaned
        _logger.warning(
            "Unknown execution_model %r – normalising to REALISTIC.  Valid: %s",
            v, ["REALISTIC", "LEGACY"],
        )
        return "REALISTIC"

    @field_validator("portfolio_simulation_enabled")
    @classmethod
    def _warn_portfolio_simulation_non_binding(cls, v: bool) -> bool:
        # Audit M1 / hardening: flag is loadable but has no runtime consumers in Spec 1.
        if v is True:
            _logger.warning(
                "portfolio_simulation_enabled=True is NON-BINDING in FEAT-024B Spec 1 "
                "(005-portfolio-config): multi-asset portfolio simulation, position sizing, "
                "and cash accounting are not wired yet. BacktestService single-asset paths "
                "remain unchanged."
            )
        return v

    @field_validator("portfolio_allow_fractional_shares")
    @classmethod
    def _validate_fractional_shares(cls, v: bool) -> bool:
        if v is True:
            raise ValueError(
                "Fractional shares are not allowed for Indian Cash Equity swing trading."
            )
        return v

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @cached_property
    def fyers_screener_symbols(self) -> list[str]:
        return [
            symbol.strip().upper() for symbol in self.fyers_screener_symbols_raw.split(",") if symbol.strip()
        ]

    @cached_property
    def nifty500_symbols(self) -> list[str]:
        csv_symbols = self._load_nifty500_symbols_from_csv()
        if csv_symbols:
            return csv_symbols
        if self.nifty500_symbols_raw:
            return [
                symbol.strip().upper() for symbol in self.nifty500_symbols_raw.split(",") if symbol.strip()
            ]
        return list(self.fyers_screener_symbols)

    @cached_property
    def universe_symbols(self) -> list[str]:
        actual_universe_raw = self.universe_symbols_raw or self.nifty1000_symbols_raw
        if actual_universe_raw:
            return [
                symbol.strip().upper() for symbol in actual_universe_raw.split(",") if symbol.strip()
            ]
        return list(self.nifty500_symbols)

    @cached_property
    def nifty_next_500_symbols(self) -> list[str]:
        actual_universe_raw = self.universe_symbols_raw or self.nifty1000_symbols_raw
        nifty_next_source = self.nifty_next_500_symbols_raw or self._difference(
            actual_universe_raw,
            ",".join(self.nifty500_symbols),
        )
        return [
            symbol.strip().upper() for symbol in nifty_next_source.split(",") if symbol.strip()
        ]

    @cached_property
    def bse500_symbols(self) -> list[str]:
        return [
            symbol.strip().upper() for symbol in self.bse500_symbols_raw.split(",") if symbol.strip()
        ]

    @cached_property
    def bse1000_symbols(self) -> list[str]:
        return [
            symbol.strip().upper() for symbol in self.bse1000_symbols_raw.split(",") if symbol.strip()
        ]

    def _difference(self, larger: str, smaller: str) -> str:
        larger_symbols = [symbol.strip().upper() for symbol in larger.split(",") if symbol.strip()]
        smaller_keys = {
            symbol.strip().upper() for symbol in smaller.split(",") if symbol.strip()
        }
        return ",".join(symbol for symbol in larger_symbols if symbol not in smaller_keys)

    def _load_nifty500_symbols_from_csv(self) -> list[str]:
        csv_path = Path(self.nifty500_csv_path)
        if not csv_path.is_absolute():
            csv_path = ROOT_DIR / csv_path
        if not csv_path.exists():
            return []

        symbols: list[str] = []
        try:
            with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                from app.utils.symbol import canonical_symbol
                for row in reader:
                    symbol = (row.get("Symbol") or "").strip().upper()
                    series = (row.get("Series") or "").strip().upper()
                    if not symbol:
                        continue
                    combined = f"{symbol}-{series}" if series else symbol
                    symbols.append(canonical_symbol(combined))
        except Exception:
            # Degrade gracefully if file is malformed, empty, or unreadable
            return []
        return list(dict.fromkeys(symbols))

    def log_portfolio_config_snapshot(self) -> None:
        """Emit non-secret portfolio config for ops (Spec 1 NON-BINDING contract)."""
        _logger.info(
            "Portfolio config loaded (FEAT-024B Spec 1 NON-BINDING): "
            "simulation_enabled=%s max_concurrent_positions=%s max_position_pct=%s "
            "minimum_trade_value=%s allow_fractional_shares=%s reserve_cash_enabled=%s "
            "starting_capital=%s | dual-source: BacktestService still uses its own "
            "hardcoded equity and position_sizing_pct",
            self.portfolio_simulation_enabled,
            self.portfolio_max_concurrent_positions,
            self.portfolio_max_position_pct,
            self.portfolio_minimum_trade_value,
            self.portfolio_allow_fractional_shares,
            self.portfolio_reserve_cash_enabled,
            self.portfolio_starting_capital,
        )


settings = Settings()
settings.log_portfolio_config_snapshot()
