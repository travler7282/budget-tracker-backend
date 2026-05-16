from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from budget_tracker import config
from budget_tracker.api.routers import auth, budget_items, cash_flow, health, root
from budget_tracker.services.database import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Budget Tracker API",
        version=config.APP_VERSION,
        lifespan=lifespan,
        contact={"name": "Budget Tracker API"},
        root_path=config.settings.app_base_path,
        docs_url=f"{config.API_PREFIX}/docs",
        openapi_url=f"{config.API_PREFIX}/openapi.json",
        redoc_url=f"{config.API_PREFIX}/redoc",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(root.router)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(budget_items.router)
    app.include_router(cash_flow.router)
    return app
