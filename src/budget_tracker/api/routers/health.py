from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import get_db_session

router = APIRouter(prefix=config.API_PREFIX, tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/readyz")
async def readyz(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    checks = {
        "database": "ok",
        "auth": "ok" if config.settings.auth_ready else "missing JWT_SECRET_KEY",
        "tls": "misconfigured"
        if config.settings.tls_misconfigured
        else ("enabled" if config.settings.tls_enabled else "disabled"),
    }

    try:
        db.execute(select(1))
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    is_ready = checks["database"] == "ok" and config.settings.auth_ready and not config.settings.tls_misconfigured
    if not is_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=checks)
    return {"status": "ready", "checks": checks}
