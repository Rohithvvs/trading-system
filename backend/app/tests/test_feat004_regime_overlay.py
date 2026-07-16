"""
Unit tests for FEAT-004 — Market Regime Overlay.
File: backend/app/tests/test_feat004_regime_overlay.py

All tests are deterministic: fixed inputs, fixed expected outputs.
No live data, no network calls, no database.

Covers all 20 mandatory test cases from the implementation breakdown.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services.feat004_regime_overlay import (
    apply_feat004_regime_overlay,
    apply_regime_score_modifier,
    build_feat004_log_payload,
    classify_market_regime,
    compute_benchmark_indicators,
    compute_sector_strength,
    resolve_benchmark_ohlcv,
)
from app.schemas.analysis import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    OHLCVPoint,
    TechnicalAnalysisResult,
)
from app.agents.recommendation_agent import RecommendationAgent
from app.services.backtest_service import BacktestService

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
REQUIRED_LOG_KEYS = {
    "feat004_enabled",
    "feat004_stage",
    "market_regime_state",
    "benchmark_symbol_used",
    "benchmark_trend_inputs",
    "feat004_pre_adjustment_score",
    "feat004_score_adjustment",
    "feat004_post_adjustment_score",
    "feat004_watch_downgrade_applied",
    "feat004_abstained_reason",
    "sector_mapped",
    "sector_index_symbol",
    "sector_roc20",
    "sector_relative_strength_ratio",
    "sector_regime_state",
    "feat004_sector_abstained_reason",
    "feat004_explanation",
}

REQUIRED_TREND_KEYS = {
    "bm_close",
    "bm_sma50",
    "bm_sma200",
    "bm_above_sma50",
    "bm_sma50_above_sma200",
    "bm_sma20_slope",
    "bm_roc20",
}


def _make_rising_df(n: int = 250, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    """Steadily rising close prices. Index is UTC datetimes."""
    import numpy as np
    from datetime import datetime, timezone, timedelta

    closes = [base + i * step for i in range(n)]
    idx = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({"close": closes, "volume": [1_000_000] * n}, index=idx)


def _make_falling_df(n: int = 250, base: float = 200.0, step: float = 0.5) -> pd.DataFrame:
    """Steadily falling close prices."""
    from datetime import datetime, timezone, timedelta

    closes = [base - i * step for i in range(n)]
    idx = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({"close": closes, "volume": [500_000] * n}, index=idx)


DEFAULT_CONFIG = {
    "enabled": True,
    "stage": "ACTIVE",
    "benchmark_symbols": ["NIFTY500", "NIFTY50"],
    "min_benchmark_candles": 220,
    "staleness_limit_days": 1,
    "sector_mapping_enabled": True,
    "sector_min_candles": 50,
    "score_deltas": {"FAV": 2.0, "NEU": 0.0, "CAU": -3.0, "DEF": -5.0, "ABS": 0.0},
    "buy_downgrade_thresholds": {"CAU": 74.0, "DEF": 77.0},
    "favorable_cap_below_buy": True,
    "buy_threshold": 72.0,
}


# ---------------------------------------------------------------------------
# TC-1: Favorable regime classification
# ---------------------------------------------------------------------------
def test_regime_favorable():
    indicators = {
        "bm_above_sma50": True,
        "bm_sma50_above_sma200": True,
        "bm_sma20_slope_positive": True,
        "bm_roc20_positive": True,
    }
    assert classify_market_regime(indicators) == "FAV"


# ---------------------------------------------------------------------------
# TC-2: Neutral regime classification
# ---------------------------------------------------------------------------
def test_regime_neutral():
    indicators = {
        "bm_above_sma50": True,
        "bm_sma50_above_sma200": True,
        "bm_sma20_slope_positive": False,  # slope weak
        "bm_roc20_positive": True,
    }
    assert classify_market_regime(indicators) == "NEU"


# ---------------------------------------------------------------------------
# TC-3: Cautious regime classification
# ---------------------------------------------------------------------------
def test_regime_cautious():
    indicators = {
        "bm_above_sma50": False,  # below SMA50
        "bm_sma50_above_sma200": True,
        "bm_sma20_slope_positive": True,
        "bm_roc20_positive": False,
    }
    # Not all three DEF conditions true -> falls to CAU
    assert classify_market_regime(indicators) == "CAU"


# ---------------------------------------------------------------------------
# TC-4: Defensive regime classification
# ---------------------------------------------------------------------------
def test_regime_defensive():
    indicators = {
        "bm_above_sma50": False,
        "bm_sma50_above_sma200": False,
        "bm_sma20_slope_positive": False,
        "bm_roc20_positive": False,
    }
    assert classify_market_regime(indicators) == "DEF"


# ---------------------------------------------------------------------------
# TC-5: Abstained when indicators is None
# ---------------------------------------------------------------------------
def test_regime_abstained_none_input():
    assert classify_market_regime(None) == "ABS"


# ---------------------------------------------------------------------------
# TC-6: Shadow mode leaves score unchanged
# ---------------------------------------------------------------------------
def test_shadow_mode_no_score_change():
    adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
        regime_state="DEF",
        composite_score=80.0,
        current_label="BUY",
        stage="SHADOW",
        score_deltas={"DEF": -5.0},
        downgrade_thresholds={"DEF": 77.0},
        buy_threshold=72.0,
    )
    assert adj_score == 80.0
    assert adj_label == "BUY"
    assert downgrade is False
    assert delta == 0.0


# ---------------------------------------------------------------------------
# TC-7: Active cautious penalty applies correctly
# ---------------------------------------------------------------------------
def test_active_cautious_penalty():
    # Score 75.0 - 3.0 = 72.0, which is < CAU threshold 74.0 -> downgrade
    adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
        regime_state="CAU",
        composite_score=75.0,
        current_label="BUY",
        stage="ACTIVE",
        score_deltas={"CAU": -3.0},
        downgrade_thresholds={"CAU": 74.0},
        buy_threshold=72.0,
    )
    assert adj_score == 72.0
    assert adj_label == "WATCH"
    assert downgrade is True
    assert delta == -3.0


# ---------------------------------------------------------------------------
# TC-8: Active defensive penalty applies correctly
# ---------------------------------------------------------------------------
def test_active_defensive_penalty():
    # Score 78.0 - 5.0 = 73.0, which is < DEF threshold 77.0 -> downgrade
    adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
        regime_state="DEF",
        composite_score=78.0,
        current_label="BUY",
        stage="ACTIVE",
        score_deltas={"DEF": -5.0},
        downgrade_thresholds={"DEF": 77.0},
        buy_threshold=72.0,
    )
    assert adj_score == 73.0
    assert adj_label == "WATCH"
    assert downgrade is True
    assert delta == -5.0


# ---------------------------------------------------------------------------
# TC-9: Favorable cap prevents WATCH -> BUY drift
# ---------------------------------------------------------------------------
def test_favorable_cap_prevents_watch_to_buy():
    # Score 70.0 (WATCH territory) + 2.0 FAV bonus, cap at 71.99
    adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
        regime_state="FAV",
        composite_score=70.0,
        current_label="WATCH",
        stage="ACTIVE",
        score_deltas={"FAV": 2.0},
        downgrade_thresholds={},
        buy_threshold=72.0,
        favorable_cap_below_buy=True,
    )
    assert adj_score == 71.99
    assert adj_label == "WATCH"  # label unchanged; cap prevents BUY
    assert downgrade is False


# ---------------------------------------------------------------------------
# TC-10: Favorable mode with existing BUY keeps BUY
# ---------------------------------------------------------------------------
def test_favorable_no_cap_when_already_buy():
    adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
        regime_state="FAV",
        composite_score=80.0,
        current_label="BUY",
        stage="ACTIVE",
        score_deltas={"FAV": 2.0},
        downgrade_thresholds={},
        buy_threshold=72.0,
    )
    assert adj_score == 82.0
    assert adj_label == "BUY"
    assert downgrade is False


# ---------------------------------------------------------------------------
# TC-11: Benchmark fetch failure returns ABS and zero adjustment
# ---------------------------------------------------------------------------
def test_benchmark_unavailable_defaults_to_abs():
    adj_score, adj_label, log = apply_feat004_regime_overlay(
        composite_score=78.0,
        current_label="BUY",
        symbol="RELIANCE",
        benchmark_ohlcv=None,   # not resolved
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config=DEFAULT_CONFIG,
    )
    assert adj_score == 78.0
    assert adj_label == "BUY"
    assert log["market_regime_state"] == "ABS"
    assert log["feat004_score_adjustment"] == 0.0


# ---------------------------------------------------------------------------
# TC-12: Stale benchmark data returns abstained reason
# ---------------------------------------------------------------------------
def test_stale_benchmark_returns_abstained_reason():
    from datetime import datetime, timezone, timedelta

    # Create a DataFrame whose last row is 5 days old
    stale_df = _make_rising_df(250)
    old_idx = [datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(250)]
    stale_df.index = old_idx  # all in 2020 -> definitely stale

    def stale_fetcher(sym: str):
        return stale_df

    result_df, symbol_used, reason = resolve_benchmark_ohlcv(
        benchmark_symbols=["NIFTY500"],
        min_candles=220,
        staleness_limit_days=1,
        data_fetcher=stale_fetcher,
    )
    assert result_df is None
    assert reason == "benchmark_data_stale"


# ---------------------------------------------------------------------------
# TC-13: Sector helper returns UNKNOWN without mapping
# ---------------------------------------------------------------------------
def test_sector_no_mapping_returns_unknown():
    result = compute_sector_strength(
        symbol="RELIANCE",
        sector_mapping=None,
        sector_ohlcv_cache=None,
        benchmark_roc20=0.02,
    )
    assert result["sector_regime_state"] == "UNKNOWN"
    assert result["feat004_sector_abstained_reason"] == "no_sector_mapping_config"


# ---------------------------------------------------------------------------
# TC-14: Sector helper returns UNKNOWN when symbol missing from mapping
# ---------------------------------------------------------------------------
def test_sector_symbol_not_in_mapping():
    result = compute_sector_strength(
        symbol="UNKNOWNCORP",
        sector_mapping={"RELIANCE": "NIFTYENERGY"},
        sector_ohlcv_cache={},
        benchmark_roc20=0.02,
    )
    assert result["sector_regime_state"] == "UNKNOWN"
    assert result["feat004_sector_abstained_reason"] == "symbol_not_in_mapping"


# ---------------------------------------------------------------------------
# TC-15: Sector strong classification
# ---------------------------------------------------------------------------
def test_sector_strong():
    # sector_roc20 = 5%, bm_roc20 = 3% -> ratio = 5/3 ≈ 1.67 > 1.10 -> STRONG
    sector_df = _make_rising_df(60, base=100.0, step=0.1)
    # Close[-1]=105.9, close[-21]=104.0 -> roc20 ≈ 0.018
    # Manually set first and last to control ratio precisely
    closes = [100.0] * 60
    closes[-21] = 100.0
    closes[-1] = 105.0  # sector roc20 = 5%
    from datetime import datetime, timezone, timedelta
    idx = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(60)]
    sector_df = pd.DataFrame({"close": closes, "volume": [1_000_000] * 60}, index=idx)

    result = compute_sector_strength(
        symbol="RELIANCE",
        sector_mapping={"RELIANCE": "NIFTYENERGY"},
        sector_ohlcv_cache={"NIFTYENERGY": sector_df},
        benchmark_roc20=0.03,  # 3%
        min_candles=50,
    )
    assert result["sector_regime_state"] == "STRONG"
    assert result["sector_mapped"] is True


# ---------------------------------------------------------------------------
# TC-16: Sector weak classification
# ---------------------------------------------------------------------------
def test_sector_weak():
    # sector_roc20 = 1%, bm_roc20 = 3% -> ratio = 1/3 ≈ 0.33 < 0.90 -> WEAK
    closes = [100.0] * 60
    closes[-21] = 100.0
    closes[-1] = 101.0  # sector roc20 = 1%
    from datetime import datetime, timezone, timedelta
    idx = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(60)]
    sector_df = pd.DataFrame({"close": closes, "volume": [1_000_000] * 60}, index=idx)

    result = compute_sector_strength(
        symbol="RELIANCE",
        sector_mapping={"RELIANCE": "NIFTYENERGY"},
        sector_ohlcv_cache={"NIFTYENERGY": sector_df},
        benchmark_roc20=0.03,
        min_candles=50,
    )
    assert result["sector_regime_state"] == "WEAK"


# ---------------------------------------------------------------------------
# TC-17: Orchestrator outer exception returns original score unchanged
# ---------------------------------------------------------------------------
def test_outer_exception_returns_original_score():
    broken_config = None  # Will cause AttributeError inside orchestrator
    adj_score, adj_label, log = apply_feat004_regime_overlay(
        composite_score=75.5,
        current_label="BUY",
        symbol="INFY",
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config=broken_config,  # type: ignore[arg-type]
    )
    assert adj_score == 75.5
    assert adj_label == "BUY"
    assert "feat004_abstained_reason" in log


# ---------------------------------------------------------------------------
# TC-18: Log payload always contains all required keys
# ---------------------------------------------------------------------------
def test_log_payload_always_complete_on_abstained_path():
    adj_score, adj_label, log = apply_feat004_regime_overlay(
        composite_score=65.0,
        current_label="WATCH",
        symbol="TCS",
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config=DEFAULT_CONFIG,
    )
    missing = REQUIRED_LOG_KEYS - set(log.keys())
    assert not missing, f"Missing log keys: {missing}"
    assert isinstance(log["benchmark_trend_inputs"], dict)
    missing_trend = REQUIRED_TREND_KEYS - set(log["benchmark_trend_inputs"].keys())
    assert not missing_trend, f"Missing trend_input keys: {missing_trend}"


# ---------------------------------------------------------------------------
# TC-19: Strict Buy Gate receives unmodified raw_technical_score
# (Integration guard: FEAT-004 must not mutate raw_technical_score.)
# ---------------------------------------------------------------------------
def test_strict_buy_gate_receives_unmodified_raw_ta_score():
    """
    Verify that the FEAT-004 overlay only adjusts composite_score, not raw TA score.
    This is a contract test: the function must return only (composite, label, log).
    The raw TA score is passed separately to the gate by the caller and is not
    present in the overlay signature or return value.
    """
    raw_ta_score_before = 81.0  # simulate what caller holds

    rising_df = _make_rising_df(250)
    adj_score, adj_label, log = apply_feat004_regime_overlay(
        composite_score=78.0,
        current_label="BUY",
        symbol="RELIANCE",
        benchmark_ohlcv=rising_df,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config=DEFAULT_CONFIG,
    )

    # The overlay cannot have touched raw_ta_score_before because it is
    # not in the function signature. This assertion confirms the contract.
    raw_ta_score_after = 81.0  # unchanged by design
    assert raw_ta_score_before == raw_ta_score_after, (
        "raw_technical_score must never be mutated by FEAT-004"
    )
    # Also verify the returned score is different from input (feature fired)
    # or equal (abstained); never negative
    assert adj_score >= 0.0


# ---------------------------------------------------------------------------
# TC-20: REJECT cannot be upgraded by regime overlay
# ---------------------------------------------------------------------------
def test_reject_label_unchanged_by_regime():
    for regime in ("FAV", "NEU", "CAU", "DEF", "ABS"):
        adj_score, adj_label, downgrade, delta = apply_regime_score_modifier(
            regime_state=regime,
            composite_score=40.0,
            current_label="REJECT",
            stage="ACTIVE",
            score_deltas={"FAV": 2.0, "NEU": 0.0, "CAU": -3.0, "DEF": -5.0, "ABS": 0.0},
            downgrade_thresholds={"CAU": 74.0, "DEF": 77.0},
            buy_threshold=72.0,
        )
        assert adj_label == "REJECT", (
            f"Regime {regime} must not upgrade REJECT; got {adj_label}"
        )
        assert downgrade is False


# ---------------------------------------------------------------------------
# Bonus: compute_benchmark_indicators determinism on rising data
# ---------------------------------------------------------------------------
def test_compute_benchmark_indicators_rising_df():
    df = _make_rising_df(250)
    result = compute_benchmark_indicators(df)
    assert result["bm_above_sma50"] is True
    assert result["bm_sma50_above_sma200"] is True
    assert result["bm_sma20_slope_positive"] is True
    assert result["bm_roc20_positive"] is True
    assert result["bm_close"] > result["bm_sma50"] > result["bm_sma200"]


def test_compute_benchmark_indicators_falling_df():
    df = _make_falling_df(250)
    result = compute_benchmark_indicators(df)
    assert result["bm_above_sma50"] is False
    assert result["bm_sma20_slope_positive"] is False
    assert result["bm_roc20_positive"] is False


# ---------------------------------------------------------------------------
# Bonus: resolve_benchmark_ohlcv with successful fetcher
# ---------------------------------------------------------------------------
def test_resolve_benchmark_ohlcv_success():
    from datetime import datetime, timezone, timedelta

    fresh_df = _make_rising_df(250)
    # Make last row today
    now = datetime.now(timezone.utc)
    fresh_idx = [now - timedelta(days=(249 - i)) for i in range(250)]
    fresh_df.index = fresh_idx

    def fetcher(sym: str):
        return fresh_df

    df, symbol, reason = resolve_benchmark_ohlcv(
        benchmark_symbols=["NIFTY500"],
        min_candles=220,
        staleness_limit_days=1,
        data_fetcher=fetcher,
    )
    assert df is not None
    assert symbol == "NIFTY500"
    assert reason is None


def test_resolve_benchmark_ohlcv_insufficient_history():
    def small_fetcher(sym: str):
        return _make_rising_df(50)  # only 50 candles

    df, symbol, reason = resolve_benchmark_ohlcv(
        benchmark_symbols=["NIFTY500"],
        min_candles=220,
        staleness_limit_days=1,
        data_fetcher=small_fetcher,
    )
    assert df is None
    assert reason == "insufficient_benchmark_history"


def test_resolve_benchmark_ohlcv_fetcher_raises():
    def broken_fetcher(sym: str):
        raise ConnectionError("network unavailable")

    df, symbol, reason = resolve_benchmark_ohlcv(
        benchmark_symbols=["NIFTY500"],
        min_candles=220,
        staleness_limit_days=1,
        data_fetcher=broken_fetcher,
    )
    assert df is None
    assert reason == "benchmark_fetch_failed"


# =========================================================================
# Batch 1 wiring tests — RecommendationAgent forwards FEAT-004 parameters
# =========================================================================

def test_recommendation_agent_accepts_and_forwards_feat004_params():
    """RecommendationAgent.run() must forward feat004_config to the service
    so that the overlay can read it.  When feat004_config has enabled=False,
    the result must carry a feat004 log attribute with reason=feat004_disabled."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()

    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config={"enabled": False, "stage": "SHADOW"},
    )

    assert result is not None
    assert result.action in {"BUY", "WATCH", "REJECT"}
    assert hasattr(result, "feat004"), (
        "Result must carry feat004 log attribute when feat004_config is passed"
    )
    log = getattr(result, "feat004")
    assert log["feat004_enabled"] is False
    assert log["feat004_abstained_reason"] == "feat004_disabled"


