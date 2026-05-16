from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import get_db_session
from budget_tracker.models import UserORM
from budget_tracker.schemas import CashFlowCalendar
from budget_tracker.security import get_current_user
from budget_tracker.services.cash_flow import build_cash_flow_calendar

router = APIRouter(prefix=f"{config.API_PREFIX}/cash-flow", tags=["cash-flow"])


@router.get("/calendar", response_model=CashFlowCalendar)
async def read_cash_flow_calendar(
    start_date: date = Query(alias="startDate"),
    end_date: date = Query(alias="endDate"),
    starting_balance: Decimal = Query(default=Decimal("0"), alias="startingBalance"),
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CashFlowCalendar:
    return build_cash_flow_calendar(
        db=db,
        owner_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        starting_balance=starting_balance,
    )
