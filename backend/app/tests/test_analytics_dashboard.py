from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisHistory
from app.models.stock import WatchedStock


VALID_GOVERNANCE_STATUSES = {"GREEN", "YELLOW", "RED", "INSUFFICIENT_DATA"}
ACTIVE_SHADOW_RULES = ["news_dedup", "sentiment_decay", "market_breadth", "sector_strength"]


async def _create_stock(db: AsyncSession, prefix: str = "ANL") -> WatchedStock:
    stock = WatchedStock(
        symbol=f"{prefix}_{uuid.uuid4().hex[:8]}".upper(),
        display_name=f"Analytics {prefix}",
    )
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock


async def _add_history(
    db: AsyncSession,
    stock: WatchedStock,
    *,
    recommendation: str = "BUY",
    confidence: float = 75.0,
    created_at: datetime | None = None,
    shadow_outputs: dict | None = None,
    mode: str = "live",
    backtest_score: float = 65.0,
) -> AnalysisHistory:
    history = AnalysisHistory(
        stock_id=stock.id,
        mode=mode,
        technical_score=70.0,
        sentiment_score=0.5,
        backtest_score=backtest_score,
        confidence=confidence,
        reasoning="analytics dashboard seed",
        created_at=created_at or datetime.now(timezone.utc),
        recommendation=recommendation,
        shadow_outputs=shadow_outputs,
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return history


@pytest.mark.asyncio
async def test_engine_health_endpoint(test_client: AsyncClient):
    """GET /api/v1/analytics/engine-health returns 200 OK with valid schema."""
    response = await test_client.get("/api/v1/analytics/engine-health")
    assert response.status_code == 200
    data = response.json()
    assert "window_days" in data
    assert data["window_days"] == 7
    assert "total_scans" in data
    assert "total_recommendations" in data
    assert "signal_distribution" in data
    assert "BUY" in data["signal_distribution"]
    assert "SELL" in data["signal_distribution"]
    assert "HOLD" in data["signal_distribution"]
    assert "average_confidence_score" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_shadow_status_endpoint(test_client: AsyncClient):
    """GET /api/v1/analytics/shadow-status returns 200 OK with shadow rules telemetry."""
    response = await test_client.get("/api/v1/analytics/shadow-status")
    assert response.status_code == 200
    data = response.json()
    assert "active_shadow_rules" in data
    assert "news_dedup" in data["active_shadow_rules"]
    assert "sector_strength" in data["active_shadow_rules"]
    assert "rules_telemetry" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_rule_governance_endpoint(test_client: AsyncClient):
    """GET /api/v1/analytics/rule-governance returns 200 OK matching governance report format."""
    response = await test_client.get("/api/v1/analytics/rule-governance")
    assert response.status_code == 200
    data = response.json()
    assert "evaluated_at" in data
    assert "promoted_rules_count" in data
    assert "rules" in data
    assert isinstance(data["rules"], list)
    if data["rules"]:
        first = data["rules"][0]
        assert "rule_id" in first
        assert "health_status" in first
        assert "baseline_false_positive_rate" in first


# ---------------------------------------------------------------------------
# Integration with seeded data, contracts, windows, latency (FR-008..010, SC-003/004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_health_seeded_signal_distribution(
    test_client: AsyncClient, db: AsyncSession
):
    """US3 scenario 1: engine health reflects recommendation totals and signal distribution."""
    before = (await test_client.get("/api/v1/analytics/engine-health")).json()
    stock = await _create_stock(db, "EH")
    now = datetime.now(timezone.utc)

    # 3 BUY @ 80 (2 positive / 1 negative backtest), 2 SELL @ 60, 1 HOLD @ 50
    await _add_history(
        db, stock, recommendation="BUY", confidence=80.0, created_at=now, backtest_score=10.0
    )
    await _add_history(
        db, stock, recommendation="BUY", confidence=80.0, created_at=now, backtest_score=5.0
    )
    await _add_history(
        db, stock, recommendation="BUY", confidence=80.0, created_at=now, backtest_score=-3.0
    )
    for _ in range(2):
        await _add_history(db, stock, recommendation="SELL", confidence=60.0, created_at=now)
    await _add_history(db, stock, recommendation="HOLD", confidence=50.0, created_at=now)

    after = (await test_client.get("/api/v1/analytics/engine-health")).json()
    assert after["window_days"] == 7
    assert after["total_recommendations"] >= before["total_recommendations"] + 6
    # total_scans = distinct stock_id coverage (not row count)
    assert after["total_scans"] >= before["total_scans"]
    assert after["signal_distribution"]["BUY"] >= before["signal_distribution"]["BUY"] + 3
    assert after["signal_distribution"]["SELL"] >= before["signal_distribution"]["SELL"] + 2
    assert after["signal_distribution"]["HOLD"] >= before["signal_distribution"]["HOLD"] + 1
    assert after["average_confidence_score"] is not None
    assert after["generated_at"]
    assert after["positive_outcome_rate"] is not None
    assert 0.0 <= after["positive_outcome_rate"] <= 1.0


