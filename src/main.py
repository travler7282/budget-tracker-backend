from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
    delete,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "budget_tracker.db"
API_PREFIX = "/api/v1"
APP_VERSION = "2.0.0"


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret_key: str | None
    jwt_algorithm: str
    access_token_expire_minutes: int
    auth_rate_limit_window_seconds: int
    auth_rate_limit_max_requests: int
    auth_lockout_threshold: int
    auth_lockout_seconds: int
    bootstrap_admin_username: str | None
    bootstrap_admin_password: str | None
    host: str
    port: int
    reload: bool
    tls_cert_file: str | None
    tls_key_file: str | None
    tls_ca_file: str | None
    app_base_path: str

    @property
    def auth_ready(self) -> bool:
        return bool(self.jwt_secret_key)

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_cert_file and self.tls_key_file)

    @property
    def tls_misconfigured(self) -> bool:
        return bool(self.tls_cert_file) ^ bool(self.tls_key_file)


def strtobool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def normalize_base_path(value: str | None) -> str:
    if not value:
        return ""
    cleaned = "/" + value.strip().strip("/")
    return "" if cleaned == "/" else cleaned


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", os.getenv("ALGORITHM", "HS256")),
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
        auth_rate_limit_window_seconds=int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")),
        auth_rate_limit_max_requests=int(os.getenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "10")),
        auth_lockout_threshold=int(os.getenv("AUTH_LOCKOUT_THRESHOLD", "5")),
        auth_lockout_seconds=int(os.getenv("AUTH_LOCKOUT_SECONDS", "300")),
        bootstrap_admin_username=os.getenv("BOOTSTRAP_ADMIN_USERNAME"),
        bootstrap_admin_password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD"),
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=strtobool(os.getenv("APP_RELOAD"), default=False),
        tls_cert_file=os.getenv("TLS_CERT_FILE"),
        tls_key_file=os.getenv("TLS_KEY_FILE"),
        tls_ca_file=os.getenv("TLS_CA_FILE"),
        app_base_path=normalize_base_path(os.getenv("APP_BASE_PATH")),
    )


settings = get_settings()
sqlite_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=sqlite_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_PREFIX}/auth/token")


class Base(DeclarativeBase):
    pass


