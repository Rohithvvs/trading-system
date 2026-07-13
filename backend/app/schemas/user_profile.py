from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class NotificationPrefs(BaseModel):
    email: bool = True
    browser: bool = True
    scanner: bool = True
    priceAlerts: bool = True
    portfolioAlerts: bool = True
    weeklyReport: bool = True
    monthlyReport: bool = False


class ProfilePreferences(BaseModel):
    scannerMode: Optional[str] = "swing"
    defaultTimeframe: Optional[str] = "1d"
    defaultUniverse: Optional[str] = "NIFTY500"
    dashboardLayout: Optional[str] = "comfortable"
    themePreference: Optional[str] = "dark"
    notifications: Optional[NotificationPrefs] = None
    watchlist: Optional[list[str]] = None
    recentlyViewed: Optional[list[str]] = None

    class Config:
        extra = "allow"


class UserProfileBase(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    username: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    language: Optional[str] = Field(None, max_length=50)
    timezone: Optional[str] = Field(None, max_length=80)
    currency: Optional[str] = Field(None, max_length=16)
    address: Optional[str] = None
    postal_code: Optional[str] = Field(None, max_length=32)
    date_of_birth: Optional[str] = Field(None, max_length=32)
    bio: Optional[str] = None
    trading_experience: Optional[str] = Field(None, max_length=50)
    risk_profile: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = None
    preferences: Optional[dict[str, Any]] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        cleaned = v.strip()
        # Allow +, digits, spaces, dashes — basic sanity
        allowed = set("0123456789+ -()")
        if any(ch not in allowed for ch in cleaned):
            raise ValueError("Phone contains invalid characters")
        digits = sum(ch.isdigit() for ch in cleaned)
        if digits < 7 or digits > 15:
            raise ValueError("Phone must contain 7–15 digits")
        return cleaned

    @field_validator("postal_code")
    @classmethod
    def validate_postal(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        cleaned = v.strip()
        if len(cleaned) > 32:
            raise ValueError("Postal code too long")
        return cleaned

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        return v.strip().upper()[:16]


class UserProfileUpdate(UserProfileBase):
    """PUT body — full replace of provided fields (missing keys left unchanged if partial client)."""

    pass


class UserProfilePatch(UserProfileBase):
    """PATCH body — only non-null fields applied; preferences deep-merged."""

    pass


class UserProfileResponse(UserProfileBase):
    id: UUID
    user_id: UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_email_verified: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    # Convenience flat watchlist for clients
    watchlist: Optional[list[str]] = None

    class Config:
        from_attributes = True
