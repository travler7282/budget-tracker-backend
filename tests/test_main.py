from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"


def load_main_module(monkeypatch, tmp_path):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    if os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS") is None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
    if os.getenv("AUTH_RATE_LIMIT_MAX_REQUESTS") is None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "10")
    if os.getenv("AUTH_LOCKOUT_THRESHOLD") is None:
        monkeypatch.setenv("AUTH_LOCKOUT_THRESHOLD", "5")
    if os.getenv("AUTH_LOCKOUT_SECONDS") is None:
        monkeypatch.setenv("AUTH_LOCKOUT_SECONDS", "300")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "admin-password")
    monkeypatch.delenv("APP_BASE_PATH", raising=False)

    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    for module_name in list(sys.modules):
        if module_name == "main" or module_name.startswith("budget_tracker"):
            del sys.modules[module_name]

    module = importlib.import_module("main")
    return module


def override_settings(monkeypatch, main, **overrides):
    settings_data = dict(main.settings.__dict__)
    settings_data.update(overrides)
    new_settings = main.Settings(**settings_data)
    monkeypatch.setattr(main.config, "settings", new_settings)
    monkeypatch.setattr(main, "settings", new_settings)


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def create_user(client: TestClient, admin_headers: dict[str, str], username: str, password: str) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        headers=admin_headers,
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 201


def test_health_and_readiness(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        health_response = client.get("/api/v1/healthz")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

        ready_response = client.get("/api/v1/readyz")
        assert ready_response.status_code == 200
        assert ready_response.json()["status"] == "ready"

    main.engine.dispose()


def test_budget_items_require_authentication(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        response = client.get("/api/v1/budget-items")
        assert response.status_code == 401

        user_response = client.get("/api/v1/auth/me")
        assert user_response.status_code == 401

    main.engine.dispose()


def test_register_requires_admin_authentication(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        anonymous_response = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "super-secret"},
        )
        assert anonymous_response.status_code == 401

        admin_headers = login_headers(client, "admin", "admin-password")
        create_user(client, admin_headers, "bob", "super-secret")
        user_headers = login_headers(client, "bob", "super-secret")

        non_admin_response = client.post(
            "/api/v1/auth/register",
            headers=user_headers,
            json={"username": "charlie", "password": "super-secret"},
        )
        assert non_admin_response.status_code == 403

    main.engine.dispose()


def test_register_writes_audit_log(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        admin_headers = login_headers(client, "admin", "admin-password")
        create_user(client, admin_headers, "dana", "super-secret")

    with main.SessionLocal() as session:
        audit_count = session.query(main.AuditLogORM).filter(main.AuditLogORM.action == "user.create").count()
        assert audit_count == 1

    main.engine.dispose()


def test_register_trims_and_rejects_blank_usernames(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        admin_headers = login_headers(client, "admin", "admin-password")

        blank_response = client.post(
            "/api/v1/auth/register",
            headers=admin_headers,
            json={"username": "   ", "password": "super-secret"},
        )
        assert blank_response.status_code == 422

        create_response = client.post(
            "/api/v1/auth/register",
            headers=admin_headers,
            json={"username": "  trimmed-user  ", "password": "super-secret"},
        )
        assert create_response.status_code == 201
        assert create_response.json()["username"] == "trimmed-user"

    main.engine.dispose()


def test_login_lockout_after_failed_attempts(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_LOCKOUT_THRESHOLD", "2")
    monkeypatch.setenv("AUTH_LOCKOUT_SECONDS", "120")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "20")
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        first_fail = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "wrong-password"},
        )
        assert first_fail.status_code == 401

        second_fail = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "wrong-password"},
        )
        assert second_fail.status_code == 401

        locked_response = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin-password"},
        )
        assert locked_response.status_code == 423

    main.engine.dispose()


def test_login_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("AUTH_LOCKOUT_THRESHOLD", "10")
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        first = client.post(
            "/api/v1/auth/token",
            data={"username": "missing-user", "password": "wrong-password"},
        )
        assert first.status_code == 401

        second = client.post(
            "/api/v1/auth/token",
            data={"username": "missing-user", "password": "wrong-password"},
        )
        assert second.status_code == 401

        third = client.post(
            "/api/v1/auth/token",
            data={"username": "missing-user", "password": "wrong-password"},
        )
        assert third.status_code == 429

    main.engine.dispose()


