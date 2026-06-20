import uuid
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from ..models.market_data import ScanSnapshot, ScanSnapshotRecord
from ..schemas import ScreenerResponse
from ..utils import get_logger
from ..observability.scan_diagnostics import get_current_scan, log_scan_persist

logger = get_logger("backend.app.services.latest_scan_service")

class LatestScanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def persist_successful_scan(self, response: ScreenerResponse, duration_ms: int):
        logger.info("Persisting successful scan snapshot")
        scan_ctx = get_current_scan()
        if scan_ctx:
            log_scan_persist(scan_ctx, "SCAN_PERSIST_BEGIN")
        
        scan_id = str(uuid.uuid4())
        scan_timestamp = datetime.datetime.now(datetime.timezone.utc)
        
        buy_candidates = response.buy_candidate_symbols or []
        watch_candidates = response.watch_candidate_symbols or []
        
        # We need to construct the records based on `response.analysis.items`
        # Because we need `recommendation.action`, `score`, `close`, `sma50`, `sma200`, `rsi`, `macd`, `volume`, `reason`.
        # However, `response.analysis` contains items for shortlisted ones.
        # What about rejected candidates? They are in `response.matches` or `response.all_analyzed_stocks`.
        
        # We need the full list of candidates that were recommended or rejected.
        # Let's extract from response.
        
        snapshot = ScanSnapshot(
            scan_id=scan_id,
            scan_timestamp=scan_timestamp,
            scan_duration_ms=duration_ms,
            total_scanned=response.scanned_symbols,
            valid_symbols=len(response.data_valid_symbols),
            buy_count=len(buy_candidates),
            watch_count=len(watch_candidates),
            rejected_count=0, # Will update below
            status="completed"
        )
        
        self.db.add(snapshot)
        
        # Let's process the ones in analysis (buy, watch, some rejected)
        processed_symbols = set()
        rejected_count = 0
        
        if response.analysis and response.analysis.items:
            for item in response.analysis.items:
                rec_action = item.recommendation.action.upper()
                if rec_action not in ["BUY", "WATCH"]:
                    rec_action = "REJECTED"
                
                tech_data = item.technical_indicators if hasattr(item, 'technical_indicators') else {}
                
                record = ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=item.symbol,
                    recommendation=rec_action,
                    score=item.recommendation.score,
                    close_price=item.ohlcv[-1].close if item.ohlcv else 0.0,
                    sma50=tech_data.get('sma_50'),
                    sma200=tech_data.get('sma_200'),
                    rsi=tech_data.get('rsi_14'),
                    macd=tech_data.get('macd'),
                    volume=None,
                    reason=item.recommendation.summary
                )
                self.db.add(record)
                processed_symbols.add(item.symbol)
                
                if rec_action == "REJECTED":
                    rejected_count += 1
                    
        # Now process the rest of the matched or eligible but not shortlisted symbols as REJECTED
        # Actually, let's look at `all_analyzed_stocks` or `matches`
        for match in response.matches:
            if match.symbol not in processed_symbols:
                record = ScanSnapshotRecord(
                    scan_id=scan_id,
                    symbol=match.symbol,
                    recommendation="REJECTED",
                    score=match.screener_score,
                    close_price=match.close,
                    sma50=match.sma_50,
                    sma200=match.sma_200,
                    rsi=None, # RSI not directly on match if not fully analyzed, but we can try to extract from conditions or leave None
                    macd=match.macd,
                    volume=match.volume,
                    reason="Not shortlisted by orchestrator"
                )
                self.db.add(record)
                processed_symbols.add(match.symbol)
                rejected_count += 1
                
        snapshot.rejected_count = rejected_count
        
        try:
            await self.db.flush()
            logger.info("scan_persist_completed | scan_id=%s | scan_timestamp=%s | duration_ms=%s | buy=%s | watch=%s | rejected=%s",
                        scan_id, scan_timestamp, duration_ms, snapshot.buy_count, snapshot.watch_count, snapshot.rejected_count)
            if scan_ctx:
                rows_written = len(processed_symbols)
                log_scan_persist(
                    scan_ctx, "SCAN_PERSIST_SUCCESS",
                    buy_count=snapshot.buy_count,
                    watch_count=snapshot.watch_count,
                    reject_count=snapshot.rejected_count,
                    rows_written=rows_written,
                )
        except Exception as e:
            logger.error("scan_persist_failed | scan_id=%s | error=%s", scan_id, str(e))
            if scan_ctx:
                log_scan_persist(scan_ctx, "SCAN_PERSIST_FAILED")
            raise

    async def get_latest_completed_scan(self):
        logger.info("latest_scan_requested")
        stmt = select(ScanSnapshot).order_by(desc(ScanSnapshot.scan_timestamp)).limit(1)
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()
        
        if not snapshot:
            logger.info("latest_scan_not_found")
            from ..observability.scan_diagnostics import log_dashboard_request
            log_dashboard_request(scan_id=None, endpoint="/scanner/latest", returned_records=0, query_duration_ms=0)
            return None
            
        # Get records
        stmt_records = select(ScanSnapshotRecord).where(ScanSnapshotRecord.scan_id == snapshot.scan_id)
        result_records = await self.db.execute(stmt_records)
        records = result_records.scalars().all()
        
        buy_candidates = []
        watch_candidates = []
        rejected_candidates = []
        
        for r in records:
            item = {
                "symbol": r.symbol,
                "recommendation": r.recommendation,
                "score": float(r.score) if r.score else 0.0,
                "close_price": float(r.close_price) if r.close_price else 0.0,
                "sma50": float(r.sma50) if r.sma50 else None,
                "sma200": float(r.sma200) if r.sma200 else None,
                "rsi": float(r.rsi) if r.rsi else None,
                "macd": float(r.macd) if r.macd else None,
                "volume": r.volume,
                "reason": r.reason
            }
            if r.recommendation == "BUY":
                buy_candidates.append(item)
            elif r.recommendation == "WATCH":
                watch_candidates.append(item)
            else:
                rejected_candidates.append(item)
                
        # Sort candidates
        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        watch_candidates.sort(key=lambda x: x["score"], reverse=True)
        rejected_candidates.sort(key=lambda x: x["score"], reverse=True)

        logger.info("latest_scan_loaded | scan_id=%s", snapshot.scan_id)
        from ..observability.scan_diagnostics import log_dashboard_request
        total_records = len(buy_candidates) + len(watch_candidates) + len(rejected_candidates)
        log_dashboard_request(scan_id=snapshot.scan_id, endpoint="/scanner/latest", returned_records=total_records, query_duration_ms=0)
        return {
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
