from __future__ import annotations

import yfinance as yf

from ..schemas.analysis import FundamentalAnalysisResult
from ..utils import get_logger


class FundamentalAnalysisAgent:
    def __init__(self) -> None:
        self.logger = get_logger("app.fundamental_agent")

    def run(self, symbol: str) -> FundamentalAnalysisResult:
        try:
            # yfinance expects Indian equities to have the .NS suffix (e.g. RELIANCE.NS)
            yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info

            if not info:
                self.logger.warning("No fundamental info found for %s", yf_symbol)
                return self._fallback_result()

            revenue_growth_pct = info.get("revenueGrowth")
            profit_margin_pct = info.get("profitMargins")
            debt_to_equity = info.get("debtToEquity")
            pe_ratio = info.get("trailingPE")

            # Convert fractional decimals to standard percentages if they exist
            if revenue_growth_pct is not None:
                revenue_growth_pct = round(revenue_growth_pct * 100, 2)
            if profit_margin_pct is not None:
                profit_margin_pct = round(profit_margin_pct * 100, 2)

            score = self._calculate_fundamental_score(
                revenue_growth=revenue_growth_pct, 
                profit_margin=profit_margin_pct, 
                debt_to_equity=debt_to_equity, 
                pe_ratio=pe_ratio
            )

            # Build a dynamic string for the UI overview
            summary_parts = []
            if revenue_growth_pct is not None:
                summary_parts.append(f"Rev Growth: {revenue_growth_pct}%")
            if profit_margin_pct is not None:
                summary_parts.append(f"Margins: {profit_margin_pct}%")
            if debt_to_equity is not None:
                summary_parts.append(f"D/E: {debt_to_equity}")
            if pe_ratio is not None:
                summary_parts.append(f"P/E: {round(pe_ratio, 2)}")

            summary = " | ".join(summary_parts) if summary_parts else "Fundamental data unavailable."

            return FundamentalAnalysisResult(
                revenue_growth_pct=revenue_growth_pct,
                profit_margin_pct=profit_margin_pct,
                debt_to_equity=debt_to_equity,
                pe_ratio=pe_ratio,
                fundamental_score=score,
                summary=summary
            )
        except Exception as e:
            self.logger.error("Failed to fetch fundamentals for %s: %s", symbol, e)
            return self._fallback_result()

    def _calculate_fundamental_score(
        self,
        revenue_growth: float | None,
        profit_margin: float | None,
        debt_to_equity: float | None,
        pe_ratio: float | None
    ) -> float:
        """
        Calculates a normalized fundamental score strictly bounded between -1.0 and 1.0.
        """
        score = 0.0
        factors_counted = 0

        # Score Revenue Growth (Expect >20% = 1.0, <0% = -1.0)
        if revenue_growth is not None:
            rg_score = max(-1.0, min(1.0, revenue_growth / 20.0))
            score += rg_score
            factors_counted += 1

        # Score Profit Margin (Expect >15% = 1.0, <0% = -1.0)
        if profit_margin is not None:
            pm_score = max(-1.0, min(1.0, profit_margin / 15.0))
            score += pm_score
            factors_counted += 1

        # Score Debt to Equity (Expect <50 = 1.0, >200 = -1.0)
        if debt_to_equity is not None:
            if debt_to_equity <= 50:
                de_score = 1.0
            elif debt_to_equity >= 200:
                de_score = -1.0
            else:
                # Linear penalty between 50 and 200
                de_score = 1.0 - ((debt_to_equity - 50) / 150) * 2.0
            score += de_score
            factors_counted += 1

        # Score P/E Ratio (Deep Value <10 = 1.0, Overvalued >50 = -1.0)
        if pe_ratio is not None and pe_ratio > 0:
            if 10 <= pe_ratio <= 25:
                pe_score = 0.5
            elif pe_ratio < 10:
                pe_score = 1.0
            elif pe_ratio > 50:
                pe_score = -1.0
            else:
                pe_score = -0.5
            score += pe_score
            factors_counted += 1

        # Fallback to true neutral if API is missing all data
        if factors_counted == 0:
            return 0.0

        return round(score / factors_counted, 2)

    def _fallback_result(self) -> FundamentalAnalysisResult:
        return FundamentalAnalysisResult(
            revenue_growth_pct=None,
            profit_margin_pct=None,
            debt_to_equity=None,
            pe_ratio=None,
            fundamental_score=0.0,
            summary="Fundamental data API unavailable or timed out."
        )
