"""Secure headers middleware — FR-015.

Applies production-grade HTTP security headers when:
  - ENV=production  OR
  - SECURE_HEADERS_ENABLED=1

Uses the `secure` package which mirrors Helmet.js for Python.

CSP in production MUST NOT include 'unsafe-inline' or 'unsafe-eval' (FR-015).
Local dev may use a looser CSP if needed for Swagger/HMR (documented in README).
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _is_production() -> bool:
    return (
        os.environ.get("ENV", "").lower() == "production"
        or os.environ.get("SECURE_HEADERS_ENABLED", "0") == "1"
    )


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers on every response when in production mode."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        if _is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'self'"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"

        return response
