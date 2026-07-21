"""Historical situation-tag backfill with keyset paging, progress, and production safeguards.

Hardening (audit): H1 processed_count accuracy, H2 FAILED on interrupt/error,
H3 single-job concurrency, H4/H6 news sources without N+1, H5 streamed report,
plus resume remaining budget and ±3 day news window.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload

from ..db.locks import acquire_singleton_lease
from ..db.session import AsyncSessionLocal
from ..models.analysis import AnalysisHistory, BackfillProgress
from ..models.stock import WatchedStock
from .taxonomy_classifier import determine_situation_tags

logger = logging.getLogger(__name__)

# Plan/research: earnings news window around recommendation time
_NEWS_WINDOW = timedelta(days=3)
_BACKFILL_LOCK_NAME = "taxonomy_situation_backfill"
_REPORT_PAGE_SIZE = 1000
_ALLOWED_TAGS = (
    "GOOD_NEWS_CATALYST",
    "BAD_NEWS_CATALYST",
    "EARNINGS_PLAY",
    "MARKET_REGIME",
    "RANGE_BOUND",
    "UNKNOWN",
)

# SC-004 distribution health targets (spec success criteria)
_SC004_MAX_SINGLE_TAG_PCT = 60.0  # excluding UNKNOWN
_SC004_MAX_UNKNOWN_PCT = 15.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BackfillService:
    async def get_job_progress(self, job_id: str) -> BackfillProgress | None:
        """Load the latest progress row for a backfill job."""
        async with AsyncSessionLocal() as db:
            return (
                await db.scalars(
                    select(BackfillProgress).where(BackfillProgress.job_id == job_id)
                )
            ).first()

    async def pause_backfill(self, job_id: str) -> BackfillProgress:
        """M3: Mark a RUNNING (or FAILED mid-run) job as PAUSED for clean resume.

        The active runner checks status between batches and exits when PAUSED.
        """
        async with AsyncSessionLocal() as db:
            progress = (
                await db.scalars(
                    select(BackfillProgress).where(BackfillProgress.job_id == job_id)
                )
            ).first()
            if not progress:
                raise RuntimeError(f"No backfill job found for job_id={job_id}")
            if progress.status == "COMPLETED":
                raise RuntimeError(
                    f"Backfill job {job_id} is already COMPLETED and cannot be paused"
                )
            if progress.status == "PAUSED":
                return progress
            progress.status = "PAUSED"
            progress.updated_at = _utc_now()
            await db.commit()
            await db.refresh(progress)
            logger.info(
                "Backfill job %s paused at last_processed_id=%s processed_count=%s",
                job_id,
                progress.last_processed_id,
                progress.processed_count,
            )
            return progress

    async def _mark_job_status(
        self,
        progress_id: int | None,
        status: str,
        *,
        last_processed_id: int | None = None,
        processed_count: int | None = None,
    ) -> None:
        if progress_id is None:
            return
        try:
            async with AsyncSessionLocal() as db:
                progress_db = await db.get(BackfillProgress, progress_id)
                if not progress_db:
                    return
                # Do not overwrite a terminal COMPLETED state
                if progress_db.status == "COMPLETED" and status != "COMPLETED":
                    return
                progress_db.status = status
                progress_db.updated_at = _utc_now()
                if last_processed_id is not None:
                    progress_db.last_processed_id = last_processed_id
                if processed_count is not None:
                    progress_db.processed_count = processed_count
                await db.commit()
        except Exception:
            logger.exception(
                "Failed to mark backfill progress_id=%s as %s", progress_id, status
            )

    async def _assert_single_running_job(self, db, job_id: str) -> None:
        """H3: reject when another job is already RUNNING."""
        running = (
            await db.scalars(
                select(BackfillProgress).where(BackfillProgress.status == "RUNNING")
            )
        ).all()
        for row in running:
            if row.job_id != job_id:
                raise RuntimeError(
                    f"Another backfill job is already RUNNING (job_id={row.job_id}). "
                    "Wait for it to finish, or resume/stop that job before starting another."
                )

    async def _detect_news_source(self, db) -> str | None:
        """Prefer news_articles; fall back to news_deduplication_audit (H4)."""
        dialect_name = db.bind.dialect.name if db.bind else "postgresql"
        candidates = ("news_articles", "news_deduplication_audit")
        for table in candidates:
            try:
                if dialect_name == "postgresql":
                    check_stmt = text(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = :table_name
                        )
                        """
                    )
                    exists = (await db.execute(check_stmt, {"table_name": table})).scalar() or False
                else:
                    check_stmt = text(
                        """
                        SELECT count(*) FROM sqlite_master
                        WHERE type='table' AND name=:table_name
                        """
                    )
                    count = (await db.execute(check_stmt, {"table_name": table})).scalar() or 0
                    exists = count > 0
                if exists:
                    return table
            except Exception:
                logger.warning("News source probe failed for table=%s", table, exc_info=True)
        return None

    async def _fetch_articles_for_batch(
        self,
        db,
        batch: list[AnalysisHistory],
        news_source: str | None,
        symbol_by_stock_id: dict[int, str],
    ) -> dict[int, list[dict]]:
        """H6: one batched news query per page; map analysis id -> articles within ±3 days."""
        empty: dict[int, list[dict]] = {rec.id: [] for rec in batch}
        if not news_source or not batch:
            return empty

        symbols: set[str] = set()
        min_ts: datetime | None = None
        max_ts: datetime | None = None
        for rec in batch:
            symbol = None
            if rec.stock is not None and getattr(rec.stock, "symbol", None):
                symbol = rec.stock.symbol
            else:
                symbol = symbol_by_stock_id.get(rec.stock_id)
            if not symbol or not rec.created_at:
                continue
            symbols.add(symbol)
            start = rec.created_at - _NEWS_WINDOW
            end = rec.created_at + _NEWS_WINDOW
            min_ts = start if min_ts is None else min(min_ts, start)
            max_ts = end if max_ts is None else max(max_ts, end)

        if not symbols or min_ts is None or max_ts is None:
            return empty

        from sqlalchemy import bindparam

        rows: list = []
        try:
            if news_source == "news_articles":
                news_stmt = text(
                    """
                    SELECT symbol, title, description, published_at
                    FROM news_articles
                    WHERE symbol IN :symbols
                      AND published_at BETWEEN :start AND :end
                    """
                ).bindparams(bindparam("symbols", expanding=True))
                res = await db.execute(
                    news_stmt,
                    {"symbols": list(symbols), "start": min_ts, "end": max_ts},
                )
                rows = res.fetchall()
            elif news_source == "news_deduplication_audit":
                news_stmt = text(
                    """
                    SELECT symbol, kept_title, deduplicated_title, created_at
                    FROM news_deduplication_audit
                    WHERE symbol IN :symbols
                      AND created_at BETWEEN :start AND :end
                    """
                ).bindparams(bindparam("symbols", expanding=True))
                res = await db.execute(
                    news_stmt,
                    {"symbols": list(symbols), "start": min_ts, "end": max_ts},
                )
                rows = res.fetchall()
        except Exception:
            logger.warning(
                "Batch news fetch failed for source=%s; continuing without articles",
                news_source,
                exc_info=True,
            )
            return empty

        # Index by symbol for in-memory window match
        by_symbol: dict[str, list[tuple]] = {}
        for row in rows:
            by_symbol.setdefault(row[0], []).append(row)

        result = dict(empty)
        for rec in batch:
            symbol = None
            if rec.stock is not None and getattr(rec.stock, "symbol", None):
                symbol = rec.stock.symbol
            else:
                symbol = symbol_by_stock_id.get(rec.stock_id)
            if not symbol or not rec.created_at:
                continue
            start = rec.created_at - _NEWS_WINDOW
            end = rec.created_at + _NEWS_WINDOW
            articles: list[dict] = []
            for nrow in by_symbol.get(symbol, []):
                ts = nrow[3]
                if ts is None:
                    continue
                # Normalize tz-aware vs naive for comparison
                try:
                    if ts.tzinfo is not None and start.tzinfo is None:
                        start_cmp = start.replace(tzinfo=timezone.utc)
                        end_cmp = end.replace(tzinfo=timezone.utc)
                    elif ts.tzinfo is None and start.tzinfo is not None:
                        start_cmp = start.replace(tzinfo=None)
                        end_cmp = end.replace(tzinfo=None)
                    else:
                        start_cmp, end_cmp = start, end
                    if not (start_cmp <= ts <= end_cmp):
                        continue
                except TypeError:
                    continue
                if news_source == "news_articles":
                    articles.append({"title": nrow[1] or "", "description": nrow[2] or ""})
                else:
                    articles.append(
                        {
                            "title": nrow[1] or "",
                            "description": nrow[2] or "",
                        }
                    )
            result[rec.id] = articles
        return result

    async def run_backfill(
        self,
        job_id: str,
        batch_size: int = 100,
        delay_seconds: float = 0.5,
        resume: bool = True,
        limit: int | None = None,
    ) -> int:
        """Run the backfill process in controlled batches with keyset paging and yield locks."""
        logger.info(
            "Starting backfill job %s (resume=%s, batch_size=%s, delay=%s, limit=%s)",
            job_id,
            resume,
            batch_size,
            delay_seconds,
            limit,
        )

        # H3: process-wide single backfill (Postgres advisory lock; no-op acquire on SQLite)
        lease = await acquire_singleton_lease(
            _BACKFILL_LOCK_NAME,
            max_lease_seconds=24 * 3600,
        )
        if not lease.acquired:
            raise RuntimeError(
                "Another taxonomy backfill holds the concurrency lock. "
                "Only one backfill may run at a time."
            )

        progress_id: int | None = None
        last_processed_id = 0
        cumulative_processed = 0
        this_run_count = 0
        stop_requested = {"value": False}

        def _request_stop(signum, frame):  # noqa: ARG001
            stop_requested["value"] = True
            logger.warning(
                "Backfill job %s received signal %s; will stop after current batch",
                job_id,
                signum,
            )

        prev_sigint = None
        prev_sigterm = None
        try:
            prev_sigint = signal.signal(signal.SIGINT, _request_stop)
            if hasattr(signal, "SIGTERM"):
                prev_sigterm = signal.signal(signal.SIGTERM, _request_stop)
        except (ValueError, OSError):
            # Not in main thread or platform restriction
            pass

        try:
            async with AsyncSessionLocal() as db:
                progress = None
                if resume:
                    progress = (
                        await db.scalars(
                            select(BackfillProgress).where(BackfillProgress.job_id == job_id)
                        )
                    ).first()

                if progress:
                    if progress.status == "COMPLETED":
                        logger.info("Job %s is already completed. Exiting.", job_id)
                        return 0
                    await self._assert_single_running_job(db, job_id)
                    progress.status = "RUNNING"
                    progress.updated_at = _utc_now()
                    await db.commit()
                    logger.info(
                        "Resuming job %s from last_processed_id=%s processed_count=%s",
                        job_id,
                        progress.last_processed_id,
                        progress.processed_count,
                    )
                else:
                    await self._assert_single_running_job(db, job_id)
                    await db.execute(
                        text("DELETE FROM backfill_progress WHERE job_id = :job_id"),
                        {"job_id": job_id},
                    )
                    await db.commit()

                    total_count = (
                        await db.execute(select(func.count(AnalysisHistory.id)))
                    ).scalar() or 0

                    now = _utc_now()
                    progress = BackfillProgress(
                        job_id=job_id,
                        last_processed_id=0,
                        status="RUNNING",
                        processed_count=0,
                        total_count=total_count,
                        started_at=now,
                        updated_at=now,
                    )
                    db.add(progress)
                    await db.commit()
                    await db.refresh(progress)

                progress_id = progress.id
                last_processed_id = progress.last_processed_id
                cumulative_processed = progress.processed_count

                # M2: remaining budget on resume; unlimited until empty when no limit
                if limit is not None:
                    max_to_process: int | None = limit
                else:
                    remaining = max(0, progress.total_count - progress.processed_count)
                    # Prefer draining remaining rows; if total was 0, complete below
                    max_to_process = remaining if remaining > 0 else (
                        0 if progress.total_count == 0 else None
                    )

                news_source = await self._detect_news_source(db)
                logger.info(
                    "Backfill job %s news_source=%s max_to_process=%s",
                    job_id,
                    news_source,
                    max_to_process,
                )

                if max_to_process == 0:
                    progress.status = "COMPLETED"
                    progress.updated_at = _utc_now()
                    await db.commit()
                    logger.info(
                        "Backfill job %s completed with nothing to process.",
                        job_id,
                    )
                    return 0

            while max_to_process is None or this_run_count < max_to_process:
                if stop_requested["value"]:
                    await self._mark_job_status(
                        progress_id,
                        "FAILED",
                        last_processed_id=last_processed_id,
                        processed_count=cumulative_processed,
                    )
                    logger.warning(
                        "Backfill job %s stopped by signal. status=FAILED "
                        "last_processed_id=%s processed_count=%s",
                        job_id,
                        last_processed_id,
                        cumulative_processed,
                    )
                    break

                async with AsyncSessionLocal() as db:
                    # Honor external PAUSE (status flip in DB)
                    progress_db = await db.get(BackfillProgress, progress_id)
                    if progress_db and progress_db.status == "PAUSED":
                        logger.info(
                            "Backfill job %s observed PAUSED; exiting cleanly",
                            job_id,
                        )
                        break

                    stmt = (
                        select(AnalysisHistory)
                        .options(selectinload(AnalysisHistory.stock))
                        .where(AnalysisHistory.id > last_processed_id)
                        .order_by(AnalysisHistory.id.asc())
                        .limit(batch_size)
                    )
                    batch = list((await db.scalars(stmt)).all())
                    if not batch:
                        if progress_db:
                            progress_db.status = "COMPLETED"
                            progress_db.updated_at = _utc_now()
                            await db.commit()
                        logger.info(
                            "Backfill job %s completed successfully. processed_count=%s",
                            job_id,
                            cumulative_processed,
                        )
                        break

                    # Resolve symbols for records missing relationship
                    symbol_by_stock_id: dict[int, str] = {}
                    missing_stock_ids = {
                        rec.stock_id
                        for rec in batch
                        if rec.stock is None or not getattr(rec.stock, "symbol", None)
                    }
                    if missing_stock_ids:
                        stocks = (
                            await db.scalars(
                                select(WatchedStock).where(
                                    WatchedStock.id.in_(missing_stock_ids)
                                )
                            )
                        ).all()
                        symbol_by_stock_id = {s.id: s.symbol for s in stocks}

                    articles_by_rec = await self._fetch_articles_for_batch(
                        db, batch, news_source, symbol_by_stock_id
                    )

                    batch_processed = 0
                    for rec in batch:
                        if max_to_process is not None and this_run_count >= max_to_process:
                            break

                        symbol = None
                        if rec.stock is not None and getattr(rec.stock, "symbol", None):
                            symbol = rec.stock.symbol
                        else:
                            symbol = symbol_by_stock_id.get(rec.stock_id)

                        if not symbol:
                            logger.warning(
                                "Backfill missing symbol for analysis_history id=%s "
                                "stock_id=%s; tagging UNKNOWN",
                                rec.id,
                                rec.stock_id,
                            )

                        market_regime = None
                        if rec.market_state:
                            market_regime = {"market_state": rec.market_state}

                        situation_tags = determine_situation_tags(
                            symbol=symbol,
                            recommendation=rec.recommendation,
                            sentiment_score=rec.sentiment_score,
                            articles=articles_by_rec.get(rec.id, []),
                            market_regime=market_regime,
                        )

                        rec.situation_tags = situation_tags
                        last_processed_id = rec.id
                        batch_processed += 1
                        this_run_count += 1
                        cumulative_processed += 1

                    # H1: increment by rows actually tagged, not len(batch)
                    progress_db = await db.get(BackfillProgress, progress_id)
                    if progress_db:
                        progress_db.last_processed_id = last_processed_id
                        progress_db.processed_count = cumulative_processed
                        progress_db.updated_at = _utc_now()

                        # Short page (fully consumed) means no more rows after this cursor
                        no_more_rows = (
                            batch_processed == len(batch) and len(batch) < batch_size
                        )
                        caught_up = (
                            progress_db.total_count > 0
                            and progress_db.processed_count >= progress_db.total_count
                        )
                        if no_more_rows or caught_up:
                            progress_db.status = "COMPLETED"
                        # else: leave RUNNING (e.g. limit mid-dataset for clean resume)

                        status_now = progress_db.status
                        await db.commit()
                    else:
                        status_now = "RUNNING"

                logger.info(
                    "Backfill job %s batch done: this_run=%s cumulative=%s "
                    "last_processed_id=%s status=%s",
                    job_id,
                    this_run_count,
                    cumulative_processed,
                    last_processed_id,
                    status_now,
                )

                if status_now == "COMPLETED":
                    break
                if max_to_process is not None and this_run_count >= max_to_process:
                    # Partial run (limit) — leave RUNNING for resume
                    break

                await asyncio.sleep(delay_seconds)

            return this_run_count

        except asyncio.CancelledError:
            await self._mark_job_status(
                progress_id,
                "FAILED",
                last_processed_id=last_processed_id,
                processed_count=cumulative_processed,
            )
            logger.warning("Backfill job %s cancelled; status=FAILED", job_id)
            raise
        except RuntimeError:
            # Concurrency / precondition errors — do not force FAILED on other jobs
            raise
        except Exception:
            await self._mark_job_status(
                progress_id,
                "FAILED",
                last_processed_id=last_processed_id,
                processed_count=cumulative_processed,
            )
            logger.exception("Backfill job %s failed; status=FAILED", job_id)
            raise
        finally:
            try:
                if prev_sigint is not None:
                    signal.signal(signal.SIGINT, prev_sigint)
                if prev_sigterm is not None and hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, prev_sigterm)
            except (ValueError, OSError):
                pass
            await lease.release()

    async def write_distribution_report(self, output_dir: str | None = None) -> str:
        """Tag distribution via keyset paging (H5: no full-table materialization)."""
        from ..config import settings
        from ..config.settings import ROOT_DIR

        if output_dir:
            reports_dir = Path(output_dir)
        else:
            reports_dir = Path(settings.governance_reports_dir)
            if not reports_dir.is_absolute():
                reports_dir = ROOT_DIR / reports_dir

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        report_file = reports_dir / f"taxonomy_distribution_{stamp}.md"
        latest_file = reports_dir / "taxonomy_distribution_report.md"

        tag_counts = {tag: 0 for tag in _ALLOWED_TAGS}
        total_records = 0
        last_id = 0

        async with AsyncSessionLocal() as db:
            while True:
                stmt = (
                    select(AnalysisHistory.id, AnalysisHistory.situation_tags)
                    .where(AnalysisHistory.id > last_id)
                    .order_by(AnalysisHistory.id.asc())
                    .limit(_REPORT_PAGE_SIZE)
                )
                page = (await db.execute(stmt)).all()
                if not page:
                    break
                for row_id, tags in page:
                    last_id = row_id
                    total_records += 1
                    if not tags:
                        tag_counts["UNKNOWN"] += 1
                        continue
                    for tag in tags:
                        if tag in tag_counts:
                            tag_counts[tag] += 1
                        else:
                            tag_counts[tag] = 1

        # SC-004: share of records containing each tag (multi-tag rows can sum > 100%)
        percentages: dict[str, float] = {}
        for tag, count in tag_counts.items():
            percentages[tag] = (count / total_records * 100) if total_records > 0 else 0.0

        health_lines: list[str] = []
        health_ok = True
        if total_records > 0:
            unknown_pct = percentages.get("UNKNOWN", 0.0)
            if unknown_pct >= _SC004_MAX_UNKNOWN_PCT:
                health_ok = False
                health_lines.append(
                    f"- FAIL: UNKNOWN is {unknown_pct:.2f}% of records "
                    f"(target < {_SC004_MAX_UNKNOWN_PCT:.0f}%)."
                )
            else:
                health_lines.append(
                    f"- PASS: UNKNOWN is {unknown_pct:.2f}% of records "
                    f"(target < {_SC004_MAX_UNKNOWN_PCT:.0f}%)."
                )

            for tag, pct in percentages.items():
                if tag == "UNKNOWN":
                    continue
                if pct > _SC004_MAX_SINGLE_TAG_PCT:
                    health_ok = False
                    health_lines.append(
                        f"- FAIL: {tag} is {pct:.2f}% of records "
                        f"(target ≤ {_SC004_MAX_SINGLE_TAG_PCT:.0f}% excluding UNKNOWN)."
                    )
            if health_ok and not any(line.startswith("- FAIL") for line in health_lines):
                # Ensure at least the single-tag check summary is visible when all pass
                health_lines.append(
                    f"- PASS: No non-UNKNOWN tag exceeds {_SC004_MAX_SINGLE_TAG_PCT:.0f}% of records."
                )
        else:
            health_lines.append("- N/A: No recommendations analysed; SC-004 not evaluated.")

        health_status = "HEALTHY" if health_ok and total_records > 0 else (
            "N/A" if total_records == 0 else "NEEDS_ATTENTION"
        )

        print("\nSituation Tag Distribution:")
        print(f"{'Situation Tag':<30} | {'Count':<10} | {'Percentage':<10}")
        print("-" * 58)
        for tag, count in tag_counts.items():
            print(f"{tag:<30} | {count:<10} | {percentages[tag]:.2f}%")
        print(f"\nTotal Recommendations Analysed: {total_records}")
        print(f"SC-004 Health Status: {health_status}")
        for line in health_lines:
            print(line)
        print()

        md_content = f"""# Situation Tag Distribution Report
Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
Total Recommendations Analysed: {total_records}

## SC-004 Health Status: {health_status}

"""
        for line in health_lines:
            md_content += f"{line}\n"
        md_content += """
| Situation Tag | Count | Percentage |
| :--- | :--- | :--- |
"""
        for tag, count in tag_counts.items():
            md_content += f"| {tag} | {count} | {percentages[tag]:.2f}% |\n"

        report_file.write_text(md_content, encoding="utf-8")
        latest_file.write_text(md_content, encoding="utf-8")
        logger.info(
            "Distribution report written path=%s total_records=%s sc004_status=%s",
            report_file,
            total_records,
            health_status,
        )
        return str(report_file)