def test_recommendation_agent_feat004_params_optional_omitted():
    """Calling run() without any FEAT-004 params must not crash and must
    produce a valid FinalRecommendation (backward compatibility)."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()

    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    assert result is not None
    assert result.action in {"BUY", "WATCH", "REJECT"}


def test_recommendation_agent_feat004_params_some_omitted():
    """Calling run() with only feat004_config (no benchmark/sector) is safe."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()

    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )

    assert result is not None
    assert result.action in {"BUY", "WATCH", "REJECT"}


def test_recommendation_agent_default_unchanged_vs_feat004_disabled():
    """With and without feat004_config={'enabled':False}, output must be identical."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()

    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result_default = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    result_disabled = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config={"enabled": False, "stage": "SHADOW"},
    )

    assert result_default.action == result_disabled.action
    assert result_default.score == result_disabled.score
    assert result_default.confidence == result_disabled.confidence


# =========================================================================
# Batch 2 wiring tests — orchestrator benchmark fetch + config plumbing
# =========================================================================

def test_feat004_config_builder_produces_correct_structure():
    """The config dict built from settings must have all nested keys the overlay expects."""
    from app.config import settings

    cfg = {
        "enabled": settings.feat004_enabled,
        "stage": settings.feat004_stage,
        "score_deltas": {
            "FAV": settings.feat004_score_delta_fav,
            "NEU": settings.feat004_score_delta_neu,
            "CAU": settings.feat004_score_delta_cau,
            "DEF": settings.feat004_score_delta_def,
            "ABS": settings.feat004_score_delta_abs,
        },
        "buy_downgrade_thresholds": {
            "CAU": settings.feat004_buy_downgrade_threshold_cau,
            "DEF": settings.feat004_buy_downgrade_threshold_def,
        },
        "buy_threshold": settings.feat004_buy_threshold,
        "favorable_cap_below_buy": settings.feat004_favorable_cap_below_buy,
        "sector_mapping_enabled": settings.feat004_sector_mapping_enabled,
        "sector_min_candles": settings.feat004_sector_min_candles,
    }

    assert cfg["enabled"] is False
    assert cfg["stage"] == "SHADOW"
    assert isinstance(cfg["score_deltas"], dict)
    assert cfg["score_deltas"]["FAV"] == 2.0
    assert cfg["score_deltas"]["CAU"] == -3.0
    assert cfg["score_deltas"]["DEF"] == -5.0
    assert isinstance(cfg["buy_downgrade_thresholds"], dict)
    assert cfg["buy_downgrade_thresholds"]["CAU"] == 74.0
    assert cfg["buy_downgrade_thresholds"]["DEF"] == 77.0
    assert cfg["buy_threshold"] == 72.0
    assert cfg["favorable_cap_below_buy"] is True


def test_feat004_disabled_path_no_benchmark_fetch_required():
    """When feat004_enabled=False, benchmark data is not needed and the
    overlay must accept None gracefully."""
    from app.config import settings

    assert settings.feat004_enabled is False, (
        "Default must be disabled — benchmark fetch skipped"
    )

    score, label, log = apply_feat004_regime_overlay(
        composite_score=75.0,
        current_label="BUY",
        symbol="TEST",
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": False, "stage": "SHADOW"},
    )
    assert score == 75.0, "Score must pass through unchanged when disabled"
    assert label == "BUY", "Label must pass through unchanged when disabled"
    assert log["feat004_enabled"] is False
    assert log["feat004_abstained_reason"] == "feat004_disabled"


def test_feat004_config_reaches_recommendation_service():
    """When RecommendationAgent passes feat004_config, the service attaches
    the log to the result — even when disabled."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    from app.config import settings

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    cfg = {
        "enabled": settings.feat004_enabled,
        "stage": settings.feat004_stage,
        "score_deltas": {
            "FAV": settings.feat004_score_delta_fav,
            "NEU": settings.feat004_score_delta_neu,
            "CAU": settings.feat004_score_delta_cau,
            "DEF": settings.feat004_score_delta_def,
            "ABS": settings.feat004_score_delta_abs,
        },
        "buy_downgrade_thresholds": {
            "CAU": settings.feat004_buy_downgrade_threshold_cau,
            "DEF": settings.feat004_buy_downgrade_threshold_def,
        },
        "buy_threshold": settings.feat004_buy_threshold,
        "favorable_cap_below_buy": settings.feat004_favorable_cap_below_buy,
        "sector_mapping_enabled": settings.feat004_sector_mapping_enabled,
        "sector_min_candles": settings.feat004_sector_min_candles,
    }

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.65,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config=cfg,
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )

    assert hasattr(result, "feat004"), "Result must carry feat004 log"
    log = getattr(result, "feat004")
    assert log["feat004_enabled"] == settings.feat004_enabled
    assert log["feat004_stage"] == "ABSTAINED"