def test_login_rate_limit_is_written_to_database(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "20")
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "missing-user", "password": "wrong-password"},
        )
        assert response.status_code == 401

    with main.SessionLocal() as session:
        stored_attempts = session.query(main.AuthRateLimitORM).count()
        assert stored_attempts == 1

    main.engine.dispose()


def test_budget_item_crud_and_summary(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        headers = login_headers(client, "admin", "admin-password")

        create_response = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={
                "name": "Visa",
                "category": "Debt",
                "itemType": "credit_card",
                "budgetedAmount": "125.50",
                "actualAmount": "100.00",
                "interestRate": "19.9900",
                "isApr": True,
            },
        )
        assert create_response.status_code == 201
        item = create_response.json()
        assert item["itemType"] == "credit_card"
        assert item["isCreditCard"] is True

        list_response = client.get("/api/v1/budget-items", headers=headers)
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        update_response = client.patch(
            f"/api/v1/budget-items/{item['id']}",
            headers=headers,
            json={"actualAmount": "95.00", "isCreditCard": True},
        )
        assert update_response.status_code == 200
        assert update_response.json()["actualAmount"] == "95.00"

        summary_response = client.get("/api/v1/budget-items/summary", headers=headers)
        assert summary_response.status_code == 200
        assert summary_response.json()[0]["itemType"] == "credit_card"

        delete_response = client.delete(f"/api/v1/budget-items/{item['id']}", headers=headers)
        assert delete_response.status_code == 204

    main.engine.dispose()


def test_budget_item_names_are_trimmed_and_blank_names_are_rejected(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        headers = login_headers(client, "admin", "admin-password")

        blank_create = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={"name": "   ", "itemType": "expense", "budgetedAmount": "20.00"},
        )
        assert blank_create.status_code == 422

        create_response = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={"name": "  Rent  ", "itemType": "expense", "budgetedAmount": "1200.00"},
        )
        assert create_response.status_code == 201
        item = create_response.json()
        assert item["name"] == "Rent"

        blank_update = client.patch(
            f"/api/v1/budget-items/{item['id']}",
            headers=headers,
            json={"name": "   "},
        )
        assert blank_update.status_code == 422

        update_response = client.patch(
            f"/api/v1/budget-items/{item['id']}",
            headers=headers,
            json={"name": "  Rent payment  "},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Rent payment"

    main.engine.dispose()


def test_cash_flow_calendar_summarizes_planned_and_actual_dates(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        headers = login_headers(client, "admin", "admin-password")

        income_response = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={
                "name": "Paycheck",
                "itemType": "income",
                "budgetedDate": "2026-05-01",
                "actualDate": "2026-05-01",
                "budgetedAmount": "1000.00",
                "actualAmount": "1100.00",
            },
        )
        assert income_response.status_code == 201

        expense_response = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={
                "name": "Rent",
                "itemType": "expense",
                "budgetedDate": "2026-05-02",
                "actualDate": "2026-05-03",
                "budgetedAmount": "1000.00",
                "actualAmount": "950.00",
            },
        )
        assert expense_response.status_code == 201

        calendar_response = client.get(
            "/api/v1/cash-flow/calendar",
            headers=headers,
            params={
                "startDate": "2026-05-01",
                "endDate": "2026-05-03",
                "startingBalance": "100.00",
            },
        )
        assert calendar_response.status_code == 200
        days = calendar_response.json()["days"]

        assert days[0]["plannedIncome"] == "1000.00"
        assert days[0]["actualIncome"] == "1100.00"
        assert days[0]["plannedBalance"] == "1100.00"
        assert days[0]["actualBalance"] == "1200.00"

        assert days[1]["plannedOutflow"] == "1000.00"
        assert days[1]["actualOutflow"] == "0"
        assert days[1]["plannedBalance"] == "100.00"
        assert days[1]["actualBalance"] == "1200.00"

        assert days[2]["plannedOutflow"] == "0"
        assert days[2]["actualOutflow"] == "950.00"
        assert days[2]["plannedBalance"] == "100.00"
        assert days[2]["actualBalance"] == "250.00"
        assert {item["name"] for item in days[2]["items"]} == {"Rent"}

    main.engine.dispose()


