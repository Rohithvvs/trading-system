"""Portfolio / risk snapshot for RE-001 validation (FR-026)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PortfolioSnapshot:
    available: bool
    source: str
    open_positions: int = 0
    max_positions: int | None = None
    available_cash: float | None = None
    notes: str = ""


def resolve_portfolio_snapshot(
    *,
    user_portfolio: dict[str, Any] | None = None,
    risk_settings: dict[str, Any] | None = None,
) -> PortfolioSnapshot:
    """Prefer authenticated user paper/risk context; else mark unavailable."""
    if user_portfolio:
        return PortfolioSnapshot(
            available=True,
            source="user_paper",
            open_positions=int(user_portfolio.get("open_positions_count") or 0),
            max_positions=(
                int(user_portfolio["max_positions"])
                if user_portfolio.get("max_positions") is not None
                else None
            ),
            available_cash=(
                float(user_portfolio["available_cash"])
                if user_portfolio.get("available_cash") is not None
                else None
            ),
            notes="requesting_user_paper",
        )
    if risk_settings:
        return PortfolioSnapshot(
            available=True,
            source="risk_settings",
            open_positions=0,
            max_positions=(
                int(risk_settings["max_positions"])
                if risk_settings.get("max_positions") is not None
                else None
            ),
            notes="risk_settings_only",
        )
    return PortfolioSnapshot(
        available=False,
        source="none",
        notes="portfolio_context_unavailable",
    )


def portfolio_blocks_buy(snapshot: PortfolioSnapshot) -> tuple[bool, str | None]:
    if not snapshot.available:
        return True, "portfolio_context_unavailable"
    if snapshot.max_positions is not None and snapshot.open_positions >= snapshot.max_positions:
        return True, "portfolio_position_limit"
    return False, None