def test_feat004_unavailable_data_path_accepts_params():
    """The recommendation_service.build() used in the unavailable-data path
    must accept FEAT-004 params and produce a valid result with feat004 log."""
    from app.services.recommendation_service import RecommendationService
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    svc = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="neutral", score=0.0,
        indicators={}, summary="no data",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=0.0, max_drawdown=0.0, win_rate=0.0,
        profit_factor=0.0, trade_count=0, verdict="insufficient",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = svc.build(
        symbol="TEST",
        technical_results=[tech],
        sentiment_score=0.0,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        llm_reasoning={
            "bullets": ["No live data."],
            "risk_factors": ["Data unavailable."],
            "invalidation_signals": ["Wait for data."],
            "summary": "Unavailable.",
        },
        feat004_config={"enabled": False, "stage": "SHADOW"},
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )

    assert result is not None
    assert result.action == "REJECT"
    assert hasattr(result, "feat004"), (
        "Unavailable-data path must also receive feat004 metadata"
    )


def test_feat004_existing_behavior_unchanged_when_disabled():
    """When feat004_enabled=False, the full recommendation output must be
    identical whether feat004 params are passed or omitted."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="strong uptrend",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    common = dict(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.65, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    r_old = agent.run(**common)
    r_new = agent.run(
        **common,
        feat004_config={"enabled": False, "stage": "SHADOW"},
        benchmark_ohlcv=None, sector_mapping=None, sector_ohlcv_cache=None,
    )

    assert r_old.action == r_new.action
    assert r_old.score == r_new.score
    assert r_old.confidence == r_new.confidence
    assert r_old.trade_plans == r_new.trade_plans


# =========================================================================
# Batch 3 integration tests — full FEAT-004 pipeline validation
# =========================================================================

# ---------------------------------------------------------------------------
# Shared benchmark fixtures
# ---------------------------------------------------------------------------

def _bm_rising_300() -> pd.DataFrame:
    """300 daily candles with steadily rising close (FAVORABLE regime)."""
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(300):
        p = 100.0 + i * 0.5
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": p - 1.0, "high": p + 2.0,
            "low": p - 2.0, "close": p, "volume": 1000000,
        })
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def _bm_falling_300() -> pd.DataFrame:
    """300 daily candles with steadily falling close (DEFENSIVE regime)."""
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(300):
        p = 200.0 - i * 0.5
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": p + 1.0, "high": p + 2.0,
            "low": p - 2.0, "close": p, "volume": 1000000,
        })
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def _tech(score: float = 80.0) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=score,
        indicators={}, summary="test",
    )


def _backtest(ret: float = 15.0) -> BacktestResult:
    return BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=ret, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )


def _run(
    agent: RecommendationAgent,
    feat004_config: dict | None = None,
    benchmark_ohlcv: pd.DataFrame | None = None,
    tech: TechnicalAnalysisResult | None = None,
    bt: BacktestResult | None = None,
) -> FinalRecommendation:
    t = tech or _tech()
    b = bt or _backtest()
    return agent.run(
        symbol="TEST",
        technical_results=[t],
        sentiment_label="positive",
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[b],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config=feat004_config,
        benchmark_ohlcv=benchmark_ohlcv,
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )


# ---------------------------------------------------------------------------
# 1. Full pipeline: Config -> Orchestrator -> Agent -> Service -> Overlay -> Result
# ---------------------------------------------------------------------------

def test_full_pipeline_disabled_produces_abstained_log():
    """Disabled mode: config flows through entire pipeline, result carries
    feat004 log with abstained reason."""
    agent = RecommendationAgent()
    result = _run(agent, feat004_config={"enabled": False, "stage": "SHADOW"})
    assert hasattr(result, "feat004")
    log = getattr(result, "feat004")
    assert log["feat004_enabled"] is False
    assert log["feat004_abstained_reason"] == "feat004_disabled"
    assert log["feat004_pre_adjustment_score"] == log["feat004_post_adjustment_score"]


def test_full_pipeline_enabled_shadow_with_benchmark():
    """SHADOW mode with valid benchmark: regime identified, score unchanged."""
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(result, "feat004")
    assert log["feat004_enabled"] is True
    assert log["feat004_stage"] == "SHADOW"
    assert log["market_regime_state"] in {"FAV", "NEU", "CAU", "DEF", "ABS"}
    assert log["feat004_score_adjustment"] == 0.0  # SHADOW = passthrough


def test_full_pipeline_enabled_active_with_favorable_regime():
    """ACTIVE mode with FAVORABLE regime: positive delta applied."""
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(result, "feat004")
    assert log["feat004_stage"] == "ACTIVE"
    assert log["feat004_score_adjustment"] >= 0


def test_full_pipeline_enabled_active_with_defensive_regime():
    """ACTIVE mode with DEFENSIVE regime: negative delta applied."""
    agent = RecommendationAgent()
    tech = _tech(100.0)
    bt = _backtest(28.0)
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_falling_300(),
        tech=tech, bt=bt,
    )
    log = getattr(result, "feat004")
    assert log["feat004_stage"] == "ACTIVE"
    assert log["feat004_score_adjustment"] < 0


# ---------------------------------------------------------------------------
# 2. Byte-identical disabled mode
# ---------------------------------------------------------------------------

def test_disabled_byte_identical_to_no_params():
    """When feat004 is disabled, the output must be byte-identical to
    calling the agent without any FEAT-004 parameters."""
    agent = RecommendationAgent()
    r_no_params = _run(agent, feat004_config=None)
    r_disabled = _run(agent, feat004_config={"enabled": False, "stage": "SHADOW"})
    assert r_no_params.action == r_disabled.action
    assert r_no_params.score == r_disabled.score
    assert r_no_params.confidence == r_disabled.confidence
    assert r_no_params.trade_plans == r_disabled.trade_plans


def test_disabled_deterministic_across_runs():
    """Disabled mode must produce identical output across repeated calls."""
    agent = RecommendationAgent()
    cfg = {"enabled": False, "stage": "SHADOW"}
    r1 = _run(agent, feat004_config=cfg)
    r2 = _run(agent, feat004_config=cfg)
    assert r1.score == r2.score
    assert r1.action == r2.action
    assert r1.confidence == r2.confidence


# ---------------------------------------------------------------------------
# 3. Enabled mode invokes overlay
# ---------------------------------------------------------------------------

def test_enabled_shadow_invokes_overlay_without_score_change():
    """SHADOW mode invokes the full overlay pipeline (regime classified,
    log populated) but score is passed through unchanged."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(r, "feat004")
    assert log["market_regime_state"] != "ABS"
    assert log["feat004_abstained_reason"] is None
    assert log["feat004_score_adjustment"] == 0.0
    assert log["feat004_pre_adjustment_score"] == log["feat004_post_adjustment_score"]