class BudgetItemType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    LOAN = "loan"
    CREDIT_CARD = "credit_card"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    OTHER = "other"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.USER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lockout_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    budget_items: Mapped[list[BudgetItemORM]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class BudgetItemORM(Base):
    __tablename__ = "budget_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_apr: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    owner: Mapped[UserORM] = relationship(back_populates="budget_items")


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AuthRateLimitORM(Base):
    __tablename__ = "auth_rate_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


def strip_string(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class UserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: Any) -> Any:
        return strip_string(value)


class UserRead(ApiModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class BudgetItemBase(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    item_type: BudgetItemType | None = Field(default=None, alias="itemType")
    scheduled_date: date | None = Field(default=None, alias="budgetedDate")
    effective_date: date | None = Field(default=None, alias="actualDate")
    planned_amount: Decimal = Field(alias="budgetedAmount")
    actual_amount: Decimal | None = Field(default=None, alias="actualAmount")
    interest_rate: Decimal | None = Field(default=None, alias="interestRate")
    is_apr: bool | None = Field(default=None, alias="isApr")
    is_credit_card: bool | None = Field(default=None, alias="isCreditCard")
    is_loan: bool | None = Field(default=None, alias="isLoan")
    is_expense: bool | None = Field(default=None, alias="isExpense")
    is_income: bool | None = Field(default=None, alias="isIncome")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return strip_string(value)


class BudgetItemCreate(BudgetItemBase):
    pass


class BudgetItemUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    item_type: BudgetItemType | None = Field(default=None, alias="itemType")
    scheduled_date: date | None = Field(default=None, alias="budgetedDate")
    effective_date: date | None = Field(default=None, alias="actualDate")
    planned_amount: Decimal | None = Field(default=None, alias="budgetedAmount")
    actual_amount: Decimal | None = Field(default=None, alias="actualAmount")
    interest_rate: Decimal | None = Field(default=None, alias="interestRate")
    is_apr: bool | None = Field(default=None, alias="isApr")
    is_credit_card: bool | None = Field(default=None, alias="isCreditCard")
    is_loan: bool | None = Field(default=None, alias="isLoan")
    is_expense: bool | None = Field(default=None, alias="isExpense")
    is_income: bool | None = Field(default=None, alias="isIncome")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return strip_string(value)


class BudgetItemRead(ApiModel):
    id: int
    name: str
    description: str | None
    category: str | None
    item_type: BudgetItemType = Field(alias="itemType")
    scheduled_date: date | None = Field(alias="budgetedDate")
    effective_date: date | None = Field(alias="actualDate")
    planned_amount: Decimal = Field(alias="budgetedAmount")
    actual_amount: Decimal | None = Field(alias="actualAmount")
    interest_rate: Decimal | None = Field(alias="interestRate")
    is_apr: bool | None = Field(alias="isApr")
    is_credit_card: bool = Field(alias="isCreditCard")
    is_loan: bool = Field(alias="isLoan")
    is_expense: bool = Field(alias="isExpense")
    is_income: bool = Field(alias="isIncome")
    created_at: datetime
    updated_at: datetime


class BudgetSummary(ApiModel):
    item_type: BudgetItemType = Field(alias="itemType")
    item_count: int = Field(alias="itemCount")
    planned_total: Decimal = Field(alias="plannedTotal")
    actual_total: Decimal = Field(alias="actualTotal")


def get_db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def check_token_rate_limit(db: Session, client_key: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=settings.auth_rate_limit_window_seconds)

    db.execute(delete(AuthRateLimitORM).where(AuthRateLimitORM.requested_at < cutoff))
    recent_requests = db.scalars(
        select(AuthRateLimitORM.requested_at)
        .where(AuthRateLimitORM.client_key == client_key)
        .where(AuthRateLimitORM.requested_at >= cutoff)
        .order_by(AuthRateLimitORM.requested_at)
    ).all()

    if len(recent_requests) >= settings.auth_rate_limit_max_requests:
        oldest_request = to_utc(recent_requests[0]) or now
        retry_at = oldest_request + timedelta(seconds=settings.auth_rate_limit_window_seconds)
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
    if user.failed_login_attempts >= settings.auth_lockout_threshold:
        user.lockout_until = now + timedelta(seconds=settings.auth_lockout_seconds)
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


def create_access_token(subject: str, role: str) -> Token:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire_at}
    if not settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return Token(access_token=encoded, expires_in_seconds=settings.access_token_expire_minutes * 60)


def require_auth_configured() -> None:
    if not settings.auth_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY environment variable must be set before using authenticated endpoints",
        )


def derive_item_type(
    payload: BudgetItemBase | BudgetItemUpdate,
    existing_type: BudgetItemType | None = None,
) -> BudgetItemType:
    if payload.item_type is not None:
        return payload.item_type

    flag_map = {
        BudgetItemType.CREDIT_CARD: payload.is_credit_card,
        BudgetItemType.LOAN: payload.is_loan,
        BudgetItemType.EXPENSE: payload.is_expense,
        BudgetItemType.INCOME: payload.is_income,
    }
    enabled_types = [item_type for item_type, enabled in flag_map.items() if enabled is True]
    if len(enabled_types) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide only one budget item type",
        )
    if len(enabled_types) == 1:
        return enabled_types[0]
    if existing_type is not None:
        return existing_type
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Provide itemType or exactly one of isCreditCard, isLoan, isExpense, or isIncome",
    )


def budget_item_to_read(item: BudgetItemORM) -> BudgetItemRead:
    item_type = BudgetItemType(item.item_type)
    return BudgetItemRead.model_validate(
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "itemType": item_type,
            "budgetedDate": item.scheduled_date,
            "actualDate": item.effective_date,
            "budgetedAmount": item.planned_amount,
            "actualAmount": item.actual_amount,
            "interestRate": item.interest_rate,
            "isApr": item.is_apr,
            "isCreditCard": item_type == BudgetItemType.CREDIT_CARD,
            "isLoan": item_type == BudgetItemType.LOAN,
            "isExpense": item_type == BudgetItemType.EXPENSE,
            "isIncome": item_type == BudgetItemType.INCOME,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
    )


