from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import get_db_session
from budget_tracker.models import AuditLogORM, UserORM
from budget_tracker.schemas import Token, UserCreate, UserRead, UserUpdate
from budget_tracker.security import (
    create_access_token,
    get_current_admin,
    get_current_user,
    get_password_hash,
    require_auth_configured,
    verify_password,
)
from budget_tracker.services.auth import (
    check_token_rate_limit,
    ensure_user_not_locked,
    register_failed_login_attempt,
    reset_login_backoff,
)

router = APIRouter(prefix=f"{config.API_PREFIX}/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user: UserCreate,
    db: Session = Depends(get_db_session),
    admin_user: UserORM = Depends(get_current_admin),
) -> UserRead:
    require_auth_configured()
    db_user = UserORM(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        role=user.role.value,
        is_active=True,
    )
    audit_log = AuditLogORM(
        actor_user_id=admin_user.id,
        action="user.create",
        details=f"Admin '{admin_user.username}' created user '{db_user.username}' with role '{db_user.role}'",
    )
    try:
        db.add(db_user)
        db.flush()
        audit_log.target_user_id = db_user.id
        db.add(audit_log)
        db.commit()
        db.refresh(db_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered") from exc
    return UserRead.model_validate(db_user)


@router.post("/token", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_session),
) -> Token:
    require_auth_configured()
    client_host = request.client.host if request.client else "unknown"
    check_token_rate_limit(db, client_host)

    username = form_data.username.strip()
    user = db.scalar(select(UserORM).where(UserORM.username == username))
    if user is not None:
        ensure_user_not_locked(user)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        if user is not None:
            register_failed_login_attempt(db, user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    if user.failed_login_attempts > 0 or user.lockout_until is not None or user.last_failed_login_at is not None:
        reset_login_backoff(db, user)
    return create_access_token(subject=user.username, role=user.role)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: UserORM = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: Session = Depends(get_db_session),
    _: UserORM = Depends(get_current_admin),
) -> list[UserRead]:
    users = db.scalars(select(UserORM).order_by(UserORM.id)).all()
    return [UserRead.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db_session),
    _: UserORM = Depends(get_current_admin),
) -> UserRead:
    db_user = db.scalar(select(UserORM).where(UserORM.id == user_id))
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(db_user)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db_session),
    admin_user: UserORM = Depends(get_current_admin),
) -> UserRead:
    require_auth_configured()
    db_user = db.scalar(select(UserORM).where(UserORM.id == user_id))
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user fields were provided to update")

    new_role = update_data.get("role")
    new_is_active = update_data.get("is_active")
    if db_user.id == admin_user.id and (
        (new_role is not None and new_role.value != db_user.role) or (new_is_active is False)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot demote or deactivate themselves",
        )

    if "username" in update_data and update_data["username"] is not None:
        db_user.username = update_data["username"]
    if new_role is not None:
        db_user.role = new_role.value
    if new_is_active is not None:
        db_user.is_active = new_is_active
    if "password" in update_data and update_data["password"] is not None:
        db_user.hashed_password = get_password_hash(update_data["password"])

    audit_log = AuditLogORM(
        actor_user_id=admin_user.id,
        target_user_id=db_user.id,
        action="user.update",
        details=f"Admin '{admin_user.username}' updated user '{db_user.username}'",
    )
    try:
        db.add(db_user)
        db.add(audit_log)
        db.commit()
        db.refresh(db_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered") from exc

    return UserRead.model_validate(db_user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db_session),
    admin_user: UserORM = Depends(get_current_admin),
) -> None:
    require_auth_configured()
    db_user = db.scalar(select(UserORM).where(UserORM.id == user_id))
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if db_user.id == admin_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot delete themselves")

    audit_log = AuditLogORM(
        actor_user_id=admin_user.id,
        target_user_id=db_user.id,
        action="user.delete",
        details=f"Admin '{admin_user.username}' deleted user '{db_user.username}'",
    )
    db.add(audit_log)
    db.delete(db_user)
    db.commit()
