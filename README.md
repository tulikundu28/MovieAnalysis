# MovieAnalysis

A movie browsing and access-management API built with FastAPI, async SQLAlchemy Core, and PostgreSQL. Users can search and browse movies, request elevated access tiers through a human-in-the-loop approval workflow, and manage their own requests.

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI |
| Database | PostgreSQL 16 |
| ORM / queries | SQLAlchemy Core (async) + asyncpg |
| Auth | HS256 JWT (`python-jose`) + bcrypt (`passlib`) |
| Migrations | Alembic |
| CSV ingestion | pandas |
| Containerisation | Docker + Docker Compose |

---

## Project Structure

```
├── auth/                   # JWT creation/decoding, FastAPI auth dependencies
├── controllers/            # HTTP handlers (thin — delegate to services)
├── db/                     # Engine, session factory, table definitions
├── migrations/             # Alembic migration scripts
├── models/                 # Pydantic request/response schemas
├── repositories/           # Raw SQL queries (SQLAlchemy Core)
├── services/               # Business logic
├── tests/
│   ├── unit/               # Service-layer tests (mocked repositories, no DB)
│   └── integration/        # Full-stack tests via httpx (real PostgreSQL)
├── ui/                     # Static single-page UI
├── utils/                  # Constants, errors, CSV helper
├── main.py                 # App entry point, lifespan, global exception handler
└── routers.py              # Router registration
```

---

## Roles & Access

Two independent user populations share the `users` table, distinguished by `user_type`.

| Role | User type | Permissions |
|---|---|---|
| `free` | movie_customer | Browse movie titles (no login required) |
| `full_access` | movie_customer | Full movie details + pagination |
| `movie_admin` | movie_customer | Full details + CSV upload + edit movies |
| `manager` | workflow_approver | Approve / deny `full_access` requests |
| `workflow_admin` | workflow_approver | Approve / deny `movie_admin`, `manager`, `workflow_admin` requests; revoke active access |

---

## API Endpoints

### Movies

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/movies/` | None | Search / list movies (title, genre, year; cursor-paginated) |
| `GET` | `/movies/{id}` | None | Get single movie |
| `POST` | `/movies/` | `movie_admin` | Bulk upload via CSV |
| `PATCH` | `/movies/{id}` | `movie_admin` | Partial update |

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/users/` | None | Register as movie customer |
| `POST` | `/sessions/` | None | Log in, receive JWT |
| `POST` | `/workflow-users/` | None | Register as workflow approver |

### Access Requests

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/access-requests/` | Any | Submit a role upgrade request |
| `GET` | `/access-requests/` | `manager` / `workflow_admin` | List queue (role-filtered); `?owner=me` for own requests |
| `GET` | `/access-requests/{ref}` | Optional | Get request (full view for owners/approvers; status-only for public) |
| `PATCH` | `/access-requests/{ref}` | Any | Approve / deny / cancel / revoke |
| `GET` | `/access-requests/{ref}/audit` | `manager` / `workflow_admin` | Full audit trail |

### Ops

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | DB connectivity check |

---

## Access Request Lifecycle

```
pending ──approve──► approved ──revoke──► revoked
        ──deny────► denied               (re-requestable)
        ──cancel──► cancelled
                    approved ──expires──► free (background task, every 60s)
```

Every transition is recorded in the `audit_log` table with actor, action, timestamp, and optional comment.

---

## Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL 16 (or Docker)

### Setup

```bash
# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=password
export POSTGRES_DB=moviesdb
export JWT_SECRET=<random-hex-32>

# Start PostgreSQL (if using Docker)
docker compose up -d db

# Run the app (migrations run automatically on startup)
uvicorn main:app --reload
```

| URL | Description |
|---|---|
| `http://localhost:8000/` | Single-page UI |
| `http://localhost:8000/docs` | Swagger / OpenAPI docs |
| `http://localhost:8000/healthz` | Health check |

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_USER` | Yes | — | Database username |
| `POSTGRES_PASSWORD` | Yes | — | Database password |
| `POSTGRES_DB` | Yes | — | Database name |
| `POSTGRES_HOST` | No | `localhost` | Database host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `JWT_SECRET` | Yes | — | Secret key for JWT signing |
| `JWT_EXPIRY_MINUTES` | No | `60` | JWT lifetime in minutes |
| `APP_ENV` | No | `dev` | Set to `prod` to silence SQL query logs |

---

## Docker

### Full stack

```bash
docker compose up -d
```

Starts `db` (PostgreSQL 16) and `app` (FastAPI). The app waits for the DB health check before starting. Data persists in the `movies-db-data` named volume across restarts.

```bash
docker compose logs -f app     # tail logs
docker compose down            # stop (data preserved)
docker compose down -v         # stop and wipe database
```

### Production override

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
```

The prod override sets `APP_ENV=prod`, `restart: unless-stopped`, and removes the DB port binding.

### Pre-built image

```bash
docker pull tulikundu/movie-analysis:latest
```

Multi-arch image (`linux/amd64` + `linux/arm64`) published to Docker Hub.

---

## Tests

```bash
# Unit tests — no database required (42 tests)
python -m pytest tests/unit/ -v

# Integration tests — requires a running PostgreSQL instance (57 tests)
POSTGRES_TEST_DB=moviesdb_test python -m pytest tests/integration/ -v
```

Unit tests mock the repository layer with `AsyncMock`. Integration tests mount the FastAPI app directly via `httpx.AsyncClient` and reset the database before each test.

---

## CI/CD

Pushing a SemVer tag triggers the GitHub Actions workflow (`.github/workflows/docker-publish.yml`), which builds and pushes a multi-arch image to Docker Hub:

```bash
git tag v1.2.0 && git push origin v1.2.0
```
