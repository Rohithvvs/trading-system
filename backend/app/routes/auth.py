from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.auth import UserCreate, UserResponse, GoogleLoginRequest, LoginRequest
from ..services.auth_service import create_user, authenticate_user, google_auth, request_password_reset, confirm_password_reset
from ..db.session import get_db

router = APIRouter()


def _request_is_https(request: Request) -> bool:
    """True when the public-facing request is HTTPS (Render terminates TLS and sets X-Forwarded-Proto)."""
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded:
        return forwarded == "https"
    return request.url.scheme == "https"


def _auth_cookie_params(request: Request, max_age: int) -> dict[str, Any]:
    """
    Cookie flags for SPA auth.

    Local HTTP: Secure=False, SameSite=Lax (same-site Vite proxy / localhost).
    HTTPS (Render + Vercel cross-origin): Secure=True, SameSite=None so
    credentials:include fetches from https://*.vercel.app can store and send cookies.
    """
    https = _request_is_https(request)
    samesite: Literal["lax", "strict", "none"] = "none" if https else "lax"
    return {
        "httponly": True,
        "secure": https,
        "samesite": samesite,
        "max_age": max_age,
        "path": "/",
    }


def _set_auth_cookies(
    response: Response,
    request: Request,
    access_token: str,
    refresh_token: str,
    *,
    remember_me: bool = False,
) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        **_auth_cookie_params(request, 1440 * 60),
    )
    refresh_max_age = 30 * 24 * 60 * 60 if remember_me else 7 * 24 * 60 * 60
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        **_auth_cookie_params(request, refresh_max_age),
    )


def _clear_auth_cookies(response: Response, request: Request) -> None:
    https = _request_is_https(request)
    samesite: Literal["lax", "strict", "none"] = "none" if https else "lax"
    # delete_cookie must match path/secure/samesite used when setting
    response.delete_cookie("access_token", path="/", secure=https, samesite=samesite)
    response.delete_cookie("refresh_token", path="/", secure=https, samesite=samesite)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    user = await create_user(db, user_in, ip_address=ip_address, user_agent=user_agent)
    
    return user

@router.post("/login")
async def login(request_data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    # 1. Authenticate
    user = await authenticate_user(db, request_data.email, request_data.password, ip_address, user_agent)
    
    # 2. Create Session
    from ..services.auth_service import create_user_session
    access_token, refresh_token = await create_user_session(
        db, str(user.id), ip_address, user_agent, request_data.remember_me
    )
    
    # 4. Set HttpOnly cookies (SameSite=None; Secure on HTTPS for Vercel↔Render)
    response = JSONResponse(content={"message": "Logged in successfully", "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name}})
    _set_auth_cookies(
        response,
        request,
        access_token,
        refresh_token,
        remember_me=bool(request_data.remember_me),
    )
    return response

@router.post("/google")
async def google_login(request_data: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    from ..services.auth_service import create_user_session
    user = await google_auth(db, request_data.id_token, ip_address, user_agent)

    access_token, refresh_token = await create_user_session(
        db, str(user.id), ip_address, user_agent, remember_me=False
    )

    response = JSONResponse(content={
        "message": "Logged in successfully",
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name}
    })
    _set_auth_cookies(response, request, access_token, refresh_token, remember_me=False)
    return response


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # 1. We could invalidate the refresh token in the database here by extracting it from cookies
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        # We can decode it to get jti or just clear it from the DB.
        # For now, just clearing the cookies is a basic logout.
        pass
        
    response = JSONResponse(content={"message": "Logged out successfully"})
    _clear_auth_cookies(response, request)
    return response

@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
        
    try:
        from ..core.security import decode_refresh_token
        payload = decode_refresh_token(refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            
        # In a real app we'd verify the refresh token hasn't been revoked in DB
        
        from ..services.auth_service import create_user_session
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # We don't know "remember_me" state here, default to False (7 days)
        # Ideally we'd look up the existing session
        new_access_token, new_refresh_token = await create_user_session(db, user_id, ip_address, user_agent, remember_me=False)
        
        response = JSONResponse(content={"message": "Token refreshed"})
        _set_auth_cookies(response, request, new_access_token, new_refresh_token, remember_me=False)
        return response
        
    except Exception as e:
        err_response = JSONResponse(content={"detail": "Invalid or expired refresh token"}, status_code=status.HTTP_401_UNAUTHORIZED)
        _clear_auth_cookies(err_response, request)
        return err_response

@router.get("/sessions")
async def get_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    try:
        from ..core.security import decode_access_token
        payload = decode_access_token(access_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            
        from ..services.auth_service import get_active_sessions
        sessions = await get_active_sessions(db, user_id)
        
        return {
            "sessions": [
                {
                    "id": str(s.id),
                    "device_name": "Unknown Device" if not s.device else s.device.device_name,
                    "ip_address": s.ip_address,
                    "last_active_at": s.last_active_at,
                    "created_at": s.created_at,
                    "is_current": False # We would determine this by matching session ID to current token jti
                } for s in sessions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

@router.post("/sessions/{session_id}/revoke")
async def revoke_user_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    try:
        from ..core.security import decode_access_token
        payload = decode_access_token(access_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            
        from ..services.auth_service import revoke_session
        await revoke_session(db, user_id, session_id)
        return {"message": "Session revoked"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

from ..schemas.auth import ForgotPasswordRequest, ResetPasswordRequest

@router.post("/forgot-password")
async def forgot_password(request_data: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    return await request_password_reset(db, request_data.email, ip_address)

@router.post("/reset-password")
async def reset_password(request_data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if request_data.password != request_data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")
    return await confirm_password_reset(db, request_data.token, request_data.password)

from ..core.deps import get_current_active_user
from ..schemas.user_profile import UserProfileResponse, UserProfileUpdate, UserProfilePatch
from ..services.user_profile_service import get_or_create_profile, profile_to_dict, update_profile

@router.get('/me', response_model=UserResponse)
async def get_me(current_user = Depends(get_current_active_user)):
    return current_user


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's profile (DB-backed, device-independent)."""
    profile = await get_or_create_profile(db, current_user)
    return profile_to_dict(profile, current_user)


@router.put("/profile", response_model=UserProfileResponse)
async def put_profile(
    body: UserProfileUpdate,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace/update profile fields for the authenticated user."""
    profile = await update_profile(db, current_user, body, partial=False)
    return profile_to_dict(profile, current_user)


@router.patch("/profile", response_model=UserProfileResponse)
async def patch_profile(
    body: UserProfilePatch,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Partial profile update; preferences are deep-merged."""
    profile = await update_profile(db, current_user, body, partial=True)
    return profile_to_dict(profile, current_user)

