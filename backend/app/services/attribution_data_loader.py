"""Shared loader: AnalysisHistory → attribution ablation records.

Fixes wrong ORM field mapping (situation_tags / confidence) and applies
evaluation-window + shadow-feature filters used by REST and CLI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisHistory


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float parse; corrupt telemetry must not crash report generation."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_score_0_100(value: float | None, default: float = 50.0) -> float:
    """Normalize confidence-like values to a 0–100 score scale."""
    if value is None:
        return default
    v = _safe_float(value, default)
    if 0.0 <= v <= 1.0:
        return v * 100.0
    return max(0.0, min(100.0, v))


def _situation_tag_from_history(history: AnalysisHistory) -> str:
    tags = getattr(history, "situation_tags", None) or []
    if isinstance(tags, list) and tags:
        return str(tags[0])
    if isinstance(tags, str) and tags.strip():
        return tags.strip()
    return "GENERAL_MARKET"


def _actual_outcome_from_history(history: AnalysisHistory) -> bool:
    """Non-circular outcome proxy: prefer backtest return; else recommendation action.

    Never uses confidence as ground truth (audit H4).
    """
    bt = getattr(history, "backtest_score", None)
    if bt is not None:
        try:
            return float(bt) > 0.0
        except (TypeError, ValueError):
            pass
    rec = (getattr(history, "recommendation", None) or "").upper()
    return rec in {"BUY", "STRONG_BUY"}


def history_to_ablation_record(history: AnalysisHistory) -> dict[str, Any] | None:
    """Convert one AnalysisHistory row to an ablation record.

    Returns None when shadow_outputs lacks both candidate features.
    """
    so = history.shadow_outputs if isinstance(history.shadow_outputs, dict) else {}
    decay_telemetry = so.get("sentiment_decay") if isinstance(so.get("sentiment_decay"), dict) else None
    breadth_telemetry = so.get("market_breadth") if isinstance(so.get("market_breadth"), dict) else None

    if decay_telemetry is None and breadth_telemetry is None:
        return None

    baseline_score = _as_score_0_100(getattr(history, "confidence", None), default=50.0)

    # Sentiment telemetry is on roughly [-1, 1]; convert delta to score points.
    if decay_telemetry is not None:
        raw_sent = _safe_float(decay_telemetry.get("aggregate_raw_score"), 0.0)
        dec_sent = _safe_float(decay_telemetry.get("aggregate_decayed_score"), raw_sent)
        decay_delta = (dec_sent - raw_sent) * 50.0
    else:
        decay_delta = 0.0

    if breadth_telemetry is not None:
        breadth_contrib = _safe_float(breadth_telemetry.get("soft_score_contribution"), 0.0)
    else:
        breadth_contrib = 0.0

    return {
        "situation_tag": _situation_tag_from_history(history),
        "actual_outcome": _actual_outcome_from_history(history),
        "scores": {
            "baseline": baseline_score,
            "decay_only": max(0.0, min(100.0, baseline_score + decay_delta)),
            "breadth_only": max(0.0, min(100.0, baseline_score + breadth_contrib)),
            "combined": max(0.0, min(100.0, baseline_score + decay_delta + breadth_contrib)),
        },
        "decay_delta": decay_delta,
        "breadth_contrib": breadth_contrib,
    }


def records_from_histories(histories: Sequence[AnalysisHistory]) -> tuple[list[dict[str, Any]], list[float], list[float]]:
    """Build ablation records and correlation series from history rows."""
    records: list[dict[str, Any]] = []
    decay_deltas: list[float] = []
    breadth_contribs: list[float] = []
    for h in histories:
        rec = history_to_ablation_record(h)
        if rec is None:
            continue
        records.append(rec)
        decay_deltas.append(float(rec["decay_delta"]))
        breadth_contribs.append(float(rec["breadth_contrib"]))
    return records, decay_deltas, breadth_contribs


async def load_shadow_histories(
    db: AsyncSession,
    *,
    days: int = 30,
    limit: int = 500,
) -> list[AnalysisHistory]:
    """Load recent analysis rows within the evaluation window.

    Filtering for shadow feature presence is applied in Python after fetch
    (JSONB key presence varies by dialect). Date filter uses created_at.
    """
    days = max(1, min(int(days), 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(AnalysisHistory)
        .where(AnalysisHistory.created_at >= cutoff)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
