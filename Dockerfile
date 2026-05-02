# =========================================================
# TTB Label Verifier — single-service Dockerfile
# Three stages:
#   1. frontend-build  — Node 20, builds Vite/React → dist/
#   2. python-build    — Python 3.12, installs deps to /install prefix
#   3. runtime         — slim image, non-root, copies both
# Single container so the deploy URL serves both UI and API.
# =========================================================

# ---- Stage 1: frontend build ----
FROM node:20-alpine AS frontend-build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# In production the React app calls the API on the same origin, so VITE_API_URL
# is set to empty string ('' resolves to relative URLs against location.origin).
ENV VITE_API_URL=""
RUN npm run build

# ---- Stage 2: python build ----
FROM python:3.12-slim AS python-build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY README.md ./
COPY app/ ./app/
RUN pip install --no-cache-dir --prefix=/install .

# ---- Stage 3: runtime ----
FROM python:3.12-slim AS runtime
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
WORKDIR /app

# Python deps
COPY --from=python-build /install /usr/local
# App source
COPY --from=python-build /build/app ./app
# Frontend static bundle (FastAPI serves this from /app/frontend_dist/)
COPY --from=frontend-build /web/dist ./frontend_dist

# Audit log directory (ephemeral on Railway free tier; promoted to a Railway
# volume in production via dashboard — captured in ROADMAP.md). Owned by
# appuser so the FastAPI process can append.
RUN mkdir -p /data && chown appuser:appgroup /data

EXPOSE 8000
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
