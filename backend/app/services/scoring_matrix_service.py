from __future__ import annotations

import logging
import math
from typing import Any
from app.schemas.scoring_config import (
    BASELINE_SCORING_MATRIX,
    REBALANCED_SCORING_MATRIX,
    ScoringMatrixConfig,
)

logger = logging.getLogger(__name__)


class ScoringMatrixService:
    """Service managing 100-point composite scoring matrix configurations, sum validation,

    normalization, and RuleManager-guided matrix resolution.
    """

    @staticmethod
    def validate_matrix(config: ScoringMatrixConfig | dict[str, Any]) -> bool:
        """Validates that a scoring matrix configuration sums to exactly 100.0 points."""
        if isinstance(config, dict):
            config = ScoringMatrixConfig(**config)
        total = (
            config.technical_weight
            + config.sentiment_weight
            + config.fundamental_weight
            + config.volume_weight
            + config.market_breadth_weight
        )
        return abs(total - 100.0) <= 1e-5

    @staticmethod
    def normalize_weights(weights: dict[str, float], target_total: float = 100.0) -> dict[str, float]:
        """Normalizes factor weights so their sum strictly equals target_total (default 100.0)."""
        current_sum = sum(weights.values())
        if current_sum <= 0:
            raise ValueError("Weight sum must be strictly positive to normalize.")
        scale = target_total / current_sum
        return {k: round(v * scale, 6) for k, v in weights.items()}

    @staticmethod
    def get_matrix_config(market_breadth_promoted: bool = False) -> ScoringMatrixConfig:
        """Returns the appropriate 100-point scoring matrix config based on whether

        Market Breadth (Stage 2) is active in production.
        """
        if market_breadth_promoted:
            return REBALANCED_SCORING_MATRIX
        return BASELINE_SCORING_MATRIX

    @staticmethod
    def compute_composite_score(
        technical_score: float,
        sentiment_score: float,
        fundamental_score: float,
        volume_score: float,
        market_breadth_score: float = 0.0,
        matrix_config: ScoringMatrixConfig | None = None,
    ) -> float:
        """Computes composite score in range [0, 100] given factor scores and scoring matrix config."""
        if matrix_config is None:
            matrix_config = BASELINE_SCORING_MATRIX

        def _factor(v: float) -> float:
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return 0.0
            # Each factor score is expected in range [0, 100] or normalized scale [0, 1].
            return v * 100.0 if 0.0 <= v <= 1.0 else float(v)

        tech = _factor(technical_score)
        sent = _factor(sentiment_score)
        fund = _factor(fundamental_score)
        vol = _factor(volume_score)
        breadth = _factor(market_breadth_score)

        raw_weighted_sum = (
            tech * (matrix_config.technical_weight / 100.0)
            + sent * (matrix_config.sentiment_weight / 100.0)
            + fund * (matrix_config.fundamental_weight / 100.0)
            + vol * (matrix_config.volume_weight / 100.0)
            + breadth * (matrix_config.market_breadth_weight / 100.0)
        )
        if math.isnan(raw_weighted_sum) or math.isinf(raw_weighted_sum):
            logger.warning("composite_score_non_finite | sum=%s | fail_open=0", raw_weighted_sum)
            return 0.0
        return max(0.0, min(100.0, raw_weighted_sum))
