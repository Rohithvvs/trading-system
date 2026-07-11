"""Unit tests for swing research engine — pure computation, no broker/auth."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.research_service import ResearchService, NA
from backend.app.services.research_cache import ResearchCache


def _candles(n: int = 120, start: float = 100.0):
    points = []
    price = start
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = price * (1.002 if i % 5 else 0.999)
        o = price * 0.995
        h = price * 1.01
        l = price * 0.99
        c = price
        vol = 100000 + i * 500
        points.append(
            SimpleNamespace(
                timestamp=ts + timedelta(days=i),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vol,
            )
        )
    return points


def _item(symbol: str = "TEST"):
    plan = SimpleNamespace(
        mode=SimpleNamespace(value="swing"),
        entry_low=100.0,
        entry_high=102.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=118.0,
        target_3=125.0,
        risk_reward_ratio=2.0,
    )
    rec = SimpleNamespace(
        action="BUY",
        confidence=0.8,
        score=78.0,
        summary="Test setup",
        trade_plans=[plan],
        reasoning=SimpleNamespace(bullets=[], risk_factors=[], invalidation_signals=[]),
    )
    tech = SimpleNamespace(mode=SimpleNamespace(value="swing"), signal="bullish", score=80.0, indicators={}, summary="ok")
    fund = SimpleNamespace(
        pe_ratio=18.0,
        debt_to_equity=40.0,
        revenue_growth_pct=12.0,
        profit_margin_pct=15.0,
        fundamental_score=0.4,
        summary="ok",
    )
    trades = [
        {
            "entry_date": "2024-01-01",
            "exit_date": "2024-01-05",
            "entry_price": 100,
            "exit_price": 105,
            "pnl_percent": 5.0,
        },
        {
            "entry_date": "2024-02-01",
            "exit_date": "2024-02-08",
            "entry_price": 100,
            "exit_price": 97,
            "pnl_percent": -3.0,
        },
    ] * 30
    bt = SimpleNamespace(
        mode=SimpleNamespace(value="swing"),
        strategy_name="sma_rsi_macd",
        total_return=12.0,
        cagr=10.0,
        max_drawdown=8.0,
        win_rate=55.0,
        profit_factor=1.4,
        trade_count=len(trades),
        verdict="favorable",
        trades=trades,
        sharpe_ratio=1.1,
    )
    return SimpleNamespace(
        symbol=symbol,
        technical=[tech],
        recommendation=rec,
        fundamental=fund,
        backtests=[bt],
        news_articles=[],
        news_summary="No news",
        news_sentiment_label="neutral",
        news_sentiment_score=0.0,
        social_sentiment_score=None,
    )


def test_research_build_contains_core_sections():
    svc = ResearchService()
    payload = svc.build(
        symbol="TEST",
        item=_item(),
        ohlcv=_candles(150),
        company_info={"company_name": "Test Co", "sector": "Tech", "industry": "Software", "market_cap": 1e10},
        tech_extra={"atr": 2.0, "atr_pct": 1.5, "multi_timeframe": {"daily": "bullish", "weekly": "bullish"}},
        backtest_extra={
            "trades": _item().backtests[0].trades,
            "win_rate": 55.0,
            "max_drawdown": 8.0,
            "strategy_name": "sma_rsi_macd",
            "profit_factor": 1.4,
            "sharpe_ratio": 1.1,
            "total_return": 12.0,
            "trade_count": 60,
            "verdict": "favorable",
        },
    )
    assert payload["symbol"] == "TEST"
    assert "swing_score" in payload
    assert 0 <= payload["swing_score"]["score"] <= 100
    assert "trend_analysis" in payload
    assert "momentum_analysis" in payload
    assert "volume_analysis" in payload
    assert "volatility" in payload
    assert "price_action" in payload
    assert "pattern_detection" in payload
    assert "multi_timeframe" in payload
    assert "risk_analysis" in payload
    assert "holding_period" in payload
    assert "backtesting" in payload
    assert "historical_similar_setups" in payload
    assert payload["historical_similar_setups"]["number_of_similar_setups"] > 0
    assert "ai_confidence" in payload
    assert payload["ai_confidence"]["label"] in ("High", "Medium", "Low")
    assert "fundamental_analysis" in payload
    assert "institutional_activity" in payload
    assert payload["institutional_activity"]["fii_buying"] == NA
    assert "checklist" in payload
    assert payload["checklist"]["overall"] in ("Trade Ready", "Avoid")
    assert "ai_research_summary" in payload


def test_research_cache_fingerprint_and_hit():
    cache = ResearchCache(ttl_seconds=60)
    key = "t1"
    cache.set(key, {"ok": True})
    assert cache.get(key) == {"ok": True}
    fp = ResearchCache.fingerprint("AAA", "2024-01-01", 100, 12.5)
    assert isinstance(fp, str) and len(fp) == 24


def test_empty_ohlcv_does_not_crash():
    svc = ResearchService()
    payload = svc.build(symbol="EMPTY", item=_item("EMPTY"), ohlcv=[], company_info={})
    assert payload["symbol"] == "EMPTY"
    assert payload["supply_demand"]["support"] == NA or payload["supply_demand"]["support"] is not None
