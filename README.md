# Maritime PMS Data Extraction & Setup Tool

A full-stack web application for extracting, classifying, and exporting data from Planned Maintenance System (PMS) documents for vessel onboarding at Union Maritime.

---

## Architecture Overview

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TanStack Query v5, Zustand, Tailwind CSS v3 |
| Backend | FastAPI (Python 3.11), SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 15 (asyncpg driver) |
| Cache / Queue | Redis 7, Celery |
| Infrastructure | Azure Container Apps, Azure Static Web Apps, Azure Database for PostgreSQL |
| CI/CD | GitHub Actions |
| IaC | Terraform (Azure Provider ~3.90) |

---

## Quick Start (Docker Compose)

### Prerequisites
- Docker Desktop 4.x+
- Docker Compose v2

```bash
# 1. Clone the repository
git clone https://github.com/unionmaritime/maritime-pms-tool.git
cd maritime-pms-tool

# 2. Start the full stack
docker compose up --build

# 3. Apply database migrations (first run only)
docker compose exec backend alembic upgrade head

# 4. Seed the default super_admin user
docker compose exec backend python scripts/seed_admin.py
```

Services will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/api/v1/docs
- Health check: http://localhost:8000/health

Default seed credentials (set in `.env` or environment):
- Email: `admin@unionmaritime.com`
- Password: set via `SEED_ADMIN_PASSWORD` env var

---

## Local Development (without Docker)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL and SECRET_KEY

# Run database migrations
alembic upgrade head

# Seed admin user
python scripts/seed_admin.py

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api to localhost:8000)
npm run dev
```

---

## Project Structure

```
maritime-pms-tool/
├── backend/
│   ├── app/
│   │   ├── core/           # Config, security (JWT), database engine
│   │   ├── models/         # SQLAlchemy ORM models (User, VesselProject, …)
│   │   ├── schemas/        # Pydantic v2 request/response schemas
│   │   ├── api/v1/         # FastAPI route handlers (auth, users, vessels)
│   │   ├── deps.py         # Shared FastAPI dependencies (auth, RBAC)
│   │   └── main.py         # Application entry point
│   ├── alembic/            # Database migration scripts
│   ├── scripts/            # Utility scripts (seed_admin.py)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios client with JWT interceptors
│   │   ├── components/     # Layout shell, ProtectedRoute
│   │   ├── hooks/          # useAuth
│   │   ├── pages/          # Login, Dashboard, Users
│   │   ├── store/          # Zustand auth store
│   │   └── types/          # Shared TypeScript interfaces
│   ├── vite.config.ts
│   └── package.json
├── terraform/              # Azure infrastructure (main.tf, variables.tf, outputs.tf)
├── .github/workflows/      # GitHub Actions CI pipeline
├── docker-compose.yml      # Local dev stack
└── docker-compose.prod.yml # Production overrides
```

---

## User Roles

| Role | Permissions |
|---|---|
| `super_admin` | Full access to all resources, user management |
| `vessel_admin` | Create and manage vessel projects |
| `qc_reviewer` | Review and approve classified documents |
| `viewer` | Read-only access to assigned vessels |
| `api_integration` | Machine-to-machine API access |

---

## API Endpoints (Sprint 1)

### Authentication
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Obtain access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Exchange refresh token for new access token |
| POST | `/api/v1/auth/logout` | Invalidate session (client-side) |

### Users
| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/users` | super_admin |
| POST | `/api/v1/users` | super_admin |
| GET | `/api/v1/users/me` | authenticated |
| PUT | `/api/v1/users/me` | authenticated |
| GET | `/api/v1/users/{id}` | super_admin |
| PUT | `/api/v1/users/{id}` | super_admin |
| DELETE | `/api/v1/users/{id}` | super_admin |

### Vessels
| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/vessels` | authenticated |
| POST | `/api/v1/vessels` | vessel_admin+ |
| GET | `/api/v1/vessels/{id}` | authenticated |
| PUT | `/api/v1/vessels/{id}` | vessel_admin+ |
| DELETE | `/api/v1/vessels/{id}` | vessel_admin+ |

---

## Database Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

---

## Infrastructure Deployment (Terraform)

```bash
cd terraform

# Initialise providers
terraform init

# Plan changes
terraform plan \
  -var="subscription_id=<YOUR_SUBSCRIPTION_ID>" \
  -var="db_admin_password=<SECURE_PASSWORD>"

# Apply
terraform apply \
  -var="subscription_id=<YOUR_SUBSCRIPTION_ID>" \
  -var="db_admin_password=<SECURE_PASSWORD>"
```

---

## CI/CD

The GitHub Actions pipeline (`.github/workflows/ci.yml`) runs on every push to `main`/`develop` and on PRs to `main`:

1. **backend-test** — runs `pytest` against a live PostgreSQL service container
2. **frontend-test** — type-checks, lints, and builds the React app
3. **docker-build** — builds and tags both Docker images with the git SHA
4. **deploy-staging** — manual trigger; pushes images to ACR and updates Container App revision

---

## Security Notes

- All passwords hashed with bcrypt (passlib)
- JWT tokens contain: `user_id`, `email`, `role`, `tenant_id`
- `tenant_id` present on **every** database table (multi-tenancy)
- Soft-delete pattern: rows are never hard-deleted (`is_deleted = True`)
- Rate limiting: 100 requests/minute per IP (configurable)
- CORS origins configured via `ALLOWED_ORIGINS` env var

---

## Sprint Roadmap

| Sprint | Focus |
|---|---|
| Sprint 1 (current) | Foundation: auth, user management, vessel CRUD, infrastructure |
| Sprint 2 | Document ingestion from SharePoint, file upload pipeline |
| Sprint 3 | AI-powered classification engine |
| Sprint 4 | QC review workflow |
| Sprint 5 | Export to target PMS formats |
| Sprint 6 | Reporting, audit trail, production hardening |
