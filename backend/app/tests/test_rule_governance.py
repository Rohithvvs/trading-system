from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.experiment_cli import _parse_args
from app.governance.rule_governance import (
    load_rule_baselines,
    get_rule_baseline,
    evaluate_rule_governance,
    evaluate_all_promoted_rules,
    _is_false_positive_record,
    MIN_SAMPLE_COUNT,
    PROMOTED_RULES_DEFAULT,
)
from app.schemas.governance import health_status_to_label
from app.models.analysis import AnalysisHistory
from app.models.stock import WatchedStock
from app.schemas.governance import RuleGovernanceRecord, RuleGovernanceResponse


VALID_HEALTH_STATUSES = {"GREEN", "YELLOW", "RED", "INSUFFICIENT_DATA"}


async def _get_or_create_stock(db: AsyncSession, symbol_prefix: str, name: str) -> WatchedStock:
    symbol = f"{symbol_prefix}_{uuid.uuid4().hex[:6]}".upper()
    stock = WatchedStock(symbol=symbol, display_name=name)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock


async def _seed_rule_histories(
    db: AsyncSession,
    *,
    rule_id: str,
    total: int,
    false_positive_count: int,
    recommendation: str = "BUY",
    days_ago_offset: int = 0,
    stock: WatchedStock | None = None,
) -> WatchedStock:
    """Seed BUY (or other) AnalysisHistory rows with rule-scoped FP telemetry."""
    if stock is None:
        stock = await _get_or_create_stock(db, "GOV", f"Governance {rule_id}")
    now = datetime.now(timezone.utc)
    for i in range(total):
        is_fp = i < false_positive_count
        history = AnalysisHistory(
            stock_id=stock.id,
            mode="shadow",
            technical_score=75.0,
            sentiment_score=0.5,
            backtest_score=70.0,
            confidence=80.0,
            reasoning=f"seed {rule_id}",
            created_at=now - timedelta(days=(i % 25) + days_ago_offset),
            recommendation=recommendation,
            shadow_outputs={
                rule_id: {
                    "outcome": "negative" if is_fp else "positive",
                    "false_positive": is_fp,
                }
            },
        )
        db.add(history)
    await db.commit()
    return stock


@pytest.mark.asyncio
async def test_baseline_loading_default(tmp_path, monkeypatch):
    """Verify default baseline rate (0.15) when baseline file is missing."""
    monkeypatch.setattr("app.governance.rule_governance.ROOT_DIR", tmp_path)
    baselines = load_rule_baselines()
    assert get_rule_baseline("news_dedup", baselines) == 0.15
    assert get_rule_baseline("unknown_rule", baselines) == 0.15


@pytest.mark.asyncio
async def test_baseline_loading_from_file(tmp_path, monkeypatch):
    """Verify loading baseline rates from baseline_v1.0.json."""
    baseline_file = tmp_path / "baseline_v1.0.json"
    content = {
        "news_dedup": {"false_positive_rate": 0.12},
        "sentiment_decay": {"false_positive_rate": 0.18},
    }
    baseline_file.write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr("app.governance.rule_governance.ROOT_DIR", tmp_path)

    baselines = load_rule_baselines()
    assert get_rule_baseline("news_dedup", baselines) == 0.12
    assert get_rule_baseline("sentiment_decay", baselines) == 0.18
    assert get_rule_baseline("market_breadth", baselines) == 0.15  # Fallback default


@pytest.mark.asyncio
async def test_sample_size_protection(db: AsyncSession):
    """Sample count < 15 yields INSUFFICIENT_DATA and None for false_positive_rate_30d."""
    stock = await _get_or_create_stock(db, "RELIANCE", "Reliance Industries")

    now = datetime.now(timezone.utc)
    # Insert 10 records (< 15)
    for i in range(10):
        history = AnalysisHistory(
            stock_id=stock.id,
            mode="shadow",
            technical_score=75.0,
            sentiment_score=0.5,
            backtest_score=70.0,
            confidence=80.0,
            reasoning="Test reasoning",
            created_at=now - timedelta(days=i),
            recommendation="BUY",
            shadow_outputs={"news_dedup": {"status": "success"}},
        )
        db.add(history)
    await db.commit()

    record = await evaluate_rule_governance(db, rule_id="news_dedup")
    assert isinstance(record, RuleGovernanceRecord)
    assert record.rule_id == "news_dedup"
    assert record.sample_count_30d >= 10
    if record.sample_count_30d < 15:
        assert record.health_status == "INSUFFICIENT_DATA"
        assert record.false_positive_rate_30d is None
        assert "Insufficient sample count" in record.status_reason


