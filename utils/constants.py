"""Application-wide constants: column names, enums, config values, and pagination defaults."""
import os
from datetime import datetime, timezone

class MovieColumns:
    MOVIE_ID = "movie_id"
    TITLE = "title"
    RELEASE_YEAR = "release_year"
    GENRES = "genres"

MOVIES_TABLE = "movies"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
INSERTED_KEY = "inserted"
BATCH_SIZE = 500
CSV_TITLE_COL = "title"
CSV_GENRES_COL = "genres"
NO_GENRES_VALUE = "(no genres listed)"
YEAR_EXTRACT_PATTERN = r"\((\d{4})\)$"
YEAR_STRIP_PATTERN = r"\s*\(\d{4}\)\s*$"
CSV_TO_DB_COLUMNS = {"movieId": MovieColumns.MOVIE_ID}
GENRE_SEPARATOR = "|"

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))
LOGIN_SENTINEL_REQUEST_ID = 0

TOKEN_TYPE = "bearer"
REGISTRATION_REASON = "Account registration"
EXPIRY_AUDIT_REASON = "Role expired or all access tokens revoked"
WORKFLOW_EXPIRY_DATE = datetime(2099, 1, 1, tzinfo=timezone.utc)


class UserRole:
    FREE           = "free"
    FULL_ACCESS    = "full_access"
    MOVIE_ADMIN    = "movie_admin"
    WORKFLOW_ADMIN = "workflow_admin"
    MANAGER        = "manager"


class UserType:
    MOVIE_CUSTOMER    = "movie_customer"
    WORKFLOW_APPROVER = "workflow_approver"


class RequestStatus:
    PENDING   = "pending"
    APPROVED  = "approved"
    DENIED    = "denied"
    REVOKED   = "revoked"
    CANCELLED = "cancelled"


class AuditAction:
    SUBMITTED = "submitted"
    APPROVED  = "approved"
    DENIED    = "denied"
    REVOKED   = "revoked"
    CANCELLED = "cancelled"
    EXPIRED   = "expired"


DOWNGRADEABLE_ROLES = (UserRole.FULL_ACCESS, UserRole.MOVIE_ADMIN)
