
# Coding Assignment — Submission Report

**GitHub:** https://github.com/tulikundu28/MovieAnalysis  
**Docker Hub:** https://hub.docker.com/r/tulikundu/movie-analysis (tags: `1.1.1`, `latest`)

---

## Deployment

### Local development

```bash
# Start PostgreSQL
docker compose up -d db

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the API (auto-reload on file change)
uvicorn main:app --reload
```

API: `http://localhost:8000` · UI: `http://localhost:8000/` · Docs: `http://localhost:8000/docs`

### Full stack with Docker Compose

```bash
docker compose up -d
```

Starts both `db` (PostgreSQL 16) and `app` (FastAPI). The app waits for the DB health check before starting. Schema and seed data are applied from `init.sql` on first boot. Data is persisted in the `movies-db-data` named Docker volume — survives `docker compose down`. Only `docker compose down -v` removes the data.

```bash
docker compose logs -f app   # tail logs
docker compose down          # stop (data preserved)
docker compose down -v       # stop + wipe database
```

### Container image

The image is published to Docker Hub as a multi-architecture build (`linux/amd64` + `linux/arm64`) so it runs on both standard x86 instances and ARM-based instances (AWS Graviton):

```
docker pull tulikundu/movie-analysis:latest
```

| Tag | Meaning |
|-----|---------|
| `1.1.1` | Exact patch version |
| `1.1` | Latest patch in the 1.1 minor |
| `1` | Latest in the 1.x major |
| `latest` | Current stable release |

### CI/CD pipeline (GitHub Actions)

Pushing a SemVer tag (`v1.x.y`) triggers `.github/workflows/docker-publish.yml` automatically:

1. Checks out the code
2. Sets up QEMU (cross-compilation) and Docker Buildx
3. Uses `docker/metadata-action` to derive all four tags from the Git tag
4. Builds `linux/amd64` + `linux/arm64` in parallel with layer caching (`cache-from: type=gha`)
5. Pushes all tags to Docker Hub

```bash
git tag v1.1.1 && git push origin v1.1.1   # triggers the pipeline
```

### Deploying to a Linux instance (EC2 / Lightsail)

Only three files are needed on the server — the app code ships inside the image:

```
docker-compose.yml
docker-compose.prod.yml
init.sql
```

```bash
# Export secrets (no .env file on disk in production)
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=<strong-password>
export POSTGRES_DB=moviesdb
export JWT_SECRET=<random-hex-32>

# Pull and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
```

`docker-compose.prod.yml` overrides: `APP_ENV=prod` (silences SQL query logs), `restart: unless-stopped`, no DB port exposed to the host.

### Alembic migrations

The app runs `alembic upgrade head` automatically on startup. Fresh installs skip the baseline migration (the schema is already applied by `init.sql`, which stamps `alembic_version = 0001`). Subsequent migrations run normally.

To rebuild the database from scratch (required after `init.sql` schema changes):

```bash
docker compose down -v && docker compose up -d
```

---

## Tests

Two test suites: unit tests (no database) and integration tests (real PostgreSQL).

```bash
pip install -r requirements-test.txt
```

### Unit tests — 42 tests, no database required

All tests mock the repository layer with `AsyncMock`.

```bash
python -m pytest tests/unit/ -v
```

```
tests/unit/test_access_service.py    24 tests
tests/unit/test_auth_service.py       7 tests
tests/unit/test_jwt_handler.py        5 tests
tests/unit/test_workflow_service.py   6 tests
─────────────────────────────────────────────
Total: 42 passed
```

### Integration tests — 57 tests, requires PostgreSQL

Hit a real test database (`moviesdb_test`). Use `httpx.AsyncClient` with the FastAPI app mounted directly — no running server needed.

**One-time test DB setup:**

```bash
createdb moviesdb_test
psql moviesdb_test < init.sql
```

```bash
POSTGRES_TEST_DB=moviesdb_test python -m pytest tests/integration/ -v
```

The `clean_db` autouse fixture truncates all tables and reseeds the admin user + login sentinel before every test, so tests are fully isolated.

### What is tested

**`test_access_service.py` (24 tests)**

