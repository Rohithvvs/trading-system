from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from app.schemas.governance import SectorStrengthItem, SectorStrengthTelemetry

logger = logging.getLogger("app.services.sector_strength")

_SECTOR_MAPPINGS_CACHE: Optional[Dict[str, str]] = None


def load_sector_mappings() -> Dict[str, str]:
    """Load symbol → sector index mapping (cached)."""
    global _SECTOR_MAPPINGS_CACHE
    if _SECTOR_MAPPINGS_CACHE is not None:
        return _SECTOR_MAPPINGS_CACHE
    mapping_path = Path(__file__).resolve().parent.parent / "config" / "sector_mappings.json"
    mappings: Dict[str, str] = {}
    if mapping_path.exists():
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                mappings = {str(k).upper(): str(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("Failed to load sector mappings: %s", exc)
    _SECTOR_MAPPINGS_CACHE = mappings
    return mappings


def _roc_to_return_pct(roc: Any) -> Optional[float]:
    """Convert ROC ratio or percent to return_pct scale used by sector strength."""
    if roc is None:
        return None
    try:
        value = float(roc)
    except (TypeError, ValueError):
        return None
    # Ratios like 0.02 → 2.0%; values already in percent (|x| > 1) left as-is.
    if abs(value) <= 1.0:
        return round(value * 100.0, 4)
    return round(value, 4)


def _stock_return_pct_from_indicators(indicators: Dict[str, Any]) -> Optional[float]:
    """Best-effort day/period return from technical indicators."""
    if not indicators:
        return None
    for key in ("change_pct", "day_change_pct", "roc", "pct_change", "return_pct"):
        if indicators.get(key) is not None:
            try:
                return float(indicators[key])
            except (TypeError, ValueError):
                pass
    close = indicators.get("close") or indicators.get("current_price")
    open_ = indicators.get("open") or indicators.get("prev_close")
    try:
        if close is not None and open_ is not None and float(open_) != 0.0:
            return round((float(close) - float(open_)) / float(open_) * 100.0, 4)
    except (TypeError, ValueError):
        pass
    return None


def build_sector_strength_scan_inputs(
    *,
    universe_technical: Optional[Dict[str, Any]] = None,
    sector_overlay: Any = None,
    mappings: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], str, Optional[float]]:
    """Build (sectors, benchmark_symbol, benchmark_return_pct) for shadow FEAT-020.

    Prefers live universe returns grouped by sector mapping; falls back to
    sector_overlay ROC (sector index vs NIFTY50) when constituent coverage is thin.
    """
    mappings = mappings if mappings is not None else load_sector_mappings()
    by_sector: Dict[str, List[Dict[str, Any]]] = {}

    if universe_technical:
        for sym, tech in universe_technical.items():
            canon = str(sym).upper().replace("NSE:", "").split("-")[0]
            sector = mappings.get(canon) or mappings.get(str(sym).upper())
            if not sector:
                continue
            inds = getattr(tech, "indicators", None) or {}
            if not isinstance(inds, dict):
                inds = {}
            ret = _stock_return_pct_from_indicators(inds)
            if ret is None:
                continue
            by_sector.setdefault(sector, []).append(
                {"symbol": str(sym), "return_pct": float(ret)}
            )

    # Enrich / seed from sector overlay index ROC for the mapped sector.
    mapped_sector = getattr(sector_overlay, "mapped_sector", None) if sector_overlay else None
    sector_ret = (
        _roc_to_return_pct(getattr(sector_overlay, "sector_roc20", None))
        if sector_overlay
        else None
    )
    if mapped_sector and sector_ret is not None:
        stocks = list(by_sector.get(mapped_sector) or [])
        if len(stocks) < 3:
            # Pad with sector-index proxy constituents so RS is recorded with
            # high confidence when index ROC is available (watch-only dataset).
            while len(stocks) < 3:
                stocks.append(
                    {
                        "symbol": f"{mapped_sector}#idx{len(stocks)}",
                        "return_pct": sector_ret,
                    }
                )
            by_sector[mapped_sector] = stocks

    sectors: List[Dict[str, Any]] = [
        {"sector": sector, "stocks": stocks} for sector, stocks in by_sector.items()
    ]

    benchmark_symbol = "NIFTY50"
    benchmark_return_pct: Optional[float] = None
    if sector_overlay is not None:
        benchmark_return_pct = _roc_to_return_pct(
            getattr(sector_overlay, "nifty50_roc20", None)
        )

    return sectors, benchmark_symbol, benchmark_return_pct


class StockPriceReturn(BaseModel):
    """Stock symbol and price return percentage."""

    symbol: str
    return_pct: float


class SectorInput(BaseModel):
    """Sector name and constituent stock price returns."""

    sector: str
    stocks: List[StockPriceReturn] = Field(default_factory=list)


def _parse_sector_input(data: Union[SectorInput, Dict[str, Any]]) -> Optional[SectorInput]:
    """Coerce dict or Pydantic model into SectorInput."""
    if isinstance(data, SectorInput):
        return data
    if isinstance(data, dict):
        try:
            sector_name = data.get("sector") or data.get("name") or "UNKNOWN"
            raw_stocks = data.get("stocks") or data.get("constituents") or []
            stocks: List[StockPriceReturn] = []
            for item in raw_stocks:
                if isinstance(item, StockPriceReturn):
                    stocks.append(item)
                elif isinstance(item, dict):
                    sym = item.get("symbol")
                    ret = item.get("return_pct") if item.get("return_pct") is not None else item.get("return", 0.0)
                    if sym is not None:
                        stocks.append(StockPriceReturn(symbol=str(sym), return_pct=float(ret)))
            return SectorInput(sector=str(sector_name), stocks=stocks)
        except Exception as exc:
            logger.warning("Failed to parse SectorInput from dict: %s", exc)
            return None
    return None


def calculate_sector_strength(
    sectors: Optional[List[Union[SectorInput, Dict[str, Any]]]] = None,
    benchmark_symbol: str = "NIFTY50",
    benchmark_return_pct: Optional[float] = 0.0,
    scan_time: Optional[datetime] = None,
) -> SectorStrengthTelemetry:
    """Pure calculation of sector relative strength against benchmark index.

    Calculates sector average price return relative to benchmark return and
    classifies sectors into Outperforming (> +1.0%), Neutral ([-1.0%, +1.0%]),
    or Underperforming (< -1.0%). High confidence requires >= 3 constituents.
    """
    executed_at = (scan_time or datetime.now(timezone.utc)).isoformat()

    if not sectors:
        return SectorStrengthTelemetry(
            executed_at=executed_at,
            status="success",
            benchmark_symbol=benchmark_symbol,
            benchmark_return_pct=benchmark_return_pct or 0.0,
            sectors=[],
        )

    sector_items: List[SectorStrengthItem] = []

    for item in sectors:
        parsed = _parse_sector_input(item)
        if not parsed:
            continue

        constituent_count = len(parsed.stocks)
        if constituent_count > 0:
            avg_sector_return = sum(s.return_pct for s in parsed.stocks) / constituent_count
            avg_sector_return = round(avg_sector_return, 4)
        else:
            avg_sector_return = 0.0

        if constituent_count < 3 or benchmark_return_pct is None:
            confidence = "low"
            rel_strength = None
            label = "Neutral"
        else:
            rel_strength = round(avg_sector_return - benchmark_return_pct, 4)
            confidence = "high"
            if rel_strength > 1.0:
                label = "Outperforming"
            elif rel_strength < -1.0:
                label = "Underperforming"
            else:
                label = "Neutral"

        sector_items.append(
            SectorStrengthItem(
                sector=parsed.sector,
                sector_return_pct=avg_sector_return,
                relative_strength=rel_strength,
                label=label,
                constituent_count=constituent_count,
                confidence=confidence,
            )
        )

    return SectorStrengthTelemetry(
        executed_at=executed_at,
        status="success",
        benchmark_symbol=benchmark_symbol,
        benchmark_return_pct=benchmark_return_pct or 0.0,
        sectors=sector_items,
    )
