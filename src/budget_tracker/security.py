from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import get_db_session
from budget_tracker.models import UserORM, UserRole
from budget_tracker.schemas import Token

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{config.settings.app_base_path}{config.API_PREFIX}/auth/token")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def create_access_token(subject: str, role: str) -> Token:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=config.settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire_at}
    if not config.settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    encoded = jwt.encode(payload, config.settings.jwt_secret_key, algorithm=config.settings.jwt_algorithm)
    return Token(access_token=encoded, expires_in_seconds=config.settings.access_token_expire_minutes * 60)


def require_auth_configured() -> None:
    if not config.settings.auth_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY environment variable must be set before using authenticated endpoints",
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> UserORM:
    require_auth_configured()
    secret_key = config.settings.jwt_secret_key
    if not secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload: dict[str, Any] = jwt.decode(token, secret_key, algorithms=[config.settings.jwt_algorithm])
        username = payload.get("sub")
        if not isinstance(username, str) or not username:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.scalar(select(UserORM).where(UserORM.username == username))
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_admin(current_user: UserORM = Depends(get_current_user)) -> UserORM:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges are required for this operation",
        )
    return current_user
