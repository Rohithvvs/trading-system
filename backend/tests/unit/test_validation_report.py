"""Unit tests for FEAT-012 Challenger Validation Report.

Spec: specs/012-validation-minimal-promotion/spec.md
Covers FR-001..FR-004, SC-001, US1 acceptance scenarios, edge cases.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisHistory
from app.models.live_trading import LiveOrder
from app.models.paper_trading import PaperOrder
from app.models.stock import WatchedStock
from app.services.validation_report import ValidationReportGenerator


REQUIRED_REPORT_FIELDS = {
    "rule_id",
    "generated_at",
    "window_start",
    "window_end",
    "total_recommendations_analyzed",
    "total_articles_processed",
    "total_articles_deduplicated",
    "deduplication_rate",
    "average_sentiment_score",
    "total_signals_evaluated",
    "false_positive_count",
    "false_positive_rate",
    "baseline_false_positive_rate",
    "baseline_sentiment_score",
    "status",
    "data_incomplete",
    "incomplete_data_warning",
    "available_data_span_days",
}


async def _seed_stock(session: AsyncSession, symbol: str = "RELIANCE-EQ") -> WatchedStock:
    stock = WatchedStock(symbol=symbol, display_name=symbol.replace("-EQ", ""))
    session.add(stock)
    await session.flush()
    return stock


def _shadow(
    original: int, kept: int, removed: int | None = None, nested: bool = True
) -> dict:
    removed = original - kept if removed is None else removed
    payload = {
        "original_news_count": original,
        "kept_news_count": kept,
        "removed_news_count": removed,
    }
    if nested:
        return {"news_dedup": payload}
    return payload


async def _hist(
    session: AsyncSession,
    stock_id: int,
    *,
    recommendation: str,
    sentiment: float,
    created_at: datetime,
    shadow_outputs: dict | None,
) -> AnalysisHistory:
    hist = AnalysisHistory(
        stock_id=stock_id,
        mode="test",
        technical_score=0.5,
        sentiment_score=sentiment,
        backtest_score=0.5,
        recommendation=recommendation,
        confidence=0.9,
        reasoning="test",
        created_at=created_at,
        shadow_outputs=shadow_outputs,
    )
    session.add(hist)
    await session.flush()
    return hist


# ---------------------------------------------------------------------------
# US1 — empty / schema / core metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_report_empty(async_db_session: AsyncSession, tmp_path: Path) -> None:
    """Graceful empty-window report: zeros and FAIL status when no data."""
    with patch.object(ValidationReportGenerator, "__init__", lambda self, db: None):
        generator = ValidationReportGenerator.__new__(ValidationReportGenerator)
        generator.db = async_db_session
        generator.reports_dir = tmp_path

        report = await generator.generate_report("news_dedup")

    assert report["rule_id"] == "news_dedup"
    assert report["total_recommendations_analyzed"] == 0
    assert report["total_articles_processed"] == 0
    assert report["total_articles_deduplicated"] == 0
    assert report["deduplication_rate"] == 0.0
    assert report["false_positive_rate"] == 0.0
    assert report["status"] == "FAIL"
    assert report["data_incomplete"] is True
    assert report["incomplete_data_warning"] is not None
    assert "incomplete" in str(report["incomplete_data_warning"]).lower()
    assert REQUIRED_REPORT_FIELDS.issubset(report.keys())


@pytest.mark.asyncio
async def test_validation_report_calculations(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Aggregates metrics and false-positive rate from shadow + filled live orders."""
    stock1 = await _seed_stock(async_db_session, "RELIANCE-EQ")
    stock2 = await _seed_stock(async_db_session, "INFY-EQ")
    now = datetime.now(timezone.utc)

    await _hist(
        async_db_session,
        stock1.id,
        recommendation="BUY",
        sentiment=0.8,
        created_at=now - timedelta(days=5),
        shadow_outputs=_shadow(50, 40),
    )
    await _hist(
        async_db_session,
        stock2.id,
        recommendation="SELL",
        sentiment=-0.6,
        created_at=now - timedelta(days=2),
        shadow_outputs=_shadow(20, 15),
    )
    await _hist(
        async_db_session,
        stock1.id,
        recommendation="HOLD",
        sentiment=0.0,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(10, 10),
    )

    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("10"),
            filled_qty=Decimal("10"),
            status="FILLED",
            idempotency_key="key1",
            created_at=now - timedelta(days=5) + timedelta(hours=2),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 3
    assert report["total_articles_processed"] == 80
    assert report["total_articles_deduplicated"] == 15
    assert report["deduplication_rate"] == 0.1875
    assert report["average_sentiment_score"] == pytest.approx(0.0667, abs=1e-3)
    assert report["total_signals_evaluated"] == 2
    assert report["false_positive_count"] == 1
    assert report["false_positive_rate"] == 0.5
    assert report["status"] == "FAIL"  # FP 0.50 > baseline 0.15


