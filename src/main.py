from __future__ import annotations

import uvicorn
from fastapi import HTTPException as FastAPIHTTPException
from fastapi import status as fastapi_status

from budget_tracker import app as app_module
from budget_tracker import config, database, models, schemas, security
from budget_tracker.services import auth as auth_service
from budget_tracker.services import budget_items as budget_item_service
from budget_tracker.services import cash_flow as cash_flow_service
from budget_tracker.services import database as database_service

HTTPException = FastAPIHTTPException
status = fastapi_status

API_PREFIX = config.API_PREFIX
APP_VERSION = config.APP_VERSION
BASE_DIR = config.BASE_DIR
DEFAULT_SQLITE_PATH = config.DEFAULT_SQLITE_PATH
Settings = config.Settings
get_settings = config.get_settings
normalize_base_path = config.normalize_base_path
strtobool = config.strtobool
settings = config.settings

Base = database.Base
SessionLocal = database.SessionLocal
engine = database.engine
get_db_session = database.get_db_session

AuditLogORM = models.AuditLogORM
AuthRateLimitORM = models.AuthRateLimitORM
BudgetItemORM = models.BudgetItemORM
BudgetItemType = models.BudgetItemType
UserORM = models.UserORM
UserRole = models.UserRole

ApiModel = schemas.ApiModel
BudgetItemBase = schemas.BudgetItemBase
BudgetItemCreate = schemas.BudgetItemCreate
BudgetItemRead = schemas.BudgetItemRead
BudgetItemUpdate = schemas.BudgetItemUpdate
BudgetSummary = schemas.BudgetSummary
CashFlowCalendar = schemas.CashFlowCalendar
CashFlowDay = schemas.CashFlowDay
CashFlowItem = schemas.CashFlowItem
Token = schemas.Token
UserCreate = schemas.UserCreate
UserRead = schemas.UserRead
strip_string = schemas.strip_string

create_access_token = security.create_access_token
get_current_admin = security.get_current_admin
get_current_user = security.get_current_user
get_password_hash = security.get_password_hash
oauth2_scheme = security.oauth2_scheme
pwd_context = security.pwd_context
require_auth_configured = security.require_auth_configured
to_utc = security.to_utc
verify_password = security.verify_password

check_token_rate_limit = auth_service.check_token_rate_limit
ensure_bootstrap_admin = auth_service.ensure_bootstrap_admin
ensure_user_not_locked = auth_service.ensure_user_not_locked
register_failed_login_attempt = auth_service.register_failed_login_attempt
reset_login_backoff = auth_service.reset_login_backoff

budget_item_to_read = budget_item_service.budget_item_to_read
derive_item_type = budget_item_service.derive_item_type
get_budget_item_or_404 = budget_item_service.get_budget_item_or_404
infer_legacy_item_type = budget_item_service.infer_legacy_item_type

build_cash_flow_calendar = cash_flow_service.build_cash_flow_calendar
signed_amount = cash_flow_service.signed_amount

initialize_database = database_service.initialize_database

create_app = app_module.create_app
lifespan = app_module.lifespan
app = create_app()


def run() -> None:
    if config.settings.tls_misconfigured:
        raise RuntimeError("TLS_CERT_FILE and TLS_KEY_FILE must both be set to enable TLS")
    uvicorn.run(
        app,
        host=config.settings.host,
        port=config.settings.port,
        reload=config.settings.reload,
        ssl_certfile=config.settings.tls_cert_file,
        ssl_keyfile=config.settings.tls_key_file,
        ssl_ca_certs=config.settings.tls_ca_file,
    )


if __name__ == "__main__":
    run()