@pytest.mark.asyncio
async def test_engine_health_excludes_records_outside_7_day_window(
    test_client: AsyncClient, db: AsyncSession
):
    """Rolling 7-day window excludes older analysis history rows."""
    before = (await test_client.get("/api/v1/analytics/engine-health")).json()
    stock = await _create_stock(db, "EHOLD")
    old = datetime.now(timezone.utc) - timedelta(days=10)
    for _ in range(5):
        await _add_history(db, stock, recommendation="BUY", confidence=90.0, created_at=old)

    after = (await test_client.get("/api/v1/analytics/engine-health")).json()
    # Counts must not increase solely due to 10-day-old rows
    assert after["total_recommendations"] == before["total_recommendations"]
    assert after["signal_distribution"]["BUY"] == before["signal_distribution"]["BUY"]


@pytest.mark.asyncio
async def test_engine_health_ignores_unknown_recommendation_labels(
    test_client: AsyncClient, db: AsyncSession
):
    """Unknown recommendation values do not corrupt BUY/SELL/HOLD distribution keys."""
    before = (await test_client.get("/api/v1/analytics/engine-health")).json()
    stock = await _create_stock(db, "EHUNK")
    now = datetime.now(timezone.utc)
    await _add_history(db, stock, recommendation="WATCH", confidence=55.0, created_at=now)
    await _add_history(db, stock, recommendation="BUY", confidence=70.0, created_at=now)

    after = (await test_client.get("/api/v1/analytics/engine-health")).json()
    assert set(after["signal_distribution"].keys()) >= {"BUY", "SELL", "HOLD"}
    assert after["total_recommendations"] >= before["total_recommendations"] + 2
    assert after["signal_distribution"]["BUY"] >= before["signal_distribution"]["BUY"] + 1
    # WATCH must not appear as a distribution key in the contract shape
    assert "WATCH" not in after["signal_distribution"]


@pytest.mark.asyncio
async def test_engine_health_contract_required_fields(test_client: AsyncClient):
    """Contract analytics-api.json required fields for engine-health."""
    data = (await test_client.get("/api/v1/analytics/engine-health")).json()
    for key in (
        "window_days",
        "total_scans",
        "total_recommendations",
        "signal_distribution",
        "generated_at",
    ):
        assert key in data
    assert data["window_days"] == 7
    for sig in ("BUY", "SELL", "HOLD"):
        assert sig in data["signal_distribution"]
        assert isinstance(data["signal_distribution"][sig], int)
    assert "positive_outcome_rate" in data
    assert "average_confidence_score" in data


@pytest.mark.asyncio
async def test_shadow_status_seeded_sector_strength_and_rules(
    test_client: AsyncClient, db: AsyncSession
):
    """US3 scenario 2: shadow telemetry counts active rules including sector_strength."""
    before = (await test_client.get("/api/v1/analytics/shadow-status")).json()
    stock = await _create_stock(db, "SH")
    now = datetime.now(timezone.utc)

    await _add_history(
        db,
        stock,
        created_at=now,
        shadow_outputs={
            "sector_strength": {
                "status": "success",
                "benchmark_symbol": "NIFTY50",
                "sectors": [],
            },
            "news_dedup": {"status": "success"},
            "sentiment_decay": {"status": "success"},
            "market_breadth": {"status": "success"},
        },
    )
    # Flat news_dedup keys still count as news_dedup execution
    await _add_history(
        db,
        stock,
        created_at=now - timedelta(hours=1),
        shadow_outputs={"original_news_count": 10, "kept_news_count": 4},
    )

    after = (await test_client.get("/api/v1/analytics/shadow-status")).json()
    assert after["active_shadow_rules"] == ACTIVE_SHADOW_RULES or set(
        ACTIVE_SHADOW_RULES
    ).issubset(set(after["active_shadow_rules"]))

    for rule in ACTIVE_SHADOW_RULES:
        assert rule in after["rules_telemetry"]
        item = after["rules_telemetry"][rule]
        assert item["status"] == "active"
        assert "total_executions_7d" in item
        assert "last_executed_at" in item

    assert (
        after["rules_telemetry"]["sector_strength"]["total_executions_7d"]
        >= before["rules_telemetry"]["sector_strength"]["total_executions_7d"] + 1
    )
    assert (
        after["rules_telemetry"]["news_dedup"]["total_executions_7d"]
        >= before["rules_telemetry"]["news_dedup"]["total_executions_7d"] + 2
    )
    assert after["rules_telemetry"]["sector_strength"]["last_executed_at"] is not None
    # M4: latest output metrics exposed
    assert after["rules_telemetry"]["sector_strength"].get("last_status") is not None
    assert after["rules_telemetry"]["sector_strength"].get("last_output_summary") is not None


