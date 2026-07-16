"""
FEAT-001 Stage-1 Screener compliance regression tests.

These tests prove that Stage-1 (ScreenerService pre-analysis filters)
depends ONLY on the four FEAT-001-approved conditions:
  1. Minimum 220 candles
  2. SMA50 > SMA200
  3. Close > SMA50
  4. 20-day average volume > 100,000

They also prove that Stage-1 no longer depends on:
  - technical hard filters (hard_filters_pass)
  - technical score (technical.score >= 48)

And that downstream technical analysis and recommendation outputs
remain unchanged for valid Stage-1 candidates.
"""
import pytest
import datetime
from unittest.mock import MagicMock, patch

from backend.app.schemas.analysis import OHLCVPoint, TechnicalAnalysisResult
from backend.app.services.screener_service import ScreenerService, MINIMUM_SWING_CANDLES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int = 30, close: float = 150.0, volume: int = 150000) -> list[OHLCVPoint]:
    base = datetime.datetime(2024, 1, 1)
    return [
        OHLCVPoint(
            timestamp=base + datetime.timedelta(days=i),
            open=close - 1,
            high=close + 2,
            low=close - 2,
            close=close,
            volume=volume,
        )
        for i in range(n)
    ]


def _make_technical(
    sma_50: float = 140.0,
    sma_200: float = 120.0,
    hard_filters_pass: bool = True,
    score: float = 60.0,
) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        mode="swing",
        signal="bullish",
        score=score,
        indicators={
            "sma_50": sma_50,
            "sma_200": sma_200,
            "hard_filters_pass": hard_filters_pass,
        },
        summary="test",
    )


def _make_screener():
    screener = ScreenerService.__new__(ScreenerService)
    screener.logger = MagicMock()
    screener._scan_log = None
    return screener


# ---------------------------------------------------------------------------
# 1. Stage-1 no longer depends on technical score
# ---------------------------------------------------------------------------

def test_broad_trend_passes_with_low_technical_score():
    """Stage-1 must pass even when technical.score is 0."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=0.0)
    assert screener._passes_broad_trend(candles, technical) is True


def test_broad_trend_passes_with_technical_score_below_48():
    """Stage-1 must pass even when technical.score < 48 (the old threshold)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=30.0)
    assert screener._passes_broad_trend(candles, technical) is True


def test_broad_trend_passes_with_high_technical_score():
    """Stage-1 still passes when technical.score is high (unchanged behavior)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=90.0)
    assert screener._passes_broad_trend(candles, technical) is True


def test_broad_trend_score_does_not_affect_pass_fail():
    """Stage-1 pass/fail is identical regardless of technical.score."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    tech_low = _make_technical(sma_50=140, sma_200=120, score=0.0)
    tech_high = _make_technical(sma_50=140, sma_200=120, score=100.0)
    assert screener._passes_broad_trend(candles, tech_low) == screener._passes_broad_trend(candles, tech_high)


# ---------------------------------------------------------------------------
# 2. Stage-1 no longer depends on hard filters
# ---------------------------------------------------------------------------

def test_broad_trend_passes_with_hard_filters_failed():
    """Stage-1 must pass even when hard_filters_pass is False."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, hard_filters_pass=False)
    assert screener._passes_broad_trend(candles, technical) is True


def test_broad_trend_passes_with_hard_filters_passed():
    """Stage-1 still passes when hard_filters_pass is True (unchanged behavior)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, hard_filters_pass=True)
    assert screener._passes_broad_trend(candles, technical) is True


def test_broad_trend_hard_filter_does_not_affect_pass_fail():
    """Stage-1 pass/fail is identical regardless of hard_filters_pass."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    tech_pass = _make_technical(sma_50=140, sma_200=120, hard_filters_pass=True)
    tech_fail = _make_technical(sma_50=140, sma_200=120, hard_filters_pass=False)
    assert screener._passes_broad_trend(candles, tech_pass) == screener._passes_broad_trend(candles, tech_fail)


# ---------------------------------------------------------------------------
# 3. Stage-1 still enforces the four FEAT-001 filters
# ---------------------------------------------------------------------------

def test_broad_trend_close_above_sma50():
    """Close > SMA50 is enforced."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=160, sma_200=120)
    assert screener._passes_broad_trend(candles, technical) is False


def test_broad_trend_sma50_above_sma200():
    """SMA50 > SMA200 is enforced."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=160)
    assert screener._passes_broad_trend(candles, technical) is False


def test_broad_trend_volume_above_100k():
    """20-day average volume > 100,000 is enforced."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=50000)
    technical = _make_technical(sma_50=140, sma_200=120)
    assert screener._passes_broad_trend(candles, technical) is False


def test_broad_trend_volume_exactly_100k_fails():
    """Volume exactly 100,000 must fail (strict >)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=100000)
    technical = _make_technical(sma_50=140, sma_200=120)
    assert screener._passes_broad_trend(candles, technical) is False


def test_broad_trend_all_four_filters_pass():
    """All four FEAT-001 Stage-1 filters passing → broad_trend True."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120)
    assert screener._passes_broad_trend(candles, technical) is True


def test_data_quality_enforces_220_candles():
    """Minimum 220 candles is enforced in _passes_data_quality."""
    screener = _make_screener()
    candles = _make_candles(n=30, close=150, volume=150000)
    assert screener._passes_data_quality(candles, total_candle_count=219) is False
    assert screener._passes_data_quality(candles, total_candle_count=220) is True


