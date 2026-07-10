from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
from ..models.auth import AuditLog
import uuid

class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        user_id: Optional[uuid.UUID],
        event_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log a security-critical event to the database.
        """
        audit_log = AuditLog(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_=metadata
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(audit_log)
        return audit_log
