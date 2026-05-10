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