def test_item_type_flags_require_single_budget_type(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        headers = login_headers(client, "admin", "admin-password")
        invalid_response = client.post(
            "/api/v1/budget-items",
            headers=headers,
            json={
                "name": "Ambiguous",
                "budgetedAmount": "20.00",
                "isExpense": True,
                "isIncome": True,
            },
        )
        assert invalid_response.status_code == 422

    main.engine.dispose()


def test_helper_branches_for_bool_paths_and_legacy_inference(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    assert main.strtobool(None, default=True) is True
    assert main.strtobool("OFF") is False
    assert main.normalize_base_path(None) == ""
    assert main.normalize_base_path("/") == ""
    assert main.normalize_base_path(" /budget-tracker/ ") == "/budget-tracker"

    assert main.infer_legacy_item_type("credit card payment") == main.BudgetItemType.CREDIT_CARD.value
    assert main.infer_legacy_item_type("home loan") == main.BudgetItemType.LOAN.value
    assert main.infer_legacy_item_type("mortgage") == main.BudgetItemType.MORTGAGE.value
    assert main.infer_legacy_item_type("student loan") == main.BudgetItemType.STUDENT_LOAN.value
    assert main.infer_legacy_item_type("salary") == main.BudgetItemType.INCOME.value
    assert main.infer_legacy_item_type("misc") == main.BudgetItemType.EXPENSE.value

    main.engine.dispose()


def test_require_auth_configured_and_create_access_token_fail_without_secret(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)
    override_settings(monkeypatch, main, jwt_secret_key=None)

    with pytest.raises(main.HTTPException) as require_exc:
        main.require_auth_configured()
    assert require_exc.value.status_code == 503

    with pytest.raises(main.HTTPException) as token_exc:
        main.create_access_token("user", "user")
    assert token_exc.value.status_code == 503

    main.engine.dispose()


def test_to_utc_and_lockout_guard(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    assert main.to_utc(None) is None

    naive = datetime.now(timezone.utc).replace(tzinfo=None)
    assert main.to_utc(naive).tzinfo == timezone.utc

    future_lock = datetime.now(timezone.utc) + timedelta(seconds=30)
    user = main.UserORM(
        username="locked-user",
        hashed_password="x",
        role=main.UserRole.USER.value,
        is_active=True,
        lockout_until=future_lock,
    )
    with pytest.raises(main.HTTPException) as lock_exc:
        main.ensure_user_not_locked(user)
    assert lock_exc.value.status_code == 423

    user.lockout_until = datetime.now(timezone.utc) - timedelta(seconds=30)
    main.ensure_user_not_locked(user)

    main.engine.dispose()


def test_bootstrap_admin_requires_complete_configuration(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)
    override_settings(monkeypatch, main, bootstrap_admin_username="admin", bootstrap_admin_password=None)

    with pytest.raises(RuntimeError):
        main.ensure_bootstrap_admin()

    main.engine.dispose()


def test_bootstrap_admin_updates_existing_password(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        first_login = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin-password"},
        )
        assert first_login.status_code == 200

    override_settings(
        monkeypatch,
        main,
        bootstrap_admin_username="admin",
        bootstrap_admin_password="new-admin-password",
    )
    main.ensure_bootstrap_admin()

    with TestClient(main.app) as client:
        old_password_login = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin-password"},
        )
        assert old_password_login.status_code == 401

        new_password_login = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "new-admin-password"},
        )
        assert new_password_login.status_code == 200

    main.engine.dispose()


def test_readyz_unready_when_auth_secret_missing(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)
    override_settings(monkeypatch, main, jwt_secret_key=None)

    with TestClient(main.app) as client:
        ready_response = client.get("/api/v1/readyz")
        assert ready_response.status_code == 503
        assert "missing JWT_SECRET_KEY" in ready_response.text

    main.engine.dispose()


def test_login_inactive_user_forbidden(monkeypatch, tmp_path):
    main = load_main_module(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        with main.SessionLocal() as session:
            admin = session.query(main.UserORM).filter(main.UserORM.username == "admin").one()
            admin.is_active = False
            session.add(admin)
            session.commit()

        response = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin-password"},
        )
        assert response.status_code == 403

    main.engine.dispose()
