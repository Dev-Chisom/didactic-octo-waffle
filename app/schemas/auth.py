"""Auth request/response schemas."""

from uuid import UUID
from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str


class GoogleCallbackRequest(BaseModel):
    code: str


class TokenPair(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    role: str

    model_config = {"from_attributes": True}


class WorkspaceResponse(BaseModel):
    id: UUID
    plan: str
    creditsBalance: int
    limits: Optional[dict] = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserResponse
    workspace: WorkspaceResponse
    tokens: TokenPair


class RefreshResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
