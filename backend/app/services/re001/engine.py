"""RE-001 strategy orchestration (baseline + Doc 02 priorities)."""

from __future__ import annotations

from typing import Any

from .context import LabExecutionContext
from .eligibility import bull_stock_filter_pass, exceptional_rs_leader, _tech_score
from .portfolio_context import portfolio_blocks_buy, resolve_portfolio_snapshot
from .regime import is_regime_usable, map_market_regime
from .strategy_config import (
    BEAR_MINIMAL_PARTICIPATION,
    REGIME_PRIMARY_PRIORITY,
    SIDEWAYS_STRICT_PULLBACK,
)


def _sector_rs(ctx: LabExecutionContext) -> float | None:
    so = ctx.sector_overlay
    if so is None:
        return None
    try:
        v = getattr(so, "sector_rs_20", None)
        if v is None and isinstance(so, dict):
            v = so.get("sector_rs_20")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _signal_bullish(technical_results: list[Any]) -> bool:
    if not technical_results:
        return False
    t0 = technical_results[0]
    sig = str(getattr(t0, "signal", None) or (t0.get("signal") if isinstance(t0, dict) else "") or "").lower()
    return sig in {"bullish", "buy", "strong_buy"}


def _volume_expanding(candles: list[Any]) -> bool:
    if not candles or len(candles) < 25:
        return False
    try:
        vols = [float(getattr(c, "volume", None) or c["volume"]) for c in candles[-25:]]  # type: ignore[index]
    except Exception:
        return False
    recent = sum(vols[-5:]) / 5.0
    base = sum(vols[-25:-5]) / 20.0 if len(vols) >= 25 else sum(vols[:-5]) / max(len(vols) - 5, 1)
    return base > 0 and recent >= 1.1 * base


