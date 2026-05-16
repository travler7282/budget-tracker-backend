from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from budget_tracker import config

router = APIRouter()


@router.get("/")
async def root() -> dict[str, Any]:
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
        },
        "budget_items": f"{config.API_PREFIX}/budget-items",
        "cash_flow": f"{config.API_PREFIX}/cash-flow/calendar",
    }
