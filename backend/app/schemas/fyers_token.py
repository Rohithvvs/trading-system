from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FyersTokenCreate(BaseModel):
    access_token: str
    # refresh_token removed - only access token supported. Extra fields (legacy) ignored.
    expires_at: Optional[datetime] = None

    class Config:
        extra = 'ignore'


class FyersTokenResponse(BaseModel):
    id: int
    access_token: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool
    # No refresh token fields after removal of auto-renewal support
    status: Optional[str] = None
    access_token_saved_at: Optional[datetime] = None
    last_error: Optional[str] = None
