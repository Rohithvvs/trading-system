from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ScoringMatrixConfig(BaseModel):
    version: str = "2.0.0"
    technical_weight: float = 35.0
    sentiment_weight: float = 25.0
    fundamental_weight: float = 15.0
    volume_weight: float = 15.0
    market_breadth_weight: float = 10.0

    @model_validator(mode="after")
    def validate_sum_100(self) -> "ScoringMatrixConfig":
        weights = (
            self.technical_weight,
            self.sentiment_weight,
            self.fundamental_weight,
            self.volume_weight,
            self.market_breadth_weight,
        )
        for w in weights:
            if w < 0.0 or w > 100.0:
                raise ValueError(
                    f"Scoring matrix weights must be in [0, 100], got component={w}"
                )
        total = sum(weights)
        if abs(total - 100.0) > 1e-5:
            raise ValueError(f"Scoring matrix sum must equal exactly 100.0, got {total:.2f}")
        return self


# Default Matrix Allocations
BASELINE_SCORING_MATRIX = ScoringMatrixConfig(
    version="1.0.0",
    technical_weight=35.0,
    sentiment_weight=25.0,
    fundamental_weight=25.0,
    volume_weight=15.0,
    market_breadth_weight=0.0,
)

REBALANCED_SCORING_MATRIX = ScoringMatrixConfig(
    version="2.0.0",
    technical_weight=35.0,
    sentiment_weight=25.0,
    fundamental_weight=15.0,
    volume_weight=15.0,
    market_breadth_weight=10.0,
)
