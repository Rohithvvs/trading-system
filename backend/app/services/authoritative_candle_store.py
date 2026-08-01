"""Authoritative Candle Store Service for Sprint 4.

Single Authoritative Owner for all OHLCV candle reads, writes, validations, and caching.
Provides multi-tier resolution (L1 RAM -> L2 PostgreSQL -> L3 FYERS Provider Fetch).
Guarded by settings.is_authoritative_candle_store_enabled() for zero-redeploy rollback.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config.settings import settings
from ..db.session import AsyncSessionLocal
from ..models.market_data import HistoricalCandle
from ..schemas.analysis import OHLCVPoint
from .candle_validation_engine import normalize_resolution, validate_candle_series
from .l1_candle_cache import l1_candle_cache, L1CandleCache

logger = logging.getLogger(__name__)

# Process-local counters (always available; Prometheus wired via observability.metrics).
CANDLE_STORE_METRICS: dict[str, int | float] = {
    "l1_hits": 0,
    "l2_hits": 0,
    "l3_fetches": 0,
    "legacy_fallbacks": 0,
    "writes_total": 0,
    "write_errors": 0,
    "consistency_audits_total": 0,
    "discrepancies_repaired": 0,
    "provider_retries": 0,
    "provider_failures": 0,
}

# FR-008: relative close discrepancy threshold (0.01%)
_CLOSE_REL_THRESHOLD = Decimal("0.0001")
_PROVIDER_MAX_RETRIES = 3
_PROVIDER_BACKOFF_BASE_S = 0.25
# Spec §11: provider timeout target ~3.5s including retries budget per attempt
_PROVIDER_ATTEMPT_TIMEOUT_S = 3.5
# Cap concurrent provider fetches to reduce 429 / stampede risk under scan load
_PROVIDER_CONCURRENCY = 5
# Cap supervised background tasks (ingest / dual-write) to bound memory
_MAX_BACKGROUND_TASKS = 64


class IngestionResult(BaseModel):
    symbol: str
    resolution: str
    inserted_count: int
    updated_count: int
    dual_write_status: str


class AuditReport(BaseModel):
    total_audited: int
    matched_count: int
    mismatched_count: int
    repaired_count: int
    discrepancies: list[dict[str, Any]]


def _inc_metric(name: str, amount: int = 1) -> None:
    CANDLE_STORE_METRICS[name] = int(CANDLE_STORE_METRICS.get(name, 0) or 0) + amount
    try:
        from ..observability import metrics as prom

        record = getattr(prom, "record_candle_store_metric", None)
        if callable(record):
            record(name, amount)
    except Exception:
        pass


def _observe_latency(source: str, seconds: float) -> None:
    try:
        from ..observability import metrics as prom

        observe = getattr(prom, "observe_candle_store_read_latency", None)
        if callable(observe):
            observe(source, seconds)
    except Exception:
        pass


def _resolution_timedelta(resolution: str) -> timedelta:
    """Canonical step size for interior-gap detection."""
    norm = normalize_resolution(resolution)
    mapping = {
        "1D": timedelta(days=1),
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "60m": timedelta(hours=1),
    }
    return mapping.get(norm, timedelta(days=1))


def _max_allowed_gap(resolution: str) -> timedelta:
    """Max allowed delta between consecutive bars before treating as interior gap.

    Daily series allow weekend/holiday gaps (up to 5 calendar days).
    Intraday series allow one skipped bar (2x step).
    """
    step = _resolution_timedelta(resolution)
    if normalize_resolution(resolution) == "1D":
        return timedelta(days=5)
    return step * 2


def _close_discrepancy(db_close: Decimal, prov_close: Decimal) -> bool:
    """Return True when relative close difference exceeds 0.01% (FR-008)."""
    db_c = Decimal(str(db_close))
    pr_c = Decimal(str(prov_close))
    if db_c == 0 and pr_c == 0:
        return False
    base = abs(db_c) if db_c != 0 else abs(pr_c)
    if base == 0:
        return abs(db_c - pr_c) > 0
    return abs(db_c - pr_c) / base > _CLOSE_REL_THRESHOLD


class AuthoritativeCandleStore:
    """Canonical owner and gateway for all market OHLCV candle data."""

    def __init__(
        self,
        cache: L1CandleCache | None = None,
        fyers_service: Any = None,
        market_data_service: Any = None,
    ) -> None:
        self.cache = cache or l1_candle_cache
        self._fyers_service = fyers_service
        self._market_data_service = market_data_service
        self._background_tasks: set[asyncio.Task] = set()
        self._symbol_locks: dict[str, asyncio.Lock] = {}
        self._provider_sem: asyncio.Semaphore | None = None

    @property
    def fyers_service(self) -> Any:
        if self._fyers_service is None:
            from .fyers_service import fyers_service
            self._fyers_service = fyers_service
        return self._fyers_service

    @property
    def market_data_service(self) -> Any:
        if self._market_data_service is None:
            from .market_data_service import market_data_service
            self._market_data_service = market_data_service
        return self._market_data_service

    def is_enabled(self) -> bool:
        """Check if Authoritative Candle Store is active via feature flag."""
        return settings.is_authoritative_candle_store_enabled()

    def _get_provider_sem(self) -> asyncio.Semaphore:
        if self._provider_sem is None:
            self._provider_sem = asyncio.Semaphore(_PROVIDER_CONCURRENCY)
        return self._provider_sem

    def _get_symbol_lock(self, symbol: str, resolution: str) -> asyncio.Lock:
        key = f"{symbol}:{resolution}"
        lock = self._symbol_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._symbol_locks[key] = lock
        return lock

    def _schedule_background(
        self, coro: Any, *, label: str, critical: bool = False
    ) -> None:
        """Schedule a supervised fire-and-forget task (H1 / FR-004).

        Non-critical work is dropped when the queue is saturated.
        Critical work (L3 persistence) waits for a free slot then runs — never dropped.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "candle_store_bg_skip | label=%s | reason=no_running_loop",
                label,
            )
            if asyncio.iscoroutine(coro):
                coro.close()
            return

        # Prune completed tasks and enforce bound
        done = {t for t in self._background_tasks if t.done()}
        self._background_tasks -= done
        if len(self._background_tasks) >= _MAX_BACKGROUND_TASKS:
            if not critical:
                _inc_metric("write_errors")
                logger.warning(
                    "candle_store_bg_saturated | label=%s | pending=%s | action=drop",
                    label,
                    len(self._background_tasks),
                )
                if asyncio.iscoroutine(coro):
                    coro.close()
                return
            # Critical ingest: serialize behind an in-flight task (never drop).
            logger.warning(
                "candle_store_bg_saturated | label=%s | pending=%s | action=serialize",
                label,
                len(self._background_tasks),
            )
            original = coro
            pending_snapshot = [t for t in self._background_tasks if not t.done()]

            async def _serialized() -> None:
                if pending_snapshot:
                    await asyncio.wait(
                        pending_snapshot, return_when=asyncio.FIRST_COMPLETED
                    )
                await original

            coro = _serialized()

        task = loop.create_task(coro, name=f"candle_store:{label}")
        self._background_tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            except Exception as e:  # pragma: no cover
                logger.warning(
                    "candle_store_bg_inspect_failed | label=%s | error=%s", label, e
                )
                return
            if exc is not None:
                _inc_metric("write_errors")
                logger.warning(
                    "candle_store_bg_failed | label=%s | error=%s",
                    label,
                    exc,
                )

        task.add_done_callback(_done)

    async def get_candles(
        self,
        symbol: str,
        resolution: str,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        force_provider_fetch: bool = False,
    ) -> list[OHLCVPoint]:
        """Retrieve continuous OHLCV candle series using multi-tier resolution."""
        t0 = time.perf_counter()
        norm_sym = symbol.strip().upper()
        norm_res = normalize_resolution(resolution)

        start_dt = self._parse_datetime(start_date)
        end_dt = self._parse_datetime(end_date)

        if not self.is_enabled():
            _inc_metric("legacy_fallbacks")
            out = await self._legacy_get_candles(norm_sym, norm_res, start_dt, end_dt)
            _observe_latency("legacy", time.perf_counter() - t0)
            logger.info(
                "candle_store_read | symbol=%s | resolution=%s | source=legacy | candles=%s | latency_ms=%.1f",
                norm_sym,
                norm_res,
                len(out),
                (time.perf_counter() - t0) * 1000,
            )
            return out

        # 1. Tier 1: L1 RAM Cache
        if not force_provider_fetch:
            cached_candles = self.cache.get(norm_sym, norm_res, start_dt, end_dt)
            if cached_candles is not None and not self._has_data_gap(
                cached_candles, start_dt, end_dt, norm_res
            ):
                _inc_metric("l1_hits")
                _observe_latency("l1", time.perf_counter() - t0)
                logger.debug(
                    "candle_store_read | symbol=%s | resolution=%s | source=l1 | cache_hit=true | candles=%s",
                    norm_sym,
                    norm_res,
                    len(cached_candles),
                )
                return cached_candles

        # 2. Tier 2: L2 PostgreSQL
        db_candles = await self._query_db_candles(norm_sym, norm_res, start_dt, end_dt)
        needs_provider_fetch = force_provider_fetch or self._has_data_gap(
            db_candles, start_dt, end_dt, norm_res
        )

        if not needs_provider_fetch and db_candles:
            validated = validate_candle_series(db_candles)
            self.cache.set(norm_sym, norm_res, validated)
            _inc_metric("l2_hits")
            _observe_latency("l2", time.perf_counter() - t0)
            logger.info(
                "candle_store_read | symbol=%s | resolution=%s | source=l2 | cache_hit=false | candles=%s | latency_ms=%.1f",
                norm_sym,
                norm_res,
                len(validated),
                (time.perf_counter() - t0) * 1000,
            )
            return validated

        # 3. Tier 3: Provider backfill — single-flight per symbol/resolution
        async with self._get_symbol_lock(norm_sym, norm_res):
            # Re-check L1 after waiting (another coroutine may have filled it)
            if not force_provider_fetch:
                cached_candles = self.cache.get(norm_sym, norm_res, start_dt, end_dt)
                if cached_candles is not None and not self._has_data_gap(
                    cached_candles, start_dt, end_dt, norm_res
                ):
                    _inc_metric("l1_hits")
                    _observe_latency("l1", time.perf_counter() - t0)
                    return cached_candles

            db_candles = await self._query_db_candles(
                norm_sym, norm_res, start_dt, end_dt
            )
            needs_provider_fetch = force_provider_fetch or self._has_data_gap(
                db_candles, start_dt, end_dt, norm_res
            )
            if not needs_provider_fetch and db_candles:
                validated = validate_candle_series(db_candles)
                self.cache.set(norm_sym, norm_res, validated)
                _inc_metric("l2_hits")
                _observe_latency("l2", time.perf_counter() - t0)
                return validated

            missing = self._missing_windows(
                db_candles or [], start_dt, end_dt, norm_res
            )
            provider_candles: list[OHLCVPoint] = []
            if force_provider_fetch or not missing:
                provider_candles = await self._fetch_provider_candles(
                    norm_sym, norm_res, start_dt, end_dt
                )
            else:
                for win_start, win_end in missing:
                    chunk = await self._fetch_provider_candles(
                        norm_sym, norm_res, win_start, win_end
                    )
                    provider_candles.extend(chunk)

            _inc_metric("l3_fetches")
            merged = validate_candle_series((db_candles or []) + provider_candles)
            if start_dt or end_dt:
                merged = [
                    c
                    for c in merged
                    if (start_dt is None or c.timestamp >= start_dt)
                    and (end_dt is None or c.timestamp <= end_dt)
                ]

            if merged:
                self._schedule_background(
                    self.ingest_candles(norm_sym, norm_res, merged, source="FYERS"),
                    label=f"ingest:{norm_sym}:{norm_res}",
                    critical=True,
                )
                self.cache.set(norm_sym, norm_res, merged)
            elif db_candles and settings.is_candle_store_allow_fallback():
                merged = validate_candle_series(db_candles)
                logger.warning(
                    "candle_store_partial | symbol=%s | resolution=%s | partial_data=true | candles=%s",
                    norm_sym,
                    norm_res,
                    len(merged),
                )

            _observe_latency("l3", time.perf_counter() - t0)
            logger.info(
                "candle_store_read | symbol=%s | resolution=%s | source=l3 | candles=%s | missing_windows=%s | latency_ms=%.1f",
                norm_sym,
                norm_res,
                len(merged),
                len(missing),
                (time.perf_counter() - t0) * 1000,
            )
            return merged

    async def ingest_candles(
        self,
        symbol: str,
        resolution: str,
        candles: list[OHLCVPoint | dict[str, Any]],
        source: str = "FYERS",
    ) -> IngestionResult:
        """Idempotently persist candle arrays into storage (ON CONFLICT DO UPDATE)."""
        norm_sym = symbol.strip().upper()
        norm_res = normalize_resolution(resolution)

        validated_candles = validate_candle_series(candles)
        if not validated_candles:
            return IngestionResult(
                symbol=norm_sym,
                resolution=norm_res,
                inserted_count=0,
                updated_count=0,
                dual_write_status="SKIPPED",
            )

        inserted, updated = await self._upsert_db_candles(
            norm_sym, norm_res, validated_candles, source
        )
        _inc_metric("writes_total")

        self.cache.set(norm_sym, norm_res, validated_candles)

        dual_write_status = "SKIPPED"
        if settings.candle_store_dual_write:
            # FR-004: secondary dual-write is non-blocking background work.
            dual_write_status = "SUCCESS"

            async def _dual() -> None:
                try:
                    await self._sync_legacy_dual_write(norm_sym, norm_res, validated_candles)
                except Exception as exc:
                    logger.warning(
                        "candle_store_dual_write_failed | symbol=%s | resolution=%s | error=%s",
                        norm_sym,
                        norm_res,
                        exc,
                    )
                    raise

            self._schedule_background(_dual(), label=f"dual_write:{norm_sym}:{norm_res}")

        logger.info(
            "candle_store_write | symbol=%s | resolution=%s | inserted=%s | updated=%s | dual_write=%s | source=%s",
            norm_sym,
            norm_res,
            inserted,
            updated,
            dual_write_status,
            source,
        )
        return IngestionResult(
            symbol=norm_sym,
            resolution=norm_res,
            inserted_count=inserted,
            updated_count=updated,
            dual_write_status=dual_write_status,
        )

    async def validate_consistency(
        self,
        symbols: list[str],
        resolution: str,
        sample_ratio: float = 0.01,
    ) -> AuditReport:
        """Audit a sample of stored series against provider (FR-008)."""
        norm_res = normalize_resolution(resolution)
        _inc_metric("consistency_audits_total")

        if not symbols:
            return AuditReport(
                total_audited=0,
                matched_count=0,
                mismatched_count=0,
                repaired_count=0,
                discrepancies=[],
            )

        ratio = max(0.0, min(1.0, float(sample_ratio)))
        sample_size = max(1, int(math.ceil(len(symbols) * ratio))) if ratio > 0 else 0
        sample_size = min(sample_size, len(symbols))
        sampled = random.sample(list(symbols), sample_size) if sample_size else []

        matched = 0
        mismatched = 0
        repaired = 0
        discrepancies: list[dict[str, Any]] = []

        for sym in sampled:
            norm_sym = sym.strip().upper()
            db_candles = await self._query_db_candles(norm_sym, norm_res)
            if not db_candles:
                continue
            prov_candles = await self._fetch_provider_candles(norm_sym, norm_res)
            if not prov_candles:
                continue

            db_map = {c.timestamp: c for c in db_candles}
            prov_map = {c.timestamp: c for c in prov_candles}

            diff_count = 0
            for ts, p_candle in prov_map.items():
                if ts not in db_map:
                    continue
                d_candle = db_map[ts]
                if _close_discrepancy(d_candle.close, p_candle.close):
                    diff_count += 1
                    discrepancies.append(
                        {
                            "symbol": norm_sym,
                            "timestamp": ts.isoformat(),
                            "db_close": float(d_candle.close),
                            "provider_close": float(p_candle.close),
                        }
                    )

            if diff_count == 0:
                matched += 1
            else:
                mismatched += 1
                await self.ingest_candles(
                    norm_sym, norm_res, prov_candles, source="REPAIR_AUDIT"
                )
                repaired += 1
                _inc_metric("discrepancies_repaired")

        return AuditReport(
            total_audited=len(sampled),
            matched_count=matched,
            mismatched_count=mismatched,
            repaired_count=repaired,
            discrepancies=discrepancies,
        )

    async def _query_db_candles(
        self,
        symbol: str,
        resolution: str,
        start_dt: datetime | None = None,
        end_dt: datetime | None = None,
    ) -> list[OHLCVPoint]:
        """Query PostgreSQL historical_candles table directly."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(HistoricalCandle)
                    .where(
                        HistoricalCandle.symbol == symbol,
                        HistoricalCandle.resolution == resolution,
                    )
                    .order_by(HistoricalCandle.timestamp.asc())
                )
                if start_dt:
                    stmt = stmt.where(HistoricalCandle.timestamp >= start_dt)
                if end_dt:
                    stmt = stmt.where(HistoricalCandle.timestamp <= end_dt)

                res = await session.execute(stmt)
                rows = res.scalars().all()

                return [
                    OHLCVPoint(
                        timestamp=self._ensure_utc(r.timestamp),
                        open=r.open,
                        high=r.high,
                        low=r.low,
                        close=r.close,
                        volume=r.volume,
                    )
                    for r in rows
                ]
        except Exception as exc:
            logger.error(
                "candle_store_db_query_error | symbol=%s | resolution=%s | error=%s",
                symbol,
                resolution,
                exc,
            )
            return []

    async def _upsert_db_candles(
        self,
        symbol: str,
        resolution: str,
        candles: list[OHLCVPoint],
        source: str,
    ) -> tuple[int, int]:
        """Execute PostgreSQL ON CONFLICT DO UPDATE batch upsert."""
        if not candles:
            return 0, 0

        chunk_size = 500
        inserted_count = 0
        updated_count = 0

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for i in range(0, len(candles), chunk_size):
                        chunk = candles[i : i + chunk_size]
                        # Pre-count existing keys so we can split insert vs update.
                        timestamps = [c.timestamp for c in chunk]
                        existing_stmt = select(HistoricalCandle.timestamp).where(
                            HistoricalCandle.symbol == symbol,
                            HistoricalCandle.resolution == resolution,
                            HistoricalCandle.timestamp.in_(timestamps),
                        )
                        existing_res = await session.execute(existing_stmt)
                        existing_ts = {
                            self._ensure_utc(ts) for ts in existing_res.scalars().all()
                        }
                        chunk_updated = sum(
                            1 for c in chunk if self._ensure_utc(c.timestamp) in existing_ts
                        )
                        chunk_inserted = len(chunk) - chunk_updated

                        records = [
                            {
                                "symbol": symbol,
                                "resolution": resolution,
                                "timestamp": c.timestamp,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                                "source": source,
                                "created_at": datetime.now(timezone.utc),
                                "updated_at": datetime.now(timezone.utc),
                            }
                            for c in chunk
                        ]

                        stmt = pg_insert(HistoricalCandle).values(records)
                        update_dict = {
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "source": stmt.excluded.source,
                            "updated_at": datetime.now(timezone.utc),
                        }

                        upsert_stmt = stmt.on_conflict_do_update(
                            constraint="uq_historical_candle", set_=update_dict
                        )
                        await session.execute(upsert_stmt)
                        inserted_count += chunk_inserted
                        updated_count += chunk_updated

                return inserted_count, updated_count
        except Exception as exc:
            _inc_metric("write_errors")
            logger.error(
                "candle_store_db_upsert_error | symbol=%s | resolution=%s | error=%s",
                symbol,
                resolution,
                exc,
            )
            return 0, 0

    async def _fetch_provider_candles(
        self,
        symbol: str,
        resolution: str,
        start_dt: datetime | None = None,
        end_dt: datetime | None = None,
    ) -> list[OHLCVPoint]:
        """Fetch candles from FYERS with timeout, concurrency limit, and retries."""
        lookback = self._lookback_for_range(start_dt, end_dt, resolution)
        last_exc: Exception | None = None

        for attempt in range(_PROVIDER_MAX_RETRIES):
            try:
                from ..schemas.analysis import AnalysisMode

                async with self._get_provider_sem():
                    raw_candles = await asyncio.wait_for(
                        self.fyers_service.fetch_ohlcv(
                            symbol=symbol,
                            mode=AnalysisMode.swing,
                            resolution=resolution,
                            lookback_window=lookback,
                            bypass_authoritative_store=True,
                        ),
                        timeout=_PROVIDER_ATTEMPT_TIMEOUT_S,
                    )
                series = validate_candle_series(raw_candles or [])
                if start_dt or end_dt:
                    series = [
                        c
                        for c in series
                        if (start_dt is None or c.timestamp >= start_dt)
                        and (end_dt is None or c.timestamp <= end_dt)
                    ]
                return series
            except Exception as exc:
                last_exc = exc
                _inc_metric("provider_retries")
                if attempt + 1 >= _PROVIDER_MAX_RETRIES:
                    break
                delay = _PROVIDER_BACKOFF_BASE_S * (2**attempt)
                logger.warning(
                    "candle_store_provider_retry | symbol=%s | resolution=%s | attempt=%s | sleep_s=%.2f | error=%s",
                    symbol,
                    resolution,
                    attempt + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        _inc_metric("provider_failures")
        logger.warning(
            "candle_store_provider_failed | symbol=%s | resolution=%s | error=%s",
            symbol,
            resolution,
            last_exc,
        )
        return []

    async def _legacy_get_candles(
        self,
        symbol: str,
        resolution: str,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ) -> list[OHLCVPoint]:
        """Legacy retrieval path when AUTHORITATIVE_CANDLE_STORE_ENABLED=False."""
        try:
            return await self.market_data_service.get_candles(
                symbol=symbol, timeframe=resolution
            )
        except Exception:
            if settings.is_candle_store_allow_fallback():
                return await self._fetch_provider_candles(
                    symbol, resolution, start_dt, end_dt
                )
            return []

    async def _sync_legacy_dual_write(
        self, symbol: str, resolution: str, candles: list[OHLCVPoint]
    ) -> None:
        """Dual-write secondary sync to legacy Fyers memory cache (Phase 1/2)."""
        from ..schemas.analysis import AnalysisMode

        cache_key = (
            self.fyers_service._cache_symbol(symbol),
            AnalysisMode.swing.value,
            resolution.lower(),
        )
        self.fyers_service._store_ohlcv_cache(
            cache_key, max(len(candles), 260), candles, "DUAL_WRITE_SYNC"
        )

    def _has_data_gap(
        self,
        candles: list[OHLCVPoint],
        start_dt: datetime | None,
        end_dt: datetime | None,
        resolution: str = "1D",
    ) -> bool:
        """True when series has head/tail/interior gaps relative to requested bounds."""
        return bool(self._missing_windows(candles, start_dt, end_dt, resolution))

    def _missing_windows(
        self,
        candles: list[OHLCVPoint],
        start_dt: datetime | None,
        end_dt: datetime | None,
        resolution: str = "1D",
    ) -> list[tuple[datetime | None, datetime | None]]:
        """Identify missing head/tail/interior windows for provider backfill (C1/C2)."""
        if not candles:
            return [(start_dt, end_dt)]

        windows: list[tuple[datetime | None, datetime | None]] = []
        first_ts = self._ensure_utc(candles[0].timestamp)
        last_ts = self._ensure_utc(candles[-1].timestamp)

        if start_dt and first_ts > start_dt:
            windows.append((start_dt, first_ts))
        if end_dt and last_ts < end_dt:
            windows.append((last_ts, end_dt))

        max_gap = _max_allowed_gap(resolution)
        for prev, cur in zip(candles, candles[1:]):
            prev_ts = self._ensure_utc(prev.timestamp)
            cur_ts = self._ensure_utc(cur.timestamp)
            if cur_ts - prev_ts > max_gap:
                windows.append((prev_ts, cur_ts))

        return windows

    def _lookback_for_range(
        self,
        start_dt: datetime | None,
        end_dt: datetime | None,
        resolution: str,
    ) -> int:
        """Compute provider lookback bars covering [start, end] with margin."""
        if start_dt is None:
            return 500
        end = end_dt or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=timezone.utc)
        if end < start:
            end = start
        delta = end - start
        step = _resolution_timedelta(resolution)
        if step.total_seconds() <= 0:
            return 500
        bars = int(delta.total_seconds() / step.total_seconds()) + 1
        # Margin for holidays / partial sessions
        return max(bars + 30, 50)

    @staticmethod
    def _ensure_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    def _parse_datetime(self, val: datetime | str | None) -> datetime | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if isinstance(val, str):
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return None


# Global singleton instance
authoritative_candle_store = AuthoritativeCandleStore()
