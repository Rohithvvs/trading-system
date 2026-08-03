"""Integration: paper prefill retains RE-001 provenance (SC-005, FR-015)."""

from app.schemas.paper_trading import RecommendationPrefillRequest
from app.services.paper_trading_service import PaperTradingService


class _DummyDB:
    pass


def test_prefill_stamps_re001_provenance():
    svc = PaperTradingService(_DummyDB())  # type: ignore[arg-type]
    # recommendation_prefill only uses payload + symbol helper; no DB reads
    payload = RecommendationPrefillRequest(
        symbol="INFY-EQ",
        suggested_entry=1500.0,
        suggested_stop=1450.0,
        suggested_targets=[1600.0],
        recommendation_meta={"signal": "BUY", "score": "80", "confidence": "0.85"},
        source_engine_id="RE-001",
        source_engine_version="1.0",
        source_recommendation_id="rec-123",
    )
    out = svc.recommendation_prefill(payload)
    assert out.source_engine_id == "RE-001"
    assert out.source_engine_version == "1.0"
    assert out.source_recommendation_id == "rec-123"
    assert "RE-001" in out.note
    assert "rec-123" in out.note
    assert out.limit_price == 1500.0
    assert out.stop_loss == 1450.0
    assert out.target == 1600.0


def test_prefill_without_engine_leaves_provenance_none():
    svc = PaperTradingService(_DummyDB())  # type: ignore[arg-type]
    payload = RecommendationPrefillRequest(
        symbol="TCS",
        suggested_entry=100.0,
        recommendation_meta={"signal": "BUY"},
    )
    out = svc.recommendation_prefill(payload)
    assert out.source_engine_id is None
    assert "RE-001" not in out.note


def test_prefill_uses_re001_trade_guidance_when_complete(db_session, test_engine, monkeypatch):
    """FR-015: complete RE-001 trade_guidance overrides client levels."""
    import uuid
    from datetime import datetime, timezone

    from app.db.base import Base
    from app.models.recommendation_engine import RecommendationEngineDecision

    Base.metadata.create_all(bind=test_engine, tables=[RecommendationEngineDecision.__table__])
    rid = str(uuid.uuid4())
    db_session.add(
        RecommendationEngineDecision(
            recommendation_id=rid,
            engine_id="RE-001",
            engine_version="1.0",
            symbol="INFY",
            mode="swing",
            market_regime="Bull",
            trading_objective="trend_continuation",
            trading_style="long_only_swing",
            recommendation_state="BUY",
            confidence_score=0.8,
            trade_guidance={
                "entry_low": 100.0,
                "entry_high": 101.0,
                "stop_loss": 95.0,
                "target_1": 120.0,
                "complete": True,
            },
            evaluation_status="success",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    svc = PaperTradingService(db_session)
    payload = RecommendationPrefillRequest(
        symbol="INFY",
        suggested_entry=50.0,
        suggested_stop=40.0,
        suggested_targets=[60.0],
        recommendation_meta={"signal": "BUY"},
        source_engine_id="RE-001",
        source_recommendation_id=rid,
    )
    out = svc.recommendation_prefill(payload)
    assert out.source_engine_id == "RE-001"
    assert out.source_recommendation_id == rid
    assert out.limit_price == 101.0
    assert out.stop_loss == 95.0
    assert out.target == 120.0
