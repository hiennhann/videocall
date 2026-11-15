from enum import StrEnum


class ErrorCode(StrEnum):
    REGISTRATION_DISABLED = "REGISTRATION_DISABLED"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_REFRESH_TOKEN = "INVALID_REFRESH_TOKEN"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    GUEST_DISABLED = "GUEST_DISABLED"
    MAINTENANCE_MODE = "MAINTENANCE_MODE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    GUEST_NOT_ALLOWED = "GUEST_NOT_ALLOWED"
    WRONG_PASSWORD = "WRONG_PASSWORD"
    PASSWORD_UNCHANGED = "PASSWORD_UNCHANGED"


class AuthError(Exception):
    def __init__(self, code: ErrorCode, *, retry_after: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
