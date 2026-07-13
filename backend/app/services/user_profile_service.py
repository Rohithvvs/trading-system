"""CRUD for authenticated user profiles (DB-backed, not browser storage)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auth import User
from ..models.user_profile import UserProfile
from ..schemas.user_profile import UserProfilePatch, UserProfileUpdate


DEFAULT_PREFERENCES: dict[str, Any] = {
    "scannerMode": "swing",
    "defaultTimeframe": "1d",
    "defaultUniverse": "NIFTY500",
    "dashboardLayout": "comfortable",
    "themePreference": "dark",
    "notifications": {
        "email": True,
        "browser": True,
        "scanner": True,
        "priceAlerts": True,
        "portfolioAlerts": True,
        "weeklyReport": True,
        "monthlyReport": False,
    },
    "watchlist": [],
    "recentlyViewed": [],
}


def _merge_preferences(
    existing: Optional[dict[str, Any]],
    incoming: Optional[dict[str, Any]],
) -> dict[str, Any]:
    base = {**DEFAULT_PREFERENCES, **(existing or {})}
    if not incoming:
        return base
    merged = {**base, **incoming}
    if "notifications" in incoming and isinstance(incoming["notifications"], dict):
        prev = base.get("notifications") if isinstance(base.get("notifications"), dict) else {}
        merged["notifications"] = {**prev, **incoming["notifications"]}
    if "watchlist" in incoming and isinstance(incoming["watchlist"], list):
        # Normalize symbols
        merged["watchlist"] = [str(s).strip().upper() for s in incoming["watchlist"] if str(s).strip()]
    return merged


async def get_or_create_profile(db: AsyncSession, user: User) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = UserProfile(
        user_id=user.id,
        display_name=user.full_name,
        country="India",
        language="English",
        currency="INR",
        timezone="Asia/Kolkata",
        avatar_url=user.profile_picture,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def profile_to_dict(profile: UserProfile, user: User) -> dict[str, Any]:
    prefs = _merge_preferences(profile.preferences, None)
    watchlist = prefs.get("watchlist") if isinstance(prefs.get("watchlist"), list) else []
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "is_email_verified": user.is_email_verified,
        "display_name": profile.display_name,
        "username": profile.username,
        "phone": profile.phone,
        "country": profile.country,
        "state": profile.state,
        "city": profile.city,
        "language": profile.language,
        "timezone": profile.timezone,
        "currency": profile.currency,
        "address": profile.address,
        "postal_code": profile.postal_code,
        "date_of_birth": profile.date_of_birth,
        "bio": profile.bio,
        "trading_experience": profile.trading_experience,
        "risk_profile": profile.risk_profile,
        "avatar_url": profile.avatar_url or user.profile_picture,
        "preferences": prefs,
        "watchlist": watchlist,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


_SCALAR_FIELDS = (
    "display_name",
    "username",
    "phone",
    "country",
    "state",
    "city",
    "language",
    "timezone",
    "currency",
    "address",
    "postal_code",
    "date_of_birth",
    "bio",
    "trading_experience",
    "risk_profile",
    "avatar_url",
)


async def update_profile(
    db: AsyncSession,
    user: User,
    payload: UserProfileUpdate | UserProfilePatch,
    *,
    partial: bool = False,
) -> UserProfile:
    profile = await get_or_create_profile(db, user)
    # Always exclude unset so clients can send partial bodies on PUT as well
    data = payload.model_dump(exclude_unset=True)

    for field in _SCALAR_FIELDS:
        if field not in data:
            continue
        value = data[field]
        # Skip explicit nulls on PATCH to avoid wiping fields unintentionally
        if partial and value is None:
            continue
        setattr(profile, field, value)

    if "preferences" in data and data["preferences"] is not None:
        profile.preferences = _merge_preferences(
            profile.preferences if isinstance(profile.preferences, dict) else None,
            data["preferences"] if isinstance(data["preferences"], dict) else None,
        )

    # Keep User.full_name in sync when display_name provided
    if data.get("display_name"):
        user.full_name = str(data["display_name"]).strip() or user.full_name

    if "avatar_url" in data:
        user.profile_picture = data["avatar_url"]

    db.add(profile)
    db.add(user)
    await db.commit()
    await db.refresh(profile)
    await db.refresh(user)
    return profile
