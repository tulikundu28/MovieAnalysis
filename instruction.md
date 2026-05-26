# MovieAnalysis — Setup & Operations Guide

## Overview

FastAPI + PostgreSQL application for browsing and managing movies. Includes a role-based access control system, an access-request approval workflow, and a Bootstrap 5 single-page UI served directly from the API.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.13+ |
| Docker + Docker Compose | 24+ |
| PostgreSQL (local dev only) | 16 (via Docker) |

---

## Environment Variables

Create a `.env` file in the project root. All variables below are required.

```env
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=moviesdb
POSTGRES_PORT=5432

# App (overridden to "db" automatically inside Docker Compose)
POSTGRES_HOST=localhost

# JWT
JWT_SECRET=change-this-to-a-long-random-secret-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=60
```

> **Production**: change `JWT_SECRET` and `POSTGRES_PASSWORD` to strong random values before deploying.

---

## Running Locally (without Docker)

### 1. Start the database

```bash
docker compose up -d db
```

This starts PostgreSQL 16, creates the schema and seed data from `init.sql`, and persists data in the `movies-db-data` named volume.

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the API

```bash
uvicorn main:app --reload
```

API: `http://localhost:8000`
UI:  `http://localhost:8000/`
Docs: `http://localhost:8000/docs`

---

## Running with Docker Compose (full stack)

```bash
docker compose up -d
```

This starts both `db` (PostgreSQL) and `app` (FastAPI) containers. The app waits for the DB health check before starting.

```bash
# View logs
docker compose logs -f app

# Stop
docker compose down

# Stop and wipe the database volume (full reset)
docker compose down -v
```

> After `down -v` the DB volume is deleted. The schema and seed data are re-applied automatically from `init.sql` on next `up`.

---

## Deploying to EC2

### On your local machine — build and push

```bash
docker build -t tulikundu/movie-analysis:latest .
docker push tulikundu/movie-analysis:latest
```

### On the EC2 instance

**1. Install Docker**

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # log out and back in after this
```

**2. Copy required files to the instance**

Only three files are needed on EC2 — the app code is in the Docker Hub image:

```
docker-compose.yml
init.sql
.env             ← use production values here
```

**3. Start the stack**

```bash
docker compose pull
docker compose up -d
```

**4. Open port 8000** in the EC2 security group (inbound TCP 8000 from your IP or 0.0.0.0/0).

App is available at `http://<ec2-public-ip>:8000`.

### Redeploying after a code change

```bash
# On your Mac
docker build -t tulikundu/movie-analysis:latest .
docker push tulikundu/movie-analysis:latest

# On EC2
docker compose pull && docker compose up -d
```

The `movies-db-data` volume is preserved across redeployments — data is never lost unless you run `down -v`.

---

## Default Admin Account

Seeded by `init.sql` on first boot:

| Field | Value |
|-------|-------|
| Email | tuli.ku09@gmail.com |
| Password | TestAdmin123 |
| Role | workflow_admin |
| User type | workflow_approver |

This account can approve all role requests and manage workflow users.

---

## API Reference

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/sessions/` | — | Login → JWT |
| POST | `/users/` | — | Register movie customer |
| POST | `/workflow-users/` | — | Register workflow approver |

### Movies

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/movies/` | Optional | Search movies |
| GET | `/movies/{id}` | Optional | Get one movie |
| POST | `/movies/` | movie_admin / workflow_admin | Upload CSV |
| PATCH | `/movies/{id}` | movie_admin / workflow_admin | Edit movie |

### Access Requests

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/access-requests/` | Any logged-in | Submit upgrade request |
| GET | `/access-requests/mine` | Any logged-in | My own requests |
| GET | `/access-requests/` | manager / workflow_admin | Approver queue |
| GET | `/access-requests/{ref}` | Owner or approver | Get one request |
| GET | `/access-requests/{ref}/audit` | manager / workflow_admin | Audit trail |
| PATCH | `/access-requests/{ref}` | Varies | Approve / deny / revoke / cancel |

**PATCH status values:**

| `status` | Who can call | Effect |
|----------|-------------|--------|
| `approved` | Assigned approver | Upgrades user role, issues API token |
| `denied` | Assigned approver | Denies request (comment required) |
| `revoked` | Assigned approver | Downgrades user back to free, revokes tokens |
| `cancelled` | Request owner | Cancels own pending request |

---

## Role & Approval Routing

### Movie Customers (`user_type = movie_customer`)

| Role | Permissions |
|------|-------------|
| `free` | Search movies (title only, max 20 results, no login needed) |
| `full_access` | Search movies with full details + pagination |
| `movie_admin` | Full access + upload and edit movies |

### Workflow Approvers (`user_type = workflow_approver`)

| Role | Can approve |
|------|-------------|
| `manager` | `full_access` requests |
| `workflow_admin` | `movie_admin`, `manager`, `workflow_admin` requests |

### Approval routing

```
full_access   → approved by manager
movie_admin   → approved by workflow_admin
manager       → approved by workflow_admin
workflow_admin→ approved by workflow_admin
```

---

## Database Schema

```
movies            movie_id, title, release_year, genres[]
users             id, email, name, password_hash, role, user_type, expires_at
access_requests   id, reference_id (UUID), requester_id, requested_role,
                  reason, status, reviewed_by, review_comment, requested_expires_at
api_tokens        id, user_id, request_id, tier, token, expires_at, revoked
audit_log         id, request_id, actor_id (NULL = system), action, reason
```

### Rebuilding the database

Required when `init.sql` schema changes:

```bash
docker compose down -v && docker compose up -d
```

---

## Running Tests

```bash
pip install pytest pytest-asyncio pytest-mock
python -m pytest tests/unit/ -v
```

42 unit tests covering JWT handling, auth service, access request workflow, and workflow user registration. All tests mock the repository layer — no database required.

---

## Project Structure

```
main.py                     FastAPI app + lifespan (role expiry task)
routers.py                  All route registrations
init.sql                    DB schema + seed data
Dockerfile                  App container definition
docker-compose.yml          Full-stack local/deploy setup
.dockerignore               Files excluded from the image

auth/
  jwt_handler.py            Create / decode JWT
  dependencies.py           get_current_user, require_roles

controllers/
  auth_controller.py        Login, register
  movie_controller.py       Search, get, upload, edit
  access_controller.py      Access request CRUD
  workflow_controller.py    Workflow user registration

services/
  auth_service.py           Register + login logic
  access_service.py         Access request workflow, ROLE_APPROVER_MAP
  workflow_service.py       Workflow user registration
  movie_service.py          Movie fetch / edit / CSV upload
  role_expiry_service.py    Background loop: downgrades expired users

repositories/
  user_repository.py        User DB operations
  access_repository.py      Access requests, tokens, audit log
  movie_repository.py       Movie DB operations

models/                     Pydantic request/response schemas
db/
  database.py               Async engine + session factory
  tables.py                 SQLAlchemy Core table definitions

utils/constants.py          All shared string constants and enums
ui/index.html               Bootstrap 5 single-page UI
tests/unit/                 42 unit tests
```
