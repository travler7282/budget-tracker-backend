from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
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
    cors_allowed_origins: list[str]

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
    cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "https://www.travler7282.com,https://api.travler7282.com")
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    
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
        cors_allowed_origins=cors_origins,
    )


settings = get_settings()
