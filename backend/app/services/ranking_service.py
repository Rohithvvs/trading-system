from __future__ import annotations

from ..schemas import RankingItem, RankingsResponse, StockAnalysisResult
from ..utils import advisory_payload


class RankingService:
    def rank(self, items: list[StockAnalysisResult]) -> RankingsResponse:
        scored = sorted(items, key=lambda item: (-item.recommendation.score, item.symbol))
        rankings: list[RankingItem] = []

        for index, item in enumerate(scored, start=1):
            rankings.append(
                RankingItem(
                    rank=index,
                    symbol=item.symbol,
                    overall_score=item.recommendation.score,
                    recommendation=item.recommendation.action,
                )
            )

        buy_rankings = [
            RankingItem(
                rank=index,
                symbol=item.symbol,
                overall_score=item.recommendation.score,
                recommendation=item.recommendation.action,
            )
            for index, item in enumerate(
                [candidate for candidate in scored if candidate.recommendation.action == "BUY"],
                start=1,
            )
        ]
        watch_rankings = [
            RankingItem(
                rank=index,
                symbol=item.symbol,
                overall_score=item.recommendation.score,
                recommendation=item.recommendation.action,
            )
            for index, item in enumerate(
                [candidate for candidate in scored if candidate.recommendation.action == "WATCH"],
                start=1,
            )
        ]

        best_intraday = self._best_by_mode(items, "intraday")
        best_swing = self._best_by_mode(items, "swing")

        for entry in rankings:
            if best_intraday and entry.symbol == best_intraday:
                entry.best_for_mode = "intraday"
            if best_swing and entry.symbol == best_swing:
                entry.best_for_mode = "swing" if not entry.best_for_mode else "intraday,swing"

        return RankingsResponse(
            rankings=rankings,
            buy_rankings=buy_rankings,
            watch_rankings=watch_rankings,
            best_intraday_candidate=best_intraday,
            best_swing_candidate=best_swing,
            disclaimer=advisory_payload(),
        )

    def _best_by_mode(self, items: list[StockAnalysisResult], mode_name: str) -> str | None:
        filtered = [item for item in items if any(result.mode.value == mode_name for result in item.technical)]
        if not filtered:
            return None
        return min(filtered, key=lambda item: (-item.recommendation.score, item.symbol)).symbol
