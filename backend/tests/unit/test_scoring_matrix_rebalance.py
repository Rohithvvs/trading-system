"""Unit tests for ScoringMatrixConfig / ScoringMatrixService (Sprint 8 / 015)."""
from __future__ import annotations

import pytest

from app.schemas.scoring_config import (
    BASELINE_SCORING_MATRIX,
    REBALANCED_SCORING_MATRIX,
    ScoringMatrixConfig,
)
from app.services.scoring_matrix_service import ScoringMatrixService


def test_baseline_scoring_matrix_sum():
    config = BASELINE_SCORING_MATRIX
    assert config.technical_weight == 35.0
    assert config.sentiment_weight == 25.0
    assert config.fundamental_weight == 25.0
    assert config.volume_weight == 15.0
    assert config.market_breadth_weight == 0.0
    assert ScoringMatrixService.validate_matrix(config) is True


def test_rebalanced_scoring_matrix_sum():
    config = REBALANCED_SCORING_MATRIX
    assert config.fundamental_weight == 15.0
    assert config.market_breadth_weight == 10.0
    assert ScoringMatrixService.validate_matrix(config) is True


def test_invalid_matrix_sum_raises_error():
    with pytest.raises(ValueError, match="Scoring matrix sum must equal exactly 100.0"):
        ScoringMatrixConfig(
            version="invalid",
            technical_weight=35.0,
            sentiment_weight=25.0,
            fundamental_weight=25.0,
            volume_weight=15.0,
            market_breadth_weight=10.0,
        )


def test_invalid_matrix_underflow_raises_error():
    with pytest.raises(ValueError, match="Scoring matrix sum must equal exactly 100.0"):
        ScoringMatrixConfig(
            version="underflow",
            technical_weight=30.0,
            sentiment_weight=20.0,
            fundamental_weight=15.0,
            volume_weight=15.0,
            market_breadth_weight=10.0,
        )


def test_negative_weight_rejected():
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        ScoringMatrixConfig(
            version="neg",
            technical_weight=50.0,
            sentiment_weight=50.0,
            fundamental_weight=20.0,
            volume_weight=0.0,
            market_breadth_weight=-20.0,
        )


def test_validate_matrix_dict_input():
    valid = {
        "version": "dict-ok",
        "technical_weight": 40.0,
        "sentiment_weight": 20.0,
        "fundamental_weight": 20.0,
        "volume_weight": 10.0,
        "market_breadth_weight": 10.0,
    }
    assert ScoringMatrixService.validate_matrix(valid) is True


def test_validate_matrix_rejects_invalid_dict():
    invalid = {
        "version": "dict-bad",
        "technical_weight": 50.0,
        "sentiment_weight": 50.0,
        "fundamental_weight": 50.0,
        "volume_weight": 50.0,
        "market_breadth_weight": 50.0,
    }
    with pytest.raises(ValueError):
        ScoringMatrixService.validate_matrix(invalid)


def test_minimal_disruption_fundamental_only_reduced():
    base = BASELINE_SCORING_MATRIX
    rebal = REBALANCED_SCORING_MATRIX
    assert rebal.technical_weight == base.technical_weight
    assert rebal.sentiment_weight == base.sentiment_weight
    assert rebal.volume_weight == base.volume_weight
    assert rebal.fundamental_weight == base.fundamental_weight - 10.0
    assert rebal.market_breadth_weight == base.market_breadth_weight + 10.0


def test_composite_score_calculation_bounds():
    score = ScoringMatrixService.compute_composite_score(
        technical_score=80.0,
        sentiment_score=70.0,
        fundamental_score=60.0,
        volume_score=90.0,
        market_breadth_score=50.0,
        matrix_config=REBALANCED_SCORING_MATRIX,
    )
    assert score == pytest.approx(73.0, abs=1e-3)
    assert 0.0 <= score <= 100.0


def test_composite_score_clamps_above_100():
    score = ScoringMatrixService.compute_composite_score(
        technical_score=200.0,
        sentiment_score=200.0,
        fundamental_score=200.0,
        volume_score=200.0,
        market_breadth_score=200.0,
        matrix_config=REBALANCED_SCORING_MATRIX,
    )
    assert score == 100.0


def test_composite_score_clamps_below_zero():
    score = ScoringMatrixService.compute_composite_score(
        technical_score=-50.0,
        sentiment_score=-50.0,
        fundamental_score=-50.0,
        volume_score=-50.0,
        market_breadth_score=-50.0,
        matrix_config=BASELINE_SCORING_MATRIX,
    )
    assert score == 0.0


def test_composite_score_unit_scale_normalized():
    score = ScoringMatrixService.compute_composite_score(
        technical_score=0.80,
        sentiment_score=0.70,
        fundamental_score=0.60,
        volume_score=0.90,
        market_breadth_score=0.50,
        matrix_config=REBALANCED_SCORING_MATRIX,
    )
    assert score == pytest.approx(73.0, abs=1e-3)


def test_composite_score_defaults_to_baseline_matrix():
    score_default = ScoringMatrixService.compute_composite_score(
        technical_score=100.0,
        sentiment_score=100.0,
        fundamental_score=100.0,
        volume_score=100.0,
        market_breadth_score=100.0,
        matrix_config=None,
    )
    score_baseline = ScoringMatrixService.compute_composite_score(
        technical_score=100.0,
        sentiment_score=100.0,
        fundamental_score=100.0,
        volume_score=100.0,
        market_breadth_score=100.0,
        matrix_config=BASELINE_SCORING_MATRIX,
    )
    assert score_default == score_baseline


def test_get_matrix_config_shadow_vs_promoted():
    shadow = ScoringMatrixService.get_matrix_config(market_breadth_promoted=False)
    promoted = ScoringMatrixService.get_matrix_config(market_breadth_promoted=True)
    assert shadow.market_breadth_weight == 0.0
    assert promoted.market_breadth_weight == 10.0
    assert shadow.fundamental_weight == 25.0
    assert promoted.fundamental_weight == 15.0


def test_normalize_weights_to_100():
    raw = {"a": 1.0, "b": 1.0, "c": 2.0}
    normalized = ScoringMatrixService.normalize_weights(raw, target_total=100.0)
    assert sum(normalized.values()) == pytest.approx(100.0, abs=1e-5)


def test_normalize_weights_zero_sum_raises():
    with pytest.raises(ValueError, match="strictly positive"):
        ScoringMatrixService.normalize_weights({"a": 0.0, "b": 0.0})


def test_normalize_weights_negative_sum_raises():
    with pytest.raises(ValueError, match="strictly positive"):
        ScoringMatrixService.normalize_weights({"a": -10.0, "b": -5.0})