@pytest.mark.asyncio
async def test_validation_report_status_pass(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """PASS when dedup rate in [5%, 40%] and FP rate at or below baseline."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_pass",
            created_at=now - timedelta(days=1) + timedelta(minutes=30),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["deduplication_rate"] == 0.20
    assert report["false_positive_rate"] == 0.0
    assert report["status"] == "PASS"


# ---------------------------------------------------------------------------
# FR-004 — machine-readable JSON + human-readable Markdown persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_persists_json_and_markdown(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Report writes challenger_report_news_dedup.json and .md under reports dir."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.4,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_files",
            created_at=now - timedelta(hours=12),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    json_path = tmp_path / "challenger_report_news_dedup.json"
    md_path = tmp_path / "challenger_report_news_dedup.md"
    assert json_path.exists()
    assert md_path.exists()

    disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert disk["rule_id"] == report["rule_id"]
    assert disk["status"] == report["status"]
    assert REQUIRED_REPORT_FIELDS.issubset(disk.keys())

    md = md_path.read_text(encoding="utf-8")
    assert "Challenger Validation Report" in md
    assert "Deduplication Rate" in md
    assert "False-Positive Rate" in md
    assert str(report["status"]) in md


# ---------------------------------------------------------------------------
# FR-003 — false-positive correlation (live, paper, window, status)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paper_order_fill_counts_as_true_positive(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """A matching FILLED paper order within 24h prevents FP classification."""
    stock = await _seed_stock(async_db_session, "TCS-EQ")
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=1)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="SELL",
        sentiment=-0.3,
        created_at=created,
        shadow_outputs=_shadow(20, 16),
    )
    async_db_session.add(
        PaperOrder(
            account_id=1,
            symbol="TCS-EQ",
            side="SELL",
            order_type="MARKET",
            qty=Decimal("5"),
            status="FILLED",
            idempotency_key="paper_fp_ok",
            created_at=created + timedelta(hours=3),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_signals_evaluated"] == 1
    assert report["false_positive_count"] == 0
    assert report["false_positive_rate"] == 0.0


@pytest.mark.asyncio
async def test_order_outside_24h_window_is_false_positive(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Filled order after the 24h correlation window still counts as FP."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=2)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=created,
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_late",
            created_at=created + timedelta(hours=25),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["false_positive_count"] == 1
    assert report["false_positive_rate"] == 1.0


@pytest.mark.asyncio
async def test_non_filled_order_does_not_clear_false_positive(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Non-FILLED live orders do not clear a false positive."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=1)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=created,
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("0"),
            status="CANCELLED",
            idempotency_key="key_cancel",
            created_at=created + timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["false_positive_count"] == 1


@pytest.mark.asyncio
async def test_hold_recommendations_excluded_from_fp_signals(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """HOLD recommendations are analyzed for volume but not FP signal evaluation."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    await _hist(
        async_db_session,
        stock.id,
        recommendation="HOLD",
        sentiment=0.1,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(10, 8),
    )

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 1
    assert report["total_signals_evaluated"] == 0
    assert report["false_positive_count"] == 0
    assert report["false_positive_rate"] == 0.0


