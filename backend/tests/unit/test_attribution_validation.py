"""Unit tests for AttributionValidationService (Sprint 8 / 015).

Spec: specs/015-shadow-promotion-rebalance/spec.md
Covers FR-001..FR-004, US1 acceptance scenarios, edge cases, failure paths.
"""
from __future__ import annotations

from app.schemas.shadow_telemetry import AttributionReport, InteractionAnalysis
from app.services.attribution_validation_service import AttributionValidationService


def _make_records(n: int, *, include_tags: bool = True) -> list[dict]:
    records: list[dict] = []
    for i in range(n):
        is_win = i % 3 != 0
        rec: dict = {
            "actual_outcome": is_win,
            "scores": {
                "baseline": 65.0 if is_win else 55.0,
                "decay_only": 70.0 if is_win else 45.0,
                "breadth_only": 68.0 if is_win else 48.0,
                "combined": 72.0 if is_win else 38.0,
            },
        }
        if include_tags:
            rec["situation_tag"] = "BULL_REGIME" if i % 2 == 0 else "VOLATILE"
        records.append(rec)
    return records


def test_sample_size_safeguard():
    small_records = [{"baseline_score": 60.0, "actual_outcome": True} for _ in range(15)]
    report = AttributionValidationService.evaluate_ablation(small_records, days=30)
    assert report.status == "INSUFFICIENT_DATA"
    assert report.total_samples == 15


def test_sample_size_boundary_exactly_29_insufficient():
    records = _make_records(29)
    report = AttributionValidationService.evaluate_ablation(records, days=30)
    assert report.status == "INSUFFICIENT_DATA"
    assert report.total_samples == 29


def test_sample_size_boundary_exactly_30_valid():
    records = _make_records(30)
    report = AttributionValidationService.evaluate_ablation(records, days=30)
    assert report.status == "VALID"
    assert report.total_samples == 30


def test_empty_records_insufficient():
    report = AttributionValidationService.evaluate_ablation([], days=30)
    assert report.status == "INSUFFICIENT_DATA"
    assert report.total_samples == 0


def test_4way_ablation_valid():
    records = _make_records(40)
    report = AttributionValidationService.evaluate_ablation(records, days=30)
    assert report.status == "VALID"
    assert report.total_samples == 40
    assert report.combined_metrics.precision > report.baseline_metrics.precision
    assert "BULL_REGIME" in report.situation_tag_breakdown


def test_4way_ablation_all_configurations_present():
    report = AttributionValidationService.evaluate_ablation(_make_records(35), days=14)
    assert isinstance(report, AttributionReport)
    for metrics in (
        report.baseline_metrics,
        report.decay_only_metrics,
        report.breadth_only_metrics,
        report.combined_metrics,
    ):
        assert metrics.sample_size == 35
        assert 0.0 <= metrics.false_positive_rate <= 1.0


def test_4way_ablation_missing_scores_key_defaults():
    records = [{"actual_outcome": True, "baseline_score": 60.0} for _ in range(30)]
    report = AttributionValidationService.evaluate_ablation(records, days=7)
    assert report.status == "VALID"


def test_4way_ablation_missing_situation_tag_uses_default():
    records = _make_records(32, include_tags=False)
    report = AttributionValidationService.evaluate_ablation(records, days=30)
    assert "GENERAL_MARKET" in report.situation_tag_breakdown


def test_ablation_all_losses_no_division_error():
    records = [
        {
            "actual_outcome": False,
            "scores": {
                "baseline": 40.0,
                "decay_only": 40.0,
                "breadth_only": 40.0,
                "combined": 40.0,
            },
        }
        for _ in range(30)
    ]
    report = AttributionValidationService.evaluate_ablation(records, days=30)
    assert report.status == "VALID"
    assert report.baseline_metrics.precision == 0.0