def infer_legacy_item_type(category: str | None) -> str:
    normalized = (category or "").strip().lower()
    if "credit" in normalized or "card" in normalized:
        return BudgetItemType.CREDIT_CARD.value
    if "loan" in normalized or "mortgage" in normalized:
        return BudgetItemType.LOAN.value
    if "income" in normalized or "salary" in normalized or "pay" in normalized or "revenue" in normalized:
        return BudgetItemType.INCOME.value
    return BudgetItemType.EXPENSE.value


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "users" in inspector.get_table_names():
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "role" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'"))
            if "is_active" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            if "created_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                connection.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            if "failed_login_attempts" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
                )
            if "lockout_until" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN lockout_until DATETIME"))
            if "last_failed_login_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_failed_login_at DATETIME"))

        table_names = set(inspector.get_table_names())
        if "budget_entries" in table_names and "budget_items" in table_names:
            migrated_count = connection.execute(text("SELECT COUNT(*) FROM budget_items")).scalar_one()
            if migrated_count == 0:
                legacy_rows = connection.execute(
                    text(
                        """
                        SELECT
                            owner_id,
                            name,
                            description,
                            category,
                            budgetedDate,
                            actualDate,
                            budgetedAmount,
                            actualAmount
                        FROM budget_entries
                        """
                    )
                ).mappings()
                for row in legacy_rows:
                    connection.execute(
                        text(
                            """
                            INSERT INTO budget_items (
                                owner_id, name, description, category, item_type, scheduled_date,
                                effective_date, planned_amount, actual_amount, interest_rate, is_apr,
                                created_at, updated_at
                            ) VALUES (
                                :owner_id, :name, :description, :category, :item_type, :scheduled_date,
                                :effective_date, :planned_amount, :actual_amount, NULL, NULL,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            """
                        ),
                        {
                            "owner_id": row["owner_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "item_type": infer_legacy_item_type(row["category"]),
                            "scheduled_date": row["budgetedDate"],
                            "effective_date": row["actualDate"],
                            "planned_amount": row["budgetedAmount"],
                            "actual_amount": row["actualAmount"],
                        },
                    )

    ensure_bootstrap_admin()


def ensure_bootstrap_admin() -> None:
    username = settings.bootstrap_admin_username.strip() if settings.bootstrap_admin_username else None
    password = settings.bootstrap_admin_password
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
                username=username.strip(),
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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> UserORM:
    require_auth_configured()
    secret_key = settings.jwt_secret_key
    if not secret_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload: dict[str, Any] = jwt.decode(token, secret_key, algorithms=[settings.jwt_algorithm])
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Budget Tracker API",
    version=APP_VERSION,
    lifespan=lifespan,
    contact={"name": "Budget Tracker API"},
    root_path=settings.app_base_path,
    docs_url=f"{API_PREFIX}/docs",
    openapi_url=f"{API_PREFIX}/openapi.json",
    redoc_url=f"{API_PREFIX}/redoc",
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": app.title,
        "version": app.version,
        "docs": f"{API_PREFIX}/docs",
        "health": f"{API_PREFIX}/healthz",
        "ready": f"{API_PREFIX}/readyz",
        "auth": {
            "register": f"{API_PREFIX}/auth/register",
            "token": f"{API_PREFIX}/auth/token",
            "me": f"{API_PREFIX}/auth/me",
        },
        "budget_items": f"{API_PREFIX}/budget-items",
    }