# ---------------------------------------------------------------------------
# Window / structure edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_records_outside_14_day_window_excluded(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Analysis older than 14 days is excluded from the report window."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=20),
        shadow_outputs=_shadow(100, 50),
    )
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=3),
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_window",
            created_at=now - timedelta(days=3) + timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 1
    assert report["total_articles_processed"] == 10
    assert report["total_articles_deduplicated"] == 2


@pytest.mark.asyncio
async def test_flat_shadow_outputs_structure_supported(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Flat (non-nested) shadow_outputs keys are accepted for metric extraction."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.2,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(10, 8, nested=False),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_flat",
            created_at=now - timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 1
    assert report["total_articles_processed"] == 10
    assert report["total_articles_deduplicated"] == 2


@pytest.mark.asyncio
async def test_missing_or_invalid_shadow_outputs_skipped(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Histories without usable news_dedup telemetry are not counted."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=None,
    )
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs={"other_feature": {"foo": 1}},
    )
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(5, 4),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_skip",
            created_at=now - timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 1
    assert report["total_articles_processed"] == 5


# ---------------------------------------------------------------------------
# PASS/FAIL boundary conditions (SC-001)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_rate_below_5_percent_fails(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Dedup rate under 5% yields FAIL even with excellent FP rate."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    # 1 removed of 100 => 1%
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(100, 99),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_low_dedup",
            created_at=now - timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["deduplication_rate"] == 0.01
    assert report["false_positive_rate"] == 0.0
    assert report["status"] == "FAIL"