def test_correlation_and_interaction_complementary():
    x = [10.0, 20.0, 15.0, 30.0, 25.0, 40.0, 35.0, 50.0] * 4  # n=32
    y = [5.0, 2.0, 8.0, 1.0, 9.0, 3.0, 7.0, 4.0] * 4
    analysis = AttributionValidationService.analyze_interaction(x, y)
    assert analysis.pearson_correlation < 0.70
    assert analysis.redundancy_classification == "COMPLEMENTARY"
    assert analysis.decay_promotion_recommendation == "GO"
    assert analysis.breadth_promotion_recommendation == "GO"


def test_correlation_and_interaction_redundant():
    x = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0] * 4
    y = [10.5, 20.2, 30.1, 40.4, 50.2, 60.5, 70.1, 80.3] * 4
    analysis = AttributionValidationService.analyze_interaction(x, y)
    assert analysis.pearson_correlation > 0.85
    assert analysis.redundancy_classification == "REDUNDANT"
    assert analysis.decay_promotion_recommendation == "GO"
    assert analysis.breadth_promotion_recommendation == "NO_GO"


def test_correlation_and_interaction_moderate_overlap():
    x = [float(i) for i in range(1, 31)]
    y = [
        -3.5, 1.0, 5.5, -2.0, 2.5, 7.0, -0.5, 4.0, 8.5, 1.0,
        5.5, 10.0, 2.5, 7.0, 11.5, 4.0, 8.5, 13.0, 5.5, 10.0,
        14.5, 7.0, 11.5, 16.0, 8.5, 13.0, 17.5, 10.0, 14.5, 19.0,
    ]
    analysis = AttributionValidationService.analyze_interaction(x, y)
    assert 0.70 <= analysis.pearson_correlation <= 0.85
    assert analysis.redundancy_classification == "MODERATE_OVERLAP"
    assert analysis.decay_promotion_recommendation == "GO"
    assert analysis.breadth_promotion_recommendation == "NO_GO"


def test_correlation_empty_series_returns_no_go():
    """Insufficient samples → NO_GO for both (spec edge case)."""
    analysis = AttributionValidationService.analyze_interaction([], [])
    assert analysis.decay_promotion_recommendation == "NO_GO"
    assert analysis.breadth_promotion_recommendation == "NO_GO"
    assert "Insufficient" in analysis.rationale


def test_correlation_mismatched_lengths_returns_zero():
    pearson, spearman = AttributionValidationService.calculate_correlation(
        [1.0, 2.0, 3.0], [1.0, 2.0]
    )
    assert pearson == 0.0
    assert spearman == 0.0


def test_correlation_single_element_returns_zero():
    pearson, spearman = AttributionValidationService.calculate_correlation([5.0], [9.0])
    assert pearson == 0.0


def test_correlation_constant_series_zero_variance():
    pearson, _ = AttributionValidationService.calculate_correlation(
        [3.0, 3.0, 3.0, 3.0],
        [1.0, 2.0, 3.0, 4.0],
    )
    assert pearson == 0.0


def test_interaction_preserves_feature_keys():
    x = [float(i) for i in range(30)]
    y = [float(30 - i) for i in range(30)]
    analysis = AttributionValidationService.analyze_interaction(
        x, y, decay_key="sentiment_decay", breadth_key="market_breadth"
    )
    assert isinstance(analysis, InteractionAnalysis)
    assert analysis.decay_feature_key == "sentiment_decay"
    assert analysis.breadth_feature_key == "market_breadth"


def test_perfect_negative_correlation_is_complementary():
    x = [float(i) for i in range(1, 33)]
    y = [float(33 - i) for i in range(1, 33)]
    analysis = AttributionValidationService.analyze_interaction(x, y)
    assert analysis.pearson_correlation < 0.0
    assert analysis.redundancy_classification == "COMPLEMENTARY"
    assert analysis.breadth_promotion_recommendation == "GO"


def test_post_promotion_quality_pass():
    ok, rationale = AttributionValidationService.verify_post_promotion_quality(0.10, 0.11)
    assert ok is True
    assert "within" in rationale


def test_post_promotion_quality_fail_triggers_rollback_signal():
    ok, rationale = AttributionValidationService.verify_post_promotion_quality(0.10, 0.15)
    assert ok is False
    assert "kill-switch" in rationale.lower()
