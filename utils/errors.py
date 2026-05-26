from fastapi import HTTPException, status as http_status


class AppError(HTTPException):
    """Base class — never raised directly."""


# ── 400 Bad Request ────────────────────────────────────────────────────────────

class PasswordMismatchError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_400_BAD_REQUEST, "Passwords do not match")


class InvalidRoleError(AppError):
    def __init__(self, detail: str):
        super().__init__(http_status.HTTP_400_BAD_REQUEST, detail)


class CommentRequiredError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_400_BAD_REQUEST, "Comment required when denying a request")


# ── 401 Unauthorized ───────────────────────────────────────────────────────────

class InvalidCredentialsError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_401_UNAUTHORIZED, "Invalid credentials")


class TokenInvalidError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


class TokenRevokedError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_401_UNAUTHORIZED, "Token has been revoked or does not exist")


# ── 403 Forbidden ──────────────────────────────────────────────────────────────

class InsufficientPermissionsError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_403_FORBIDDEN, "Insufficient permissions")


class NotAuthorisedToViewError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_403_FORBIDDEN, "Not authorised to view this request")


class NotAuthorisedToCancelError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_403_FORBIDDEN, "Not authorised to cancel this request")


class NotAuthorisedToReviewError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_403_FORBIDDEN, "Not authorised to review this request")


class NotAuthorisedToRevokeError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_403_FORBIDDEN, "Not authorised to revoke this request")


# ── 404 Not Found ──────────────────────────────────────────────────────────────

class MovieNotFoundError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_404_NOT_FOUND, "Movie not found")


class RequestNotFoundError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_404_NOT_FOUND, "Request not found")


# ── 409 Conflict ───────────────────────────────────────────────────────────────

class EmailAlreadyRegisteredError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_409_CONFLICT, "Email already registered")


class DuplicatePendingRequestError(AppError):
    def __init__(self, reference_id: str):
        super().__init__(
            http_status.HTTP_409_CONFLICT,
            {"message": "You already have a pending request", "reference_id": reference_id},
        )


class RequestAlreadyReviewedError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_409_CONFLICT, "Request has already been reviewed")


class RequestNotCancellableError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_409_CONFLICT, "Only pending requests can be cancelled")


class RequestNotRevocableError(AppError):
    def __init__(self):
        super().__init__(http_status.HTTP_409_CONFLICT, "Only approved requests can be revoked")
