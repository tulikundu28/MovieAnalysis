import os
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from services.auth_service import hash_password

# ── Test database ─────────────────────────────────────────────────────────────
# Requires a separate PostgreSQL DB (default: moviesdb_test) with the schema
# already applied from init.sql. Set POSTGRES_TEST_DB to override the name.

_TEST_DB_URL = (
    f"postgresql+asyncpg://"
    f"{os.getenv('POSTGRES_USER', 'postgres')}:{os.getenv('POSTGRES_PASSWORD', 'postgres')}"
    f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
    f"/{os.getenv('POSTGRES_TEST_DB', 'moviesdb_test')}"
)

_engine  = create_async_engine(_TEST_DB_URL, echo=False)
_Session = sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)

# ── Shared test credentials ───────────────────────────────────────────────────

ADMIN_EMAIL    = "admin@test.com"
ADMIN_PASSWORD = "Admin123!"
EXPIRES_AT     = "2099-01-01T00:00:00Z"


# ── DB override for FastAPI dependency injection ──────────────────────────────

async def _test_get_db():
    async with _Session() as session:
        yield session


# ── Seed helper (runs after each truncation) ──────────────────────────────────

async def _seed(session: AsyncSession) -> None:
    admin_hash = hash_password(ADMIN_PASSWORD)
    await session.execute(text("""
        INSERT INTO users (email, name, password_hash, role, user_type, created_at)
        VALUES (:email, 'Test Admin', :hash, 'workflow_admin', 'workflow_approver', NOW())
    """), {"email": ADMIN_EMAIL, "hash": admin_hash})

    # Sentinel row: login-issued tokens reference access_requests.id = 0
    await session.execute(text("""
        INSERT INTO access_requests (id, reference_id, requester_id, requested_role,
                                     reason, status, requested_expires_at, created_at, updated_at)
        SELECT 0, '00000000-0000-0000-0000-000000000000', id, 'workflow_admin',
               'system sentinel', 'approved', '2099-01-01 00:00:00+00', NOW(), NOW()
        FROM users WHERE email = :email
        ON CONFLICT (id) DO NOTHING
    """), {"email": ADMIN_EMAIL})

    # A handful of movies for search/get tests
    await session.execute(text("""
        INSERT INTO movies (movie_id, title, release_year, genres) VALUES
          (1,   'Toy Story',       1995, ARRAY['Animation','Comedy','Family']),
          (2,   'Jumanji',         1995, ARRAY['Action','Adventure','Family']),
          (10,  'GoldenEye',       1995, ARRAY['Action','Adventure','Thriller']),
          (50,  'Usual Suspects',  1995, ARRAY['Crime','Mystery','Thriller']),
          (260, 'Star Wars',       1977, ARRAY['Action','Adventure','Sci-Fi'])
        ON CONFLICT (movie_id) DO NOTHING
    """))

    await session.commit()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Truncate all tables and reseed base data before every test."""
    async with _Session() as session:
        await session.execute(text(
            "TRUNCATE movies, audit_log, api_tokens, access_requests, users"
            " RESTART IDENTITY CASCADE"
        ))
        await session.commit()
        await _seed(session)
    yield


@pytest_asyncio.fixture
async def client():
    """AsyncClient wired to the FastAPI app with the test DB and no lifespan."""
    from main import app
    from db.database import get_db

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_db] = _test_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


# ── Token fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def admin_token(client):
    return await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest_asyncio.fixture
async def manager_token(client, admin_token):
    await _register_approver(client, "manager@test.com", "Test Manager", "Manager123!", "manager")
    ref = await _first_pending_ref(client, admin_token, role="manager")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(admin_token))
    return await _login(client, "manager@test.com", "Manager123!")


@pytest_asyncio.fixture
async def full_access_token(client, manager_token):
    await _register_customer(client, "fauser@test.com", "FA User", "FAUser123!", "full_access")
    ref = await _first_pending_ref(client, manager_token, role="full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))
    return await _login(client, "fauser@test.com", "FAUser123!")


@pytest_asyncio.fixture
async def movie_admin_token(client, admin_token):
    await _register_customer(client, "madmin@test.com", "Movie Admin", "MAdmin123!", "movie_admin")
    ref = await _first_pending_ref(client, admin_token, role="movie_admin")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(admin_token))
    return await _login(client, "madmin@test.com", "MAdmin123!")


# ── API helpers (used by fixtures and tests) ──────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/sessions/", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


async def _register_customer(client, email, name, password, role="full_access"):
    return await client.post("/users/", json={
        "email": email, "name": name,
        "create_password": password, "confirm_password": password,
        "role": role, "requested_expires_at": EXPIRES_AT,
    })


async def _register_approver(client, email, name, password, role="manager"):
    return await client.post("/workflow-users/", json={
        "email": email, "name": name,
        "create_password": password, "confirm_password": password,
        "requested_role": role, "reason": "Integration test approver account",
    })


async def _first_pending_ref(client, approver_token: str, role: str) -> str:
    resp = await client.get("/access-requests/", headers=_auth(approver_token))
    assert resp.status_code == 200
    matches = [r for r in resp.json()
               if r["requested_role"] == role and r["status"] == "pending"]
    assert matches, f"No pending {role} request found in queue"
    return matches[0]["reference_id"]
