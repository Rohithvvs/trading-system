"""
FEAT-004 — Market Regime Overlay
Module: backend/app/services/feat004_regime_overlay.py

FEAT-004 is a synthesis-layer overlay only. It may adjust the final composite
recommendation score and label, but it must NEVER mutate the raw technical score
consumed by the Strict Buy Gate.

Classification:
  Primary Component : COMP-REC (RecommendationService synthesis layer)
  Secondary Component: COMP-EXP (sector-strength metadata, explanation-only in v1)
  Primary Situation  : SIT-BMR  (Broad Market Regime)
  Secondary Situation: SIT-SR   (Sector Regime, optional metadata)

Stage A (SHADOW) : compute all metadata, log everything, zero score effect.
Stage B (ACTIVE) : apply regime score deltas and optional BUY->WATCH downgrades.
Rollback         : set feat004_stage = "SHADOW" in config. No code change needed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger("app.feat004_regime_overlay")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
BenchmarkResult = tuple["pd.DataFrame | None", "str | None", "str | None"]
IndicatorDict = dict[str, Any]
SectorResult = dict[str, Any]
LogPayload = dict[str, Any]
OverlayResult = tuple[float, str, LogPayload]


# ---------------------------------------------------------------------------
# Helper 1: resolve_benchmark_ohlcv
# ---------------------------------------------------------------------------
def resolve_benchmark_ohlcv(
    benchmark_symbols: list[str],
    min_candles: int,
    staleness_limit_days: int,
    data_fetcher: Any,
) -> BenchmarkResult:
    """
    Fetch benchmark index OHLCV from the existing data layer.

    Returns:
        (DataFrame, symbol_used, failure_reason)
        On success : (df, "NIFTY500", None)
        On failure : (None, None, reason_string)

    Failure reasons:
        benchmark_fetch_failed
        insufficient_benchmark_history
        benchmark_data_stale

    Never raises.
    """
    for symbol in benchmark_symbols:
        try:
            df: pd.DataFrame | None = data_fetcher(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FEAT-004 benchmark fetch exception for %s: %s", symbol, exc
            )
            continue

        if df is None or df.empty:
            logger.debug("FEAT-004: %s returned empty DataFrame; trying next symbol.", symbol)
            continue

        # Minimum candle check
        if len(df) < min_candles:
            logger.warning(
                "FEAT-004: %s has %d candles, need %d.", symbol, len(df), min_candles
            )
            return None, None, "insufficient_benchmark_history"

        # Staleness check: examine last row index value
        try:
            last_ts = df.index[-1]
            if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            age_days = (now_utc - last_ts).days
            if age_days > staleness_limit_days:
                logger.warning(
                    "FEAT-004: %s last candle is %d day(s) old (limit=%d).",
                    symbol,
                    age_days,
                    staleness_limit_days,
                )
                return None, None, "benchmark_data_stale"
        except Exception as exc:  # noqa: BLE001
            logger.warning("FEAT-004: staleness check failed for %s: %s", symbol, exc)
            # If we cannot determine staleness, treat as stale to be safe.
            return None, None, "benchmark_data_stale"

        # Passed all checks
        return df, symbol, None

    return None, None, "benchmark_fetch_failed"


# ---------------------------------------------------------------------------
# Helper 2: compute_benchmark_indicators
# ---------------------------------------------------------------------------
def compute_benchmark_indicators(ohlcv_df: pd.DataFrame) -> IndicatorDict:
    """
    Compute benchmark trend inputs from OHLCV DataFrame.

    Returns a dict with exactly these keys:
        bm_close, bm_sma50, bm_sma200, bm_sma20_slope, bm_roc20,
        bm_above_sma50, bm_sma50_above_sma200, bm_sma20_slope_positive,
        bm_roc20_positive

    Uses iloc, not date-based indexing.
    On any partial failure, numeric fields default to 0.0 and booleans to False.
    Never raises.
    """
    defaults: IndicatorDict = {
        "bm_close": 0.0,
        "bm_sma50": 0.0,
        "bm_sma200": 0.0,
        "bm_sma20_slope": 0.0,
        "bm_roc20": 0.0,
        "bm_above_sma50": False,
        "bm_sma50_above_sma200": False,
        "bm_sma20_slope_positive": False,
        "bm_roc20_positive": False,
    }

    try:
        close = ohlcv_df["close"].astype(float)
        n = len(close)

        # Require minimum rows for SMA200
        if n < 200:
            logger.warning("FEAT-004: Only %d rows; need 200 for SMA200.", n)
            return defaults.copy()

        bm_close = float(close.iloc[-1])
        bm_sma50 = float(close.iloc[-50:].mean())
        bm_sma200 = float(close.iloc[-200:].mean())

        # SMA20 slope: (SMA20[-1] - SMA20[-6]) / SMA20[-6]
        sma20_today = float(close.iloc[-20:].mean())
        sma20_5ago = float(close.iloc[-25:-5].mean())  # 5 bars ago window
        if sma20_5ago != 0.0:
            bm_sma20_slope = (sma20_today - sma20_5ago) / sma20_5ago
        else:
            bm_sma20_slope = 0.0

        # ROC20: (close[-1] - close[-21]) / close[-21]
        if n >= 21:
            close_21ago = float(close.iloc[-21])
            bm_roc20 = (bm_close - close_21ago) / close_21ago if close_21ago != 0.0 else 0.0
        else:
            bm_roc20 = 0.0

        return {
            "bm_close": bm_close,
            "bm_sma50": bm_sma50,
            "bm_sma200": bm_sma200,
            "bm_sma20_slope": bm_sma20_slope,
            "bm_roc20": bm_roc20,
            "bm_above_sma50": bm_close > bm_sma50,
            "bm_sma50_above_sma200": bm_sma50 > bm_sma200,
            "bm_sma20_slope_positive": bm_sma20_slope > 0.0,
            "bm_roc20_positive": bm_roc20 > 0.0,
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning("FEAT-004: compute_benchmark_indicators failed: %s", exc)
        return defaults.copy()


# ---------------------------------------------------------------------------
# Helper 3: classify_market_regime
# ---------------------------------------------------------------------------
def classify_market_regime(indicators: IndicatorDict | None) -> str:
    """
    Map benchmark indicators to one discrete regime code.

    Return values: "FAV" | "NEU" | "CAU" | "DEF" | "ABS"

    Priority (top-to-bottom, first match wins):
      1. indicators is None            -> ABS
      2. All four bullish signals true  -> FAV
      3. SMA cross OK, slope/ROC mixed  -> NEU
      4. Full bear structure             -> DEF  (more specific than CAU)
      5. Broader caution                -> CAU
      6. Default tie-break              -> NEU

    Never raises; returns ABS on exception.
    """
    try:
        if indicators is None:
            return "ABS"

        above_sma50: bool = bool(indicators.get("bm_above_sma50", False))
        sma50_above_sma200: bool = bool(indicators.get("bm_sma50_above_sma200", False))
        slope_positive: bool = bool(indicators.get("bm_sma20_slope_positive", False))
        roc20_positive: bool = bool(indicators.get("bm_roc20_positive", False))

        # 1. Fully bullish
        if above_sma50 and sma50_above_sma200 and slope_positive and roc20_positive:
            return "FAV"

        # 2. SMA cross intact but momentum weakening
        if above_sma50 and sma50_above_sma200:
            return "NEU"

        # 3. Full bear structure (DEF must be checked BEFORE broader CAU)
        if not above_sma50 and not sma50_above_sma200 and not slope_positive:
            return "DEF"

        # 4. Broader caution
        if not above_sma50:
            return "CAU"
        if not sma50_above_sma200:
            return "CAU"

        # 5. Tie-break default: conservative but not alarming
        return "NEU"

    except Exception as exc:  # noqa: BLE001
        logger.error("FEAT-004: classify_market_regime exception: %s", exc)
        return "ABS"


# ---------------------------------------------------------------------------
# Helper 4: apply_regime_score_modifier
# ---------------------------------------------------------------------------
def apply_regime_score_modifier(
    regime_state: str,
    composite_score: float,
    current_label: str,
    stage: str,
    score_deltas: dict[str, float],
    downgrade_thresholds: dict[str, float],
    buy_threshold: float,
    favorable_cap_below_buy: bool = True,
) -> tuple[float, str, bool, float]:
    """
    Compute score delta and optional BUY->WATCH downgrade decision.

    Returns:
        (adjusted_score, adjusted_label, downgrade_applied, score_delta_applied)

    Label rules:
        - REJECT is never upgraded by FEAT-004.
        - BUY can be downgraded to WATCH only if adj_score falls below the regime threshold.
        - WATCH remains WATCH (regime cannot upgrade it).
        - In SHADOW mode, original values are returned immediately.

    Never raises; returns original values and zero delta on exception.
    """
    try:
        # Shadow mode: zero effect
        if stage == "SHADOW":
            return composite_score, current_label, False, 0.0

        raw_delta: float = score_deltas.get(regime_state, 0.0)

        # Apply FAVORABLE cap: bonus must not push a WATCH-class score to BUY
        if regime_state == "FAV" and favorable_cap_below_buy and composite_score < buy_threshold:
            adjusted_score = min(composite_score + raw_delta, buy_threshold - 0.01)
        else:
            adjusted_score = composite_score + raw_delta

        # Clamp to [0, 100]
        adjusted_score = round(max(0.0, min(100.0, adjusted_score)), 2)

        # Evaluate BUY->WATCH downgrade
        adjusted_label = current_label
        downgrade_applied = False

        if current_label == "BUY" and regime_state in downgrade_thresholds:
            threshold = downgrade_thresholds[regime_state]
            if adjusted_score < threshold:
                adjusted_label = "WATCH"
                downgrade_applied = True

        # REJECT must never be upgraded
        # (No upgrade logic exists, but make the contract explicit.)
        if current_label == "REJECT":
            adjusted_label = "REJECT"
            downgrade_applied = False

        return adjusted_score, adjusted_label, downgrade_applied, raw_delta

    except Exception as exc:  # noqa: BLE001
        logger.error("FEAT-004: apply_regime_score_modifier exception: %s", exc)
        return composite_score, current_label, False, 0.0


# ---------------------------------------------------------------------------
# Helper 5: compute_sector_strength (optional, v1 metadata only)
# ---------------------------------------------------------------------------
def compute_sector_strength(
    symbol: str,
    sector_mapping: dict[str, str] | None,
    sector_ohlcv_cache: dict[str, pd.DataFrame] | None,
    benchmark_roc20: float | None,
    min_candles: int = 50,
) -> SectorResult:
    """
    Compute metadata-only sector relative strength.

    v1 contract: this function MUST NOT change the recommendation score or label.

    Returns a dict with exactly these keys:
        sector_mapped, sector_index_symbol, sector_roc20,
        relative_strength_ratio, sector_regime_state,
        feat004_sector_abstained_reason

    sector_regime_state: "STRONG" | "NEUTRAL" | "WEAK" | "UNKNOWN"
    Never raises.
    """
    unknown_result: SectorResult = {
        "sector_mapped": False,
        "sector_index_symbol": None,
        "sector_roc20": None,
        "relative_strength_ratio": None,
        "sector_regime_state": "UNKNOWN",
        "feat004_sector_abstained_reason": None,
    }

    try:
        if sector_mapping is None:
            unknown_result["feat004_sector_abstained_reason"] = "no_sector_mapping_config"
            return unknown_result

        sector_index_symbol: str | None = sector_mapping.get(symbol)
        if sector_index_symbol is None:
            unknown_result["feat004_sector_abstained_reason"] = "symbol_not_in_mapping"
            return unknown_result

        if sector_ohlcv_cache is None or sector_index_symbol not in sector_ohlcv_cache:
            unknown_result["feat004_sector_abstained_reason"] = "sector_index_unavailable"
            unknown_result["sector_index_symbol"] = sector_index_symbol
            return unknown_result

        sector_df: pd.DataFrame = sector_ohlcv_cache[sector_index_symbol]

        if sector_df is None or sector_df.empty or len(sector_df) < min_candles:
            unknown_result["feat004_sector_abstained_reason"] = "insufficient_sector_history"
            unknown_result["sector_index_symbol"] = sector_index_symbol
            unknown_result["sector_mapped"] = True
            return unknown_result

        close = sector_df["close"].astype(float)
        n = len(close)
        if n < 21:
            unknown_result["feat004_sector_abstained_reason"] = "insufficient_sector_history"
            unknown_result["sector_index_symbol"] = sector_index_symbol
            unknown_result["sector_mapped"] = True
            return unknown_result

        sector_close_today = float(close.iloc[-1])
        sector_close_20ago = float(close.iloc[-21])
        if sector_close_20ago == 0.0:
            sector_roc20 = 0.0
        else:
            sector_roc20 = (sector_close_today - sector_close_20ago) / sector_close_20ago

        # Safe divide: if benchmark ROC is missing or zero, ratio = 1.0 (neutral)
        bm_roc = benchmark_roc20 if (benchmark_roc20 is not None and benchmark_roc20 != 0.0) else None
        if bm_roc is None:
            relative_strength_ratio = 1.0
            logger.debug(
                "FEAT-004 sector: benchmark_roc20 is None or zero; "
                "setting relative_strength_ratio=1.0 (neutral)."
            )
        else:
            relative_strength_ratio = round(sector_roc20 / bm_roc, 4)

        # Classify sector regime
        if relative_strength_ratio > 1.10:
            sector_regime_state = "STRONG"
        elif relative_strength_ratio >= 0.90:
            sector_regime_state = "NEUTRAL"
        else:
            sector_regime_state = "WEAK"

        return {
            "sector_mapped": True,
            "sector_index_symbol": sector_index_symbol,
            "sector_roc20": round(sector_roc20, 6),
            "relative_strength_ratio": relative_strength_ratio,
            "sector_regime_state": sector_regime_state,
            "feat004_sector_abstained_reason": None,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("FEAT-004: compute_sector_strength exception: %s", exc)
        unknown_result["feat004_sector_abstained_reason"] = f"exception:{type(exc).__name__}"
        return unknown_result


# ---------------------------------------------------------------------------
# Helper 6: build_feat004_log_payload
# ---------------------------------------------------------------------------
def build_feat004_log_payload(
    *,
    feat004_enabled: bool,
    stage: str,
    regime_state: str,
    symbol_used: str | None,
    indicators: IndicatorDict | None,
    pre_score: float,
    delta: float,
    post_score: float,
    downgrade_applied: bool,
    abstained_reason: str | None,
    sector_result: SectorResult,
) -> LogPayload:
    """
    Assemble the complete FEAT-004 log dict.

    All fields are always present. Missing values are explicitly None.
    Never raises; on exception returns a minimal valid dict.
    """
    try:
        # Build benchmark_trend_inputs sub-dict
        if indicators:
            trend_inputs = {
                "bm_close": indicators.get("bm_close"),
                "bm_sma50": indicators.get("bm_sma50"),
                "bm_sma200": indicators.get("bm_sma200"),
                "bm_above_sma50": indicators.get("bm_above_sma50"),
                "bm_sma50_above_sma200": indicators.get("bm_sma50_above_sma200"),
                "bm_sma20_slope": indicators.get("bm_sma20_slope"),
                "bm_roc20": indicators.get("bm_roc20"),
            }
        else:
            trend_inputs = {
                "bm_close": None,
                "bm_sma50": None,
                "bm_sma200": None,
                "bm_above_sma50": None,
                "bm_sma50_above_sma200": None,
                "bm_sma20_slope": None,
                "bm_roc20": None,
            }

        # Build explanation string
        state_labels = {
            "FAV": "Favorable",
            "NEU": "Neutral",
            "CAU": "Cautious",
            "DEF": "Defensive",
            "ABS": "Abstained",
        }

        if abstained_reason:
            explanation = f"FEAT-004 abstained: {abstained_reason}"
        else:
            state_label = state_labels.get(regime_state, regime_state)
            cond_parts: list[str] = []
            if indicators:
                if indicators.get("bm_above_sma50") is not None:
                    cond_parts.append(
                        "index above SMA50" if indicators["bm_above_sma50"] else "index below SMA50"
                    )
                if indicators.get("bm_sma50_above_sma200") is not None:
                    cond_parts.append(
                        "SMA50>SMA200" if indicators["bm_sma50_above_sma200"] else "SMA50<SMA200"
                    )
            cond_summary = ", ".join(cond_parts) if cond_parts else "n/a"
            downgrade_text = "BUY downgraded to WATCH. " if downgrade_applied else ""
            sector_str = (
                f"{sector_result.get('sector_index_symbol', 'n/a')} - "
                f"{sector_result.get('sector_regime_state', 'UNKNOWN')}"
            )
            explanation = (
                f"Market regime: {state_label} ({cond_summary}). "
                f"Score adjusted by {delta:+.1f} ({pre_score:.1f} -> {post_score:.1f}). "
                f"{downgrade_text}"
                f"Sector: {sector_str}. "
                f"Benchmark: {symbol_used or 'none'}."
            )

        return {
            # Core
            "feat004_enabled": feat004_enabled,
            "feat004_stage": stage,
            # Benchmark
            "market_regime_state": regime_state,
            "benchmark_symbol_used": symbol_used,
            "benchmark_trend_inputs": trend_inputs,
            # Score adjustment
            "feat004_pre_adjustment_score": pre_score,
            "feat004_score_adjustment": delta,
            "feat004_post_adjustment_score": post_score,
            "feat004_watch_downgrade_applied": downgrade_applied,
            "feat004_abstained_reason": abstained_reason,
            # Sector
            "sector_mapped": sector_result.get("sector_mapped", False),
            "sector_index_symbol": sector_result.get("sector_index_symbol"),
            "sector_roc20": sector_result.get("sector_roc20"),
            "sector_relative_strength_ratio": sector_result.get("relative_strength_ratio"),
            "sector_regime_state": sector_result.get("sector_regime_state", "UNKNOWN"),
            "feat004_sector_abstained_reason": sector_result.get("feat004_sector_abstained_reason"),
            # Explanation
            "feat004_explanation": explanation,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("FEAT-004: build_feat004_log_payload exception: %s", exc)
        return {
            "feat004_enabled": feat004_enabled,
            "feat004_stage": "ABSTAINED",
            "market_regime_state": "ABS",
            "benchmark_symbol_used": None,
            "benchmark_trend_inputs": {
                "bm_close": None, "bm_sma50": None, "bm_sma200": None,
                "bm_above_sma50": None, "bm_sma50_above_sma200": None,
                "bm_sma20_slope": None, "bm_roc20": None,
            },
            "feat004_pre_adjustment_score": pre_score,
            "feat004_score_adjustment": 0.0,
            "feat004_post_adjustment_score": pre_score,
            "feat004_watch_downgrade_applied": False,
            "feat004_abstained_reason": f"log_build_exception:{type(exc).__name__}",
            "sector_mapped": False,
            "sector_index_symbol": None,
            "sector_roc20": None,
            "sector_relative_strength_ratio": None,
            "sector_regime_state": "UNKNOWN",
            "feat004_sector_abstained_reason": None,
            "feat004_explanation": f"FEAT-004 abstained: log_build_exception:{type(exc).__name__}",
        }


# ---------------------------------------------------------------------------
# Helper 7: apply_feat004_regime_overlay  (top-level orchestrator)
# ---------------------------------------------------------------------------
def apply_feat004_regime_overlay(
    *,
    composite_score: float,
    current_label: str,
    symbol: str,
    benchmark_ohlcv: "pd.DataFrame | None",
    sector_mapping: dict[str, str] | None,
    sector_ohlcv_cache: "dict[str, pd.DataFrame] | None",
    feat004_config: dict[str, Any],
    benchmark_failure_reason: str | None = None,
    benchmark_symbol: str | None = None,
) -> OverlayResult:
    """
    Top-level FEAT-004 entry point called from RecommendationService.build().

    Execution order:
      1. Resolve benchmark OHLCV (already fetched externally; passed in).
      2. Compute benchmark indicators.
      3. Classify market regime.
      4. Apply stage-based score modifier.
      5. Compute sector strength metadata (optional).
      6. Build final log payload.
      7. Return (adjusted_score, adjusted_label, log_payload).

    Returns:
        (adjusted_score, adjusted_label, feat004_log_payload)

    On any unhandled failure: original score and label are returned unchanged.
    """
    # Normalise config early; a None config must not crash the outer try/except
    # because the except clause also reads feat004_config.
    if feat004_config is None:
        feat004_config = {}

    try:
        enabled: bool = bool(feat004_config.get("enabled", False))

        if not enabled:
            _abstained_log = _minimal_abstained_payload(
                enabled=False,
                pre_score=composite_score,
                reason="feat004_disabled",
            )
            return composite_score, current_label, _abstained_log

        stage: str = str(feat004_config.get("stage", "SHADOW")).upper()
        score_deltas: dict[str, float] = feat004_config.get(
            "score_deltas", {"FAV": 2.0, "NEU": 0.0, "CAU": -3.0, "DEF": -5.0, "ABS": 0.0}
        )
        downgrade_thresholds: dict[str, float] = feat004_config.get(
            "buy_downgrade_thresholds", {"CAU": 74.0, "DEF": 77.0}
        )
        buy_threshold: float = float(feat004_config.get("buy_threshold", 72.0))
        favorable_cap: bool = bool(feat004_config.get("favorable_cap_below_buy", True))
        sector_mapping_enabled: bool = bool(feat004_config.get("sector_mapping_enabled", True))
        sector_min_candles: int = int(feat004_config.get("sector_min_candles", 50))

        # ----------------------------------------------------------------
        # Step 2: Compute benchmark indicators
        # ----------------------------------------------------------------
        indicators: IndicatorDict | None
        abstained_reason: str | None = None
        symbol_used: str | None = None

        if benchmark_ohlcv is None:
            # Benchmark was not resolved before calling the overlay.
            # Preserve the specific failure reason from the orchestrator
            # (benchmark_fetch_failed, benchmark_data_stale,
            # benchmark_insufficient_history) instead of collapsing to
            # a generic "benchmark_unavailable".
            indicators = None
            abstained_reason = benchmark_failure_reason or "benchmark_unavailable"
            logger.info("FEAT-004: benchmark_ohlcv is None; defaulting to ABSTAINED (%s).", abstained_reason)
        else:
            indicators = compute_benchmark_indicators(benchmark_ohlcv)
            # Detect total indicator failure (all defaults remain)
            if indicators["bm_close"] == 0.0 and indicators["bm_sma50"] == 0.0:
                indicators = None
                abstained_reason = "benchmark_indicator_compute_failed"
            else:
                symbol_used = benchmark_symbol

        # ----------------------------------------------------------------
        # Step 3: Classify regime
        # ----------------------------------------------------------------
        regime_state: str = classify_market_regime(
            None if abstained_reason else indicators
        )

        # ----------------------------------------------------------------
        # Step 4: Score modifier
        # ----------------------------------------------------------------
        adjusted_score, adjusted_label, downgrade_applied, delta = apply_regime_score_modifier(
            regime_state=regime_state,
            composite_score=composite_score,
            current_label=current_label,
            stage=stage,
            score_deltas=score_deltas,
            downgrade_thresholds=downgrade_thresholds,
            buy_threshold=buy_threshold,
            favorable_cap_below_buy=favorable_cap,
        )

        # ----------------------------------------------------------------
        # Step 5: Sector strength metadata (optional; depends on benchmark ROC)
        # ----------------------------------------------------------------
        bm_roc20: float | None = None
        if indicators:
            bm_roc20 = indicators.get("bm_roc20")

        if sector_mapping_enabled:
            sector_result: SectorResult = compute_sector_strength(
                symbol=symbol,
                sector_mapping=sector_mapping,
                sector_ohlcv_cache=sector_ohlcv_cache,
                benchmark_roc20=bm_roc20,
                min_candles=sector_min_candles,
            )
        else:
            sector_result = {
                "sector_mapped": False,
                "sector_index_symbol": None,
                "sector_roc20": None,
                "relative_strength_ratio": None,
                "sector_regime_state": "UNKNOWN",
                "feat004_sector_abstained_reason": "sector_mapping_disabled_in_config",
            }

        # ----------------------------------------------------------------
        # Step 6: Build log payload
        # ----------------------------------------------------------------
        log_payload: LogPayload = build_feat004_log_payload(
            feat004_enabled=enabled,
            stage=stage if not abstained_reason else "ABSTAINED",
            regime_state=regime_state,
            symbol_used=symbol_used,
            indicators=indicators,
            pre_score=composite_score,
            delta=delta,
            post_score=adjusted_score,
            downgrade_applied=downgrade_applied,
            abstained_reason=abstained_reason,
            sector_result=sector_result,
        )

        logger.debug(
            "FEAT-004 [%s] symbol=%s regime=%s delta=%+.1f %s->%s adj_score=%.2f",
            stage,
            symbol,
            regime_state,
            delta,
            current_label,
            adjusted_label,
            adjusted_score,
        )

        return adjusted_score, adjusted_label, log_payload

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "FEAT-004: apply_feat004_regime_overlay unhandled exception for %s: %s",
            symbol,
            exc,
            exc_info=True,
        )
        fallback_log = _minimal_abstained_payload(
            enabled=bool(feat004_config.get("enabled", False)),
            pre_score=composite_score,
            reason=f"exception:{type(exc).__name__}",
        )
        return composite_score, current_label, fallback_log


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------
def _minimal_abstained_payload(
    *,
    enabled: bool,
    pre_score: float,
    reason: str,
) -> LogPayload:
    """Return a fully-keyed log payload in the ABSTAINED state."""
    return {
        "feat004_enabled": enabled,
        "feat004_stage": "ABSTAINED",
        "market_regime_state": "ABS",
        "benchmark_symbol_used": None,
        "benchmark_trend_inputs": {
            "bm_close": None, "bm_sma50": None, "bm_sma200": None,
            "bm_above_sma50": None, "bm_sma50_above_sma200": None,
            "bm_sma20_slope": None, "bm_roc20": None,
        },
        "feat004_pre_adjustment_score": pre_score,
        "feat004_score_adjustment": 0.0,
        "feat004_post_adjustment_score": pre_score,
        "feat004_watch_downgrade_applied": False,
        "feat004_abstained_reason": reason,
        "sector_mapped": False,
        "sector_index_symbol": None,
        "sector_roc20": None,
        "sector_relative_strength_ratio": None,
        "sector_regime_state": "UNKNOWN",
        "feat004_sector_abstained_reason": None,
        "feat004_explanation": f"FEAT-004 abstained: {reason}",
    }