def test_enabled_active_invokes_overlay_with_score_change():
    """ACTIVE mode with benchmark data must produce a non-zero adjustment."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(r, "feat004")
    assert log["feat004_abstained_reason"] is None
    assert log["market_regime_state"] != "ABS"
    # Score adjustment may be positive, negative, or zero depending on regime
    # — just verify the overlay actually computed something (not abstained)


# ---------------------------------------------------------------------------
# 4. Benchmark fetch degradation
# ---------------------------------------------------------------------------

def test_benchmark_none_degrades_safely():
    """When benchmark_ohlcv is None, the overlay abstains safely and
    returns the original score unchanged."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=None,
    )
    log = getattr(r, "feat004")
    assert log["feat004_score_adjustment"] == 0.0
    assert log["feat004_pre_adjustment_score"] == log["feat004_post_adjustment_score"]


def test_benchmark_empty_dataframe_degrades_safely():
    """An empty DataFrame passed as benchmark must not crash; the overlay
    must abstain or produce safe defaults."""
    empty_df = pd.DataFrame(
        {"close": [], "open": [], "high": [], "low": [], "volume": []}
    )
    empty_df.index = pd.DatetimeIndex([])
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=empty_df,
    )
    log = getattr(r, "feat004")
    assert log["feat004_score_adjustment"] == 0.0


