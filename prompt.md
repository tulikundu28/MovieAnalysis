# Build Conversation — MovieAnalysis

This file records every user prompt and the decisions made in response, in chronological order. It serves as the design rationale and build history for the project.

---

## Session 1 — Base app + Auth + UI

**Prompt:** Read claude.md to get the context. The Sign Up as Movie Customer has only signup — no login.

**Decision:** Added a login form to the Movie Customer tab. The tab now has two sections: Sign Up (registration form) and Sign In (login form with a link back to the Existing Customer tab).

---

**Prompt:** In logged-in movie user, under Account tab, if full_access user, add a button to upgrade request to Admin User. If free (i.e. expired), user can request both full and admin.

**Decision:** Added conditional UI in the Account tab. Full-access users see an "Upgrade to Movie Admin" button. Free users see two buttons: "Request Full Access" and "Request Movie Admin". Both open a modal to capture reason and expiry date.

---

**Prompt:** Getting "Movie customers can only request full_access"… I am a full_access user.

**Decision:** Bug fix — `MOVIE_CUSTOMER_ROLES` only contained `{"full_access"}`. Added `"movie_admin"` so that full-access users can request promotion to movie admin.

---

**Prompt:** There are two separate admin roles. Maybe rename as MovieAdmin and WorkflowAdmin?

**Decision:** Split the single `admin` role into `movie_admin` (movie customers who can edit movies) and `workflow_admin` (workflow approvers who can approve manager/workflow_admin requests). Updated DB ENUMs, all service logic, and UI labels accordingly.

---

**Prompt:** workflow_admin should be able to upload movies — why is it not seeing that?

**Prompt:** workflow_admin should also be able to update movies.

**Decision:** Updated `require_roles()` guards on the upload and edit endpoints to accept both `movie_admin` and `workflow_admin`.

---

**Prompt:** In name don't show "User 1" — show the name of the user.

**Decision:** Added `name` to the JWT payload at token creation. Updated `get_user_by_id` in the repository so the approval path (which creates a token) can look up the user's name. UI now displays the name from `payload.name`.

---

**Prompt:** Why is "Request #undefined submitted" when user tries to update access from full to admin? Also the movie user access form doesn't have a dropdown to choose time. Default to ~30 days.

**Decision:**
- Fixed `data.id` → `data.reference_id` in the UI submission handler (integer `id` is never returned in API responses).
- Added an expiry date picker to the access request modal, defaulting to +30 days from today.

---

**Prompt:** For manager, it shouldn't show movie_admin requests — only admin can approve those.

**Decision:** `fetch_access_requests` now derives the visible role list dynamically from `ROLE_APPROVER_MAP`: only requests whose approver matches the caller's role are returned. Managers only see `full_access` requests; workflow_admin sees `movie_admin`, `manager`, and `workflow_admin` requests.

---

**Prompt:** Sign Up as Movie Customer / Free account — browse movies instantly — is not correct. It's signup to get full access and it needs an expiry calendar.

**Decision:** Updated UI copy and layout. Sign-up form now prominently says "Request Full Access or Movie Admin". Added expiry date picker with a 30-day default. Removed misleading "free account" messaging.

---

**Prompt:** For workflow_manager and workflow_admin, they should be able to revoke requests they are eligible to approve. Also needs to be added to the audit log.

**Decision:** Added `revoke_access_request` service function. Revoke downgrades the user back to `free`, revokes all their API tokens, and writes an audit entry. A "Revoke Access" button appears on approved requests in the approver queue.

---

**Prompt:** Revoke is just delete?

**Decision:** No — status is changed to `revoked` (not deleted). The record and audit trail are preserved.

---

**Prompt:** My Access Requests shouldn't have a revoke button — you can't revoke your own token.

**Decision:** Revoke button is only rendered in the approver queue view, not in the user's own "My Requests" view.

---

**Prompt:** Seeing "submitted by User #2" — show names.

**Decision:** `get_audit_logs_for_request` now JOINs `users` to return `actor_name` alongside each audit entry. UI renders the name instead of a user ID.

---

**Prompt:** Check the audit flow. All request, approval, revoke, expired should be audited. Also need to keep track of who and when.

**Decision:** Confirmed all transitions write to `audit_log`: submitted, approved, denied, revoked, cancelled, expired (system). Made `actor_id` nullable so the expiry background task can log `actor_id=NULL` (system action).

---

**Prompt:** In Movie tab, break "Sign Up as Movie Customer" into "Sign Up as Movie Customer" and "Request Access". If already a customer, "Upgrade your access" link goes to the wrong tab — remove that hyperlink. Make the layout better.

