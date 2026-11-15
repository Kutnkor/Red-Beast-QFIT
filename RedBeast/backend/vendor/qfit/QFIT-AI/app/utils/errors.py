"""Typed errors. Only `code` and `message` ever reach API clients."""
from __future__ import annotations


class QFitError(Exception):
    code = "internal_error"
    status_code = 500
    retryable = False

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable,
                "details": self.details}


class InvalidInputError(QFitError):
    code, status_code = "invalid_input", 422


class NotFoundError(QFitError):
    code, status_code = "not_found", 404


class UpstreamError(QFitError):
    """An external service answered with an error or an unreadable response."""
    code, status_code, retryable = "upstream_error", 502, True


class UpstreamUnavailableError(UpstreamError):
    """An external service could not be reached at all (network, DNS, timeout)."""
    code, status_code = "upstream_unavailable", 504


class AIUnavailableError(QFitError):
    code, status_code = "ai_unavailable", 503


class RateLimitedError(QFitError):
    code, status_code, retryable = "rate_limited", 429, True


class UnauthorizedError(QFitError):
    code, status_code = "unauthorized", 401
