from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
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
    ) -> None:
        """
        No-op audit logging for single-user system.
        """
        return None
