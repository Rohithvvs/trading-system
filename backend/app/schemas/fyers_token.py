from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FyersTokenCreate(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None


class FyersTokenResponse(BaseModel):
    id: int
    access_token: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool
    
    refresh_token_present: bool = False
    refresh_token_expires_at: Optional[datetime] = None
    refresh_token_days_remaining: Optional[int] = None
    refresh_token_status: str = "expired"
    last_auto_renewal_at: Optional[datetime] = None
    last_auto_renewal_status: Optional[str] = None
