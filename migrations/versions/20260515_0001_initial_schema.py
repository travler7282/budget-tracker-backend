"""Initial schema.

Revision ID: 20260515_0001
Revises:
Create Date: 2026-05-15 00:00:00

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260515_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lockout_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("details", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_id"), "audit_logs", ["id"], unique=False)

    op.create_table(
        "auth_rate_limits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_key", sa.String(length=255), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_rate_limits_client_key"), "auth_rate_limits", ["client_key"], unique=False)
    op.create_index(op.f("ix_auth_rate_limits_id"), "auth_rate_limits", ["id"], unique=False)
    op.create_index(op.f("ix_auth_rate_limits_requested_at"), "auth_rate_limits", ["requested_at"], unique=False)

    op.create_table(
        "budget_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("item_type", sa.String(length=50), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("planned_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("interest_rate", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("is_apr", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budget_items_category"), "budget_items", ["category"], unique=False)
    op.create_index(op.f("ix_budget_items_id"), "budget_items", ["id"], unique=False)
    op.create_index(op.f("ix_budget_items_item_type"), "budget_items", ["item_type"], unique=False)
    op.create_index(op.f("ix_budget_items_owner_id"), "budget_items", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_budget_items_owner_id"), table_name="budget_items")
    op.drop_index(op.f("ix_budget_items_item_type"), table_name="budget_items")
    op.drop_index(op.f("ix_budget_items_id"), table_name="budget_items")
    op.drop_index(op.f("ix_budget_items_category"), table_name="budget_items")
    op.drop_table("budget_items")

    op.drop_index(op.f("ix_auth_rate_limits_requested_at"), table_name="auth_rate_limits")
    op.drop_index(op.f("ix_auth_rate_limits_id"), table_name="auth_rate_limits")
    op.drop_index(op.f("ix_auth_rate_limits_client_key"), table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")

    op.drop_index(op.f("ix_audit_logs_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
