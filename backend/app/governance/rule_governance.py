from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import ROOT_DIR
from ..models.analysis import AnalysisHistory
from ..schemas.governance import (
    RuleGovernanceRecord,
    RuleGovernanceResponse,
    health_status_to_label,
)

logger = logging.getLogger("app.governance")

DEFAULT_BASELINE_FP_RATE = 0.15
MIN_SAMPLE_COUNT = 15
PROMOTED_RULES_DEFAULT = ["news_dedup", "sentiment_decay", "market_breadth"]
# Hardening (H1): avoid unbounded memory when evaluating large 30d windows.
_MAX_GOVERNANCE_HISTORY_ROWS = 50_000


def load_rule_baselines() -> Dict[str, float]:
    """Load Sprint baseline false-positive rates from baseline_v1.0.json."""
    baseline_file = ROOT_DIR / "baseline_v1.0.json"
    baselines: Dict[str, float] = {}

    if not baseline_file.exists():
        logger.info("Baseline metrics file %s does not exist; using defaults", baseline_file)
        return baselines

    try:
        with open(baseline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for rule_id, metrics in data.items():
                    if isinstance(metrics, dict) and "false_positive_rate" in metrics:
                        try:
                            baselines[rule_id] = float(metrics["false_positive_rate"])
                        except (TypeError, ValueError):
                            pass
    except Exception as e:
        logger.error("Failed to load baseline metrics from %s: %s", baseline_file, e)

    return baselines


def get_rule_baseline(rule_id: str, baselines: Optional[Dict[str, float]] = None) -> float:
    """Return baseline false-positive rate for rule_id, defaulting to 0.15."""
    if baselines is None:
        baselines = load_rule_baselines()
    return baselines.get(rule_id, DEFAULT_BASELINE_FP_RATE)


def outcome_fields_from_history(history: Any) -> Dict[str, Any]:
    """Derive outcome / false_positive labels from AnalysisHistory (BUY + backtest proxy).

    Positive outcome: backtest_score > 0 when available.
    False positive: BUY recommendation with non-positive backtest outcome.
    Returns empty dict when outcome cannot be determined (no backtest score).
    """
    bt = getattr(history, "backtest_score", None)
    if bt is None:
        return {}
    try:
        positive = float(bt) > 0.0
    except (TypeError, ValueError):
        return {}

    rec = (getattr(history, "recommendation", None) or "").upper()
    is_buy = rec in {"BUY", "STRONG_BUY"}
    return {
        "outcome": "positive" if positive else "negative",
        "false_positive": bool(is_buy and not positive),
        "outcome_source": "backtest_score",
    }


def _is_false_positive_record(
    shadow_outputs: Any,
    rule_id: str,
    history: Any = None,
) -> bool:
    """Determine if a history row is a false positive for ``rule_id``.

    Only rule-scoped telemetry is considered (no global flat FP selectors).
    When explicit labels are absent, derive from history backtest_score if the
    rule key is present on shadow_outputs.
    """
    if not shadow_outputs or not isinstance(shadow_outputs, dict):
        return False

    rule_telemetry = shadow_outputs.get(rule_id)
    if isinstance(rule_telemetry, dict):
        if rule_telemetry.get("false_positive") is True:
            return True
        if rule_telemetry.get("false_positive") is False:
            return False
        outcome = str(rule_telemetry.get("outcome", "")).lower()
        if outcome in ("negative", "zero", "loss", "false_positive"):
            return True
        if outcome in ("positive", "win", "profit"):
            return False

    # Derive only when this rule contributed telemetry on the row.
    if history is not None and rule_id in shadow_outputs:
        derived = outcome_fields_from_history(history)
        return bool(derived.get("false_positive"))

    return False


def _evaluate_rule_from_histories(
    rule_id: str,
    histories: Sequence[Any],
    *,
    baseline_fp_rate: float,
    evaluated_at: str,
) -> RuleGovernanceRecord:
    """Pure evaluation over a pre-loaded BUY history window (rule-scoped samples)."""
    evaluated_histories: List[Any] = []
    for history in histories:
        so = getattr(history, "shadow_outputs", None)
        if not so or not isinstance(so, dict):
            continue
        if rule_id in so:
            evaluated_histories.append(history)

    sample_count = len(evaluated_histories)

    if sample_count < MIN_SAMPLE_COUNT:
        status = "INSUFFICIENT_DATA"
        return RuleGovernanceRecord(
            rule_id=rule_id,
            evaluated_at=evaluated_at,
            false_positive_rate_30d=None,
            baseline_false_positive_rate=baseline_fp_rate,
            sample_count_30d=sample_count,
            health_status=status,
            health_label=health_status_to_label(status),
            status_reason=(
                f"Insufficient sample count ({sample_count} < {MIN_SAMPLE_COUNT} "
                "recommendations evaluated in 30-day window)"
            ),
        )

    fp_count = 0
    for history in evaluated_histories:
        if _is_false_positive_record(
            getattr(history, "shadow_outputs", None), rule_id, history=history
        ):
            fp_count += 1

    fp_rate = round(fp_count / sample_count, 4)

    if fp_rate <= baseline_fp_rate + 0.05:
        health_status = "GREEN"
        status_reason = (
            f"30-day false-positive rate ({fp_rate * 100:.1f}%) is within baseline "
            f"tolerance ({baseline_fp_rate * 100:.1f}% + 5.0%)"
        )
    elif fp_rate <= baseline_fp_rate + 0.15:
        health_status = "YELLOW"
        status_reason = (
            f"30-day false-positive rate ({fp_rate * 100:.1f}%) exceeds baseline "
            f"tolerance but is within caution threshold "
            f"({baseline_fp_rate * 100:.1f}% + 15.0%)"
        )
    else:
        health_status = "RED"
        status_reason = (
            f"30-day false-positive rate ({fp_rate * 100:.1f}%) exceeds degradation "
            f"threshold ({baseline_fp_rate * 100:.1f}% + 15.0%)"
        )

    return RuleGovernanceRecord(
        rule_id=rule_id,
        evaluated_at=evaluated_at,
        false_positive_rate_30d=fp_rate,
        baseline_false_positive_rate=baseline_fp_rate,
        sample_count_30d=sample_count,
        health_status=health_status,
        health_label=health_status_to_label(health_status),
        status_reason=status_reason,
    )


async def _load_buy_histories_30d(db: AsyncSession) -> List[Any]:
    """Load 30-day BUY histories with only columns required for governance evaluation."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=30)
    # Column projection: avoid loading unused ORM fields (H1 reliability).
    stmt = (
        select(
            AnalysisHistory.recommendation,
            AnalysisHistory.backtest_score,
            AnalysisHistory.shadow_outputs,
            AnalysisHistory.created_at,
        )
        .where(
            AnalysisHistory.created_at >= start_date,
            AnalysisHistory.recommendation == "BUY",
        )
        .order_by(AnalysisHistory.created_at.desc())
        .limit(_MAX_GOVERNANCE_HISTORY_ROWS + 1)
    )
    result = await db.execute(stmt)
    rows = result.all()
    if len(rows) > _MAX_GOVERNANCE_HISTORY_ROWS:
        logger.warning(
            "Governance 30d BUY history truncated | loaded=%s | cap=%s",
            len(rows),
            _MAX_GOVERNANCE_HISTORY_ROWS,
        )
        rows = rows[:_MAX_GOVERNANCE_HISTORY_ROWS]
    return list(rows)


async def evaluate_rule_governance(
    db: AsyncSession, rule_id: str, baselines: Optional[Dict[str, float]] = None
) -> RuleGovernanceRecord:
    """Evaluate 30-day performance of a promoted rule against its baseline."""
    evaluated_at = datetime.now(timezone.utc).isoformat()
    baseline_fp_rate = get_rule_baseline(rule_id, baselines)
    t0 = time.perf_counter()
    try:
        histories = await _load_buy_histories_30d(db)
        record = _evaluate_rule_from_histories(
            rule_id,
            histories,
            baseline_fp_rate=baseline_fp_rate,
            evaluated_at=evaluated_at,
        )
        logger.info(
            "rule_governance_evaluated | rule_id=%s | status=%s | samples=%s | elapsed_ms=%.1f",
            rule_id,
            record.health_status,
            record.sample_count_30d,
            (time.perf_counter() - t0) * 1000.0,
        )
        return record
    except Exception:
        logger.exception(
            "rule_governance_failed | rule_id=%s | elapsed_ms=%.1f",
            rule_id,
            (time.perf_counter() - t0) * 1000.0,
        )
        # Fail closed to INSUFFICIENT_DATA rather than crashing CLI / API (reliability).
        status = "INSUFFICIENT_DATA"
        return RuleGovernanceRecord(
            rule_id=rule_id,
            evaluated_at=evaluated_at,
            false_positive_rate_30d=None,
            baseline_false_positive_rate=baseline_fp_rate,
            sample_count_30d=0,
            health_status=status,
            health_label=health_status_to_label(status),
            status_reason="Governance evaluation failed due to internal error; see logs",
        )


async def evaluate_all_promoted_rules(
    db: AsyncSession, rule_ids: Optional[List[str]] = None
) -> RuleGovernanceResponse:
    """Evaluate rule governance across all promoted production rules.

    Hardening: single 30d BUY history load shared across all rules (no N+1 queries).
    """
    now = datetime.now(timezone.utc)
    evaluated_at = now.isoformat()
    if rule_ids is None:
        rule_ids = list(PROMOTED_RULES_DEFAULT)

    baselines = load_rule_baselines()
    t0 = time.perf_counter()
    try:
        histories = await _load_buy_histories_30d(db)
        records: List[RuleGovernanceRecord] = []
        for rid in rule_ids:
            rec = _evaluate_rule_from_histories(
                rid,
                histories,
                baseline_fp_rate=get_rule_baseline(rid, baselines),
                evaluated_at=evaluated_at,
            )
            records.append(rec)
        logger.info(
            "rule_governance_all_evaluated | rules=%s | history_rows=%s | elapsed_ms=%.1f",
            len(records),
            len(histories),
            (time.perf_counter() - t0) * 1000.0,
        )
        return RuleGovernanceResponse(
            evaluated_at=evaluated_at,
            promoted_rules_count=len(records),
            rules=records,
        )
    except Exception:
        logger.exception(
            "rule_governance_all_failed | elapsed_ms=%.1f",
            (time.perf_counter() - t0) * 1000.0,
        )
        # Preserve response shape for operators; mark each rule insufficient.
        status = "INSUFFICIENT_DATA"
        fallback = [
            RuleGovernanceRecord(
                rule_id=rid,
                evaluated_at=evaluated_at,
                false_positive_rate_30d=None,
                baseline_false_positive_rate=get_rule_baseline(rid, baselines),
                sample_count_30d=0,
                health_status=status,
                health_label=health_status_to_label(status),
                status_reason="Governance evaluation failed due to internal error; see logs",
            )
            for rid in rule_ids
        ]
        return RuleGovernanceResponse(
            evaluated_at=evaluated_at,
            promoted_rules_count=len(fallback),
            rules=fallback,
        )


def persist_governance_report(
    response: RuleGovernanceResponse, reports_dir: Any = None
) -> Path:
    """Write machine-readable governance report JSON to governance reports directory.

    Raises OSError/IOError on failure after structured logging (callers may catch).
    """
    from ..config import settings

    base = Path(reports_dir) if reports_dir is not None else Path(settings.governance_reports_dir)
    if not base.is_absolute():
        base = ROOT_DIR / base

    try:
        base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = base / f"rule_governance_{ts}.json"
        payload = response.model_dump()
        # Atomic-ish write: temp then replace to avoid partial files on crash.
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        logger.info(
            "Governance report persisted | path=%s | rules=%s",
            path,
            response.promoted_rules_count,
        )
        return path
    except Exception:
        logger.exception(
            "Governance report persist failed | reports_dir=%s | rules=%s",
            base,
            response.promoted_rules_count,
        )
        raise