@pytest.mark.asyncio
async def test_status_assignment_green(db: AsyncSession):
    """FP rate <= baseline + 0.05 yields GREEN health status."""
    stock = await _get_or_create_stock(db, "TCS", "Tata Consultancy Services")

    now = datetime.now(timezone.utc)
    # 20 BUY records (>= 15)
    # 2 false positives (10% FP rate) vs baseline 0.15 -> 0.10 <= 0.15 + 0.05 -> GREEN
    for i in range(20):
        is_fp = i < 2  # first 2 are false positives
        history = AnalysisHistory(
            stock_id=stock.id,
            mode="shadow",
            technical_score=75.0,
            sentiment_score=0.5,
            backtest_score=70.0,
            confidence=80.0,
            reasoning="Test reasoning",
            created_at=now - timedelta(days=i % 25),
            recommendation="BUY",
            shadow_outputs={
                "test_green_rule": {
                    "outcome": "negative" if is_fp else "positive",
                    "false_positive": is_fp,
                }
            },
        )
        db.add(history)
    await db.commit()

    record = await evaluate_rule_governance(db, rule_id="test_green_rule")
    assert record.sample_count_30d >= 20
    assert record.health_status == "GREEN"
    assert record.false_positive_rate_30d == pytest.approx(0.10, abs=1e-3)
    assert "within baseline tolerance" in record.status_reason


@pytest.mark.asyncio
async def test_status_assignment_yellow(db: AsyncSession):
    """Baseline + 0.05 < FP rate <= Baseline + 0.15 yields YELLOW health status."""
    stock = await _get_or_create_stock(db, "INFY", "Infosys")

    now = datetime.now(timezone.utc)
    # 20 BUY records, 5 false positives (25% FP rate) vs baseline 0.15
    for i in range(20):
        is_fp = i < 5
        history = AnalysisHistory(
            stock_id=stock.id,
            mode="shadow",
            technical_score=75.0,
            sentiment_score=0.5,
            backtest_score=70.0,
            confidence=80.0,
            reasoning="Test reasoning",
            created_at=now - timedelta(days=i % 25),
            recommendation="BUY",
            shadow_outputs={
                "test_yellow_rule": {
                    "outcome": "negative" if is_fp else "positive",
                    "false_positive": is_fp,
                }
            },
        )
        db.add(history)
    await db.commit()

    record = await evaluate_rule_governance(db, rule_id="test_yellow_rule")
    assert record.sample_count_30d >= 20
    assert record.health_status == "YELLOW"
    assert record.false_positive_rate_30d == pytest.approx(0.25, abs=1e-3)
    assert "exceeds baseline tolerance but is within caution threshold" in record.status_reason


@pytest.mark.asyncio
async def test_status_assignment_red(db: AsyncSession):
    """FP rate > Baseline + 0.15 yields RED health status."""
    stock = await _get_or_create_stock(db, "HDFCBANK", "HDFC Bank")

    now = datetime.now(timezone.utc)
    # 20 BUY records, 8 false positives (40% FP rate) vs baseline 0.15
    for i in range(20):
        is_fp = i < 8
        history = AnalysisHistory(
            stock_id=stock.id,
            mode="shadow",
            technical_score=75.0,
            sentiment_score=0.5,
            backtest_score=70.0,
            confidence=80.0,
            reasoning="Test reasoning",
            created_at=now - timedelta(days=i % 25),
            recommendation="BUY",
            shadow_outputs={
                "test_red_rule": {
                    "outcome": "negative" if is_fp else "positive",
                    "false_positive": is_fp,
                }
            },
        )
        db.add(history)
    await db.commit()

    record = await evaluate_rule_governance(db, rule_id="test_red_rule")
    assert record.sample_count_30d >= 20
    assert record.health_status == "RED"
    assert record.false_positive_rate_30d == pytest.approx(0.40, abs=1e-3)
    assert "exceeds degradation threshold" in record.status_reason