@pytest.mark.asyncio
async def test_dedup_rate_above_40_percent_fails(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Dedup rate above 40% yields FAIL even with excellent FP rate."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    # 50 removed of 100 => 50%
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(100, 50),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_high_dedup",
            created_at=now - timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["deduplication_rate"] == 0.5
    assert report["status"] == "FAIL"


@pytest.mark.asyncio
async def test_dedup_rate_exactly_5_percent_passes(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Exactly 5% deduplication rate is within the healthy inclusive range."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)

    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=2),
        shadow_outputs=_shadow(100, 95),  # 5 removed
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_bound_5",
            created_at=now - timedelta(days=2) + timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")
    assert report["deduplication_rate"] == 0.05
    assert report["status"] == "PASS"


@pytest.mark.asyncio
async def test_dedup_rate_exactly_40_percent_passes(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Exactly 40% deduplication rate is within the healthy inclusive range."""
    stock = await _seed_stock(async_db_session, "WIPRO-EQ")
    now = datetime.now(timezone.utc)
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=1),
        shadow_outputs=_shadow(100, 60),  # 40 removed
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="WIPRO-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_exact_40",
            created_at=now - timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    # Other symbols may exist in session from prior tests? Each async_db_session is
    # fresh in-memory per fixture — only this stock exists here.
    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["deduplication_rate"] == 0.40
    assert report["status"] == "PASS"


@pytest.mark.asyncio
async def test_baseline_metrics_loaded_into_report(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Report includes baseline FP and sentiment from configuration defaults/file."""
    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert "baseline_false_positive_rate" in report
    assert "baseline_sentiment_score" in report
    assert report["baseline_false_positive_rate"] == pytest.approx(0.15, abs=1e-4)
    assert report["baseline_sentiment_score"] == pytest.approx(0.65, abs=1e-4)


@pytest.mark.asyncio
async def test_baseline_load_defaults_when_file_missing(tmp_path: Path) -> None:
    """Missing baseline file falls back to documented default rates."""
    generator = ValidationReportGenerator.__new__(ValidationReportGenerator)
    generator.reports_dir = tmp_path

    with patch("app.services.validation_report.ROOT_DIR", tmp_path):
        baseline = generator._load_baseline_metrics()

    assert baseline["false_positive_rate"] == 0.15
    assert baseline["average_sentiment_score"] == 0.65


@pytest.mark.asyncio
async def test_incomplete_window_still_computes_available_metrics(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Edge: sparse (<14 days) shadow data still yields metrics for available rows.

    Spec also requires an incomplete-data warning field; that is not yet present
    in the report payload (implementation gap — reported, not fixed).
    """
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    # Only 2 days of data
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.7,
        created_at=now - timedelta(days=2),
        shadow_outputs=_shadow(20, 16),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_sparse",
            created_at=now - timedelta(days=2) + timedelta(hours=2),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["total_recommendations_analyzed"] == 1
    assert report["deduplication_rate"] == 0.20
    assert report["window_start"] is not None
    assert report["window_end"] is not None
    assert report["data_incomplete"] is True
    assert report["incomplete_data_warning"] is not None
    assert "14-day" in str(report["incomplete_data_warning"])
    assert report["available_data_span_days"] is not None
    assert float(report["available_data_span_days"]) < 14.0


@pytest.mark.asyncio
async def test_full_14_day_window_marks_data_complete(
    async_db_session: AsyncSession, tmp_path: Path
) -> None:
    """Shadow data spanning ~14 days is treated as complete (no warning)."""
    stock = await _seed_stock(async_db_session)
    now = datetime.now(timezone.utc)
    # Near the start of the 14-day window
    await _hist(
        async_db_session,
        stock.id,
        recommendation="BUY",
        sentiment=0.5,
        created_at=now - timedelta(days=13, hours=12),
        shadow_outputs=_shadow(10, 8),
    )
    async_db_session.add(
        LiveOrder(
            account_id=1,
            symbol="RELIANCE-EQ",
            side="BUY",
            order_type="MARKET",
            requested_qty=Decimal("1"),
            filled_qty=Decimal("1"),
            status="FILLED",
            idempotency_key="key_full_window",
            created_at=now - timedelta(days=13) + timedelta(hours=1),
        )
    )
    await async_db_session.flush()

    generator = ValidationReportGenerator(async_db_session)
    generator.reports_dir = tmp_path
    report = await generator.generate_report("news_dedup")

    assert report["data_incomplete"] is False
    assert report["incomplete_data_warning"] is None
    assert report["available_data_span_days"] is not None
    assert float(report["available_data_span_days"]) >= 13.0


@pytest.mark.asyncio
async def test_markdown_summary_contains_key_metrics() -> None:
    """Markdown builder includes operational and quality metric labels."""
    generator = ValidationReportGenerator.__new__(ValidationReportGenerator)
    data = {
        "rule_id": "news_dedup",
        "generated_at": "2026-07-21T00:00:00+00:00",
        "window_start": "2026-07-07T00:00:00+00:00",
        "window_end": "2026-07-21T00:00:00+00:00",
        "status": "PASS",
        "deduplication_rate": 0.2,
        "false_positive_rate": 0.1,
        "baseline_false_positive_rate": 0.15,
        "average_sentiment_score": 0.5,
        "baseline_sentiment_score": 0.65,
        "total_recommendations_analyzed": 10,
        "total_articles_processed": 100,
        "total_articles_deduplicated": 20,
        "total_signals_evaluated": 8,
        "false_positive_count": 1,
        "data_incomplete": True,
        "incomplete_data_warning": (
            "WARNING: Shadow data is incomplete for the 14-day analysis window. "
            "Metrics are calculated for the available time window only."
        ),
        "available_data_span_days": 5.0,
    }
    md = generator._build_markdown_summary(data)
    assert "PASS" in md
    assert "20.00%" in md
    assert "Total Recommendations Analyzed" in md
    assert "False Positive Count" in md
    assert "incomplete" in md.lower()
    assert "Data Incomplete" in md
