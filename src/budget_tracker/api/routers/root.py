from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from budget_tracker import config
from budget_tracker.models import UserORM
from budget_tracker.security import get_current_user

router = APIRouter()


@router.get("/")
async def root(current_user: UserORM = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "service": "Budget Tracker API",
        "version": config.APP_VERSION,
        "docs": f"{config.API_PREFIX}/docs",
        "health": f"{config.API_PREFIX}/healthz",
        "ready": f"{config.API_PREFIX}/readyz",
        "auth": {
            "register": f"{config.API_PREFIX}/auth/register",
            "token": f"{config.API_PREFIX}/auth/token",
            "me": f"{config.API_PREFIX}/auth/me",
            "update_user": f"{config.API_PREFIX}/auth/users/{{user_id}}",
            "delete_user": f"{config.API_PREFIX}/auth/users/{{user_id}}",
        },
        "budget_items": f"{config.API_PREFIX}/budget-items",
        "cash_flow": f"{config.API_PREFIX}/cash-flow/calendar",
        "current_user": current_user.username,
    }
