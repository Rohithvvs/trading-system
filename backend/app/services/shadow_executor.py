from __future__ import annotations

import atexit
import copy
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.analysis import AnalysisHistory, ArticleDedupLog
from app.models.stock import WatchedStock
from app.schemas.analysis import ArticleItem
from .news_deduplication import _as_utc, _clean_title, deduplicate_articles

logger = logging.getLogger("app.shadow_executor")

# SC-003: allow orchestrator to persist AnalysisHistory after news agent returns.
_HISTORY_RETRY_ATTEMPTS = 10
_HISTORY_RETRY_DELAY_SECONDS = 0.5  # total wait budget ~5s
# Drop work when backlog is large so bulk scans cannot unbounded-grow memory.
_MAX_PENDING_SHADOW_TASKS = 64
# Accept history rows created slightly before run start (clock skew / flush delay).
_HISTORY_NOT_BEFORE_SLACK = timedelta(seconds=2)


class ShadowThreadPool:
    """Dedicated thread pool for background shadow mode execution (max_workers=4)."""

    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ShadowWorker")

    @classmethod
    def submit_task(cls, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            # Best-effort backpressure using the executor work queue size.
            work_queue = getattr(cls._executor, "_work_queue", None)
            if work_queue is not None and work_queue.qsize() >= _MAX_PENDING_SHADOW_TASKS:
                logger.warning(
                    "ShadowThreadPool queue full (pending>=%s); dropping task",
                    _MAX_PENDING_SHADOW_TASKS,
                )
                return None
            return cls._executor.submit(fn, *args, **kwargs)
        except Exception as e:
            logger.warning("Failed to submit task to ShadowThreadPool: %s", e)
            return None

    @classmethod
    def shutdown(cls, wait: bool = False) -> None:
        try:
            cls._executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            # Python < 3.9 compatibility for cancel_futures
            cls._executor.shutdown(wait=wait)
        except Exception as exc:  # pragma: no cover
            logger.warning("ShadowThreadPool shutdown failed: %s", exc)


atexit.register(lambda: ShadowThreadPool.shutdown(wait=False))


def _article_identity(article: ArticleItem) -> str:
    """Stable identity for keep/remove comparison when URL is missing."""
    if article.url:
        return article.url
    published = article.published_at.isoformat() if article.published_at else ""
    return f"{article.title}|{published}|{article.source}"


def _normalize_shadow_outputs(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


def _build_removed_audit_rows(
    symbol: str,
    removed_articles: list[ArticleItem],
    kept_articles: list[ArticleItem],
) -> list[ArticleDedupLog]:
    rows: list[ArticleDedupLog] = []
    for removed in removed_articles:
        clean_removed = _clean_title(removed.title)
        kept_match: ArticleItem | None = None
        similarity = 3.0
        for kept in kept_articles:
            clean_kept = _clean_title(kept.title)
            overlap = len(clean_removed.intersection(clean_kept))
            if overlap >= 3:
                kept_match = kept
                similarity = float(overlap)
                break
        if kept_match is None and kept_articles:
            kept_match = kept_articles[0]

        kept_id = _article_identity(kept_match) if kept_match else "unknown"
        kept_title = kept_match.title if kept_match else "unknown"
        rows.append(
            ArticleDedupLog(
                symbol=symbol,
                kept_id=kept_id,
                deduplicated_id=_article_identity(removed),
                kept_title=kept_title,
                deduplicated_title=removed.title,
                similarity=similarity,
                reason="Duplicate in 4h window, source priority tie-breaker applied",
            )
        )
    return rows


def _persist_audit_logs(session: Session, rows: list[ArticleDedupLog]) -> None:
    """Commit audit rows independently so telemetry failures cannot roll them back."""
    if not rows:
        return
    for row in rows:
        session.add(row)
    session.commit()


def _resolve_stock_id(session: Session, symbol: str) -> int | None:
    return session.execute(
        select(WatchedStock.id).where(WatchedStock.symbol == symbol)
    ).scalar_one_or_none()


def _load_latest_history(
    session: Session,
    stock_id: int,
    not_before: datetime | None = None,
) -> AnalysisHistory | None:
    """Return latest history row, optionally requiring created_at >= not_before."""
    history = session.execute(
        select(AnalysisHistory)
        .where(AnalysisHistory.stock_id == stock_id)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if history is None or not_before is None or history.created_at is None:
        return history

    created = history.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    else:
        created = created.astimezone(timezone.utc)

    threshold = not_before.astimezone(timezone.utc) - _HISTORY_NOT_BEFORE_SLACK
    if created < threshold:
        # Stale prior scan — keep waiting for the current analysis row.
        return None
    return history


def _persist_shadow_telemetry(
    symbol: str,
    stock_id: int | None,
    original_news_count: int,
    kept_news_count: int,
    removed_news_count: int,
    not_before: datetime | None = None,
) -> None:
    """Attach news_dedup telemetry to the current AnalysisHistory for the stock.

    Retries briefly so the orchestrator can finish ``_persist_analysis`` after
    the news agent returns (FR-010 / SC-003). Skips stale prior-scan rows when
    ``not_before`` is provided.
    """
    if stock_id is None:
        logger.warning(
            "Shadow telemetry skipped: watched stock not found | symbol=%s",
            symbol,
        )
        return

    telemetry = {
        "original_news_count": original_news_count,
        "kept_news_count": kept_news_count,
        "removed_news_count": removed_news_count,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    last_error: Exception | None = None
    for attempt in range(_HISTORY_RETRY_ATTEMPTS):
        session = SessionLocal()
        try:
            history = _load_latest_history(session, stock_id, not_before=not_before)
            if history is None:
                session.close()
                if attempt + 1 < _HISTORY_RETRY_ATTEMPTS:
                    time.sleep(_HISTORY_RETRY_DELAY_SECONDS)
                continue

            shadow_outputs = _normalize_shadow_outputs(history.shadow_outputs)
            # Nested under news_dedup so multi-feature shadow keys can coexist.
            # Flat FR-010 keys are also mirrored for literal-spec consumers.
            shadow_outputs["news_dedup"] = telemetry
            shadow_outputs["original_news_count"] = original_news_count
            shadow_outputs["kept_news_count"] = kept_news_count
            history.shadow_outputs = shadow_outputs
            session.commit()
            logger.info(
                "Shadow news dedup complete | symbol=%s | original=%s | kept=%s | "
                "removed=%s | history_id=%s | attempt=%s",
                symbol,
                original_news_count,
                kept_news_count,
                removed_news_count,
                history.id,
                attempt + 1,
            )
            return
        except Exception as exc:
            last_error = exc
            try:
                session.rollback()
            except Exception:
                pass
            logger.warning(
                "Shadow telemetry write failed (attempt %s/%s): %s | symbol=%s",
                attempt + 1,
                _HISTORY_RETRY_ATTEMPTS,
                exc,
                symbol,
            )
            if attempt + 1 < _HISTORY_RETRY_ATTEMPTS:
                time.sleep(_HISTORY_RETRY_DELAY_SECONDS)
        finally:
            session.close()

    logger.warning(
        "Shadow telemetry not written after %s attempts | symbol=%s | last_error=%s",
        _HISTORY_RETRY_ATTEMPTS,
        symbol,
        last_error,
    )


def execute_shadow_news_dedup(symbol: str, articles: list[ArticleItem]) -> None:
    """Run deduplication in shadow mode, writing audit logs and telemetry to DB.

    Isolation guarantees:
    - Deep-copies input so production article lists are never mutated (FR-007/008).
    - All exceptions are caught and logged as warnings (FR-011).
    - Audit log commits are independent of telemetry updates (H3).
    """
    try:
        if not articles:
            return

        run_started_at = datetime.now(timezone.utc)

        # 1. Deep-copy articles to prevent downstream mutations
        articles_copy = copy.deepcopy(articles)

        # 2. Run pure deduplication logic
        kept_articles = deduplicate_articles(articles_copy)

        # Only articles that entered the capped window can be "removed" duplicates.
        # Older items dropped by the 50-cap are not audit-logged as duplicates.
        # Normalize timestamps so mixed naive/aware values never raise TypeError.
        capped_candidates = sorted(
            articles_copy, key=lambda x: _as_utc(x.published_at), reverse=True
        )[:50]
        kept_ids = {_article_identity(a) for a in kept_articles}
        removed_articles = [
            a for a in capped_candidates if _article_identity(a) not in kept_ids
        ]

        original_news_count = len(capped_candidates)
        kept_news_count = len(kept_articles)
        removed_news_count = len(removed_articles)

        audit_rows = _build_removed_audit_rows(symbol, removed_articles, kept_articles)

        # 3. Persist audit logs (own transaction — survives telemetry failures)
        session = SessionLocal()
        stock_id: int | None = None
        try:
            _persist_audit_logs(session, audit_rows)
            stock_id = _resolve_stock_id(session, symbol)
        except Exception as audit_error:
            try:
                session.rollback()
            except Exception:
                pass
            logger.warning(
                "Shadow audit log transaction failed: %s | symbol=%s",
                audit_error,
                symbol,
            )
        finally:
            session.close()

        # 4. Persist telemetry with retry for post-news AnalysisHistory creation
        try:
            _persist_shadow_telemetry(
                symbol=symbol,
                stock_id=stock_id,
                original_news_count=original_news_count,
                kept_news_count=kept_news_count,
                removed_news_count=removed_news_count,
                not_before=run_started_at,
            )
        except Exception as telemetry_error:
            logger.warning(
                "Shadow telemetry path failed: %s | symbol=%s",
                telemetry_error,
                symbol,
            )

    except Exception as e:
        logger.warning(
            "Shadow news deduplication execution failed: %s | symbol=%s", e, symbol
        )
