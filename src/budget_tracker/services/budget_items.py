from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from budget_tracker.models import BudgetItemORM, BudgetItemType
from budget_tracker.schemas import BudgetItemBase, BudgetItemRead, BudgetItemUpdate


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
    if "student" in normalized:
        return BudgetItemType.STUDENT_LOAN.value
    if "mortgage" in normalized:
        return BudgetItemType.MORTGAGE.value
    if "loan" in normalized or "mortgage" in normalized:
        return BudgetItemType.LOAN.value
    if "income" in normalized or "salary" in normalized or "pay" in normalized or "revenue" in normalized:
        return BudgetItemType.INCOME.value
    return BudgetItemType.EXPENSE.value


def get_budget_item_or_404(db: Session, item_id: int, owner_id: int) -> BudgetItemORM:
    item = db.scalar(select(BudgetItemORM).where(BudgetItemORM.id == item_id, BudgetItemORM.owner_id == owner_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget item not found")
    return item
