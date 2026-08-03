"""Unit/integration-lite: persist + query Decision Objects on test DB."""

from __future__ import annotations

import uuid

from app.models.recommendation_engine import RecommendationEngineDecision  # noqa: F401 — register metadata
from app.schemas.re001 import Re001DecisionObject
from app.services.re001.persistence import (
    get_decision_by_id,
    list_decisions_for_scan,
    persist_decision,
    row_to_decision_dict,
)


def test_persist_and_list_by_scan(db_session, test_engine, monkeypatch):
    from app.config import settings
    from app.db.base import Base

    # Ensure new table exists on the per-test engine (model may post-date older metadata caches)
    Base.metadata.create_all(bind=test_engine, tables=[RecommendationEngineDecision.__table__])

    monkeypatch.setattr(settings, "re001_persist_decisions", True)
    rid = str(uuid.uuid4())
    decision = Re001DecisionObject(
        recommendation_id=rid,
        recommendation_state="REJECT",
        confidence_score=0.1,
        market_regime="UNKNOWN",
        reason_codes=["missing_market_context"],
        explanation="test",
        evidence={"k": 1},
        symbol="INFY",
        scan_run_id="scan-test-1",
        evaluation_status="rejected_by_rules",
    )
    row = persist_decision(db_session, decision, mode="swing")
    assert row is not None
    assert row.recommendation_id == rid

    listed = list_decisions_for_scan(db_session, "scan-test-1")
    assert any(r.recommendation_id == rid for r in listed)

    got = get_decision_by_id(db_session, rid)
    assert got is not None
    d = row_to_decision_dict(got)
    assert d["symbol"] == "INFY"
    assert d["recommendation_state"] == "REJECT"


def test_persist_disabled_skips_write(db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_persist_decisions", False)
    decision = Re001DecisionObject(
        recommendation_id=str(uuid.uuid4()),
        recommendation_state="WATCH",
        confidence_score=0.5,
        strategy_name="Trend Following",
        strategy_family="Trend Following",
        market_regime="Bull",
        explanation="x",
        evidence={},
        symbol="TCS",
        scan_run_id="scan-x",
    )
    assert persist_decision(db_session, decision) is None