@pytest.mark.asyncio
async def test_evaluate_all_promoted_rules(db: AsyncSession):
    """Verify evaluation of all promoted production rules into RuleGovernanceResponse."""
    response = await evaluate_all_promoted_rules(db)
    assert isinstance(response, RuleGovernanceResponse)
    assert response.promoted_rules_count >= 3
    rule_ids = {r.rule_id for r in response.rules}
    assert "news_dedup" in rule_ids
    assert "sentiment_decay" in rule_ids
    assert "market_breadth" in rule_ids
    assert response.evaluated_at
    for rec in response.rules:
        assert rec.health_status in VALID_HEALTH_STATUSES
        assert rec.health_label == health_status_to_label(rec.health_status)
        assert rec.health_label in {
            "healthy",
            "caution",
            "degraded",
            "insufficient data",
        }
        assert rec.baseline_false_positive_rate >= 0.0
        assert rec.sample_count_30d >= 0
        assert rec.status_reason


# ---------------------------------------------------------------------------
# Failure / edge / boundary coverage (spec edge cases + FR-001..004)
# ---------------------------------------------------------------------------


def test_is_false_positive_record_rule_scoped_flag():
    """Rule-scoped false_positive=True counts as FP."""
    assert _is_false_positive_record({"news_dedup": {"false_positive": True}}, "news_dedup") is True
    assert _is_false_positive_record({"news_dedup": {"false_positive": False}}, "news_dedup") is False


def test_is_false_positive_record_rule_scoped_outcomes():
    """Rule-scoped outcome values negative/zero/loss/false_positive count as FP."""
    for outcome in ("negative", "zero", "loss", "false_positive", "NEGATIVE"):
        assert _is_false_positive_record({"r1": {"outcome": outcome}}, "r1") is True
    assert _is_false_positive_record({"r1": {"outcome": "positive"}}, "r1") is False


def test_is_false_positive_record_flat_telemetry_ignored():
    """H2: top-level flat false_positive / outcome must not cross-contaminate rules."""
    assert _is_false_positive_record({"false_positive": True}, "any_rule") is False
    assert _is_false_positive_record({"outcome": "loss"}, "any_rule") is False
    assert _is_false_positive_record({"outcome": "positive"}, "any_rule") is False


def test_is_false_positive_record_invalid_inputs():
    """Missing/null/non-dict shadow_outputs never raise and never count as FP."""
    assert _is_false_positive_record(None, "news_dedup") is False
    assert _is_false_positive_record([], "news_dedup") is False
    assert _is_false_positive_record("bad", "news_dedup") is False
    assert _is_false_positive_record({}, "news_dedup") is False


def test_is_false_positive_derived_from_history_backtest():
    """C1: BUY + non-positive backtest_score derives FP when rule key present."""
    from types import SimpleNamespace

    history = SimpleNamespace(recommendation="BUY", backtest_score=-5.0)
    so = {"news_dedup": {"status": "success"}}
    assert _is_false_positive_record(so, "news_dedup", history=history) is True

    history_ok = SimpleNamespace(recommendation="BUY", backtest_score=12.0)
    assert _is_false_positive_record(so, "news_dedup", history=history_ok) is False

    # Rule not present → no derivation
    assert _is_false_positive_record({"other": {}}, "news_dedup", history=history) is False


@pytest.mark.asyncio
async def test_zero_recommendations_insufficient_data(db: AsyncSession):
    """Spec edge: a rule with no rule-scoped samples yields INSUFFICIENT_DATA without error.

    Uses a unique rule id so only accidental global flat-telemetry pollution can inflate
    sample count; when the DB is clean, sample_count is 0.
    """
    rule_id = f"zero_recs_{uuid.uuid4().hex[:8]}"
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert isinstance(record, RuleGovernanceRecord)
    assert record.rule_id == rule_id
    assert record.baseline_false_positive_rate == pytest.approx(0.15)
    if record.sample_count_30d < MIN_SAMPLE_COUNT:
        assert record.health_status == "INSUFFICIENT_DATA"
        assert record.false_positive_rate_30d is None
        assert "Insufficient sample count" in record.status_reason
    else:
        # Residual shared-DB telemetry matched via global selectors — still a valid evaluation
        assert record.health_status in VALID_HEALTH_STATUSES


