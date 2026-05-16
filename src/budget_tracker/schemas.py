from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from budget_tracker.models import BudgetItemType, UserRole


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


def strip_string(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


class UserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: Any) -> Any:
        return strip_string(value)


class UserRead(ApiModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(ApiModel):
    username: str | None = Field(default=None, min_length=3, max_length=150)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: Any) -> Any:
        return strip_string(value)


class Token(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class BudgetItemBase(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    item_type: BudgetItemType | None = Field(default=None, alias="itemType")
    scheduled_date: date | None = Field(default=None, alias="budgetedDate")
    effective_date: date | None = Field(default=None, alias="actualDate")
    planned_amount: Decimal = Field(alias="budgetedAmount")
    actual_amount: Decimal | None = Field(default=None, alias="actualAmount")
    interest_rate: Decimal | None = Field(default=None, alias="interestRate")
    is_apr: bool | None = Field(default=None, alias="isApr")
    is_credit_card: bool | None = Field(default=None, alias="isCreditCard")
    is_loan: bool | None = Field(default=None, alias="isLoan")
    is_expense: bool | None = Field(default=None, alias="isExpense")
    is_income: bool | None = Field(default=None, alias="isIncome")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return strip_string(value)


class BudgetItemCreate(BudgetItemBase):
    pass


class BudgetItemUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    item_type: BudgetItemType | None = Field(default=None, alias="itemType")
    scheduled_date: date | None = Field(default=None, alias="budgetedDate")
    effective_date: date | None = Field(default=None, alias="actualDate")
    planned_amount: Decimal | None = Field(default=None, alias="budgetedAmount")
    actual_amount: Decimal | None = Field(default=None, alias="actualAmount")
    interest_rate: Decimal | None = Field(default=None, alias="interestRate")
    is_apr: bool | None = Field(default=None, alias="isApr")
    is_credit_card: bool | None = Field(default=None, alias="isCreditCard")
    is_loan: bool | None = Field(default=None, alias="isLoan")
    is_expense: bool | None = Field(default=None, alias="isExpense")
    is_income: bool | None = Field(default=None, alias="isIncome")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return strip_string(value)


class BudgetItemRead(ApiModel):
    id: int
    name: str
    description: str | None
    category: str | None
    item_type: BudgetItemType = Field(alias="itemType")
    scheduled_date: date | None = Field(alias="budgetedDate")
    effective_date: date | None = Field(alias="actualDate")
    planned_amount: Decimal = Field(alias="budgetedAmount")
    actual_amount: Decimal | None = Field(alias="actualAmount")
    interest_rate: Decimal | None = Field(alias="interestRate")
    is_apr: bool | None = Field(alias="isApr")
    is_credit_card: bool = Field(alias="isCreditCard")
    is_loan: bool = Field(alias="isLoan")
    is_expense: bool = Field(alias="isExpense")
    is_income: bool = Field(alias="isIncome")
    created_at: datetime
    updated_at: datetime


class BudgetSummary(ApiModel):
    item_type: BudgetItemType = Field(alias="itemType")
    item_count: int = Field(alias="itemCount")
    planned_total: Decimal = Field(alias="plannedTotal")
    actual_total: Decimal = Field(alias="actualTotal")


class CashFlowItem(ApiModel):
    id: int
    name: str
    category: str | None
    item_type: BudgetItemType = Field(alias="itemType")
    planned_date: date | None = Field(alias="plannedDate")
    actual_date: date | None = Field(alias="actualDate")
    planned_amount: Decimal = Field(alias="plannedAmount")
    actual_amount: Decimal | None = Field(alias="actualAmount")


class CashFlowDay(ApiModel):
    date: date
    planned_income: Decimal = Field(alias="plannedIncome")
    planned_outflow: Decimal = Field(alias="plannedOutflow")
    planned_net: Decimal = Field(alias="plannedNet")
    actual_income: Decimal = Field(alias="actualIncome")
    actual_outflow: Decimal = Field(alias="actualOutflow")
    actual_net: Decimal = Field(alias="actualNet")
    planned_balance: Decimal = Field(alias="plannedBalance")
    actual_balance: Decimal = Field(alias="actualBalance")
    items: list[CashFlowItem]


class CashFlowCalendar(ApiModel):
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    starting_balance: Decimal = Field(alias="startingBalance")
    days: list[CashFlowDay]