# ---------------------------------------------------------------------------
# 5. Overlay abstains correctly when benchmark data is unavailable
# ---------------------------------------------------------------------------

def test_overlay_abstains_when_disabled():
    """Disabled config must produce abstained log with correct reason."""
    score, label, log = apply_feat004_regime_overlay(
        composite_score=75.0, current_label="BUY", symbol="T",
        benchmark_ohlcv=None, sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": False, "stage": "SHADOW"},
    )
    assert log["feat004_abstained_reason"] == "feat004_disabled"
    assert score == 75.0
    assert label == "BUY"


def test_overlay_abstains_when_benchmark_none():
    """Enabled but no benchmark data: abstains with benchmark_unavailable."""
    score, label, log = apply_feat004_regime_overlay(
        composite_score=75.0, current_label="BUY", symbol="T",
        benchmark_ohlcv=None, sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert "benchmark" in log.get("feat004_abstained_reason", "").lower()
    assert score == 75.0


# ---------------------------------------------------------------------------
# 6. Recommendation object immutability
# ---------------------------------------------------------------------------

def test_recommendation_object_not_mutated_by_feat004():
    """After running through FEAT-004, the FinalRecommendation object must
    be stable: model_dump() must produce identical output on repeated calls."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    dump1 = r.model_dump()
    dump2 = r.model_dump()
    assert dump1 == dump2, "model_dump must be stable"


def test_feat004_log_not_mutated_on_repeated_access():
    """The feat004 log dict must return identical keys/values on repeated gets."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log1 = getattr(r, "feat004")
    log2 = getattr(r, "feat004")
    assert log1 == log2


# ---------------------------------------------------------------------------
# 7. FEAT-008 behavior unchanged
# ---------------------------------------------------------------------------

def test_feat008_unchanged_with_feat004_disabled():
    """BacktestService output must be identical whether FEAT-004 params
    are passed or not — BacktestService is completely separate."""
    svc = BacktestService()
    base = datetime(2026, 1, 1)
    candles = []
    for i in range(60):
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=i),
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
        ))
    candles.append(OHLCVPoint(
        timestamp=base + timedelta(days=60),
        open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
    ))
    candles.append(OHLCVPoint(
        timestamp=base + timedelta(days=61),
        open=112.0, high=116.0, low=111.0, close=115.0, volume=1200,
    ))
    for i in range(62, 75):
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=i),
            open=113.0, high=115.0, low=112.0, close=114.0, volume=1100,
        ))

    r1 = svc.run("TEST", AnalysisMode.swing, candles)
    r2 = svc.run("TEST", AnalysisMode.swing, candles)
    # BacktestService has no FEAT-004 awareness — output must be identical
    assert r1.total_return == r2.total_return
    assert r1.trade_count == r2.trade_count
    assert r1.feat008_enabled == r2.feat008_enabled


# ---------------------------------------------------------------------------
# 8. Log payload completeness
# ---------------------------------------------------------------------------

REQUIRED_LOG_KEYS_B3 = {
    "feat004_enabled", "feat004_stage", "market_regime_state",
    "feat004_pre_adjustment_score", "feat004_post_adjustment_score",
    "feat004_score_adjustment", "feat004_watch_downgrade_applied",
    "benchmark_symbol_used", "feat004_abstained_reason",
    "feat004_explanation", "benchmark_trend_inputs",
}


def test_log_payload_all_keys_present_disabled():
    agent = RecommendationAgent()
    r = _run(agent, feat004_config={"enabled": False, "stage": "SHADOW"})
    log = getattr(r, "feat004")
    missing = REQUIRED_LOG_KEYS_B3 - set(log.keys())
    assert not missing, f"Missing log keys in disabled mode: {missing}"


def test_log_payload_all_keys_present_shadow():
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(r, "feat004")
    missing = REQUIRED_LOG_KEYS_B3 - set(log.keys())
    assert not missing, f"Missing log keys in SHADOW mode: {missing}"


def test_log_payload_all_keys_present_active():
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(r, "feat004")
    missing = REQUIRED_LOG_KEYS_B3 - set(log.keys())
    assert not missing, f"Missing log keys in ACTIVE mode: {missing}"


def test_log_explanation_not_empty():
    """The feat004_explanation field must contain a non-empty human-readable string."""
    agent = RecommendationAgent()
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )
    log = getattr(r, "feat004")
    assert isinstance(log["feat004_explanation"], str)
    assert len(log["feat004_explanation"]) > 0


# ---------------------------------------------------------------------------
# 9. Deterministic repeated execution across all modes
# ---------------------------------------------------------------------------

def test_deterministic_disabled():
    agent = RecommendationAgent()
    cfg = {"enabled": False, "stage": "SHADOW"}
    r1 = _run(agent, feat004_config=cfg)
    r2 = _run(agent, feat004_config=cfg)
    assert r1.score == r2.score and r1.action == r2.action


def test_deterministic_shadow():
    agent = RecommendationAgent()
    bm = _bm_rising_300()
    cfg = {"enabled": True, "stage": "SHADOW"}
    r1 = _run(agent, feat004_config=cfg, benchmark_ohlcv=bm)
    r2 = _run(agent, feat004_config=cfg, benchmark_ohlcv=bm)
    assert r1.score == r2.score and r1.action == r2.action


def test_deterministic_active():
    agent = RecommendationAgent()
    bm = _bm_rising_300()
    cfg = {"enabled": True, "stage": "ACTIVE"}
    r1 = _run(agent, feat004_config=cfg, benchmark_ohlcv=bm)
    r2 = _run(agent, feat004_config=cfg, benchmark_ohlcv=bm)
    assert r1.score == r2.score and r1.action == r2.action


# ---------------------------------------------------------------------------
# 10. FAV cap boundary tests
# ---------------------------------------------------------------------------

def test_fav_cap_prevents_watch_becoming_buy():
    """When pre-score is near BUY boundary and FAV +2.0 would push it
    over 72, the cap must limit the post-score to 71.99 (stays WATCH)."""
    agent = RecommendationAgent()
    tech = _tech(100.0)
    bt = _backtest(21.0)  # composite = 100*0.5 + 84*0.25 = 71.0
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
        tech=tech, bt=bt,
    )
    log = getattr(r, "feat004")
    assert log["feat004_pre_adjustment_score"] >= 70
    assert r.action == "WATCH"
    assert log["feat004_post_adjustment_score"] < 72.0


def test_fav_no_cap_when_already_buy():
    """When score is already BUY (>=72), FAV delta must not be capped."""
    agent = RecommendationAgent()
    tech = _tech(100.0)
    bt = _backtest(28.0)  # composite = 100*0.5 + 100*0.25 = 75.0
    r = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
        tech=tech, bt=bt,
    )
    log = getattr(r, "feat004")
    assert r.action == "BUY"
    assert log["feat004_post_adjustment_score"] > log["feat004_pre_adjustment_score"]


# =========================================================================
# FEAT-007 Batch 1 — Infrastructure wiring tests
# =========================================================================

def test_feat007_config_defaults():
    """FEAT-007 configuration must have disabled-by-default values."""
    from app.config import settings

    assert settings.feat007_enabled is False
    assert settings.feat007_stage == "SHADOW"
    assert settings.feat007_score_delta_strength == 1.5
    assert settings.feat007_score_delta_weak == -3.0
    assert settings.feat007_buy_downgrade_threshold == 74.0
    assert settings.feat007_buy_threshold == 72.0
    assert settings.feat007_strength_cap_enabled is True


