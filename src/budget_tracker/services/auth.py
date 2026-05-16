from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import SessionLocal
from budget_tracker.models import AuthRateLimitORM, UserORM, UserRole
from budget_tracker.security import get_password_hash, to_utc


def check_token_rate_limit(db: Session, client_key: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=config.settings.auth_rate_limit_window_seconds)

    db.execute(delete(AuthRateLimitORM).where(AuthRateLimitORM.requested_at < cutoff))
    recent_requests = db.scalars(
        select(AuthRateLimitORM.requested_at)
        .where(AuthRateLimitORM.client_key == client_key)
        .where(AuthRateLimitORM.requested_at >= cutoff)
        .order_by(AuthRateLimitORM.requested_at)
    ).all()

    if len(recent_requests) >= config.settings.auth_rate_limit_max_requests:
        oldest_request = to_utc(recent_requests[0]) or now
        retry_at = oldest_request + timedelta(seconds=config.settings.auth_rate_limit_window_seconds)
        retry_after_seconds = max(1, int((retry_at - now).total_seconds()))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this client. Please try again later.",
            headers={"Retry-After": str(retry_after_seconds)},
        )

    db.add(AuthRateLimitORM(client_key=client_key, requested_at=now))
    db.commit()


def register_failed_login_attempt(db: Session, user: UserORM) -> None:
    now = datetime.now(timezone.utc)
    user.failed_login_attempts += 1
    user.last_failed_login_at = now
    if user.failed_login_attempts >= config.settings.auth_lockout_threshold:
        user.lockout_until = now + timedelta(seconds=config.settings.auth_lockout_seconds)
        user.failed_login_attempts = 0
    db.add(user)
    db.commit()


def reset_login_backoff(db: Session, user: UserORM) -> None:
    user.failed_login_attempts = 0
    user.lockout_until = None
    user.last_failed_login_at = None
    db.add(user)
    db.commit()


def ensure_user_not_locked(user: UserORM) -> None:
    lockout_until = to_utc(user.lockout_until)
    if lockout_until is None:
        return
    now = datetime.now(timezone.utc)
    if lockout_until > now:
        retry_after = int((lockout_until - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account is temporarily locked due to failed logins. Retry in {retry_after} seconds.",
        )


def ensure_bootstrap_admin() -> None:
    username = config.settings.bootstrap_admin_username.strip() if config.settings.bootstrap_admin_username else None
    password = config.settings.bootstrap_admin_password
    if not username and not password:
        return
    if not username or not password:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD must both be set to create a bootstrap admin"
        )

    with SessionLocal() as session:
        existing_user = session.scalar(select(UserORM).where(UserORM.username == username))
        if existing_user is None:
            existing_user = UserORM(
                username=username,
                hashed_password=get_password_hash(password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            session.add(existing_user)
        else:
            existing_user.role = UserRole.ADMIN.value
            existing_user.is_active = True
            existing_user.hashed_password = get_password_hash(password)
            session.add(existing_user)
        session.commit()