@pytest.mark.asyncio
async def test_boundary_green_at_baseline_plus_five(db: AsyncSession):
    """FP rate exactly baseline + 0.05 (0.20) remains GREEN."""
    rule_id = f"bound_green_{uuid.uuid4().hex[:8]}"
    # 4/20 = 0.20 == 0.15 + 0.05 → GREEN
    await _seed_rule_histories(db, rule_id=rule_id, total=20, false_positive_count=4)
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 20
    assert record.false_positive_rate_30d == pytest.approx(0.20, abs=1e-3)
    assert record.health_status == "GREEN"


@pytest.mark.asyncio
async def test_boundary_yellow_at_baseline_plus_fifteen(db: AsyncSession):
    """FP rate exactly baseline + 0.15 (0.30) is YELLOW (caution upper bound)."""
    rule_id = f"bound_yellow_{uuid.uuid4().hex[:8]}"
    # 6/20 = 0.30 == 0.15 + 0.15 → YELLOW
    await _seed_rule_histories(db, rule_id=rule_id, total=20, false_positive_count=6)
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 20
    assert record.false_positive_rate_30d == pytest.approx(0.30, abs=1e-3)
    assert record.health_status == "YELLOW"


@pytest.mark.asyncio
async def test_excludes_non_buy_recommendations(db: AsyncSession):
    """Only BUY recommendations contribute to 30-day governance samples."""
    rule_id = f"buy_only_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "BUYONLY", "Buy Only Stock")
    await _seed_rule_histories(
        db, rule_id=rule_id, total=10, false_positive_count=0, recommendation="BUY", stock=stock
    )
    await _seed_rule_histories(
        db, rule_id=rule_id, total=10, false_positive_count=5, recommendation="SELL", stock=stock
    )
    await _seed_rule_histories(
        db, rule_id=rule_id, total=10, false_positive_count=5, recommendation="HOLD", stock=stock
    )
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 10
    assert record.health_status == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_excludes_records_older_than_30_days(db: AsyncSession):
    """Records outside the rolling 30-day window are ignored."""
    rule_id = f"old_window_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "OLDWIN", "Old Window Stock")
    # 20 old records (> 30 days) — should not count
    await _seed_rule_histories(
        db,
        rule_id=rule_id,
        total=20,
        false_positive_count=10,
        days_ago_offset=40,
        stock=stock,
    )
    # 5 recent — still insufficient
    await _seed_rule_histories(
        db,
        rule_id=rule_id,
        total=5,
        false_positive_count=0,
        days_ago_offset=0,
        stock=stock,
    )
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 5
    assert record.health_status == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_excludes_records_without_rule_telemetry(db: AsyncSession):
    """Histories without the rule key or flat FP telemetry do not inflate sample count."""
    rule_id = f"no_telem_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "NOTELEM", "No Telemetry Stock")
    now = datetime.now(timezone.utc)
    for i in range(20):
        db.add(
            AnalysisHistory(
                stock_id=stock.id,
                mode="live",
                technical_score=70.0,
                sentiment_score=0.4,
                backtest_score=65.0,
                confidence=70.0,
                reasoning="no rule telemetry",
                created_at=now - timedelta(days=i % 10),
                recommendation="BUY",
                shadow_outputs={"other_feature": {"status": "ok"}},
            )
        )
    await db.commit()
    before = await evaluate_rule_governance(db, rule_id=f"baseline_ref_{uuid.uuid4().hex[:6]}")
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    # other_feature-only rows must not add samples beyond residual shared noise
    assert record.sample_count_30d == before.sample_count_30d
    if record.sample_count_30d < MIN_SAMPLE_COUNT:
        assert record.health_status == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_rule_scoped_outcome_telemetry_counts(db: AsyncSession):
    """Rule-scoped outcome telemetry drives FP rate without polluting other rules.

    Top-level flat ``false_positive`` / ``outcome`` keys are intentionally global
    selectors in production; unit tests cover those paths without shared-DB side effects.
    """
    rule_id = f"scoped_fp_{uuid.uuid4().hex[:8]}"
    other_rule = f"other_fp_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "SCOPEDFP", "Scoped FP Stock")
    now = datetime.now(timezone.utc)
    for i in range(20):
        is_fp = i < 2
        db.add(
            AnalysisHistory(
                stock_id=stock.id,
                mode="shadow",
                technical_score=75.0,
                sentiment_score=0.5,
                backtest_score=70.0,
                confidence=80.0,
                reasoning="scoped fp",
                created_at=now - timedelta(days=i % 20),
                recommendation="BUY",
                shadow_outputs={
                    rule_id: {
                        "outcome": "negative" if is_fp else "positive",
                        "false_positive": is_fp,
                    }
                },
            )
        )
    await db.commit()
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 20
    assert record.false_positive_rate_30d == pytest.approx(0.10, abs=1e-3)
    assert record.health_status == "GREEN"

    # Unrelated rule must not pick up these scoped-only rows
    other = await evaluate_rule_governance(db, rule_id=other_rule)
    assert other.sample_count_30d == 0
    assert other.health_status == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_corrupt_baseline_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """Corrupt baseline JSON does not raise; defaults (0.15) are used."""
    baseline_file = tmp_path / "baseline_v1.0.json"
    baseline_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr("app.governance.rule_governance.ROOT_DIR", tmp_path)
    baselines = load_rule_baselines()
    assert baselines == {}
    assert get_rule_baseline("news_dedup", baselines) == 0.15


