"""Unified notification center — persistent, searchable, realtime-ready."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.retail import UserNotification
from ..schemas.retail import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
)


class NotificationCenterService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def list_notifications(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> NotificationListResponse:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        q = select(UserNotification).where(UserNotification.user_id == self.user_id)
        if category:
            q = q.where(UserNotification.category == category)
        if unread_only:
            q = q.where(UserNotification.is_read == False)  # noqa: E712
        if search:
            term = f"%{search}%"
            q = q.where(
                or_(
                    UserNotification.title.ilike(term),
                    UserNotification.body.ilike(term),
                    UserNotification.symbol.ilike(term),
                )
            )
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        unread = (
            self.db.scalar(
                select(func.count()).select_from(UserNotification).where(
                    UserNotification.user_id == self.user_id,
                    UserNotification.is_read == False,  # noqa: E712
                )
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                q.order_by(UserNotification.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return NotificationListResponse(
            items=[self._ser(r) for r in rows],
            total=int(total),
            unread_count=int(unread),
            page=page,
            page_size=page_size,
        )

    def create(self, payload: NotificationCreate) -> NotificationResponse:
        row = UserNotification(
            user_id=self.user_id,
            category=payload.category,
            title=payload.title,
            body=payload.body,
            level=payload.level,
            symbol=payload.symbol,
            payload_json=json.dumps(payload.payload) if payload.payload else None,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._ser(row)

    def create_simple(
        self,
        *,
        category: str,
        title: str,
        body: str,
        level: str = "info",
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> NotificationResponse:
        return self.create(
            NotificationCreate(
                category=category,  # type: ignore[arg-type]
                title=title,
                body=body,
                level=level,  # type: ignore[arg-type]
                symbol=symbol,
                payload=payload,
            )
        )

    def mark_read(self, ids: list[int] | None = None, mark_read: bool = True) -> int:
        q = select(UserNotification).where(UserNotification.user_id == self.user_id)
        if ids:
            q = q.where(UserNotification.id.in_(ids))
        rows = list(self.db.scalars(q).all())
        for r in rows:
            r.is_read = mark_read
        self.db.commit()
        return len(rows)

    def mark_all_read(self) -> int:
        return self.mark_read(ids=None, mark_read=True)

    def delete(self, ids: list[int]) -> int:
        rows = list(
            self.db.scalars(
                select(UserNotification).where(
                    UserNotification.user_id == self.user_id,
                    UserNotification.id.in_(ids),
                )
            ).all()
        )
        for r in rows:
            self.db.delete(r)
        self.db.commit()
        return len(rows)

    def unread_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(UserNotification).where(
                    UserNotification.user_id == self.user_id,
                    UserNotification.is_read == False,  # noqa: E712
                )
            )
            or 0
        )

    def _ser(self, row: UserNotification) -> NotificationResponse:
        payload = None
        if row.payload_json:
            try:
                payload = json.loads(row.payload_json)
            except Exception:
                payload = None
        return NotificationResponse(
            id=row.id,
            category=row.category,
            title=row.title,
            body=row.body,
            level=row.level,
            symbol=row.symbol,
            payload=payload,
            is_read=row.is_read,
            created_at=row.created_at,
        )