def _evaluate_primaries(
    *,
    regime: str,
    tech_score: float,
    bullish: bool,
    volume_ok: bool,
    rs: float | None,
    strict_pullback: bool,
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
    """Return (qualified families, supporting, rejected)."""
    supporting: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    qualified: list[str] = []

    if rs is not None and rs >= 0:
        supporting.append({"name": "Relative Strength", "result": "pass"})
    else:
        supporting.append({"name": "Relative Strength", "result": "weak"})

    if volume_ok:
        supporting.append({"name": "Volume Confirmation", "result": "pass"})
    else:
        supporting.append({"name": "Volume Confirmation", "result": "weak"})

    if bullish:
        supporting.append({"name": "Multi-Timeframe Alignment", "result": "pass"})
    else:
        supporting.append({"name": "Multi-Timeframe Alignment", "result": "fail"})

    # Primary qualification heuristics using existing TA score
    candidates = {
        "Trend Following": tech_score >= 68 and bullish,
        "Pullback Continuation": tech_score >= 60 and bullish and (not strict_pullback or volume_ok),
        "Breakout Continuation": tech_score >= 72 and volume_ok,
        "Momentum Continuation": tech_score >= 70 and bullish,
    }

    if regime == "Sideways" and SIDEWAYS_STRICT_PULLBACK:
        if candidates["Pullback Continuation"] and not (volume_ok and tech_score >= 68):
            candidates["Pullback Continuation"] = False
            rejected.append({"name": "Pullback Continuation", "reason": "sideways_strict_pullback"})

    for name, ok in candidates.items():
        if ok:
            qualified.append(name)
        else:
            if not any(r["name"] == name for r in rejected):
                rejected.append({"name": name, "reason": "conditions_not_met"})

    # Priority order
    order = REGIME_PRIMARY_PRIORITY.get(regime, REGIME_PRIMARY_PRIORITY["Sideways"])
    qualified_sorted = [f for f in order if f in qualified]
    return qualified_sorted, supporting, rejected


def evaluate_re001(ctx: LabExecutionContext) -> dict[str, Any]:
    """Core evaluate → dict suitable for Decision Object builder."""
    reason_codes: list[str] = []
    regime = map_market_regime(ctx.market_regime)
    if not is_regime_usable(regime):
        reason_codes.append("missing_market_context")
        return {
            "recommendation_state": "REJECT",
            "market_regime": "UNKNOWN",
            "confidence_score": 0.0,
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {"regime": "UNKNOWN", "validation": {"market_regime": "missing"}},
            "explanation": "Missing or unusable market regime context.",
            "portfolio_decision": {"status": "skipped"},
            "risk_profile": {"mode": "n/a"},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
        }

    rs = _sector_rs(ctx)
    eligible, elig_reasons = bull_stock_filter_pass(
        candles=ctx.candles,
        technical_results=ctx.technical_results,
        sector_rs=rs,
    )

    portfolio = resolve_portfolio_snapshot(
        user_portfolio=ctx.user_portfolio,
        risk_settings=ctx.risk_settings,
    )
    port_block, port_reason = portfolio_blocks_buy(portfolio)

    tech_score = _tech_score(ctx.technical_results)
    bullish = _signal_bullish(ctx.technical_results)
    volume_ok = _volume_expanding(ctx.candles)

    if regime == "Bear" and BEAR_MINIMAL_PARTICIPATION:
        if not exceptional_rs_leader(technical_results=ctx.technical_results, sector_rs=rs):
            reason_codes.append("bear_regime_minimal_participation")
            return {
                "recommendation_state": "REJECT",
                "market_regime": regime,
                "confidence_score": min(tech_score / 100.0, 0.4),
                "strategy_family": None,
                "strategy_name": None,
                "reason_codes": reason_codes + elig_reasons,
                "evidence": {
                    "regime": regime,
                    "validation": {
                        "market_regime": "pass",
                        "bull_stock_filter": "fail" if not eligible else "pass",
                        "bear_exceptional_rs": "fail",
                    },
                },
                "explanation": "Bear regime: ordinary continuation rejected; not an exceptional RS leader.",
                "portfolio_decision": {
                    "status": "ok" if portfolio.available else "unavailable",
                    "source": portfolio.source,
                },
                "risk_profile": {"regime": regime, "mode": "capital_preservation"},
                "primary_strategy": None,
                "supporting_strategies": [],
                "rejected_strategies": [{"name": "all_primaries", "reason": "bear_minimal"}],
                "evaluation_status": "rejected_by_rules",
            }

    if not eligible:
        reason_codes.extend(elig_reasons or ["bull_stock_filter_failed"])
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": min(tech_score / 100.0, 0.45),
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": reason_codes,
            "evidence": {
                "regime": regime,
                "validation": {"bull_stock_filter": "fail", "reasons": elig_reasons},
            },
            "explanation": "Failed Bull Stock Filter eligibility.",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": [],
            "rejected_strategies": [],
            "evaluation_status": "rejected_by_rules",
        }

    qualified, supporting, rejected = _evaluate_primaries(
        regime=regime,
        tech_score=tech_score,
        bullish=bullish,
        volume_ok=volume_ok,
        rs=rs,
        strict_pullback=(regime == "Sideways"),
    )

    if not qualified:
        return {
            "recommendation_state": "REJECT",
            "market_regime": regime,
            "confidence_score": min(tech_score / 100.0, 0.5),
            "strategy_family": None,
            "strategy_name": None,
            "reason_codes": ["no_primary_strategy"],
            "evidence": {
                "regime": regime,
                "supporting": supporting,
                "rejected": rejected,
            },
            "explanation": "No primary continuation strategy qualified.",
            "portfolio_decision": {
                "status": "ok" if portfolio.available else "unavailable",
                "source": portfolio.source,
            },
            "risk_profile": {"regime": regime},
            "primary_strategy": None,
            "supporting_strategies": supporting,
            "rejected_strategies": rejected,
            "evaluation_status": "rejected_by_rules",
        }

    primary = qualified[0]
    # Confidence from tech + support
    support_pass = sum(1 for s in supporting if s.get("result") == "pass")
    conf = min(0.95, max(0.35, tech_score / 100.0 * 0.7 + support_pass * 0.08))

    if tech_score >= 72 and support_pass >= 2:
        state = "BUY"
    elif tech_score >= 55:
        state = "WATCH"
    else:
        state = "REJECT"
        reason_codes.append("low_technical_score")

    if port_block:
        if port_reason:
            reason_codes.append(port_reason)
        if state == "BUY":
            state = "WATCH"

    return {
        "recommendation_state": state,
        "market_regime": regime,
        "confidence_score": conf,
        "strategy_family": primary,
        "strategy_name": primary,
        "reason_codes": reason_codes,
        "evidence": {
            "regime": regime,
            "priority_order": REGIME_PRIMARY_PRIORITY.get(regime, []),
            "qualified_primaries": qualified,
            "supporting": supporting,
            "rejected": rejected,
            "technical_score": tech_score,
            "validation": {
                "market_regime": "pass",
                "bull_stock_filter": "pass",
                "portfolio": "fail" if port_block else "pass",
                "liquidity": "pass" if volume_ok else "weak",
            },
        },
        "explanation": (
            f"Primary {primary} under {regime} regime; tech_score={tech_score:.1f}; "
            f"state={state}."
        ),
        "portfolio_decision": {
            "status": "blocked" if port_block else "ok",
            "source": portfolio.source,
            "reason": port_reason,
        },
        "risk_profile": {"regime": regime, "mode": "continuation"},
        "primary_strategy": primary,
        "supporting_strategies": supporting,
        "rejected_strategies": rejected,
        "evaluation_status": "success" if state != "REJECT" or not reason_codes else "rejected_by_rules",
    }
