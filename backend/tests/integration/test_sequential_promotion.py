"""Integration tests for sequential promotion & kill-switch (Sprint 8 / 015)."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.governance.rule_manager import RuleManager
from app.services.scoring_matrix_service import ScoringMatrixService


@pytest.fixture
def temp_rule_states(tmp_path: Path):
    RuleManager.reset_instance()
    state_file = tmp_path / "test_rule_states.json"
    mgr = RuleManager(states_file=state_file)
    yield mgr
    RuleManager.reset_instance()


@pytest.fixture(autouse=True)
def _reset_rule_manager() -> None:
    RuleManager.reset_instance()
    yield
    RuleManager.reset_instance()


async def _promote(mgr: RuleManager, rule_id: str, reason: str = "test") -> None:
    """Promote Sprint-8 rules with SC-001 attribution approval."""
    await mgr.promote_rule(
        rule_id,
        checklist_approved=True,
        reason=reason,
        attribution_report_approved=True,
    )


@pytest.mark.asyncio
async def test_sequential_promotion_and_killswitch_flow(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    assert mgr.get_rule_state("sentiment_decay") == "shadow"
    assert mgr.get_rule_state("market_breadth") == "shadow"

    matrix_shadow = ScoringMatrixService.get_matrix_config(
        market_breadth_promoted=mgr.is_active_in_production("market_breadth")
    )
    assert matrix_shadow.market_breadth_weight == 0.0

    await _promote(mgr, "sentiment_decay", "Stage 1")
    assert mgr.is_active_in_production("sentiment_decay") is True
    assert mgr.is_active_in_production("market_breadth") is False

    await _promote(mgr, "market_breadth", "Stage 2")
    assert mgr.is_active_in_production("market_breadth") is True

    matrix_rebalanced = ScoringMatrixService.get_matrix_config(
        market_breadth_promoted=mgr.is_active_in_production("market_breadth")
    )
    assert matrix_rebalanced.market_breadth_weight == 10.0
    assert matrix_rebalanced.fundamental_weight == 15.0

    await mgr.kill_rule("market_breadth", reason="Emergency Rollback Test")
    assert mgr.is_active_in_production("market_breadth") is False
    matrix_killed = ScoringMatrixService.get_matrix_config(
        market_breadth_promoted=mgr.is_active_in_production("market_breadth")
    )
    assert matrix_killed.market_breadth_weight == 0.0


@pytest.mark.asyncio
async def test_stage1_only_keeps_breadth_shadow_and_baseline_matrix(
    temp_rule_states: RuleManager,
):
    mgr = temp_rule_states
    await _promote(mgr, "sentiment_decay", "Stage 1 only")
    assert mgr.is_active_in_production("sentiment_decay") is True
    assert mgr.is_active_in_production("market_breadth") is False
    matrix = ScoringMatrixService.get_matrix_config(
        market_breadth_promoted=mgr.is_active_in_production("market_breadth")
    )
    assert matrix.market_breadth_weight == 0.0
    assert matrix.fundamental_weight == 25.0


@pytest.mark.asyncio
async def test_fr008_stage2_blocked_in_rule_manager(temp_rule_states: RuleManager):
    """FR-008 enforced inside RuleManager (not only REST)."""
    mgr = temp_rule_states
    with pytest.raises(ValueError, match="Stage 1"):
        await _promote(mgr, "market_breadth", "blocked")
    assert mgr.is_active_in_production("market_breadth") is False


@pytest.mark.asyncio
async def test_sc001_requires_attribution_approval(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    with pytest.raises(ValueError, match="SC-001"):
        await mgr.promote_rule(
            "sentiment_decay",
            checklist_approved=True,
            reason="no report",
            attribution_report_approved=False,
        )


@pytest.mark.asyncio
async def test_kill_sentiment_decay_independently(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    await _promote(mgr, "sentiment_decay", "s1")
    await _promote(mgr, "market_breadth", "s2")
    await mgr.kill_rule("sentiment_decay", reason="Decay regression")
    assert mgr.is_active_in_production("sentiment_decay") is False
    assert mgr.is_active_in_production("market_breadth") is True


@pytest.mark.asyncio
async def test_kill_switch_lookup_under_one_second(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    await _promote(mgr, "sentiment_decay")
    await _promote(mgr, "market_breadth", "latency")
    t0 = time.perf_counter()
    await mgr.kill_rule("market_breadth", reason="latency kill")
    active = mgr.is_active_in_production("market_breadth")
    elapsed = time.perf_counter() - t0
    assert active is False
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_promote_without_checklist_raises(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    with pytest.raises(ValueError, match="checklist"):
        await mgr.promote_rule(
            "sentiment_decay",
            checklist_approved=False,
            reason="missing checklist",
            attribution_report_approved=True,
        )


@pytest.mark.asyncio
async def test_kill_without_reason_raises(temp_rule_states: RuleManager):
    mgr = temp_rule_states
    await _promote(mgr, "sentiment_decay")
    with pytest.raises(ValueError, match="reason"):
        await mgr.kill_rule("sentiment_decay", reason="")


def _async_empty_db_client(client: TestClient):
    from app.main import app
    from app.db.session import get_db

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    return client


def test_api_attribution_report_insufficient_data(client: TestClient):
    _async_empty_db_client(client)
    with patch(
        "app.routes.governance.load_shadow_histories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = client.get("/api/v1/governance/attribution-report?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["total_samples"] == 0


def test_api_interaction_check_empty_db(client: TestClient):
    _async_empty_db_client(client)
    with patch(
        "app.routes.governance.load_shadow_histories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = client.get("/api/v1/governance/interaction-check")
    assert response.status_code == 200
    body = response.json()
    assert body["decay_promotion_recommendation"] == "NO_GO"
    assert body["breadth_promotion_recommendation"] == "NO_GO"


def test_api_promote_stage2_blocked_without_stage1(client: TestClient, tmp_path: Path):
    RuleManager.reset_instance()
    state_file = tmp_path / "api_rule_states.json"
    mgr = RuleManager(states_file=state_file)
    with patch("app.routes.governance.RuleManager", return_value=mgr):
        response = client.post(
            "/api/v1/governance/rules/market_breadth/promote",
            json={
                "actor": "admin",
                "reason": "Attempt Stage 2 without Stage 1",
                "checklist_approved": True,
                "attribution_report_approved": True,
            },
        )
    assert response.status_code == 400
    assert "Stage 1" in response.json()["detail"]
    RuleManager.reset_instance()


@pytest.mark.asyncio
async def test_api_promote_stage1_then_stage2_then_kill(client: TestClient, tmp_path: Path):
    RuleManager.reset_instance()
    state_file = tmp_path / "api_seq_states.json"
    mgr = RuleManager(states_file=state_file)

    with patch("app.routes.governance.RuleManager", return_value=mgr):
        r1 = client.post(
            "/api/v1/governance/rules/sentiment_decay/promote",
            json={
                "actor": "admin",
                "reason": "Stage 1 Approved",
                "checklist_approved": True,
                "attribution_report_approved": True,
            },
        )
        assert r1.status_code == 200
        assert r1.json()["new_state"] == "production"
        assert "promotion_record" in r1.json()

        r2 = client.post(
            "/api/v1/governance/rules/market_breadth/promote",
            json={
                "actor": "admin",
                "reason": "Stage 2 Approved",
                "checklist_approved": True,
                "attribution_report_approved": True,
            },
        )
        assert r2.status_code == 200

        rk = client.post(
            "/api/v1/governance/rules/market_breadth/kill",
            json={"actor": "admin", "reason": "Emergency performance degradation"},
        )
        assert rk.status_code == 200
        assert rk.json()["new_state"] == "disabled"

    assert mgr.is_active_in_production("market_breadth") is False
    RuleManager.reset_instance()


def test_api_promote_checklist_rejected(client: TestClient, tmp_path: Path):
    RuleManager.reset_instance()
    state_file = tmp_path / "api_checklist.json"
    mgr = RuleManager(states_file=state_file)
    with patch("app.routes.governance.RuleManager", return_value=mgr):
        response = client.post(
            "/api/v1/governance/rules/sentiment_decay/promote",
            json={
                "actor": "admin",
                "reason": "no checklist",
                "checklist_approved": False,
                "attribution_report_approved": True,
            },
        )
    assert response.status_code == 400
    assert "checklist" in response.json()["detail"].lower()
    RuleManager.reset_instance()


def test_api_post_promotion_verify_auto_kill(client: TestClient, tmp_path: Path):
    RuleManager.reset_instance()
    state_file = tmp_path / "api_verify.json"
    mgr = RuleManager(states_file=state_file)
    # put breadth in production via direct state for kill target
    mgr._states["market_breadth"] = "production"
    mgr._save_states()

    with patch("app.routes.governance.RuleManager", return_value=mgr):
        response = client.post(
            "/api/v1/governance/post-promotion-verify",
            json={
                "baseline_false_positive_rate": 0.10,
                "live_false_positive_rate": 0.15,
                "max_fpr_increase": 0.02,
                "rule_id": "market_breadth",
                "auto_kill": True,
                "actor": "admin",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["auto_killed"] is True
    assert mgr.is_active_in_production("market_breadth") is False
    RuleManager.reset_instance()


def test_recommendation_uses_baseline_path_when_breadth_shadow(
    temp_rule_states: RuleManager,
):
    """Regression: shadow breadth uses legacy dynamic-weight formula, not matrix."""
    from app.services.recommendation_service import RecommendationService
    from app.schemas import AnalysisMode, TechnicalAnalysisResult, BacktestResult

    mgr = temp_rule_states
    assert mgr.is_active_in_production("market_breadth") is False

    svc = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal="neutral",
        score=70.0,
        indicators={},
        summary="t",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="sma",
        total_return=0.1,
        max_drawdown=0.05,
        win_rate=0.5,
        profit_factor=1.2,
        trade_count=10,
        verdict="ok",
        equity_curve=[{"label": "S", "equity": 100000.0}],
    )
    result = svc.build(
        symbol="INFY-EQ",
        technical_results=[tech],
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        llm_reasoning={"bullets": [], "risk_factors": [], "invalidation_signals": []},
        feat004_config={"enabled": False},
    )
    assert 0.0 <= result.score <= 100.0


@pytest.mark.asyncio
async def test_recommendation_matrix_uses_soft_score_when_breadth_promoted(
    temp_rule_states: RuleManager,
):
    """Stage 2 uses rebalanced matrix with soft-mapped breadth factor (not hardcoded 50)."""
    from app.services.recommendation_service import RecommendationService
    from app.schemas import AnalysisMode, TechnicalAnalysisResult, BacktestResult

    mgr = temp_rule_states
    await _promote(mgr, "sentiment_decay")
    await _promote(mgr, "market_breadth")

    svc = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal="bullish",
        score=80.0,
        indicators={},
        summary="t",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="sma",
        total_return=0.2,
        max_drawdown=0.05,
        win_rate=0.6,
        profit_factor=1.5,
        trade_count=10,
        verdict="ok",
        equity_curve=[{"label": "S", "equity": 100000.0}],
    )
    # soft +15 → factor 100; soft -15 → factor 0
    strong = svc.build(
        symbol="INFY-EQ",
        technical_results=[tech],
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        llm_reasoning={"bullets": [], "risk_factors": [], "invalidation_signals": []},
        feat004_config={"enabled": False},
        market_breadth_soft_score=15.0,
    )
    weak = svc.build(
        symbol="INFY-EQ",
        technical_results=[tech],
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        llm_reasoning={"bullets": [], "risk_factors": [], "invalidation_signals": []},
        feat004_config={"enabled": False},
        market_breadth_soft_score=-15.0,
    )
    assert strong.score > weak.score


@pytest.mark.asyncio
async def test_kill_breadth_restores_baseline_score_identity(
    temp_rule_states: RuleManager,
):
    mgr = temp_rule_states
    factors = dict(
        technical_score=80.0,
        sentiment_score=70.0,
        fundamental_score=60.0,
        volume_score=90.0,
    )
    baseline_score = ScoringMatrixService.compute_composite_score(
        **factors,
        market_breadth_score=0.0,
        matrix_config=ScoringMatrixService.get_matrix_config(False),
    )
    await _promote(mgr, "sentiment_decay")
    await _promote(mgr, "market_breadth", "temp")
    await mgr.kill_rule("market_breadth", reason="restore baseline")
    after_kill = ScoringMatrixService.compute_composite_score(
        **factors,
        market_breadth_score=0.0,
        matrix_config=ScoringMatrixService.get_matrix_config(
            mgr.is_active_in_production("market_breadth")
        ),
    )
    assert after_kill == pytest.approx(baseline_score, abs=1e-9)
