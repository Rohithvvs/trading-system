from __future__ import annotations

import csv
import logging
from pathlib import Path
from functools import cached_property
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator

_logger = logging.getLogger("app.config")

ROOT_DIR = Path(__file__).resolve().parents[3]
# Prefer repo-root .env; also accept backend/.env for local overrides.
_ENV_FILES = (
    str(ROOT_DIR / ".env"),
    str(ROOT_DIR / "backend" / ".env"),
)


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
    app_env: str = Field(default="development", alias="APP_ENV")
    # Must match the frontend VITE_GOOGLE_CLIENT_ID (GIS Web client).
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    quarantine_mode: bool = False
    app_host: str = Field(default="0.0.0.0", alias="HOST")   # ← critical change
    app_port: int = Field(default=8000, alias="PORT")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
    redis_url: str = "redis://localhost:6379/0"
    # Evaluated live via is_scanner_latest_cache_enabled() — mutating this attribute
    # takes effect on the next request without code redeploy (audit H5).
    scanner_latest_cache_enabled: bool = Field(default=False, alias="SCANNER_LATEST_CACHE_ENABLED")
    scanner_latest_cache_ttl_seconds: int = Field(
        default=300, ge=10, alias="SCANNER_LATEST_CACHE_TTL_SECONDS"
    )
    redis_cache_read_timeout_ms: int = Field(
        default=50, ge=5, alias="REDIS_CACHE_READ_TIMEOUT_MS"
    )
    redis_cache_write_timeout_ms: int = Field(
        default=100, ge=10, alias="REDIS_CACHE_WRITE_TIMEOUT_MS"
    )

    def is_scanner_latest_cache_enabled(self) -> bool:
        """Live feature-flag read for scanner latest-cache (zero-redeploy rollback).

        Priority on every call:
        1. ``os.environ["SCANNER_LATEST_CACHE_ENABLED"]`` when set (non-empty) — allows
           ops to flip the process environment without a code redeploy/restart when
           their runtime can inject env (and keeps attribute in sync).
        2. ``settings.scanner_latest_cache_enabled`` attribute — mutable in-process
           for tests and admin toggles when env is unset.
        """
        raw = os.environ.get("SCANNER_LATEST_CACHE_ENABLED")
        if raw is not None and str(raw).strip() != "":
            enabled = str(raw).strip().lower() in {"1", "true", "yes", "on"}
            # Keep attribute aligned so logs/diagnostics match live behavior.
            object.__setattr__(self, "scanner_latest_cache_enabled", enabled)
            return enabled
        return bool(self.scanner_latest_cache_enabled)

    scanner_unified_latest_enabled: bool = Field(default=False, alias="SCANNER_UNIFIED_LATEST_ENABLED")

    def is_scanner_unified_latest_enabled(self) -> bool:
        """Live feature-flag read for unified latest-scan endpoints (zero-redeploy rollback)."""
        raw = os.environ.get("SCANNER_UNIFIED_LATEST_ENABLED")
        if raw is not None and str(raw).strip() != "":
            enabled = str(raw).strip().lower() in {"1", "true", "yes", "on"}
            object.__setattr__(self, "scanner_unified_latest_enabled", enabled)
            return enabled
        return bool(self.scanner_unified_latest_enabled)
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
    # Canonical names: SMTP_*. Common MAIL_* aliases are accepted via model_validator
    # (empty SMTP_* must not block MAIL_SERVER / MAIL_USERNAME / etc.).
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_from_name: str = Field(default="TradeX", alias="SMTP_FROM_NAME")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
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

    # FEAT-011 Spec 1 (Shadow Infrastructure Foundation): configuration contract
    shadow_mode_enabled: bool = Field(default=False, alias="SHADOW_MODE_ENABLED")
    shadow_mode_stage: str = Field(default="SHADOW", alias="SHADOW_MODE_STAGE")
    shadow_mode_ruleset: str = Field(default="experimental_v1", alias="SHADOW_MODE_RULESET")
    shadow_mode_persistence_enabled: bool = Field(default=False, alias="SHADOW_MODE_PERSISTENCE_ENABLED")

    # RE-001 Trend Continuation lab engine (default OFF — production shortlist authority unchanged)
    re001_enabled: bool = Field(default=False, alias="RE001_ENABLED")
    re001_stage: str = Field(default="OFF", alias="RE001_STAGE")  # OFF | LAB_SHADOW | PAPER_LINKED
    re001_version: str = Field(default="1.0", alias="RE001_VERSION")
    re001_persist_decisions: bool = Field(default=True, alias="RE001_PERSIST_DECISIONS")
    re001_compare_with_production: bool = Field(default=True, alias="RE001_COMPARE_WITH_PRODUCTION")
    re001_timeout_ms: float = Field(default=3000.0, ge=200.0, le=60000.0, alias="RE001_TIMEOUT_MS")
    # UI kill-switch (default True so feature permission remains primary gate; set false to hide lab APIs)
    re001_ui_enabled: bool = Field(default=True, alias="RE001_UI_ENABLED")

    # Sprint 3: Reduce Scan-Result Fan-out feature flag
    scan_result_minimal_writes: bool = Field(default=False, alias="SCAN_RESULT_MINIMAL_WRITES")

    def is_scan_result_minimal_writes(self) -> bool:
        try:
            raw = os.environ.get("SCAN_RESULT_MINIMAL_WRITES")
            if raw is not None and str(raw).strip() != "":
                enabled = str(raw).strip().lower() in {"1", "true", "yes", "on"}
                object.__setattr__(self, "scan_result_minimal_writes", enabled)
                return enabled
            return bool(self.scan_result_minimal_writes)
        except Exception:
            return False

    # Sprint 5: Scanner Single Final Write feature flag
    scanner_single_final_write_enabled: bool = Field(default=False, alias="SCANNER_SINGLE_FINAL_WRITE_ENABLED")
    # Full broker-backed scan wall-clock budget (data fetch + analysis + rate limits).
    # FR-012's 30s target applies to pure in-memory aggregation; production Fyers
    # universe scans need a much larger budget. Override via env.
    scan_execution_timeout_seconds: float = Field(
        default=600.0, ge=30.0, le=3600.0, alias="SCAN_EXECUTION_TIMEOUT_SECONDS"
    )

    def is_scanner_single_final_write_enabled(self) -> bool:
        try:
            raw = os.environ.get("SCANNER_SINGLE_FINAL_WRITE_ENABLED")
            if raw is not None and str(raw).strip() != "":
                enabled = str(raw).strip().lower() in {"1", "true", "yes", "on"}
                object.__setattr__(self, "scanner_single_final_write_enabled", enabled)
                return enabled
            return bool(self.scanner_single_final_write_enabled)
        except Exception:
            return False

    # Sprint 4: Authoritative Candle Store feature flags
    authoritative_candle_store_enabled: bool = Field(default=False, alias="AUTHORITATIVE_CANDLE_STORE_ENABLED")
    candle_store_dual_write: bool = Field(default=True, alias="CANDLE_STORE_DUAL_WRITE")
    candle_store_allow_fallback: bool = Field(default=True, alias="CANDLE_STORE_ALLOW_FALLBACK")

    def is_authoritative_candle_store_enabled(self) -> bool:
        """Live feature-flag read for Authoritative Candle Store (zero-redeploy rollback).

        Priority on every call (pure read — does not mutate settings attributes):
        1. ``os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"]`` when set (non-empty).
        2. ``settings.authoritative_candle_store_enabled`` attribute (tests / in-process toggles).

        On any evaluation error, defaults to False (legacy fallback fail-safe).
        """
        try:
            raw = os.environ.get("AUTHORITATIVE_CANDLE_STORE_ENABLED")
            if raw is not None and str(raw).strip() != "":
                return str(raw).strip().lower() in {"1", "true", "yes", "on"}
            return bool(self.authoritative_candle_store_enabled)
        except Exception:
            return False

    def is_candle_store_allow_fallback(self) -> bool:
        """Whether ACS may return best-available data / provider fallback on errors."""
        try:
            raw = os.environ.get("CANDLE_STORE_ALLOW_FALLBACK")
            if raw is not None and str(raw).strip() != "":
                return str(raw).strip().lower() in {"1", "true", "yes", "on"}
            return bool(self.candle_store_allow_fallback)
        except Exception:
            return True



    # FEAT-012/FEAT-013: Governance states and validation reporting
    governance_reports_dir: str = Field(default="governance/reports", alias="GOVERNANCE_REPORTS_DIR")
    rule_states_file: str = Field(default="backend/app/config/rule_states.json", alias="RULE_STATES_FILE")

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _resolve_smtp_mail_aliases(self):
        """
        Accept both SMTP_* (canonical) and MAIL_* (common Flask/Django-style) names.

        Root cause of missed password-reset emails: .env had MAIL_SERVER / MAIL_USERNAME
        filled while SMTP_HOST / SMTP_USER were empty. pydantic only binds SMTP_* aliases.
        Empty SMTP_* must fall back to MAIL_*.
        """
        try:
            from dotenv import dotenv_values
        except ImportError:  # pragma: no cover
            dotenv_values = None  # type: ignore[assignment]

        merged: dict[str, str] = {}
        if dotenv_values is not None:
            for path in _ENV_FILES:
                if Path(path).is_file():
                    for key, val in dotenv_values(path).items():
                        if key and val is not None and str(val).strip():
                            merged[key] = str(val).strip()
        for key, val in os.environ.items():
            if val is not None and str(val).strip():
                merged[key] = str(val).strip()

        def pick(*names: str) -> str:
            for name in names:
                val = merged.get(name)
                if val is not None and str(val).strip():
                    return str(val).strip()
            return ""

        if not (self.smtp_host or "").strip():
            self.smtp_host = pick("SMTP_HOST", "MAIL_SERVER")
        if not (self.smtp_user or "").strip():
            self.smtp_user = pick("SMTP_USER", "MAIL_USERNAME")
        if not (self.smtp_password or "").strip():
            self.smtp_password = pick("SMTP_PASSWORD", "MAIL_PASSWORD")
        if not (self.smtp_from or "").strip():
            self.smtp_from = pick("SMTP_FROM", "MAIL_FROM", "SMTP_USER", "MAIL_USERNAME")
        if not (self.smtp_from_name or "").strip():
            self.smtp_from_name = pick("SMTP_FROM_NAME", "MAIL_FROM_NAME") or "TradeX"

        # Port: only override default when MAIL_PORT / SMTP_PORT provides a value
        port_raw = pick("SMTP_PORT", "MAIL_PORT")
        if port_raw:
            try:
                self.smtp_port = int(port_raw)
            except ValueError:
                _logger.warning("Invalid SMTP/MAIL port %r; keeping %s", port_raw, self.smtp_port)

        tls_raw = pick("SMTP_USE_TLS", "MAIL_USE_TLS")
        if tls_raw:
            self.smtp_use_tls = tls_raw.lower() in {"1", "true", "yes", "on"}

        # Note: this may run before setup_logging() attaches handlers (import order
        # in main.py). Call log_smtp_config_snapshot() again after logging is ready.
        self._log_smtp_config_snapshot(prefix="SMTP load-time")
        return self

    def log_smtp_config_snapshot(self) -> None:
        """Emit non-secret SMTP config for ops (safe after setup_logging)."""
        self._log_smtp_config_snapshot(prefix="SMTP startup")

    def _log_smtp_config_snapshot(self, prefix: str = "SMTP") -> None:
        password_set = bool((self.smtp_password or "").strip())
        if (self.smtp_host or "").strip() and (self.smtp_user or "").strip() and password_set:
            _logger.info(
                "%s | configured=True | host=%s port=%s user=%s from=%s from_name=%s "
                "tls=%s password_set=%s",
                prefix,
                self.smtp_host,
                self.smtp_port,
                self.smtp_user or "(none)",
                self.smtp_from or self.smtp_user or "(none)",
                self.smtp_from_name or "(none)",
                self.smtp_use_tls,
                password_set,
            )
        else:
            _logger.warning(
                "%s | configured=False | host=%r user=%r password_set=%s from=%r | "
                "set SMTP_HOST/SMTP_USER/SMTP_PASSWORD "
                "(or MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD) for password-reset emails",
                prefix,
                self.smtp_host,
                self.smtp_user,
                password_set,
                self.smtp_from,
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

    @field_validator("shadow_mode_stage", mode="before")
    @classmethod
    def _validate_shadow_mode_stage(cls, v: str | None) -> str:
        if v is None or not str(v).strip():
            return "SHADOW"
        cleaned = str(v).strip().upper()
        if cleaned in {"OFF", "SHADOW", "ACTIVE"}:
            return cleaned
        raise ValueError(f"Invalid shadow_mode_stage: {v}. Valid options: OFF, SHADOW, ACTIVE")

    @field_validator("shadow_mode_persistence_enabled")
    @classmethod
    def _warn_shadow_persistence_non_binding(cls, v: bool) -> bool:
        # Audit M3: flag is loadable but IShadowStore writes are not wired in Spec 1.
        if v is True:
            _logger.warning(
                "shadow_mode_persistence_enabled=True is NON-BINDING in FEAT-011 Spec 1 "
                "(006-shadow-infra-foundation): shadow comparison DB writes are not wired yet. "
                "IShadowStore persistence lands in a later specification."
            )
        return v

    def is_shadow_hook_enabled(self) -> bool:
        """Return True when the orchestrator shadow hook should run.

        Requires the master toggle and a non-OFF stage. Stage ACTIVE is accepted
        for forward-compat but Spec 1 still only constructs context / invokes a
        registered executor without affecting production recommendations.
        """
        return bool(self.shadow_mode_enabled) and self.shadow_mode_stage != "OFF"

    def is_re001_active(self) -> bool:
        """True when RE-001 lab evaluation should run (enabled + LAB_SHADOW|PAPER_LINKED)."""
        if not bool(self.re001_enabled):
            return False
        stage = str(self.re001_stage or "OFF").strip().upper()
        return stage in {"LAB_SHADOW", "PAPER_LINKED"}

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

    def log_shadow_config_snapshot(self) -> None:
        """Emit non-secret shadow config for ops (Spec 1)."""
        _logger.info(
            "Shadow config loaded: "
            "enabled=%s stage=%s ruleset=%s persistence_enabled=%s hook_active=%s",
            self.shadow_mode_enabled,
            self.shadow_mode_stage,
            self.shadow_mode_ruleset,
            self.shadow_mode_persistence_enabled,
            self.is_shadow_hook_enabled(),
        )
        if self.shadow_mode_stage == "ACTIVE":
            _logger.warning(
                "shadow_mode_stage=ACTIVE is reserved for future execution activation; "
                "Spec 1 still isolates shadow work from production scoring and API responses."
            )
        if self.shadow_mode_persistence_enabled:
            _logger.warning(
                "shadow_mode_persistence_enabled=True is NON-BINDING in Spec 1 "
                "(no shadow DB writes yet)."
            )


settings = Settings()
settings.log_portfolio_config_snapshot()
settings.log_shadow_config_snapshot()