| Test | What it verifies |
|------|-----------------|
| `test_role_approver_map` (×4) | Each role maps to the correct approver |
| `test_movie_customer_roles` | `full_access` and `movie_admin` are valid customer roles |
| `test_workflow_roles` | `manager` and `workflow_admin` are valid workflow roles |
| `test_submit_invalid_role_raises_400` | Submitting an invalid role returns 400 |
| `test_submit_duplicate_pending_raises_409` | A second pending request returns 409 with existing `reference_id` |
| `test_submit_happy_path` | Successful submission creates request and audit entry |
| `test_review_not_found_raises_404` | Reviewing a non-existent request returns 404 |
| `test_review_already_reviewed_raises_409` | Reviewing an already-reviewed request returns 409 |
| `test_review_wrong_approver_raises_403` | Approver outside their scope returns 403 |
| `test_review_deny_without_comment_raises_400` | Denial without a comment returns 400 |
| `test_review_approve_issues_token` | Approval upgrades role and issues a JWT token |
| `test_review_deny_with_comment_succeeds` | Denial with comment closes the request |
| `test_revoke_non_approved_raises_409` | Revoking a non-approved request returns 409 |
| `test_revoke_wrong_approver_raises_403` | Wrong approver on revoke returns 403 |
| `test_revoke_happy_path_downgrades_user` | Revoke downgrades user to `free` and revokes tokens |
| `test_cancel_not_found_raises_404` | Cancelling unknown request returns 404 |
| `test_cancel_wrong_requester_raises_403` | Cancelling another user's request returns 403 |
| `test_cancel_non_pending_raises_409` | Cancelling a non-pending request returns 409 |
| `test_cancel_happy_path` | Owner can cancel their own pending request |
| `test_manager_queue_contains_only_full_access` | Manager queue never contains `movie_admin` requests |
| `test_workflow_admin_queue_excludes_full_access` | Workflow admin queue never contains `full_access` requests |

**`test_auth_service.py` (7 tests)** — password hash/verify round-trip, duplicate email, password mismatch, login with wrong password, login with unknown email, successful login returns token.

**`test_jwt_handler.py` (5 tests)** — round-trip claim preservation, default name, `None` expiry, tampered token returns empty dict, expired token returns empty dict.

**`test_workflow_service.py` (6 tests)** — invalid role, password mismatch, duplicate email, both valid roles (`manager`, `workflow_admin`), happy path creates workflow approver.

### Integration test coverage

**`test_auth.py` (16 tests)**

| Area | Happy paths | Non-happy paths |
|------|-------------|-----------------|
| Customer registration | Returns UUID `reference_id`, pending request created | Duplicate email → 409, password mismatch → 400, weak password → 422, past expiry → 422, missing fields → 422 |
| Approver registration | Returns integer `request_id` | Invalid role → 400, duplicate email → 409, password mismatch → 400 |
| Login | Admin token returned with `bearer` type, pending user gets `free`-role token | Wrong password → 401, unknown email → 401 |
| Token enforcement | Authenticated requests succeed | Invalid token → 401, no token on protected endpoint → 403 |

**`test_movies.py` (17 tests)**

| Area | Happy paths | Non-happy paths |
|------|-------------|-----------------|
| Search | Returns results without auth, filters by title/genre/year, cursor pagination advances correctly, last page has null `next_cursor` | No match → empty list, `page_size` over max → 422 |
| Get by ID | Returns correct movie with all fields | Unknown ID → 404 |
| CSV upload | `movie_admin` uploads 3 movies, re-upload is idempotent (upsert), duplicate updates existing row, `workflow_admin` can also upload | No auth → 403, `full_access` token → 403 |
| Edit | Updates title, updates genres | No auth → 403, `full_access` token → 403, unknown ID → 404, empty genres → 422 |

**`test_access_workflow.py` (24 tests)**

