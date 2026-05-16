# Budget Tracker Backend

FastAPI backend for managing budget items with JWT authentication, SQLAlchemy-backed persistence, health checks, and Kubernetes-ready deployment settings.

## Features

- CORS enabled with configurable allowed origins, restricts to api.travler7282.com by default.
- Auth endpoints for registration, token issuance, and current-user lookup.
- Database-backed token endpoint rate limiting to reduce brute-force attempts across app processes.
- Login lockout/backoff after repeated failed password attempts.
- Audit logging for admin-driven user creation.
- CRUD endpoints for budget items at `/api/v1/budget-items`.
- Budget item typing via `itemType` with compatibility flags such as `isLoan`, `isExpense`, and `isCreditCard`.
- Cash-flow calendar endpoint for planned vs actual daily balances.
- Health and readiness endpoints at `/api/v1/healthz` and `/api/v1/readyz`.
- Alembic migrations for schema changes.
- Environment-driven configuration for secrets, database connection, ingress base path, and optional TLS.

## Environment Variables

Set these before running the API:

- `JWT_SECRET_KEY`: required for authenticated endpoints.
- `AUTH_RATE_LIMIT_WINDOW_SECONDS`: optional token endpoint rate-limit window in seconds, defaults to `60`.
- `AUTH_RATE_LIMIT_MAX_REQUESTS`: optional max token requests per client per window, defaults to `10`.
- `AUTH_LOCKOUT_THRESHOLD`: optional failed login attempts before lockout, defaults to `5`.
- `AUTH_LOCKOUT_SECONDS`: optional lockout/backoff duration in seconds, defaults to `300`.
- `BOOTSTRAP_ADMIN_USERNAME`: optional username for creating or updating the first admin account at startup.
- `BOOTSTRAP_ADMIN_PASSWORD`: optional password for the bootstrap admin account. Set this from your shell or secret store, not the repo.
- `CORS_ALLOWED_ORIGINS`: optional comma-separated list of allowed CORS origins, defaults to `https://www.travler7282.com,https://api.travler7282.com` (frontend and backend). Set to `*` for development/open access (not recommended for production).
- `DATABASE_URL`: optional, defaults to a local SQLite database file for dev/test. Use PostgreSQL for deployed environments, such as `postgresql+psycopg://budget_tracker:<password>@<host>:5432/budget_tracker`.
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
- `GET /api/v1/auth/users` is admin-only and returns the list of all users without passwords.
- `GET /api/v1/auth/users/{user_id}` is admin-only and returns a single user without their password.
- `PATCH /api/v1/auth/users/{user_id}` is admin-only and can update username, password, role, and active status.
- `DELETE /api/v1/auth/users/{user_id}` is admin-only and removes a user account.
- Admin-driven user creation is captured in the audit log table.
- Admin-driven user updates and deletes are captured in the audit log table.
- All API endpoints require authentication except `GET /api/v1/healthz`, `GET /api/v1/readyz`, and `POST /api/v1/auth/token`.
- All `/api/v1/budget-items` endpoints require a valid bearer token.

## Architecture

The app is now structured as a modular backend with service boundaries that can later become separate deployable services:

- `budget_tracker.config`: environment-driven settings.
- `budget_tracker.database`: SQLAlchemy engine, sessions, and base metadata.
- `budget_tracker.models`: persistence models and database-owned enums.
- `budget_tracker.schemas`: request and response contracts.
- `budget_tracker.security`: password hashing, JWT creation, and auth dependencies.
- `budget_tracker.services.auth`: login rate limiting, lockout/backoff, and bootstrap admin behavior.
- `budget_tracker.services.budget_items`: budget item domain rules and conversion helpers.
- `budget_tracker.services.cash_flow`: planned vs actual cash-flow calendar calculations.
- `budget_tracker.api.routers`: HTTP routing for auth, budget items, health, and root metadata.

SQLite is retained as the zero-setup local default. Kubernetes and production-style deployments should provide `DATABASE_URL` from a secret that points to PostgreSQL or a managed relational database.

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
- `GET /api/v1/auth/users`
- `GET /api/v1/auth/users/{user_id}`
- `PATCH /api/v1/auth/users/{user_id}`
- `DELETE /api/v1/auth/users/{user_id}`
- `GET /api/v1/healthz`
- `GET /api/v1/readyz`
- `GET /api/v1/budget-items`
- `GET /api/v1/budget-items/summary`
- `GET /api/v1/budget-items/{item_id}`
- `POST /api/v1/budget-items`
- `PATCH /api/v1/budget-items/{item_id}`
- `DELETE /api/v1/budget-items/{item_id}`
- `GET /api/v1/cash-flow/calendar`

