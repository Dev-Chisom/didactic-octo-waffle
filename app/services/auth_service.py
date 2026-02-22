"""Auth: register, login, token refresh, forgot/reset password."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.user import User
from app.db.models.workspace import Workspace, Member
from app.db.models.password_reset import PasswordResetToken
from app.services.email_service import send_password_reset_email


def register(
    db: Session,
    email: str,
    password: str,
    name: Optional[str] = None,
) -> tuple[User, Workspace, str, str]:
    """Create user, default workspace, and owner member. Return (user, workspace, access, refresh)."""
    if db.query(User).filter(User.email == email).first():
        raise ValueError("Email already registered")
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        name=name or email.split("@")[0],
        role="user",
    )
    db.add(user)
    workspace = Workspace(
        id=uuid.uuid4(),
        owner_id=user.id,
        plan="free",
        credits_balance=0,
        limits={"maxSeries": 1, "maxConnectedAccounts": 1},
    )
    db.add(workspace)
    member = Member(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
    db.commit()
    db.refresh(user)
    db.refresh(workspace)
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return user, workspace, access, refresh


def login(db: Session, email: str, password: str) -> tuple[User, Workspace, str, str]:
    """Authenticate user; return (user, workspace, access, refresh)."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password")
    # Resolve primary workspace
    member = db.query(Member).filter(Member.user_id == user.id).first()
    if not member:
        raise ValueError("No workspace found")
    workspace = db.query(Workspace).filter(Workspace.id == member.workspace_id).first()
    if not workspace:
        raise ValueError("Workspace not found")
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return user, workspace, access, refresh


def refresh_tokens(db: Session, refresh_token: str) -> tuple[User, str, str]:
    """Validate refresh token and return (user, new_access_token, new_refresh_token)."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("Invalid refresh token")
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid refresh token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return user, access, refresh


def request_password_reset(db: Session, email: str) -> None:
    """Create a password reset token for the user if email exists. Always returns without error."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash:
        return
    # Invalidate any existing tokens for this user
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    db.add(
        PasswordResetToken(
            token=token,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    try:
        send_password_reset_email(user.email, token)
    except Exception:
        pass  # Token is created; email failure is non-fatal


def reset_password(db: Session, token: str, new_password: str) -> None:
    """Consume token and set new password. Raises ValueError if token invalid."""
    record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == token,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if not record:
        raise ValueError("Invalid or expired reset token")
    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise ValueError("User not found")
    user.password_hash = hash_password(new_password)
    db.delete(record)
    db.commit()