**Decision:** Restructured the Movie tab into three distinct cards: Browse (free), Sign Up (new customers), and Request Access (existing customers). Removed the broken upgrade hyperlink.

---

**Prompt:** Remove Check Request Status. On signup, say "free account created. Sign in to check upgrade request".

**Decision:** Removed the public status-check form. Post-registration message now says "Account created. Sign in to track your request." Users check status by logging in and viewing the Account tab.

---

**Prompt:** Sign in — add link to Existing Customer tab.

**Decision:** Added a "Sign in here" link in the Sign Up card that switches to the Existing Customer tab.

---

**Prompt:** If the same user submits two pending requests, there needs to be a way to cancel the pending request from the user side. If a second request is submitted while one is pending, show the existing ref ID and prevent duplicates.

**Decision:** Added `get_pending_request_for_user` repo function. `submit_access_request` checks for an existing pending request and returns 409 with the `reference_id` if one exists. Users can cancel their pending request via `PATCH /access-requests/{ref}` with `{"status": "cancelled"}`. A "Cancel Request" button is rendered for pending requests in the Account tab.

---

**Prompt:** `POST /access-requests/{ref}/cancel` is not REST.

**Decision:** Merged cancel into the existing `PATCH /access-requests/{ref}` endpoint. The controller routes by `body.status`: `cancelled` → `cancel_own_request`; `revoked` → `revoke_access_request`; `approved`/`denied` → `review_access_request`.

---

**Prompt:** Update `DELETE /access-requests/{reference_id}` to be `PATCH` and `{"status": "revoked"}`.

**Decision:** Removed the DELETE route. Revoke is now a PATCH with `{"status": "revoked"}`, consistent with the single status-transition endpoint pattern.

---

**Prompt:** Why do we have `lookup: access_router.get('/lookup/{reference_id}')` — lookup is just GET.

**Decision:** Removed the `/lookup/{ref}` route alias. The public status check is now just `GET /access-requests/{ref}` (no auth required for the public read path, which goes through a separate public-facing service function).

---

## Session 2 — Unit tests

**Prompt:** Give ideas for adding unit tests. Main concentrate on the Python modules and workflow.

**Ideas presented:**
- `test_jwt_handler.py` — round-trip, tamper, expiry
- `test_auth_service.py` — register, login, password helpers
- `test_access_service.py` — ROLE_APPROVER_MAP, submit, review, revoke, cancel, queue filter
- `test_workflow_service.py` — role validation, password mismatch, duplicate email, user type

**Prompt:** Yup, add the tests and run and see. DON'T change any logic.

**Decision:** Added 42 unit tests across 4 test files. All test at the service layer, mocking the repository layer with `AsyncMock`. All 42 passed on first run. No logic was changed.

---

## Session 3 — Constants refactor

**Prompt:** OK now check each file. There shouldn't be any hardcoded values. Things should come from the constant file. Refactor and run tests — it should not change any logic.

**Decision:** Added to `utils/constants.py`:
- `UserRole`, `UserType`, `RequestStatus`, `AuditAction` classes
- `TOKEN_TYPE`, `REGISTRATION_REASON`, `EXPIRY_AUDIT_REASON`, `WORKFLOW_EXPIRY_DATE`
- `DOWNGRADEABLE_ROLES`

Updated 8 files to import and use these constants instead of inline strings:
- `services/access_service.py`
- `services/auth_service.py`
- `services/workflow_service.py`
- `services/role_expiry_service.py`
- `repositories/access_repository.py`
- `controllers/access_controller.py`
- `controllers/movie_controller.py`
- `db/tables.py`

All 42 tests passed after the refactor. No logic changed.

---

## Session 4 — Containerisation + Docker Hub

**Prompt:** I need the Python code in a container. Also the Postgres needs a volume attached so that data is not lost. I want to upload this to Docker Hub so I can pull and deploy on an EC2 instance.

**Decisions:**

1. **`db/database.py`** — replaced hardcoded `localhost` with `POSTGRES_HOST` env var (default `localhost`), so the app container can reach the `db` container by service name.

2. **`Dockerfile`** — `python:3.13-slim`, installs `requirements.txt`, copies source, runs `uvicorn main:app --host 0.0.0.0 --port 8000`.

3. **`.dockerignore`** — excludes `.venv`, `__pycache__`, `.env`, `tests/`, `.claude/`, `archive/`.

4. **`docker-compose.yml`** — added `app` service (`build: .`, `image: tulikundu/movie-analysis:latest`, `depends_on: db: condition: service_healthy`, `POSTGRES_HOST=db`). Postgres already had `movies-db-data` named volume.

5. Image built and pushed to `docker.io/tulikundu/movie-analysis:latest`.
