"""
errors.py — typed exception hierarchy for the SAT Prep API.

All AppError subclasses carry an HTTP status_code and a public_message
that is safe to return to clients (no SQL, no stack traces).
"""
from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    public_message: str = "internal error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.public_message)
        self.detail = detail or self.public_message


class NotFound(AppError):
    status_code = 404
    public_message = "resource not found"


class Forbidden(AppError):
    status_code = 403
    public_message = "forbidden"


class Conflict(AppError):
    status_code = 409
    public_message = "conflict"


class BadRequest(AppError):
    status_code = 400
    public_message = "bad request"


class Unauthorized(AppError):
    status_code = 401
    public_message = "unauthorized"
