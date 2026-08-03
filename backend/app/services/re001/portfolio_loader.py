"""Load paper/risk snapshot for RE-001 (FR-026)."""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Any
from uuid import UUID

from ...config.settings import settings

logger = logging.getLogger("app.re001")

# Bound DB wait so RE-001 portfolio context cannot stall the production scan path.
_DEFAULT_PORTFOLIO_LOAD_TIMEOUT_S = 2.0


def _load_user_portfolio_dict_impl(user_id: str) -> dict[str, Any] | None:
    from ...db.session import SessionLocal
    from ...models.paper_trading import PaperPosition, PaperTradingAccount
    from sqlalchemy import func, select

    uid: Any = user_id
    try:
        uid = UUID(str(user_id))
    except Exception:
        pass

    db = SessionLocal()
    try:
        acct = db.execute(
            select(PaperTradingAccount).where(PaperTradingAccount.user_id == uid)
        ).scalar_one_or_none()
        if acct is None:
            return None
        open_pos = (
            db.execute(
                select(func.count())
                .select_from(PaperPosition)
                .where(
                    PaperPosition.account_id == acct.id,
                    PaperPosition.qty > 0,
                )
            ).scalar()
            or 0
        )
        return {
            "open_positions_count": int(open_pos),
            "max_positions": int(getattr(settings, "portfolio_max_concurrent_positions", 5) or 5),
            "available_cash": float(getattr(acct, "balance", 0) or 0),
            "account_id": acct.id,
        }
    finally:
        db.close()


def load_user_portfolio_dict(
    user_id: str | None,
    *,
    timeout_s: float | None = None,
) -> dict[str, Any] | None:
    """Best-effort paper account snapshot for authenticated user.

    Fail-open: timeouts and errors return None (no invented portfolio).

    When ``timeout_s`` is ``0`` or negative, run the DB load directly (caller is
    expected to bound wall time, e.g. ``asyncio.wait_for``). Otherwise apply an
    internal ThreadPool wall-clock timeout for sync callers.
    """
    if not user_id:
        return None
    try:
        if timeout_s is not None and float(timeout_s) <= 0:
            return _load_user_portfolio_dict_impl(str(user_id))

        bound = float(
            timeout_s
            if timeout_s is not None
            else getattr(settings, "re001_portfolio_timeout_s", _DEFAULT_PORTFOLIO_LOAD_TIMEOUT_S)
            or _DEFAULT_PORTFOLIO_LOAD_TIMEOUT_S
        )
        bound = max(0.2, min(bound, 10.0))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_load_user_portfolio_dict_impl, str(user_id))
            return fut.result(timeout=bound)
    except concurrent.futures.TimeoutError:
        logger.warning(
            "RE-001 portfolio load timeout | user_id=%s | timeout_s=%s",
            user_id,
            timeout_s,
        )
        return None
    except Exception as exc:
        logger.warning(
            "RE-001 portfolio load failed | user_id=%s | err=%s",
            user_id,
            exc,
            exc_info=True,
        )
        return None


def system_risk_settings() -> dict[str, Any]:
    """Non-user risk policy snapshot (does not invent positions)."""
    return {
        "max_positions": int(getattr(settings, "portfolio_max_concurrent_positions", 5) or 5),
        "source": "system_policy",
    }
