from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from budget_tracker.models import BudgetItemORM, BudgetItemType
from budget_tracker.schemas import CashFlowCalendar, CashFlowDay, CashFlowItem

INFLOW_TYPES = {BudgetItemType.INCOME}


def signed_amount(item_type: BudgetItemType, amount: Decimal) -> Decimal:
    if item_type in INFLOW_TYPES:
        return amount
    return -amount


def empty_day(day: date) -> dict[str, object]:
    return {
        "date": day,
        "plannedIncome": Decimal("0"),
        "plannedOutflow": Decimal("0"),
        "plannedNet": Decimal("0"),
        "actualIncome": Decimal("0"),
        "actualOutflow": Decimal("0"),
        "actualNet": Decimal("0"),
        "plannedBalance": Decimal("0"),
        "actualBalance": Decimal("0"),
        "items": [],
    }


def add_amount(day_data: dict[str, object], prefix: str, item_type: BudgetItemType, amount: Decimal) -> None:
    signed = signed_amount(item_type, amount)
    income_key = f"{prefix}Income"
    outflow_key = f"{prefix}Outflow"
    net_key = f"{prefix}Net"

    if signed >= 0:
        day_data[income_key] = day_data[income_key] + signed  # type: ignore[operator]
    else:
        day_data[outflow_key] = day_data[outflow_key] + abs(signed)  # type: ignore[operator]
    day_data[net_key] = day_data[net_key] + signed  # type: ignore[operator]


def date_range(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def build_cash_flow_calendar(
    db: Session,
    owner_id: int,
    start_date: date,
    end_date: date,
    starting_balance: Decimal,
) -> CashFlowCalendar:
    if end_date < start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="endDate must be after startDate")

    days = {day: empty_day(day) for day in date_range(start_date, end_date)}
    items = db.scalars(
        select(BudgetItemORM)
        .where(BudgetItemORM.owner_id == owner_id)
        .where(
            or_(
                BudgetItemORM.scheduled_date.between(start_date, end_date),
                BudgetItemORM.effective_date.between(start_date, end_date),
            )
        )
        .order_by(BudgetItemORM.scheduled_date, BudgetItemORM.effective_date, BudgetItemORM.name)
    ).all()

    items_by_day: dict[date, dict[int, CashFlowItem]] = defaultdict(dict)
    for item in items:
        item_type = BudgetItemType(item.item_type)
        cash_flow_item = CashFlowItem.model_validate(
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "itemType": item_type,
                "plannedDate": item.scheduled_date,
                "actualDate": item.effective_date,
                "plannedAmount": item.planned_amount,
                "actualAmount": item.actual_amount,
            }
        )

        if item.scheduled_date in days:
            add_amount(days[item.scheduled_date], "planned", item_type, item.planned_amount)
            items_by_day[item.scheduled_date][item.id] = cash_flow_item

        if item.effective_date in days:
            actual_amount = item.actual_amount if item.actual_amount is not None else item.planned_amount
            add_amount(days[item.effective_date], "actual", item_type, actual_amount)
            items_by_day[item.effective_date][item.id] = cash_flow_item

    planned_balance = starting_balance
    actual_balance = starting_balance
    response_days: list[CashFlowDay] = []
    for day in sorted(days):
        day_data = days[day]
        planned_balance += day_data["plannedNet"]  # type: ignore[operator]
        actual_balance += day_data["actualNet"]  # type: ignore[operator]
        day_data["plannedBalance"] = planned_balance
        day_data["actualBalance"] = actual_balance
        day_data["items"] = list(items_by_day[day].values())
        response_days.append(CashFlowDay.model_validate(day_data))

    return CashFlowCalendar.model_validate(
        {
            "startDate": start_date,
            "endDate": end_date,
            "startingBalance": starting_balance,
            "days": response_days,
        }
    )