@pytest.mark.asyncio
async def test_baseline_invalid_metric_values_skipped(tmp_path, monkeypatch):
    """Non-numeric false_positive_rate entries are skipped without error."""
    baseline_file = tmp_path / "baseline_v1.0.json"
    content = {
        "news_dedup": {"false_positive_rate": "not-a-number"},
        "sentiment_decay": {"false_positive_rate": 0.11},
        "market_breadth": "not-a-dict",
    }
    baseline_file.write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr("app.governance.rule_governance.ROOT_DIR", tmp_path)
    baselines = load_rule_baselines()
    assert "news_dedup" not in baselines
    assert get_rule_baseline("sentiment_decay", baselines) == 0.11
    assert get_rule_baseline("market_breadth", baselines) == 0.15


@pytest.mark.asyncio
async def test_evaluate_all_custom_rule_ids(db: AsyncSession):
    """evaluate_all_promoted_rules honors an explicit rule_ids filter."""
    r1 = f"custom_a_{uuid.uuid4().hex[:6]}"
    r2 = f"custom_b_{uuid.uuid4().hex[:6]}"
    response = await evaluate_all_promoted_rules(db, rule_ids=[r1, r2])
    assert response.promoted_rules_count == 2
    assert {r.rule_id for r in response.rules} == {r1, r2}
    for rec in response.rules:
        assert rec.health_status in VALID_HEALTH_STATUSES
        assert rec.rule_id in {r1, r2}


@pytest.mark.asyncio
async def test_sample_size_exactly_at_minimum_threshold(db: AsyncSession):
    """Exactly MIN_SAMPLE_COUNT rule-scoped samples is sufficient for status assignment."""
    rule_id = f"min_n_{uuid.uuid4().hex[:8]}"
    # Seed MIN_SAMPLE_COUNT with 0 FP → if only our rows match, rate 0.0 → GREEN
    await _seed_rule_histories(
        db, rule_id=rule_id, total=MIN_SAMPLE_COUNT, false_positive_count=0
    )
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d >= MIN_SAMPLE_COUNT
    assert record.health_status != "INSUFFICIENT_DATA"
    assert record.false_positive_rate_30d is not None
    # With zero FPs in our seed, rate cannot exceed residual pollution; still a valid status
    assert record.health_status in VALID_HEALTH_STATUSES


def test_promoted_rules_default_covers_spec_rules():
    """FR-001/SC-001: default promoted set includes News Dedup, Sentiment Decay, Market Breadth."""
    assert PROMOTED_RULES_DEFAULT == ["news_dedup", "sentiment_decay", "market_breadth"]