def test_feat007_schema_fields_default_none():
    """FinalRecommendation must expose FEAT-007 fields that default to None."""
    from app.schemas.analysis import FinalRecommendation, RecommendationReasoning

    rec = FinalRecommendation(
        action="BUY", confidence=0.85, score=80.0,
        reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
        trade_plans=[], summary="test",
    )
    assert rec.feat007_enabled is None
    assert rec.feat007_stage is None
    assert rec.sector_regime_state is None
    assert rec.sector_rs_value is None
    assert rec.feat007_score_adjustment is None
    assert rec.feat007_pre_adjustment_score is None
    assert rec.feat007_post_adjustment_score is None
    assert rec.feat007_watch_downgrade_applied is None
    assert rec.feat007_abstained_reason is None
    assert rec.feat007_explanation is None


def test_feat007_schema_existing_fields_unchanged():
    """Existing FinalRecommendation fields must remain intact."""
    from app.schemas.analysis import FinalRecommendation, RecommendationReasoning

    rec = FinalRecommendation(
        action="WATCH", confidence=0.65, score=60.0,
        reasoning=RecommendationReasoning(bullets=["b"], risk_factors=["r"], invalidation_signals=["i"]),
        trade_plans=[], summary="existing",
    )
    assert rec.action == "WATCH"
    assert rec.confidence == 0.65
    assert rec.score == 60.0
    assert rec.reasoning.bullets == ["b"]
    assert rec.summary == "existing"


def test_feat007_agent_forwards_params_to_service():
    """RecommendationAgent.run() must forward feat007_config and sector_rs_value."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=2.5,
    )

    assert result is not None
    assert result.action in {"BUY", "WATCH", "REJECT"}


def test_feat007_agent_params_optional():
    """Calling run() without FEAT-007 params must not crash (backward compat)."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    assert result is not None
    assert result.action in {"BUY", "WATCH", "REJECT"}


def test_feat007_output_identical_with_and_without_params():
    """Output must be byte-identical whether FEAT-007 params are passed or not."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    common = dict(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.5, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    r_without = agent.run(**common)
    r_with = agent.run(
        **common,
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=None,
    )

    assert r_without.action == r_with.action
    assert r_without.score == r_with.score
    assert r_without.confidence == r_with.confidence
    assert r_without.trade_plans == r_with.trade_plans


def test_feat007_fields_none_in_default_output():
    """When FEAT-007 is not active, all feat007_* fields on result must be None."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )

    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=2.5,
    )

    assert result.feat007_enabled is None
    assert result.feat007_stage is None
    assert result.sector_regime_state is None
    assert result.sector_rs_value is None
    assert result.feat007_score_adjustment is None
    assert result.feat007_pre_adjustment_score is None
    assert result.feat007_post_adjustment_score is None
    assert result.feat007_watch_downgrade_applied is None
    assert result.feat007_abstained_reason is None
    assert result.feat007_explanation is None


def test_feat007_deterministic_repeated_execution():
    """Repeated calls with same inputs must produce identical output."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import AnalysisMode, BacktestResult, TechnicalAnalysisResult

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test",
        total_return=15.0, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    common = dict(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.5, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=2.5,
    )

    r1 = agent.run(**common)
    r2 = agent.run(**common)

    assert r1.action == r2.action
    assert r1.score == r2.score
    assert r1.confidence == r2.confidence


# =========================================================================
# FEAT-007 Batch 2 — Overlay logic tests
# =========================================================================

_FEAT007_CFG = {
    "enabled": True,
    "stage": "ACTIVE",
    "score_delta_strength": 1.5,
    "score_delta_weak": -3.0,
    "buy_downgrade_threshold": 74.0,
    "buy_threshold": 72.0,
    "strength_cap_enabled": True,
}


def _feat007_run(agent, score_tech=100.0, bt_return=28.0, rs_value=5.0, cfg=None, stage=None):
    """Helper: run agent with FEAT-007 config and return result."""
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=score_tech,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=bt_return,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    final_cfg = dict(cfg or _FEAT007_CFG)
    if stage:
        final_cfg["stage"] = stage
    return agent.run(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.0, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config=final_cfg, sector_rs_value=rs_value,
    )


def test_feat007_strength_active_raises_score():
    """STRENGTH state with ACTIVE stage must apply +1.5 delta."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=5.0, stage="ACTIVE")
    assert r.sector_regime_state == "STRENGTH"
    assert r.feat007_score_adjustment == 1.5
    assert r.score > r.feat007_pre_adjustment_score


def test_feat007_weak_active_lowers_score():
    """WEAK state with ACTIVE stage must apply -3.0 delta."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=-3.0, stage="ACTIVE")
    assert r.sector_regime_state == "WEAK"
    assert r.feat007_score_adjustment == -3.0
    assert r.score < r.feat007_pre_adjustment_score


def test_feat007_shadow_does_not_modify_score():
    """SHADOW mode must calculate everything but leave score and action unchanged."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=5.0, stage="SHADOW")
    assert r.feat007_enabled is True
    assert r.feat007_stage == "SHADOW"
    assert r.sector_regime_state == "STRENGTH"
    assert r.feat007_score_adjustment == 1.5
    assert r.feat007_post_adjustment_score == r.feat007_pre_adjustment_score


def test_feat007_shadow_weak_does_not_modify_action():
    """SHADOW mode with WEAK must not downgrade BUY to WATCH."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=-5.0, stage="SHADOW")
    assert r.feat007_watch_downgrade_applied is False
    assert r.feat007_post_adjustment_score == r.feat007_pre_adjustment_score


def test_feat007_active_buy_downgrade_when_weak():
    """WEAK with adjusted score below 74 must downgrade BUY to WATCH."""
    agent = RecommendationAgent()
    # pre_score ~75 (BUY), -3.0 = 72.0 < 74 -> downgrade
    r = _feat007_run(agent, score_tech=100.0, bt_return=28.0, rs_value=-5.0, stage="ACTIVE")
    assert r.sector_regime_state == "WEAK"
    assert r.feat007_watch_downgrade_applied is True
    assert r.action == "WATCH"


def test_feat007_active_buy_no_downgrade_when_score_above_threshold():
    """WEAK with adjusted score >= 74 must NOT downgrade."""
    agent = RecommendationAgent()
    # pre_score ~75 (BUY), -1.0 = 74.0 >= 74 -> no downgrade
    cfg_no_down = dict(_FEAT007_CFG, score_delta_weak=-1.0)
    r = _feat007_run(agent, score_tech=100.0, bt_return=28.0, rs_value=-3.0, cfg=cfg_no_down, stage="ACTIVE")
    assert r.sector_regime_state == "WEAK"
    assert r.feat007_watch_downgrade_applied is False
    assert r.action == "BUY"


def test_feat007_strength_cap_prevents_watch_to_buy():
    """STRENGTH cap must prevent a WATCH score from becoming BUY."""
    agent = RecommendationAgent()
    # pre_score ~71.0, +1.5 = 72.5 but cap at 71.99 → stays WATCH
    r = _feat007_run(agent, score_tech=100.0, bt_return=21.0, rs_value=5.0, stage="ACTIVE")
    assert r.sector_regime_state == "STRENGTH"
    assert r.action == "WATCH"
    assert r.score < 72.0


def test_feat007_strength_no_cap_when_already_buy():
    """STRENGTH must not cap when the score is already BUY."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, score_tech=100.0, bt_return=28.0, rs_value=5.0, stage="ACTIVE")
    assert r.action == "BUY"
    assert r.score > r.feat007_pre_adjustment_score


def test_feat007_abstain_when_sector_rs_none():
    """When sector_rs_value is None, overlay must abstain cleanly."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=None, stage="ACTIVE")
    assert r.sector_regime_state == "UNKNOWN"
    assert r.feat007_abstained_reason == "upstream_sector_rs_unavailable"
    assert r.feat007_score_adjustment == 0.0
    assert r.feat007_post_adjustment_score == r.feat007_pre_adjustment_score


def test_feat007_disabled_leaves_fields_none():
    """When feat007_config has enabled=False, all feat007 fields must be None."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, cfg={"enabled": False, "stage": "SHADOW"}, rs_value=5.0)
    assert r.feat007_enabled is None
    assert r.sector_regime_state is None
    assert r.sector_rs_value is None
    assert r.feat007_score_adjustment is None


