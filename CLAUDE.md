# Movies API — Claude Context

## Overview

FastAPI + PostgreSQL application for browsing and managing movies. Has two distinct user populations (movie customers and workflow approvers) with a role-based access control system, an access-request approval workflow, and a single-page Bootstrap 5 UI served from the API itself.

Run: `uvicorn main:app --reload` (API at `localhost:8000`, UI at `localhost:8000/`)  
DB: `docker compose up -d` (PostgreSQL 16, init via `init.sql`)

---

## Tech Stack

- **FastAPI** with async SQLAlchemy (Core, not ORM) + asyncpg
- **PostgreSQL 16** — ENUMs for roles/statuses, `pg_trgm` for fuzzy title search, UUID for public IDs
- **JWT** via `python-jose` (HS256); tokens stored in `api_tokens` table for revocation support
- **passlib/bcrypt** for password hashing; `SecretStr` (Pydantic) for password fields
- **pandas** for CSV upload processing

---

## User Types & Roles

Two completely separate populations share the same `users` table, distinguished by `user_type`.

### Movie Customers (`user_type = 'movie_customer'`)
Registered via `POST /users/`. Account starts as `role='free`; an access request is created for their chosen role and must be approved before they can use elevated access.

| Role | Can do |
|------|--------|
| `free` | Search movies — title only, max 20, no pagination, no login required |
| `full_access` | Search movies — full details (title/year/genres), paginated |
| `admin` | Full details + edit movies |

### Workflow Approvers (`user_type = 'workflow_approver'`)
Registered via `POST /workflow-users/`. Same pending-approval flow. Can never edit movies.

| Role | Can do |
|------|--------|
| `manager` | Approve/deny `full_access` requests from movie customers |
| `admin` | Approve/deny `manager` and `admin` requests |

> A `manager` and a movie-customer `admin` both have `role='admin'` in the DB — they are distinguished by `user_type` only where that matters. The `require_roles()` dependency checks role only, not user_type.

---

## Registration & Approval Flow

1. User registers (`POST /users/` or `POST /workflow-users/`).
2. User is created with `role='free'`; an `access_requests` row is created with `status='pending'`.
3. A UUID `reference_id` is returned — the user pastes this into the "Check Request Status" form in the UI to poll their status without logging in.
4. An approver (manager or admin, routed by `ROLE_APPROVER_MAP`) reviews and approves/denies.
5. On approval: user's `role` and `expires_at` are updated; a JWT API token is issued and stored in `api_tokens`.
6. User can now log in.

**Approval routing** (`services/access_service.py`):
```
full_access  → manager approves
manager      → admin approves
admin        → admin approves
```

---

## Auth Flow

- `POST /sessions/` → validates credentials → issues JWT → stores token in `api_tokens` table.
- Every protected request: JWT decoded + token looked up in `api_tokens` (revocation check).
- `get_current_user` (dependency): decodes JWT + verifies token not revoked.
- `require_roles(*roles)`: wraps `get_current_user`, checks `payload["role"]`.

### Login Sentinel
`api_tokens.request_id` is a FK to `access_requests.id`. Login-issued tokens use `request_id=0`, pointing to a sentinel row seeded in `init.sql` with `id=0, reference_id='00000000-0000-0000-0000-000000000000'`. This sentinel exists so the FK constraint is satisfied without making `request_id` nullable.

`LOGIN_SENTINEL_REQUEST_ID = 0` in `utils/constants.py`.

---

## Role Expiry Background Task

`services/role_expiry_service.py` runs a loop every 60 seconds (started in FastAPI `lifespan`). It downgrades users with `full_access` or `admin` roles back to `free` if:
- Their `expires_at` has passed, **or**
- They have no non-sentinel `api_tokens` rows that are still active (i.e., access was revoked).

Workflow approver accounts use `expires_at = 2099-01-01` so they are never auto-downgraded.

---

## Database Schema