@pytest.mark.asyncio
async def test_shadow_status_excludes_outside_7_day_window(
    test_client: AsyncClient, db: AsyncSession
):
    """Shadow executions older than 7 days do not inflate 7d counters."""
    before = (await test_client.get("/api/v1/analytics/shadow-status")).json()
    stock = await _create_stock(db, "SHOLD")
    old = datetime.now(timezone.utc) - timedelta(days=12)
    await _add_history(
        db,
        stock,
        created_at=old,
        shadow_outputs={"sector_strength": {"status": "success"}},
    )
    after = (await test_client.get("/api/v1/analytics/shadow-status")).json()
    assert (
        after["rules_telemetry"]["sector_strength"]["total_executions_7d"]
        == before["rules_telemetry"]["sector_strength"]["total_executions_7d"]
    )


@pytest.mark.asyncio
async def test_shadow_status_handles_null_and_empty_shadow_outputs(
    test_client: AsyncClient, db: AsyncSession
):
    """Null/empty shadow_outputs rows do not crash shadow-status aggregation."""
    stock = await _create_stock(db, "SHNULL")
    now = datetime.now(timezone.utc)
    await _add_history(db, stock, created_at=now, shadow_outputs=None)
    await _add_history(db, stock, created_at=now, shadow_outputs={})
    response = await test_client.get("/api/v1/analytics/shadow-status")
    assert response.status_code == 200
    data = response.json()
    assert "rules_telemetry" in data
    assert "sector_strength" in data["rules_telemetry"]


@pytest.mark.asyncio
async def test_rule_governance_endpoint_contract_and_promoted_rules(
    test_client: AsyncClient,
):
    """US3 scenario 3 + contract: full rule governance payload for promoted rules."""
    response = await test_client.get("/api/v1/analytics/rule-governance")
    assert response.status_code == 200
    data = response.json()

    for key in ("evaluated_at", "promoted_rules_count", "rules"):
        assert key in data
    assert data["promoted_rules_count"] >= 3
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) == data["promoted_rules_count"]

    rule_ids = {r["rule_id"] for r in data["rules"]}
    assert {"news_dedup", "sentiment_decay", "market_breadth"}.issubset(rule_ids)

    for rule in data["rules"]:
        for key in (
            "rule_id",
            "evaluated_at",
            "health_status",
            "health_label",
            "baseline_false_positive_rate",
            "sample_count_30d",
            "status_reason",
        ):
            assert key in rule
        assert rule["health_status"] in VALID_GOVERNANCE_STATUSES
        assert rule["health_label"] in {
            "healthy",
            "caution",
            "degraded",
            "insufficient data",
        }
        assert rule["sample_count_30d"] >= 0
        assert isinstance(rule["baseline_false_positive_rate"], (int, float))
        # FP rate may be null when insufficient data
        fp = rule.get("false_positive_rate_30d")
        assert fp is None or isinstance(fp, (int, float))
        if rule["health_status"] == "INSUFFICIENT_DATA":
            assert fp is None
            assert rule["health_label"] == "insufficient data"


@pytest.mark.asyncio
async def test_analytics_auth_rejects_invalid_key_when_configured(
    test_client: AsyncClient, monkeypatch
):
    """H4: when API_KEY is set, missing/invalid bearer is rejected."""
    monkeypatch.setenv("API_KEY", "analytics-secret")
    resp = await test_client.get("/api/v1/analytics/engine-health")
    assert resp.status_code == 401
    resp_ok = await test_client.get(
        "/api/v1/analytics/engine-health",
        headers={"Authorization": "Bearer analytics-secret"},
    )
    assert resp_ok.status_code == 200


@pytest.mark.asyncio
async def test_analytics_endpoints_respond_within_two_seconds(test_client: AsyncClient):
    """SC-004: analytics dashboard endpoints return within 2 seconds."""
    paths = [
        "/api/v1/analytics/engine-health",
        "/api/v1/analytics/shadow-status",
        "/api/v1/analytics/rule-governance",
    ]
    for path in paths:
        start = time.perf_counter()
        response = await test_client.get(path)
        elapsed = time.perf_counter() - start
        assert response.status_code == 200, path
        assert elapsed < 2.0, f"{path} took {elapsed:.3f}s (limit 2s)"


@pytest.mark.asyncio
async def test_all_analytics_endpoints_are_reachable(test_client: AsyncClient):
    """SC-003 regression: operators can complete health review via endpoints alone."""
    health = await test_client.get("/api/v1/analytics/engine-health")
    shadow = await test_client.get("/api/v1/analytics/shadow-status")
    gov = await test_client.get("/api/v1/analytics/rule-governance")
    assert health.status_code == 200
    assert shadow.status_code == 200
    assert gov.status_code == 200
    # Each provides machine-readable monitoring data without SQL
    assert health.json()["total_recommendations"] >= 0
    assert isinstance(shadow.json()["rules_telemetry"], dict)
    assert isinstance(gov.json()["rules"], list)
