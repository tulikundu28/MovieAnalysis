# Design Decisions & Discussion

## Part 1 — Movies API

### Database
- **PostgreSQL** via Docker Compose with a named volume for data persistence
- **GIN index** on `genres` (array contains queries `@>`)
- **B-tree index** on `release_year` (scalar integer, range queries)
- **GIN trigram index** on `title` using `pg_trgm` extension for `ILIKE '%term%'` substring search
- `movie_id` is the primary key — already indexed, no extra index needed

### Schema
- `genres` stored as `TEXT[]` (Postgres array) — enables `= ANY()` and `@>` queries with GIN index
- `release_year` extracted from title string at insert time (e.g. "Toy Story (1995)" → 1995)
- `(no genres listed)` normalised to `NULL` at insert
- Genres normalised to title case at insert and lookup for consistent matching

### Architecture
- Layered: controllers → services → repositories → db
- **SQLAlchemy Core** (not ORM) as query builder — no hardcoded SQL strings
- Column names and table names defined as constants in `utils/constants.py`
- **asyncpg** driver for async PostgreSQL connections
- `db/tables.py` defines table structure using SQLAlchemy Core with constants
- `ARRAY` imported from `sqlalchemy.dialects.postgresql` for proper Postgres array support

### File Upload
- `POST /movies/upload` accepts CSV as `multipart/form-data`
- `CSVProcessorHelper` extends `FileProcessorHelper` ABC — extensible to XLS/XLSX later
- CSV transformation logic lives in the helper, not the service
- Service only orchestrates: call helper → insert in batches
- Batch insert size defined as `BATCH_SIZE = 500` constant
- All CSV column names, patterns, and sentinel values are constants

### Search & Pagination
- `GET /movies/` handles both list (no params) and search (with params)
- `GET /movies/{movie_id}` is a direct lookup — not a filter
- Search filters: `title` (ILIKE), `genre` (array contains), `release_year` (exact match)
- **Cursor pagination** over offset pagination — more efficient for large datasets, no drift on inserts
- Cursor is `movie_id` — stable, indexed, sequential
- `next_cursor` is `None` when results fewer than `page_size` — signals end of results
- `page_size` capped at `MAX_PAGE_SIZE = 100`

### Models
- Pydantic `Movie` used as response model on `GET /movies/{movie_id}`
- `MovieSearchResponse` wraps list results: `{"data": [...], "next_cursor": int | null}`
- `MoviesSearch` removed — controller uses FastAPI query params directly

### Credentials & Config
- Credentials in `.env`, never hardcoded
- `.env` excluded from git via `.gitignore`
- `.env.example` committed with empty values as reference
- `python-dotenv` loads env vars at runtime

### Requirements
- Dependencies pinned to major versions using `~=` (e.g. `fastapi~=0.115`)
- Allows minor/patch updates, blocks breaking major changes

---

## Part 2 — Access Request Workflow

### Workflow Engine
- **Temporal** chosen for durable workflow orchestration
- Handles long-running workflows that pause for hours/days waiting for human approval
- State persisted in Postgres — survives service restarts
- Approval/rejection sent as Temporal signals to the waiting workflow
- `temporalio/auto-setup` image handles Temporal's own DB schema automatically
- Temporal shares the same Postgres instance, creates its own `temporal` and `temporal_visibility` databases

### Roles
- Three roles: `requester` (default), `manager`, `admin`
- Roles stored in separate `user_roles` table, not on the `users` table
- Role is dynamic — can be granted, expired, revoked
- Separating roles from users gives full role history and supports multiple concurrent roles
- Current role = latest active, non-revoked, non-expired row in `user_roles`
- `expires_at = NULL` means permanent (e.g. permanent admin)
- On expiry — Temporal activity sets `revoked = TRUE`

### Access Requests
- `expires_at` on `access_requests` (not `duration_days`) — explicit timestamp is clearer and unambiguous
- `workflow_id` stored on request — used to send Temporal signals (approve/reject) back to the correct workflow
- Routing: `write` tier → manager approver, `admin` tier → admin approver

### Tokens
- JWT tokens issued on approval, scoped to approved tier
- Raw token never stored — only `token_hash` stored in `api_tokens`
- Token expiry matches `access_request.expires_at`
- Tokens can be revoked by admin — sets `revoked = TRUE`

### Audit Log
- Every transition recorded: who, what, when, why
- `audit_log` references both `request_id` and `actor_id`
- Append-only — no updates, full history preserved

### DB Schema Decisions
- `ENUM` types for `access_tier`, `request_status`, `user_role` — enforced at DB level
- `TIMESTAMPTZ` everywhere — timezone-aware timestamps
- `updated_at` on `access_requests` — tracks last status change
- Foreign keys throughout for referential integrity
- Indexes on frequently queried columns: `user_id`, `status`, `request_id`

### Infrastructure
- All services containerised in Docker Compose
- Temporal UI available at `http://localhost:8080` for workflow monitoring
- Single `.env` file shared across all services
- Temporal uses same Postgres credentials as app, different database
