"""FastAPI application factory — wires middleware, CORS, routes.

This module owns:
  - app = FastAPI(...) construction
  - Middleware registration (CORS, secure headers, rate limiting)
  - Router inclusion

Import `app` from here in tests and ASGI servers.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.routes import router
from app.api.security import SecureHeadersMiddleware

# ---------------------------------------------------------------------------
# Rate limiter (slowapi) — 30 req/min per IP on verify endpoints.
# In test mode (TESTING=1) the limit is raised so unit tests don't trip it.
# ---------------------------------------------------------------------------

_is_testing = os.environ.get("TESTING", "0") == "1" or os.environ.get("PYTEST_CURRENT_TEST") is not None

_rate_limit = "10000/minute" if _is_testing else "30/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit])

# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TTB Label Verifier",
    description="AI-powered TTB alcohol-label compliance verification prototype.",
    version="0.1.0",
)

# Attach limiter to app state so slowapi middleware can find it
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Middleware (order matters: applied bottom-up to requests, top-down to responses)
# ---------------------------------------------------------------------------

# 1. Security headers (outermost — ensures headers on all responses)
app.add_middleware(SecureHeadersMiddleware)

# 2. Rate limiting
app.add_middleware(SlowAPIMiddleware)

# 3. CORS — only allow configured origins in production
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(router)
