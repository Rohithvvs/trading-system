from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.auth import UserCreate, UserResponse, GoogleLoginRequest
from ..services.auth_service import create_user, authenticate_user, google_auth, request_password_reset, confirm_password_reset
from ..db.session import get_db

router = APIRouter()

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    user = await create_user(db, user_in, ip_address=ip_address, user_agent=user_agent)
    
    return user

from fastapi.responses import JSONResponse
from ..schemas.auth import LoginRequest

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
    
    # 4. Set HttpOnly cookies
    response = JSONResponse(content={"message": "Logged in successfully", "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name}})
    
    # Secure in production (requires HTTPS)
    # Using secure=False for local dev right now
    # We should set samesite="lax" or "strict"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False, 
        samesite="lax",
        max_age=1440 * 60 # 24 hours
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=30 * 24 * 60 * 60 if request_data.remember_me else 7 * 24 * 60 * 60
    )
    
    return response

@router.post("/google")
async def google_login(request_data: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user = await google_auth(db, request_data.id_token, ip_address, user_agent)

    access_token, refresh_token = await create_user_session(
        db, str(user.id), ip_address, user_agent, remember_me=False
    )

    response = JSONResponse(content={
        "message": "Logged in successfully",
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name}
    })

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=1440 * 60
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

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
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
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
        
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=False, 
            samesite="lax",
            max_age=1440 * 60
        )
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60
        )
        
        return {"message": "Token refreshed"}
        
    except Exception as e:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

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

@router.get('/me', response_model=UserResponse)
async def get_me(current_user = Depends(get_current_active_user)):
    return current_user

