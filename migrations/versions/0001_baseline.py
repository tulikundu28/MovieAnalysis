"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-05-26

"""
from typing import Sequence, Union
from alembic import op

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ENUMs — idempotent via exception handler so this is safe on existing DBs
    for stmt in [
        "CREATE TYPE user_role AS ENUM ('free', 'full_access', 'movie_admin', 'workflow_admin', 'manager')",
        "CREATE TYPE user_type AS ENUM ('movie_customer', 'workflow_approver')",
        "CREATE TYPE request_status AS ENUM ('pending', 'approved', 'denied', 'revoked', 'cancelled')",
        "CREATE TYPE requested_role AS ENUM ('full_access', 'movie_admin', 'workflow_admin', 'manager')",
    ]:
        op.execute(f"DO $$ BEGIN {stmt}; EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            movie_id     INTEGER PRIMARY KEY,
            title        TEXT NOT NULL,
            release_year INTEGER,
            genres       TEXT[]
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_genres ON movies USING GIN (genres)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_release_year ON movies (release_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_title_trgm ON movies USING GIN (title gin_trgm_ops)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            name          TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role          user_role NOT NULL DEFAULT 'free',
            user_type     user_type NOT NULL DEFAULT 'movie_customer',
            expires_at    TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id                   SERIAL PRIMARY KEY,
            reference_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            requester_id         INTEGER NOT NULL REFERENCES users(id),
            requested_role       requested_role NOT NULL,
            reason               TEXT NOT NULL,
            status               request_status NOT NULL DEFAULT 'pending',
            reviewed_by          INTEGER REFERENCES users(id),
            review_comment       TEXT,
            requested_expires_at TIMESTAMPTZ NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            request_id INTEGER REFERENCES access_requests(id),
            tier       user_role NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked    BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id         SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL REFERENCES access_requests(id),
            actor_id   INTEGER REFERENCES users(id),
            action     TEXT NOT NULL,
            reason     TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_access_requests_requester ON access_requests(requester_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_request ON audit_log(request_id)")

    # Seed admin user and login sentinel (idempotent)
    op.execute("""
        INSERT INTO users (email, name, password_hash, role, user_type) VALUES (
            'tuli.ku09@gmail.com', 'Tuli',
            '$2b$12$5L2NxqX8pdfupN9rxtPM6u1g3IszvvClS.C8j3oEbt3PGH3A6sJTC',
            'workflow_admin', 'workflow_approver'
        ) ON CONFLICT (email) DO NOTHING
    """)
    op.execute("""
        INSERT INTO access_requests (id, reference_id, requester_id, requested_role, reason, status, requested_expires_at, created_at, updated_at)
        SELECT 0, '00000000-0000-0000-0000-000000000000', id, 'workflow_admin',
               'system sentinel for direct login tokens', 'approved',
               '2099-01-01 00:00:00+00', NOW(), NOW()
        FROM users WHERE email = 'tuli.ku09@gmail.com'
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS api_tokens")
    op.execute("DROP TABLE IF EXISTS access_requests")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS movies")
    op.execute("DROP TYPE IF EXISTS requested_role")
    op.execute("DROP TYPE IF EXISTS request_status")
    op.execute("DROP TYPE IF EXISTS user_type")
    op.execute("DROP TYPE IF EXISTS user_role")
