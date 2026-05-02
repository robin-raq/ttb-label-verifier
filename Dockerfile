# =========================================================
# TTB Label Verifier — Backend Dockerfile
# Multi-stage build: install deps → lean runtime image
# =========================================================

# ---- Stage 1: build ----
FROM python:3.12-slim AS build

WORKDIR /build

# Install build toolchain (needed for some C-extension deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what pip needs to install the package
COPY pyproject.toml ./
COPY README.md ./
COPY app/ ./app/

# Install production deps (not editable) into a prefix we can copy
RUN pip install --no-cache-dir --prefix=/install .

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from build stage
COPY --from=build /install /usr/local

# Copy application source
COPY --from=build /build/app ./app

# Audit log volume mount point (Railway mounts persistent disk here)
VOLUME ["/data"]

# Expose default port; Railway overrides via $PORT
EXPOSE 8000

# Switch to non-root
USER appuser

# Healthcheck — Railway uses this to verify the service is up
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