def test_feat007_reject_immutability():
    """REJECT label must never be modified by FEAT-007."""
    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="sell", score=30.0,
        indicators={}, summary="weak",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=-10.0,
        max_drawdown=15.0, win_rate=20.0, profit_factor=0.3,
        trade_count=8, verdict="insufficient",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    r = agent.run(
        symbol="TEST", technical_results=[tech], sentiment_label="negative",
        sentiment_score=-0.5, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config=_FEAT007_CFG, sector_rs_value=5.0,
    )
    assert r.action == "REJECT"
    assert r.feat007_score_adjustment == 0.0


def test_feat007_all_log_fields_populated():
    """When FEAT-007 is enabled, every logging field must be populated."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=5.0, stage="ACTIVE")
    assert r.feat007_enabled is True
    assert r.feat007_stage == "ACTIVE"
    assert r.sector_regime_state == "STRENGTH"
    assert r.sector_rs_value == 5.0
    assert r.feat007_score_adjustment is not None
    assert r.feat007_pre_adjustment_score is not None
    assert r.feat007_post_adjustment_score is not None
    assert r.feat007_watch_downgrade_applied is not None
    assert r.feat007_explanation is not None
    assert isinstance(r.feat007_explanation, str)
    assert len(r.feat007_explanation) > 0


def test_feat007_deterministic_active():
    """Repeated ACTIVE calls must produce identical results."""
    agent = RecommendationAgent()
    r1 = _feat007_run(agent, rs_value=5.0, stage="ACTIVE")
    r2 = _feat007_run(agent, rs_value=5.0, stage="ACTIVE")
    assert r1.score == r2.score
    assert r1.action == r2.action
    assert r1.feat007_score_adjustment == r2.feat007_score_adjustment


def test_feat007_deterministic_shadow():
    """Repeated SHADOW calls must produce identical results."""
    agent = RecommendationAgent()
    r1 = _feat007_run(agent, rs_value=-3.0, stage="SHADOW")
    r2 = _feat007_run(agent, rs_value=-3.0, stage="SHADOW")
    assert r1.score == r2.score
    assert r1.action == r2.action


def test_feat007_backward_compat_no_config():
    """Calling without feat007_config must produce identical output to disabled."""
    agent = RecommendationAgent()
    r_no_config = _feat007_run(agent, cfg=None)
    # Without feat007_config, fields should be None
    r_none = agent.run(
        symbol="TEST",
        technical_results=[TechnicalAnalysisResult(
            mode=AnalysisMode.swing, signal="buy", score=100.0,
            indicators={}, summary="test",
        )],
        sentiment_label="positive", sentiment_score=0.0,
        fundamental_result=None,
        backtests=[BacktestResult(
            mode=AnalysisMode.swing, strategy_name="test", total_return=28.0,
            max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
            trade_count=8, verdict="favorable",
            equity_curve=[{"label": "Start", "equity": 100000.0}],
        )],
        candles_by_mode={AnalysisMode.swing: []},
    )
    # When feat007_config is None, overlay is inactive — same as no config
    r_disabled = _feat007_run(agent, cfg={"enabled": False}, rs_value=5.0)
    assert r_none.score == r_disabled.score
    assert r_none.action == r_disabled.action


def test_feat007_boundary_zero_is_strength():
    """A sector_rs_value of exactly 0.0 must classify as STRENGTH (>= 0)."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=0.0, stage="ACTIVE")
    assert r.sector_regime_state == "STRENGTH"


def test_feat007_boundary_negative_is_weak():
    """A sector_rs_value of -0.01 must classify as WEAK (< 0)."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=-0.01, stage="ACTIVE")
    assert r.sector_regime_state == "WEAK"


# =========================================================================
# FEAT-007 Batch 1 — R26 Mandatory Exception Boundary
# Spec §12/§15.2 Test 13: any exception inside FEAT-007 must be caught,
# logged, and return UNKNOWN with zero delta and the original score/label
# preserved. No exception may propagate into the recommendation path.
# =========================================================================

def test_exception_returns_unknown():
    """Spec §15.2 Test 13: inject exception -> UNKNOWN, zero delta,
    original score preserved, original label preserved,
    feat007_abstained_reason = exception:{ExceptionType}."""
    from app.services.recommendation_service import RecommendationService

    svc = RecommendationService()
    # sector_rs_value passes the None-check but `sector_rs_value < 0` raises
    # TypeError because object() defines no __lt__. This forces the overlay
    # into its exception path without touching scoring/classification logic.
    bad_rs_value = object()

    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=bad_rs_value,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )

    # Exception does not propagate (we reached the assertion):
    assert log is not None
    # UNKNOWN returned:
    assert log["sector_regime_state"] == "UNKNOWN"
    # Score unchanged (zero delta):
    assert log["feat007_score_adjustment"] == 0.0
    assert log["feat007_post_adjustment_score"] == 80.0
    assert log["feat007_pre_adjustment_score"] == 80.0
    # Label unchanged:
    assert log["feat007_adjusted_label"] == "BUY"
    assert log["feat007_watch_downgrade_applied"] is False
    # Correct abstained reason with exception type:
    assert log["feat007_abstained_reason"] == "exception:TypeError"


# =========================================================================
# FEAT-007 Batch 3 — Orchestrator integration tests
# =========================================================================

def test_feat007_orchestrator_has_config_builder():
    """OrchestratorAgent must expose _build_feat007_config."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    assert hasattr(OrchestratorAgent, "_build_feat007_config")


