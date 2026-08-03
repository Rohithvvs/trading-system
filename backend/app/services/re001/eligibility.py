"""Bull Stock Filter and eligibility helpers for RE-001."""

from __future__ import annotations

from typing import Any


def _tech_score(technical_results: list[Any]) -> float:
    if not technical_results:
        return 0.0
    t0 = technical_results[0]
    try:
        return float(getattr(t0, "score", None) or t0.get("score") or 0.0)  # type: ignore[union-attr]
    except Exception:
        return 0.0


def _close_and_mas(candles: list[Any]) -> tuple[float | None, float | None, float | None]:
    if not candles or len(candles) < 50:
        return None, None, None
    closes: list[float] = []
    for c in candles:
        try:
            closes.append(float(getattr(c, "close", None) or c["close"]))  # type: ignore[index]
        except Exception:
            continue
    if len(closes) < 50:
        return None, None, None
    price = closes[-1]
    sma50 = sum(closes[-50:]) / 50.0
    sma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else None
    return price, sma50, sma200


def bull_stock_filter_pass(
    *,
    candles: list[Any],
    technical_results: list[Any],
    sector_rs: float | None = None,
) -> tuple[bool, list[str]]:
    """REDS bull stock filter intent: price vs intermediate/long MAs + structure."""
    reasons: list[str] = []
    price, sma50, sma200 = _close_and_mas(candles)
    if price is None or sma50 is None:
        return False, ["insufficient_history"]
    if price <= sma50:
        reasons.append("price_not_above_sma50")
    if sma200 is not None and price <= sma200:
        reasons.append("price_not_above_sma200")
    if sma200 is not None and sma50 < sma200:
        reasons.append("sma50_not_above_sma200")
    score = _tech_score(technical_results)
    if score < 52:
        reasons.append("technical_score_below_floor")
    # Relative strength recommended but not hard-required for eligibility
    if sector_rs is not None and sector_rs < -5.0:
        reasons.append("weak_sector_rs")
    return (len(reasons) == 0, reasons)


def exceptional_rs_leader(
    *,
    technical_results: list[Any],
    sector_rs: float | None,
) -> bool:
    """Bear-regime exceptional relative-strength leader."""
    score = _tech_score(technical_results)
    if score < 75:
        return False
    if sector_rs is None:
        return score >= 85
    return sector_rs >= 0 and score >= 75
