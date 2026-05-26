from sqlalchemy import Table, Column, Integer, Text, MetaData, TIMESTAMP, Boolean, text

from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID

TZ = TIMESTAMP(timezone=True)

from utils.constants import MovieColumns, MOVIES_TABLE

metadata = MetaData()

movies_table = Table(
    MOVIES_TABLE,
    metadata,
    Column(MovieColumns.MOVIE_ID, Integer, primary_key=True),
    Column(MovieColumns.TITLE, Text, nullable=False),
    Column(MovieColumns.RELEASE_YEAR, Integer),
    Column(MovieColumns.GENRES, ARRAY(Text))
)

user_role_enum = ENUM('free', 'full_access', 'movie_admin', 'workflow_admin', 'manager', name='user_role', create_type=False)
user_type_enum = ENUM('movie_customer', 'workflow_approver', name='user_type', create_type=False)

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", user_role_enum, nullable=False, server_default="free"),
    Column("user_type", user_type_enum, nullable=False, server_default="movie_customer"),
    Column("expires_at", TZ),
    Column("created_at", TZ, nullable=False)
)

request_status_enum = ENUM('pending', 'approved', 'denied', name='request_status', create_type=False)
requested_role_enum = ENUM('full_access', 'movie_admin', 'workflow_admin', 'manager', name='requested_role', create_type=False)

access_requests_table = Table(
    "access_requests",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("reference_id", UUID(as_uuid=False), nullable=False, server_default=text("gen_random_uuid()")),
    Column("requester_id", Integer, nullable=False),
    Column("requested_role", requested_role_enum, nullable=False),
    Column("reason", Text, nullable=False),
    Column("status", request_status_enum, nullable=False, server_default="pending"),
    Column("reviewed_by", Integer),
    Column("review_comment", Text),
    Column("requested_expires_at", TZ, nullable=False),
    Column("created_at", TZ, nullable=False),
    Column("updated_at", TZ, nullable=False)
)

api_tokens_table = Table(
    "api_tokens",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("request_id", Integer, nullable=False),
    Column("tier", user_role_enum, nullable=False),
    Column("token", Text, nullable=False, unique=True),
    Column("expires_at", TZ, nullable=False),
    Column("revoked", Boolean, nullable=False, server_default="false"),
    Column("created_at", TZ, nullable=False)
)

audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("request_id", Integer, nullable=False),
    Column("actor_id", Integer, nullable=False),
    Column("action", Text, nullable=False),
    Column("reason", Text),
    Column("created_at", TZ, nullable=False)
)