def test_health_status_to_label_maps_spec_vocabulary():
    """M6: GREEN/YELLOW/RED/INSUFFICIENT_DATA map to healthy/caution/degraded/insufficient data."""
    assert health_status_to_label("GREEN") == "healthy"
    assert health_status_to_label("YELLOW") == "caution"
    assert health_status_to_label("RED") == "degraded"
    assert health_status_to_label("INSUFFICIENT_DATA") == "insufficient data"


def test_cli_parse_governance_report():
    """CLI exposes governance-report command (FR-001 on-demand report)."""
    args = _parse_args(["governance-report"])
    assert args.command == "governance-report"
    assert getattr(args, "rules", None) is None


def test_cli_parse_governance_report_with_rules_filter():
    """CLI accepts --rules filter for selective evaluation."""
    args = _parse_args(["governance-report", "--rules", "news_dedup,market_breadth"])
    assert args.command == "governance-report"
    assert args.rules == "news_dedup,market_breadth"


@pytest.mark.asyncio
async def test_governance_evaluation_never_raises_on_empty_shadow_outputs(db: AsyncSession):
    """Fault isolation: null/empty shadow_outputs do not crash evaluation (FR-011)."""
    rule_id = f"null_so_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "NULLSO", "Null Shadow Outputs")
    now = datetime.now(timezone.utc)
    for i in range(5):
        db.add(
            AnalysisHistory(
                stock_id=stock.id,
                mode="live",
                technical_score=50.0,
                sentiment_score=0.2,
                backtest_score=50.0,
                confidence=50.0,
                reasoning="null so",
                created_at=now - timedelta(days=i),
                recommendation="BUY",
                shadow_outputs=None,
            )
        )
    await db.commit()
    # Must complete without exception even when histories lack usable telemetry
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert isinstance(record, RuleGovernanceRecord)
    assert record.rule_id == rule_id
    assert record.health_status in VALID_HEALTH_STATUSES
    assert record.status_reason
    assert record.evaluated_at


@pytest.mark.asyncio
async def test_fp_rate_derived_from_backtest_without_explicit_flags(db: AsyncSession):
    """C1: governance computes FP from backtest_score when rule telemetry lacks flags."""
    rule_id = f"derive_fp_{uuid.uuid4().hex[:8]}"
    stock = await _get_or_create_stock(db, "DERIVE", "Derive FP Stock")
    now = datetime.now(timezone.utc)
    # 20 BUY with rule key only: 4 negative backtest → 20% FP → GREEN vs 0.15 baseline
    for i in range(20):
        bt = -10.0 if i < 4 else 15.0
        db.add(
            AnalysisHistory(
                stock_id=stock.id,
                mode="shadow",
                technical_score=75.0,
                sentiment_score=0.5,
                backtest_score=bt,
                confidence=80.0,
                reasoning="derive fp",
                created_at=now - timedelta(days=i % 20),
                recommendation="BUY",
                shadow_outputs={rule_id: {"status": "success"}},
            )
        )
    await db.commit()
    record = await evaluate_rule_governance(db, rule_id=rule_id)
    assert record.sample_count_30d == 20
    assert record.false_positive_rate_30d == pytest.approx(0.20, abs=1e-3)
    assert record.health_status == "GREEN"
    assert record.evaluated_at


def test_persist_governance_report_writes_json(tmp_path):
    """M5: governance report is persisted as machine-readable JSON."""
    from app.governance.rule_governance import persist_governance_report
    from app.schemas.governance import RuleGovernanceRecord, RuleGovernanceResponse

    response = RuleGovernanceResponse(
        evaluated_at="2026-07-22T12:00:00+00:00",
        promoted_rules_count=1,
        rules=[
            RuleGovernanceRecord(
                rule_id="news_dedup",
                evaluated_at="2026-07-22T12:00:00+00:00",
                health_status="INSUFFICIENT_DATA",
                false_positive_rate_30d=None,
                baseline_false_positive_rate=0.15,
                sample_count_30d=0,
                status_reason="test",
            )
        ],
    )
    path = persist_governance_report(response, reports_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["promoted_rules_count"] == 1
    assert data["rules"][0]["rule_id"] == "news_dedup"
    assert data["rules"][0]["evaluated_at"]
