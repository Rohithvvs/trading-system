"""Unit tests for attribution_data_loader (ORM field mapping & outcome proxy)."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.attribution_data_loader import (
    history_to_ablation_record,
    records_from_histories,
)


def _history(**kwargs):
    defaults = dict(
        confidence=0.65,
        backtest_score=0.05,
        recommendation="BUY",
        situation_tags=["BULL_REGIME", "GOOD_NEWS"],
        shadow_outputs={
            "sentiment_decay": {
                "aggregate_raw_score": 0.4,
                "aggregate_decayed_score": 0.2,
            },
            "market_breadth": {"soft_score_contribution": 7.5},
        },
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_history_maps_situation_tags_and_confidence():
    rec = history_to_ablation_record(_history())
    assert rec is not None
    assert rec["situation_tag"] == "BULL_REGIME"
    assert rec["scores"]["baseline"] == 65.0
    assert rec["actual_outcome"] is True  # backtest_score > 0


def test_skips_rows_without_shadow_features():
    rec = history_to_ablation_record(_history(shadow_outputs={}))
    assert rec is None


def test_outcome_from_recommendation_when_no_backtest():
    rec = history_to_ablation_record(
        _history(backtest_score=None, recommendation="REJECT")
    )
    assert rec is not None
    assert rec["actual_outcome"] is False


def test_does_not_use_confidence_as_outcome():
    """High confidence alone must not mark win if backtest negative and not BUY."""
    rec = history_to_ablation_record(
        _history(confidence=0.99, backtest_score=-0.1, recommendation="WATCH")
    )
    assert rec is not None
    assert rec["actual_outcome"] is False


def test_records_from_histories_filters_and_series():
    rows = [
        _history(),
        _history(shadow_outputs=None),
        _history(
            shadow_outputs={
                "sentiment_decay": {
                    "aggregate_raw_score": 0.0,
                    "aggregate_decayed_score": 0.0,
                },
                "market_breadth": {"soft_score_contribution": -7.5},
            }
        ),
    ]
    records, decay, breadth = records_from_histories(rows)
    assert len(records) == 2
    assert len(decay) == 2
    assert len(breadth) == 2
    assert breadth[1] == -7.5