@app.get(f"{API_PREFIX}/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get(f"{API_PREFIX}/readyz")
async def readyz(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    checks = {
        "database": "ok",
        "auth": "ok" if settings.auth_ready else "missing JWT_SECRET_KEY",
        "tls": "misconfigured" if settings.tls_misconfigured else ("enabled" if settings.tls_enabled else "disabled"),
    }

    try:
        db.execute(select(1))
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    is_ready = checks["database"] == "ok" and settings.auth_ready and not settings.tls_misconfigured
    if not is_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=checks)
    return {"status": "ready", "checks": checks}


@app.post(f"{API_PREFIX}/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
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


@app.post(f"{API_PREFIX}/auth/token", response_model=Token)
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


@app.get(f"{API_PREFIX}/auth/me", response_model=UserRead)
async def read_current_user(current_user: UserORM = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@app.get(f"{API_PREFIX}/budget-items", response_model=list[BudgetItemRead])
async def list_budget_items(
    item_type: BudgetItemType | None = None,
    category: str | None = None,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[BudgetItemRead]:
    query = (
        select(BudgetItemORM)
        .where(BudgetItemORM.owner_id == current_user.id)
        .order_by(BudgetItemORM.created_at.desc())
    )
    if item_type is not None:
        query = query.where(BudgetItemORM.item_type == item_type.value)
    if category:
        query = query.where(BudgetItemORM.category == category)
    items = db.scalars(query).all()
    return [budget_item_to_read(item) for item in items]


@app.get(f"{API_PREFIX}/budget-items/summary", response_model=list[BudgetSummary])
async def summarize_budget_items(
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[BudgetSummary]:
    rows = db.execute(
        select(
            BudgetItemORM.item_type,
            func.count(BudgetItemORM.id),
            func.coalesce(func.sum(BudgetItemORM.planned_amount), 0),
            func.coalesce(func.sum(BudgetItemORM.actual_amount), 0),
        )
        .where(BudgetItemORM.owner_id == current_user.id)
        .group_by(BudgetItemORM.item_type)
        .order_by(BudgetItemORM.item_type)
    ).all()
    return [
        BudgetSummary.model_validate(
            {
                "itemType": BudgetItemType(row[0]),
                "itemCount": row[1],
                "plannedTotal": row[2],
                "actualTotal": row[3],
            }
        )
        for row in rows
    ]


def get_budget_item_or_404(db: Session, item_id: int, owner_id: int) -> BudgetItemORM:
    item = db.scalar(select(BudgetItemORM).where(BudgetItemORM.id == item_id, BudgetItemORM.owner_id == owner_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget item not found")
    return item


@app.get(f"{API_PREFIX}/budget-items/{{item_id}}", response_model=BudgetItemRead)
async def read_budget_item(
    item_id: int,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BudgetItemRead:
    return budget_item_to_read(get_budget_item_or_404(db, item_id, current_user.id))


@app.post(f"{API_PREFIX}/budget-items", response_model=BudgetItemRead, status_code=status.HTTP_201_CREATED)
async def create_budget_item(
    payload: BudgetItemCreate,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BudgetItemRead:
    db_item = BudgetItemORM(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        item_type=derive_item_type(payload).value,
        scheduled_date=payload.scheduled_date,
        effective_date=payload.effective_date,
        planned_amount=payload.planned_amount,
        actual_amount=payload.actual_amount,
        interest_rate=payload.interest_rate,
        is_apr=payload.is_apr,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return budget_item_to_read(db_item)


@app.patch(f"{API_PREFIX}/budget-items/{{item_id}}", response_model=BudgetItemRead)
async def update_budget_item(
    item_id: int,
    payload: BudgetItemUpdate,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BudgetItemRead:
    db_item = get_budget_item_or_404(db, item_id, current_user.id)
    update_data = payload.model_dump(exclude_unset=True, by_alias=False)

    if "name" in update_data and update_data["name"] is not None:
        db_item.name = update_data["name"]
    if "description" in update_data:
        db_item.description = update_data["description"]
    if "category" in update_data:
        db_item.category = update_data["category"]
    if "scheduled_date" in update_data:
        db_item.scheduled_date = update_data["scheduled_date"]
    if "effective_date" in update_data:
        db_item.effective_date = update_data["effective_date"]
    if "planned_amount" in update_data and update_data["planned_amount"] is not None:
        db_item.planned_amount = update_data["planned_amount"]
    if "actual_amount" in update_data:
        db_item.actual_amount = update_data["actual_amount"]
    if "interest_rate" in update_data:
        db_item.interest_rate = update_data["interest_rate"]
    if "is_apr" in update_data:
        db_item.is_apr = update_data["is_apr"]

    type_fields = {"item_type", "is_credit_card", "is_loan", "is_expense", "is_income"}
    if type_fields.intersection(update_data):
        db_item.item_type = derive_item_type(payload, existing_type=BudgetItemType(db_item.item_type)).value

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return budget_item_to_read(db_item)


@app.delete(f"{API_PREFIX}/budget-items/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_item(
    item_id: int,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Response:
    db_item = get_budget_item_or_404(db, item_id, current_user.id)
    db.delete(db_item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def run() -> None:
    if settings.tls_misconfigured:
        raise RuntimeError("TLS_CERT_FILE and TLS_KEY_FILE must both be set to enable TLS")
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        ssl_certfile=settings.tls_cert_file,
        ssl_keyfile=settings.tls_key_file,
        ssl_ca_certs=settings.tls_ca_file,
    )


if __name__ == "__main__":
    run()
