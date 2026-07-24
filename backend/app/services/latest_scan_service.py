"""Latest scan snapshot persistence.

Architecture
------------
``scan_execution_service`` may INSERT a ``ScanSnapshot`` row with status=RUNNING
at scan start (same ``scan_id``). When the scan finishes it calls
``persist_successful_scan(scan_id=...)`` which MUST **update** that row (and
replace child records), never INSERT a second parent with the same ``scan_id``.

One scan_id ⇒ exactly one ``scan_snapshots`` row.
"""
from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market_data import ScanSnapshot, ScanSnapshotRecord
from ..schemas import AnalysisMode, ScreenerResponse
from ..utils import get_logger
from ..observability.scan_diagnostics import get_current_scan, log_scan_persist

logger = get_logger("app.services.latest_scan_service")


def _swing_indicators(item) -> dict:
    """Extract indicator map from StockAnalysisResult.technical (swing preferred)."""
    technical = getattr(item, "technical", None) or []
    swing = None
    for t in technical:
        mode = getattr(t, "mode", None)
        if mode == AnalysisMode.swing or (isinstance(mode, str) and mode.lower() == "swing"):
            swing = t
            break
    chosen = swing or (technical[0] if technical else None)
    if chosen is None:
        return {}
    indicators = getattr(chosen, "indicators", None)
    return dict(indicators) if isinstance(indicators, dict) else {}


def _close_price(item) -> float:
    ohlcv = getattr(item, "ohlcv", None) or []
    if ohlcv:
        try:
            return float(ohlcv[-1].close)
        except Exception:
            return 0.0
    return 0.0


def _caller_summary(depth: int = 6) -> str:
    """Compact stack of external callers (skip this module frames)."""
    frames = traceback.extract_stack(limit=depth + 8)
    parts: list[str] = []
    for fr in frames[:-1]:
        if "latest_scan_service" in (fr.filename or ""):
            continue
        if fr.name in {"_caller_summary", "persist_successful_scan"}:
            continue
        parts.append(f"{fr.filename.split('/')[-1].split(chr(92))[-1]}:{fr.lineno}:{fr.name}")
    return " <- ".join(parts[-depth:]) if parts else "unknown"


class LatestScanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def persist_successful_scan(
        self,
        response: ScreenerResponse,
        duration_ms: int,
        scan_id: str | None = None,
    ):
        """Persist one completed scan snapshot.

        If ``scan_id`` already exists (e.g. RUNNING placeholder from
        ``scan_execution_service``), **update** that row and replace records.
        Never insert a second parent row for the same ``scan_id``.
        """
        scan_ctx = get_current_scan()
        if scan_ctx:
            log_scan_persist(scan_ctx, "SCAN_PERSIST_BEGIN")

        scan_id = scan_id or str(uuid.uuid4())
        scan_timestamp = datetime.now(timezone.utc)
        try:
            task = asyncio.current_task()
            task_id = id(task) if task else None
            task_name = task.get_name() if task else None
        except Exception:
            task_id = None
            task_name = None
        thread_id = threading.get_ident()
        request_id = getattr(scan_ctx, "scan_id", None) if scan_ctx else None
        caller = _caller_summary()

        logger.info(
            "PERSIST_CALL | scan_id=%s | task_id=%s | task_name=%s | thread_id=%s | "
            "request_id=%s | timestamp=%s | caller=%s",
            scan_id,
            task_id,
            task_name,
            thread_id,
            request_id,
            scan_timestamp.isoformat(),
            caller,
        )

        buy_candidates = list(response.buy_candidate_symbols or [])
        watch_candidates = list(response.watch_candidate_symbols or [])
        shortlisted = list(response.shortlisted_symbols or [])
        analysis_items = (
            list(response.analysis.items) if response.analysis and response.analysis.items else []
        )

        logger.info(
            "PERSIST_INPUT | scan_id=%s | shortlisted=%s | buy=%s | watch=%s | "
            "analysis_items=%s | matches=%s | all_analyzed=%s",
            scan_id,
            len(shortlisted),
            len(buy_candidates),
            len(watch_candidates),
            len(analysis_items),
            len(response.matches or []),
            len(response.all_analyzed_stocks or []),
        )

        # --- Upsert parent snapshot (one row per scan_id) ---
        existing = await self.db.scalar(
            select(ScanSnapshot).where(ScanSnapshot.scan_id == scan_id)
        )

        if existing is not None:
            logger.info(
                "PERSIST_UPSERT | mode=UPDATE | scan_id=%s | prior_status=%s",
                scan_id,
                existing.status,
            )
            snapshot = existing
            snapshot.scan_timestamp = scan_timestamp
            snapshot.scan_duration_ms = duration_ms
            snapshot.total_scanned = response.scanned_symbols
            snapshot.valid_symbols = len(response.data_valid_symbols or [])
            snapshot.buy_count = len(buy_candidates)
            snapshot.watch_count = len(watch_candidates)
            snapshot.rejected_count = 0
            snapshot.status = "COMPLETED"
            snapshot.error_type = None
            # Replace child rows so re-persist is idempotent
            await self.db.execute(
                delete(ScanSnapshotRecord).where(ScanSnapshotRecord.scan_id == scan_id)
            )
        else:
            logger.info("PERSIST_UPSERT | mode=INSERT | scan_id=%s", scan_id)
            snapshot = ScanSnapshot(
                scan_id=scan_id,
                scan_timestamp=scan_timestamp,
                scan_duration_ms=duration_ms,
                total_scanned=response.scanned_symbols,
                valid_symbols=len(response.data_valid_symbols or []),
                buy_count=len(buy_candidates),
                watch_count=len(watch_candidates),
                rejected_count=0,
                status="COMPLETED",
                error_type=None,
            )
            self.db.add(snapshot)

        processed_symbols: set[str] = set()
        buy_written = 0
        watch_written = 0
        rejected_written = 0

        # 1) Full analysis results (BUY / WATCH / REJECT for shortlisted set)
        for item in analysis_items:
            rec_action = (item.recommendation.action or "REJECT").upper()
            if rec_action == "BUY":
                db_action = "BUY"
                buy_written += 1
            elif rec_action == "WATCH":
                db_action = "WATCH"
                watch_written += 1
            else:
                db_action = "REJECTED"
                rejected_written += 1

            tech = _swing_indicators(item)
            self.db.add(
                ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=item.symbol,
                    recommendation=db_action,
                    score=float(item.recommendation.score or 0.0),
                    close_price=_close_price(item),
                    sma50=tech.get("sma_50") or tech.get("sma50"),
                    sma200=tech.get("sma_200") or tech.get("sma200"),
                    rsi=tech.get("rsi_14") or tech.get("rsi"),
                    macd=tech.get("macd"),
                    volume=None,
                    reason=item.recommendation.summary,
                )
            )
            processed_symbols.add(item.symbol)

        # 2) Ensure every BUY/WATCH symbol has a row even if analysis item was missing
        analysis_by_symbol = {item.symbol: item for item in analysis_items}
        for sym in buy_candidates:
            if sym in processed_symbols:
                continue
            item = analysis_by_symbol.get(sym)
            tech = _swing_indicators(item) if item else {}
            self.db.add(
                ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=sym,
                    recommendation="BUY",
                    score=float(item.recommendation.score) if item else 0.0,
                    close_price=_close_price(item) if item else 0.0,
                    sma50=tech.get("sma_50") or tech.get("sma50"),
                    sma200=tech.get("sma_200") or tech.get("sma200"),
                    rsi=tech.get("rsi_14") or tech.get("rsi"),
                    macd=tech.get("macd"),
                    volume=None,
                    reason=(item.recommendation.summary if item else "BUY candidate"),
                )
            )
            processed_symbols.add(sym)
            buy_written += 1

        for sym in watch_candidates:
            if sym in processed_symbols:
                continue
            item = analysis_by_symbol.get(sym)
            tech = _swing_indicators(item) if item else {}
            self.db.add(
                ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=sym,
                    recommendation="WATCH",
                    score=float(item.recommendation.score) if item else 0.0,
                    close_price=_close_price(item) if item else 0.0,
                    sma50=tech.get("sma_50") or tech.get("sma50"),
                    sma200=tech.get("sma_200") or tech.get("sma200"),
                    rsi=tech.get("rsi_14") or tech.get("rsi"),
                    macd=tech.get("macd"),
                    volume=None,
                    reason=(item.recommendation.summary if item else "WATCH candidate"),
                )
            )
            processed_symbols.add(sym)
            watch_written += 1

        # 3) Remaining matched (not shortlisted / not already written) → REJECTED
        for match in response.matches or []:
            if match.symbol in processed_symbols:
                continue
            self.db.add(
                ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=match.symbol,
                    recommendation="REJECTED",
                    score=float(match.screener_score or 0.0),
                    close_price=float(match.close or 0.0),
                    sma50=match.sma_50,
                    sma200=match.sma_200,
                    rsi=None,
                    macd=match.macd,
                    volume=match.volume,
                    reason="Not shortlisted by orchestrator",
                )
            )
            processed_symbols.add(match.symbol)
            rejected_written += 1

        snapshot.buy_count = len(buy_candidates)
        snapshot.watch_count = len(watch_candidates)
        snapshot.rejected_count = rejected_written

        try:
            await self.db.flush()
            logger.info(
                "PERSIST_OUTPUT | scan_id=%s | mode=%s | rows_written=%s | buy_rows=%s | "
                "watch_rows=%s | rejected_rows=%s | header_buy=%s | header_watch=%s | duration_ms=%s",
                scan_id,
                "UPDATE" if existing is not None else "INSERT",
                len(processed_symbols),
                buy_written,
                watch_written,
                rejected_written,
                snapshot.buy_count,
                snapshot.watch_count,
                duration_ms,
            )
            if scan_ctx:
                log_scan_persist(
                    scan_ctx,
                    "SCAN_PERSIST_SUCCESS",
                    buy_count=snapshot.buy_count,
                    watch_count=snapshot.watch_count,
                    reject_count=snapshot.rejected_count,
                    rows_written=len(processed_symbols),
                )
        except Exception as e:
            logger.error(
                "scan_persist_failed | scan_id=%s | error=%s | caller=%s",
                scan_id,
                str(e),
                caller,
                exc_info=True,
            )
            if scan_ctx:
                log_scan_persist(scan_ctx, "SCAN_PERSIST_FAILED")
            raise

    async def get_latest_completed_scan(self):
        logger.info("latest_scan_requested")
        stmt = (
            select(ScanSnapshot)
            .where(ScanSnapshot.status == "COMPLETED")
            .order_by(desc(ScanSnapshot.scan_timestamp))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        # Fallback: any latest row if no COMPLETED yet
        if not snapshot:
            result = await self.db.execute(
                select(ScanSnapshot).order_by(desc(ScanSnapshot.scan_timestamp)).limit(1)
            )
            snapshot = result.scalar_one_or_none()

        if not snapshot:
            logger.info("latest_scan_not_found")
            from ..observability.scan_diagnostics import log_dashboard_request

            log_dashboard_request(
                scan_id=None, endpoint="/scanner/latest", returned_records=0, query_duration_ms=0
            )
            return None

        stmt_records = select(ScanSnapshotRecord).where(
            ScanSnapshotRecord.scan_id == snapshot.scan_id
        )
        result_records = await self.db.execute(stmt_records)
        records = result_records.scalars().all()

        buy_candidates = []
        watch_candidates = []
        rejected_candidates = []

        for r in records:
            item = {
                "symbol": r.symbol,
                "recommendation": r.recommendation,
                "score": float(r.score) if r.score is not None else 0.0,
                "close_price": float(r.close_price) if r.close_price is not None else 0.0,
                "sma50": float(r.sma50) if r.sma50 is not None else None,
                "sma200": float(r.sma200) if r.sma200 is not None else None,
                "rsi": float(r.rsi) if r.rsi is not None else None,
                "macd": float(r.macd) if r.macd is not None else None,
                "volume": r.volume,
                "reason": r.reason,
            }
            rec = (r.recommendation or "").upper()
            if rec == "BUY":
                buy_candidates.append(item)
            elif rec == "WATCH":
                watch_candidates.append(item)
            else:
                rejected_candidates.append(item)

        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        watch_candidates.sort(key=lambda x: x["score"], reverse=True)
        rejected_candidates.sort(key=lambda x: x["score"], reverse=True)

        logger.info(
            "latest_scan_loaded | scan_id=%s | buy=%s | watch=%s | rejected=%s | "
            "header_buy=%s | header_watch=%s",
            snapshot.scan_id,
            len(buy_candidates),
            len(watch_candidates),
            len(rejected_candidates),
            snapshot.buy_count,
            snapshot.watch_count,
        )
        from ..observability.scan_diagnostics import log_dashboard_request

        total_records = len(buy_candidates) + len(watch_candidates) + len(rejected_candidates)
        log_dashboard_request(
            scan_id=snapshot.scan_id,
            endpoint="/scanner/latest",
            returned_records=total_records,
            query_duration_ms=0,
        )
        return {
            "scan_id": snapshot.scan_id,
            "scan_timestamp": snapshot.scan_timestamp.isoformat(),
            "last_scan_completed_at": snapshot.scan_timestamp.isoformat(),
            "total_scanned": snapshot.total_scanned,
            "valid_symbols": snapshot.valid_symbols,
            "buy_count": snapshot.buy_count,
            "watch_count": snapshot.watch_count,
            "rejected_count": snapshot.rejected_count,
            "buy_candidates": buy_candidates,
            "watch_candidates": watch_candidates,
            "rejected_candidates": rejected_candidates,
        }
