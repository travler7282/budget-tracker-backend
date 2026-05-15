# Budget Tracker Backend

FastAPI backend for managing budget items with JWT authentication, SQLAlchemy-backed persistence, health checks, and Kubernetes-ready deployment settings.

## Features

- Auth endpoints for registration, token issuance, and current-user lookup.
- Database-backed token endpoint rate limiting to reduce brute-force attempts across app processes.
- Login lockout/backoff after repeated failed password attempts.
- Audit logging for admin-driven user creation.
- CRUD endpoints for budget items at `/api/v1/budget-items`.
- Budget item typing via `itemType` with compatibility flags such as `isLoan`, `isExpense`, and `isCreditCard`.
- Health and readiness endpoints at `/api/v1/healthz` and `/api/v1/readyz`.
- Alembic migrations for schema changes.
- Environment-driven configuration for secrets, database path, ingress base path, and optional TLS.

## Environment Variables

Set these before running the API:

- `JWT_SECRET_KEY`: required for authenticated endpoints.
- `AUTH_RATE_LIMIT_WINDOW_SECONDS`: optional token endpoint rate-limit window in seconds, defaults to `60`.
- `AUTH_RATE_LIMIT_MAX_REQUESTS`: optional max token requests per client per window, defaults to `10`.
- `AUTH_LOCKOUT_THRESHOLD`: optional failed login attempts before lockout, defaults to `5`.
- `AUTH_LOCKOUT_SECONDS`: optional lockout/backoff duration in seconds, defaults to `300`.
- `BOOTSTRAP_ADMIN_USERNAME`: optional username for creating or updating the first admin account at startup.
- `BOOTSTRAP_ADMIN_PASSWORD`: optional password for the bootstrap admin account. Set this from your shell or secret store, not the repo.
- `DATABASE_URL`: optional, defaults to a local SQLite database file.
- `APP_HOST`: optional, defaults to `0.0.0.0`.
- `APP_PORT`: optional, defaults to `8000`.
- `APP_RELOAD`: optional, set to `true` for local reload.
- `APP_BASE_PATH`: optional ingress prefix such as `/budget-tracker`.
- `TLS_CERT_FILE`: optional path to the TLS certificate for direct HTTPS.
- `TLS_KEY_FILE`: optional path to the TLS key for direct HTTPS.
- `TLS_CA_FILE`: optional CA bundle path when needed.

## Run Locally

### Linux/macOS

Create and activate a local virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the app and test tooling:

```bash
pip install -e .[test]
```

Run the API with uvicorn:

```bash
export JWT_SECRET_KEY="set-this-from-your-shell-or-secret-store"
export BOOTSTRAP_ADMIN_USERNAME="admin"
export BOOTSTRAP_ADMIN_PASSWORD="set-this-from-your-shell-or-secret-store"
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --proxy-headers
```

Or run the entrypoint directly:

```bash
export JWT_SECRET_KEY="set-this-from-your-shell-or-secret-store"
export BOOTSTRAP_ADMIN_USERNAME="admin"
export BOOTSTRAP_ADMIN_PASSWORD="set-this-from-your-shell-or-secret-store"
python src/main.py
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[test]

$env:JWT_SECRET_KEY = "set-this-from-your-shell-or-secret-store"
$env:BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:BOOTSTRAP_ADMIN_PASSWORD = "set-this-from-your-shell-or-secret-store"
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --proxy-headers
```

Or run the entrypoint directly:

```powershell
$env:JWT_SECRET_KEY = "set-this-from-your-shell-or-secret-store"
$env:BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:BOOTSTRAP_ADMIN_PASSWORD = "set-this-from-your-shell-or-secret-store"
python src/main.py
```

### Windows (cmd)

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .[test]

set JWT_SECRET_KEY=set-this-from-your-shell-or-secret-store
set BOOTSTRAP_ADMIN_USERNAME=admin
set BOOTSTRAP_ADMIN_PASSWORD=set-this-from-your-shell-or-secret-store
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --proxy-headers
```

Or run the entrypoint directly:

```bat
set JWT_SECRET_KEY=set-this-from-your-shell-or-secret-store
set BOOTSTRAP_ADMIN_USERNAME=admin
set BOOTSTRAP_ADMIN_PASSWORD=set-this-from-your-shell-or-secret-store
python src/main.py
```

## Authentication Model

- `POST /api/v1/auth/token` is the public login endpoint.
- `POST /api/v1/auth/token` is rate-limited by client source and enforces account lockout/backoff for repeated failed logins.
- `GET /api/v1/auth/me` requires a valid bearer token.
- `POST /api/v1/auth/register` is admin-only. Anonymous users and non-admin users cannot create accounts.
- Admin-driven user creation is captured in the audit log table.
- All `/api/v1/budget-items` endpoints require a valid bearer token.

## Run Tests

### Linux/macOS

Run unit tests:

```bash
pytest
```

Run tests with coverage:

```bash
coverage run -m pytest
coverage report -m
```

Run Ruff:

```bash
ruff check .
```

### Windows (PowerShell)

```powershell
pytest
coverage run -m pytest
coverage report -m
ruff check .
```

### Windows (cmd)

```bat
pytest
coverage run -m pytest
coverage report -m
ruff check .
```

## Database Migrations

The app still creates missing tables on startup for local convenience, but schema changes should be managed through Alembic.

Run migrations against the configured database:

```bash
alembic upgrade head
```

Create a new migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe change"
```

## API Summary

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/token`
- `GET /api/v1/auth/me`
- `GET /api/v1/healthz`
- `GET /api/v1/readyz`
- `GET /api/v1/budget-items`
- `GET /api/v1/budget-items/summary`
- `GET /api/v1/budget-items/{item_id}`
- `POST /api/v1/budget-items`
- `PATCH /api/v1/budget-items/{item_id}`
- `DELETE /api/v1/budget-items/{item_id}`

## Container And Kubernetes

The included Dockerfile starts uvicorn against `src/main.py`, and the Kubernetes manifest under `infrastructure/k8s/deployment.yaml` is set up for a single-replica SQLite deployment on k3s behind Traefik and cert-manager.
