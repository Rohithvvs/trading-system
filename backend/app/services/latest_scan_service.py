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

from ..models.market_data import LatestScanResult, ScanSnapshot, ScanSnapshotRecord
from ..schemas import AnalysisMode, ScreenerResponse
from ..utils import get_logger
from ..observability.scan_diagnostics import get_current_scan, log_scan_persist
from ..config.settings import settings
from .persistence_service import PersistenceService

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
        *,
        minimal_writes: bool | None = None,
    ):
        """Persist one completed scan snapshot.

        If ``scan_id`` already exists (e.g. RUNNING placeholder from
        ``scan_execution_service``), **update** that row and replace records.
        Never insert a second parent row for the same ``scan_id``.

        ``minimal_writes`` freezes the feature-flag decision for this unit of work
        (avoids mid-scan flag drift). When None, the live flag is evaluated once here.
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

        # --- Canonical latest scan results write (always written) ---
        latest_records = []
        processed_latest: set[str] = set()

        for item in analysis_items:
            rec_action = (getattr(item.recommendation, "action", None) or "REJECT").upper()
            sig_type = "BUY" if rec_action == "BUY" else ("WATCH" if rec_action == "WATCH" else "REJECT")
            score_val = float(getattr(item.recommendation, "score", 0.0) or 0.0)
            conf_val = float(getattr(item.recommendation, "confidence", 0.0) or (score_val / 100.0 if score_val else 0.0))
            latest_records.append({
                "symbol": item.symbol,
                "signal_type": sig_type,
                "score": score_val,
                "confidence": conf_val,
                "scanned_at": scan_timestamp,
            })
            processed_latest.add(item.symbol)

        for sym in buy_candidates:
            if sym not in processed_latest:
                latest_records.append({
                    "symbol": sym,
                    "signal_type": "BUY",
                    "score": 0.0,
                    "confidence": 0.0,
                    "scanned_at": scan_timestamp,
                })
                processed_latest.add(sym)

        for sym in watch_candidates:
            if sym not in processed_latest:
                latest_records.append({
                    "symbol": sym,
                    "signal_type": "WATCH",
                    "score": 0.0,
                    "confidence": 0.0,
                    "scanned_at": scan_timestamp,
                })
                processed_latest.add(sym)

        if latest_records:
            try:
                ps = PersistenceService(self.db)
                await ps.save_latest_scan_results(latest_records)
                logger.info("PERSIST_CANONICAL_OK | scan_id=%s | count=%s", scan_id, len(latest_records))
                try:
                    from ..observability.metrics import record_scanner_write

                    record_scanner_write("latest_scan_results", "ok")
                except Exception:
                    pass
            except Exception as canon_exc:
                # Spec §12: canonical failure must fail the unit of work and skip history.
                logger.error(
                    "DB_CANONICAL_WRITE_FAILED | scan_id=%s | error=%s",
                    scan_id,
                    canon_exc,
                    exc_info=True,
                )
                try:
                    from ..observability.metrics import record_scanner_write

                    record_scanner_write("latest_scan_results", "failed")
                except Exception:
                    pass
                if scan_ctx:
                    log_scan_persist(scan_ctx, "SCAN_PERSIST_FAILED")
                raise RuntimeError(
                    f"DB_CANONICAL_WRITE_FAILED: {canon_exc}"
                ) from canon_exc

        if minimal_writes is None:
            is_minimal = False
            try:
                is_minimal = bool(settings.is_scan_result_minimal_writes())
            except Exception as ff_exc:
                logger.warning(
                    "FF_DEFAULT_FALLBACK | SCAN_RESULT_MINIMAL_WRITES evaluation error (defaulting to False): %s",
                    ff_exc,
                )
                is_minimal = False
        else:
            is_minimal = bool(minimal_writes)

        try:
            from ..observability.metrics import set_minimal_writes_flag_metric

            set_minimal_writes_flag_metric(is_minimal)
        except Exception:
            pass

        if is_minimal:
            logger.info(
                "PERSIST_MINIMAL_MODE | scan_id=%s | Bypassing scan_snapshots and scan_snapshot_records",
                scan_id,
            )
            try:
                from ..observability.metrics import record_scanner_write

                for table in (
                    "scan_snapshots",
                    "scan_snapshot_records",
                    "scan_history_snapshots",
                    "scanned_candidates",
                ):
                    record_scanner_write(table, "skipped")
            except Exception:
                pass
            return

        # --- Legacy Mode: Upsert parent snapshot (one row per scan_id) ---
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
            try:
                from ..observability.metrics import record_scanner_write

                record_scanner_write("scan_snapshots", "ok")
                record_scanner_write("scan_snapshot_records", "ok")
            except Exception:
                pass
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

    @staticmethod
    def build_dashboard_payload_from_screener(
        response: ScreenerResponse,
        *,
        duration_ms: int = 0,
        scan_id: str | None = None,
        scan_timestamp: datetime | None = None,
    ) -> dict:
        """Build a full dashboard-contract payload from an in-memory ScreenerResponse.

        Used for cache pre-warm under minimal-write mode so clients retain close/OHLCV
        and technical fields even though ``latest_scan_results`` does not store them.
        """
        ts = scan_timestamp or datetime.now(timezone.utc)
        scan_id = scan_id or f"live-{ts.isoformat()}"
        buy_candidates: list[dict] = []
        watch_candidates: list[dict] = []
        rejected_candidates: list[dict] = []
        analysis_items = (
            list(response.analysis.items) if response.analysis and response.analysis.items else []
        )
        by_symbol = {item.symbol: item for item in analysis_items}

        def _cand_from_item(item, rec: str) -> dict:
            tech = _swing_indicators(item)
            return {
                "symbol": item.symbol,
                "recommendation": rec,
                "score": float(getattr(item.recommendation, "score", 0.0) or 0.0),
                "close_price": float(_close_price(item) or 0.0),
                "sma50": tech.get("sma_50") or tech.get("sma50"),
                "sma200": tech.get("sma_200") or tech.get("sma200"),
                "rsi": tech.get("rsi_14") or tech.get("rsi"),
                "macd": tech.get("macd"),
                "volume": None,
                "reason": getattr(item.recommendation, "summary", None),
                "confidence": float(
                    getattr(item.recommendation, "confidence", 0.0) or 0.0
                ),
            }

        for item in analysis_items:
            action = (getattr(item.recommendation, "action", None) or "REJECT").upper()
            if action == "BUY":
                buy_candidates.append(_cand_from_item(item, "BUY"))
            elif action == "WATCH":
                watch_candidates.append(_cand_from_item(item, "WATCH"))
            else:
                rejected_candidates.append(_cand_from_item(item, "REJECTED"))

        for sym in response.buy_candidate_symbols or []:
            if sym in by_symbol:
                continue
            buy_candidates.append(
                {
                    "symbol": sym,
                    "recommendation": "BUY",
                    "score": 0.0,
                    "close_price": 0.0,
                    "sma50": None,
                    "sma200": None,
                    "rsi": None,
                    "macd": None,
                    "volume": None,
                    "reason": None,
                    "confidence": 0.0,
                }
            )
        for sym in response.watch_candidate_symbols or []:
            if sym in by_symbol:
                continue
            watch_candidates.append(
                {
                    "symbol": sym,
                    "recommendation": "WATCH",
                    "score": 0.0,
                    "close_price": 0.0,
                    "sma50": None,
                    "sma200": None,
                    "rsi": None,
                    "macd": None,
                    "volume": None,
                    "reason": None,
                    "confidence": 0.0,
                }
            )

        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        watch_candidates.sort(key=lambda x: x["score"], reverse=True)
        rejected_candidates.sort(key=lambda x: x["score"], reverse=True)
        ts_iso = ts.isoformat()
        return {
            "scan_id": scan_id,
            "scan_timestamp": ts_iso,
            "last_scan_completed_at": ts_iso,
            "total_scanned": int(response.scanned_symbols or 0),
            "valid_symbols": len(response.data_valid_symbols or []),
            "buy_count": len(buy_candidates),
            "watch_count": len(watch_candidates),
            "rejected_count": len(rejected_candidates),
            "buy_candidates": buy_candidates,
            "watch_candidates": watch_candidates,
            "rejected_candidates": rejected_candidates,
            "duration_ms": duration_ms,
        }

    async def prewarm_scanner_latest_cache(self, payload: dict | None = None) -> None:
        """Active pre-warm for GET /scanner/latest using the dashboard payload schema.

        Prefer an in-memory ``payload`` (built from ScreenerResponse) when provided so
        minimal-write mode retains technical fields in Redis. Otherwise load from DB.
        """
        from ..config.settings import settings

        if not settings.is_scanner_latest_cache_enabled():
            return
        try:
            import json

            from ..services.scanner_cache_service import scanner_cache_service

            if payload is None:
                payload = await self.get_latest_completed_scan()
            if payload is None:
                logger.info("scanner cache prewarm skipped | reason=no_completed_scan")
                return
            await scanner_cache_service.set_latest_scan(
                "scanner:latest:v1", json.dumps(payload)
            )
            logger.info(
                "Active cache pre-warming completed for scanner:latest:v1 | scan_id=%s",
                payload.get("scan_id"),
            )
        except Exception as cache_exc:
            logger.warning("Active scanner cache pre-warming failed | err=%s", cache_exc)

    async def _enrich_dashboard_from_history(self, payload: dict) -> dict:
        """Merge close/technical fields from market_data.scan_results when present (M-R1)."""
        try:
            from ..db.scan_store import load_latest_scan

            hist = await load_latest_scan()
            if not hist or not isinstance(hist, dict):
                return payload

            # Build symbol → enrichment from history items / analysis.items
            enrich: dict[str, dict] = {}
            for key in ("items", "all_analyzed_stocks", "matches"):
                for raw in hist.get(key) or []:
                    if not isinstance(raw, dict):
                        continue
                    sym = raw.get("symbol")
                    if not sym:
                        continue
                    entry = enrich.setdefault(sym, {})
                    if raw.get("close") is not None:
                        entry["close_price"] = float(raw.get("close") or 0.0)
                    if raw.get("close_price") is not None:
                        entry["close_price"] = float(raw.get("close_price") or 0.0)
                    tech = raw.get("technical") if isinstance(raw.get("technical"), dict) else {}
                    for src, dst in (
                        ("sma50", "sma50"),
                        ("sma_50", "sma50"),
                        ("sma200", "sma200"),
                        ("sma_200", "sma200"),
                        ("rsi", "rsi"),
                        ("rsi_14", "rsi"),
                        ("macd", "macd"),
                    ):
                        if tech.get(src) is not None:
                            entry[dst] = tech.get(src)
                    rec = raw.get("recommendation")
                    if isinstance(rec, dict):
                        if rec.get("summary"):
                            entry["reason"] = rec.get("summary")
                        if rec.get("score") is not None and "score" not in entry:
                            entry["score"] = float(rec.get("score") or 0.0)

            analysis = hist.get("analysis") if isinstance(hist.get("analysis"), dict) else {}
            for raw in analysis.get("items") or []:
                if not isinstance(raw, dict):
                    continue
                sym = raw.get("symbol")
                if not sym:
                    continue
                entry = enrich.setdefault(sym, {})
                rec = raw.get("recommendation") if isinstance(raw.get("recommendation"), dict) else {}
                if rec.get("summary"):
                    entry["reason"] = rec.get("summary")
                ohlcv = raw.get("ohlcv") or []
                if ohlcv and isinstance(ohlcv[-1], dict) and ohlcv[-1].get("close") is not None:
                    entry["close_price"] = float(ohlcv[-1]["close"])

            if not enrich:
                return payload

            for bucket in ("buy_candidates", "watch_candidates", "rejected_candidates"):
                for cand in payload.get(bucket) or []:
                    extra = enrich.get(cand.get("symbol") or "")
                    if not extra:
                        continue
                    for k, v in extra.items():
                        if v is None:
                            continue
                        # Only fill missing / zero close prices; keep canonical scores.
                        if k == "close_price" and float(cand.get("close_price") or 0) == 0.0:
                            cand[k] = v
                        elif k != "close_price" and cand.get(k) in (None, "", 0, 0.0):
                            cand[k] = v
            return payload
        except Exception as exc:
            logger.debug("dashboard history enrichment skipped | err=%s", exc)
            return payload

    async def resolve_dashboard_payload(self) -> dict | None:
        """Resolve dashboard latest payload with flag-aware source selection.

        When ``SCAN_RESULT_MINIMAL_WRITES`` is ON, ``latest_scan_results`` is the
        authoritative source (avoids stale ``scan_snapshots`` after fan-out reduction).
        When OFF, prefer snapshot tables (legacy) with canonical fallback.
        """
        use_canonical_first = False
        try:
            use_canonical_first = bool(settings.is_scan_result_minimal_writes())
        except Exception:
            use_canonical_first = False

        if use_canonical_first:
            canonical = await self._fetch_latest_from_canonical_results()
            if canonical:
                return await self._enrich_dashboard_from_history(canonical)
            # Fallback to last snapshot if canonical empty (pre-flag data only).
            snapshot, records = await self._fetch_latest_snapshot_and_records()
            if snapshot:
                return self._format_dashboard_payload(snapshot, records)
            return None

        snapshot, records = await self._fetch_latest_snapshot_and_records()
        if snapshot:
            return self._format_dashboard_payload(snapshot, records)
        canonical = await self._fetch_latest_from_canonical_results()
        if canonical:
            return await self._enrich_dashboard_from_history(canonical)
        return None

    async def get_latest_completed_scan(self):
        """Dashboard loader — flag-aware snapshot/canonical resolution (C1/C2)."""
        logger.info("latest_scan_requested")
        payload = await self.resolve_dashboard_payload()

        if not payload:
            logger.info("latest_scan_not_found")
            from ..observability.scan_diagnostics import log_dashboard_request

            log_dashboard_request(
                scan_id=None, endpoint="/scanner/latest", returned_records=0, query_duration_ms=0
            )
            return None

        buy_n = len(payload.get("buy_candidates") or [])
        watch_n = len(payload.get("watch_candidates") or [])
        rejected_n = len(payload.get("rejected_candidates") or [])
        scan_id = payload.get("scan_id")
        logger.info(
            "latest_scan_loaded | scan_id=%s | buy=%s | watch=%s | rejected=%s | "
            "header_buy=%s | header_watch=%s",
            scan_id,
            buy_n,
            watch_n,
            rejected_n,
            payload.get("buy_count"),
            payload.get("watch_count"),
        )
        from ..observability.scan_diagnostics import log_dashboard_request

        log_dashboard_request(
            scan_id=str(scan_id) if scan_id is not None else None,
            endpoint="/scanner/latest",
            returned_records=buy_n + watch_n + rejected_n,
            query_duration_ms=0,
        )
        return payload

    @staticmethod
    def _format_dashboard_payload(snapshot: ScanSnapshot | None, records: list[ScanSnapshotRecord]) -> dict:
        """Adapter for dashboard format (/scanner/latest)."""
        if not snapshot:
            return {
                "message": "No completed scans found",
                "buy_candidates": [],
                "watch_candidates": [],
                "rejected_candidates": [],
            }

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

    @staticmethod
    def _format_analysis_payload(snapshot: ScanSnapshot | None, records: list[ScanSnapshotRecord]) -> dict:
        """ORM-based analysis-shaped adapter (tests / internal tooling).

        Production ``GET /analysis/scan/latest`` uses ``scan_store.load_latest_scan``
        via ``get_latest_scan(format_type="analysis")`` so the payload remains
        ScreenerResponse-compatible for frontend clients.
        """
        if not snapshot:
            return {"available": False}

        items = []
        buy_signals = 0
        watch_signals = 0
        no_signals = 0

        for r in records:
            rec = (r.recommendation or "").upper()
            if rec == "BUY":
                buy_signals += 1
            elif rec == "WATCH":
                watch_signals += 1
            else:
                no_signals += 1

            items.append(
                {
                    "symbol": r.symbol,
                    "recommendation": r.recommendation,
                    "score": float(r.score) if r.score is not None else 0.0,
                    "close_price": float(r.close_price) if r.close_price is not None else 0.0,
                    "technical": {
                        "sma50": float(r.sma50) if r.sma50 is not None else None,
                        "sma200": float(r.sma200) if r.sma200 is not None else None,
                        "rsi": float(r.rsi) if r.rsi is not None else None,
                        "macd": float(r.macd) if r.macd is not None else None,
                    },
                    "reason": r.reason,
                }
            )

        return {
            "available": True,
            "timestamp": snapshot.scan_timestamp.isoformat(),
            "scan_id": snapshot.scan_id,
            "total_symbols": snapshot.total_scanned,
            "buy_signals": buy_signals,
            "watch_signals": watch_signals,
            "no_signals": no_signals,
            "items": items,
        }

    async def _fetch_latest_snapshot_and_records(self) -> tuple[ScanSnapshot | None, list[ScanSnapshotRecord]]:
        """Fetch the latest completed snapshot (or newest fallback) and child records."""
        stmt = (
            select(ScanSnapshot)
            .where(ScanSnapshot.status == "COMPLETED")
            .order_by(desc(ScanSnapshot.scan_timestamp))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if not snapshot:
            result = await self.db.execute(
                select(ScanSnapshot).order_by(desc(ScanSnapshot.scan_timestamp)).limit(1)
            )
            snapshot = result.scalar_one_or_none()

        if not snapshot:
            return None, []

        stmt_records = select(ScanSnapshotRecord).where(
            ScanSnapshotRecord.scan_id == snapshot.scan_id
        )
        result_records = await self.db.execute(stmt_records)
        records = result_records.scalars().all()
        return snapshot, list(records)

    async def _fetch_latest_from_canonical_results(self) -> dict | None:
        """Derive dashboard payload from ``latest_scan_results`` (canonical source).

        Shape matches ``_format_dashboard_payload`` so clients get the same field
        contract whether data came from snapshots or canonical rows (FR-009).
        Only the latest scan wave (max ``scanned_at``) is included so stale
        symbols from older runs do not pollute the dashboard.
        """
        res = await self.db.execute(select(LatestScanResult))
        scalars_result = res.scalars()
        # Support both sync Result.scalars() and async mock/session variants.
        if hasattr(scalars_result, "__await__"):
            scalars_result = await scalars_result  # type: ignore[misc]
        all_method = getattr(scalars_result, "all", None)
        if all_method is None:
            all_rows = list(scalars_result) if scalars_result else []
        else:
            maybe_rows = all_method()
            if hasattr(maybe_rows, "__await__"):
                maybe_rows = await maybe_rows  # type: ignore[misc]
            all_rows = list(maybe_rows or [])
        if not all_rows:
            return None

        max_scanned_at = max(
            (r.scanned_at for r in all_rows if r.scanned_at is not None),
            default=None,
        )
        if max_scanned_at is None:
            rows = all_rows
        else:
            # Same-wave equality: all rows written in one persist share scan_timestamp.
            rows = [r for r in all_rows if r.scanned_at == max_scanned_at]
            if not rows:
                rows = all_rows

        buy_candidates: list[dict] = []
        watch_candidates: list[dict] = []
        rejected_candidates: list[dict] = []

        for row in rows:
            sig = (row.signal_type or "REJECT").upper()
            if sig == "BUY":
                rec = "BUY"
            elif sig == "WATCH":
                rec = "WATCH"
            else:
                rec = "REJECTED"

            cand_dict = {
                "symbol": row.symbol,
                "recommendation": rec if rec != "REJECTED" else row.signal_type,
                "score": float(row.score or 0.0),
                # Canonical table has no OHLCV; preserve field presence for contract parity.
                "close_price": 0.0,
                "sma50": None,
                "sma200": None,
                "rsi": None,
                "macd": None,
                "volume": None,
                "reason": f"Signal: {row.signal_type}",
                "confidence": float(row.confidence or 0.0),
            }

            if rec == "BUY":
                buy_candidates.append(cand_dict)
            elif rec == "WATCH":
                watch_candidates.append(cand_dict)
            else:
                rejected_candidates.append(cand_dict)

        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        watch_candidates.sort(key=lambda x: x["score"], reverse=True)
        rejected_candidates.sort(key=lambda x: x["score"], reverse=True)

        scan_ts = (
            max_scanned_at.isoformat()
            if max_scanned_at is not None
            else datetime.now(timezone.utc).isoformat()
        )
        # Stable synthetic id for ops/diagnostics (not a UUID from scan_snapshots).
        scan_id = f"canonical-{scan_ts}"

        return {
            "scan_id": scan_id,
            "scan_timestamp": scan_ts,
            "last_scan_completed_at": scan_ts,
            "total_scanned": len(rows),
            "valid_symbols": len(buy_candidates) + len(watch_candidates),
            "buy_count": len(buy_candidates),
            "watch_count": len(watch_candidates),
            "rejected_count": len(rejected_candidates),
            "buy_candidates": buy_candidates,
            "watch_candidates": watch_candidates,
            "rejected_candidates": rejected_candidates,
        }

    async def _fetch_analysis_from_canonical_results(self) -> dict | None:
        """ScreenerResponse-compatible projection from canonical latest for analysis path."""
        dashboard = await self._fetch_latest_from_canonical_results()
        if not dashboard:
            return None

        buy_syms = [c["symbol"] for c in (dashboard.get("buy_candidates") or [])]
        watch_syms = [c["symbol"] for c in (dashboard.get("watch_candidates") or [])]
        items = []
        for c in (dashboard.get("buy_candidates") or []):
            items.append(
                {
                    "symbol": c["symbol"],
                    "signal": "BUY",
                    "matched": True,
                    "score": c.get("score", 0.0),
                    "confidence": c.get("confidence", 0.0),
                }
            )
        for c in (dashboard.get("watch_candidates") or []):
            items.append(
                {
                    "symbol": c["symbol"],
                    "signal": "WATCH",
                    "matched": True,
                    "score": c.get("score", 0.0),
                    "confidence": c.get("confidence", 0.0),
                }
            )

        scan_ts = dashboard.get("scan_timestamp")
        return {
            "buy_candidate_symbols": buy_syms,
            "watch_candidate_symbols": watch_syms,
            "shortlisted_symbols": buy_syms + watch_syms,
            "all_analyzed_stocks": items,
            "matches": items,
            "items": items,
            "scanned_at": scan_ts,
            "last_scan_completed_at": scan_ts,
            "scanned_symbols": dashboard.get("total_scanned", len(items)),
            "scan_id": dashboard.get("scan_id"),
        }

    async def get_latest_scan(
        self,
        format_type: str = "dashboard",
        force: bool = False,
        cache_enabled: bool | None = None,
    ) -> tuple[str, str]:
        """Unified entry point for scan snapshot resolution across all endpoints.

        Returns tuple of (serialized_json_payload, cache_status).

        format_type:
          - ``dashboard``: ScanSnapshot ORM → dashboard candidate buckets
            (``GET /scanner/latest`` contract).
          - ``analysis``: ``scan_store.load_latest_scan`` → ScreenerResponse-compatible
            body with ``available`` wrapper (``GET /analysis/scan/latest`` contract).
            Analysis intentionally uses the same JSONB source as the legacy path so
            Redis key ``analysis:scan:latest:v1`` never stores a divergent shape.
        """
        import json
        import time
        from ..config.settings import settings
        from ..services.scanner_cache_service import scanner_cache_service
        from ..observability.scan_diagnostics import log_dashboard_request
        from ..observability.metrics import (
            record_latest_scan_service_invocation,
            record_scanner_cache_hit,
            record_scanner_cache_miss,
        )

        if format_type not in ("dashboard", "analysis"):
            raise ValueError(
                f"Unsupported format_type={format_type!r}; expected 'dashboard' or 'analysis'"
            )

        start_t = time.perf_counter()
        if cache_enabled is None:
            cache_enabled = settings.is_scanner_latest_cache_enabled()

        record_latest_scan_service_invocation(format_type)

        if format_type == "analysis":
            cache_key = "analysis:scan:latest:v1"
            endpoint = "/analysis/scan/latest"
        else:
            cache_key = "scanner:latest:v1"
            endpoint = "/scanner/latest"

        # Force-refresh metrics are recorded once at the route boundary to avoid
        # double-counting when unified path fails and legacy fallback also runs.

        async def produce_json() -> str:
            duration_ms = int((time.perf_counter() - start_t) * 1000)

            if format_type == "analysis":
                from ..db.scan_store import load_latest_scan

                data = await load_latest_scan()
                if data is None:
                    # M1: under minimal writes, history may be empty — derive from canonical.
                    canonical_analysis = await self._fetch_analysis_from_canonical_results()
                    if canonical_analysis:
                        payload_dict = {"available": True, **canonical_analysis}
                        items = canonical_analysis.get("items") or []
                        scan_id = canonical_analysis.get("scan_id")
                        returned_records = len(items)
                        is_empty = False
                    else:
                        payload_dict = {"available": False}
                        scan_id = None
                        returned_records = 0
                        is_empty = True
                else:
                    # Must match legacy route: full ScreenerResponse fields for FE clients.
                    payload_dict = {"available": True, **data}
                    items = data.get("items") if isinstance(data.get("items"), list) else []
                    scan_id = (
                        data.get("scan_id")
                        or data.get("scanned_at")
                        or data.get("last_scan_completed_at")
                    )
                    returned_records = len(items)
                    is_empty = False
            else:
                # C1: flag-aware resolution — minimal mode prefers canonical over stale snapshots.
                resolved = await self.resolve_dashboard_payload()
                if resolved:
                    payload_dict = resolved
                    scan_id = resolved.get("scan_id")
                    returned_records = (
                        len(payload_dict.get("buy_candidates") or [])
                        + len(payload_dict.get("watch_candidates") or [])
                        + len(payload_dict.get("rejected_candidates") or [])
                    )
                    is_empty = False
                else:
                    payload_dict = self._format_dashboard_payload(None, [])
                    scan_id = None
                    returned_records = 0
                    is_empty = True

                # Preserve legacy dashboard diagnostics on the unified path.
                try:
                    from ..services.diagnostics_service import diagnostics

                    diagnostics.record_dashboard_snapshot(
                        {
                            "response_time_ms": duration_ms,
                            "snapshot_id": scan_id,
                            "record_count": returned_records,
                        }
                    )
                except Exception as diag_exc:  # pragma: no cover - best effort
                    logger.debug("dashboard diagnostics record skipped | err=%s", diag_exc)

            log_dashboard_request(
                scan_id=str(scan_id) if scan_id is not None else None,
                endpoint=endpoint,
                returned_records=returned_records,
                query_duration_ms=duration_ms,
            )

            serialized_payload = json.dumps(payload_dict)
            if cache_enabled:
                ttl = 10 if is_empty else settings.scanner_latest_cache_ttl_seconds
                await scanner_cache_service.set_latest_scan(
                    cache_key, serialized_payload, ttl_seconds=ttl
                )
            return serialized_payload

        payload, cache_status = await scanner_cache_service.resolve_latest_scan(
            cache_key,
            produce_json,
            force=force,
            cache_enabled=cache_enabled,
        )

        if cache_status == "HIT":
            record_scanner_cache_hit(endpoint)
        elif cache_status in ("MISS", "FALLBACK"):
            record_scanner_cache_miss(endpoint)

        return payload, cache_status
