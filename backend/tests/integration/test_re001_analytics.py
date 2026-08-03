"""Integration: RE-001 health segment aggregation (FR-016)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.recommendation_engine import RecommendationEngineDecision
from app.services.re001.analytics import re001_health_segment


def _row(**kw):
    defaults = dict(
        recommendation_id=str(uuid.uuid4()),
        engine_id="RE-001",
        engine_version="1.0",
        symbol="X",
        mode="swing",
        market_regime="Bull",
        trading_objective="trend_continuation",
        trading_style="long_only_swing",
        recommendation_state="REJECT",
        confidence_score=0.1,
        evaluation_status="success",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    return RecommendationEngineDecision(**defaults)


def test_health_counts_by_state(db_session, test_engine):
    from app.db.base import Base

    Base.metadata.create_all(bind=test_engine, tables=[RecommendationEngineDecision.__table__])
    db = db_session
    db.add(_row(recommendation_state="BUY", symbol="A", is_mismatch=True))
    db.add(_row(recommendation_state="WATCH", symbol="B"))
    db.add(_row(recommendation_state="REJECT", symbol="C", evaluation_status="error"))
    db.add(_row(recommendation_state="REJECT", symbol="D", evaluation_status="timeout"))
    db.commit()

    seg = re001_health_segment(db, days=7)
    assert seg.engine_id == "RE-001"
    assert seg.buy_count >= 1
    assert seg.watch_count >= 1
    assert seg.reject_count >= 2
    assert seg.error_count >= 1
    assert seg.timeout_count >= 1
    assert seg.mismatch_count >= 1
    assert seg.total >= 4