| Area | Happy paths | Non-happy paths |
|------|-------------|-----------------|
| Submit | New request after cancellation, re-request after denial | No auth → 403, duplicate pending → 409 with existing `reference_id` |
| View | Owner lists own requests, owner gets by ref, public get returns status-only 4-field shape, approver sees full detail | Unknown ref → 404, different user → 403, non-approver queue → 403 |
| Queue filtering | Manager queue contains only `full_access`, admin queue excludes `full_access` | — |
| Approve | Manager approves `full_access`, approved user logs in with elevated role, admin approves `movie_admin`, token issued | Wrong approver scope (manager on `movie_admin`) → not in queue, double-approve → 409 |
| Deny | Denial with comment recorded, user can resubmit after denial | No comment → 400 |
| Cancel | Owner cancels own pending request | Cancel approved → 409, cancel another user's → 403 |
| Revoke | Manager revokes approved request, revoked token immediately returns 401, user can resubmit after revoke | Revoke pending → 409 |
| Audit log | Full lifecycle recorded (submitted → approved → revoked) | Non-approver → 403 |
| End-to-end | Register → approve → use token → revoke → token rejected → resubmit | — |

---

## Accessing the Live Demo

The application is running on an AWS Lightsail instance. Access is via an SSH tunnel from your local machine:

```bash
ssh -L 16000:localhost:8000 ec2-user@3.107.76.63 -i lightsail.pem
```

Once the tunnel is open, the app is available at:

| URL | Description |
|-----|-------------|
| `http://localhost:16000/` | Bootstrap 5 single-page UI |
| `http://localhost:16000/docs` | Interactive Swagger API docs |
| `http://localhost:16000/healthz` | Health check |

---

## Test Accounts

The following accounts are pre-created on the live instance and can be used for the end-to-end demo:

### Workflow Approvers

| Email | Password | Role | Can approve |
|-------|----------|------|-------------|
| tuli.ku09@gmail.com | TestAdmin123 | `workflow_admin` | `movie_admin`, `manager`, `workflow_admin` requests |
| manager@gmail.com | Manager123 | `manager` | `full_access` requests |

### Movie Customers

| Name | Email | Password | Role |
|------|-------|----------|------|
| Test User | test_user@gmail.com | TestUser123 | `full_access` |
| Test User1 | test_user1@gmail.com | TestUser1234 | `movie_admin` |

> Both movie customer accounts have already been approved and can log in immediately.

---

## Functional Requirements

### What the service does

A movie browsing and access management platform with two independent user populations: **movie customers** who consume movie data, and **workflow approvers** who manage access. Movie data is sourced from the MovieLens public dataset and loaded via CSV upload.

### User populations

| Population | Registration | Scale assumption |
|------------|-------------|-----------------|
| Movie customers | Self-service via `POST /users/` | Hundreds to low thousands — a community of movie enthusiasts, not a public SaaS |
| Workflow approvers | Registered via `POST /workflow-users/` (separate endpoint) | Small number — a handful of managers and admins within the organisation |

### Movie customer capabilities

- **Browse** movies by title, genre, year — no login required (title-only, max 20 results)
- **Register** and submit an access request for `full_access` (full details + pagination) or `movie_admin` (upload/edit)
- **Log in** once their request is approved and use their issued API token
- **Check** the status of their own access request
- **Cancel** a pending request if they change their mind (one pending request per user — a second submission returns the existing `reference_id` and a 409)
- **Re-request** access after a denial or after their access expires — they cannot submit a new request while one is still pending

### Access request rules

- **One pending request per user at any time** — enforced in `submit_access_request` via `get_pending_request_for_user`
- **Re-requestable** after denial (`status = denied`) or expiry (role downgraded back to `free` by the background task)
- **Cancellable** by the owner at any time while `status = pending`
- **Revocable** by an eligible approver at any time while `status = approved` — revoke downgrades the user back to `free` and invalidates all their tokens; they may then re-request

### Approval routing

| Requested role | Approver required |
|---------------|------------------|
| `full_access` | `manager` |
| `movie_admin` | `workflow_admin` |
| `manager` | `workflow_admin` |
| `workflow_admin` | `workflow_admin` |

A manager only sees `full_access` requests in their queue. A `workflow_admin` sees `movie_admin`, `manager`, and `workflow_admin` requests. Neither can act on requests outside their designated scope.

---

## Part 1 — The Movie API

### List endpoint — returns movies, with pagination

`GET /movies/` supports cursor-based pagination via `cursor` (last seen `movie_id`) and `page_size` (default 20, max 100). The response includes a `next_cursor` field — when non-null, pass it as `?cursor=<value>` to fetch the next page. This avoids the offset-scan cost of `LIMIT/OFFSET` on large datasets.

