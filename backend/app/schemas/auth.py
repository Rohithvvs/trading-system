from pydantic import BaseModel, EmailStr, Field, UUID4
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "trader"

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserResponse(UserBase):
    id: UUID4
    email: EmailStr
    full_name: str
    role: str = "trader"
    is_active: bool = True
    provider: str = "email"
    profile_picture: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AuthSuccessResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str = "trader"
    access_token: str
    refresh_token: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    id_token: str

class TokenPayload(BaseModel):
    sub: str
    role: str = "trader"
    jti: str
    exp: int

class DeviceInfo(BaseModel):
    device_fingerprint: str
    device_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_info: Optional[DeviceInfo] = None
    remember_me: bool = False

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
