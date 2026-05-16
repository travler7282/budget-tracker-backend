from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from budget_tracker import config
from budget_tracker.database import get_db_session
from budget_tracker.models import BudgetItemORM, BudgetItemType, UserORM
from budget_tracker.schemas import BudgetItemCreate, BudgetItemRead, BudgetItemUpdate, BudgetSummary
from budget_tracker.security import get_current_user
from budget_tracker.services.budget_items import budget_item_to_read, derive_item_type, get_budget_item_or_404

router = APIRouter(prefix=f"{config.API_PREFIX}/budget-items", tags=["budget-items"])


@router.get("", response_model=list[BudgetItemRead])
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


@router.get("/summary", response_model=list[BudgetSummary])
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


@router.get("/{item_id}", response_model=BudgetItemRead)
async def read_budget_item(
    item_id: int,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BudgetItemRead:
    return budget_item_to_read(get_budget_item_or_404(db, item_id, current_user.id))


@router.post("", response_model=BudgetItemRead, status_code=status.HTTP_201_CREATED)
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


@router.patch("/{item_id}", response_model=BudgetItemRead)
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


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_item(
    item_id: int,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Response:
    db_item = get_budget_item_or_404(db, item_id, current_user.id)
    db.delete(db_item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