```
users
  id, email, name, password_hash
  role: user_role ENUM('free','full_access','admin','manager')
  user_type: user_type ENUM('movie_customer','workflow_approver')
  expires_at, created_at

access_requests
  id (internal integer PK — never exposed in API responses)
  reference_id UUID DEFAULT gen_random_uuid() — user-facing public ID
  requester_id → users.id
  requested_role: requested_role ENUM('full_access','manager','admin')
  reason, status: request_status ENUM('pending','approved','denied')
  reviewed_by → users.id, review_comment
  requested_expires_at, created_at, updated_at

api_tokens
  id, user_id → users.id
  request_id → access_requests.id  (0 = login sentinel)
  tier: user_role, token (JWT string), expires_at
  revoked BOOLEAN, created_at

audit_log
  id, request_id → access_requests.id
  actor_id → users.id, action, reason, created_at

movies
  movie_id, title, release_year, genres TEXT[]
```

**Important**: the integer `id` from `access_requests` is **never returned in API responses**. All external references use `reference_id` (UUID). Internal service/repo code uses the integer `id` for FK operations.

---

## API Routes

```
POST   /sessions/                      login → JWT
POST   /users/                         register movie customer → {reference_id, message}
POST   /workflow-users/                register workflow approver → {request_id, message}

GET    /movies/                        search (free: title-only, max 20; auth: full details + pagination)
GET    /movies/{movie_id}              get one
POST   /movies/                        upload CSV — admin only
PATCH  /movies/{movie_id}             edit movie — admin only

POST   /access-requests/              submit upgrade request (auth required)
GET    /access-requests/mine          list my own requests (auth required)
GET    /access-requests/lookup/{ref}  check status by UUID — PUBLIC, no auth
GET    /access-requests/              list queue — manager/admin only
GET    /access-requests/{ref}         get one — auth required, own or approver
PATCH  /access-requests/{ref}         approve/deny — manager/admin only
```

---

## File Structure

```
main.py                         FastAPI app + lifespan (role expiry task)
routers.py                      All route registrations in one place
init.sql                        DB schema + seed data (admin user + sentinel row)
docker-compose.yml              PostgreSQL 16 container

auth/
  jwt_handler.py                create/decode JWT
  dependencies.py               get_current_user, require_roles

controllers/
  auth_controller.py            login, register
  movie_controller.py           search, get, upload, edit
  access_controller.py          CRUD + lookup for access requests
  workflow_controller.py        workflow user registration

services/
  auth_service.py               register_user (creates user + access_request), login_user
  access_service.py             submit/fetch/review access requests; ROLE_APPROVER_MAP
  workflow_service.py           register_workflow_user
  movie_service.py              fetch/edit/upload movies
  role_expiry_service.py        background downgrade loop

repositories/
  user_repository.py            get_user_by_email, create_user
  access_repository.py          CRUD for access_requests, api_tokens, audit_log
  movie_repository.py           search, get, upsert, update movies

models/
  auth.py                       LoginRequest, RegisterRequest, TokenResponse, RegistrationResponse
  access.py                     AccessRequestCreate, AccessRequestResponse, ReviewResponse, AccessRequestStatusResponse
  movie.py                      Movie, MovieSearchResponse, MovieUpdate

db/
  database.py                   async engine + session factory
  tables.py                     SQLAlchemy Table definitions

utils/constants.py              JWT settings, CSV column names, LOGIN_SENTINEL_REQUEST_ID

ui/index.html                   Single-page Bootstrap 5 UI (served at /)
```

---

## Key Conventions

- **Passwords** are always `SecretStr` in request models; call `.get_secret_value()` before passing to services.
- **Integer IDs** in `access_requests` are internal only. Always expose `reference_id` (UUID string) to users.
- **Route order matters**: `/mine` and `/lookup/{ref}` must be registered before `/{ref}` in `routers.py` to prevent FastAPI matching literal strings as path params.
- **SQLAlchemy Core** (not ORM) — use `table.insert().values(...)`, `select(table)`, `update(table)`. Row objects from `fetchone()` are accessed by attribute (e.g., `row.id`, `row.reference_id`).
- **Transactions**: `create_user` in the repository commits immediately. Services that do multi-step writes (create user + create request + audit log) call `db.commit()` at the end for the second batch. This is an intentional two-phase commit pattern, not a bug.
- **Seeded admin**: `tuli.ku09@gmail.com` / `TestAdmin123`, `role='admin'`, `user_type='workflow_approver'`. Defined in `init.sql`.
- **DB rebuild**: `docker compose down -v && docker compose up -d` — required whenever `init.sql` changes schema.