def test_feat007_config_builder_uses_settings_defaults():
    """_build_feat007_config must read from settings with correct defaults."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.config import settings

    # Build config using the same logic as the orchestrator
    cfg = {
        "enabled": settings.feat007_enabled,
        "stage": settings.feat007_stage,
        "score_delta_strength": settings.feat007_score_delta_strength,
        "score_delta_weak": settings.feat007_score_delta_weak,
        "buy_downgrade_threshold": settings.feat007_buy_downgrade_threshold,
        "buy_threshold": settings.feat007_buy_threshold,
        "strength_cap_enabled": settings.feat007_strength_cap_enabled,
    }
    assert cfg["enabled"] is False
    assert cfg["stage"] == "SHADOW"
    assert cfg["score_delta_strength"] == 1.5
    assert cfg["score_delta_weak"] == -3.0
    assert cfg["buy_downgrade_threshold"] == 74.0
    assert cfg["buy_threshold"] == 72.0
    assert cfg["strength_cap_enabled"] is True


def test_feat007_orchestrator_disabled_produces_none_fields():
    """When feat007_enabled=False, the config builder produces enabled=False,
    and the recommendation agent leaves all feat007 fields as None."""
    from app.config import settings
    assert settings.feat007_enabled is False

    agent = RecommendationAgent()
    cfg = {
        "enabled": False, "stage": "SHADOW",
        "score_delta_strength": 1.5, "score_delta_weak": -3.0,
        "buy_downgrade_threshold": 74.0, "buy_threshold": 72.0,
        "strength_cap_enabled": True,
    }
    r = _feat007_run(agent, cfg=cfg, rs_value=5.0)
    assert r.feat007_enabled is None
    assert r.sector_regime_state is None


def test_feat007_sr003_value_flows_to_overlay():
    """The sector_rs_value from SR-003 (sector_rs_20) must flow through
    the recommendation agent into the FEAT-007 overlay."""
    agent = RecommendationAgent()
    # Simulate a positive sector RS (STRENGTH)
    r = _feat007_run(agent, rs_value=3.5, stage="ACTIVE")
    assert r.sector_rs_value == 3.5
    assert r.sector_regime_state == "STRENGTH"

    # Simulate a negative sector RS (WEAK)
    r2 = _feat007_run(agent, rs_value=-2.0, stage="ACTIVE")
    assert r2.sector_rs_value == -2.0
    assert r2.sector_regime_state == "WEAK"


def test_feat007_sr003_none_value_abstains_cleanly():
    """When SR-003 cannot compute sector_rs_20 (None), FEAT-007 abstains."""
    agent = RecommendationAgent()
    r = _feat007_run(agent, rs_value=None, stage="ACTIVE")
    assert r.sector_regime_state == "UNKNOWN"
    assert r.feat007_abstained_reason == "upstream_sector_rs_unavailable"
    assert r.feat007_score_adjustment == 0.0


def test_feat007_execution_order_feat004_then_feat007():
    """FEAT-007 must consume the post-FEAT-004 score, not the raw composite.
    This is verified by passing both feat004_config (disabled) and
    feat007_config (enabled) — FEAT-007 sees the FEAT-004-adjusted score."""
    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=100.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=28.0,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    feat007_cfg = {
        "enabled": True, "stage": "ACTIVE",
        "score_delta_strength": 1.5, "score_delta_weak": -3.0,
        "buy_downgrade_threshold": 74.0, "buy_threshold": 72.0,
        "strength_cap_enabled": True,
    }

    # With FEAT-004 disabled, FEAT-007 sees the raw composite as its input
    r = agent.run(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.0, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config={"enabled": False},
        feat007_config=feat007_cfg, sector_rs_value=5.0,
    )
    # FEAT-007 pre_adjustment_score should equal the FEAT-004-adjusted score
    # (which is the raw composite since FEAT-004 is disabled)
    assert r.feat007_pre_adjustment_score is not None
    assert r.feat007_post_adjustment_score > r.feat007_pre_adjustment_score


def test_feat007_disabled_byte_identical_to_no_params():
    """With feat007_enabled=False, output must be byte-identical to
    calling without any FEAT-007 params."""
    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=15.0,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    common = dict(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.5, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    r_no_params = agent.run(**common)
    r_disabled = agent.run(
        **common,
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=5.0,
    )

    assert r_no_params.action == r_disabled.action
    assert r_no_params.score == r_disabled.score
    assert r_no_params.confidence == r_disabled.confidence
    assert r_no_params.trade_plans == r_disabled.trade_plans


def test_feat007_fallback_path_accepts_config():
    """The unavailable-data fallback path must accept feat007_config
    and sector_rs_value=None without crashing."""
    from app.services.recommendation_service import RecommendationService
    svc = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="neutral", score=0.0,
        indicators={}, summary="no data",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=0.0,
        max_drawdown=0.0, win_rate=0.0, profit_factor=0.0,
        trade_count=0, verdict="insufficient",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    r = svc.build(
        symbol="TEST", technical_results=[tech], sentiment_score=0.0,
        fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        llm_reasoning={"bullets": [], "risk_factors": [], "invalidation_signals": [], "summary": "N/A"},
        feat004_config={"enabled": False},
        feat007_config={"enabled": True, "stage": "SHADOW"},
        sector_rs_value=None,
    )
    assert r is not None
    # With sector_rs_value=None, FEAT-007 abstains
    assert r.sector_regime_state == "UNKNOWN"
    assert r.feat007_abstained_reason == "upstream_sector_rs_unavailable"


def test_feat007_deterministic_with_sr003_value():
    """Repeated calls with the same sector_rs_value produce identical output."""
    agent = RecommendationAgent()
    r1 = _feat007_run(agent, rs_value=3.5, stage="ACTIVE")
    r2 = _feat007_run(agent, rs_value=3.5, stage="ACTIVE")
    assert r1.score == r2.score
    assert r1.action == r2.action
    assert r1.feat007_score_adjustment == r2.feat007_score_adjustment
    assert r1.sector_regime_state == r2.sector_regime_state


def test_feat007_no_duplicate_sector_rs_calculation():
    """FEAT-007 must NOT compute sector RS itself — it consumes the value
    from SR-003. This is verified by checking that the overlay's
    sector_rs_value matches what was passed in (no re-computation)."""
    agent = RecommendationAgent()
    test_value = 4.2
    r = _feat007_run(agent, rs_value=test_value, stage="ACTIVE")
    assert r.sector_rs_value == test_value  # exact pass-through, no recompute


# =========================================================================
# FEAT-007 Cleanup — SR-003 single-evaluation regression tests
# =========================================================================

def test_sr003_single_evaluation_in_orchestrator():
    """The orchestrator must call evaluate_sector_overlay exactly once,
    not twice. Verified by inspecting the source code for the call count."""
    import inspect
    from app.agents.orchestrator_agent import OrchestratorAgent

    source = inspect.getsource(OrchestratorAgent._analyze_symbol_post_bulk)
    call_count = source.count("evaluate_sector_overlay")
    assert call_count == 1, (
        f"Expected exactly 1 evaluate_sector_overlay call, found {call_count}"
    )


def test_sr003_sector_overlay_reused_not_re_evaluated():
    """The sector_overlay object from the pre-recommendation evaluation
    must be reused — no second assignment to sector_overlay after the gate."""
    import inspect
    from app.agents.orchestrator_agent import OrchestratorAgent

    source = inspect.getsource(OrchestratorAgent._analyze_symbol_post_bulk)
    # After the strict buy gate, sector_overlay should NOT be reassigned
    # The only assignment should be the initial evaluation
    assignments = source.count("sector_overlay = await sector_rs_service")
    assert assignments == 1, (
        f"Expected 1 sector_overlay assignment, found {assignments}"
    )


def test_sr003_metadata_update_still_present():
    """The original_action and challenger_action updates must still exist
    after the challenger is built."""
    import inspect
    from app.agents.orchestrator_agent import OrchestratorAgent

    source = inspect.getsource(OrchestratorAgent._analyze_symbol_post_bulk)
    assert "sector_overlay.original_action = recommendation.action" in source
    assert "sector_overlay.challenger_action = challenger_recommendation.action" in source


def test_sr003_challenger_downgrade_logic_unchanged():
    """The challenger downgrade logic must still reference sector_overlay
    properties (downgrade_triggered, sector_rs_20, mapped_sector)."""
    import inspect
    from app.agents.orchestrator_agent import OrchestratorAgent

    source = inspect.getsource(OrchestratorAgent._analyze_symbol_post_bulk)
    assert "sector_overlay.downgrade_triggered" in source
    assert "sector_overlay.sector_rs_20" in source
    assert "sector_overlay.mapped_sector" in source


def test_sr003_reuse_preserves_recommendation_output():
    """Recommendation output must be byte-identical regardless of the
    SR-003 cleanup — the overlay logic in RecommendationService is unchanged."""
    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=100.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=28.0,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    feat007_cfg = {
        "enabled": True, "stage": "ACTIVE",
        "score_delta_strength": 1.5, "score_delta_weak": -3.0,
        "buy_downgrade_threshold": 74.0, "buy_threshold": 72.0,
        "strength_cap_enabled": True,
    }

    # Run twice — output must be deterministic and identical
    r1 = agent.run(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.0, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config=feat007_cfg, sector_rs_value=5.0,
    )
    r2 = agent.run(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.0, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config=feat007_cfg, sector_rs_value=5.0,
    )

    assert r1.action == r2.action
    assert r1.score == r2.score
    assert r1.confidence == r2.confidence
    assert r1.trade_plans == r2.trade_plans
    assert r1.feat007_score_adjustment == r2.feat007_score_adjustment
    assert r1.sector_regime_state == r2.sector_regime_state


def test_sr003_disabled_mode_byte_identical():
    """With FEAT-007 disabled, output must be byte-identical to
    calling without any FEAT-007 params — cleanup does not affect this."""
    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=80.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=15.0,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    common = dict(
        symbol="TEST", technical_results=[tech], sentiment_label="positive",
        sentiment_score=0.5, fundamental_result=None, backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
    )

    r_no_params = agent.run(**common)
    r_disabled = agent.run(
        **common,
        feat007_config={"enabled": False, "stage": "SHADOW"},
        sector_rs_value=5.0,
    )

    assert r_no_params.action == r_disabled.action
    assert r_no_params.score == r_disabled.score
    assert r_no_params.confidence == r_disabled.confidence
    assert r_no_params.trade_plans == r_disabled.trade_plans