## Container And Kubernetes

The included Dockerfile starts uvicorn against `src/main.py`, and the Kubernetes manifest under `infrastructure/k8s/deployment.yaml` is set up for k3s behind Traefik and cert-manager. The manifest includes an in-cluster PostgreSQL deployment, a ClusterIP service for internal-only database access, and a persistent volume claim for database storage. Application credentials are intentionally not committed to the repo.

Create the namespace first if it does not already exist:

```bash
kubectl create namespace budget-tracker
```

Create the application secret separately from the manifest so secrets stay out of git:

```bash
kubectl -n budget-tracker create secret generic budget-tracker-app-secrets \
	--from-literal=jwt-secret-key='<generate-a-long-random-secret>' \
	--from-literal=postgres-user='budget_tracker' \
	--from-literal=postgres-password='<generate-a-strong-password>' \
	--from-literal=postgres-db='budget_tracker' \
	--from-literal=bootstrap-admin-username='admin' \
	--from-literal=bootstrap-admin-password='<set-an-initial-admin-password>' \
	--from-literal=database-url='postgresql+psycopg://budget_tracker:<generate-a-strong-password>@budget-tracker-postgres.budget-tracker.svc.cluster.local:5432/budget_tracker'
```

If the secret already exists, replace it safely with:

```bash
kubectl -n budget-tracker delete secret budget-tracker-app-secrets
kubectl -n budget-tracker create secret generic budget-tracker-app-secrets \
	--from-literal=jwt-secret-key='<generate-a-long-random-secret>' \
	--from-literal=postgres-user='budget_tracker' \
	--from-literal=postgres-password='<generate-a-strong-password>' \
	--from-literal=postgres-db='budget_tracker' \
	--from-literal=bootstrap-admin-username='admin' \
	--from-literal=bootstrap-admin-password='<set-an-initial-admin-password>' \
	--from-literal=database-url='postgresql+psycopg://budget_tracker:<generate-a-strong-password>@budget-tracker-postgres.budget-tracker.svc.cluster.local:5432/budget_tracker'
```

If `bootstrap-admin-username` and `bootstrap-admin-password` are present in the secret, the app will create or reset that admin user on startup. Because of that, treat those keys as bootstrap-only values: once you have confirmed the admin account works, remove or rotate them if you do not want every restart to keep resetting the same admin password.

Apply the manifest:

```bash
kubectl apply -f infrastructure/k8s/deployment.yaml
```

The API should use this in-cluster PostgreSQL connection string for `DATABASE_URL`:

```text
postgresql+psycopg://budget_tracker:<postgres-password>@budget-tracker-postgres.budget-tracker.svc.cluster.local:5432/budget_tracker
```

Replace `<postgres-password>` with the same value you set in `budget-tracker-app-secrets`. The hostname `budget-tracker-postgres.budget-tracker.svc.cluster.local` is only reachable from inside the cluster, so the database does not need an Ingress.

The bootstrap admin values map to the app environment variables `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD`.

The manifest creates these PostgreSQL-related resources:

- `Deployment/budget-tracker-postgres`
- `Service/budget-tracker-postgres`
- `PersistentVolumeClaim/budget-tracker-postgres-data`

The application secret is expected to be named `budget-tracker-app-secrets`. Ingress TLS is configured to use a separate secret named `budget-tracker-tls`, which should be created and managed by cert-manager.

The backend `Deployment`, `Service`, and `Ingress` are all placed in the `budget-tracker` namespace so the app and database resolve each other consistently.

After deployment, you can verify database connectivity from the API pod:

```bash
kubectl -n budget-tracker get pods
kubectl -n budget-tracker exec deploy/budget-tracker-backend -- printenv DATABASE_URL
kubectl -n budget-tracker get svc budget-tracker-postgres
kubectl -n budget-tracker get secret budget-tracker-app-secrets
```

The deployment still configures ingress using host `api.travler7282.com`; update that hostname for your environment before exposing the app publicly.