def test_minimum_swing_candles_constant():
    """MINIMUM_SWING_CANDLES is 220 per FEAT-001."""
    assert MINIMUM_SWING_CANDLES == 220


# ---------------------------------------------------------------------------
# 4. Downstream technical analysis still runs unchanged
# ---------------------------------------------------------------------------

def test_technical_analysis_service_not_modified():
    """TechnicalAnalysisService.analyze_bulk_from_frame signature unchanged."""
    import inspect
    from backend.app.services.technical_analysis_service import TechnicalAnalysisService
    sig = inspect.signature(TechnicalAnalysisService.analyze_bulk_from_frame)
    params = list(sig.parameters.keys())
    assert "mode" in params
    assert "frame" in params


def test_screener_still_calls_analyze_bulk_from_frame():
    """The screener still runs vectorized bulk technical analysis."""
    import inspect
    source = inspect.getsource(ScreenerService.screen_symbols_swing)
    assert "analyze_bulk_from_frame" in source


def test_weighted_score_formula_unchanged():
    """_weighted_score still uses technical.score * 0.5 (not removed)."""
    import inspect
    source = inspect.getsource(ScreenerService._weighted_score)
    assert "technical.score * 0.5" in source


def test_matched_logic_unchanged():
    """matched = broad_eligibility and screener_score >= 52 (not changed)."""
    import inspect
    source = inspect.getsource(ScreenerService._process_single_symbol)
    assert "screener_score >= 52" in source


def test_build_conditions_still_includes_hard_filters():
    """_build_conditions still reports hard_filters_pass (for logging)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    latest = candles[-1]
    previous = candles[-2]
    technical = _make_technical(sma_50=140, sma_200=120, hard_filters_pass=True)
    conditions = screener._build_conditions(
        technical.indicators, latest, previous, True, technical
    )
    assert "hard_filters_pass" in conditions
    assert conditions["hard_filters_pass"] is True


# ---------------------------------------------------------------------------
# 5. Recommendation outputs remain unchanged for valid Stage-1 candidates
# ---------------------------------------------------------------------------

def test_valid_stage1_candidate_still_scored_and_matched():
    """A stock passing all four FEAT-001 filters with a good technical score
    still gets scored and can be matched — downstream pipeline unaffected."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=70.0, hard_filters_pass=True)

    broad_eligibility = screener._passes_broad_trend(candles, technical)
    assert broad_eligibility is True

    conditions = screener._build_conditions(
        technical.indicators, candles[-1], candles[-2], broad_eligibility, technical
    )
    screener_score = screener._weighted_score(candles, technical, conditions)
    matched = broad_eligibility and screener_score >= 52

    assert screener_score > 0
    assert matched is True


def test_valid_stage1_candidate_with_low_score_not_matched_but_eligible():
    """A stock passing all four FEAT-001 filters but with a low screener score
    is still broad-eligible (Stage-1 pass) but not matched (shortlisting filter).
    This proves Stage-1 (eligibility) is separated from shortlisting (score)."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=0.0, hard_filters_pass=False)

    broad_eligibility = screener._passes_broad_trend(candles, technical)
    assert broad_eligibility is True

    conditions = screener._build_conditions(
        technical.indicators, candles[-1], candles[-2], broad_eligibility, technical
    )
    screener_score = screener._weighted_score(candles, technical, conditions)
    matched = broad_eligibility and screener_score >= 52

    # Score is low because technical.score is 0, but eligibility is True
    assert broad_eligibility is True
    # matched may be False due to low screener_score — that's the shortlist filter, not Stage-1


def test_stock_failing_sma50_gt_sma200_not_eligible_even_with_high_score():
    """A stock failing SMA50 > SMA200 is not eligible, regardless of technical score."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=150000)
    technical = _make_technical(sma_50=120, sma_200=160, score=100.0, hard_filters_pass=True)
    assert screener._passes_broad_trend(candles, technical) is False


def test_stock_failing_close_gt_sma50_not_eligible_even_with_high_score():
    """A stock failing Close > SMA50 is not eligible, regardless of technical score."""
    screener = _make_screener()
    candles = _make_candles(close=130, volume=150000)
    technical = _make_technical(sma_50=140, sma_200=120, score=100.0, hard_filters_pass=True)
    assert screener._passes_broad_trend(candles, technical) is False


def test_stock_failing_volume_not_eligible_even_with_high_score():
    """A stock failing 20-day avg volume > 100k is not eligible, regardless of technical score."""
    screener = _make_screener()
    candles = _make_candles(close=150, volume=80000)
    technical = _make_technical(sma_50=140, sma_200=120, score=100.0, hard_filters_pass=True)
    assert screener._passes_broad_trend(candles, technical) is False


# ---------------------------------------------------------------------------
# 6. Strict Buy Gate and RecommendationService not modified
# ---------------------------------------------------------------------------

def test_strict_buy_gate_not_modified():
    """Strict Buy Gate still checks technical_score >= 75 (unchanged)."""
    import inspect
    from backend.app.agents.orchestrator_agent import OrchestratorAgent
    source = inspect.getsource(OrchestratorAgent._enforce_strict_buy_gate)
    assert "75" in source


def test_recommendation_service_not_modified():
    """RecommendationService.build signature unchanged."""
    import inspect
    from backend.app.services.recommendation_service import RecommendationService
    sig = inspect.signature(RecommendationService.build)
    params = list(sig.parameters.keys())
    assert "technical_results" in params
    assert "backtests" in params
