"""FastAPI application factory — wires middleware, CORS, routes.

This module owns:
  - app = FastAPI(...) construction
  - Middleware registration (CORS, secure headers, rate limiting)
  - Router inclusion

Import `app` from here in tests and ASGI servers.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

_is_testing = (
    os.environ.get("TESTING", "0") == "1"
    or os.environ.get("PYTEST_CURRENT_TEST") is not None
)

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

# Stateful auth / cookies unused — disallow credentials so wildcard origins remain valid.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Railway / Docker healthcheck."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static frontend (mounted only when frontend/dist/ exists in the container).
# In local dev the React app is served by Vite on port 5173; in production the
# Dockerfile builds the frontend and copies dist/ into /app/frontend_dist/.
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST_DIR", "/app/frontend_dist"))


def _safe_frontend_file(full_path: str) -> Path | None:
    """Serve only paths that resolve inside `_FRONTEND_DIST` (block path traversal).

    Rejects '..', NUL, Windows drive letters, absolute segments, etc. via pathlib
    resolution + `.relative_to()` check.
    """
    # Drop leading slashes so Path("/foo") joining doesn't ignore the prefix.
    rel = PurePosixPath(full_path.replace("\\", "/").lstrip("/"))
    candidate = (_FRONTEND_DIST / Path(*rel.parts)).resolve()
    try:
        candidate.relative_to(_FRONTEND_DIST.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


if _FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )

    @app.get("/")
    def _index() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def _spa_fallback(full_path: str) -> FileResponse:
        # SPA fallback: static file if safe path exists, else shell.
        resolved = _safe_frontend_file(full_path)
        if resolved is not None:
            return FileResponse(resolved)
        return FileResponse(_FRONTEND_DIST / "index.html")
