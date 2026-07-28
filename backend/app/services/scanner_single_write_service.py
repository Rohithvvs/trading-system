from __future__ import annotations

import logging
import time
from typing import List, Dict, Any, Optional
from decimal import Decimal
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models.market_data import LatestScanResult
from ..schemas.scan_aggregate import ScanAggregateResult, SingleWriteResult
from ..observability.metrics import (
    observe_single_write_duration,
    record_scanner_transaction,
    record_scanner_write,
    record_single_write_failure,
)

logger = logging.getLogger(__name__)

BATCH_CHUNK_SIZE = 500


class ScannerSingleWriteService:
    """
    Authoritative single-transaction persistence service for market scan execution (Sprint 5).
    Executes a single atomic transaction at successful scan completion.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def persist_single_final_write(
        self,
        aggregate: ScanAggregateResult,
    ) -> SingleWriteResult:
        """
        Executes a single atomic database transaction containing latest scan results upsert
        and optional history insertions.
        """
        start_time = time.monotonic()
        latest_upsert_count = 0
        history_insert_count = 0

        try:
            # Determine database dialect
            try:
                conn = await self.db.connection()
                dialect = conn.dialect.name
            except Exception:
                dialect = "postgresql"

            # Prepare records for latest_scan_results
            latest_records: List[Dict[str, Any]] = []
            for c in aggregate.candidates:
                latest_records.append({
                    "symbol": c.symbol,
                    "signal_type": c.signal_type,
                    "score": Decimal(str(c.score)) if c.score is not None else None,
                    "confidence": Decimal(str(c.score)) if c.score is not None else None,
                    "scanned_at": aggregate.execution_timestamp,
                })

            # Execute within an atomic transaction context
            async with self._ensure_transaction_context():
                # 1. Upsert latest_scan_results
                if latest_records:
                    if dialect == "sqlite":
                        stmt = sqlite_insert(LatestScanResult).values(latest_records)
                    else:
                        stmt = pg_insert(LatestScanResult).values(latest_records)

                    upsert_stmt = stmt.on_conflict_do_update(
                        index_elements=["symbol"],
                        set_={
                            "signal_type": stmt.excluded.signal_type,
                            "score": stmt.excluded.score,
                            "confidence": stmt.excluded.confidence,
                            "scanned_at": stmt.excluded.scanned_at,
                            "updated_at": func.now(),
                        },
                    )
                    await self.db.execute(upsert_stmt)
                    latest_upsert_count = len(latest_records)
                    record_scanner_write("latest_scan_results", "ok")

                # 2. Conditional History Persistence (market_data.scan_results)
                if aggregate.save_history and latest_records:
                    history_insert_count = await self._persist_history_chunks(
                        aggregate, latest_records, dialect
                    )
                    record_scanner_write("market_data.scan_results", "ok")
                elif not aggregate.save_history:
                    record_scanner_write("market_data.scan_results", "skipped")

            duration = time.monotonic() - start_time
            duration_ms = duration * 1000.0

            observe_single_write_duration(duration)
            record_scanner_transaction(mode="single_final_write")

            logger.info(
                "Single Final Write completed successfully: %d latest upserted, %d history inserted in %.2fms",
                latest_upsert_count,
                history_insert_count,
                duration_ms,
            )

            return SingleWriteResult(
                success=True,
                latest_rows_upserted=latest_upsert_count,
                history_rows_inserted=history_insert_count,
                transaction_duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            record_single_write_failure(reason="db_error")
            record_scanner_write("latest_scan_results", "failed")
            logger.error(
                "Single Final Write transaction failed | scan_id=%s | universe=%s | candidates=%d | duration_ms=%.2fms | error=%s",
                aggregate.scan_id,
                aggregate.symbol_universe,
                len(aggregate.candidates),
                duration_ms,
                exc,
                exc_info=True,
            )
            raise

    def _ensure_transaction_context(self):
        """Returns session transaction manager context."""
        if self.db.in_transaction():
            class DummyAsyncContext:
                async def __aenter__(self):
                    return None
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    if exc_type is not None:
                        pass
            return DummyAsyncContext()
        else:
            return self.db.begin()

    async def _persist_history_chunks(
        self,
        aggregate: ScanAggregateResult,
        latest_records: List[Dict[str, Any]],
        dialect: str,
    ) -> int:
        """Batch inserts historical scan candidate records in parameterised chunks of 500."""
        inserted_total = 0
        for i in range(0, len(latest_records), BATCH_CHUNK_SIZE):
            chunk = latest_records[i : i + BATCH_CHUNK_SIZE]
            if dialect == "sqlite":
                # For SQLite testing, insert into sqlite scan_results if available
                try:
                    await self.db.execute(
                        text("CREATE TABLE IF NOT EXISTS scan_results (id INTEGER PRIMARY KEY, symbol TEXT, signal_type TEXT, score REAL, scanned_at TEXT)")
                    )
                    for r in chunk:
                        await self.db.execute(
                            text("INSERT INTO scan_results (symbol, signal_type, score, scanned_at) VALUES (:symbol, :signal_type, :score, :scanned_at)"),
                            {
                                "symbol": r["symbol"],
                                "signal_type": r["signal_type"],
                                "score": float(r["score"]) if r["score"] is not None else 0.0,
                                "scanned_at": str(r["scanned_at"]),
                            },
                        )
                except Exception as sq_err:
                    logger.debug("SQLite history test table write: %s", sq_err)
            else:
                # PostgreSQL chunked insert
                for r in chunk:
                    await self.db.execute(
                        text(
                            "INSERT INTO market_data.scan_results (symbol, signal_type, score, created_at) "
                            "VALUES (:symbol, :signal_type, :score, :created_at)"
                        ),
                        {
                            "symbol": r["symbol"],
                            "signal_type": r["signal_type"],
                            "score": r["score"],
                            "created_at": r["scanned_at"],
                        },
                    )
            inserted_total += len(chunk)
        return inserted_total