```
GET /movies/?cursor=500&page_size=20
→ { "data": [...], "next_cursor": 520 }
```

Implemented in `repositories/movie_repository.py:search_movies` and `services/movie_service.py:fetch_movies`.

### Search endpoint — filter by title, genre, year

`GET /movies/` accepts query parameters `title`, `genre`, and `release_year`, all optional and combinable:

- **title** — `ILIKE %term%` substring match (PostgreSQL)
- **genre** — array containment (`genres @> ARRAY['Action']`) against the PostgreSQL `TEXT[]` column
- **release_year** — exact integer match

```
GET /movies/?title=toy&genre=Animation&release_year=1995
```

### Get-by-ID endpoint

`GET /movies/{movie_id}` — returns a single movie or `404` if not found. Implemented in `controllers/movie_controller.py:get_movie`.

### Python-backed, containerized

- **FastAPI** with async **SQLAlchemy Core** + **asyncpg** driver against **PostgreSQL 16**
- Multi-stage `Dockerfile` (builder stage installs dependencies, final stage copies only what's needed — no pip cache, non-root `appuser`)
- `docker-compose.yml` brings up the full stack: `db` (PostgreSQL with named volume) + `app` (FastAPI). The app waits for the DB health check before starting.
- Multi-arch image built for `linux/amd64` and `linux/arm64` via Docker Buildx

### Three access tiers

| Tier | Role | What they can do |
|------|------|------------------|
| Public | `free` (no login required) | `GET /movies/` — title only, max 20 results, no pagination |
| Authenticated | `full_access` | `GET /movies/` — full details (title, year, genres), paginated |
| Admin | `movie_admin` | Full details + `POST /movies/` (CSV upload) + `PATCH /movies/{id}` (edit) |

Tier enforcement is done at the route level using the `require_roles()` FastAPI dependency (`auth/dependencies.py`). Every protected request validates the JWT and checks the token against the `api_tokens` table (revocation check) before the handler runs.

---

## Part 2 — The Access Request Workflow

### 1. Request — who, what tier, why, how long

`POST /access-requests/` accepts:

```json
{
  "requested_role": "full_access",
  "reason": "I need to browse movie details for research",
  "requested_expires_at": "2026-12-31T00:00:00Z"
}
```

Requires a logged-in user (any role). On submission, an `access_requests` row is created with `status='pending'` and a UUID `reference_id` is returned. The requester can paste this UUID into the UI's "Check Request Status" form to poll their status without logging in (`GET /access-requests/{ref}` — public, returns status/comment only).

Implemented in `services/access_service.py:submit_access_request`.

### 2. Route — request routed to the right approver by tier

Routing is driven by `ROLE_APPROVER_MAP` in `services/access_service.py`:

```python
ROLE_APPROVER_MAP = {
    "full_access":    "manager",
    "movie_admin":    "workflow_admin",
    "manager":        "workflow_admin",
    "workflow_admin": "workflow_admin",
}
```

When an approver calls `GET /access-requests/`, the service filters the queue to only the roles they are authorised to approve — a manager never sees `movie_admin` requests. The routing check is also enforced on the `PATCH` — if a manager tries to approve a `movie_admin` request, they get `403`.

### 3. Approve or reject — with optional comment

`PATCH /access-requests/{ref}` accepts `status` and an optional `review_comment`:

| status | Who can call | Effect |
|--------|-------------|--------|
| `approved` | Assigned approver | Upgrades user role, issues API token |
| `denied` | Assigned approver | Closes request (comment required) |
| `revoked` | Assigned approver | Downgrades user back to `free`, revokes tokens |
| `cancelled` | Request owner | Cancels own pending request |

Implemented in `services/access_service.py:review_access_request` and `revoke_access_request`.

### 4. Wait — durable, survives restart

All workflow state lives in PostgreSQL (`access_requests` table, `status` column). There is no in-memory state. If the container restarts while a request is pending, nothing is lost — the row is still there, the approver queue still shows it, and the approver can act on it immediately after restart.

The PostgreSQL data lives in a named Docker volume (`movies-db-data`) which survives `docker compose down` and redeployments. Only `docker compose down -v` removes it intentionally.

### 5. Issue or deny — scoped token, time-bounded

On approval:
- The user's `role` and `expires_at` are updated in the `users` table
- A JWT is signed (HS256, `python-jose`) scoped to the approved role and expiry window
- The JWT is stored in `api_tokens` (linked to the `access_requests.id`) for revocation support
- The token is returned to the approver in the API response; the user can log in immediately

On denial: the request is marked `denied` with the recorded comment. No token is issued.

A background task (`services/role_expiry_service.py`) runs every 60 seconds and automatically downgrades users whose `expires_at` has passed or whose tokens have all been revoked — enforcing the time-bounded access without manual intervention.

Implemented in `services/access_service.py:review_access_request` and `services/role_expiry_service.py`.

### 6. Audit — every transition recorded with who/what/when/why

Every state change appends a row to the `audit_log` table:

```
audit_log: id, request_id, actor_id, action, reason, created_at
```

Actions recorded: `submitted`, `approved`, `denied`, `revoked`, `cancelled`, `expired`.

`GET /access-requests/{ref}/audit` returns the full audit trail for a request (manager/workflow_admin only). If someone asks six months later why a user was granted admin access, the answer is one query away — actor, action, timestamp, and comment all recorded at each step.

---

## Roles

| Role | User type | Can do |
|------|-----------|--------|
| `free` | movie_customer | Browse movies (title only, no login needed) |
| `full_access` | movie_customer | Browse movies — full details + pagination |
| `movie_admin` | movie_customer | Full access + upload/edit movies |
| `manager` | workflow_approver | Approve/deny `full_access` requests; see own queue |
| `workflow_admin` | workflow_approver | Approve/deny `movie_admin`, `manager`, `workflow_admin` requests; revoke active access |

Two populations share the `users` table, distinguished by `user_type`. Movie customers register via `POST /users/`; workflow approvers via `POST /workflow-users/`. Both start with `role='free'` and a pending approval request.

---

## Suggested Components — Implementation Status

| Component | Implemented |
|-----------|-------------|
| Request submission endpoint | `POST /access-requests/` |
| Role-aware approval endpoints | `GET /access-requests/` filters queue by caller role; `PATCH` enforces same |
| Durable workflow | PostgreSQL-backed state + named Docker volume — survives any restart |
| Access enforcement | `get_current_user` (JWT decode + revocation check) + `require_roles()` dependency on every protected route |
| Audit log | `audit_log` table; `GET /access-requests/{ref}/audit` |
| Containerized | Multi-stage Dockerfile, `docker-compose.yml`, multi-arch Docker Hub image |

---

## Open-Source Tools & Framework Choices

| Tool | Why chosen |
|------|-----------|
| **FastAPI** | Async-first, automatic OpenAPI docs, Pydantic validation, dependency injection — all the right defaults for a JSON API |
| **PostgreSQL 16** | ACID transactions, native `UUID`, `TEXT[]` for genres, native `ENUM` types for roles/statuses, named volumes for durable state |
| **SQLAlchemy Core** (not ORM) | Explicit query control; cleaner async story than the ORM; rows-as-dicts fit the use case |
| **asyncpg** | Fastest async PostgreSQL driver; pairs naturally with SQLAlchemy async |
| **python-jose** + **passlib/bcrypt** | Standard JWT (HS256) + secure password hashing |
| **Alembic** | Schema migrations with version tracking; idempotent baseline migration so fresh installs and existing deployments converge |
| **pandas** | CSV parsing and transformation for the MovieLens dataset upload |
| **Docker Buildx** | Multi-arch (`linux/amd64` + `linux/arm64`) image from a single build command |

**What I would do differently:** For the approval workflow specifically, a dedicated workflow engine like **Temporal** or **Prefect** would be a better fit at scale. The current design is a hand-rolled state machine in PostgreSQL — it works and is durable, but a workflow engine would give you built-in retry handling, timeouts, escalation, and observable state transitions out of the box. The trade-off was implementation speed vs operational richness.

---

## AI Usage

Claude Code (Claude Sonnet, Anthropic's terminal CLI) was used throughout this project:

- **Scaffolding** — initial project structure, SQLAlchemy table definitions, FastAPI router wiring
- **Design** — worked through the two-phase commit pattern for user+access_request creation, the login sentinel approach for the `api_tokens` FK constraint, and the `ROLE_APPROVER_MAP` routing design
- **Debugging** — diagnosed the duplicate CSV upload 500 (IntegrityError → fixed with `pg_insert().on_conflict_do_update()`), traced the `/mine` 500 back to PostgreSQL attempting a UUID cast on the string "mine"
- **Code review** — flagged dead code (unused repository functions, an unreachable service path), caught the hardcoded `localhost:8000` in the UI, enforced REST conventions (`?owner=me` instead of a `/mine` sub-route, optional-auth on `GET /{ref}` instead of a separate `/lookup/` path)
- **Documentation** — `instruction.md`, inline log messages

Where it accelerated: boilerplate (Dockerfile, Alembic env.py, GitHub Actions workflow YAML) and cross-cutting changes (adding structured logging across all files, centralising all errors into `utils/errors.py`).

Where it needed course-correction:

- **Workflow engine over-engineering:** AI initially suggested adopting a fully managed workflow engine (Temporal, Prefect) for the approval state machine. This was the right instinct for a complex, multi-step workflow with retries and timeouts — but for a linear three-state machine (`pending → approved/denied/revoked`) with no branching, no async side-effects, and a team of one, it was significant operational overhead (running a Temporal cluster, learning its SDK, mapping the data model). The decision was to use PostgreSQL as the state store directly — simpler, already a dependency, and sufficient for the durability requirement. The trade-off is explicitly called out under Reliability.

- **Non-REST route design:** AI proposed `/access-requests/lookup/{ref}` as a separate public lookup path, and `/access-requests/mine` as a sub-route for the user's own requests. Both were corrected: the former became optional-auth on the standard `GET /access-requests/{ref}` endpoint (unauthenticated callers get a public status view; authenticated callers get full detail); the latter became `GET /access-requests/?owner=me` (a query parameter, not a path segment).

- **Separate cancel and delete endpoints:** AI initially generated `POST /access-requests/{ref}/cancel` for cancellation and `DELETE /access-requests/{ref}` for revocation. Both violate REST — cancel and revoke are status transitions, not resource creation or deletion. Corrected to `PATCH /access-requests/{ref}` with `{"status": "cancelled"}` and `{"status": "revoked"}` respectively, routed through the same status-transition endpoint.

- **Internal IDs leaking into the API:** AI returned the integer `id` from `access_requests` in several response bodies. The design decision was that the internal PK is never exposed — all external references use the UUID `reference_id`. This was caught during review of the registration response and the UI's request submission handler (`data.id` → `data.reference_id`).

- **Constant placement:** `OWNER_ME` was placed in `utils/constants.py`; corrected to `access_controller.py` — it is a controller-local sentinel, not a shared application constant.

Validation approach: every AI-generated change was read before accepting, imports were checked, and the server was started to test the affected flow end-to-end. Unit tests (42 total) provided a regression safety net for service-layer changes.

---

## Architectural Trade-offs

### Security

**Current:** HS256 JWT with `python-jose`, bcrypt passwords, `SecretStr` for all password fields, token revocation table (`api_tokens`), `require_roles()` enforced at the dependency layer, secrets fail-loud on startup (app exits if `JWT_SECRET` or `POSTGRES_PASSWORD` are unset).

**To fully harden for production:**
- TLS termination via nginx reverse proxy (currently running HTTP only)
- Short-lived JWTs (15–30 min) with a refresh token flow instead of long-lived tokens
- Rate limiting on `/sessions/` and `/users/` to prevent credential stuffing
- Row-level security in PostgreSQL so the app user cannot read other users' data even if SQL is injected
- AWS Secrets Manager or Vault instead of environment variables for secrets rotation
- Signed audit log (append-only table + WAL archiving) to prevent tampering

### Scalability & Performance

**Current:** Single FastAPI process, single PostgreSQL instance, async I/O throughout (asyncpg + async SQLAlchemy avoids thread-per-request overhead).

**At 10x–100x volume:**
- Horizontal FastAPI scaling: multiple containers behind a load balancer (Compose `replicas`, or k8s Deployment) — stateless, so trivially horizontal
- PostgreSQL read replicas for movie search queries
- PgBouncer connection pooler — asyncpg opens one connection per coroutine; under high concurrency the DB will hit `max_connections` quickly
- **Response caching for read endpoints:** `GET /movies/` and `GET /movies/{id}` are pure reads against slowly changing data — ideal candidates for an HTTP cache layer. Options:
  - **Redis** (`fastapi-cache2` with `@cache` decorator): cache search results by query fingerprint (title + genre + year + cursor), TTL 60–300s. Invalidate on `POST /movies/` or `PATCH /movies/{id}`
  - **CDN / reverse proxy cache** (nginx `proxy_cache`, Cloudflare): cache at the edge for anonymous (`free`) requests — these require no auth and have identical responses across all users
  - `GET /movies/{id}` is a particularly good fit: single key, low write rate, high read rate
- Redis token cache: currently every authenticated request does a DB roundtrip to check `api_tokens`. Replace with a Redis SET lookup (token hash → valid/revoked) to remove DB load from the hot path
- **Rate limiting:** as request volume grows, unthrottled endpoints become a DoS vector and an unfair resource consumer. At scale, apply rate limiting at multiple layers:
  - **Per-IP on unauthenticated endpoints** (`GET /movies/`, `POST /sessions/`, `POST /users/`) — nginx `limit_req_zone` or a gateway like Kong/Traefik; prevents credential stuffing on login and abuse of the free search tier
  - **Per-user on authenticated endpoints** — token-keyed counters in Redis (`slowapi` library integrates directly with FastAPI); ensures one heavy user cannot saturate the DB connection pool for others
  - **Per-user on write endpoints** (`POST /access-requests/`, `POST /movies/`) — tighter limits; a user should not be able to flood the approval queue or trigger thousands of CSV upserts
- The CSV upload batches at 500 rows; for very large datasets, offload to a background worker (Celery, ARQ) so the HTTP request doesn't time out

### Reliability

**Current state:** All workflow state is in PostgreSQL. A service restart mid-flow loses nothing — pending requests remain pending, the approver queue is unaffected. The Docker named volume survives `down` and redeployments.

**Idempotency:** CSV upload uses `INSERT ... ON CONFLICT DO UPDATE` — re-uploading the same file is safe. Seed data uses `ON CONFLICT DO NOTHING`. Alembic migration baseline is idempotent (`CREATE TABLE IF NOT EXISTS`, `DO $$ EXCEPTION WHEN duplicate_object`).

**Gaps to address for production:**
- DB connection retries with exponential backoff on startup (currently the Compose `healthcheck` handles timing, but app code has no retry logic)
- The role expiry background loop has no dead-letter handling — a transient DB error silently skips the expiry cycle. Should log and alert.
- For the approval workflow at scale: idempotency keys on `PATCH /access-requests/{ref}` to prevent double-approval if a client retries a timed-out request

### Auditability

Every state transition writes to `audit_log` with `actor_id`, `action`, `reason`, and `created_at`. The internal integer `access_requests.id` is used as the FK (never exposed in the API); all external references use the UUID `reference_id`.

`GET /access-requests/{ref}/audit` returns the complete trail. Six months later: query by `reference_id` → join `audit_log` → see exactly who submitted, who approved, with what comment, at what time. The `reviewed_by` column on `access_requests` also records the approver directly on the request row.

For a production audit trail: ship `audit_log` to an append-only store (S3 + Athena, or a SIEM) on a schedule so it survives even a database loss.

### Cost

**Current:** One EC2/Lightsail instance (~$5–10/month) running both containers. Docker Hub free tier for the image. GitHub free tier for the repo. PostgreSQL data lives on the instance's local disk (Docker volume).

**Production considerations:**
- Managed RDS (PostgreSQL) adds ~$25–50/month for a `db.t4g.micro` but removes the operational burden of backups, failover, and patching
- Separate instance for the app container and RDS means the DB is not lost if the instance is replaced
- CloudWatch / Grafana for monitoring adds minimal cost but is essential for production visibility
- The multi-arch Docker image means the same image runs on ARM instances (Graviton) which are ~20% cheaper than x86 equivalents for the same workload
