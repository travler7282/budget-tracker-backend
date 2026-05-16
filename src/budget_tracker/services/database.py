from __future__ import annotations

from sqlalchemy import inspect, select, text

from budget_tracker.database import Base, SessionLocal, engine
from budget_tracker.models import UserORM
from budget_tracker.services.auth import ensure_bootstrap_admin
from budget_tracker.services.budget_items import infer_legacy_item_type


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "users" in inspector.get_table_names():
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "role" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'"))
            if "is_active" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            if "created_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                connection.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            if "failed_login_attempts" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
                )
            if "lockout_until" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN lockout_until DATETIME"))
            if "last_failed_login_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_failed_login_at DATETIME"))

        table_names = set(inspector.get_table_names())
        if "budget_entries" in table_names and "budget_items" in table_names:
            migrated_count = connection.execute(text("SELECT COUNT(*) FROM budget_items")).scalar_one()
            if migrated_count == 0:
                legacy_rows = connection.execute(
                    text(
                        """
                        SELECT
                            owner_id,
                            name,
                            description,
                            category,
                            budgetedDate,
                            actualDate,
                            budgetedAmount,
                            actualAmount
                        FROM budget_entries
                        """
                    )
                ).mappings()
                for row in legacy_rows:
                    connection.execute(
                        text(
                            """
                            INSERT INTO budget_items (
                                owner_id, name, description, category, item_type, scheduled_date,
                                effective_date, planned_amount, actual_amount, interest_rate, is_apr,
                                created_at, updated_at
                            ) VALUES (
                                :owner_id, :name, :description, :category, :item_type, :scheduled_date,
                                :effective_date, :planned_amount, :actual_amount, NULL, NULL,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            """
                        ),
                        {
                            "owner_id": row["owner_id"],
                            "name": row["name"],
                            "description": row["description"],
                            "category": row["category"],
                            "item_type": infer_legacy_item_type(row["category"]),
                            "scheduled_date": row["budgetedDate"],
                            "effective_date": row["actualDate"],
                            "planned_amount": row["budgetedAmount"],
                            "actual_amount": row["actualAmount"],
                        },
                    )

    ensure_bootstrap_admin()


def user_exists(username: str) -> bool:
    with SessionLocal() as session:
        return session.scalar(select(UserORM).where(UserORM.username == username)) is not None
