from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..config.settings import ROOT_DIR
from ..models.analysis import AnalysisHistory
from ..models.live_trading import LiveOrder
from ..models.paper_trading import PaperOrder
from ..models.stock import WatchedStock

logger = logging.getLogger("app.services")

ANALYSIS_WINDOW_DAYS = 14
INCOMPLETE_DATA_WARNING = (
    "WARNING: Shadow data is incomplete for the 14-day analysis window. "
    "Metrics are calculated for the available time window only."
)


class ValidationReportGenerator:
    """Generates the Challenger Validation Report for news deduplication.

    Analyses the last 14 days of shadow execution data and correlates signals
    with executed orders to calculate false-positive rates.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Resolve output directory
        from ..config.settings import ROOT_DIR
        reports_dir = Path(settings.governance_reports_dir)
        if not reports_dir.is_absolute():
            self.reports_dir = ROOT_DIR / reports_dir
        else:
            self.reports_dir = reports_dir

    def _load_baseline_metrics(self) -> dict[str, float]:
        """Load Sprint 1 baseline metrics from baseline_v1.0.json."""
        baseline_file = ROOT_DIR / "baseline_v1.0.json"
        defaults = {
            "false_positive_rate": 0.15,
            "average_sentiment_score": 0.65,
        }
        if not baseline_file.exists():
            logger.info("Baseline metrics file %s does not exist; using defaults", baseline_file)
            return defaults

        try:
            with open(baseline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                news_dedup_data = data.get("news_dedup", {})
                return {
                    "false_positive_rate": float(
                        news_dedup_data.get("false_positive_rate", defaults["false_positive_rate"])
                    ),
                    "average_sentiment_score": float(
                        news_dedup_data.get(
                            "average_sentiment_score", defaults["average_sentiment_score"]
                        )
                    ),
                }
        except Exception as e:
            logger.error("Failed to load baseline metrics from %s: %s", baseline_file, e)
            return defaults

    @staticmethod
    def _normalize_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _safe_int(value: object) -> int | None:
        """Coerce telemetry counters to non-negative int; None if unusable."""
        if value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number < 0:
            return None
        return number

    def _assess_data_completeness(
        self,
        matched_histories: list[tuple[AnalysisHistory, str]],
        now: datetime,
        start_date: datetime,
    ) -> tuple[bool, str | None, float | None]:
        """Detect incomplete shadow coverage for the 14-day window.

        Returns (data_incomplete, warning_or_none, available_span_days_or_none).
        Incomplete when no shadow rows exist, or the earliest observation does not
        reach the start of the analysis window (fewer than 14 days of data).
        """
        if not matched_histories:
            return True, INCOMPLETE_DATA_WARNING, None

        earliest = min(
            self._normalize_utc(history.created_at) for history, _ in matched_histories
        )
        span = now - earliest
        available_span_days = round(span.total_seconds() / 86400.0, 4)
        # Full coverage requires earliest sample within the first day of the window.
        # Query uses created_at >= start_date, so earliest is never before start_date.
        if earliest > start_date + timedelta(days=1) or span < timedelta(
            days=ANALYSIS_WINDOW_DAYS - 1
        ):
            return True, INCOMPLETE_DATA_WARNING, available_span_days
        return False, None, available_span_days

    async def _has_matching_fill(
        self, symbol: str, side: str, created_at: datetime
    ) -> bool | None:
        """Return True/False if correlation succeeded, None if lookup failed.

        Lookup failures must not abort report generation; the signal is excluded
        from FP evaluation when correlation cannot be completed safely.
        """
        window_end = created_at + timedelta(hours=24)
        try:
            live_stmt = (
                select(LiveOrder.id)
                .where(
                    LiveOrder.symbol == symbol,
                    LiveOrder.side == side,
                    LiveOrder.status == "FILLED",
                    LiveOrder.created_at >= created_at,
                    LiveOrder.created_at <= window_end,
                )
                .limit(1)
            )
            live_res = await self.db.execute(live_stmt)
            if live_res.scalar_one_or_none() is not None:
                return True

            paper_stmt = (
                select(PaperOrder.id)
                .where(
                    PaperOrder.symbol == symbol,
                    PaperOrder.side == side,
                    PaperOrder.status == "FILLED",
                    PaperOrder.created_at >= created_at,
                    PaperOrder.created_at <= window_end,
                )
                .limit(1)
            )
            paper_res = await self.db.execute(paper_stmt)
            return paper_res.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(
                "Order correlation failed for %s %s at %s: %s",
                symbol,
                side,
                created_at.isoformat(),
                e,
            )
            return None

    async def generate_report(self, rule_id: str = "news_dedup") -> dict[str, object]:
        """Compile validation metrics for the rule and persist JSON and Markdown reports."""
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=ANALYSIS_WINDOW_DAYS)

        # 1. Fetch analysis histories from the last 14 days
        # Join with WatchedStock to resolve the symbol name
        stmt = (
            select(AnalysisHistory, WatchedStock.symbol)
            .join(WatchedStock, AnalysisHistory.stock_id == WatchedStock.id)
            .where(AnalysisHistory.created_at >= start_date)
            .order_by(AnalysisHistory.created_at.desc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        matched_histories: list[tuple[AnalysisHistory, str]] = []
        total_articles_processed = 0
        total_articles_deduplicated = 0
        sentiment_scores: list[float] = []

        # 2. Extract news_dedup telemetry
        for history, symbol in rows:
            shadow_outputs = history.shadow_outputs
            if not shadow_outputs or not isinstance(shadow_outputs, dict):
                continue

            # Check both flat and nested key structures for news_dedup
            news_dedup = shadow_outputs.get("news_dedup")
            if isinstance(news_dedup, dict):
                original = self._safe_int(news_dedup.get("original_news_count"))
                kept = self._safe_int(news_dedup.get("kept_news_count"))
            else:
                original = self._safe_int(shadow_outputs.get("original_news_count"))
                kept = self._safe_int(shadow_outputs.get("kept_news_count"))

            if original is None or kept is None:
                continue

            matched_histories.append((history, symbol))
            total_articles_processed += original
            total_articles_deduplicated += max(0, original - kept)
            if history.sentiment_score is not None:
                try:
                    sentiment_scores.append(float(history.sentiment_score))
                except (TypeError, ValueError):
                    logger.warning(
                        "Skipping non-numeric sentiment_score on analysis id=%s",
                        getattr(history, "id", "?"),
                    )

        total_recommendations = len(matched_histories)
        dedup_rate = 0.0
        if total_articles_processed > 0:
            dedup_rate = total_articles_deduplicated / total_articles_processed

        avg_sentiment = 0.0
        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)

        # 3. Calculate False Positive Rate
        total_signals = 0
        false_positive_count = 0
        correlation_errors = 0

        for history, symbol in matched_histories:
            rec = history.recommendation
            if not rec or rec.upper() not in ("BUY", "SELL"):
                continue

            side = rec.upper()
            created_at = self._normalize_utc(history.created_at)
            fill_match = await self._has_matching_fill(symbol, side, created_at)
            if fill_match is None:
                correlation_errors += 1
                continue

            total_signals += 1
            if not fill_match:
                false_positive_count += 1

        fp_rate = 0.0
        if total_signals > 0:
            fp_rate = false_positive_count / total_signals

        # 4. Load baseline metrics & evaluate PASS/FAIL status
        baseline = self._load_baseline_metrics()
        baseline_fp_rate = baseline["false_positive_rate"]
        baseline_sentiment = baseline["average_sentiment_score"]

        # PASS Criteria: dedup rate between 5% and 40%, and FP rate not worse than baseline
        # (Must also have at least some recommendations analyzed to verify logic works)
        is_dedup_healthy = 0.05 <= dedup_rate <= 0.40
        is_fp_stable = fp_rate <= baseline_fp_rate

        status = "FAIL"
        if total_recommendations > 0 and is_dedup_healthy and is_fp_stable:
            status = "PASS"

        data_incomplete, incomplete_warning, available_span_days = self._assess_data_completeness(
            matched_histories, now, start_date
        )
        if data_incomplete:
            logger.warning(
                "Validation report for %s: incomplete shadow data (span_days=%s)",
                rule_id,
                available_span_days,
            )
        if correlation_errors:
            logger.warning(
                "Validation report for %s: excluded %s signals due to order-correlation errors",
                rule_id,
                correlation_errors,
            )

        # Compile report payload
        report_data: dict[str, object] = {
            "rule_id": rule_id,
            "generated_at": now.isoformat(),
            "window_start": start_date.isoformat(),
            "window_end": now.isoformat(),
            "total_recommendations_analyzed": total_recommendations,
            "total_articles_processed": total_articles_processed,
            "total_articles_deduplicated": total_articles_deduplicated,
            "deduplication_rate": round(dedup_rate, 4),
            "average_sentiment_score": round(avg_sentiment, 4),
            "total_signals_evaluated": total_signals,
            "false_positive_count": false_positive_count,
            "false_positive_rate": round(fp_rate, 4),
            "baseline_false_positive_rate": round(baseline_fp_rate, 4),
            "baseline_sentiment_score": round(baseline_sentiment, 4),
            "status": status,
            "data_incomplete": data_incomplete,
            "incomplete_data_warning": incomplete_warning,
            "available_data_span_days": available_span_days,
            "correlation_errors": correlation_errors,
        }

        # 5. Persist reports (best-effort; metrics still returned to CLI/stdout)
        self._save_report_files(report_data)
        return report_data

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        """Write via temp file + replace to avoid truncated artifacts on crash."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, path)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise

    def _save_report_files(self, data: dict[str, object]) -> None:
        """Write reports in both JSON and Markdown formats (atomic where possible)."""
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)

            json_file = self.reports_dir / "challenger_report_news_dedup.json"
            self._atomic_write_text(json_file, json.dumps(data, indent=2))

            md_file = self.reports_dir / "challenger_report_news_dedup.md"
            self._atomic_write_text(md_file, self._build_markdown_summary(data))

            logger.info("Saved validation report to %s", self.reports_dir)
        except Exception as e:
            logger.error("Failed to write validation report files: %s", e)

    def _build_markdown_summary(self, d: dict[str, object]) -> str:
        """Construct the human-readable Markdown summary representation."""
        warning_block = ""
        if d.get("data_incomplete") and d.get("incomplete_data_warning"):
            warning_block = f"\n> **{d['incomplete_data_warning']}**\n"
            if d.get("available_data_span_days") is not None:
                warning_block += (
                    f"> Available shadow data span: **{d['available_data_span_days']}** days "
                    f"(required: {ANALYSIS_WINDOW_DAYS} days)\n"
                )

        return f"""# Challenger Validation Report: {d['rule_id']}

Generated: {d['generated_at']}
Analysis Window: {d['window_start']} to {d['window_end']}
{warning_block}
## Summary Status: {d['status']}

| Metric | Calculated Value | Reference Baseline / Target | Status |
| :--- | :--- | :--- | :--- |
| **Deduplication Rate** | {float(d['deduplication_rate'])*100:.2f}% | 5.00% - 40.00% | {'✓ Healthy' if 0.05 <= d['deduplication_rate'] <= 0.40 else '✗ Out of Range'} |
| **False-Positive Rate** | {float(d['false_positive_rate'])*100:.2f}% | <= {float(d['baseline_false_positive_rate'])*100:.2f}% | {'✓ Stable / Improved' if d['false_positive_rate'] <= d['baseline_false_positive_rate'] else '✗ Degraded'} |
| **Avg Sentiment Score** | {d['average_sentiment_score']:.4f} | {d['baseline_sentiment_score']:.4f} (Baseline) | N/A |

## Operational Volume Metrics
* **Total Recommendations Analyzed**: {d['total_recommendations_analyzed']}
* **Total Articles Processed**: {d['total_articles_processed']}
* **Total Articles Deduplicated**: {d['total_articles_deduplicated']}
* **Total Signals Evaluated**: {d['total_signals_evaluated']}
* **False Positive Count**: {d['false_positive_count']}
* **Data Incomplete**: {d.get('data_incomplete', False)}
"""
